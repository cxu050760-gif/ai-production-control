#!/usr/bin/env python3
"""GATE-2#6 (hardening 2026-08-31): lease atomicity/revocation offline tests.

Covers the four defects the audit found in controller_lease.py:
  A1  concurrent acquire() must serialise (previously two callers could both
      compute generation+1 and both win — fencing broken)
  A2  a revoked lease is refused by check_execute_right (the revoked flag
      previously existed but was never read) and cannot be renewed
  A3  a malformed expires_at fails CLOSED (previously raised ValueError that
      callers caught-and-skipped -> fail-open)
  A4  a busy lock raises LeaseLockTimeout (fail-closed), and a stale lock
      older than STALE_LOCK_SECONDS is reclaimed

All offline: tmp lease paths only, never the real state/controller_lease.json.
"""
import datetime
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import controller_lease as cl  # noqa: E402


def _tmp_lease(td) -> str:
    return str(Path(td) / "state" / "controller_lease.json")


class LeaseAtomicityTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.path = _tmp_lease(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_a1_concurrent_acquire_serialises(self):
        results = []
        errors = []
        barrier = threading.Barrier(4)

        def worker():
            try:
                barrier.wait(timeout=10)
                results.append(cl.acquire("controller-x", path=self.path)["generation"])
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        self.assertEqual(errors, [])
        # Every acquire must observe a DISTINCT generation: fencing intact.
        self.assertEqual(sorted(results), [1, 2, 3, 4])
        # The surviving file holds exactly the highest generation.
        final = cl.load_lease(self.path)
        self.assertEqual(final["generation"], 4)

    def test_a2_revoked_lease_refused_and_not_renewable(self):
        lease = cl.acquire("controller-x", path=self.path)
        r = cl.revoke(self.path, reason="operator takeover")
        self.assertTrue(r["ok"])
        chk = cl.check_execute_right("controller-x", lease["generation"], path=self.path)
        self.assertFalse(chk["ok"])
        self.assertEqual(chk["reason"], cl.LEASE_REVOKED)
        # Renewal of a revoked lease must not resurrect authority.
        rn = cl.renew("controller-x", lease["generation"], path=self.path)
        self.assertFalse(rn["ok"])
        self.assertEqual(rn["reason"], cl.LEASE_REVOKED)
        # Fresh acquire starts a clean, non-revoked generation.
        fresh = cl.acquire("controller-y", path=self.path)
        self.assertFalse(fresh.get("revoked"))
        self.assertTrue(cl.check_execute_right("controller-y", fresh["generation"], path=self.path)["ok"])

    def test_a3_malformed_expires_at_fails_closed(self):
        cl.acquire("controller-x", path=self.path)
        import json
        data = json.loads(Path(self.path).read_text(encoding="utf-8"))
        data["expires_at"] = "not-a-timestamp"
        Path(self.path).write_text(json.dumps(data), encoding="utf-8")
        chk = cl.check_execute_right("controller-x", data["generation"], path=self.path)
        self.assertFalse(chk["ok"])
        self.assertEqual(chk["reason"], cl.LEASE_EXPIRED)
        self.assertIn("malformed", chk["error"])

    def test_a4_busy_lock_times_out_and_stale_lock_self_heals(self):
        lease = cl.acquire("controller-x", path=self.path)
        lock_path = Path(self.path + ".lock")
        # Simulate a live holder: create the lock and hold it.
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            with self.assertRaises(cl.LeaseLockTimeout):
                cl.acquire("controller-y", path=self.path, lock_timeout=0.05)
        finally:
            os.close(fd)
            lock_path.unlink(missing_ok=True)
        # Simulate a STALE holder: lock file older than STALE_LOCK_SECONDS.
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        stale = time.time() - (cl.STALE_LOCK_SECONDS + 5)
        os.utime(lock_path, (stale, stale))
        try:
            fresh = cl.acquire("controller-y", path=self.path, lock_timeout=2.0)
            self.assertEqual(fresh["generation"], lease["generation"] + 1)
        finally:
            Path(str(self.path) + ".lock").unlink(missing_ok=True)

    def test_a5_concurrent_renew_vs_acquire_no_lost_update(self):
        lease = cl.acquire("controller-x", path=self.path)
        outs = {"renew": None, "acquire": None}

        def do_renew():
            outs["renew"] = cl.renew("controller-x", lease["generation"], path=self.path)

        def do_acquire():
            outs["acquire"] = cl.acquire("controller-y", path=self.path)

        t1 = threading.Thread(target=do_renew)
        t2 = threading.Thread(target=do_acquire)
        t1.start(); t2.start(); t1.join(timeout=30); t2.join(timeout=30)
        final = cl.load_lease(self.path)
        # Whatever order won, the file must be internally consistent (no torn
        # write): generation is an int and exactly one of the two outcomes.
        self.assertIsInstance(final["generation"], int)
        self.assertIn(final["generation"], (lease["generation"], lease["generation"] + 1))
        self.assertIsNotNone(outs["renew"])
        self.assertIsNotNone(outs["acquire"])


class StateRootSeamTests(unittest.TestCase):
    """GATE-3 补强回归钉（v16 §4-A 欠账清零 2026-08-31）。

    controller_lease 曾恒解析仓根真实 state/controller_lease.json（audit hook
    实证全套件回归中 admission 用例对真实租约续约写入，时间依赖性污染）。
    现约定与 runtime.py/harness_verify.py 一致：设 APC_RUNTIME_STATE_ROOT 时
    lease 落 env 根；不设时保持仓根默认（生产行为不变）。
    """

    def test_s1_env_root_isolates_lease_ops(self):
        real_path = Path(cl.default_lease_path())
        # 前置：真实仓根文件 mtime 指纹
        before = real_path.stat().st_mtime_ns if real_path.exists() else None
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        old = os.environ.get("APC_RUNTIME_STATE_ROOT")
        os.environ["APC_RUNTIME_STATE_ROOT"] = td.name
        self.addCleanup(lambda: (os.environ.pop("APC_RUNTIME_STATE_ROOT", None),
                                 old and os.environ.__setitem__("APC_RUNTIME_STATE_ROOT", old)))
        try:
            self.assertEqual(Path(cl.default_lease_path()),
                             Path(td.name) / "state" / "controller_lease.json")
            res = cl.acquire("controller-seam", path=None)  # 走 default → env 根
            self.assertGreaterEqual(int(res["generation"]), 1)
            self.assertEqual(res["holder"], "controller-seam")
            self.assertTrue((Path(td.name) / "state" / "controller_lease.json").exists())
        finally:
            if before is not None:
                self.assertEqual(real_path.stat().st_mtime_ns, before,
                                 "真实仓根 lease 文件被测试触碰")
            else:
                self.assertFalse(real_path.exists(),
                                 "真实仓根 lease 文件被测试创建")

    def test_s2_no_env_keeps_repo_default(self):
        old = os.environ.pop("APC_RUNTIME_STATE_ROOT", None)
        self.addCleanup(lambda: old and os.environ.__setitem__(
            "APC_RUNTIME_STATE_ROOT", old))
        p = Path(cl.default_lease_path())
        self.assertEqual(p.name, "controller_lease.json")
        self.assertEqual(p.parent.name, "state")


class LeaseStealReverifyTests(unittest.TestCase):
    """P2-2/P3-4（盲审 fa5406f）：_lease_lock rename-steal 复验钉测。

    模拟竞争：A 判定 stale → 在 A rename 之前，B 已偷走 stale 并在原路径重建
    新鲜锁；A 的 rename 实际偷到 B 的新鲜锁 → 复验必须恢复 B 的锁并按 busy
    重试，绝不产生双持有者。
    """

    def test_v1_never_steals_fresh_rebuild(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        lease = Path(td.name) / "lease.json"
        lock = Path(str(lease) + ".lock")
        lease.write_text("{}", encoding="utf-8")
        lock.write_bytes(b"")  # 旧 stale 锁
        stale_mtime = time.time() - cl.STALE_LOCK_SECONDS - 60
        os.utime(lock, (stale_mtime, stale_mtime))
        real_rename = os.rename
        state = {"swapped": False}

        def swapping_rename(src, dst):
            # B 的动作：在 A 的 stat 与 rename 之间偷走 stale 锁并重建新鲜锁
            if str(src) == str(lock) and not state["swapped"]:
                state["swapped"] = True
                lock.unlink()
                lock.write_bytes(b"")
            return real_rename(src, dst)

        with mock.patch.object(cl.os, "rename", side_effect=swapping_rename):
            with self.assertRaises(cl.LeaseLockTimeout):
                cl._lease_lock(lease, timeout=0.05)
        self.assertTrue(lock.exists(), "活跃持有者的新鲜锁必须被恢复原位")
        leftovers = list(Path(td.name).glob("*.stolen-*"))
        self.assertEqual(leftovers, [], "墓碑必须清理")

    def test_v2_genuine_stale_takeover_unaffected(self):
        """正向钉：无竞争时真 stale 锁照常接管（复验不得误伤正常路径）。"""
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        lease = Path(td.name) / "lease.json"
        lock = Path(str(lease) + ".lock")
        lease.write_text("{}", encoding="utf-8")
        lock.write_bytes(b"")
        stale_mtime = time.time() - cl.STALE_LOCK_SECONDS - 60
        os.utime(lock, (stale_mtime, stale_mtime))
        fd, lock_path = cl._lease_lock(lease, timeout=2.0)
        try:
            self.assertEqual(lock_path, lock)
            self.assertTrue(lock.exists())
        finally:
            cl._release_lease_lock(fd, lock_path)
        self.assertFalse(lock.exists())


if __name__ == "__main__":
    unittest.main()
