# -*- coding: utf-8 -*-
"""relay_autopilot wiring 接线测试（§59/§55/§34，调度准入三闸 + drive lease）。

GATE-3 隔离改造（hardening 2026-08-31）：admission_checks 依赖的三个闸全部
patch 到 tmp 假实现，本文件不读写真实 state/（既不碰 E:\WB 也不碰仓内 state/）：

  cost_router.load_policy         -> 最小合成 policy（见 _FAKE_POLICY 注释）
  cost_router.load_registry_costs -> {}
  cost_router.load_state          -> cost_router.default_state()（纯内存假状态）
  cost_router.save_state          -> 落到本用例 tmp 目录。do_route 有意不被 patch
                                     （真逻辑跑在假数据上），但它内部会持久化状态；
                                     不重定向 save_state 就会写真实
                                     state/cost_router_state.json
  controller_lease.load_lease     -> 有效租约 {"generation":9,"holder":"relay_autopilot",
                                     "expires_at":"2099-01-01T00:00:00Z"}
  controller_lease.check_execute_right -> {"ok": True}
  controller_lease.acquire        -> 返回同一有效租约（本组用例不会走到）

do_route / context_sufficiency.route 不 patch：真逻辑跑在假数据上。
config 只读文件（cost_policy.json 等）也不再被触碰——policy 完全由测试提供。
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, _SCRIPTS)
ap = import_module("relay_autopilot")

import context_sufficiency as cs  # noqa: E402  (blocked-分支用例 monkeypatch _load_policy)
import controller_lease as cl  # noqa: E402
import cost_router as cr  # noqa: E402

_LEASE = {
    "schema": cl.SCHEMA,
    "generation": 9,
    "holder": "relay_autopilot",
    "issued_at": "2098-01-01T00:00:00Z",
    "expires_at": "2099-01-01T00:00:00Z",
}

# 假 policy 必须是 do_route 可运行的最小合法结构：空 dict 会让 route_options 为空，
# do_route 在选择 rec 时抛 StopIteration -> cost 闸被 skip -> checks 缺 cost。
# 全部单价缺失 -> ETC=None -> verdict=UNDETERMINED（不误拦，不触发写盘熔断路径）。
_FAKE_POLICY = {
    "unit_prices": {},
    "route_options": {
        "weak": {"worker": "worker-fake", "reviewer": "", "note": "fake"},
        "hybrid": {"worker": "worker-fake", "reviewer": "reviewer-fake", "note": "fake"},
        "strong": {"worker": "reviewer-fake", "reviewer": "reviewer-fake", "note": "fake"},
    },
    "circuit_breaker": {"consecutive_breach_limit": 2, "no_progress_limit": 3},
    "rework_probability": {"low": 0.1, "mid": 0.3, "high": 0.5},
    "goal_type_keywords": {},
    "max_review_cycles": 3,
    "reference_tokens_per_call": 2000,
    "tokens_est_default": 2000,
    "budget": {"default_budget_threshold": 0.5},
}


class AdmissionGateTests(unittest.TestCase):
    """admission_checks 三闸：正常目标通过；缺上下文信息拒绝自动入队。"""

    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="wiring-test-")
        self._isolate_gates()

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def _isolate_gates(self):
        """把三闸依赖 patch 到 tmp 假实现（GATE-3：绝不触真实 state/）。"""
        td = self.td

        def fake_load_policy(path=None):
            return dict(_FAKE_POLICY)

        def fake_load_registry_costs(path=None):
            return {}

        def fake_load_state(path=None):
            return cr.default_state()

        def fake_save_state(state, path=None):
            # 重定向到 tmp：do_route 内部会持久化，不能让它写真实 state/
            p = Path(td) / "cost_router_state.json"
            p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            return p

        def fake_load_lease(path=None):
            return dict(_LEASE)

        def fake_check_execute_right(controller_id, generation, path=None, now=None):
            return {"schema": cl.SCHEMA, "ok": True, "reason": cl.OK, "lease": dict(_LEASE)}

        def fake_acquire(controller_id, ttl_seconds=cl.DEFAULT_LEASE_SECONDS, path=None,
                         now=None, lock_timeout=cl.DEFAULT_LOCK_TIMEOUT):
            return dict(_LEASE)

        for patcher in (
            mock.patch.object(cr, "load_policy", fake_load_policy),
            mock.patch.object(cr, "load_registry_costs", fake_load_registry_costs),
            mock.patch.object(cr, "load_state", fake_load_state),
            mock.patch.object(cr, "save_state", fake_save_state),
            mock.patch.object(cl, "load_lease", fake_load_lease),
            mock.patch.object(cl, "check_execute_right", fake_check_execute_right),
            mock.patch.object(cl, "acquire", fake_acquire),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

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
        now = datetime.datetime(2026, 8, 31, 12, 0, 0, tzinfo=datetime.timezone.utc)
        cl.acquire("controller-X", ttl_seconds=60, path=self.path, now=now)
        later = now + datetime.timedelta(seconds=61)
        r = cl.check_execute_right("controller-X", 1, path=self.path, now=later)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], cl.LEASE_EXPIRED)


if __name__ == "__main__":
    unittest.main()
