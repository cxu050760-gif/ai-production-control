#!/usr/bin/env python3
import importlib.util
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
RUNTIME = HERE / "runtime.py"
ADAPTER = HERE / "send_guard_lite.py"
R1 = "https://chatgpt.com/c/1e1ebbbb-1111-2222-3333-000000000002"

# AD-8 scenario policy: permits only the classifications the send path carries.
# Deliberately not a blanket grant -- SECRET must still be denied.
SCENARIO_EGRESS_POLICY = {"default": ["PUBLIC", "INTERNAL"]}


def _load_rt():
    spec = importlib.util.spec_from_file_location("apc_runtime_core", RUNTIME)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _declare_scenario_world(env, run_id, *, purpose="review transport",
                            destination=None, resource=None):
    """AD-8: declare a healthy sealed world for this run (scenario construction only).

    Gate 1 (egress) rides on the contract via --egress-policy-file; gate 2 (TCB) is
    declared through the state key ``effect_tcb_verified`` (never ``tcb_status``) and
    gate 3 (authority) through the product's own ``grant_authorization`` API, with an
    issuer role from AUTHORIZED_ISSUER_ROLES and an issuer identity distinct from the
    holder so the anti-self-grant rule stays enforced. Router flows that send to
    several role destinations inside ONE process use the explicit ``*`` wildcard the
    authority matrix supports for provider/resource/destination; the purpose stays
    exact-bound and SECRET is absent from data_classes. Exactly one authorization is
    granted (the freshest generation is the live one by design). No expectation and
    no assertion is altered by this helper.
    """
    import effect_safety_lite as es

    saved = {key: os.environ.get(key) for key in env
             if key.startswith("APC_RUNTIME_")}
    os.environ.update({key: value for key, value in env.items() if key.startswith("APC_RUNTIME_")})
    try:
        rt = _load_rt()
        state = rt.load_state(run_id)
        state["effect_tcb_verified"] = True
        if destination is None:
            destination = str(state.get("r_url") or "")
        if resource is None:
            resource = destination
        scope = {
            "provider": "chatgpt-web", "resource": resource, "purpose": purpose,
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
    egress = root / "egress_policy.json"
    egress.write_text(json.dumps(SCENARIO_EGRESS_POLICY), encoding="utf-8")
    env = dict(os.environ)
    env["APC_RUNTIME_STATE_ROOT"] = str(root / "state")
    env["APC_RUNTIME_BRIDGE_WRAPPER"] = _ready_wrapper(root)
    env["APC_RUNTIME_INJECT_BRIDGE_FAIL"] = "SCRIPT"
    env["APC_RUNTIME_INJECT_SCRIPT_FILE"] = str(cfg)
    env["APC_SCENARIO_EGRESS_POLICY"] = str(egress)
    return env


def _egress_arg(env):
    """AD-8: the contract-carried egress policy option for start-like commands."""
    return ["--egress-policy-file", env["APC_SCENARIO_EGRESS_POLICY"]]


# AD-8 scenario adapter for single-process router commands (router-run): the run
# is created and driven inside ONE process, so the scenario world cannot be
# declared "after start" from the test process. This fixture installs the exact
# production gate chain (goal_contract -> effect_safety -> ec gate, identical to
# send_guard_lite) and declares gates 2+3 per outbound router effect through the
# product's own API before the gated chain evaluates the effect. Gate 1 rides on
# the contract via --egress-policy-file. No gate logic, product default,
# expectation or assertion is altered.
SCENARIO_ROUTER_ADAPTER = '''#!/usr/bin/env python3
"""AD-8 scenario adapter for single-process router commands (test fixture only).

Installs the production gate chain exactly as send_guard_lite does, then, per
outbound router effect, declares the scenario world through the product's own
API: gate 2 (TCB) via the state declaration effect_tcb_verified=True, gate 3
(authority) via effect_safety_lite.grant_authorization with an issuer role from
AUTHORIZED_ISSUER_ROLES and an issuer identity distinct from the holder. Gate 1
(egress) rides on the contract via --egress-policy-file.
"""
import sys
from pathlib import Path

RUNTIME_DIR = Path("__RUNTIME_DIR__")
sys.path.insert(0, str(RUNTIME_DIR))

import goal_contract_lite as gc
import effect_safety_lite as es
import ec_lite as ec


def main() -> int:
    argv = list(sys.argv[1:])
    rt = gc._load_runtime()
    cleaned, options = gc._extract_contract_options(argv)
    gc.install(rt, options)
    es.install(rt, {})
    ec.install(rt)

    gated_router_send = rt._router_send_to_role

    def scenario_router_send(state, role, message, timeout):
        destination = str((state.get("role_urls") or {}).get(role)
                          or state.get("r_url") or "")
        holder = "runtime-v1"
        state["effect_tcb_verified"] = True
        es.grant_authorization(
            rt, state,
            issuer_role="HUMAN_AUTHORITY",          # in AUTHORIZED_ISSUER_ROLES
            issuer_identity="scenario-authority",   # distinct from holder
            holder=holder,
            scope={"provider": "chatgpt-web", "resource": destination,
                   "purpose": "router transport", "identity": holder,
                   "destination": destination,
                   "data_classes": ["PUBLIC", "INTERNAL"]},
            max_effect_count=2)
        return gated_router_send(state, role, message, timeout)

    rt._router_send_to_role = scenario_router_send
    sys.argv = [str(RUNTIME_DIR / "runtime.py"), *cleaned]
    return rt.main()


if __name__ == "__main__":
    sys.exit(main())
'''


def _scenario_router_adapter(root):
    """Write the AD-8 scenario router adapter fixture and return its path."""
    path = root / "scenario_router_adapter.py"
    # forward slashes keep the generated literal free of backslash escapes
    runtime_dir = str(HERE).replace("\\", "/")
    path.write_text(SCENARIO_ROUTER_ADAPTER.replace("__RUNTIME_DIR__", runtime_dir),
                    encoding="utf-8")
    return path


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
                                             "--acceptance", "A", *_egress_arg(env)], env)
        self.assertEqual(code, 0, raw)
        rid = out["run_id"]
        _declare_scenario_world(env, rid)
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
        adapter = _scenario_router_adapter(self.root)
        code, out, raw = _run_json(adapter, [
            "router-run", "--goal-file", str(goal),
            "--b-url", "https://chatgpt.com/c/b0b0aaaa-1111-2222-3333-000000000001",
            "--r-url", R1, "--acceptance", "A", "--max-rounds", "1", "--timeout", "30",
            *_egress_arg(env)], env)
        self.assertEqual(code, 0, raw[-800:])
        state = json.loads((Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / out["run_id"] / "state.json").read_text())
        self.assertTrue(state.get("goal_contract_hash"))
        ops = [r.get("operation") for r in state.get("effect_safety_log", [])]
        self.assertIn("router-send", ops)
        self.assertEqual(state["effect_safety"]["authorization_status"], "GRANTED")

    def test_j4_router_continue_preserves_contract_and_effect_across_processes(self):
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
            "router-start", "--goal-file", str(goal),
            "--b-url", "https://chatgpt.com/c/b0b0aaaa-1111-2222-3333-000000000001",
            "--r-url", R1, "--acceptance", "A", *_egress_arg(env)], env)
        self.assertEqual(code, 0, raw)
        rid = out["run_id"]
        # router-continue sends to BOTH role destinations inside one process;
        # the scenario authorization therefore uses the explicit * wildcard for
        # provider/resource/destination with the purpose still exact-bound.
        _declare_scenario_world(env, rid, purpose="router transport",
                                destination="*", resource="*")
        code, out, raw = _run_json(ADAPTER, ["router-continue", "--run-id", rid, "--timeout", "30"], env)
        self.assertEqual(code, 0, raw[-800:])
        state = json.loads((Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / rid / "state.json").read_text())
        self.assertEqual(state["goal_contract_hash"], h)
        self.assertEqual(state["status"], "DONE")
        self.assertTrue(state.get("effect_authorizations"))
        self.assertIn("router-send", [r.get("operation") for r in state.get("effect_safety_log", [])])



    def test_j5_reviewer_ready_handshake_unit(self):
        """2026-09-02: readiness predicate + handshake text contract.
        (Handshake transport itself is covered by the SCRIPT-seam send tests;
        this locks the pure-logic contract: not-ready -> handshake text ->
        ready, and implicit readiness after a real verdict.)"""
        import runtime as rt_mod

        state = {
            "run_id": "RUN-20260902-000000-xxxx", "review_epoch": 1,
            "goal": "Build X", "r_url": R1,
            "reviewer_ready": {"epoch": 1, "ready": False, "handshake_sent": False},
            "last_r_verdict": None, "metrics": {"bridge_retries": 0},
        }
        self.assertFalse(rt_mod.reviewer_ready_satisfied(state))
        state["last_r_verdict"] = "PASS"
        self.assertTrue(rt_mod.reviewer_ready_satisfied(state))
        state["last_r_verdict"] = None
        text = rt_mod.reviewer_handshake_text("Build X")
        self.assertIn("审查者初始化", text)
        self.assertIn(rt_mod.REVIEWER_READY_CONFIRM, text)
        self.assertIn("不是待审提交", text)
        state["reviewer_ready"] = {"epoch": 1, "ready": True, "handshake_sent": True}
        self.assertTrue(rt_mod.reviewer_ready_satisfied(state))



    def test_j6_reviewer_not_ready_never_locks_effect_wal(self):
        """2026-09-02 (dual-review): a reviewer handshake failure must NEVER
        fall into OUTCOME_UNKNOWN — the readiness gate runs before the effect
        WAL, so retries stay retryable. Handcrafted env WITHOUT the INJECT
        seam (so the readiness gate truly short-circuits to NOT_READY without
        touching transport): pre-mark handshake_sent=True, verify:
        (1) send -> REVIEWER_NOT_READY (EXIT_ERR) and effect_safety has NO
        OUTCOME_UNKNOWN record; (2) USER_OVERRIDE resets reviewer_ready."""
        goal = self.root / "goal.txt"; goal.write_text("Build X", encoding="utf-8")
        # Handcrafted environment: ready bridge wrapper, NO injected transport
        egress = self.root / "egress_j6.json"
        egress.write_text(json.dumps(SCENARIO_EGRESS_POLICY), encoding="utf-8")
        env = dict(os.environ)
        env["APC_RUNTIME_STATE_ROOT"] = str(self.root / "state")
        env["APC_RUNTIME_BRIDGE_WRAPPER"] = _ready_wrapper(self.root)
        env["APC_SCENARIO_EGRESS_POLICY"] = str(egress)
        code, out, raw = _run_json(ADAPTER, ["start", "--goal", "Build X", "--r-url", R1,
                                             "--acceptance", "A", "--egress-policy-file", str(egress)], env)
        self.assertEqual(code, 0, raw)
        rid = out["run_id"]
        # Pre-mark handshake_sent so the readiness gate short-circuits to NOT_READY
        state_path = Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / rid / "state.json"
        st = json.loads(state_path.read_text(encoding="utf-8"))
        st["reviewer_ready"] = {"epoch": 1, "ready": False, "handshake_sent": True}
        state_path.write_text(json.dumps(st), encoding="utf-8")
        _declare_scenario_world(env, rid)
        code, out, raw = _run_json(ADAPTER, ["send", "--run-id", rid, "--message", "review packet"], env)
        self.assertEqual(code, 1, raw[-800:])  # EXIT_ERR
        self.assertEqual(out.get("status"), "REVIEWER_NOT_READY", raw[-800:])
        st2 = json.loads(state_path.read_text(encoding="utf-8"))
        es_status = (st2.get("effect_safety") or {}).get("status")
        self.assertNotEqual(es_status, "OUTCOME_UNKNOWN", "handshake failure must not lock effect WAL")
        # USER_OVERRIDE resets the handshake flag so a real retry can re-handshake
        code, out, raw = _run_json(ADAPTER, ["directive", "--run-id", rid, "USER_OVERRIDE",
                                             "--note", "reviewer fixed"], env)
        self.assertEqual(code, 0, raw[-400:])
        st3 = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertFalse((st3.get("reviewer_ready") or {}).get("handshake_sent"),
                         "USER_OVERRIDE must reset the handshake flag")


if __name__ == "__main__":
    unittest.main(verbosity=2)
