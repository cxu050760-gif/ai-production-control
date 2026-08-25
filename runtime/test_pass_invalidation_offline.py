#!/usr/bin/env python3
"""Offline tests for V0.5 Slice B: Material Change -> PASS Invalidation.

Definitions #30 (Stale Result Safety) / #43 (Review must bind Artifact):
binding a NEW candidate/evidence that differs from the artifact a stored PASS
was taken against must invalidate that PASS mechanically, and a RUN must not
be closable (done) on a stale or invalidated PASS.
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
sys.path.insert(0, str(HERE))
import runtime as rt

CAND = "ab11830" + "0" * 33
CAND2 = "ef11a5a" + "1" * 33
CAND3 = "dd33839" + "2" * 33
EVID = "HE-0123456789abcdef"
EVID2 = "HE-fedcba9876543210"


def _run(argv, env):
    proc = subprocess.run([sys.executable, str(RUNTIME), *argv], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env, timeout=120)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {"_raw": proc.stdout}
    return proc.returncode, out, proc.stdout + proc.stderr


def _pass_rr(rid: str) -> dict:
    return {"run_id": rid, "review_id": "REV-20260825-100101-b101",
            "candidate_commit": CAND, "evidence_id": EVID, "state_revision": 7,
            "verdict": "PASS", "next_action": "", "reply_path": "r.txt", "reply_bytes": 10,
            "returned_at": "2026-08-25T10:01:01Z"}


def _mk_state(rid: str, review_result=None, cand=None, ev=None) -> dict:
    st = {"run_id": rid, "schema_version": 1, "revision": 7, "status": "RUNNING",
          "goal": "g", "r_url": "https://chatgpt.com/c/x",
          "last_r_verdict": "PASS",
          "metrics": {"rework_count": 0, "started_at": "2026-08-25T10:00:00+00:00"},
          "candidate_commit": cand, "evidence_id": ev}
    if review_result is not None:
        st["review_result"] = review_result
    return st


def _write_state(root: Path, rid: str, state: dict) -> None:
    d = root / "runs" / rid
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2),
                                  encoding="utf-8")


class TriggerTests(unittest.TestCase):
    """In-process: _apply_review_bindings is the exact function recv uses."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self._backup = rt.RUNS_ROOT
        rt.RUNS_ROOT = self.root / "runs"

    def tearDown(self):
        rt.RUNS_ROOT = self._backup
        self.td.cleanup()

    def _state_with_pass(self, rid):
        (self.root / "runs" / rid).mkdir(parents=True, exist_ok=True)
        st = _mk_state(rid, _pass_rr(rid), cand=CAND, ev=EVID)
        return st

    def _journal(self, rid):
        p = self.root / "runs" / rid / "journal.jsonl"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def test_i1_new_candidate_invalidates(self):
        rid = "RUN-20260825-100001-b001"
        st = self._state_with_pass(rid)
        err = rt._apply_review_bindings(st, CAND2, None, None)
        self.assertIsNone(err)
        rr = st["review_result"]
        self.assertTrue(rr["invalidated"])
        self.assertEqual(rr["invalidation_reason"], "material change: candidate_commit")
        self.assertEqual(rr["superseded_binding"],
                         {"candidate_commit": CAND, "evidence_id": EVID})
        self.assertEqual(rr["candidate_commit"], CAND)  # PASS binding kept for audit
        self.assertIn("PASS_INVALIDATED", self._journal(rid))
        self.assertEqual(st["candidate_commit"], CAND2)

    def test_i2_same_binding_no_invalidation(self):
        rid = "RUN-20260825-100002-b002"
        st = self._state_with_pass(rid)
        err = rt._apply_review_bindings(st, CAND, EVID, None)
        self.assertIsNone(err)
        self.assertFalse(st["review_result"].get("invalidated"))
        self.assertNotIn("PASS_INVALIDATED", self._journal(rid))

    def test_i3_non_pass_verdict_untouched(self):
        rid = "RUN-20260825-100003-b003"
        (self.root / "runs" / rid).mkdir(parents=True, exist_ok=True)
        rr = _pass_rr(rid)
        rr["verdict"] = "REWORK"
        st = _mk_state(rid, rr, cand=CAND, ev=EVID)
        err = rt._apply_review_bindings(st, CAND2, None, None)
        self.assertIsNone(err)
        self.assertFalse(st["review_result"].get("invalidated"))
        self.assertNotIn("PASS_INVALIDATED", self._journal(rid))

    def test_i4_invalidation_is_idempotent(self):
        rid = "RUN-20260825-100004-b004"
        st = self._state_with_pass(rid)
        self.assertIsNone(rt._apply_review_bindings(st, CAND2, None, None))
        self.assertIsNone(rt._apply_review_bindings(st, CAND3, None, None))
        rr = st["review_result"]
        self.assertTrue(rr["invalidated"])
        self.assertEqual(rr["invalidation_reason"], "material change: candidate_commit")
        self.assertEqual(self._journal(rid).count("PASS_INVALIDATED"), 1)

    def test_i5_evidence_change_only(self):
        rid = "RUN-20260825-100005-b005"
        st = self._state_with_pass(rid)
        self.assertIsNone(rt._apply_review_bindings(st, None, EVID2, None))
        rr = st["review_result"]
        self.assertTrue(rr["invalidated"])
        self.assertEqual(rr["invalidation_reason"], "material change: evidence_id")

    def test_i6_empty_binding_leaves_pass_alone(self):
        rid = "RUN-20260825-100006-b006"
        st = self._state_with_pass(rid)
        self.assertIsNone(rt._apply_review_bindings(st, None, None, None))
        self.assertFalse(st["review_result"].get("invalidated"))


