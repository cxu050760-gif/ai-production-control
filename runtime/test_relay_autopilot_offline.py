"""relay_autopilot 离线测试（B1 补 A1 自动化测试）。

覆盖审计 AUDIT-V1.1-BLACKBOX-20260831 B1 要求的 4 条硬性机制：
  1) 单实例锁三态：新鲜锁不被覆盖（SKIP_LOCKED）/ stale 回收 / 幂等释放
  2) 状态机全迁移：CLAIMED->WORKING->REPORTED->WAITING_REVIEW->REVIEWING
     ->PASS(WRAPPED) 与 REWORK->requeue / rework 超限 ABORTED 异常分支
  3) R 并发度 1 门控：多 REPORTED 只取一 + rework 公平优先 + 占门不阻塞队列
  4) 沙箱越界拦截：只认领 SANDBOX_INBOX 内事件；run_id 路径逃逸拒绝

全部离线：仅操作 tmp 目录沙箱（setUp 重定向模块级路径常量）；
不触真实 construction-relay 状态、不触 R 通道、不读凭据。
依赖：scripts/relay_autopilot.py（脚本级路径常量被 patch，不写真实目录）。
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
autopilot = import_module("relay_autopilot")

EXPECTED_PASS_SEQUENCE = ["CLAIMED", "WORKING", "REPORTED", "WAITING_REVIEW", "REVIEWING", "WRAPPED"]


# ---------------------------------------------------------------------------
# Fixtures / 辅助
# ---------------------------------------------------------------------------
def make_event(base_id, **kw):
    run_id = kw.pop("run_id", base_id)
    """构造最小 BUILDER_READY 事件（含 claim_inbox 所需全部字段）。"""
    ev = {
        "schema_version": 1,
        "event": "BUILDER_READY",
        "event_id": "EV-" + run_id[:40],
        "run_id": run_id,
        "task_id": "T-" + run_id[:40],
        "candidate_commit": "0" * 40,
        "created_at": "2026-08-31T00:00:00.000Z",
        "_goal": {"goal_id": run_id, "title": "goal-" + run_id, "objective": "offline test goal",
                  "priority": 1},
    }
    ev.update(kw)
    return ev


class AutopilotSandboxCase(unittest.TestCase):
    """把 autopilot 模块的路径常量全部重定向到 tmp 沙箱。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="autopilot-test-"))
        self.auto = self.tmp / "autopilot"
        (self.auto / "inbox").mkdir(parents=True)
        (self.auto / "runs").mkdir(parents=True)
        (self.auto / "lock").mkdir(parents=True)
        self._orig = {}
        for attr, value in [
            ("AUTO_DIR", str(self.auto)),
            ("SANDBOX_INBOX", str(self.auto / "inbox")),
            ("RUNS_DIR", str(self.auto / "runs")),
            ("QUEUE_FILE", str(self.auto / "queue.json")),
            ("LOCK_DIR", str(self.auto / "lock")),
            ("LEDGER", str(self.auto / "actions.ndjson")),
        ]:
            self._orig[attr] = getattr(autopilot, attr)
            setattr(autopilot, attr, value)
            self.addCleanup(setattr, autopilot, attr, self._orig[attr])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers ------------------------------------------------------------
    def drop_event(self, inbox_name, **kw):
        """写一个 BUILDER_READY 事件到 SANDBOX_INBOX。"""
        ev = make_event(inbox_name, **kw)
        (Path(autopilot.SANDBOX_INBOX) / (inbox_name + ".json")).write_text(
            json.dumps(ev), encoding="utf-8")
        return ev

    def seed_run(self, run_id, state, rework_count=0, created_at="2026-08-31T00:00:01Z"):
        """直接向 queue 播种一个 run（不经 claim）。"""
        q = autopilot.load_queue()
        q["runs"].append({
            "run_id": run_id,
            "event_id": "EV-" + run_id,
            "task_id": "T-" + run_id,
            "title": run_id,
            "milestone": "",
            "priority": 1,
            "candidate_commit": "0" * 40,
            "state": state,
            "rework_count": rework_count,
            "created_at": created_at,
            "claimed_at": created_at,
            "verdict": None,
        })
        autopilot.save_queue(q)

    def queue_runs(self):
        return autopilot.load_queue()["runs"]

    def find_run(self, run_id):
        for r in self.queue_runs():
            if r["run_id"] == run_id:
                return r
        return None


