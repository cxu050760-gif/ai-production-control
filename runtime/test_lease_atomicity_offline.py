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


if __name__ == "__main__":
    unittest.main()
