# -*- coding: utf-8 -*-
"""GATE-3 state 卫生哨兵（offline）。

两层防线：

1. 污染探针——记录仓库 state/controller_lease.json 与
   state/cost_router_state.json 的指纹（mtime_ns + size；不存在记为"缺席"），
   然后 import relay_autopilot、mock 最小闸门环境后运行真实的
   admission_checks（正常 goal 与缺上下文 goal 各一次，cost/lease 闸都真实
   执行到），再对比指纹：测试窗口内两个真实状态文件都不得被创建或更新
   （本测试只 stat 元数据，不读写其内容）。

2. .gitignore 覆盖——以下 5 条必须存在，否则运行时工件会漏进版本库：
   state/controller_lease.json / state/cost_router_state.json /
   state/self_heal_evidence/ / state/goals/ / tmp*/

探针 mock 的最小环境（与 test_relay_autopilot_wiring_offline 同一策略）：
  cost_router.load_policy/load_registry_costs/load_state -> 假数据
  cost_router.save_state  -> tmp（do_route 不 patch，其内部会持久化，
                              不重定向就会写真实 state/cost_router_state.json）
  controller_lease.load_lease -> 有效租约 generation=9/relay_autopilot/2099
  controller_lease.check_execute_right -> {"ok": True}
  controller_lease.acquire -> 返回同一有效租约
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

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
_SCRIPTS = str(REPO / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

ap = import_module("relay_autopilot")
import controller_lease as cl  # noqa: E402
import cost_router as cr  # noqa: E402

LEASE_FILE = REPO / "state" / "controller_lease.json"
COST_STATE_FILE = REPO / "state" / "cost_router_state.json"
GITIGNORE_FILE = REPO / ".gitignore"

REQUIRED_GITIGNORE_ENTRIES = (
    "state/controller_lease.json",
    "state/cost_router_state.json",
    "state/self_heal_evidence/",
    "state/goals/",
    "tmp*/",
)

_LEASE = {
    "schema": cl.SCHEMA,
    "generation": 9,
    "holder": "relay_autopilot",
    "issued_at": "2098-01-01T00:00:00Z",
    "expires_at": "2099-01-01T00:00:00Z",
}

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


def _fingerprint(path: Path):
    """状态文件指纹：不存在 -> None；存在 -> (mtime_ns, size)。只 stat，不读写内容。"""
    try:
        st = os.stat(str(path))
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


class StateHygieneSentinelTests(unittest.TestCase):
    """admission_checks 探针不得在测试窗口内触碰真实仓库 state/ 文件。"""

    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="state-hygiene-")
        self.addCleanup(shutil.rmtree, self.td, True)
        # 测试前指纹快照（在探针运行之前记录）
        self.before = {
            "lease": _fingerprint(LEASE_FILE),
            "cost": _fingerprint(COST_STATE_FILE),
        }
        # mock 最小闸门环境（探针期间生效，跑完恢复）
        def fake_load_policy(path=None):
            return dict(_FAKE_POLICY)

        def fake_load_registry_costs(path=None):
            return {}

        def fake_load_state(path=None):
            return cr.default_state()

        def fake_save_state(state, path=None):
            p = Path(self.td) / "cost_router_state.json"
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

    def _probe(self):
        """污染探针：跑真实 admission_checks（cost/lease 闸真实执行），返回结果。"""
        results = []
        goals = (
            {
                "goal_id": "SENTINEL-001",
                "title": "mechanical probe goal",
                "objective": "mechanical read config and format output",
                "scope": ["config"],
                "acceptance": ["output correct"],
                "priority": 1,
            },
            {
                "goal_id": "SENTINEL-002",
                "title": "probe goal with missing context",
                "objective": "mechanical read config and format output",
                "scope": ["config"],
                "acceptance": ["output correct"],
                "priority": 1,
                "required_info": ["missing-special-brain-artifact"],
            },
        )
        for goal in goals:
            results.append(ap.admission_checks(goal))
        # 探针必须真实走到 cost/lease 闸（否则探针是空的，白测）
        for r in results:
            self.assertIn("cost", r["checks"], f"cost gate not exercised: {r['reasons']}")
            self.assertIn("verdict", r["checks"]["cost"])
            self.assertIn("lease", r["checks"], f"lease gate not exercised: {r['reasons']}")
            self.assertTrue(r["checks"]["lease"].get("ok"), r["checks"]["lease"])
        return results

    def test_probe_leaves_real_state_files_untouched(self):
        self._probe()
        after = {
            "lease": _fingerprint(LEASE_FILE),
            "cost": _fingerprint(COST_STATE_FILE),
        }
        for key, label in (("lease", str(LEASE_FILE)), ("cost", str(COST_STATE_FILE))):
            before_fp = self.before[key]
            after_fp = after[key]
            if before_fp is None:
                self.assertIsNone(
                    after_fp,
                    f"污染探针在测试窗口内创建了真实 state 文件：{label}（GATE-3 红线）")
            else:
                self.assertIsNotNone(
                    after_fp,
                    f"污染探针在测试窗口内删除了真实 state 文件：{label}（GATE-3 红线）")
                self.assertEqual(
                    before_fp, after_fp,
                    f"污染探针在测试窗口内更新了真实 state 文件：{label} "
                    f"before={before_fp} after={after_fp}（GATE-3 红线）")

    def test_gitignore_covers_runtime_state_paths(self):
        text = GITIGNORE_FILE.read_text(encoding="utf-8")
        for entry in REQUIRED_GITIGNORE_ENTRIES:
            self.assertIn(entry, text, f".gitignore 缺少运行时工件覆盖规则：{entry}")


if __name__ == "__main__":
    unittest.main()
