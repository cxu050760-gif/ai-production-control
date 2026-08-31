#!/usr/bin/env python3
"""GATE-1#5 (hardening 2026-08-31): offline tests for the effect-reconcile exit.

Before this hardening, reconcile_effect() had no caller anywhere: a single
transient transport failure marked the logical effect OUTCOME_UNKNOWN and
hard-blocked the RUN, while the dedupe layer refused ordinary retries of the
same payload — a permanent self-lock with no exit. run.cmd now exposes
`effect-reconcile` (routed to effect_safety_lite.cmd_effect_reconcile), with
frozen fail-closed semantics:

  X1  OUTCOME_UNKNOWN + --succeeded + evidence -> SUCCESS, RUN resumed RUNNING
      (HARD_BLOCKED lifted, auditable), journal records reconciliation+resume
  X2  OUTCOME_UNKNOWN + --not-occurred -> RECONCILED_NOT_OCCURRED, RUN stays
      HARD_BLOCKED (replay needs a new explicit authority decision)
  X3  reconciliation on a non-OUTCOME_UNKNOWN record is DENIED
  X4  missing/empty evidence file is DENIED
  X5  run.cmd routes `effect-reconcile` to effect_safety (regression anchor)

All offline: tmp state root via APC_RUNTIME_STATE_ROOT; no real inbox, no
network, no bridge. The state fixture is built with plain dicts mirroring the
production schema (effect_safety record + HARD_BLOCKED run) — the same shape
gated_cmd_send/mark_outcome_unknown/hard_block write.
"""
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
MODULE = HERE / "effect_safety_lite.py"
RUN_CMD = HERE / "run.cmd"

import importlib.util


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_env(root):
    env = dict(os.environ)
    env["APC_RUNTIME_STATE_ROOT"] = str(root / "state")
    os.makedirs(env["APC_RUNTIME_STATE_ROOT"], exist_ok=True)
    return env


def _make_run(root, env, *, run_status="HARD_BLOCKED", effect_status="OUTCOME_UNKNOWN"):
    # ORDER MATTERS: runtime.py computes RUNS_ROOT from APC_RUNTIME_STATE_ROOT
    # at import time. Set the env seam FIRST, then load the module — otherwise
    # the fixture writes into the default (real) state root. Learned the hard
    # way in this very test run (leaked RUN dirs were purged); see GATE-3.
    # v16 §4-A 修复：此处曾无条件 pop 该 env，把 discover 外层设置的隔离状态根
    # 一并摧毁（audit hook 实证：后续 admission 用例因此回落仓根真实 lease）。
    # 现改为保存/恢复外层值。
    _prev_root = os.environ.get("APC_RUNTIME_STATE_ROOT")
    os.environ["APC_RUNTIME_STATE_ROOT"] = env["APC_RUNTIME_STATE_ROOT"]
    try:
        rt = _load_module(HERE / "runtime.py", "apc_runtime_core_reconcile_fixture")
        state = rt._new_run("reconcile fixture goal", "https://chatgpt.com/c/11111111-2222-3333-4444-555555555555", "fixture-worker")
        run_id = state["run_id"]
        rec = {
            "schema": "EFFECT_SAFETY_V2",
            "logical_effect_id": "eff-test-0001",
            "operation": "send",
            "status": effect_status,
            "ordinary_retry_permitted": False,
            "outcome_unknown_at": "2026-08-31T00:00:00+00:00",
        }
        # The AUTHORITATIVE effect log is state["effect_safety_log"]; the
        # state["effect_safety"] key is only the current-record mirror.
        state["effect_safety_log"] = [rec]
        state["effect_safety"] = rec
        state["status"] = run_status
        if run_status == "HARD_BLOCKED":
            state["blocked_reason"] = "EFFECT_OUTCOME_UNKNOWN: transport lost"
            state["next_action"] = "HARD_BLOCKED: stop and report to user"
        rt.save_state(state)
        return run_id
    finally:
        if _prev_root is None:
            os.environ.pop("APC_RUNTIME_STATE_ROOT", None)
        else:
            os.environ["APC_RUNTIME_STATE_ROOT"] = _prev_root