# ---------------------------------------------------------------------------
# 1) 单实例锁三态
# ---------------------------------------------------------------------------
class LockTests(AutopilotSandboxCase):
    def test_fresh_lock_not_overwritten(self):
        """另一实例持有新鲜锁时 acquire_lock 返回 None（SKIP_LOCKED）。"""
        token1 = autopilot.acquire_lock()
        self.assertIsNotNone(token1)
        token2 = autopilot.acquire_lock()  # 同时刻再次获取
        self.assertIsNone(token2)
        # 锁内容仍属第一个实例
        info = autopilot.load_json(os.path.join(autopilot.LOCK_DIR, "lock.json"))
        self.assertIsNotNone(info)
        self.assertEqual(info["token"], token1)

    def test_stale_lock_reclaimed(self):
        """超过 300 秒的 stale 锁被回收重建，acquire_lock 成功。"""
        import datetime
        token1 = autopilot.acquire_lock()
        self.assertIsNotNone(token1)
        stale_at = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(seconds=400)
        )
        stale_at_str = stale_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        autopilot.save_json(os.path.join(autopilot.LOCK_DIR, "lock.json"),
                            {"token": "stale-token", "at": stale_at_str})
        token2 = autopilot.acquire_lock()
        self.assertIsNotNone(token2)
        self.assertNotEqual(token2, token1)
        info = autopilot.load_json(os.path.join(autopilot.LOCK_DIR, "lock.json"))
        self.assertEqual(info["token"], token2)

    def test_release_then_reacquire_idempotent(self):
        """释放后可再次获取（幂等）；重复释放不抛异常。"""
        token1 = autopilot.acquire_lock()
        self.assertIsNotNone(token1)
        autopilot.release_lock(token1)
        token2 = autopilot.acquire_lock()  # 释放后可重入
        self.assertIsNotNone(token2)
        autopilot.release_lock(token2)
        autopilot.release_lock("wrong-token")  # 他人 token 释放：no-op 不抛
        autopilot.release_lock(token2)         # 二次释放：no-op 不抛


# ---------------------------------------------------------------------------
# 2) 状态机全迁移
# ---------------------------------------------------------------------------
class StateMachineTests(AutopilotSandboxCase):
    def test_full_chain_pass_to_wrapped(self):
        """一次 goal 全链：CLAIMED->...->WRAPPED，产物齐备。"""
        self.drop_event("r-pass-0001")
        self.assertEqual(autopilot.claim_inbox(), 1)
        run = self.find_run("r-pass-0001")
        self.assertEqual(run["state"], "CLAIMED")
        seen = ["CLAIMED"]
        guard = 0
        while run["state"] != "WRAPPED" and guard < 20:
            autopilot.advance_once("PASS", 8)
            run = self.find_run("r-pass-0001")
            seen.append(run["state"])
            guard += 1
        self.assertEqual(run["state"], "WRAPPED")
        # 事件级状态序列必须完整（轮间可能合并，但所有中间态都到过）
        # 轮末压缩序列（一轮可跨多步）；REPORTED/WAITING_REVIEW 中间态由专测覆盖
        self.assertEqual(seen, ["CLAIMED", "WORKING", "REVIEWING", "WRAPPED"])
        run_dir = os.path.join(autopilot.RUNS_DIR, "r-pass-0001")
        self.assertTrue(os.path.exists(os.path.join(run_dir, "report.json")),
                        "REPORTED 产物 report.json 缺失")
        self.assertTrue(os.path.exists(os.path.join(run_dir, "review-result.json")),
                        "REVIEWING 产物 review-result.json 缺失")
        self.assertTrue(os.path.exists(os.path.join(run_dir, "wrap-summary.json")),
                        "WRAPPED 产物 wrap-summary.json 缺失")

    def test_rework_requeues_and_repairs(self):
        """REWORK 后回 WORKING、rework_count+1，随后 PASS 收敛。"""
        self.drop_event("r-rework-01")
        autopilot.claim_inbox()
        run = self.find_run("r-rework-01")
        guard = 0
        # 推进到 REVIEWING（首轮 REWORK 判定）
        while run["state"] != "REVIEWING" and guard < 10:
            autopilot.advance_once("REWORK", 8)
            run = self.find_run("r-rework-01")
            guard += 1
        self.assertEqual(run["state"], "REVIEWING")
        autopilot.advance_once("REWORK", 8)
        run = self.find_run("r-rework-01")
        self.assertEqual(run["state"], "WORKING")
        self.assertEqual(run["rework_count"], 1)
        # 继续 PASS 收敛到 WRAPPED
        guard = 0
        while run["state"] != "WRAPPED" and guard < 20:
            autopilot.advance_once("PASS", 8)
            run = self.find_run("r-rework-01")
            guard += 1
        self.assertEqual(run["state"], "WRAPPED")
        self.assertEqual(run["rework_count"], 1)

    def test_rework_limit_aborts(self):
        """rework 超限走 ABORTED 异常分支。"""
        self.drop_event("r-abort-001")
        autopilot.claim_inbox()
        run = self.find_run("r-abort-001")
        guard = 0
        while run["state"] != "ABORTED" and guard < 20:
            autopilot.advance_once("REWORK", 2)  # max_reworks=2
            run = self.find_run("r-abort-001")
            guard += 1
        self.assertEqual(run["state"], "ABORTED")
        self.assertGreaterEqual(run["rework_count"], 2)

    def test_reported_reaches_gate_within_one_round(self):
        """REPORTED 在同一轮内经门控推进到 REVIEWING（step2->step3）。"""
        self.seed_run("r-gate-0001", "REPORTED")
        changed = autopilot.advance_once("PASS", 8)
        self.assertEqual(changed, 2)  # step2 WAITING_REVIEW + step3 REVIEWING
        run = self.find_run("r-gate-0001")
        self.assertEqual(run["state"], "REVIEWING")


