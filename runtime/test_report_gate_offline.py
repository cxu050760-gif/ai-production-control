#!/usr/bin/env python3
"""GATE-1#1 (hardening 2026-08-31): report must ride the production gate chain.

cmd_report is the ONLY production outbound path (cmd_report -> cmd_send). Before
this hardening, run.cmd routed `report` to goal_contract_lite only, which
installed the contract binding but NOT the effect-safety authorization gate nor
the EC lifecycle gate -- the identical defect send_guard_lite's docstring
records for `send` before Slice J2. run.cmd now routes `report` to
send_guard_lite (three gates, outermost-first: ec -> effect_safety ->
goal_contract, all fail-closed).

These tests verify, fully offline (stub bridge + injected script + tmp state
root, same seams as test_send_guard_offline.py):
  R1  report without an effect authorization is DENIED (gate bites)
  R2  report with a declared authorization is delivered, reviewed PASS, and
      the run finalizes DONE (gate does not obstruct the happy path)
  R3  report under a HALT lifecycle (non-RUNNING) is blocked by the EC gate
      before any transport happens
  R4  run.cmd anchors `report` to the send_guard target (regression anchor)
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
RUNTIME = HERE / "runtime.py"
ADAPTER = HERE / "send_guard_lite.py"
RUN_CMD = HERE / "run.cmd"
R1 = "https://chatgpt.com/c/1e1ebbbb-1111-2222-3333-000000000002"

SCENARIO_EGRESS_POLICY = {"default": ["PUBLIC", "INTERNAL"]}


def _load_rt():
    spec = importlib.util.spec_from_file_location("apc_runtime_core_report_gate", RUNTIME)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    cfg.write_text(json.dumps({"conversations": conversations, "log": str(log)}, ensure_ascii=False),
                   encoding="utf-8")
    egress = root / "egress_policy.json"
    egress.write_text(json.dumps(SCENARIO_EGRESS_POLICY), encoding="utf-8")
    env = dict(os.environ)
    env["APC_RUNTIME_STATE_ROOT"] = str(root / "state")
    env["APC_RUNTIME_BRIDGE_WRAPPER"] = _ready_wrapper(root)
    env["APC_RUNTIME_INJECT_BRIDGE_FAIL"] = "SCRIPT"
    env["APC_RUNTIME_INJECT_SCRIPT_FILE"] = str(cfg)
    env["APC_SCENARIO_EGRESS_POLICY"] = str(egress)
    return env


def _declare_scenario_world(env, run_id):
    """Declare TCB verified + one authorization for the report destination
    through the product's own API (scenario construction only; identical to
    test_send_guard_offline._declare_scenario_world)."""
    import effect_safety_lite as es
    saved = {key: os.environ.get(key) for key in env if key.startswith("APC_RUNTIME_")}
    os.environ.update({key: value for key, value in env.items() if key.startswith("APC_RUNTIME_")})
    try:
        rt = _load_rt()
        state = rt.load_state(run_id)
        state["effect_tcb_verified"] = True
        destination = str(state.get("r_url") or "")
        scope = {
            "provider": "chatgpt-web", "resource": destination, "purpose": "review transport",
            "identity": "runtime-v1", "destination": destination,
            "data_classes": ["PUBLIC", "INTERNAL"],
        }
        return es.grant_authorization(
            rt, state, issuer_role="HUMAN_AUTHORITY", issuer_identity="scenario-authority",
            holder="runtime-v1", scope=scope, max_effect_count=4)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _run_json(argv, env):
    proc = subprocess.run([sys.executable, str(ADAPTER), *argv], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=180)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {"_raw": proc.stdout}
    return proc.returncode, out, proc.stdout + proc.stderr


def _start_run(root, env):
    code, out, raw = _run_json(["start", "--goal", "Build X", "--r-url", R1,
                                "--acceptance", "A",
                                "--egress-policy-file", env["APC_SCENARIO_EGRESS_POLICY"]], env)
    assert code == 0, raw[-800:]
    return out["run_id"]


def _state(env, run_id):
    return json.loads((Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / run_id / "state.json").read_text())


def _report_file(root, text="Work done per goal.") -> Path:
    p = root / f"report_{uuid_hex()}.txt"
    p.write_text(text, encoding="utf-8")
    return p


def uuid_hex():
    return importlib.import_module("uuid").uuid4().hex[:10]


@unittest.skipUnless(RUNTIME.exists() and ADAPTER.exists(), "runtime modules unavailable")
class ReportGateTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_r1_report_denied_without_effect_authorization(self):
        """The Effect Gate must bite on the production report path (fail-closed).

        2026-09-01 hardening merge adaptation: master's goal_contract_lite
        contract_new_run grants the per-run INTERNAL review-transport
        authorization at start (T11b triple, 2f1188a). To preserve R1's
        no-authorization intent, revoke that auto-grant before the report so
        the gate has nothing to authorize against (fail-closed unchanged).
        """
        env = _script_env(self.root, {R1: {"sid": "rsid", "replies": ["===REVIEW_VERDICT=== PASS"]}})
        rid = _start_run(self.root, env)
        # Revoke the start-time INTERNAL review-transport authorization so the
        # report path is genuinely without any effect authorization.
        sp = Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / rid / "state.json"
        st = json.loads(sp.read_text(encoding="utf-8"))
        st["effect_authorizations"] = {}
        sp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        mf = _report_file(self.root)
        code, out, raw = _run_json(["report", "--run-id", rid, "--message-file", str(mf),
                                    "--timeout", "60"], env)
        self.assertNotEqual(code, 0, raw[-800:])
        # The gate's own emit is swallowed by cmd_report's single-JSON design
        # (redirect_stdout), but the denial is durably recorded in the state.
        state = _state(env, rid)
        self.assertEqual(state.get("status"), "HARD_BLOCKED", raw[-800:])
        self.assertIn("EFFECT_SAFETY", str(state.get("blocked_reason", "")))
        # No transport may have happened: the reviewer reply slot must be unconsumed.
        self.assertNotEqual(state.get("last_r_verdict"), "PASS")

    def test_r2_report_with_authorization_delivers_and_finalizes(self):
        """With a declared authorization the report rides the gates and finalizes."""
        env = _script_env(self.root, {R1: {"sid": "rsid", "replies": ["===REVIEW_VERDICT=== PASS"]}})
        rid = _start_run(self.root, env)
        _declare_scenario_world(env, rid)
        mf = _report_file(self.root)
        code, out, raw = _run_json(["report", "--run-id", rid, "--message-file", str(mf),
                                    "--timeout", "60"], env)
        self.assertEqual(code, 0, raw[-800:])
        self.assertEqual(out.get("status"), "OK", raw[-800:])
        self.assertEqual(out.get("run_status"), "DONE")
        self.assertEqual(out.get("last_r_verdict"), "PASS")
        state = _state(env, rid)
        # Effect safety record present: the gate actually evaluated the send.
        self.assertTrue(state.get("effect_authorizations"))
        self.assertEqual(state["effect_safety"]["authorization_status"], "GRANTED")

    def test_r3_report_blocked_under_ec_halt(self):
        """Non-RUNNING lifecycle (HALT verdict) blocks report before any transport."""
        env = _script_env(self.root, {R1: {"sid": "rsid", "replies": ["===REVIEW_VERDICT=== PASS"]}})
        rid = _start_run(self.root, env)
        # Scenario construction: freeze the lifecycle through the product state.
        sp = Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / rid / "state.json"
        st = json.loads(sp.read_text())
        st["status"] = "PAUSED"
        sp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        mf = _report_file(self.root)
        code, out, raw = _run_json(["report", "--run-id", rid, "--message-file", str(mf),
                                    "--timeout", "60"], env)
        self.assertNotEqual(code, 0, raw[-800:])
        # EC HALT is a recoverable degradation point by design: DENIED (not
        # hard_block), with an auditable journal record and NO transport.
        state = _state(env, rid)
        self.assertEqual(state.get("status"), "PAUSED")
        jp = Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / rid / "journal.jsonl"
        jtext = jp.read_text(encoding="utf-8", errors="replace")
        self.assertIn("EC_GATE_DENIAL", jtext)
        self.assertIn("HALT", jtext)
        self.assertNotEqual(state.get("last_r_verdict"), "PASS")

    def test_r4_run_cmd_routes_report_to_send_guard(self):
        """Regression anchor: run.cmd must route `report` to the gated target."""
        self.assertTrue(RUN_CMD.exists())
        text = RUN_CMD.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'(?im)^if /I "%~1"=="report" goto (\S+)', text)
        self.assertIsNotNone(m, "run.cmd report routing line missing")
        self.assertEqual(m.group(1), "send_guard",
                         "report must ride the three-gate chain (send_guard), not goal_contract")


if __name__ == "__main__":
    unittest.main()
