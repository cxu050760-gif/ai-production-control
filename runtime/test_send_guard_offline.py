#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime.py"
ADAPTER = HERE / "send_guard_lite.py"
R1 = "https://chatgpt.com/c/1e1ebbbb-1111-2222-3333-000000000002"


def _msys(p):
    s = str(p).replace("\\", "/")
    return "/" + s[0].lower() + s[2:] if len(s) > 1 and s[1] == ":" else s


def _ready_wrapper(root):
    w = root / "stub_wrapper_ready.sh"
    w.write_text("#!/bin/bash\ncase \"$1\" in status) echo 'Bridge: READY'; echo 'Browser: chrome'; "
                 "echo 'Instance: deadbeef'; echo 'Upload: READY'; exit 0;; *) exit 2;; esac\n", encoding="utf-8")
    return _msys(w)


def _script_env(root, conversations):
    log = root / "transport_log.jsonl"
    cfg = root / "script.json"
    cfg.write_text(json.dumps({"conversations": conversations, "log": str(log)}, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ)
    env["APC_RUNTIME_STATE_ROOT"] = str(root / "state")
    env["APC_RUNTIME_BRIDGE_WRAPPER"] = _ready_wrapper(root)
    env["APC_RUNTIME_INJECT_BRIDGE_FAIL"] = "SCRIPT"
    env["APC_RUNTIME_INJECT_SCRIPT_FILE"] = str(cfg)
    return env


def _run_json(script, argv, env):
    proc = subprocess.run([sys.executable, str(script), *argv], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=180)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {"_raw": proc.stdout}
    return proc.returncode, out, proc.stdout + proc.stderr


@unittest.skipUnless(RUNTIME.exists(), "real runtime.py unavailable")
class SendGuardComposeTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_j2_send_enforces_contract_and_effect_authorization(self):
        goal = self.root / "goal.txt"; goal.write_text("Build X", encoding="utf-8")
        convs = {R1: {"sid": "rsid-guard", "replies": ["===REVIEW_VERDICT=== PASS"]}}
        env = _script_env(self.root, convs)
        code, out, raw = _run_json(ADAPTER, ["start", "--goal", "Build X", "--r-url", R1,
                                             "--acceptance", "A"], env)
        self.assertEqual(code, 0, raw)
        rid = out["run_id"]
        code, out, raw = _run_json(ADAPTER, ["send", "--run-id", rid, "--message", "review packet"], env)
        self.assertEqual(code, 0, raw[-800:])
        state = json.loads((Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / rid / "state.json").read_text())
        # Goal Contract binding present
        self.assertTrue(state.get("goal_contract_hash"))
        # Effect Safety authorization + record present and GRANTED
        self.assertTrue(state.get("effect_authorizations"))
        self.assertEqual(state["effect_safety"]["authorization_status"], "GRANTED")
        self.assertTrue(state["effect_safety"]["authorization_id"])

    def test_j3_router_run_records_contract_and_router_send_effects(self):
        import goal_contract_lite as gc
        goal = self.root / "goal.txt"; goal.write_text("Build a header.", encoding="utf-8")
        h = gc.build_contract(goal.read_text(), ["A"])["contract_hash"]
        convs = {
            "https://chatgpt.com/c/b0b0aaaa-1111-2222-3333-000000000001": {
                "sid": "bsid", "replies": [f"candidate v1\nGOAL_CONTRACT_HASH={h}"]},
            R1: {"sid": "rsid", "replies": ["===REVIEW_VERDICT=== PASS"]},
        }
        env = _script_env(self.root, convs)
        code, out, raw = _run_json(ADAPTER, [
            "router-run", "--goal-file", str(goal),
            "--b-url", "https://chatgpt.com/c/b0b0aaaa-1111-2222-3333-000000000001",
            "--r-url", R1, "--acceptance", "A", "--max-rounds", "1", "--timeout", "30"], env)
        self.assertEqual(code, 0, raw[-800:])
        state = json.loads((Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / out["run_id"] / "state.json").read_text())
        self.assertTrue(state.get("goal_contract_hash"))
        ops = [r.get("operation") for r in state.get("effect_safety_log", [])]
        self.assertIn("router-send", ops)
        self.assertEqual(state["effect_safety"]["authorization_status"], "GRANTED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
