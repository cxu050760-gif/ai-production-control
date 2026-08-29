#!/usr/bin/env python3
"""Offline tests for V0.6 Slice C: EC auto-telemetry.

Real runtime outcomes feed the durable EC counters without manual ec-record:
step OK -> action; send OK -> action, send failing for any reason other than
a precondition DENIED -> failure; recv OK -> artifact (R PASS) or failure
(R REWORK). Telemetry must be best-effort: it never changes exit codes and
never blocks the operation that produced the signal.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime.py"
EC = HERE / "ec_lite.py"
GC = HERE / "goal_contract_lite.py"
ADAPTER = HERE / "send_guard_lite.py"
R1 = "https://chatgpt.com/c/1e1ebbbb-1111-2222-3333-000000000002"

# AD-8 scenario policy: permits only the classifications the send path carries.
# Deliberately not a blanket grant -- SECRET must still be denied.
SCENARIO_EGRESS_POLICY = {"default": ["PUBLIC", "INTERNAL"]}

sys.path.insert(0, str(HERE))
import ec_lite as ecl  # noqa: E402
import runtime as rt   # noqa: E402


def _load_rt_fresh():
    import importlib.util
    spec = importlib.util.spec_from_file_location("apc_runtime_core_telem", RUNTIME)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _declare_scenario_world(env, run_id, *, purpose="review transport",
                            destination=None, resource=None):
    """AD-8: declare the scenario world for a run (scenario construction only).

    Gate 2 (TCB) is declared via the state key ``effect_tcb_verified`` (never
    ``tcb_status``) and gate 3 (authority) via the product's own
    ``grant_authorization`` API with an issuer role from AUTHORIZED_ISSUER_ROLES
    and an issuer identity distinct from the holder. Gate 1 (egress) rides on the
    contract via --egress-policy-file for adapter/gc paths; direct RUNTIME starts
    have no egress gate wired, so the declaration is the equivalent uniform
    scenario world. No expectation and no assertion is altered by this helper.
    """
    import effect_safety_lite as es

    saved = {key: os.environ.get(key) for key in env
             if key.startswith("APC_RUNTIME_")}
    os.environ.update({key: value for key, value in env.items() if key.startswith("APC_RUNTIME_")})
    try:
        rtf = _load_rt_fresh()
        state = rtf.load_state(run_id)
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
            rtf, state, issuer_role="HUMAN_AUTHORITY", issuer_identity="scenario-authority",
            holder="runtime-v1", scope=scope, max_effect_count=4)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _run(cmd, argv, env):
    proc = subprocess.run([sys.executable, str(cmd), *argv], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env, timeout=180)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {"_raw": proc.stdout}
    return proc.returncode, out, proc.stdout + proc.stderr


def _msys(p):
    s = str(p).replace("\\", "/")
    return "/" + s[0].lower() + s[2:] if len(s) > 1 and s[1] == ":" else s


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


class CounterSemanticsTests(unittest.TestCase):
    def test_u1_apply_ec_event_transitions(self):
        st = {"run_id": "RUN-20260825-120000-d001"}
        ec = ecl.apply_ec_event(st, "failure")
        self.assertEqual(ec["consecutive_failures"], 1)
        self.assertEqual(ec["actions_since_artifact"], 1)
        ec = ecl.apply_ec_event(st, "action")
        self.assertEqual(ec["consecutive_failures"], 1)
        self.assertEqual(ec["actions_since_artifact"], 2)
        self.assertEqual(ec["total_actions"], 1)
        ec = ecl.apply_ec_event(st, "artifact")
        self.assertEqual(ec["consecutive_failures"], 0)
        self.assertEqual(ec["actions_since_artifact"], 0)
        self.assertEqual(ec["artifact_count"], 1)

    def test_u2_cli_record_journals_source_cli(self):
        td = tempfile.TemporaryDirectory()
        try:
            root = Path(td.name)
            env = dict(os.environ)
            env["APC_RUNTIME_STATE_ROOT"] = str(root)
            code, out, raw = _run(RUNTIME, ["start", "--goal", "src test",
                                            "--r-url", "https://chatgpt.com/c/srctest001"], env)
            self.assertEqual(code, 0, raw)
            rid = out["run_id"]
            # AD-8 scenario world (TCB declaration + authority grant; the bare
            # RUNTIME path wires no egress gate, so gates 2+3 are the equivalent
            # uniform injection).
            _declare_scenario_world(env, rid)
            code, out, raw = _run(EC, ["ec-record", "--run-id", rid, "--event", "failure"], env)
            self.assertEqual(code, 0, raw)
            jl = (root / "runs" / rid / "journal.jsonl").read_text(encoding="utf-8")
            self.assertIn('"source": "cli"', jl)
        finally:
            td.cleanup()


class StepAndSendTelemetryTests(unittest.TestCase):
    """Real subprocess paths through the production adapters."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def _state(self, env, rid):
        return json.loads((Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / rid /
                           "state.json").read_text(encoding="utf-8"))

    def _journal(self, env, rid):
        return (Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / rid /
                "journal.jsonl").read_text(encoding="utf-8")

    def test_t1_step_ok_records_action(self):
        env = dict(os.environ)
        env["APC_RUNTIME_STATE_ROOT"] = str(self.root / "state")
        egress = self.root / "egress_policy_t1.json"
        egress.write_text(json.dumps(SCENARIO_EGRESS_POLICY), encoding="utf-8")
        env["APC_SCENARIO_EGRESS_POLICY"] = str(egress)
        code, out, raw = _run(GC, ["start", "--goal", "telemetry step test",
                                   "--r-url", "https://chatgpt.com/c/telem0001",
                                   *_egress_arg(env)], env)
        self.assertEqual(code, 0, raw)
        rid = out["run_id"]
        # AD-8 scenario world for this run (TCB declaration + authority grant;
        # uniform with the adapter-path scenario construction).
        _declare_scenario_world(env, rid)
        code, out, raw = _run(GC, ["step", "--run-id", rid, "--current", "doing",
                                   "--next", "next"], env)
        self.assertEqual(code, 0, raw)
        st = self._state(env, rid)
        self.assertEqual(st["ec"]["total_actions"], 1)
        self.assertEqual(st["ec"]["actions_since_artifact"], 1)
        jl = self._journal(env, rid)
        self.assertIn('"source": "auto"', jl)
        self.assertIn('"ec_event": "action"', jl)

    def test_t2_send_transport_failure_records_failure(self):
        # Deterministic bridge-failure seam: every bridge call fails at the
        # facade boundary (documented Batch3 T7 seam), so the send degrades
        # through the real transport-failure chain without touching a bridge.
        env = dict(os.environ)
        env["APC_RUNTIME_STATE_ROOT"] = str(self.root / "state")
        env["APC_RUNTIME_BRIDGE_WRAPPER"] = _ready_wrapper(self.root)
        env["APC_RUNTIME_INJECT_BRIDGE_FAIL"] = "1"
        egress = self.root / "egress_policy_t2.json"
        egress.write_text(json.dumps(SCENARIO_EGRESS_POLICY), encoding="utf-8")
        env["APC_SCENARIO_EGRESS_POLICY"] = str(egress)
        code, out, raw = _run(ADAPTER, ["start", "--goal", "Build X", "--r-url", R1,
                                        "--acceptance", "A", *_egress_arg(env)], env)
        self.assertEqual(code, 0, raw)
        rid = out["run_id"]
        # AD-8 scenario world (gate 2 state declaration + gate 3 authority
        # grant) so the send reaches the deterministic transport-failure seam.
        _declare_scenario_world(env, rid)
        code, out, raw = _run(ADAPTER, ["send", "--run-id", rid, "--message", "packet"], env)
        self.assertNotIn(code, (0, 5), raw[-800:])  # failed, and not a precondition DENIED
        st = self._state(env, rid)
        self.assertEqual(st["ec"]["consecutive_failures"], 1)
        self.assertIn('"ec_event": "failure"', self._journal(env, rid))
        self.assertIn('"source": "auto"', self._journal(env, rid))

    def test_t3_send_ok_records_action(self):
        env = _script_env(self.root, {R1: {"sid": "rsid-t", "replies": ["received, no verdict"]}})
        code, out, raw = _run(ADAPTER, ["start", "--goal", "Build X", "--r-url", R1,
                                        "--acceptance", "A", *_egress_arg(env)], env)
        self.assertEqual(code, 0, raw)
        rid = out["run_id"]
        # AD-8 scenario world (gates 2+3) so the gated send path can flow.
        _declare_scenario_world(env, rid)
        code, out, raw = _run(ADAPTER, ["send", "--run-id", rid, "--message", "packet"], env)
        self.assertEqual(code, 0, raw[-800:])
        st = self._state(env, rid)
        self.assertEqual(st["ec"]["total_actions"], 1)
        self.assertEqual(st["ec"]["consecutive_failures"], 0)
        self.assertIn('"ec_event": "action"', self._journal(env, rid))


