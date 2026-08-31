# -*- coding: utf-8 -*-
"""controller_lease 离线测试（\u00a734 Controller \u7ea7 fencing 补充，V1.1-blackbox）。

覆盖\u5baa\u6cd5 :1226-1242 的 fencing 语义：
  1) acquire = generation+1（新 Controller 接管，老代立即失效）
  2) check_execute_right：当前代 + 同 holder + 未过期 -> OK
  3) STALE_GENERATION：老 generation 执行 effect 被拒（老权失效）
  4) LEASE_EXPIRED：超时后未续约被拒（fail-closed）
  5) renew：同代同 holder 可续约；跨代续约被拒
  6) 无 lease -> NO_LEASE（fail-closed）
"""
import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest
from importlib import import_module
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
lease = import_module("controller_lease")


class ControllerLeaseTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="lease-test-")
        self.path = os.path.join(self.td, "controller_lease.json")

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def _load(self):
        return json.loads(Path(self.path).read_text(encoding="utf-8"))

    def test_acquire_new_generation_evicts_old(self):
        """新 Controller 接管 generation+1；老代（旧 generation）随后 check 被拒。"""
        l1 = lease.acquire("controller-A", path=self.path)
        self.assertEqual(l1["generation"], 1)
        self.assertEqual(l1["holder"], "controller-A")
        l2 = lease.acquire("controller-B", path=self.path)  # B 接管
        self.assertEqual(l2["generation"], 2)
        # A 用老代 1 执行 effect -> STALE_GENERATION（老权失效 \u00a734）
        r = lease.check_execute_right("controller-A", 1, path=self.path)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], lease.STALE_GENERATION)
        # B 用新代 2 执行 -> OK
        r2 = lease.check_execute_right("controller-B", 2, path=self.path)
        self.assertTrue(r2["ok"])
        self.assertEqual(r2["reason"], lease.OK)

    def test_check_requires_matching_holder(self):
        """generation 对但 holder 不符 -> 无权限执行。"""
        lease.acquire("controller-A", path=self.path)
        r = lease.check_execute_right("controller-C", 1, path=self.path)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], lease.STALE_GENERATION)

    def test_lease_expiry_denies_execution(self):
        """超时未续约 -> LEASE_EXPIRED（fail-closed）。"""
        now = datetime.datetime(2026, 8, 31, 12, 0, 0, tzinfo=datetime.timezone.utc)
        lease.acquire("controller-A", ttl_seconds=600, path=self.path, now=now)
        later = now + datetime.timedelta(seconds=601)
        r = lease.check_execute_right("controller-A", 1, path=self.path, now=later)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], lease.LEASE_EXPIRED)

    def test_renew_within_generation(self):
        """同代同 holder 续约成功；续约后 check 通过。"""
        now = datetime.datetime(2026, 8, 31, 12, 0, 0, tzinfo=datetime.timezone.utc)
        l1 = lease.acquire("controller-A", ttl_seconds=600, path=self.path, now=now)
        renewed = lease.renew("controller-A", l1["generation"], ttl_seconds=600, path=self.path,
                              now=now + datetime.timedelta(seconds=500))
        self.assertEqual(renewed["generation"], l1["generation"])
        r = lease.check_execute_right("controller-A", l1["generation"], path=self.path,
                                      now=now + datetime.timedelta(seconds=700))
        self.assertTrue(r["ok"])

    def test_renew_cross_generation_rejected(self):
        """旧代续约被拒（已被新接管者超越）。"""
        l1 = lease.acquire("controller-A", path=self.path)
        lease.acquire("controller-B", path=self.path)  # B 接管 -> gen 2
        r = lease.renew("controller-A", l1["generation"], path=self.path)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], lease.STALE_GENERATION)

    def test_no_lease_fail_closed(self):
        """无 lease -> NO_LEASE（无法证明权限即拒绝）。"""
        r = lease.check_execute_right("controller-A", 1, path=self.path)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], lease.NO_LEASE)

    def test_lease_file_not_tracked_by_git(self):
        """lease 默认落在 state/ 下（B3 非跟踪）——模块默认路径断言。"""
        self.assertTrue(lease.LEASE_FILE.startswith("state/"))


if __name__ == "__main__":
    unittest.main()