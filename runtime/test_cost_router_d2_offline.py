"""CostRouter 离线测试（D2）：Expected Total Cost 路由 / 预算熔断 / SAFE_HALT / NO_PROGRESS。

全部离线：使用 tmp 目录构造 policy/registry/state fixture；不触真实网络、
不消耗真实额度、不读真实凭据。少量用例读取仓库真实 config 验证默认加载路径。
"""

import json
import os
import sys
import tempfile
import unittest
from importlib import import_module
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
cost_router = import_module("cost_router")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _policy() -> dict:
    """最小完整 cost policy（与 config/cost_policy.json 同构，测试可控）。"""
    return {
        "schema": "COST_POLICY",
        "schema_version": 1,
        "reference_tokens_per_call": 2000,
        "tokens_est_default": 2000,
        "unit_prices": {
            "brain-chatgpt-web": {"model": "chatgpt-web", "unit_price": 0.30, "source": "估算"},
            "worker-workbuddy-cli": {"model": "deepseek-v4-flash", "unit_price": 0.05, "source": "估算"},
            "worker-codex-cli": {"model": "codex-local", "unit_price": 0.20, "source": "估算"},
            "r-prod-chatgpt-web": {"model": "chatgpt-web", "unit_price": 0.30, "source": "估算"},
            "r-deepseek-v4-flash": {"model": "deepseek-v4-flash", "unit_price": 0.05, "source": "估算"},
            "provider-catpaw": {"model": "catpaw", "unit_price": None, "source": "待实测"},
        },
        "roles": {
            "worker_weak": "worker-workbuddy-cli",
            "worker_strong": "worker-codex-cli",
            "r_strong": "r-prod-chatgpt-web",
            "r_weak": "r-deepseek-v4-flash",
        },
        "route_options": {
            "weak": {"worker": "worker-workbuddy-cli", "reviewer": None, "note": "弱直接交付"},
            "hybrid": {"worker": "worker-workbuddy-cli", "reviewer": "r-prod-chatgpt-web",
                       "note": "弱干活+强审查"},
            "strong": {"worker": "worker-codex-cli", "reviewer": "r-prod-chatgpt-web",
                       "note": "强干活+强审查"},
        },
        "rework_probability": {"low": 0.1, "mid": 0.3, "high": 0.6},
        "max_review_cycles": 3,
        "budget": {"default_budget_threshold": 0.5},
        "circuit_breaker": {
            "enabled": True,
            "no_progress_limit": 3,
            "consecutive_breach_limit": 2,
            "freeze_on_trigger": True,
        },
        "goal_type_keywords": {
            "high": ["high-risk", "高危", "安全", "production", "生产"],
            "mid": ["analysis", "分析", "refactor", "重构"],
            "low": ["mechanical", "机械", "read", "读取", "test", "测试"],
        },
    }


def _registry_costs() -> dict:
    """registry costs 节（capability_id -> cost 元数据）。"""
    return {
        "worker-workbuddy-cli": {"cost_per_call": 0.05, "cost_model": "per_call_estimate",
                                 "source": "估算", "note": "fixture"},
        "r-prod-chatgpt-web": {"cost_per_call": 0.30, "cost_model": "per_call_estimate",
                               "source": "估算", "note": "fixture"},
    }


def _write_policy(tmp: Path) -> Path:
    p = tmp / "cost_policy.json"
    p.write_text(json.dumps(_policy(), ensure_ascii=False), encoding="utf-8")
    return p


def _state_path(tmp: Path) -> Path:
    return tmp / "cost_router_state.json"


def _load_state_at(path: Path) -> dict:
    return cost_router.load_state(str(path))


def _goal_high_risk() -> str:
    return "high-risk production 安全发布任务（需强审查）"


