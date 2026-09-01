"""Offline tests for runtime/final_gate.py (Canonical §74 十二条件门禁).

Covers:
- F1: happy path — all 12 conditions satisfied → FINAL_DONE_ELIGIBLE
- F2: each of the 12 conditions has an independent fail path
- F3: §45 integration — artifact states validated, completion states
      demand evidence, garbage evidence rejected, state/verdict cross-check
- F4: fail-closed — malformed manifests, missing files → exit 2
- F5: authority boundary — verdict is ELIGIBLE, never FINAL DONE

R-E rework hardening: every declarative boolean cites an on-disk
evidence source; C8 is digest+content bound (hex SHA, non-empty PASS
file naming every artifact); artifact review-level states must agree
with the reviewer verdict.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (str(HERE),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import final_gate as fg  # noqa: E402

PY = sys.executable


def _manifest(tmp: str, **overrides):
    """Fully-eligible manifest with real temp files on disk."""
    art = Path(tmp) / "artifact.txt"
    art.write_text("a", encoding="utf-8")
    dlv = Path(tmp) / "deliverable.md"
    dlv.write_text("d", encoding="utf-8")
    ev = Path(tmp) / "evidence.json"
    ev.write_text("{}", encoding="utf-8")
    rev = Path(tmp) / "r-verdict.md"
    rev.write_text("verdict: PASS\n- core: R_REVIEW_PASS\n", encoding="utf-8")
    runner = Path(tmp) / "acceptance.py"
    runner.write_text("# runner", encoding="utf-8")
    chk = Path(tmp) / "regression.log"
    chk.write_text("OK", encoding="utf-8")
    led = Path(tmp) / "effect-ledger.json"
    led.write_text("[]", encoding="utf-8")
    aud = Path(tmp) / "authority-audit.json"
    aud.write_text("[]", encoding="utf-8")
    goal_ev = Path(tmp) / "goal-evidence.md"
    goal_ev.write_text("goal met", encoding="utf-8")
    m = {
        "goal": {"ref": "FINAL_PROMPT v16", "implemented": True,
                 "evidence": str(goal_ev)},
        "deliverables": [{"name": "report", "path": str(dlv)}],
        "acceptance": {"criteria_met": True, "runner": str(runner)},
        "artifacts": [{"name": "core", "path": str(art),
                       "state": "R_REVIEW_PASS",
                       "evidence": ["tests/test_x.py", "reviews/R-VERDICT.md"]}],
        "machine_checks": [{"name": "regression", "passed": True,
                            "command": "runtime/run.cmd regression",
                            "evidence": str(chk)}],
        "evidence": [str(ev)],
        "reviewer": {"independent": True, "verdict": "PASS",
                     "commit": "18bcb3486c5abd2a4764498afb534fb54dfac7a0",
                     "evidence": str(rev)},
        "blockers": [],
        "effect_state": {"consistent": True, "unreconciled_unknown": 0,
                         "evidence": str(led)},
        "authority": {"revoked_still_used": 0, "evidence": str(aud)},
    }
    m.update(overrides)
    return m


class F1HappyPathTests(unittest.TestCase):
    """F1：十二条件全绿 → FINAL_DONE_ELIGIBLE。"""

    def test_f1_all_conditions_eligible(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = fg.evaluate(_manifest(tmp))
        self.assertEqual(r["verdict"], "FINAL_DONE_ELIGIBLE")
        self.assertTrue(r["ok"])
        self.assertTrue(all(c["ok"] for c in r["conditions"].values()))
        self.assertEqual(len(r["conditions"]), 12)

    def test_f1_twelve_conditions_c1_to_c12_in_order(self):
        codes = [code for code, _ in fg.CONDITIONS]
        self.assertEqual(codes, [f"C{i}" for i in range(1, 13)])


class F2IndependentFailTests(unittest.TestCase):
    """F2：十二条各自有独立失败路径，问题码可定位。"""

    def _expect(self, code_prefix, **overrides):
        with tempfile.TemporaryDirectory() as tmp:
            r = fg.evaluate(_manifest(tmp, **overrides))
        self.assertEqual(r["verdict"], "NOT_ELIGIBLE")
        self.assertTrue(any(p.startswith(code_prefix) for p in r["problems"]),
                        r["problems"])
        self.assertFalse(r["conditions"][code_prefix.split("_")[0]]["ok"])
        return r

    def test_f2_c1_goal(self):
        self._expect("C1_", goal={"ref": "x", "implemented": False})
        self._expect("C1_GOAL_REF_MISSING", goal={"implemented": True})
        self._expect("C1_GOAL_EVIDENCE_NOT_FOUND",
                     goal={"ref": "x", "implemented": True,
                           "evidence": "Z:/no/goal.md"})

    def test_f2_c2_deliverables(self):
        self._expect("C2_NO_DELIVERABLES", deliverables=[])
        with tempfile.TemporaryDirectory() as tmp:
            r = fg.evaluate(_manifest(
                tmp, deliverables=[{"name": "ghost", "path": "Z:/no/where"}]))
        self.assertTrue(any(p.startswith("C2_DELIVERABLE_NOT_FOUND")
                            for p in r["problems"]))

    def test_f2_c3_acceptance(self):
        self._expect("C3_CRITERIA_NOT_MET",
                     acceptance={"criteria_met": False, "runner": "r"})
        self._expect("C3_RUNNER_MISSING", acceptance={"criteria_met": True})
        self._expect("C3_RUNNER_NOT_FOUND",
                     acceptance={"criteria_met": True,
                                 "runner": "Z:/no/runner.py"})

    def test_f2_c4_artifacts(self):
        self._expect("C4_NO_ARTIFACTS", artifacts=[])
        with tempfile.TemporaryDirectory() as tmp:
            r = fg.evaluate(_manifest(
                tmp, artifacts=[{"name": "ghost", "path": "Z:/no/where",
                                 "state": "E2E_PASS", "evidence": []}]))
        self.assertTrue(any(p.startswith("C4_ARTIFACT_NOT_FOUND")
                            for p in r["problems"]))

    def test_f2_c5_machine_checks(self):
        self._expect("C5_NO_MACHINE_CHECKS", machine_checks=[])
        self._expect("C5_CHECK_FAILED",
                     machine_checks=[{"name": "reg", "passed": False,
                                      "command": "x", "evidence": "e"}])
        self._expect("C5_CHECK_NO_COMMAND",
                     machine_checks=[{"name": "reg", "passed": True,
                                      "command": "",
                                      "evidence": str(Path("e"))}])
        self._expect("C5_CHECK_EVIDENCE_NOT_FOUND",
                     machine_checks=[{"name": "reg", "passed": True,
                                      "command": "x",
                                      "evidence": "Z:/no/log.txt"}])

    def test_f2_c6_evidence(self):
        self._expect("C6_NO_EVIDENCE", evidence=[])
        with tempfile.TemporaryDirectory() as tmp:
            r = fg.evaluate(_manifest(tmp, evidence=["Z:/no/evidence.md"]))
        self.assertTrue(any(p.startswith("C6_EVIDENCE_NOT_FOUND")
                            for p in r["problems"]))

    def test_f2_c7_reviewer(self):
        self._expect("C7_REVIEWER_NOT_INDEPENDENT",
                     reviewer={"independent": False, "verdict": "PASS",
                               "commit": "a" * 40, "evidence": "e.md"})
        self._expect("C7_REVIEW_NOT_PASS",
                     reviewer={"independent": True, "verdict": "REWORK",
                               "commit": "a" * 40, "evidence": "e.md"})

    def test_f2_c8_binding(self):
        self._expect("C8_REVIEW_COMMIT_MISSING",
                     reviewer={"independent": True, "verdict": "PASS",
                               "commit": "", "evidence": "e.md"})
        self._expect("C8_REVIEW_COMMIT_MALFORMED",
                     reviewer={"independent": True, "verdict": "PASS",
                               "commit": "not-a-sha", "evidence": "e.md"})
        self._expect("C8_REVIEW_EVIDENCE_NOT_FOUND",
                     reviewer={"independent": True, "verdict": "PASS",
                               "commit": "a" * 40,
                               "evidence": "Z:/no/verdict.md"})

    def test_f2_c8_content_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.md"
            empty.write_text("", encoding="utf-8")
            self._expect("C8_REVIEW_EVIDENCE_EMPTY",
                         reviewer={"independent": True, "verdict": "PASS",
                                   "commit": "a" * 40, "evidence": str(empty)})
            nopass = Path(tmp) / "nopass.md"
            nopass.write_text("looks fine to me", encoding="utf-8")
            self._expect("C8_REVIEW_EVIDENCE_NO_PASS",
                         reviewer={"independent": True, "verdict": "PASS",
                                   "commit": "a" * 40, "evidence": str(nopass)})
            unbound = Path(tmp) / "unbound.md"
            unbound.write_text("PASS but names nothing", encoding="utf-8")
            self._expect("C8_REVIEW_NOT_BOUND",
                         reviewer={"independent": True, "verdict": "PASS",
                                   "commit": "a" * 40, "evidence": str(unbound)})

    def test_f2_c9_blockers(self):
        self._expect("C9_BLOCKER_OPEN", blockers=["lease seam unresolved"])

    def test_f2_c10_effect(self):
        self._expect("C10_EFFECT_STATE_INCONSISTENT",
                     effect_state={"consistent": False,
                                   "unreconciled_unknown": 0,
                                   "evidence": "e"})
        self._expect("C10_EFFECT_EVIDENCE_NOT_FOUND",
                     effect_state={"consistent": True,
                                   "unreconciled_unknown": 0,
                                   "evidence": "Z:/no/ledger.json"})

    def test_f2_c11_unknown(self):
        self._expect("C11_UNRECONCILED_UNKNOWN",
                     effect_state={"consistent": True,
                                   "unreconciled_unknown": 2,
                                   "evidence": "e"})

    def test_f2_c11_evidence_missing_independent(self):
        """R-E 终裁遗留:unknown=0 但 evidence 缺失 → 独立问题码。"""
        self._expect("C11_EFFECT_EVIDENCE_NOT_FOUND",
                     effect_state={"consistent": True,
                                   "unreconciled_unknown": 0,
                                   "evidence": "Z:/no/ledger.json"})

    def test_f2_c12_authority(self):
        self._expect("C12_REVOKED_AUTHORITY_IN_USE",
                     authority={"revoked_still_used": 1, "evidence": "e"})
        self._expect("C12_AUTHORITY_EVIDENCE_NOT_FOUND",
                     authority={"revoked_still_used": 0,
                                "evidence": "Z:/no/audit.json"})


class F3StateLevelIntegrationTests(unittest.TestCase):
    """F3：§45 集成——伪状态/垃圾索证/状态裁定脱钩在门禁处被拒。"""

    def test_f3_invalid_state_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = fg.evaluate(_manifest(tmp, artifacts=[
                {"name": "core", "path": str(Path(tmp) / "artifact.txt"),
                 "state": "CODE_WRITTEN", "evidence": []}]))
        self.assertTrue(any(p.startswith("C4_ARTIFACT_STATE_INVALID")
                            for p in r["problems"]))

    def test_f3_completion_state_without_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = fg.evaluate(_manifest(tmp, artifacts=[
                {"name": "core", "path": str(Path(tmp) / "artifact.txt"),
                 "state": "E2E_PASS", "evidence": []}]))
        self.assertTrue(any("CLAIM_NO_EVIDENCE" in p for p in r["problems"]))

    def test_f3_garbage_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = fg.evaluate(_manifest(tmp, artifacts=[
                {"name": "core", "path": str(Path(tmp) / "artifact.txt"),
                 "state": "LOCAL_TEST_PASS", "evidence": ["untested"]}]))
        self.assertTrue(any("CLAIM_EVIDENCE_MISSING" in p
                            for p in r["problems"]))

    def test_f3_state_verdict_mismatch_rejected(self):
        """R-E P2：artifact 自报 R_REVIEW_PASS 但 Reviewer 裁定非 PASS。"""
        with tempfile.TemporaryDirectory() as tmp:
            m = _manifest(tmp)
            m["reviewer"]["verdict"] = "REWORK"
            r = fg.evaluate(m)
        self.assertTrue(any(p.startswith("C4_STATE_REVIEW_MISMATCH")
                            for p in r["problems"]))
        self.assertFalse(r["conditions"]["C4"]["ok"])

    def test_f3_mismatch_not_flagged_when_below_review_level(self):
        """低于 review 层级的 artifact 状态不参与该交叉核验。"""
        with tempfile.TemporaryDirectory() as tmp:
            m = _manifest(tmp)
            m["reviewer"]["verdict"] = "REWORK"
            m["artifacts"][0]["state"] = "LOCAL_TEST_PASS"
            m["artifacts"][0]["evidence"] = ["tests/test_x.py"]
            r = fg.evaluate(m)
        self.assertFalse(any(p.startswith("C4_STATE_REVIEW_MISMATCH")
                             for p in r["problems"]))


class F4FailClosedTests(unittest.TestCase):
    """F4：畸形输入 fail-closed。"""

    def _run(self, *argv):
        return subprocess.run([PY, str(HERE / "final_gate.py"), *argv],
                              capture_output=True, text=True,
                              encoding="utf-8", timeout=30)

    def test_f4_missing_manifest_exit_2(self):
        self.assertEqual(self._run("check", "--file", "Z:/none.json").returncode, 2)

    def test_f4_malformed_manifest_exit_2_no_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "m.json"
            f.write_text("[1,2]", encoding="utf-8")  # 数组而非对象
            r = self._run("check", "--file", str(f))
        self.assertEqual(r.returncode, 2)
        self.assertIn("MANIFEST_INVALID", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_f4_cli_eligible_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "m.json"
            f.write_text(json.dumps(_manifest(tmp)), encoding="utf-8")
            r = self._run("check", "--file", str(f))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["verdict"], "FINAL_DONE_ELIGIBLE")


class F5AuthorityBoundaryTests(unittest.TestCase):
    """F5：门禁只出 ELIGIBLE，永不替业主宣布 FINAL DONE。"""

    def test_f5_no_final_done_string_in_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = fg.evaluate(_manifest(tmp))
        self.assertNotEqual(r["verdict"], "FINAL_DONE")
        self.assertTrue(r["non_authority"])
        self.assertIn("Human Gate", r["human_gate"])

    def test_f5_no_input_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = _manifest(tmp)
            snap = json.dumps(m, sort_keys=True)
            fg.evaluate(m)
        self.assertEqual(json.dumps(m, sort_keys=True), snap)


if __name__ == "__main__":
    unittest.main()