class RecvTelemetryWrapperTests(unittest.TestCase):
    """In-process: wrap a stubbed cmd_recv and verify verdict-driven events."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self._backup = rt.RUNS_ROOT
        rt.RUNS_ROOT = self.root / "runs"
        self.rid = "RUN-20260825-120001-d002"
        (self.root / "runs" / self.rid).mkdir(parents=True, exist_ok=True)
        state = {"run_id": self.rid, "schema_version": 1, "revision": 1,
                 "status": "RUNNING", "goal": "g",
                 "r_url": "https://chatgpt.com/c/telem0002",
                 "metrics": {"rework_count": 0}}
        (self.root / "runs" / self.rid / "state.json").write_text(
            json.dumps(state), encoding="utf-8")

    def tearDown(self):
        rt.RUNS_ROOT = self._backup
        self.td.cleanup()

    def _install_with_stub(self, verdict):
        def stub_cmd_recv(args):
            st = rt.load_state(args.run_id)
            st["last_r_verdict"] = verdict
            rt.save_state(st)
            return rt.EXIT_OK
        rt.cmd_recv = stub_cmd_recv
        ecl.install_telemetry(rt)

    def _journal(self):
        return (self.root / "runs" / self.rid / "journal.jsonl").read_text(encoding="utf-8")

    def test_w1_recv_pass_records_artifact(self):
        self._install_with_stub("PASS")
        code = rt.cmd_recv(SimpleNamespace(run_id=self.rid))
        self.assertEqual(code, rt.EXIT_OK)
        st = rt.load_state(self.rid)
        self.assertEqual(st["ec"]["artifact_count"], 1)
        self.assertEqual(st["ec"]["consecutive_failures"], 0)
        jl = self._journal()
        self.assertIn('"ec_event": "artifact"', jl)
        self.assertIn('"source": "auto"', jl)

    def test_w2_recv_rework_records_failure(self):
        self._install_with_stub("REWORK")
        code = rt.cmd_recv(SimpleNamespace(run_id=self.rid))
        self.assertEqual(code, rt.EXIT_OK)
        st = rt.load_state(self.rid)
        self.assertEqual(st["ec"]["consecutive_failures"], 1)
        self.assertIn('"ec_event": "failure"', self._journal())

    def test_w3_telemetry_does_not_alter_exit_code(self):
        def stub_denied(args):
            return rt.EXIT_DENIED
        rt.cmd_recv = stub_denied
        ecl.install_telemetry(rt)
        code = rt.cmd_recv(SimpleNamespace(run_id=self.rid))
        self.assertEqual(code, rt.EXIT_DENIED)
        st = rt.load_state(self.rid)
        self.assertNotIn("ec", st)  # nothing recorded for non-OK outcomes


class RecordAutoLockSafetyTests(unittest.TestCase):
    """Deterministic concurrency per verdict_r21_v2: record_auto must never
    block and must never read or write canonical state unless it holds the
    RUN lock; it releases only the lock it acquired."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self._backup = rt.RUNS_ROOT
        rt.RUNS_ROOT = self.root / "runs"
        self.rid = "RUN-20260825-120002-d003"
        (self.root / "runs" / self.rid).mkdir(parents=True, exist_ok=True)
        state = {"run_id": self.rid, "schema_version": 1, "revision": 1,
                 "status": "RUNNING", "goal": "g",
                 "r_url": "https://chatgpt.com/c/telem0003",
                 "metrics": {"rework_count": 0}}
        (self.root / "runs" / self.rid / "state.json").write_text(
            json.dumps(state), encoding="utf-8")

    def tearDown(self):
        rt.RUNS_ROOT = self._backup
        self.td.cleanup()

    def _state_bytes(self):
        return (self.root / "runs" / self.rid / "state.json").read_bytes()

    def _lock_path(self):
        return self.root / "runs" / self.rid / ".lock"

    def test_l1_busy_lock_returns_fast_without_writes(self):
        # Adversarial: hold the RUN lock, then call record_auto. It must
        # return promptly (no 30s wait), leave state bytes untouched, keep the
        # original holder's lock intact, and journal nothing.
        before = self._state_bytes()
        holder = rt.RunLock(self.rid)
        holder.__enter__()
        try:
            t0 = time.monotonic()
            ecl.record_auto(rt, self.rid, "failure")
            elapsed = time.monotonic() - t0
            self.assertLess(elapsed, 2.0, "record_auto blocked while the lock was busy")
            self.assertEqual(self._state_bytes(), before,
                             "canonical state changed without holding the lock")
            self.assertTrue(self._lock_path().exists(),
                            "original holder lost its lock")
        finally:
            holder.__exit__(None, None, None)
        jp = self.root / "runs" / self.rid / "journal.jsonl"
        if jp.exists():
            self.assertNotIn("EC_EVENT", jp.read_text(encoding="utf-8"))

    def test_l2_free_lock_persists_and_releases(self):
        # No contention: the event is persisted exactly once and the lock that
        # record_auto acquired is released afterwards.
        ecl.record_auto(rt, self.rid, "failure")
        st = rt.load_state(self.rid)
        self.assertEqual(st["ec"]["consecutive_failures"], 1)
        jl = (self.root / "runs" / self.rid / "journal.jsonl").read_text(encoding="utf-8")
        self.assertIn('"ec_event": "failure"', jl)
        self.assertIn('"source": "auto"', jl)
        self.assertFalse(self._lock_path().exists(),
                         "record_auto left its own lock behind")

if __name__ == "__main__":
    unittest.main(verbosity=2)
