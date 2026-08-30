#!/usr/bin/env python3
"""Offline tests for V0.6 Slice A: EC-lite (rules/counters execution correction).

EC-lite must be pure deterministic runtime logic: durable counters in the
canonical RUN state, frozen threshold rules, journaled events/corrections, and
lifecycle supremacy (PAUSE/STOP freezes worker action, definitions #23/#41).
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


def _run(cmd, argv, env):
    proc = subprocess.run([sys.executable, str(cmd), *argv], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env, timeout=120)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {"_raw": proc.stdout}
    return proc.returncode, out, proc.stdout + proc.stderr


class EcLiteTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.env = dict(os.environ)
        self.env["APC_RUNTIME_STATE_ROOT"] = str(self.root)
        self.env.pop("APC_EC_MAX_RETRY", None)
        self.env.pop("APC_EC_NO_PROGRESS_ACTIONS", None)
        code, out, raw = _run(RUNTIME, ["start", "--goal", "ec-lite test run",
                                        "--r-url", "https://chatgpt.com/c/ectest0001"], self.env)
        self.assertEqual(code, 0, raw)
        self.rid = out["run_id"]

    def tearDown(self):
        self.td.cleanup()

    def _check(self, env=None):
        return _run(EC, ["ec-check", "--run-id", self.rid], env or self.env)

    def _record(self, event, env=None):
        return _run(EC, ["ec-record", "--run-id", self.rid, "--event", event],
                    env or self.env)

    def _journal(self):
        return (self.root / "runs" / self.rid / "journal.jsonl").read_text(encoding="utf-8")

    def test_e1_fresh_run_proceeds(self):
        code, out, raw = self._check()
        self.assertEqual(code, 0, raw)
        self.assertEqual(out["verdict"], "PROCEED")
        self.assertEqual(out["counters"]["consecutive_failures"], 0)
        self.assertEqual(out["thresholds"], {"max_retry": 3, "no_progress_actions": 50})

    def test_e2_repeated_failure_stops_retry(self):
        for _ in range(3):
            code, out, raw = self._record("failure")
            self.assertEqual(code, 0, raw)
        code, out, raw = self._check()
        self.assertEqual(code, 0, raw)
        self.assertEqual(out["verdict"], "STOP_RETRY")
        self.assertEqual(out["actions"], ["CHANGE_TOOL", "REQUEUE"])
        self.assertEqual(out["counters"]["corrections"], 1)

    def test_e3_artifact_resets_counters(self):
        self._record("failure")
        self._record("failure")
        code, out, raw = self._record("artifact")
        self.assertEqual(code, 0, raw)
        self.assertEqual(out["consecutive_failures"], 0)
        self.assertEqual(out["actions_since_artifact"], 0)
        code, out, raw = self._check()
        self.assertEqual(out["verdict"], "PROCEED")

    def test_e4_busy_but_no_progress(self):
        env = dict(self.env)
        env["APC_EC_NO_PROGRESS_ACTIONS"] = "5"
        for _ in range(5):
            code, out, raw = self._record("action", env)
            self.assertEqual(code, 0, raw)
        code, out, raw = self._check(env)
        self.assertEqual(code, 0, raw)
        self.assertEqual(out["verdict"], "NO_PROGRESS")
        self.assertEqual(out["actions"], ["ESCALATE_C"])

    def test_e5_paused_run_halts_regardless(self):
        self._record("failure")
        self._record("failure")
        self._record("failure")
        code, out, raw = _run(RUNTIME, ["directive", "--run-id", self.rid, "PAUSE"], self.env)
        self.assertEqual(code, 0, raw)
        code, out, raw = self._check()
        self.assertEqual(code, 0, raw)
        self.assertEqual(out["verdict"], "HALT")
        self.assertEqual(out["actions"], ["OBEY_LIFECYCLE"])

    def test_e6_missing_run_not_found(self):
        code, out, raw = _run(EC, ["ec-check", "--run-id", "RUN-20260824-190006-a007"],
                              self.env)
        self.assertEqual(code, 4, raw)
        self.assertEqual(out["status"], "RUN_NOT_FOUND")
        code, out, raw = _run(EC, ["ec-record", "--run-id", "RUN-20260824-190006-a007",
                                   "--event", "failure"], self.env)
        self.assertEqual(code, 4, raw)

    def test_e7_invalid_event_denied(self):
        code, out, raw = _run(EC, ["ec-record", "--run-id", self.rid, "--event", "explosion"],
                              self.env)
        self.assertEqual(code, 5, raw)
        self.assertEqual(out["status"], "DENIED")

    def test_e8_events_and_checks_are_journaled(self):
        for ev in ("failure", "artifact"):
            code, out, raw = self._record(ev)
            self.assertEqual(code, 0, raw)
        self._check()
        jl = self._journal()
        self.assertIn('"EC_EVENT"', jl)
        self.assertIn('"EC_CHECK"', jl)
        self.assertIn('"ec_event": "failure"', jl)

    def test_e9_threshold_override_via_env(self):
        env = dict(self.env)
        env["APC_EC_MAX_RETRY"] = "1"
        self._record("failure", env)
        code, out, raw = self._check(env)
        self.assertEqual(code, 0, raw)
        self.assertEqual(out["verdict"], "STOP_RETRY")
        self.assertEqual(out["thresholds"]["max_retry"], 1)

    def test_e10_counters_survive_process_restart(self):
        # Every _record/_check above is already a fresh process; assert the
        # durable counter explicitly across two separate invocations.
        for _ in range(2):
            code, out, raw = self._record("failure")
            self.assertEqual(code, 0, raw)
        code, out, raw = self._check()
        self.assertEqual(out["counters"]["consecutive_failures"], 2)
        self.assertEqual(out["verdict"], "PROCEED")  # 2 < default max_retry=3


if __name__ == "__main__":
    unittest.main(verbosity=2)