def _goal_mechanical() -> str:
    return "机械读取配置文件并格式化输出"


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------
class TestConfigLoad(unittest.TestCase):
    def test_load_policy_default_path(self):
        policy = cost_router.load_policy()
        self.assertEqual(policy["schema"], "COST_POLICY")
        self.assertIn("unit_prices", policy)
        self.assertIn("route_options", policy)
        self.assertIn("circuit_breaker", policy)

    def test_load_policy_from_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_policy(Path(d))
            policy = cost_router.load_policy(str(p))
            self.assertEqual(policy["schema"], "COST_POLICY")

    def test_load_policy_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            cost_router.load_policy("no-such-cost-policy.json")

    def test_load_policy_bad_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.json"
            p.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ValueError):
                cost_router.load_policy(str(p))

    def test_load_policy_missing_unit_prices(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.json"
            p.write_text(json.dumps({"schema": "COST_POLICY"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                cost_router.load_policy(str(p))

    def test_load_registry_costs_default_path(self):
        costs = cost_router.load_registry_costs()
        self.assertIn("worker-workbuddy-cli", costs)
        self.assertIn("r-prod-chatgpt-web", costs)
        self.assertIn("provider-catpaw", costs)


class TestResolveUnitPrice(unittest.TestCase):
    def test_from_policy_preferred(self):
        policy = _policy()
        rc = {"worker-workbuddy-cli": {"cost_per_call": 9.9, "source": "registry"}}
        info = cost_router.resolve_unit_price("worker-workbuddy-cli", policy, rc)
        self.assertIsNotNone(info)
        self.assertEqual(info["unit_price"], 0.05)  # policy 优先于 registry

    def test_from_registry_when_policy_missing(self):
        policy = {"unit_prices": {}}
        rc = {"some-model": {"cost_per_call": 0.7, "source": "registry"}}
        info = cost_router.resolve_unit_price("some-model", policy, rc)
        self.assertIsNotNone(info)
        self.assertEqual(info["unit_price"], 0.7)

    def test_missing_returns_none(self):
        policy = _policy()
        info = cost_router.resolve_unit_price("no-such-model", policy, {})
        self.assertIsNone(info)

    def test_null_price_returns_none(self):
        policy = _policy()
        info = cost_router.resolve_unit_price("provider-catpaw", policy, {})
        self.assertIsNone(info)  # unit_price=null -> 待校准


# ---------------------------------------------------------------------------
# 分类 / 概率 / 几何级数
# ---------------------------------------------------------------------------
class TestClassifyGoal(unittest.TestCase):
    def test_high_keyword(self):
        self.assertEqual(cost_router.classify_goal("high-risk 生产发布", _policy()), "high")

    def test_mid_keyword(self):
        self.assertEqual(cost_router.classify_goal("代码分析方案", _policy()), "mid")

    def test_low_keyword(self):
        self.assertEqual(cost_router.classify_goal("机械读取任务", _policy()), "low")

    def test_default_mid(self):
        self.assertEqual(cost_router.classify_goal("完全未知的模糊目标", _policy()), "mid")

    def test_empty_default_mid(self):
        self.assertEqual(cost_router.classify_goal("", _policy()), "mid")

    def test_high_priority_over_low(self):
        # 同时含 high 与 low 关键字：high 优先
        self.assertEqual(cost_router.classify_goal("机械读取但涉及生产安全", _policy()), "high")


class TestReworkProbability(unittest.TestCase):
    def test_mapping(self):
        p = _policy()
        self.assertEqual(cost_router.rework_probability("low", p), 0.1)
        self.assertEqual(cost_router.rework_probability("mid", p), 0.3)
        self.assertEqual(cost_router.rework_probability("high", p), 0.6)

    def test_unknown_falls_back_mid(self):
        self.assertEqual(cost_router.rework_probability("bogus", _policy()), 0.3)

    def test_none_falls_back_mid(self):
        self.assertEqual(cost_router.rework_probability(None, _policy()), 0.3)


class TestGeometricSum(unittest.TestCase):
    def test_zero_prob(self):
        self.assertEqual(cost_router.geometric_sum(0.0, 3), 1.0)

    def test_high_prob_cycles_3(self):
        self.assertAlmostEqual(cost_router.geometric_sum(0.6, 3), 1.96, places=4)

    def test_cycles_1(self):
        self.assertEqual(cost_router.geometric_sum(0.9, 1), 1.0)

    def test_expected_call_counts_equal(self):
        w, r = cost_router.expected_call_counts(0.6, 3)
        self.assertAlmostEqual(w, 1.96, places=4)
        self.assertEqual(w, r)


class TestRecommendRoute(unittest.TestCase):
    def test_high_strong(self):
        self.assertEqual(cost_router.recommend_route("high", "low", _policy()), "strong")

    def test_mid_hybrid(self):
        self.assertEqual(cost_router.recommend_route("mid", "high", _policy()), "hybrid")

    def test_low_low_weak(self):
        self.assertEqual(cost_router.recommend_route("low", "low", _policy()), "weak")

    def test_low_high_hybrid(self):
        self.assertEqual(cost_router.recommend_route("low", "high", _policy()), "hybrid")


# ---------------------------------------------------------------------------
# route：成本分解 + 推荐 + 熔断
# ---------------------------------------------------------------------------
class TestRoute(unittest.TestCase):
    def test_low_risk_mechanical_allowed_weak(self):
        with tempfile.TemporaryDirectory() as d:
            st = _load_state_at(_state_path(Path(d)))
            result = cost_router.do_route(_goal_mechanical(), "low", None, None,
                                          _policy(), _registry_costs(), st, str(_state_path(Path(d))))
            self.assertTrue(result["ok"])
            self.assertEqual(result["verdict"], "ALLOWED")
            self.assertEqual(result["recommended_route"], "weak")
            self.assertEqual(result["goal_type"], "low")
            self.assertIsNotNone(result["expected_total_cost"])
            # weak：单次执行、无审查 -> 0.05
            self.assertAlmostEqual(result["expected_total_cost"], 0.05, places=6)
            # 成本分解表包含执行阶段
            stages = result["stages"]
            self.assertEqual(stages[0]["stage"], "worker_execute")
            self.assertEqual(stages[0]["model"], "worker-workbuddy-cli")
            self.assertEqual(stages[0]["expected_calls"], 1.0)
            self.assertAlmostEqual(stages[0]["expected_cost"], 0.05, places=6)

    def test_mid_goal_hybrid(self):
        with tempfile.TemporaryDirectory() as d:
            st = _load_state_at(_state_path(Path(d)))
            result = cost_router.do_route("代码分析方案", "mid", None, None,
                                          _policy(), _registry_costs(), st, str(_state_path(Path(d))))
            self.assertEqual(result["recommended_route"], "hybrid")
            self.assertEqual(result["goal_type"], "mid")
            self.assertTrue(result["ok"])

    def test_high_goal_strong(self):
        with tempfile.TemporaryDirectory() as d:
            st = _load_state_at(_state_path(Path(d)))
            result = cost_router.do_route(_goal_high_risk(), "low", None, 10.0,
                                          _policy(), _registry_costs(), st, str(_state_path(Path(d))))
            # 高价值 -> strong；max-cost=10 足够 -> ALLOWED
            self.assertEqual(result["recommended_route"], "strong")
            self.assertEqual(result["goal_type"], "high")
            self.assertTrue(result["ok"])

    def test_hybrid_etc_math(self):
        # hybrid + mid：p=0.3, E[calls]=1+0.3+0.09=1.39
        # worker=0.05*1.39 + review=0.30*1.39 = 0.4865
        with tempfile.TemporaryDirectory() as d:
            st = _load_state_at(_state_path(Path(d)))
            result = cost_router.do_route("代码分析方案", "mid", None, None,
                                          _policy(), _registry_costs(), st, str(_state_path(Path(d))))
            self.assertAlmostEqual(result["expected_total_cost"], 0.4865, places=6)
            self.assertTrue(result["ok"])  # 0.4865 <= 0.5

    def test_high_risk_high_rework_triggers_safe_halt(self):
        """L2 真实触发场景的单元等价：high-risk + rework-risk=high -> ETC 超预算 -> SAFE_HALT。"""
        with tempfile.TemporaryDirectory() as d:
            sp = _state_path(Path(d))
            st = _load_state_at(sp)
            result = cost_router.do_route(_goal_high_risk(), "high", None, None,
                                          _policy(), _registry_costs(), st, str(sp))
            self.assertFalse(result["ok"])
            self.assertEqual(result["verdict"], "SAFE_HALT")
            rec = result["safe_halt"]
            # 结构化记录：原因/时间/上下文/恢复建议
            self.assertEqual(rec["reason"], "BUDGET_BREACH")
            self.assertIn("triggered_at", rec)
            self.assertIn("context", rec)
            self.assertIn("recovery", rec)
            self.assertTrue(rec["freeze"])
            self.assertEqual(rec["schema"], "SAFE_HALT_RECORD")
            self.assertIn("SAFE_HALT-", rec["record_id"])
            # 期望总成本 > 预算阈值（strong: 0.2*1.96 + 0.3*1.96 = 0.98 > 0.5）
            self.assertGreater(result["expected_total_cost"], 0.5)
            # 状态已持久化：冻结该任务
            st2 = _load_state_at(sp)
            self.assertTrue(st2["tripped"])
            self.assertIn(result["goal_hash"], st2["frozen_tasks"])
            self.assertEqual(len(st2["history"]), 1)

    def test_frozen_task_blocks_retry(self):
        """冻结：同一任务再次 route -> FROZEN（不自动重试）；其他任务不受影响。"""
        with tempfile.TemporaryDirectory() as d:
            sp = _state_path(Path(d))
            st = _load_state_at(sp)
            r1 = cost_router.do_route(_goal_high_risk(), "high", None, None,
                                      _policy(), _registry_costs(), st, str(sp))
            self.assertEqual(r1["verdict"], "SAFE_HALT")
            # 同一任务重试 -> FROZEN
            st2 = _load_state_at(sp)
            r2 = cost_router.do_route(_goal_high_risk(), "high", None, None,
                                      _policy(), _registry_costs(), st2, str(sp))
            self.assertEqual(r2["verdict"], "FROZEN")
            self.assertFalse(r2["ok"])
            self.assertEqual(r2["safe_halt"]["reason"], "BUDGET_BREACH")
            # 其他任务仍可路由
            st3 = _load_state_at(sp)
            r3 = cost_router.do_route(_goal_mechanical(), "low", None, None,
                                      _policy(), _registry_costs(), st3, str(sp))
            self.assertEqual(r3["verdict"], "ALLOWED")

    def test_unknown_model_price_skipped(self):
        """单价缺失 -> 待校准：跳过其成本计算，etc 用有单价阶段求和。"""
        with tempfile.TemporaryDirectory() as d:
            sp = _state_path(Path(d))
            st = _load_state_at(sp)
            # 手动把 worker 单价抹掉（policy+registry 双源均缺失）-> 只剩 review 阶段有单价
            policy = _policy()
            policy["unit_prices"]["worker-workbuddy-cli"]["unit_price"] = None
            policy["unit_prices"]["worker-codex-cli"]["unit_price"] = None
            result = cost_router.do_route("代码分析方案", "mid", None, None,
                                          policy, {}, st, str(sp))
            worker_stage = [s for s in result["stages"] if s["stage"] == "worker_execute"][0]
            self.assertEqual(worker_stage["status"], "待校准")
            self.assertIsNone(worker_stage["expected_cost"])
            # 期望总成本 = 仅 review 阶段 = 0.30 * 1.39
            self.assertAlmostEqual(result["expected_total_cost"], 0.3 * 1.39, places=6)

    def test_tokens_est_scaling(self):
        """--tokens-est 缩放：6000 token -> tokens_scale=3 -> ETC 放大 3 倍。"""
        with tempfile.TemporaryDirectory() as d:
            st = _load_state_at(_state_path(Path(d)))
            base = cost_router.do_route("代码分析方案", "mid", None, None,
                                        _policy(), _registry_costs(), st, str(_state_path(Path(d))))
            st2 = _load_state_at(_state_path(Path(d)))
            scaled = cost_router.do_route("代码分析方案", "mid", 6000, None,
                                          _policy(), _registry_costs(), st2, str(_state_path(Path(d))))
            self.assertAlmostEqual(scaled["expected_total_cost"],
                                   base["expected_total_cost"] * 3.0, places=6)
            self.assertEqual(scaled["tokens_scale"], 3.0)

    def test_boundary_equal_threshold_allowed(self):
        """边界：ETC == 阈值 -> 不触发熔断（> 才熔断）。"""
        with tempfile.TemporaryDirectory() as d:
            st = _load_state_at(_state_path(Path(d)))
            result = cost_router.do_route("代码分析方案", "mid", None, 0.4865,
                                          _policy(), _registry_costs(), st, str(_state_path(Path(d))))
            self.assertEqual(result["verdict"], "ALLOWED")
            self.assertTrue(result["ok"])

    def test_route_undetermined_when_all_prices_missing(self):
        """route 全部阶段待校准 -> UNDETERMINED（ok=True，不误伤、不触发熔断）。"""
        with tempfile.TemporaryDirectory() as d:
            sp = _state_path(Path(d))
            st = _load_state_at(sp)
            policy = _policy()
            for key in policy["unit_prices"]:
                policy["unit_prices"][key]["unit_price"] = None
            result = cost_router.do_route("代码分析方案", "high", None, 0.1,
                                          policy, {}, st, str(sp))
            self.assertEqual(result["verdict"], "UNDETERMINED")
            self.assertTrue(result["ok"])
            self.assertIsNone(result["expected_total_cost"])
            # 未触发 SAFE_HALT
            st2 = _load_state_at(sp)
            self.assertFalse(st2["tripped"])


# ---------------------------------------------------------------------------
# budget：预算熔断检查
# ---------------------------------------------------------------------------
class TestBudget(unittest.TestCase):
    def test_allowed_under_budget(self):
        with tempfile.TemporaryDirectory() as d:
            sp = _state_path(Path(d))
            st = _load_state_at(sp)
            result = cost_router.do_budget(_goal_mechanical(), 10.0, "low", None,
                                           _policy(), _registry_costs(), st, str(sp))
            self.assertEqual(result["verdict"], "ALLOWED")
            self.assertTrue(result["ok"])
            self.assertFalse(result["suggest_safe_halt"])

    def test_blocked_over_budget_with_suggestion(self):
        """预算熔断检查：ETC > 阈值 -> BLOCKED（返回 SAFE_HALT 建议）。"""
        with tempfile.TemporaryDirectory() as d:
            sp = _state_path(Path(d))
            st = _load_state_at(sp)
            result = cost_router.do_budget(_goal_high_risk(), 0.3, "high", None,
                                           _policy(), _registry_costs(), st, str(sp))
            self.assertEqual(result["verdict"], "BLOCKED")
            self.assertFalse(result["ok"])
            self.assertTrue(result["suggest_safe_halt"])
            self.assertEqual(result["consecutive_breach"], 1)
            # 未触发 SAFE_HALT（连续未达上限）
            self.assertNotIn("safe_halt", result)

    def test_consecutive_breach_triggers_safe_halt(self):
        """连续熔断标记超限 -> SAFE_HALT（条件 ③）。"""
        with tempfile.TemporaryDirectory() as d:
            sp = _state_path(Path(d))
            st = _load_state_at(sp)
            r1 = cost_router.do_budget(_goal_high_risk(), 0.3, "high", None,
                                       _policy(), _registry_costs(), st, str(sp))
            self.assertEqual(r1["verdict"], "BLOCKED")
            st2 = _load_state_at(sp)
            r2 = cost_router.do_budget(_goal_high_risk(), 0.3, "high", None,
                                       _policy(), _registry_costs(), st2, str(sp))
            self.assertEqual(r2["verdict"], "SAFE_HALT")
            self.assertEqual(r2["safe_halt"]["reason"], "CONSECUTIVE_BREACH")
            self.assertFalse(r2["ok"])

    def test_undetermined_when_all_prices_missing(self):
        """全部待校准 -> UNDETERMINED：跳过预算熔断检查，不误伤。"""
        with tempfile.TemporaryDirectory() as d:
            sp = _state_path(Path(d))
            st = _load_state_at(sp)
            policy = _policy()
            for key in policy["unit_prices"]:
                policy["unit_prices"][key]["unit_price"] = None
            result = cost_router.do_budget("代码分析方案", 0.1, "mid", None,
                                           policy, {}, st, str(sp))
            self.assertEqual(result["verdict"], "UNDETERMINED")
            self.assertTrue(result["ok"])
            self.assertFalse(result["suggest_safe_halt"])

    def test_success_resets_consecutive_breach(self):
        with tempfile.TemporaryDirectory() as d:
            sp = _state_path(Path(d))
            st = _load_state_at(sp)
            cost_router.do_budget(_goal_high_risk(), 0.3, "high", None,
                                  _policy(), _registry_costs(), st, str(sp))
            st2 = _load_state_at(sp)
            r = cost_router.do_budget(_goal_mechanical(), 10.0, "low", None,
                                      _policy(), _registry_costs(), st2, str(sp))
            self.assertEqual(r["verdict"], "ALLOWED")
            st3 = _load_state_at(sp)
            self.assertEqual(st3["consecutive_breach"], 0)


# ---------------------------------------------------------------------------
# NO_PROGRESS（宪法 §19 呼应）
# ---------------------------------------------------------------------------
class TestSimulateRework(unittest.TestCase):
    def test_monitoring_under_limit(self):
        with tempfile.TemporaryDirectory() as d:
            sp = _state_path(Path(d))
            st = _load_state_at(sp)
            result = cost_router.do_simulate_rework("重构任务", 2, None,
                                                    _policy(), st, str(sp))
            self.assertEqual(result["verdict"], "MONITORING")
            self.assertTrue(result["ok"])
            self.assertEqual(result["no_progress_count"], 2)
            self.assertEqual(result["no_progress_limit"], 3)

    def test_safe_halt_at_limit(self):
        """连续 N 次 REWORK（mock）-> 触发熔断（NO_PROGRESS）。"""
        with tempfile.TemporaryDirectory() as d:
            sp = _state_path(Path(d))
            st = _load_state_at(sp)
            result = cost_router.do_simulate_rework("重构任务", 3, None,
                                                    _policy(), st, str(sp))
            self.assertEqual(result["verdict"], "SAFE_HALT")
            self.assertFalse(result["ok"])
            rec = result["safe_halt"]
            self.assertEqual(rec["reason"], "NO_PROGRESS")
            self.assertEqual(rec["context"]["no_progress_count"], 3)
            self.assertEqual(rec["context"]["no_progress_limit"], 3)
            self.assertIn("recovery", rec)
            # 状态已冻结该任务
            st2 = _load_state_at(sp)
            self.assertIn(result["goal_hash"], st2["frozen_tasks"])

    def test_cumulative_across_calls(self):
        with tempfile.TemporaryDirectory() as d:
            sp = _state_path(Path(d))
            st = _load_state_at(sp)
            r1 = cost_router.do_simulate_rework("重构任务", 2, None, _policy(), st, str(sp))
            self.assertEqual(r1["verdict"], "MONITORING")
            st2 = _load_state_at(sp)
            r2 = cost_router.do_simulate_rework("重构任务", 1, None, _policy(), st2, str(sp))
            self.assertEqual(r2["verdict"], "SAFE_HALT")
            self.assertEqual(r2["safe_halt"]["reason"], "NO_PROGRESS")


# ---------------------------------------------------------------------------
# 手动触发 / 状态 / reset / 状态文件健壮性
# ---------------------------------------------------------------------------
class TestSafeHaltAndState(unittest.TestCase):
    def test_manual_safe_halt(self):
        with tempfile.TemporaryDirectory() as d:
            sp = _state_path(Path(d))
            st = _load_state_at(sp)
            result = cost_router.do_safe_halt_manual("受控测试任务", "L2 实测", _policy(), st, str(sp))
            self.assertEqual(result["verdict"], "SAFE_HALT")
            self.assertEqual(result["safe_halt"]["reason"], "MANUAL")
            self.assertTrue(result["frozen"])

    def test_status_shows_frozen(self):
        with tempfile.TemporaryDirectory() as d:
            sp = _state_path(Path(d))
            st = _load_state_at(sp)
            cost_router.do_safe_halt_manual("受控测试任务", "L2 实测", _policy(), st, str(sp))
            st2 = _load_state_at(sp)
            status = cost_router.do_status(st2, str(sp))
            self.assertEqual(status["status"], "SAFE_HALT")
            self.assertTrue(status["tripped"])
            self.assertEqual(status["frozen_count"], 1)
            self.assertEqual(status["history_count"], 1)

    def test_reset_unfreezes_keeps_history(self):
        with tempfile.TemporaryDirectory() as d:
            sp = _state_path(Path(d))
            st = _load_state_at(sp)
            cost_router.do_safe_halt_manual("受控测试任务", "L2 实测", _policy(), st, str(sp))
            st2 = _load_state_at(sp)
            res = cost_router.do_reset(st2, "受控测试任务", str(sp))
            self.assertTrue(res["ok"])
            self.assertEqual(res["status"], "FREE")
            self.assertEqual(res["frozen_count"], 0)
            self.assertEqual(res["history_count"], 1)  # 证据保留
            st3 = _load_state_at(sp)
            # 解冻后可再次路由
            r = cost_router.do_route(_goal_mechanical(), "low", None, None,
                                     _policy(), _registry_costs(), st3, str(sp))
            self.assertEqual(r["verdict"], "ALLOWED")

    def test_reset_all(self):
        with tempfile.TemporaryDirectory() as d:
            sp = _state_path(Path(d))
            st = _load_state_at(sp)
            cost_router.do_safe_halt_manual("任务A", "L2", _policy(), st, str(sp))
            st2 = _load_state_at(sp)
            cost_router.do_safe_halt_manual("任务B", "L2", _policy(), st2, str(sp))
            st3 = _load_state_at(sp)
            res = cost_router.do_reset(st3, None, str(sp))
            self.assertEqual(res["frozen_count"], 0)
            self.assertEqual(res["detail"], "全部 2 个冻结任务已解冻")

    def test_state_file_corrupt_rebuilds_default(self):
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "state.json"
            sp.write_text("{corrupt json", encoding="utf-8")
            state = cost_router.load_state(str(sp))
            self.assertEqual(state["status"], "FREE")
            self.assertFalse(state["tripped"])
            # 损坏文件被备份
            backups = list(Path(d).glob("state.json.corrupt-*"))
            self.assertEqual(len(backups), 1)

    def test_state_missing_returns_default(self):
        with tempfile.TemporaryDirectory() as d:
            state = cost_router.load_state(str(Path(d) / "none.json"))
            self.assertEqual(state["status"], "FREE")


# ---------------------------------------------------------------------------
# CLI 退出码
# ---------------------------------------------------------------------------
class TestCLI(unittest.TestCase):
    def _cli(self, argv):
        return cost_router.main(argv)

    def test_cli_route_allowed_exit0(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_policy(Path(d))
            sp = _state_path(Path(d))
            code = self._cli(["route", "--goal", _goal_mechanical(), "--rework-risk", "low",
                              "--policy", str(p), "--state", str(sp)])
            self.assertEqual(code, 0)

    def test_cli_route_safe_halt_exit2(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_policy(Path(d))
            sp = _state_path(Path(d))
            code = self._cli(["route", "--goal", _goal_high_risk(), "--rework-risk", "high",
                              "--policy", str(p), "--state", str(sp)])
            self.assertEqual(code, 2)

    def test_cli_budget_blocked_exit2(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_policy(Path(d))
            sp = _state_path(Path(d))
            code = self._cli(["budget", "--goal", _goal_high_risk(), "--max-cost", "0.3",
                              "--rework-risk", "high",
                              "--policy", str(p), "--state", str(sp)])
            self.assertEqual(code, 2)

    def test_cli_budget_allowed_exit0(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_policy(Path(d))
            sp = _state_path(Path(d))
            code = self._cli(["budget", "--goal", _goal_mechanical(), "--max-cost", "10",
                              "--rework-risk", "low",
                              "--policy", str(p), "--state", str(sp)])
            self.assertEqual(code, 0)

    def test_cli_config_error_exit1(self):
        with tempfile.TemporaryDirectory() as d:
            code = self._cli(["route", "--goal", "x", "--policy", str(Path(d) / "missing.json")])
            self.assertEqual(code, 1)

    def test_cli_status_reset_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_policy(Path(d))
            sp = _state_path(Path(d))
            self.assertEqual(self._cli(["safe-halt", "--goal", "受控任务", "--policy", str(p),
                                        "--state", str(sp)]), 2)
            code_status = self._cli(["status", "--state", str(sp)])
            self.assertEqual(code_status, 0)
            code_reset = self._cli(["reset", "--state", str(sp)])
            self.assertEqual(code_reset, 0)


if __name__ == "__main__":
    unittest.main()
