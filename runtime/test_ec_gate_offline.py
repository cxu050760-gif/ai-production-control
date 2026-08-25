#!/usr/bin/env python3
"""Offline tests for V0.6 Slice B: EC-lite enforcement (ec-gate + send gate).

The frozen policy table: HALT freezes every gated action (definitions #23/#41);
STOP_RETRY blocks transport (send/router) but still allows step recording;
NO_PROGRESS keeps transport open so the escalation itself can travel
(definition #19); PROCEED allows everything. The official send path gains the
EC gate as the outermost guard of send_guard_lite, fail-closed, without ever
modifying the wrapped command.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime.py"
EC = HERE / "ec_lite.py"
ADAPTER = HERE / "send_guard_lite.py"
R1 = "https://chatgpt.com/c/1e1ebbbb-1111-2222-3333-000000000002"

sys.path.insert(0, str(HERE))
import ec_lite as ecl  # noqa: E402


def _msys(p):
    s = str(p).replace("\\", "/")
    return "/" + s[0].lower() + s[2:] if len(s) > 1 and s[1] == ":" else s


def _run(cmd, argv, env):
    proc = subprocess.run([sys.executable, str(cmd), *argv], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env, timeout=180)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {"_raw": proc.stdout}
    return proc.returncode, out, proc.stdout + proc.stderr


class PolicyTableTests(unittest.TestCase):
    def test_p1_halt_blocks_everything(self):
        for action in ("send", "step", "router"):
            allowed, reason = ecl.ec_gate_policy("HALT", action)
            self.assertFalse(allowed, action)
            self.assertIn("lifecycle frozen", reason)

    def test_p2_stop_retry_blocks_transport_only(self):
        self.assertFalse(ecl.ec_gate_policy("STOP_RETRY", "send")[0])
        self.assertFalse(ecl.ec_gate_policy("STOP_RETRY", "router")[0])
        self.assertTrue(ecl.ec_gate_policy("STOP_RETRY", "step")[0])

    def test_p3_no_progress_keeps_transport_open(self):
        for action in ("send", "step", "router"):
            allowed, reason = ecl.ec_gate_policy("NO_PROGRESS", action)
            self.assertTrue(allowed, action)
        self.assertIn("escalation pending", ecl.ec_gate_policy("NO_PROGRESS", "send")[1])

    def test_p4_proceed_allows_everything(self):
        for action in ("send", "step", "router"):
            self.assertTrue(ecl.ec_gate_policy("PROCEED", action)[0])

    def test_p5_stop_retry_unknown_action_denied(self):
        # R NEXT_ACTION case: unknown action under STOP_RETRY must not pass.
        allowed, reason = ecl.ec_gate_policy("STOP_RETRY", "teleport")
        self.assertFalse(allowed)
        self.assertIn("fail-closed", reason)

    def test_p6_unknown_verdict_send_denied(self):
        # R NEXT_ACTION case: unknown verdict must not default-allow transport.
        allowed, reason = ecl.ec_gate_policy("WEIRD_VERDICT", "send")
        self.assertFalse(allowed)
        self.assertIn("fail-closed", reason)

    def test_p7_proceed_unknown_action_denied(self):
        # Even under PROCEED an unknown action is denied (no default allow).
        allowed, reason = ecl.ec_gate_policy("PROCEED", "explode")
        self.assertFalse(allowed)
        self.assertIn("fail-closed", reason)

    def test_p8_known_matrix_complete_no_fail_closed(self):
        # Every known verdict x known action combination has an explicit ruling;
        # fail-closed must fire only for genuinely unknown combinations.
        for verdict in ecl.KNOWN_EC_VERDICTS:
            for action in ecl.KNOWN_EC_ACTIONS:
                allowed, reason = ecl.ec_gate_policy(verdict, action)
                self.assertNotIn("fail-closed", reason, (verdict, action))
                self.assertIsInstance(allowed, bool)


class GateCliTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.env = dict(os.environ)
        self.env["APC_RUNTIME_STATE_ROOT"] = str(self.root)
        self.env.pop("APC_EC_MAX_RETRY", None)
        self.env.pop("APC_EC_NO_PROGRESS_ACTIONS", None)
        code, out, raw = _run(RUNTIME, ["start", "--goal", "ec gate test",
                                        "--r-url", "https://chatgpt.com/c/ecgate0001"],
                              self.env)
        self.assertEqual(code, 0, raw)
        self.rid = out["run_id"]

    def tearDown(self):
        self.td.cleanup()

    def _gate(self, action, env=None):
        return _run(EC, ["ec-gate", "--run-id", self.rid, "--action", action],
                    env or self.env)

    def _record(self, event, env=None):
        return _run(EC, ["ec-record", "--run-id", self.rid, "--event", event],
                    env or self.env)

    def _journal(self):
        return (self.root / "runs" / self.rid / "journal.jsonl").read_text(encoding="utf-8")

    def test_c1_fresh_run_gate_allows(self):
        code, out, raw = self._gate("send")
        self.assertEqual(code, 0, raw)
        self.assertTrue(out["allowed"])
        self.assertEqual(out["verdict"], "PROCEED")

    def test_c2_stop_retry_blocks_send_allows_step(self):
        for _ in range(3):
            code, out, raw = self._record("failure")
            self.assertEqual(code, 0, raw)
        code, out, raw = self._gate("send")
        self.assertEqual(code, 5, raw)
        self.assertEqual(out["status"], "DENIED")
        self.assertEqual(out["verdict"], "STOP_RETRY")
        self.assertIn("CHANGE_TOOL", out["ec_actions"])
        code, out, raw = self._gate("step")
        self.assertEqual(code, 0, raw)
        self.assertTrue(out["allowed"])
        self.assertIn("EC_GATE", self._journal())

    def test_c3_artifact_reopens_transport(self):
        for _ in range(3):
            self._record("failure")
        code, out, raw = self._gate("send")
        self.assertEqual(code, 5, raw)
        code, out, raw = self._record("artifact")
        self.assertEqual(code, 0, raw)
        code, out, raw = self._gate("send")
        self.assertEqual(code, 0, raw)
        self.assertTrue(out["allowed"])

    def test_c4_pause_halts_gate_resume_reopens(self):
        code, out, raw = _run(RUNTIME, ["directive", "--run-id", self.rid, "PAUSE"], self.env)
        self.assertEqual(code, 0, raw)
        for action in ("send", "step"):
            code, out, raw = self._gate(action)
            self.assertEqual(code, 5, raw)
            self.assertEqual(out["verdict"], "HALT")
        code, out, raw = _run(RUNTIME, ["directive", "--run-id", self.rid, "RESUME"], self.env)
        self.assertEqual(code, 0, raw)
        code, out, raw = self._gate("send")
        self.assertEqual(code, 0, raw)

    def test_c5_no_progress_allows_send_with_escalation_note(self):
        env = dict(self.env)
        env["APC_EC_NO_PROGRESS_ACTIONS"] = "5"
        for _ in range(5):
            code, out, raw = self._record("action", env)
            self.assertEqual(code, 0, raw)
        code, out, raw = self._gate("send", env)
        self.assertEqual(code, 0, raw)
        self.assertTrue(out["allowed"])
        self.assertEqual(out["verdict"], "NO_PROGRESS")
        self.assertIn("escalation pending", out["note"])

    def test_c6_missing_run(self):
        code, out, raw = _run(EC, ["ec-gate", "--run-id", "RUN-20260825-110000-c001",
                                   "--action", "send"], self.env)
        self.assertEqual(code, 4, raw)
        self.assertEqual(out["status"], "RUN_NOT_FOUND")

    def test_c7_cli_unknown_action_rejected(self):
        # R NEXT_ACTION case: CLI action outside send|step|router must not pass.
        code, out, raw = self._gate("teleport")
        self.assertEqual(code, 2, raw)
        self.assertEqual(out["status"], "INVALID_ACTION")
        self.assertNotIn("EC_GATE", self._journal())  # rejected before journaling


def _ready_wrapper(root):
    w = root / "stub_wrapper_ready.sh"
    w.write_text("#!/bin/bash\ncase \"$1\" in status) echo 'Bridge: READY'; echo 'Browser: chrome'; "
                 "echo 'Instance: deadbeef'; echo 'Upload: READY'; exit 0;; *) exit 2;; esac\n",
                 encoding="utf-8")
    return _msys(w)


def _script_env(root, conversations):
    log = root / "transport_log.jsonl"
    cfg = root / "script.json"
    cfg.write_text(json.dumps({"conversations": conversations, "log": str(log)},
                              ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ)
    env["APC_RUNTIME_STATE_ROOT"] = str(root / "state")
    env["APC_RUNTIME_BRIDGE_WRAPPER"] = _ready_wrapper(root)
    env["APC_RUNTIME_INJECT_BRIDGE_FAIL"] = "SCRIPT"
    env["APC_RUNTIME_INJECT_SCRIPT_FILE"] = str(cfg)
    return env


class SendPathComposeTests(unittest.TestCase):
    """The EC gate sits outermost on the official send path: blocked sends must
    never reach transport; allowed sends must flow exactly as before."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.env = _script_env(self.root,
                               {R1: {"sid": "rsid-ec", "replies": ["===REVIEW_VERDICT=== PASS"]}})
        code, out, raw = _run(ADAPTER, ["start", "--goal", "Build X", "--r-url", R1,
                                        "--acceptance", "A"], self.env)
        self.assertEqual(code, 0, raw)
        self.rid = out["run_id"]
        self.log = self.root / "transport_log.jsonl"

    def tearDown(self):
        self.td.cleanup()

    def _log_lines(self):
        return len(self.log.read_text(encoding="utf-8").splitlines()) if self.log.exists() else 0

    def test_s1_stop_retry_blocks_send_before_transport(self):
        for _ in range(3):
            code, out, raw = _run(EC, ["ec-record", "--run-id", self.rid,
                                       "--event", "failure"], self.env)
            self.assertEqual(code, 0, raw)
        before = self._log_lines()
        code, out, raw = _run(ADAPTER, ["send", "--run-id", self.rid,
                                        "--message", "review packet"], self.env)
        self.assertEqual(code, 5, raw)
        self.assertEqual(out["status"], "DENIED")
        self.assertIn("EC_GATE", out["reason"])
        self.assertEqual(self._log_lines(), before)  # zero transport happened
        jl = (self.root / "state" / "runs" / self.rid / "journal.jsonl").read_text(
            encoding="utf-8")
        self.assertIn("EC_GATE_DENIAL", jl)

    def test_s2_paused_run_blocks_send_before_transport(self):
        code, out, raw = _run(RUNTIME, ["directive", "--run-id", self.rid, "PAUSE"], self.env)
        self.assertEqual(code, 0, raw)
        before = self._log_lines()
        code, out, raw = _run(ADAPTER, ["send", "--run-id", self.rid,
                                        "--message", "review packet"], self.env)
        self.assertEqual(code, 5, raw)
        self.assertIn("EC_GATE", out["reason"])
        self.assertEqual(out["verdict"], "HALT")
        self.assertEqual(self._log_lines(), before)

    def test_s3_healthy_run_send_still_flows(self):
        code, out, raw = _run(ADAPTER, ["send", "--run-id", self.rid,
                                        "--message", "review packet"], self.env)
        self.assertEqual(code, 0, raw[-800:])
        self.assertGreater(self._log_lines(), 0)  # scripted transport did happen


if __name__ == "__main__":
    unittest.main(verbosity=2)
