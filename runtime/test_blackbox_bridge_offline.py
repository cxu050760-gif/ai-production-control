"""blackbox_bridge 测试：§65 四动词补齐（RESULT / HUMAN_GATE）接线正确性。

离线：全部使用 tmp 目录 fixture，不碰生产状态根（红线）。
"""

import json
import os
import sys
import tempfile
import unittest
from importlib import import_module
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
bb = import_module("blackbox_bridge")


def _make_run(root: Path, run_id: str, status: str, verdict=None,
              blocked_reason=None, current_step="review completed",
              gate_flag=False, reply_text: str = "") -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": run_id,
        "revision": 3,
        "status": status,
        "goal": "产出一份测试报告",
        "worker_identity": "test-worker",
        "last_r_verdict": verdict,
        "current_step": current_step,
        "next_action": "",
        "blocked_reason": blocked_reason,
        "effect_human_gate_required": gate_flag,
        "updated_at": "2026-08-30T10:00:00+00:00",
        "metrics": {"r_roundtrips": 1, "r_wait_time_sec": 10.0, "bridge_retries": 0},
    }
    (run_dir / "state.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8")
    if reply_text:
        (run_dir / "reply_epoch1_1234567890_abc123.txt").write_text(
            reply_text, encoding="utf-8")
    return run_dir


_REPLY_PASS = (
    "===REVIEW_VERDICT=== PASS\n"
    "\n"
    "===NEXT_ACTION===\n"
    "本次提交的证据通过，没有需要继续返工的问题。\n"
    "===CHATGPT_DONE:WB_20260818_185753_000000===\n"
)
_REPLY_REWORK = (
    "===REVIEW_VERDICT=== REWORK\n"
    "\n"
    "===NEXT_ACTION===\n"
    "阶段方向正确，但有 2 个问题需要修：1) 格式；2) 证据。\n"
    "===CHATGPT_DONE:WB_20260818_185753_000000===\n"
)


class TestParseReply(unittest.TestCase):
    def test_parse_pass(self):
        r = bb.parse_reply(_REPLY_PASS)
        self.assertEqual(r["verdict"], "PASS")
        self.assertIn("没有需要继续返工", r["conclusion"])

    def test_parse_rework(self):
        r = bb.parse_reply(_REPLY_REWORK)
        self.assertEqual(r["verdict"], "REWORK")
        self.assertIn("需要修", r["conclusion"])
        self.assertNotIn("CHATGPT_DONE", r["conclusion"])

    def test_parse_no_verdict(self):
        r = bb.parse_reply("some random text")
        self.assertIsNone(r["verdict"])