class GateTests(unittest.TestCase):
    """Subprocess: review-valid + done gates against crafted durable states."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.env = dict(os.environ)
        self.env["APC_RUNTIME_STATE_ROOT"] = str(self.root)

    def tearDown(self):
        self.td.cleanup()

    def test_g1_review_valid_reports_invalidated(self):
        rid = "RUN-20260825-100007-b007"
        rr = _pass_rr(rid)
        rr["invalidated"] = True
        rr["invalidation_reason"] = "material change: candidate_commit"
        rr["invalidated_at"] = "2026-08-25T10:05:00+00:00"
        _write_state(self.root, rid, _mk_state(rid, rr, cand=CAND2, ev=EVID))
        code, out, raw = _run(["review-valid", "--run-id", rid], self.env)
        self.assertEqual(code, 0, raw)
        self.assertFalse(out["valid"])
        self.assertEqual(out["reason"], "stored PASS was invalidated by material change")
        self.assertEqual(out["invalidation_reason"], "material change: candidate_commit")

    def test_g2_done_denied_when_invalidated(self):
        rid = "RUN-20260825-100008-b008"
        rr = _pass_rr(rid)
        rr["invalidated"] = True
        rr["invalidation_reason"] = "material change: candidate_commit"
        _write_state(self.root, rid, _mk_state(rid, rr, cand=CAND2, ev=EVID))
        code, out, raw = _run(["done", "--run-id", rid], self.env)
        self.assertEqual(code, 5, raw)
        self.assertEqual(out["status"], "DENIED")
        self.assertIn("re-review required", out["reason"])

    def test_g3_done_ok_when_binding_matches(self):
        rid = "RUN-20260825-100009-b009"
        _write_state(self.root, rid, _mk_state(rid, _pass_rr(rid), cand=CAND, ev=EVID))
        code, out, raw = _run(["done", "--run-id", rid], self.env)
        self.assertEqual(code, 0, raw)
        self.assertEqual(out["run_status"], "DONE")

    def test_g4_done_denied_on_binding_mismatch(self):
        # The durable binding no longer matches the stored PASS: fail-closed.
        rid = "RUN-20260825-100010-b010"
        _write_state(self.root, rid, _mk_state(rid, _pass_rr(rid), cand=CAND2, ev=EVID))
        code, out, raw = _run(["done", "--run-id", rid], self.env)
        self.assertEqual(code, 5, raw)
        self.assertEqual(out["status"], "DENIED")
        self.assertIn("candidate_commit does not bind the current RUN artifact",
                      out["problems"])

    def test_g5_done_denied_when_review_result_missing(self):
        # R NEXT_ACTION case: last_r_verdict=PASS alone is not sufficient.
        rid = "RUN-20260825-100011-b011"
        _write_state(self.root, rid, _mk_state(rid, None, cand=CAND, ev=EVID))
        code, out, raw = _run(["done", "--run-id", rid], self.env)
        self.assertEqual(code, 5, raw)
        self.assertEqual(out["status"], "DENIED")
        self.assertIn("review_result missing", out["problems"])

    def test_g6_done_denied_when_candidate_or_evidence_empty(self):
        # R NEXT_ACTION case: PASS stored but candidate/evidence bindings empty.
        rid = "RUN-20260825-100012-b012"
        rr = _pass_rr(rid)
        rr["candidate_commit"] = ""
        rr["evidence_id"] = ""
        _write_state(self.root, rid, _mk_state(rid, rr, cand=None, ev=None))
        code, out, raw = _run(["done", "--run-id", rid], self.env)
        self.assertEqual(code, 5, raw)
        # empty durable bindings are now caught by the identity closure,
        # before the review_result-side checks
        self.assertIn("state.candidate_commit missing or not a full 40-hex string (no coercion)",
                      out["problems"])
        self.assertIn("state.evidence_id missing or not a non-empty string (no coercion)",
                      out["problems"])

    def test_g7_done_denied_when_run_id_mismatch(self):
        rid = "RUN-20260825-100013-b013"
        rr = _pass_rr("RUN-20260825-100099-b099")  # bound to a different RUN
        _write_state(self.root, rid, _mk_state(rid, rr, cand=CAND, ev=EVID))
        code, out, raw = _run(["done", "--run-id", rid], self.env)
        self.assertEqual(code, 5, raw)
        self.assertIn("review_result.run_id not a genuine string strictly bound to this RUN",
                      out["problems"])

    def test_g8_done_denied_when_review_id_empty(self):
        rid = "RUN-20260825-100014-b014"
        rr = _pass_rr(rid)
        rr["review_id"] = ""
        _write_state(self.root, rid, _mk_state(rid, rr, cand=CAND, ev=EVID))
        code, out, raw = _run(["done", "--run-id", rid], self.env)
        self.assertEqual(code, 5, raw)
        self.assertIn("review_id empty or not a string", out["problems"])

    def test_g9_done_denied_when_state_revision_missing(self):
        rid = "RUN-20260825-100015-b015"
        rr = _pass_rr(rid)
        del rr["state_revision"]
        _write_state(self.root, rid, _mk_state(rid, rr, cand=CAND, ev=EVID))
        code, out, raw = _run(["done", "--run-id", rid], self.env)
        self.assertEqual(code, 5, raw)
        self.assertIn("state_revision missing or not a non-negative int (bool excluded)", out["problems"])

    def test_g10_done_denied_when_candidate_not_full_sha(self):
        rid = "RUN-20260825-100016-b016"
        rr = _pass_rr(rid)
        rr["candidate_commit"] = "deadbeef"  # not a 40-hex SHA
        _write_state(self.root, rid, _mk_state(rid, rr, cand="deadbeef", ev=EVID))
        code, out, raw = _run(["done", "--run-id", rid], self.env)
        self.assertEqual(code, 5, raw)
        # non-SHA durable candidate is caught by the identity closure first
        self.assertIn("state.candidate_commit missing or not a full 40-hex string (no coercion)",
                      out["problems"])

    def test_g11_done_denied_when_state_revision_bool(self):
        # R adversarial case: bool is an int subclass; True must not pass.
        rid = "RUN-20260825-100017-b017"
        rr = _pass_rr(rid)
        rr["state_revision"] = True
        _write_state(self.root, rid, _mk_state(rid, rr, cand=CAND, ev=EVID))
        code, out, raw = _run(["done", "--run-id", rid], self.env)
        self.assertEqual(code, 5, raw)
        self.assertIn("state_revision missing or not a non-negative int (bool excluded)",
                      out["problems"])

    def test_g12_done_denied_when_state_revision_negative(self):
        # R adversarial case: negative revisions must not pass.
        rid = "RUN-20260825-100018-b018"
        rr = _pass_rr(rid)
        rr["state_revision"] = -1
        _write_state(self.root, rid, _mk_state(rid, rr, cand=CAND, ev=EVID))
        code, out, raw = _run(["done", "--run-id", rid], self.env)
        self.assertEqual(code, 5, raw)
        self.assertIn("state_revision missing or not a non-negative int (bool excluded)",
                      out["problems"])

    def test_g13_done_denied_when_state_revision_future(self):
        # R adversarial case: verdict cannot bind a future revision.
        rid = "RUN-20260825-100019-b019"
        rr = _pass_rr(rid)
        rr["state_revision"] = 99  # state.revision is 7 in _mk_state
        _write_state(self.root, rid, _mk_state(rid, rr, cand=CAND, ev=EVID))
        code, out, raw = _run(["done", "--run-id", rid], self.env)
        self.assertEqual(code, 5, raw)
        self.assertIn("state_revision is a future revision (greater than current state.revision)", out["problems"])

    def test_g14_done_denied_when_current_revision_bool(self):
        # Current state.revision must also be a genuine non-negative int.
        rid = "RUN-20260825-100020-b020"
        st = _mk_state(rid, _pass_rr(rid), cand=CAND, ev=EVID)
        st["revision"] = True
        _write_state(self.root, rid, st)
        code, out, raw = _run(["done", "--run-id", rid], self.env)
        self.assertEqual(code, 5, raw)
        self.assertIn("current state.revision missing or not a non-negative int (bool excluded)",
                      out["problems"])

    def test_g15_done_denied_when_review_id_bool(self):
        # Disclosed extra hardening: non-string bindings are rejected by type.
        rid = "RUN-20260825-100021-b021"
        rr = _pass_rr(rid)
        rr["review_id"] = True
        _write_state(self.root, rid, _mk_state(rid, rr, cand=CAND, ev=EVID))
        code, out, raw = _run(["done", "--run-id", rid], self.env)
        self.assertEqual(code, 5, raw)
        self.assertIn("review_id empty or not a string", out["problems"])

    def test_g16_done_denied_when_evidence_id_bool(self):
        # Disclosed extra hardening: non-string bindings are rejected by type.
        rid = "RUN-20260825-100022-b022"
        rr = _pass_rr(rid)
        rr["evidence_id"] = True
        _write_state(self.root, rid, _mk_state(rid, rr, cand=CAND, ev=EVID))
        code, out, raw = _run(["done", "--run-id", rid], self.env)
        self.assertEqual(code, 5, raw)
        self.assertIn("evidence_id empty or not a string", out["problems"])


    def test_g17_done_denied_when_state_evidence_id_bool(self):
        # R REWORK3 repro: state.evidence_id=true with rr.evidence_id="True"
        # used to slip through str() coercion; identity closure must deny.
        rid = "RUN-20260825-100023-b023"
        rr = _pass_rr(rid)
        rr["evidence_id"] = "True"
        st = _mk_state(rid, rr, cand=CAND, ev=True)
        _write_state(self.root, rid, st)
        code, out, raw = _run(["done", "--run-id", rid], self.env)
        self.assertEqual(code, 5, raw)
        self.assertIn("state.evidence_id missing or not a non-empty string (no coercion)",
                      out["problems"])
        after = json.loads((self.root / "runs" / rid / "state.json").read_text(encoding="utf-8"))
        self.assertNotEqual(after["status"], "DONE")  # no DONE side effect

    def test_g18_done_denied_when_state_candidate_commit_int(self):
        # R REWORK3 repro: an int coercing to the same 40-hex-looking string
        # must not reach DONE.
        rid = "RUN-20260825-100024-b024"
        int_cand = 1234567890123456789012345678901234567890
        rr = _pass_rr(rid)
        rr["candidate_commit"] = "1234567890123456789012345678901234567890"
        st = _mk_state(rid, rr, cand=int_cand, ev=EVID)
        _write_state(self.root, rid, st)
        code, out, raw = _run(["done", "--run-id", rid], self.env)
        self.assertEqual(code, 5, raw)
        self.assertIn("state.candidate_commit missing or not a full 40-hex string (no coercion)",
                      out["problems"])
        after = json.loads((self.root / "runs" / rid / "state.json").read_text(encoding="utf-8"))
        self.assertNotEqual(after["status"], "DONE")

    def test_g19_done_denied_on_run_id_mismatch_no_cross_run_write(self):
        # R REWORK3 repro: directory RUN-A holding state.run_id=RUN-B must not
        # complete, and RUN-B must not be created or written.
        dir_rid = "RUN-20260825-100025-b025"
        other_rid = "RUN-20260825-100026-b026"
        rr = _pass_rr(other_rid)
        st = _mk_state(other_rid, rr, cand=CAND, ev=EVID)
        _write_state(self.root, dir_rid, st)  # foreign state inside dir_rid's dir
        code, out, raw = _run(["done", "--run-id", dir_rid], self.env)
        self.assertEqual(code, 5, raw)
        self.assertIn("state.run_id missing or does not match the requested RUN (cross-RUN write blocked)",
                      out["problems"])
        after = json.loads((self.root / "runs" / dir_rid / "state.json").read_text(encoding="utf-8"))
        self.assertNotEqual(after["status"], "DONE")           # original untouched
        self.assertFalse((self.root / "runs" / other_rid).exists())  # no cross-RUN creation
        jl = self.root / "runs" / dir_rid / "journal.jsonl"
        if jl.exists():
            self.assertNotIn("RUN_DONE", jl.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main(verbosity=2)
