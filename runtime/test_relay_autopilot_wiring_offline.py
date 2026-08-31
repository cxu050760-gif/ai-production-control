# -*- coding: utf-8 -*-
"""relay_autopilot wiring 接线测试（§59/§55/§34，调度准入三闸 + drive lease）。

全部离线：admission_checks 走真实 config（cost_policy.json / capability-registry.json
在仓内），但只读计算不消耗真实额度；lease 用 tmp 文件不碰真实 state。
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from importlib import import_module
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, _SCRIPTS)
ap = import_module("relay_autopilot")


class AdmissionGateTests(unittest.TestCase):
    """admission_checks 三闸：正常目标通过；缺上下文信息拒绝自动入队。"""

    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="wiring-test-")

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def _goal(self, **kw):
        g = {
            "goal_id": "W-TEST-001",
            "title": "mechanical test goal",
            "objective": "mechanical read config and format output",
            "scope": ["config"],
            "acceptance": ["output correct"],
            "priority": 1,
        }
        g.update(kw)
        return g

    def test_wiring_modules_available(self):
        self.assertTrue(ap._WIRING_AVAILABLE)

    def test_normal_goal_admitted(self):
        r = ap.admission_checks(self._goal())
        self.assertTrue(r["admitted"], r["reasons"])
        for gate in ("cost", "context", "lease"):
            self.assertIn(gate, r["checks"], f"gate {gate} missing")

    def test_cost_gate_present(self):
        r = ap.admission_checks(self._goal())
        c = r["checks"]["cost"]
        self.assertIn("verdict", c)
        self.assertIn("recommended_route", c)
        self.assertIn("expected_total_cost", c)

    def test_context_gate_records_decision(self):
        """missing required_info -> 记录 §55 自愈分支决策（正常链路 SWITCH、不误拦）。"""
        goal = self._goal(required_info=["missing-special-brain-artifact"])
        r = ap.admission_checks(goal)
        self.assertTrue(r["admitted"], r["reasons"])
        decision = r["checks"]["context"]["decision"]
        self.assertIn(decision,
                      {"SUFFICIENT", "SWITCH_LOCAL_BRAIN", "SWITCH_ALLOWED_PROVIDER",
                       "DESENSITIZE_RETRY", "HUMAN_AUTHORIZATION", "BLOCKED"})

    def test_context_gate_human_blocked_rejects(self):
        """policy 双 Human 授权且无可用分支 -> BLOCKED 拒绝自动入队。"""
        goal = self._goal(required_info=["needs-owner-review-flag"], admission={"allow_human_authorization": False})
        # monkeypatch 策略以强制 BLOCKED 路径
        import context_sufficiency as cs
        orig = cs._load_policy
        cs._load_policy = lambda path=None: {"completeness_threshold": 1.0, "min_fallback_brains": 99,
                                              "min_alternate_providers": 99, "allow_human_authorization": False}
        self.addCleanup(setattr, cs, "_load_policy", orig)
        r = ap.admission_checks(goal)
        self.assertFalse(r["admitted"])
        self.assertTrue(any("context-gate" in x for x in r["reasons"]), r["reasons"])

    def test_lease_gate_present(self):
        r = ap.admission_checks(self._goal())
        self.assertIn("lease", r["checks"])


class LeaseModuleTests(unittest.TestCase):
    """controller_lease 模块 §34 fencing 语义（薄层，与 controller_lease 单测互补）。"""

    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="lease-wiring-")
        self.path = os.path.join(self.td, "controller_lease.json")

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_takeover_evicts_old_authority(self):
        import controller_lease as cl
        l1 = cl.acquire("controller-X", path=self.path)
        l2 = cl.acquire("controller-Y", path=self.path)
        self.assertGreater(l2["generation"], l1["generation"])
        # 老代执行被拒（老权失效 §34）
        r = cl.check_execute_right("controller-X", l1["generation"], path=self.path)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], cl.STALE_GENERATION)
        # 新代执行通过
        r2 = cl.check_execute_right("controller-Y", l2["generation"], path=self.path)
        self.assertTrue(r2["ok"])

    def test_expired_lease_denies(self):
        import datetime
        import controller_lease as cl
        now = datetime.datetime(2026, 8, 31, 12, 0, 0, tzinfo=datetime.timezone.utc)
        cl.acquire("controller-X", ttl_seconds=60, path=self.path, now=now)
        later = now + datetime.timedelta(seconds=61)
        r = cl.check_execute_right("controller-X", 1, path=self.path, now=later)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], cl.LEASE_EXPIRED)


if __name__ == "__main__":
    unittest.main()