class TestCmdResult(unittest.TestCase):
    def test_pass_done(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_run(root, "RUN-T1", "DONE", verdict="PASS",
                      reply_text=_REPLY_PASS)
            out = _run_capture(["result", "--run-id", "RUN-T1",
                                "--state-root", td])
            self.assertEqual(out["rc"], 0)
            self.assertTrue(out["json"]["ok"])
            self.assertEqual(out["json"]["verdict"], "PASS")
            self.assertTrue(out["json"]["final"])

    def test_rework_not_final(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_run(root, "RUN-T2", "RUNNING", verdict="REWORK",
                      reply_text=_REPLY_REWORK)
            out = _run_capture(["result", "--run-id", "RUN-T2",
                                "--state-root", td])
            self.assertEqual(out["rc"], 0)
            self.assertEqual(out["json"]["verdict"], "REWORK")
            self.assertFalse(out["json"]["final"])

    def test_no_verdict_rc2(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_run(root, "RUN-T3", "RUNNING", verdict=None)
            out = _run_capture(["result", "--run-id", "RUN-T3",
                                "--state-root", td])
            self.assertEqual(out["rc"], 2)
            self.assertIsNone(out["json"]["verdict"])

    def test_run_not_found_rc1(self):
        with tempfile.TemporaryDirectory() as td:
            out = _run_capture(["result", "--run-id", "RUN-NOPE",
                                "--state-root", td])
            self.assertEqual(out["rc"], 1)
            self.assertEqual(out["json"]["error"], "RUN_NOT_FOUND")


class TestCmdHumanGate(unittest.TestCase):
    def test_lists_waiting(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_run(root, "RUN-G1", "HARD_BLOCKED", verdict="BLOCKED",
                      blocked_reason="R verdict BLOCKED: 需要人工决策。")
            _make_run(root, "RUN-G2", "PAUSED", verdict=None)
            _make_run(root, "RUN-G3", "DONE", verdict="PASS")
            out = _run_capture(["human-gate", "--state-root", td])
            self.assertEqual(out["rc"], 0)
            doc = out["json"]
            self.assertTrue(doc["ok"])
            self.assertEqual(doc["waiting_count"], 2)
            ids = {x["run_id"] for x in doc["waiting"]}
            self.assertEqual(ids, {"RUN-G1", "RUN-G2"})
            self.assertNotIn("RUN-G3", ids)

    def test_gate_flag_counts_waiting(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_run(root, "RUN-G4", "RUNNING", gate_flag=True)
            out = _run_capture(["human-gate", "--state-root", td])
            self.assertEqual(out["json"]["waiting_count"], 1)

    def test_no_waiting(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_run(root, "RUN-G5", "DONE", verdict="PASS")
            _make_run(root, "RUN-G6", "RUNNING", verdict=None)
            out = _run_capture(["human-gate", "--state-root", td])
            self.assertEqual(out["rc"], 0)
            self.assertEqual(out["json"]["waiting_count"], 0)

    def test_terminal_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_run(root, "RUN-G7", "STOPPED", verdict=None)
            out = _run_capture(["human-gate", "--state-root", td])
            self.assertEqual(out["json"]["waiting_count"], 0)
            self.assertEqual(out["json"]["terminal_count"], 1)

    def test_state_root_missing_rc1(self):
        out = _run_capture(["human-gate",
                            "--state-root", r"C:\nonexistent\state"])
        self.assertEqual(out["rc"], 1)
        self.assertEqual(out["json"]["error"], "STATE_ROOT_NOT_FOUND")


class TestDelegate(unittest.TestCase):
    def _fake_run_cmd(self) -> str:
        """创建一个存在的伪 run.cmd（仅用于触发委托层 ok=True 分支）。"""
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        fake = Path(td.name) / "run.cmd"
        fake.write_text("@echo off\n", encoding="utf-8")
        return str(fake)

    def test_work_delegates_not_found(self):
        out = _run_capture(["work", "--goal-file", "goal.txt",
                            "--run-cmd", r"C:\nonexistent\run.cmd"])
        # 生产 run.cmd 不存在（离线环境）-> 委托文档 rc=1，不模拟执行
        self.assertEqual(out["rc"], 1)
        self.assertEqual(out["json"]["error"], "RUN_CMD_NOT_FOUND")
        self.assertFalse(out["json"]["executed"])

    def test_report_delegates_not_found(self):
        out = _run_capture(["report", "--run-id", "RUN-X",
                            "--message-file", "r.txt",
                            "--run-cmd", r"C:\nonexistent\run.cmd"])
        self.assertEqual(out["rc"], 1)
        self.assertEqual(out["json"]["error"], "RUN_CMD_NOT_FOUND")
        self.assertFalse(out["json"]["executed"])

    def test_work_passthrough_r_url(self):
        out = _run_capture(["work", "--goal-file", "goal.txt",
                            "--r-url", "https://chatgpt.com/c/test123",
                            "--run-cmd", self._fake_run_cmd()])
        self.assertEqual(out["rc"], 0)
        doc = out["json"]
        self.assertTrue(doc["ok"])
        self.assertFalse(doc["executed"])
        self.assertTrue(doc["r_url_provided"])
        self.assertIn("--r-url https://chatgpt.com/c/test123", doc["invocation"])
        self.assertNotIn("<R会话URL>", doc["invocation"])

    def test_work_missing_r_url_placeholder(self):
        out = _run_capture(["work", "--goal-file", "goal.txt",
                            "--run-cmd", self._fake_run_cmd()])
        self.assertEqual(out["rc"], 0)
        doc = out["json"]
        self.assertTrue(doc["ok"])
        self.assertFalse(doc["executed"])
        self.assertFalse(doc["r_url_provided"])
        self.assertIn("<R会话URL>", doc["invocation"])

    def test_report_executed_false(self):
        out = _run_capture(["report", "--run-id", "RUN-X",
                            "--message-file", "r.txt",
                            "--run-cmd", self._fake_run_cmd()])
        self.assertEqual(out["rc"], 0)
        doc = out["json"]
        self.assertTrue(doc["ok"])
        self.assertFalse(doc["executed"])
        self.assertIn("--run-id RUN-X", doc["invocation"])
        self.assertIn("--message-file r.txt", doc["invocation"])


def _run_capture(argv: list) -> dict:
    """在子进程里跑 main，捕获退出码 + stdout JSON（避免污染本进程 stdout）。"""
    import subprocess
    proc = subprocess.run(
        [sys.executable, os.path.abspath(bb.__file__)] + argv,
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        doc = json.loads(proc.stdout)
    except json.JSONDecodeError:
        doc = {"raw": proc.stdout}
    return {"rc": proc.returncode, "json": doc, "stdout": proc.stdout,
            "stderr": proc.stderr}


if __name__ == "__main__":
    unittest.main()
