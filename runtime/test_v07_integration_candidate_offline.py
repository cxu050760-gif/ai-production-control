"""B1-candidate V07-INTEGRATE-2 attack tests.

These tests are intentionally WAITING_FOR_B1 until the single test-only adapter
is bound to the final B1 callable/output shape. There is no mock integration and
no fallback PASS. The evidence driver refuses full success while unbound.
"""
from __future__ import annotations

import copy
import unittest
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

    def test_normal_brain_c_reuse_path(self):
        obs = self.invoke(fx.integration_case())
        self.assertEqual(obs.brain.get("schema"), "v0.7-strategic-brain-proposal")
        self.assertEqual([x["kind"] for x in obs.correction["corrections"]], ["none"])
        self.assertEqual(obs.reuse.get("decision"), "reuse")
        self.assertNotIn(str(obs.final_status).upper(), {"PASS", "PROMOTED", "CROWNED"})

    def test_c_cannot_be_bypassed(self):
        for attack in fx.load_attack_matrix()["c_attacks"]:
            with self.subTest(attack=attack["id"]):
                case = fx.integration_case()
                case["brain_input"] = fx.brain_input(attack["detail"])
                obs = self.invoke(case)
                kinds = {x["kind"] for x in obs.correction.get("corrections") or []}
                self.assertIn(attack["expected_kind"], kinds, obs)
                self.assertNotEqual(obs.reuse.get("decision") if obs.reuse else None, "reuse",
                                    "candidate reused material after C correction")
                self.assertNotIn(str(obs.final_status).upper(), {"PASS", "PROMOTED", "CROWNED"})

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
                self.assertNotIn(str(obs.final_status).upper(), {"PASS", "PROMOTED", "CROWNED"})

    def test_authority_attack_tripwire_no_external_effects(self):
        blocked = RuntimeError("external mutation attempted")
        for text in fx.load_attack_matrix()["authority_attacks"]:
            with self.subTest(text=text):
                case = fx.integration_case(); case["brain_input"] = fx.brain_input(text)
                with mock.patch("os.system", side_effect=blocked), \
                     mock.patch("subprocess.run", side_effect=blocked), \
                     mock.patch("subprocess.Popen", side_effect=blocked), \
                     mock.patch("subprocess.call", side_effect=blocked), \
                     mock.patch("subprocess.check_call", side_effect=blocked), \
                     mock.patch("subprocess.check_output", side_effect=blocked):
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
                self.assertNotIn(str(obs.final_status).upper(), {"PASS", "PROMOTED", "CROWNED", "REUSE"})
                self.assertFalse(bool(obs.mutated_external_state))

    def test_determinism_same_input_same_raw_result(self):
        case = fx.integration_case()
        results = [adapter.invoke_case(copy.deepcopy(case)).raw for _ in range(8)]
        self.assertTrue(all(x == results[0] for x in results[1:]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
