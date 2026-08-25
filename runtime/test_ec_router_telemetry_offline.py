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

    def test_r6_unicode_cursor_boundary_preserves_counting(self):
        # Verify binary cursor boundary works with multi-byte UTF-8 (Chinese)
        # in journal. Chinese text injected into journal, then fresh PASS
        # must create artifact_count=1.
        convs = {B1: {"sid": "bsid", "replies": ["bad output"]},
                 R1: {"sid": "rsid", "replies": ["===REVIEW_VERDICT=== REWORK"]}}
        env = _script_env(self.root, convs)
        code, out, raw = _run(ADAPTER, ["router-start", "--goal-file", str(self.goal),
                                        "--b-url", B1, "--r-url", R1,
                                        "--acceptance", "A"], env)
        self.assertEqual(code, 0, raw[-800:])
        rid = out["run_id"]
        # Inject Chinese (multi-byte UTF-8) text directly into journal
        jp = Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / rid / "journal.jsonl"
        with open(jp, "a", encoding="utf-8") as f:
            f.write('{"ts":"2026-08-25T09:00:00+00:00","event":"NOTE","message":"修复中文路径和编码问题"}\n')
        jl_pre = self._journal(env, rid)
        self.assertIn("修复中文路径", jl_pre)
        st1 = self._state(env, rid)
        # After REWORK, ec counter may not exist yet
        art1 = st1.get("ec", {}).get("artifact_count", 0)
        # Now continue and get a fresh PASS - must correctly count artifact
        convs2 = {B1: {"sid": "bsid", "replies": [f"candidate v2\nGOAL_CONTRACT_HASH={self.h}"]},
                  R1: {"sid": "rsid", "replies": ["===REVIEW_VERDICT=== PASS"]}}
        env2 = _script_env(self.root, convs2)
        code2, out2, raw2 = _run(ADAPTER, ["router-continue", "--run-id", rid,
                                           "--timeout", "30"], env2)
        self.assertEqual(code2, 0, raw2[-800:])
        st2 = self._state(env2, rid)
        # Artifact count must be 1 (first artifact from PASS)
        self.assertEqual(st2["ec"]["artifact_count"], art1 + 1)
        # Verify the journal still contains the Chinese text (cursor boundary
        # should have correctly handled the multi-byte UTF-8)
        jl_post = self._journal(env2, rid)
        self.assertIn("修复中文路径", jl_post)

    def test_r7_current_gate_denial_not_counted(self):
        # Current-command EC_GATE_DENIAL must keep consecutive_failures=3
        # and must not add source=auto failure.
        convs = {B1: {"sid": "bsid", "replies": [f"candidate v1\nGOAL_CONTRACT_HASH={self.h}"]},
                 R1: {"sid": "rsid", "replies": ["===REVIEW_VERDICT=== PASS"]}}
        env = _script_env(self.root, convs)
        code, out, raw = _run(ADAPTER, ["router-start", "--goal-file", str(self.goal),
                                        "--b-url", B1, "--r-url", R1,
                                        "--acceptance", "A"], env)
        self.assertEqual(code, 0, raw[-800:])
        rid = out["run_id"]
        # Inject 3 manual failures to set consecutive_failures=3
        for _ in range(3):
            _run(EC, ["ec-record", "--run-id", rid, "--event", "failure"], env)
        st1 = self._state(env, rid)
        self.assertEqual(st1["ec"]["consecutive_failures"], 3)
        # Now run router-continue which should trigger EC_GATE_DENIAL
        # (consecutive failures >= 3 blocks transport)
        convs2 = {B1: {"sid": "bsid", "replies": [f"candidate v2\nGOAL_CONTRACT_HASH={self.h}"]},
                  R1: {"sid": "rsid", "replies": ["===REVIEW_VERDICT=== PASS"]}}
        env2 = _script_env(self.root, convs2)
        code2, out2, raw2 = _run(ADAPTER, ["router-continue", "--run-id", rid,
                                           "--timeout", "30"], env2)
        self.assertNotEqual(code2, 0, raw2[-800:])
        st2 = self._state(env2, rid)
        # consecutive_failures must still be 3 (gate denial not counted)
        self.assertEqual(st2["ec"]["consecutive_failures"], 3)
        # No new source=auto failure should be in journal
        jl2 = self._journal(env2, rid)
        self.assertIn("EC_GATE_DENIAL", jl2)
        # Count auto-source failures - should not have a new one
        import json as _json
        auto_failure_count = 0
        for line in jl2.strip().splitlines():
            try:
                entry = _json.loads(line)
                if entry.get("event") == "failure" and entry.get("source") == "auto":
                    auto_failure_count += 1
            except _json.JSONDecodeError:
                pass
        self.assertEqual(auto_failure_count, 0, f"Unexpected auto failure count: {auto_failure_count}")

    def test_r8_next_action_token_does_not_mask_send_failure(self):
        # Adversarial regression (verdict_r22_v5): within ONE router command
        # the reviewer first returns REWORK whose NEXT_ACTION merely CONTAINS
        # the text EC_GATE_DENIAL as ordinary data; shortly after, the
        # transport reports a genuine non-gate SEND_FAILED and the command
        # hard-blocks. The token-as-data must NOT suppress the real failure:
        # exactly one source=auto failure is recorded and consecutive_failures
        # increases by exactly one. The old raw-substring scan read the
        # journal line and was fooled by the NEXT_ACTION token into masking
        # the SEND_FAILED.
        next_action = ("Inspect the backtrace; remove the spurious "
                       "EC_GATE_DENIAL token from the filter and re-test.")
        rework_reply = ("===REVIEW_VERDICT=== REWORK\n"
                        f"===NEXT_ACTION=== {next_action}")
        convs = {B1: {"sid": "bsid",
                      # Round 1: goal dispatch succeeds (candidate carries
                      # the frozen contract hash). Round 2 rework delivery
                      # fails deterministically AFTER the REWORK was received.
                      "replies": [f"candidate v1\nGOAL_CONTRACT_HASH={self.h}"],
                      "fail_after": 1, "fail_token": "SEND_FAILED"},
                 R1: {"sid": "rsid", "replies": [rework_reply]}}
        env = _script_env(self.root, convs)
        code, out, raw = _run(ADAPTER, ["router-start", "--goal-file", str(self.goal),
                                        "--b-url", B1, "--r-url", R1,
                                        "--acceptance", "A"], env)
        self.assertEqual(code, 0, raw[-800:])
        rid = out["run_id"]
        base_failures = self._state(env, rid).get("ec", {}).get("consecutive_failures", 0)
        # One drive command: REWORK with the token-as-data arrives first, then
        # the non-gate SEND_FAILED hard-blocks the command.
        code2, out2, raw2 = _run(ADAPTER, ["router-continue", "--run-id", rid,
                                           "--timeout", "30"], env)
        self.assertNotEqual(code2, 0, raw2[-800:])
        st2 = self._state(env, rid)
        self.assertEqual(st2["status"], "HARD_BLOCKED", str(st2.get("blocked_reason", ""))[:300])
        # The real non-gate failure is counted exactly once.
        self.assertEqual(st2["ec"]["consecutive_failures"], base_failures + 1,
                         f"expected {base_failures+1} consecutive failures, got "
                         f"{st2['ec']['consecutive_failures']}")
        entries = [json.loads(line) for line in self._journal(env, rid).strip().splitlines()
                   if line.strip()]
        auto_failures = [e for e in entries
                         if e.get("event") == "EC_EVENT" and e.get("source") == "auto"
                         and e.get("ec_event") == "failure"]
        self.assertEqual(len(auto_failures), 1,
                         f"expected exactly one source=auto failure, got {len(auto_failures)}")
        # The transport genuinely reported a non-gate SEND_FAILED AFTER the
        # REWORK was received (session replacement journaled with that reason).
        send_failed = [e for e in entries
                       if e.get("event") == "ROUTER_SESSION_REPLACED"
                       and "SEND_FAILED" in str(e.get("reason", ""))]
        self.assertTrue(send_failed, "no SEND_FAILED transport failure journaled")
        rework_entry = next((e for e in entries if e.get("event") == "ROUTER_REWORK"), None)
        self.assertIsNotNone(rework_entry, "no ROUTER_REWORK entry journaled")
        self.assertLess(entries.index(rework_entry), entries.index(send_failed[0]),
                        "SEND_FAILED must occur AFTER the REWORK was received")
        # The token appears ONLY as data inside the NEXT_ACTION; the real gate
        # never fired, so no EC_GATE_DENIAL event may exist.
        self.assertIn("EC_GATE_DENIAL", str(rework_entry.get("next_action", "")),
                      "NEXT_ACTION token missing from ROUTER_REWORK entry")
        self.assertEqual([e for e in entries if e.get("event") == "EC_GATE_DENIAL"], [],
                         "an EC_GATE_DENIAL event was journaled although the gate never fired")
        self.assertIn("EC_GATE_DENIAL", self._journal(env, rid))

    def test_r9_real_gate_denial_still_no_count(self):
        # Verify that a REAL EC_GATE_DENIAL (event=EC_GATE_DENIAL, action=router)
        # still preserves the no-count guard. This ensures the new JSON field
        # matching correctly identifies real gate denials while ignoring
        # spurious text matches.
        convs = {B1: {"sid": "bsid", "replies": [f"candidate v1\nGOAL_CONTRACT_HASH={self.h}"]},
                 R1: {"sid": "rsid", "replies": ["===REVIEW_VERDICT=== PASS"]}}
        env = _script_env(self.root, convs)
        code, out, raw = _run(ADAPTER, ["router-start", "--goal-file", str(self.goal),
                                        "--b-url", B1, "--r-url", R1,
                                        "--acceptance", "A"], env)
        self.assertEqual(code, 0, raw[-800:])
        rid = out["run_id"]
        # Inject 3 manual failures to trigger EC gate on next command
        for _ in range(3):
            _run(EC, ["ec-record", "--run-id", rid, "--event", "failure"], env)
        st1 = self._state(env, rid)
        self.assertEqual(st1["ec"]["consecutive_failures"], 3)
        # Also inject a spurious NOTE with "EC_GATE_DENIAL" text to verify
        # it doesn't interfere with the real gate detection
        jp = Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / rid / "journal.jsonl"
        with open(jp, "a", encoding="utf-8") as f:
            f.write('{"ts":"2026-08-25T09:00:00+00:00","event":"NOTE","action":"router","message":"Check EC_GATE_DENIAL status"}\n')
        # Run router-continue with a fresh PASS - this should hit a REAL
        # EC_GATE_DENIAL because consecutive_failures >= 3
        convs2 = {B1: {"sid": "bsid", "replies": [f"candidate v2\nGOAL_CONTRACT_HASH={self.h}"]},
                  R1: {"sid": "rsid", "replies": ["===REVIEW_VERDICT=== PASS"]}}
        env2 = _script_env(self.root, convs2)
        code2, out2, raw2 = _run(ADAPTER, ["router-continue", "--run-id", rid,
                                           "--timeout", "30"], env2)
        self.assertNotEqual(code2, 0, raw2[-800:])
        st2 = self._state(env2, rid)
        # consecutive_failures must still be 3 (real gate denial not counted)
        self.assertEqual(st2["ec"]["consecutive_failures"], 3)
        # No new source=auto failure (the real gate denial was not counted)
        import json as _json
        auto_failure_count = 0
        for line in self._journal(env2, rid).strip().splitlines():
            try:
                entry = _json.loads(line)
                if entry.get("event") == "EC_EVENT" and entry.get("source") == "auto":
                    auto_failure_count += 1
            except _json.JSONDecodeError:
                pass
        self.assertEqual(auto_failure_count, 0,
                         f"Real EC_GATE_DENIAL should not be counted but found {auto_failure_count} auto EC_EVENT entries")
        # The real EC_GATE_DENIAL entry should exist in journal
        jl2 = self._journal(env2, rid)
        self.assertIn('"EC_GATE_DENIAL"', jl2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
