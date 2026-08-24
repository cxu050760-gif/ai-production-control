#!/usr/bin/env python3
"""Offline tests for V0.5 Slice A: review-valid (PASS binding validation).

review-valid lets the Runtime answer mechanically: "does the stored R PASS still
bind to the artifact we have now?" A material change (different candidate
commit or evidence id) must invalidate the old PASS (definition #30 Stale
Result Safety / #43 Review must bind Artifact).
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

CAND = "ab11830" + "0" * 33          # 40-hex-ish sample commit
CAND2 = "ef11a5a" + "1" * 33
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


def _write_state(root: Path, rid: str, state: dict) -> None:
    d = root / "runs" / rid
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2),
                                  encoding="utf-8")


def _mk_state(rid: str, review_result=None) -> dict:
    st = {"run_id": rid, "schema_version": 1, "revision": 7, "status": "RUNNING",
          "goal": "g", "r_url": "https://chatgpt.com/c/x",
          "metrics": {"rework_count": 0}}
    if review_result is not None:
        st["review_result"] = review_result
    return st


def _pass_rr() -> dict:
    return {"run_id": "RUN-20260824-190000-a001", "review_id": "REV-20260824-190101-aaaa",
            "candidate_commit": CAND, "evidence_id": EVID, "state_revision": 7,
            "verdict": "PASS", "next_action": "", "reply_path": "r.txt", "reply_bytes": 10,
            "returned_at": "2026-08-24T19:01:01Z"}


class ReviewValidTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.env = dict(os.environ)
        self.env["APC_RUNTIME_STATE_ROOT"] = str(self.root)

    def tearDown(self):
        self.td.cleanup()

    def test_rv1_no_pass_stored(self):
        rid = "RUN-20260824-190001-a002"
        _write_state(self.root, rid, _mk_state(rid))
        code, out, raw = _run(["review-valid", "--run-id", rid], self.env)
        self.assertEqual(code, 0, raw)
        self.assertFalse(out["valid"])
        self.assertEqual(out["reason"], "no stored PASS to validate")

    def test_rv2_pass_binding_matches(self):
        rid = "RUN-20260824-190002-a003"
        _write_state(self.root, rid, _mk_state(rid, _pass_rr()))
        code, out, raw = _run(["review-valid", "--run-id", rid,
                               "--candidate-commit", CAND, "--evidence-id", EVID], self.env)
        self.assertEqual(code, 0, raw)
        self.assertTrue(out["valid"])
        self.assertEqual(out["reason"], "PASS binding matches current artifact")

    def test_rv3_candidate_changed_invalidates(self):
        rid = "RUN-20260824-190003-a004"
        _write_state(self.root, rid, _mk_state(rid, _pass_rr()))
        code, out, raw = _run(["review-valid", "--run-id", rid,
                               "--candidate-commit", CAND2, "--evidence-id", EVID], self.env)
        self.assertEqual(code, 0, raw)
        self.assertFalse(out["valid"])
        self.assertEqual(out["changed"], ["candidate_commit"])
        self.assertEqual(out["reason"], "material change invalidates old PASS")

    def test_rv4_evidence_changed_invalidates(self):
        rid = "RUN-20260824-190004-a005"
        _write_state(self.root, rid, _mk_state(rid, _pass_rr()))
        code, out, raw = _run(["review-valid", "--run-id", rid,
                               "--candidate-commit", CAND, "--evidence-id", EVID2], self.env)
        self.assertEqual(code, 0, raw)
        self.assertFalse(out["valid"])
        self.assertEqual(out["changed"], ["evidence_id"])

    def test_rv5_both_changed_lists_both(self):
        rid = "RUN-20260824-190005-a006"
        _write_state(self.root, rid, _mk_state(rid, _pass_rr()))
        code, out, raw = _run(["review-valid", "--run-id", rid,
                               "--candidate-commit", CAND2, "--evidence-id", EVID2], self.env)
        self.assertEqual(code, 0, raw)
        self.assertFalse(out["valid"])
        self.assertEqual(sorted(out["changed"]), ["candidate_commit", "evidence_id"])

    def test_rv6_run_not_found(self):
        code, out, raw = _run(["review-valid", "--run-id", "RUN-20260824-190006-a007"],
                              self.env)
        self.assertEqual(code, 4, raw)
        self.assertEqual(out["status"], "RUN_NOT_FOUND")

    def test_rv7_omitted_bindings_are_not_checked(self):
        rid = "RUN-20260824-190007-a008"
        _write_state(self.root, rid, _mk_state(rid, _pass_rr()))
        code, out, raw = _run(["review-valid", "--run-id", rid], self.env)
        self.assertEqual(code, 0, raw)
        self.assertTrue(out["valid"])

    def test_rv8_non_pass_verdict_is_not_validatable(self):
        rid = "RUN-20260824-190008-a009"
        rr = _pass_rr()
        rr["verdict"] = "REWORK"
        _write_state(self.root, rid, _mk_state(rid, rr))
        code, out, raw = _run(["review-valid", "--run-id", rid,
                               "--candidate-commit", CAND], self.env)
        self.assertEqual(code, 0, raw)
        self.assertFalse(out["valid"])
        self.assertEqual(out["reason"], "no stored PASS to validate")

    def test_rv9_apply_verdict_records_state_revision(self):
        # V0.5: review_result must carry the state revision the verdict was
        # taken against (Stale Result Safety, definition #30).
        self._rt_root_backup = rt.RUNS_ROOT
        rt.RUNS_ROOT = self.root / "runs"
        try:
            rid = "RUN-20260824-190009-a010"
            (self.root / "runs" / rid).mkdir(parents=True, exist_ok=True)
            state = _mk_state(rid)
            reply = self.root / "reply.txt"
            reply.write_text("PASS", encoding="utf-8")
            rt.apply_verdict(state, "PASS", "ok", reply, 4)
            rr = state["review_result"]
            self.assertEqual(rr["verdict"], "PASS")
            self.assertEqual(rr["state_revision"], 7)
            self.assertTrue(rr["review_id"])
            jl = (self.root / "runs" / rid / "journal.jsonl").read_text(encoding="utf-8")
            self.assertIn("REVIEW_RESULT_RETURN", jl)
        finally:
            rt.RUNS_ROOT = self._rt_root_backup


if __name__ == "__main__":
    unittest.main(verbosity=2)
