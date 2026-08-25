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
import unittest
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime.py"
EC = HERE / "ec_lite.py"
GC = HERE / "goal_contract_lite.py"
ADAPTER = HERE / "send_guard_lite.py"
R1 = "https://chatgpt.com/c/1e1ebbbb-1111-2222-3333-000000000002"

sys.path.insert(0, str(HERE))
import ec_lite as ecl  # noqa: E402
import runtime as rt   # noqa: E402


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
    env = dict(os.environ)
    env["APC_RUNTIME_STATE_ROOT"] = str(root / "state")
    env["APC_RUNTIME_BRIDGE_WRAPPER"] = _ready_wrapper(root)
    env["APC_RUNTIME_INJECT_BRIDGE_FAIL"] = "SCRIPT"
    env["APC_RUNTIME_INJECT_SCRIPT_FILE"] = str(cfg)
    return env


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
        code, out, raw = _run(GC, ["start", "--goal", "telemetry step test",
                                   "--r-url", "https://chatgpt.com/c/telem0001"], env)
        self.assertEqual(code, 0, raw)
        rid = out["run_id"]
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
        code, out, raw = _run(ADAPTER, ["start", "--goal", "Build X", "--r-url", R1,
                                        "--acceptance", "A"], env)
        self.assertEqual(code, 0, raw)
        rid = out["run_id"]
        code, out, raw = _run(ADAPTER, ["send", "--run-id", rid, "--message", "packet"], env)
        self.assertNotIn(code, (0, 5), raw[-800:])  # failed, and not a precondition DENIED
        st = self._state(env, rid)
        self.assertEqual(st["ec"]["consecutive_failures"], 1)
        self.assertIn('"ec_event": "failure"', self._journal(env, rid))
        self.assertIn('"source": "auto"', self._journal(env, rid))

    def test_t3_send_ok_records_action(self):
        env = _script_env(self.root, {R1: {"sid": "rsid-t", "replies": ["received, no verdict"]}})
        code, out, raw = _run(ADAPTER, ["start", "--goal", "Build X", "--r-url", R1,
                                        "--acceptance", "A"], env)
        self.assertEqual(code, 0, raw)
        rid = out["run_id"]
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
