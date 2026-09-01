"""Offline tests for runtime/state_level.py (Canonical §45 状态层级).

Covers:
- S1: closed enumeration — all 12 canonical states validate, unknown rejected
- S2: strict monotonic rank over the 8 progressive states
- S3: "代码写了 = 产品完成" prohibition — evidence demands per level
- S4: regression detection (E2E_PASS -> IMPLEMENTED flagged)
- S5: exception states never constitute completion claims
- S6: CLI contract (validate / check-claim / check-file exit codes)
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

import state_level as sl  # noqa: E402

PY = sys.executable


class S1ClosedEnumerationTests(unittest.TestCase):
    """S1：§45 十二态封闭枚举，未知态 fail-closed。"""

    def test_s1_all_twelve_canonical_states_validate(self):
        for st in ("DISCUSSED", "FOUND", "LOCAL_EXISTS", "IMPLEMENTED",
                   "LOCAL_TEST_PASS", "R_REVIEW_PASS", "E2E_PASS",
                   "PRODUCTION_VERIFIED", "PARTIAL", "NOT_VERIFIED",
                   "FAILED", "BLOCKED"):
            self.assertEqual(sl.validate_state(st), st)

    def test_s1_case_and_whitespace_normalized(self):
        self.assertEqual(sl.validate_state("  e2e_pass  "), "E2E_PASS")

    def test_s1_unknown_state_rejected(self):
        for bad in ("DONE", "FINISHED", "CODE_WRITTEN", "OK", ""):
            with self.assertRaises(sl.StateLevelError):
                sl.validate_state(bad)

    def test_s1_none_and_empty_rejected(self):
        with self.assertRaises(sl.StateLevelError):
            sl.validate_state(None)


class S2RankTests(unittest.TestCase):
    """S2：八个递进态严格单调，四个异常态无 rank。"""

    PROGRESSIVE = ["DISCUSSED", "FOUND", "LOCAL_EXISTS", "IMPLEMENTED",
                   "LOCAL_TEST_PASS", "R_REVIEW_PASS", "E2E_PASS",
                   "PRODUCTION_VERIFIED"]

    def test_s2_progressive_ranks_strictly_increasing(self):
        ranks = [sl.rank_of(s) for s in self.PROGRESSIVE]
        self.assertEqual(ranks, sorted(ranks))
        self.assertEqual(len(set(ranks)), len(ranks))
        self.assertEqual(ranks[0], 0)

    def test_s2_exception_states_have_no_rank(self):
        for st in ("PARTIAL", "NOT_VERIFIED", "FAILED", "BLOCKED"):
            self.assertIsNone(sl.rank_of(st))

    def test_s2_exception_states_are_exactly_the_rankless_four(self):
        rankless = {s for s in sl.STATE_LEVELS if s not in sl.LEVEL_RANK}
        self.assertEqual(rankless, {"PARTIAL", "NOT_VERIFIED", "FAILED", "BLOCKED"})


class S3CompletionProhibitionTests(unittest.TestCase):
    """S3：'代码写了 = 产品完成' 被机器拒绝。"""

    def test_s3_implemented_without_evidence_is_not_completion(self):
        self.assertFalse(sl.is_completion_claim("IMPLEMENTED"))

    def test_s3_claim_at_implemented_demands_no_more_but_flags_nothing(self):
        # IMPLEMENTED 本身不额外索证（它不是完成声明），但也不算完成。
        self.assertEqual(sl.check_claim("IMPLEMENTED", []), [])

    def test_s3_local_test_pass_requires_test_evidence(self):
        problems = sl.check_claim("LOCAL_TEST_PASS", [])
        self.assertIn("CLAIM_NO_EVIDENCE:LOCAL_TEST_PASS", problems)
        self.assertEqual(sl.check_claim("LOCAL_TEST_PASS", ["runtime/test_report.json"]), [])

    def test_s3_r_review_pass_requires_test_and_review(self):
        self.assertIn("CLAIM_EVIDENCE_MISSING:R_REVIEW_PASS:review",
                      sl.check_claim("R_REVIEW_PASS", ["test_report.json"]))
        self.assertIn("CLAIM_EVIDENCE_MISSING:R_REVIEW_PASS:test",
                      sl.check_claim("R_REVIEW_PASS", ["r-verdict.md"]))
        self.assertEqual(
            sl.check_claim("R_REVIEW_PASS",
                           ["test_report.json", "reviews/R-VERDICT.md"]), [])

    def test_s3_e2e_and_production_stack_requirements(self):
        full = ["tests/", "review.md", "e2e.log", "production/prod-log.txt"]
        self.assertEqual(sl.check_claim("E2E_PASS", full), [])
        self.assertEqual(sl.check_claim("PRODUCTION_VERIFIED", full), [])
        self.assertIn("CLAIM_EVIDENCE_MISSING:PRODUCTION_VERIFIED:production",
                      sl.check_claim("PRODUCTION_VERIFIED",
                                     ["tests/", "review.md", "e2e.log"]))

    def test_s3_token_matching_rejects_substring_evasion(self):
        """R-D P1：子串词面逃逸被词边界匹配封死。"""
        self.assertIn("CLAIM_EVIDENCE_MISSING:LOCAL_TEST_PASS:test",
                      sl.check_claim("LOCAL_TEST_PASS", ["untested"]))
        self.assertIn("CLAIM_EVIDENCE_MISSING:R_REVIEW_PASS:review",
                      sl.check_claim("R_REVIEW_PASS", ["preview.md"]))
        self.assertIn("CLAIM_EVIDENCE_MISSING:PRODUCTION_VERIFIED:production",
                      sl.check_claim("PRODUCTION_VERIFIED",
                                     ["tests/", "review.md", "e2e.log",
                                      "preproduction/notes.md"]))
        # 复数形态仍匹配：tests/ 与 reviews/ 是合法证据名
        self.assertEqual(sl.check_claim("R_REVIEW_PASS",
                                        ["tests/x.json", "reviews/R-VERDICT.md"]),
                         [])

    def test_s3_discussed_found_need_no_evidence(self):
        self.assertEqual(sl.check_claim("DISCUSSED", []), [])
        self.assertEqual(sl.check_claim("FOUND", []), [])


class S4RegressionTests(unittest.TestCase):
    """S4：层级倒退机器可见。"""

    def test_s4_regression_flagged(self):
        self.assertEqual(sl.check_progression("E2E_PASS", "IMPLEMENTED"),
                         ["LEVEL_REGRESSION:E2E_PASS->IMPLEMENTED"])
        self.assertEqual(sl.check_progression("R_REVIEW_PASS", "LOCAL_TEST_PASS"),
                         ["LEVEL_REGRESSION:R_REVIEW_PASS->LOCAL_TEST_PASS"])

    def test_s4_upgrade_and_lateral_pass(self):
        self.assertEqual(sl.check_progression("IMPLEMENTED", "LOCAL_TEST_PASS"), [])
        self.assertEqual(sl.check_progression("E2E_PASS", "E2E_PASS"), [])

    def test_s4_exception_transition_not_rank_regression(self):
        # E2E_PASS -> FAILED：非递进序倒退，但必须是显式异常态而非伪装降级。
        self.assertEqual(sl.check_progression("E2E_PASS", "FAILED"), [])

    def test_s4_reentry_from_exception_requires_evidence(self):
        """R-D P2：异常态隧道封堵——从异常态重回完成层级须重新索证。"""
        # 无证据重返 → 显式问题码，不可静默通过
        self.assertEqual(sl.check_progression("FAILED", "PRODUCTION_VERIFIED"),
                         ["REENTRY_EVIDENCE_REQUIRED:PRODUCTION_VERIFIED"])
        # 带充分证据重返 → 放行
        full = ["tests/", "review.md", "e2e.log", "production/p.log"]
        self.assertEqual(
            sl.check_progression("FAILED", "PRODUCTION_VERIFIED", full), [])
        # 带垃圾证据重返 → REENTRY_ 前缀问题码
        self.assertEqual(
            sl.check_progression("BLOCKED", "E2E_PASS", ["untested"]),
            ["REENTRY_CLAIM_EVIDENCE_MISSING:E2E_PASS:test",
             "REENTRY_CLAIM_EVIDENCE_MISSING:E2E_PASS:review",
             "REENTRY_CLAIM_EVIDENCE_MISSING:E2E_PASS:e2e"])
        # 异常态 -> 未完成层级（IMPLEMENTED）不索证，仍放行
        self.assertEqual(sl.check_progression("FAILED", "IMPLEMENTED"), [])

    def test_s4_invalid_sides_fail_closed(self):
        self.assertTrue(sl.check_progression("DONE", "E2E_PASS"))
        self.assertTrue(sl.check_progression("E2E_PASS", "WAT"))


class S5ExceptionStateTests(unittest.TestCase):
    """S5：异常态永不构成完成声明。"""

    def test_s5_exception_states_never_completion(self):
        for st in ("PARTIAL", "NOT_VERIFIED", "FAILED", "BLOCKED"):
            self.assertFalse(sl.is_completion_claim(st))

    def test_s5_all_states_below_local_test_pass_never_completion(self):
        for st in ("DISCUSSED", "FOUND", "LOCAL_EXISTS", "IMPLEMENTED"):
            self.assertFalse(sl.is_completion_claim(st))

    def test_s5_completion_requires_evidence_single_semantics(self):
        """R-D P2：单一口径——无证据永不判完成，证据充分才 True。"""
        full = ["tests/", "review.md", "e2e.log", "production/p.log"]
        for st in ("LOCAL_TEST_PASS", "R_REVIEW_PASS", "E2E_PASS",
                   "PRODUCTION_VERIFIED"):
            self.assertFalse(sl.is_completion_claim(st))          # 无证据
        self.assertFalse(sl.is_completion_claim("E2E_PASS", ["untested"]))
        self.assertTrue(sl.is_completion_claim("E2E_PASS",
                                               ["tests/", "review.md", "e2e.log"]))
        self.assertTrue(sl.is_completion_claim("PRODUCTION_VERIFIED", full))


class S6CliTests(unittest.TestCase):
    """S6：CLI 三动词契约。"""

    def _run(self, *argv):
        return subprocess.run(
            [PY, str(HERE / "state_level.py"), *argv],
            capture_output=True, text=True, encoding="utf-8", timeout=30)

    def test_s6_validate_ok_and_unknown(self):
        r = self._run("validate", "--state", "E2E_PASS")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(json.loads(r.stdout)["ok"])
        r2 = self._run("validate", "--state", "DONE")
        self.assertEqual(r2.returncode, 2)
        self.assertIn("STATE_UNKNOWN", json.loads(r2.stdout)["problem"])

    def test_s6_check_claim_exit_codes(self):
        r = self._run("check-claim", "--state", "LOCAL_TEST_PASS",
                      "--evidence", "test_report.json")
        self.assertEqual(r.returncode, 0)
        r2 = self._run("check-claim", "--state", "LOCAL_TEST_PASS", "--evidence", "")
        self.assertEqual(r2.returncode, 2)

    def test_s6_check_file_batch(self):
        payload = [
            {"id": "a", "state": "E2E_PASS", "prev_state": "R_REVIEW_PASS",
             "evidence": ["test_report.json", "review.md", "e2e.log"]},
            {"id": "b", "state": "IMPLEMENTED"},
            {"id": "c", "state": "BANANA"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "states.json"
            f.write_text(json.dumps(payload), encoding="utf-8")
            r = self._run("check-file", "--file", str(f))
        self.assertEqual(r.returncode, 2)
        out = json.loads(r.stdout)
        self.assertFalse(out["ok"])
        ids = {p["id"] for p in out["problems"]}
        self.assertEqual(ids, {"c"})
        # a 通过全部检查；b 仅 STATE_INVALID 缺席（IMPLEMENTED 合法）
        self.assertEqual(out["checked"], 3)


if __name__ == "__main__":
    unittest.main()
