"""B1-candidate V07-INTEGRATE-2 integration and attack tests.

The single test-only adapter is bound to B1's landed production callable. Tests
exercise the real integration; malformed-intermediate mocks inject failures only
at contract boundaries and never fabricate a successful result.
"""
from __future__ import annotations

import copy
import unittest
from pathlib import Path
from unittest import mock

import v07_integration_candidate_adapter as adapter
import v07_integration_verify_support as fx


@unittest.skipUnless(adapter.is_bound(), "WAITING_FOR_B1: candidate adapter not bound")
class CandidateIntegration(unittest.TestCase):
    def invoke(self, case):
        before = copy.deepcopy(case)
        obs = adapter.invoke_case(case)
        self.assertEqual(case, before, "integration mutated its supplied input")
        self.assertIsNotNone(obs.raw)
        self.assertTrue(obs.advisory_only, obs)
        self.assertTrue(obs.non_authority, obs)
        self.assertFalse(obs.mutated_external_state, obs)
        return obs

    def assert_rejected_not_authorized(self, obs):
        self.assertEqual(obs.raw.get("outcome"), "advisory_reject", obs)
        self.assertNotIn(str(obs.final_status).upper(), {"PASS", "PROMOTED", "CROWNED", "REUSE"})
        self.assertTrue(obs.advisory_only, obs)
        self.assertTrue(obs.non_authority, obs)
        self.assertFalse(obs.mutated_external_state, obs)

    def test_normal_brain_c_reuse_path(self):
        obs = self.invoke(fx.integration_case())
        self.assertEqual(obs.brain.get("schema"), "v0.7-strategic-brain-proposal")
        self.assertEqual([x["kind"] for x in obs.correction["corrections"]], ["none"])
        self.assertEqual(obs.reuse.get("decision"), "reuse")
        self.assertEqual(obs.final_status, "advisory_reuse")
        self.assertNotIn(str(obs.final_status).upper(), {"PASS", "PROMOTED", "CROWNED"})

    def test_c_cannot_be_bypassed(self):
        for attack in fx.load_attack_matrix()["c_attacks"]:
            with self.subTest(attack=attack["id"]):
                case = fx.integration_case()
                case["brain_input"] = fx.brain_input(attack["detail"])
                obs = self.invoke(case)
                kinds = {x["kind"] for x in obs.correction.get("corrections") or []}
                self.assertIn(attack["expected_kind"], kinds, obs)
                self.assertIsNone(obs.reuse, "candidate reached Reuse after C correction")
                self.assert_rejected_not_authorized(obs)

    def test_reuse_rejects_incompatible_history(self):
        mutations = [
            ("stale", lambda c: c["reuse_input"]["material"].update(claimed_milestone="V0.6"), "milestone_incompatible"),
            ("scope", lambda c: c["reuse_input"]["material"].update(requested_scope=["provider-adapter"]), "scope_incompatible"),
            ("acceptance", lambda c: c["reuse_input"]["material"].update(promises=["deterministic"]), "acceptance_unsatisfied"),
            ("role", lambda c: c["reuse_input"]["material"].update(strategy="Builder self-review and assign verdict"), "role_separation_violation"),
            ("authority", lambda c: c["reuse_input"]["material"].update(strategy="promotion and crown milestone"), "authority_violation"),
        ]
        for name, mutate, expected in mutations:
            with self.subTest(case=name):
                case = fx.integration_case(); mutate(case)
                obs = self.invoke(case)
                self.assertEqual(obs.reuse.get("decision"), "reject", obs)
                self.assertIn(expected, {x["kind"] for x in obs.reuse.get("reasons") or []})
                self.assert_rejected_not_authorized(obs)

    def test_authority_attack_tripwire_no_external_effects(self):
        blocked = RuntimeError("external mutation attempted")
        for text in fx.load_attack_matrix()["authority_attacks"]:
            with self.subTest(text=text):
                case = fx.integration_case(); case["brain_input"] = fx.brain_input(text)
                with mock.patch("os.system", side_effect=blocked), \
                     mock.patch("os.remove", side_effect=blocked), \
                     mock.patch("os.unlink", side_effect=blocked), \
                     mock.patch("os.rename", side_effect=blocked), \
                     mock.patch("os.replace", side_effect=blocked), \
                     mock.patch("subprocess.run", side_effect=blocked), \
                     mock.patch("subprocess.Popen", side_effect=blocked), \
                     mock.patch("subprocess.call", side_effect=blocked), \
                     mock.patch("subprocess.check_call", side_effect=blocked), \
                     mock.patch("subprocess.check_output", side_effect=blocked), \
                     mock.patch.object(Path, "write_text", side_effect=blocked), \
                     mock.patch.object(Path, "write_bytes", side_effect=blocked), \
                     mock.patch.object(Path, "unlink", side_effect=blocked):
                    obs = self.invoke(case)
                self.assertFalse(obs.mutated_external_state)
                self.assertNotIn(str(obs.final_status).upper(), {"PASS", "PROMOTED", "CROWNED"})

    def test_fail_closed_bad_inputs_never_escape_as_pass(self):
        bad_cases = [None, {}, {"brain_input": None}, {"brain_input": {"goal": "x" * 257}},
                     {**fx.integration_case(), "frozen_route": None},
                     {**fx.integration_case(), "reuse_input": None}]
        for case in bad_cases:
            with self.subTest(case=repr(case)[:80]):
                try:
                    obs = adapter.invoke_case(copy.deepcopy(case))
                except Exception as exc:
                    self.fail(f"integration raised instead of returning fail-closed result: {exc!r}")
                self.assert_rejected_not_authorized(obs)

    def test_invalid_intermediate_results_and_exceptions_fail_closed(self):
        candidate = adapter.integration
        cases = [
            ("brain_none", "build_proposal", None, "strategic_brain", "BRAIN_RESULT_NOT_OBJECT", False),
            ("brain_raise", "build_proposal", RuntimeError("boom"), "strategic_brain", "BRAIN_UNEXPECTED_FAILURE", True),
            ("correction_none", "evaluate_correction", None, "strategic_correction", "CORRECTION_RESULT_UNSAFE", False),
            ("correction_raise", "evaluate_correction", RuntimeError("boom"), "strategic_correction", "CORRECTION_UNEXPECTED_FAILURE", True),
            ("reuse_none", "evaluate_reuse", None, "strategic_reuse", "REUSE_RESULT_UNSAFE", False),
            ("reuse_raise", "evaluate_reuse", RuntimeError("boom"), "strategic_reuse", "REUSE_UNEXPECTED_FAILURE", True),
        ]
        for name, target, injected, stage, error, raises in cases:
            with self.subTest(case=name):
                patcher = (mock.patch.object(candidate, target, side_effect=injected)
                           if raises else mock.patch.object(candidate, target, return_value=injected))
                with patcher:
                    obs = self.invoke(fx.integration_case())
                self.assertFalse(obs.raw.get("valid"), obs)
                self.assertEqual(obs.raw.get("stage"), stage, obs)
                self.assertEqual(obs.raw.get("error"), error, obs)
                self.assert_rejected_not_authorized(obs)

    def test_determinism_same_input_same_raw_result(self):
        case = fx.integration_case()
        results = [adapter.invoke_case(copy.deepcopy(case)).raw for _ in range(8)]
        self.assertTrue(all(x == results[0] for x in results[1:]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