def _evidence_file(root, payload=None):
    p = root / f"evidence_{abs(hash(str(payload))) % 99999}.json"
    p.write_text(json.dumps(payload if payload is not None
                            else {"checked_at": "2026-08-31T00:00:00Z",
                                  "observer": "operator",
                                  "how": "reviewer confirmed report received"}, ensure_ascii=False),
                 encoding="utf-8")
    return p


def _run_cli(module_path, argv, env):
    e = dict(env)
    proc = subprocess.run([sys.executable, str(module_path), *argv], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=e, timeout=120)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {"_raw": proc.stdout}
    return proc.returncode, out, proc.stdout + proc.stderr


def _read_state(env, run_id):
    return json.loads((Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / run_id / "state.json").read_text())


def _journal(env, run_id):
    jp = Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / run_id / "journal.jsonl"
    return jp.read_text(encoding="utf-8", errors="replace") if jp.exists() else ""


@unittest.skipUnless(MODULE.exists(), "effect_safety_lite.py unavailable")
class EffectReconcileTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.env = _make_env(self.root)

    def tearDown(self):
        self.td.cleanup()

    def test_x1_succeeded_commits_and_resumes(self):
        rid = _make_run(self.root, self.env)
        ev = _evidence_file(self.root)
        code, out, raw = _run_cli(MODULE, ["effect-reconcile", "--run-id", rid,
                                           "--succeeded", "--evidence-file", str(ev)], self.env)
        self.assertEqual(code, 0, raw[-800:])
        self.assertEqual(out.get("effect_status"), "SUCCESS", raw[-800:])
        state = _read_state(self.env, rid)
        self.assertEqual(state.get("status"), "RUNNING")
        self.assertEqual(state["effect_safety"]["status"], "SUCCESS")
        self.assertTrue(state["effect_safety"].get("reconciliation_evidence"))
        jtext = _journal(self.env, rid)
        self.assertIn("EFFECT_RECONCILED_SUCCESS", jtext)
        self.assertIn("EFFECT_RECONCILE_RESUME", jtext)

    def test_x2_not_occurred_keeps_blocked(self):
        rid = _make_run(self.root, self.env)
        ev = _evidence_file(self.root, {"checked": "bridge never sent; log empty"})
        code, out, raw = _run_cli(MODULE, ["effect-reconcile", "--run-id", rid,
                                           "--not-occurred", "--evidence-file", str(ev)], self.env)
        self.assertEqual(code, 0, raw[-800:])
        self.assertEqual(out.get("effect_status"), "RECONCILED_NOT_OCCURRED")
        state = _read_state(self.env, rid)
        self.assertEqual(state.get("status"), "HARD_BLOCKED")  # fail-closed: no auto-resume
        self.assertIn("EFFECT_RECONCILED_NOT_OCCURRED", _journal(self.env, rid))

    def test_x3_denied_on_non_unknown(self):
        rid = _make_run(self.root, self.env, run_status="RUNNING", effect_status="SUCCESS")
        ev = _evidence_file(self.root)
        code, out, raw = _run_cli(MODULE, ["effect-reconcile", "--run-id", rid,
                                           "--succeeded", "--evidence-file", str(ev)], self.env)
        self.assertNotEqual(code, 0)
        self.assertEqual(out.get("status"), "DENIED", raw[-400:])

    def test_x4_missing_evidence_denied(self):
        rid = _make_run(self.root, self.env)
        missing = self.root / "nope.json"
        code, out, raw = _run_cli(MODULE, ["effect-reconcile", "--run-id", rid,
                                           "--succeeded", "--evidence-file", str(missing)], self.env)
        self.assertNotEqual(code, 0)
        self.assertEqual(out.get("status"), "DENIED", raw[-400:])

    def test_x5_run_cmd_routes_effect_reconcile(self):
        text = RUN_CMD.read_text(encoding="utf-8", errors="replace")
        self.assertIn('if /I "%~1"=="effect-reconcile" goto effect_safety', text)
        self.assertNotIn('"effect-gate" goto', text)


if __name__ == "__main__":
    unittest.main()