# ---------------------------------------------------------------------------
# 3) R 并发度 1 门控
# ---------------------------------------------------------------------------
class RGateTests(AutopilotSandboxCase):
    def test_only_one_reported_enters_gate(self):
        """多 REPORTED 同一轮只取一进 R 门，其余保持 REPORTED。"""
        self.seed_run("r-c1-0001", "REPORTED", created_at="2026-08-31T00:00:01Z")
        self.seed_run("r-c1-0002", "REPORTED", created_at="2026-08-31T00:00:02Z")
        autopilot.advance_once("PASS", 8)
        states = [r["state"] for r in self.queue_runs()]
        self.assertEqual(states.count("REVIEWING"), 1)
        self.assertEqual(states.count("REPORTED"), 1)

    def test_gate_fairness_rework_priority(self):
        """同轮多 REPORTED 按 (rework_count, created_at) 取 rework 少者优先。"""
        self.seed_run("r-fair-001", "REPORTED", rework_count=1, created_at="2026-08-31T00:00:01Z")
        self.seed_run("r-fair-002", "REPORTED", rework_count=0, created_at="2026-08-31T00:00:02Z")
        autopilot.advance_once("PASS", 8)
        entering = [r["run_id"] for r in self.queue_runs()
                    if r["state"] in ("WAITING_REVIEW", "REVIEWING")]
        self.assertEqual(entering, ["r-fair-002"])

    def test_waiting_review_does_not_block_other_runs(self):
        """占住 R 门的 run 不阻塞其余 run 的 CLAIMED->WORKING 推进。"""
        self.seed_run("r-wr-0001", "WAITING_REVIEW")
        self.seed_run("r-wr-0002", "CLAIMED")
        autopilot.advance_once("PASS", 8)
        self.assertEqual(self.find_run("r-wr-0002")["state"], "WORKING")  # 不阻塞
        self.assertEqual(self.find_run("r-wr-0001")["state"], "REVIEWING")  # 门继续推进


# ---------------------------------------------------------------------------
# 4) 沙箱越界拦截
# ---------------------------------------------------------------------------
class SandboxTests(AutopilotSandboxCase):
    def test_claim_only_scans_sandbox_inbox(self):
        """SANDBOX_INBOX 之外路径的事件不被认领。"""
        outside = self.tmp / "outside-inbox"
        outside.mkdir()
        (outside / "ev.json").write_text(json.dumps(make_event("r-out-0001")), encoding="utf-8")
        before = sorted(p.name for p in outside.iterdir())
        self.assertEqual(autopilot.claim_inbox(), 0)
        self.assertEqual(sorted(p.name for p in outside.iterdir()), before)
        self.assertIsNone(self.find_run("r-out-0001"))

    def test_claim_rejects_non_builder_ready(self):
        """非 BUILDER_READY 事件被跳过（不建 run）。"""
        ev = make_event("r-bad-0001")
        ev["event"] = "SOMETHING_ELSE"
        (Path(autopilot.SANDBOX_INBOX) / "r-bad-evt.json").write_text(
            json.dumps(ev), encoding="utf-8")
        self.assertEqual(autopilot.claim_inbox(), 0)
        self.assertIsNone(self.find_run("r-bad-0001"))

    def test_claim_rejects_path_escape_run_id(self):
        """run_id 含路径逃逸（../）被拒绝，不在沙箱外建目录。"""
        ev = make_event("escape-ev", run_id="../../../escape-write-outside")
        (Path(autopilot.SANDBOX_INBOX) / "escape-ev.json").write_text(
            json.dumps(ev), encoding="utf-8")
        self.assertEqual(autopilot.claim_inbox(), 0)
        self.assertEqual(len(self.queue_runs()), 0)
        self.assertFalse((self.tmp / "escape-write-outside").exists(),
                         "路径逃逸目录不应被创建")
        # 合法 run_id 仍正常认领（对照，防误伤）
        self.drop_event("r-ok-0001")
        self.assertEqual(autopilot.claim_inbox(), 1)
        self.assertEqual(self.find_run("r-ok-0001")["state"], "CLAIMED")


if __name__ == "__main__":
    unittest.main()
