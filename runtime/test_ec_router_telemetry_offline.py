#!/usr/bin/env python3
"""Offline tests for V0.6 Slice D: router-path EC telemetry.

A failing router transport records an EC failure at the seam (and still
re-raises, so callers keep converting to HARD_BLOCKED); router commands
record artifact (R PASS) or failure (R REWORK) after an OK completion. Gate
denials are never counted.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
EC = HERE / "ec_lite.py"
ADAPTER = HERE / "send_guard_lite.py"
R1 = "https://chatgpt.com/c/1e1ebbbb-1111-2222-3333-000000000002"
B1 = "https://chatgpt.com/c/b0b0aaaa-1111-2222-3333-000000000001"

sys.path.insert(0, str(HERE))
import goal_contract_lite as gc  # noqa: E402


def _msys(p):
    s = str(p).replace("\\", "/")
    return "/" + s[0].lower() + s[2:] if len(s) > 1 and s[1] == ":" else s


def _ready_wrapper(root):
    w = root / "stub_wrapper_ready.sh"
    w.write_text("#!/bin/bash\ncase \"$1\" in status) echo 'Bridge: READY'; echo 'Browser: chrome'; "
                 "echo 'Instance: deadbeef'; echo 'Upload: READY'; exit 0;; *) exit 2;; esac\n",
                 encoding="utf-8")
    return _msys(w)


def _script_env(root, conversations, seam: str = "SCRIPT"):
    log = root / "transport_log.jsonl"
    cfg = root / "script.json"
    cfg.write_text(json.dumps({"conversations": conversations, "log": str(log)},
                              ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ)
    env["APC_RUNTIME_STATE_ROOT"] = str(root / "state")
    env["APC_RUNTIME_BRIDGE_WRAPPER"] = _ready_wrapper(root)
    env["APC_RUNTIME_INJECT_BRIDGE_FAIL"] = seam
    env["APC_RUNTIME_INJECT_SCRIPT_FILE"] = str(cfg)
    return env


def _run(cmd, argv, env):
    proc = subprocess.run([sys.executable, str(cmd), *argv], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env, timeout=240)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {"_raw": proc.stdout}
    return proc.returncode, out, proc.stdout + proc.stderr


class RouterTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.goal = self.root / "goal.txt"
        self.goal.write_text("Build a header.", encoding="utf-8")
        self.h = gc.build_contract(self.goal.read_text(), ["A"])["contract_hash"]

    def tearDown(self):
        self.td.cleanup()

    def _state(self, env, rid):
        return json.loads((Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / rid /
                           "state.json").read_text(encoding="utf-8"))

    def _journal(self, env, rid):
        return (Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / rid /
                "journal.jsonl").read_text(encoding="utf-8")

    def _router_run(self, env):
        return _run(ADAPTER, ["router-run", "--goal-file", str(self.goal),
                              "--b-url", B1, "--r-url", R1, "--acceptance", "A",
                              "--max-rounds", "1", "--timeout", "30"], env)

    def test_r1_router_pass_records_artifact(self):
        convs = {B1: {"sid": "bsid", "replies": [f"candidate v1\nGOAL_CONTRACT_HASH={self.h}"]},
                 R1: {"sid": "rsid", "replies": ["===REVIEW_VERDICT=== PASS"]}}
        env = _script_env(self.root, convs)
        code, out, raw = self._router_run(env)
        self.assertEqual(code, 0, raw[-800:])
        st = self._state(env, out["run_id"])
        self.assertGreaterEqual(st["ec"]["artifact_count"], 1)
        self.assertEqual(st["ec"]["consecutive_failures"], 0)
        jl = self._journal(env, out["run_id"])
        self.assertIn('"ec_event": "artifact"', jl)
        self.assertIn('"source": "auto"', jl)

    def test_r2_router_transport_failure_records_failure(self):
        env = _script_env(self.root, {}, seam="1")  # every bridge call fails
        code, out, raw = self._router_run(env)
        self.assertNotEqual(code, 0, raw[-800:])
        rid = out.get("run_id")
        self.assertTrue(rid, raw[-800:])
        st = self._state(env, rid)
        self.assertGreaterEqual(st["ec"]["consecutive_failures"], 1)
        self.assertIn('"ec_event": "failure"', self._journal(env, rid))
        self.assertIn('"source": "auto"', self._journal(env, rid))

    def test_r3_gate_blocked_router_not_double_counted(self):
        convs = {B1: {"sid": "bsid", "replies": [f"candidate v1\nGOAL_CONTRACT_HASH={self.h}"]},
                 R1: {"sid": "rsid", "replies": ["===REVIEW_VERDICT=== PASS"]}}
        env = _script_env(self.root, convs)
        code, out, raw = _run(ADAPTER, ["router-start", "--goal-file", str(self.goal),
                                        "--b-url", B1, "--r-url", R1,
                                        "--acceptance", "A"], env)
        self.assertEqual(code, 0, raw[-800:])
        rid = out["run_id"]
        for _ in range(3):
            code, out2, raw2 = _run(EC, ["ec-record", "--run-id", rid,
                                         "--event", "failure"], env)
            self.assertEqual(code, 0, raw2)
        code, out, raw = _run(ADAPTER, ["router-continue", "--run-id", rid,
                                        "--timeout", "30"], env)
        self.assertNotEqual(code, 0, raw[-800:])
        st = self._state(env, rid)
        self.assertEqual(st["ec"]["consecutive_failures"], 3)  # gate denial not counted
        self.assertIn("EC_GATE_DENIAL", self._journal(env, rid))

    def test_r4_old_gate_denial_masks_new_failure(self):
        convs = {B1: {"sid": "bsid", "replies": ["bad output"]},
                 R1: {"sid": "rsid", "replies": ["===REVIEW_VERDICT=== REWORK"]}}
        env = _script_env(self.root, convs)
        code, out, raw = _run(ADAPTER, ["router-start", "--goal-file", str(self.goal),
                                        "--b-url", B1, "--r-url", R1,
                                        "--acceptance", "A"], env)
        self.assertEqual(code, 0, raw[-800:])
        rid = out["run_id"]
        # inject old EC_GATE_DENIAL into journal
        jp = Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / rid / "journal.jsonl"
        with open(jp, "a", encoding="utf-8") as f:
            f.write('{"ts":"old","event":"EC_GATE_DENIAL","action":"router"}\n')
        code, out, raw = _run(ADAPTER, ["router-continue", "--run-id", rid,
                                        "--timeout", "30"], env)
        st = self._state(env, rid)
        self.assertGreaterEqual(st["ec"]["consecutive_failures"], 1)

    def test_r5_done_idempotent_no_double_count(self):
        convs = {B1: {"sid": "bsid", "replies": [f"candidate v1\nGOAL_CONTRACT_HASH={self.h}"]},
                 R1: {"sid": "rsid", "replies": ["===REVIEW_VERDICT=== PASS"]}}
        env = _script_env(self.root, convs)
        code, out, raw = self._router_run(env)
        self.assertEqual(code, 0, raw[-800:])
        rid = out["run_id"]
        st1 = self._state(env, rid)
        art1 = st1["ec"]["artifact_count"]
        code2, out2, raw2 = _run(ADAPTER, ["router-continue", "--run-id", rid,
                                           "--timeout", "30"], env)
        st2 = self._state(env, rid)
        self.assertEqual(st2["ec"]["artifact_count"], art1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
