#!/usr/bin/env python3
"""GATE-6 转真测试（批次 C，HARDENING-PLAN 两环转真）。

Covers:
  B1  build_taskgraph 挂 brain_selection：v0.7 契约无 brain 绑定 → mode="rule"
      （显式标注，非 stub 伪装）；brain_pick 契约模式：带 brain 绑定的 proposal
      → mode="contract"（真实契约路径优先于规则分档）
  R1  RelaySubmitExecutor L3 武装门：mode=relay 无 APC_RELAY_REAL=1 → FAILURE
      且不 spawn 子进程（RELAY_REAL_NOT_ARMED）
  R2  RelaySubmitExecutor 契约 fail-closed：mode=relay + evidence 缺失
      （APC_RELAY_REAL=1 已武装）→ relay_autopilot rc=2 → FAILURE，stderr 含
      RELAY_INPUT_CONTRACT（真实主链拒绝路径）
  R3  RelaySubmitExecutor mock 正向：mode=mock 全配置有效 → 子进程 rc=0 →
      SUCCESS，事件/账本落在 APC_RELAY_STATE_ROOT 沙箱（零生产写入）

All offline: 全部状态根/沙箱隔离到 tmp；不触真实 relay 状态、零真实额度。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
SCRIPTS = HERE.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import parallel_scheduler as ps  # noqa: E402
import task_graph as tg  # noqa: E402
import brain_bridge  # noqa: E402


def _make_git_repo(tmp: Path) -> str:
    repo = Path(tmp) / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "--allow-empty", "-q",
                    "-m", "init"], check=True)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    return head


class BrainContractModeTests(unittest.TestCase):
    """GATE-6 环 1：task_graph/brain_bridge 接真实契约（或显式标注规则模式）。"""

    def test_b1_build_taskgraph_attaches_rule_mode_selection(self):
        graph = brain_bridge.build_taskgraph("产出季度报告，包含销售数据")
        self.assertTrue(graph["valid"], graph)
        sel = graph.get("brain_selection")
        self.assertIsInstance(sel, dict)
        self.assertEqual(sel["mode"], "rule",
                         "v0.7 契约无 brain 绑定 → 必须显式标注规则模式")
        self.assertTrue(sel["brain_id"])

    def test_b2_brain_pick_contract_mode_overrides_rule(self):
        proposal = {"proposal_id": "abcd1234efgh5678",
                    "brain": {"brain_id": "brain-chatgpt-web"}}
        sel = tg.brain_pick("任意目标文本", proposal=proposal)
        self.assertEqual(sel["mode"], "contract")
        self.assertEqual(sel["brain_id"], "brain-chatgpt-web")
        self.assertEqual(sel["proposal_id"], "abcd1234efgh5678")

    def test_b3_brain_pick_rule_mode_explicit_without_proposal(self):
        sel = tg.brain_pick("简单的格式转换任务")
        self.assertEqual(sel["mode"], "rule")

    def test_b4_brain_pick_falls_back_to_rule_when_binding_missing(self):
        proposal = {"proposal_id": "abcd1234efgh5678"}  # 无 brain 绑定
        sel = tg.brain_pick("任意目标文本", proposal=proposal)
        self.assertEqual(sel["mode"], "rule")


class RelaySubmitExecutorTests(unittest.TestCase):
    """GATE-6 环 2：parallel_scheduler 接 relay_autopilot 主链（真实执行器）。"""

    def _env(self, tmp: str) -> dict:
        env = dict(os.environ)
        relay_root = Path(tmp) / "relay-state"
        env["APC_RELAY_STATE_ROOT"] = str(relay_root)
        env["APC_RUNTIME_STATE_ROOT"] = str(Path(tmp) / "apc-state")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        # 沙箱最小中继配置（cmd_submit 需 relay.config + builder binding）
        (relay_root / "bindings").mkdir(parents=True, exist_ok=True)
        (relay_root / "relay.config.json").write_text(
            json.dumps({"project_id": "P-SANDBOX",
                        "automation": {"current_milestone": "V1.1"}}),
            encoding="utf-8")
        (relay_root / "bindings" / "builder.json").write_text(
            json.dumps({"provider": "sandbox", "model": "mock",
                        "conversation_id": "conv-sandbox", "generation": 1}),
            encoding="utf-8")
        return env

    def _fixtures(self, tmp: str):
        base = Path(tmp)
        head = _make_git_repo(base)
        pkt = base / "packet.txt"
        pkt.write_text("packet", encoding="utf-8")
        ev1 = base / "ev1.json"
        ev1.write_text("{}", encoding="utf-8")
        return head, str(pkt), str(ev1)

    def _run_task(self, tmp: str, relay_cfg: dict, env: dict):
        old_env = os.environ.copy()
        os.environ.update(env)
        try:
            fx = ps.ParallelScheduler(state_root=str(Path(tmp) / "ps"),
                                      timeout_sec=90)
            fx.submit({"task_id": "T-RELAY", "goal": "GATE-6 relay 主链转真验证",
                       "relay": relay_cfg})
            fx.run_until_idle()
            task = fx.tasks["T-RELAY"]
            return task["state"], task.get("result") or {}
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    def test_r1_l3_gate_blocks_unarmed_relay_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            head, pkt, ev1 = self._fixtures(tmp)
            cfg = {"mode": "relay", "repo_path": str(Path(tmp) / "repo"),
                   "review_packet": pkt, "evidence_paths": [ev1],
                   "candidate_commit": head}
            env = self._env(tmp)
            env.pop("APC_RELAY_REAL", None)          # 未武装
            state, res = self._run_task(tmp, cfg, env)
            self.assertEqual(state, ps.TASK_FAILED, res)
            self.assertEqual(res.get("outcome"), "FAILURE")
            self.assertIn("RELAY_REAL_NOT_ARMED", str(res.get("result")))
            self.assertIsNone(res.get("exit_code"))

    def test_r2_relay_contract_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            head, pkt, ev1 = self._fixtures(tmp)
            cfg = {"mode": "relay", "repo_path": str(Path(tmp) / "repo"),
                   "review_packet": pkt,
                   "evidence_paths": [ev1, str(Path(tmp) / "no-such-ev.json")],
                   "candidate_commit": head}
            env = self._env(tmp)
            env["APC_RELAY_REAL"] = "1"              # 已武装，但契约拒绝
            state, res = self._run_task(tmp, cfg, env)
            self.assertEqual(state, ps.TASK_FAILED, res)
            self.assertEqual(res.get("outcome"), "FAILURE", res)
            self.assertIn("RELAY_INPUT_CONTRACT", res.get("stderr_tail", ""), res)

    def test_r3_mock_mode_success_in_sandbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            head, pkt, ev1 = self._fixtures(tmp)
            cfg = {"mode": "mock", "repo_path": str(Path(tmp) / "repo"),
                   "review_packet": pkt, "evidence_paths": [ev1],
                   "candidate_commit": head}
            env = self._env(tmp)
            state, res = self._run_task(tmp, cfg, env)
            self.assertEqual(state, ps.TASK_COMPLETED, res)
            self.assertEqual(res.get("outcome"), "SUCCESS", res)
            self.assertEqual(res.get("exit_code"), 0)
            # 沙箱隔离：事件落在 APC_RELAY_STATE_ROOT，非生产 relay 根
            sandbox_inbox = Path(env["APC_RELAY_STATE_ROOT"]) / "autopilot" / "inbox"
            self.assertTrue(sandbox_inbox.exists(), "mock 事件应落在隔离沙箱")
            self.assertEqual(len(list(sandbox_inbox.glob("*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
