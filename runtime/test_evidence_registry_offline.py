#!/usr/bin/env python3
"""Offline tests for V0.5 Slice C: Evidence Registry Lite.

Evidence industrialization (V0.5 scope "Evidence"): HE units become first-class
durable records of the RUN — registered with an integrity hash of
machine_evidence.json, bound to the RUN's candidate when both sides carry one,
fail-closed on any precondition failure, and re-verifiable for tamper/loss
detection at any later time.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime.py"
sys.path.insert(0, str(HERE))
import runtime as rt

CAND_A = "ab11830" + "0" * 33
CAND_B = "ef11a5a" + "1" * 33


def _run(argv, env):
    proc = subprocess.run([sys.executable, str(RUNTIME), *argv], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env, timeout=120)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {"_raw": proc.stdout}
    return proc.returncode, out, proc.stdout + proc.stderr


class EvidenceRegistryTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.env = dict(os.environ)
        self.env["APC_RUNTIME_STATE_ROOT"] = str(self.root)
        code, out, raw = _run(["start", "--goal", "evidence registry test",
                               "--r-url", "https://chatgpt.com/c/evreg0001"], self.env)
        assert code == 0, raw
        self.rid = out["run_id"]
        self.ev_root = self.root / "evidence"
        self.ev_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.td.cleanup()

    def _mk_evidence(self, eid: str, doc: dict | None = None, raw: str | None = None) -> Path:
        d = self.ev_root / eid
        d.mkdir(parents=True, exist_ok=True)
        p = d / "machine_evidence.json"
        if raw is not None:
            p.write_text(raw, encoding="utf-8")
        else:
            p.write_text(json.dumps(doc if doc is not None else
                                    {"status": "SUCCEEDED", "round": 1}, ensure_ascii=False),
                         encoding="utf-8")
        return d

    def _register(self, eid: str, path: Path):
        return _run(["evidence-register", "--run-id", self.rid,
                     "--evidence-id", eid, "--path", str(path)], self.env)

    def _verify(self, eid: str | None = None):
        argv = ["evidence-verify", "--run-id", self.rid]
        if eid:
            argv += ["--evidence-id", eid]
        return _run(argv, self.env)

    def _set_run_candidate(self, cand: str):
        backup = rt.RUNS_ROOT
        rt.RUNS_ROOT = self.root / "runs"
        try:
            st = rt.load_state(self.rid)
            st["candidate_commit"] = cand
            rt.save_state(st)
        finally:
            rt.RUNS_ROOT = backup

    def _journal(self):
        return (self.root / "runs" / self.rid / "journal.jsonl").read_text(encoding="utf-8")

    def test_v1_register_valid(self):
        eid = "HE-aaaaaaaaaaaaaaa1"
        d = self._mk_evidence(eid)
        code, out, raw = self._register(eid, d)
        self.assertEqual(code, 0, raw)
        self.assertEqual(out["status"], "OK")
        self.assertEqual(len(out["sha256_machine_evidence"]), 64)
        self.assertIn("EVIDENCE_REGISTERED", self._journal())

    def test_v2_missing_doc_denied(self):
        eid = "HE-aaaaaaaaaaaaaaa2"
        d = self.ev_root / eid
        d.mkdir(parents=True, exist_ok=True)
        code, out, raw = self._register(eid, d)
        self.assertEqual(code, 5, raw)
        self.assertEqual(out["status"], "DENIED")

    def test_v3_invalid_he_id(self):
        d = self._mk_evidence("HE-bbbbbbbbbbbbbbb3")
        code, out, raw = self._register("HE-XYZ", d)
        self.assertEqual(code, 2, raw)
        self.assertEqual(out["status"], "INVALID_EVIDENCE_ID")

    def test_v4_unparseable_doc_denied(self):
        eid = "HE-aaaaaaaaaaaaaaa4"
        d = self._mk_evidence(eid, raw="{ broken")
        code, out, raw = self._register(eid, d)
        self.assertEqual(code, 5, raw)
        self.assertEqual(out["status"], "DENIED")

    def test_v5_candidate_mismatch_denied(self):
        self._set_run_candidate(CAND_A)
        eid = "HE-aaaaaaaaaaaaaaa5"
        d = self._mk_evidence(eid, {"candidate_commit": CAND_B})
        code, out, raw = self._register(eid, d)
        self.assertEqual(code, 5, raw)
        self.assertEqual(out["status"], "DENIED")
        self.assertIn("does not bind", out["reason"])

    def test_v6_candidate_match_case_insensitive(self):
        self._set_run_candidate(CAND_A)
        eid = "HE-aaaaaaaaaaaaaaa6"
        d = self._mk_evidence(eid, {"candidate_commit": CAND_A.upper()})
        code, out, raw = self._register(eid, d)
        self.assertEqual(code, 0, raw)
        self.assertEqual(out["status"], "OK")

    def test_v7_reregister_updates_entry(self):
        eid = "HE-aaaaaaaaaaaaaaa7"
        d = self._mk_evidence(eid, {"v": 1})
        code, out, raw = self._register(eid, d)
        self.assertEqual(code, 0, raw)
        self.assertFalse(out["reregistered"])
        (d / "machine_evidence.json").write_text(json.dumps({"v": 2}), encoding="utf-8")
        code, out, raw = self._register(eid, d)
        self.assertEqual(code, 0, raw)
        self.assertTrue(out["reregistered"])
        self.assertEqual(out["registered_count"], 1)

    def test_v8_verify_all_valid(self):
        for i in (8, 9):
            eid = f"HE-aaaaaaaaaaaaaaa{i}"
            self._register(eid, self._mk_evidence(eid))
        code, out, raw = self._verify()
        self.assertEqual(code, 0, raw)
        self.assertTrue(out["all_valid"])
        self.assertEqual(out["checked"], 2)

    def test_v9_tamper_detected(self):
        eid = "HE-aaaaaaaaaaaaaa10"
        d = self._mk_evidence(eid, {"v": 1})
        code, out, raw = self._register(eid, d)
        self.assertEqual(code, 0, raw)
        # Rewrite as different-but-still-valid JSON -> hash drift, not a parse error.
        (d / "machine_evidence.json").write_text(json.dumps({"v": 2}), encoding="utf-8")
        code, out, raw = self._verify(eid)
        self.assertEqual(code, 0, raw)
        self.assertFalse(out["all_valid"])
        self.assertIn("hash drift", out["results"][eid]["reason"])

    def test_v10_missing_dir_detected(self):
        eid = "HE-aaaaaaaaaaaaaa11"
        d = self._mk_evidence(eid)
        code, out, raw = self._register(eid, d)
        self.assertEqual(code, 0, raw)
        shutil.rmtree(d)
        code, out, raw = self._verify(eid)
        self.assertEqual(code, 0, raw)
        self.assertFalse(out["results"][eid]["valid"])
        self.assertEqual(out["results"][eid]["reason"], "evidence directory missing")

    def test_v11_verify_unknown_id(self):
        eid = "HE-aaaaaaaaaaaaaa12"
        self._register(eid, self._mk_evidence(eid))
        code, out, raw = self._verify("HE-fffffffffffffff0")
        self.assertEqual(code, 0, raw)
        self.assertEqual(out["status"], "EVIDENCE_NOT_REGISTERED")
        self.assertEqual(out["registered"], [eid])


if __name__ == "__main__":
    unittest.main(verbosity=2)
