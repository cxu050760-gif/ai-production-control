"""B1-candidate V07-INTEGRATE-2 integration and attack tests.

Every attack reaches the real ``strategic_integration.evaluate``. Boundary mocks
only inject malformed upstream contract outputs; they never fabricate a successful
integration result. The clean path must still reach advisory_reuse.
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
        self.assertIsInstance(obs.raw, dict, obs)
        self.assertEqual(obs.raw.get("outcome"), "advisory_reject", obs)
        self.assertNotIn(str(obs.final_status).upper(), {"PASS", "PROMOTED", "CROWNED", "REUSE"})
        self.assertTrue(obs.advisory_only, obs)
        self.assertTrue(obs.non_authority, obs)
        self.assertFalse(obs.mutated_external_state, obs)

    def assert_invalid_intermediate(self, obs, stage):
        self.assert_rejected_not_authorized(obs)
        self.assertIs(obs.raw.get("valid"), False, obs)
        self.assertEqual(obs.raw.get("stage"), stage, obs)

    def test_normal_brain_c_reuse_path(self):
        obs = self.invoke(fx.integration_case())
        self.assertEqual(obs.brain.get("schema"), "v0.7-strategic-brain-proposal")
        self.assertEqual([x["kind"] for x in obs.correction["corrections"]], ["none"])
        self.assertEqual(obs.reuse.get("decision"), "reuse")
        self.assertEqual(obs.final_status, "advisory_reuse")
        self.assertNotIn(str(obs.final_status).upper(), {"PASS", "PROMOTED", "CROWNED"})

    def test_legacy_dual_fact_packets_are_not_silently_fused(self):
        """REWORK-C: the adapter must not reconcile two competing fact sources."""
        conflicts = []

        case = fx.legacy_dual_fact_case()
        case["reuse_input"]["current"]["milestone"] = "V0.8"
        conflicts.append(("milestone", case))

        case = fx.legacy_dual_fact_case()
        case["frozen_route"]["scope_allowlist"] = ["strategic-brain"]
        case["reuse_input"]["current"]["scope_allowlist"] = ["strategic-reuse"]
        conflicts.append(("scope_allowlist", case))

        case = fx.legacy_dual_fact_case()
        case["frozen_route"]["acceptance_requirements"] = ["deterministic"]
        case["reuse_input"]["current"]["acceptance_requirements"] = ["fail-closed"]
        conflicts.append(("acceptance_requirements", case))

        case = fx.legacy_dual_fact_case()
        case["frozen_route"]["authority_constraints"] = ["write verdict"]
        case["reuse_input"]["current"]["authority_constraints"] = ["promotion"]
        conflicts.append(("authority_constraints", case))

        for name, conflicted in conflicts:
            with self.subTest(conflict=name):
                obs = self.invoke(conflicted)
                self.assert_rejected_not_authorized(obs)
                self.assertNotEqual(obs.final_status, "advisory_reuse", obs)

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
            ("stale", lambda c: c["reuse_material"].update(claimed_milestone="V0.6"), "milestone_incompatible"),
            ("scope", lambda c: c["reuse_material"].update(requested_scope=["provider-adapter"]), "scope_incompatible"),
            ("acceptance", lambda c: c["reuse_material"].update(promises=["deterministic"]), "acceptance_unsatisfied"),
            ("role", lambda c: c["reuse_material"].update(strategy="Builder self-review and assign verdict"), "role_separation_violation"),
            ("authority", lambda c: c["reuse_material"].update(strategy="promotion and crown milestone"), "authority_violation"),
        ]
        for name, mutate, expected in mutations:
            with self.subTest(case=name):
                case = fx.integration_case()
                mutate(case)
                obs = self.invoke(case)
                self.assertEqual(obs.reuse.get("decision"), "reject", obs)
                self.assertIn(expected, {x["kind"] for x in obs.reuse.get("reasons") or []})
                self.assert_rejected_not_authorized(obs)

    def test_authority_attack_tripwire_no_external_effects(self):
        blocked = RuntimeError("external mutation attempted")
        for text in fx.load_attack_matrix()["authority_attacks"]:
            with self.subTest(text=text):
                case = fx.integration_case()
                case["brain_input"] = fx.brain_input(text)
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
        bad_cases = [
            None,
            {},
            {"brain_input": None},
            {"brain_input": {"goal": "x" * 257}},
            {**fx.integration_case(), "frozen_facts": None},
            {**fx.integration_case(), "reuse_material": None},
        ]
        for case in bad_cases:
            with self.subTest(case=repr(case)[:80]):
                try:
                    obs = adapter.invoke_case(copy.deepcopy(case))
                except Exception as exc:
                    self.fail(f"integration raised instead of returning fail-closed result: {exc!r}")
                self.assert_rejected_not_authorized(obs)

    def test_malformed_brain_outputs_fail_at_brain_boundary(self):
        candidate = adapter.integration
        clean = candidate.build_proposal(fx.brain_input())

        malformed = []
        value = copy.deepcopy(clean)
        value.pop("goal", None)
        value.pop("proposal_id", None)
        malformed.append(("missing_required_fields", value))

        value = copy.deepcopy(clean)
        value["plan"] = [{"step": 1, "action": "plan_item"}]
        malformed.append(("malformed_plan_item", value))

        value = copy.deepcopy(clean)
        value["origin"] = "builder"
        malformed.append(("wrong_fixed_origin", value))

        value = copy.deepcopy(clean)
        value["plan"] = [{"step": 1, "action": "promote", "detail": "internally illegal action"}]
        malformed.append(("valid_shell_illegal_interior", value))

        for name, injected in malformed:
            with self.subTest(case=name), \
                 mock.patch.object(candidate, "build_proposal", return_value=injected), \
                 mock.patch.object(candidate, "evaluate_correction", wraps=candidate.evaluate_correction) as c_mock, \
                 mock.patch.object(candidate, "evaluate_reuse", wraps=candidate.evaluate_reuse) as reuse_mock:
                obs = self.invoke(fx.integration_case())
                self.assert_invalid_intermediate(obs, "strategic_brain")
                self.assertEqual(c_mock.call_count, 0, "malformed Brain reached C")
                self.assertEqual(reuse_mock.call_count, 0, "malformed Brain reached Reuse")

    def test_malformed_c_outputs_fail_closed_before_reuse(self):
        candidate = adapter.integration
        proposal = candidate.build_proposal(fx.brain_input())
        clean = candidate.evaluate_correction({"proposal": proposal, "frozen_route": fx.frozen_route()})

        malformed = []
        value = copy.deepcopy(clean)
        value["corrections"] = [{"kind": "none"}]
        malformed.append(("none_missing_severity_and_detail", value))

        value = copy.deepcopy(clean)
        value["corrections"][0].pop("severity", None)
        malformed.append(("missing_severity", value))

        value = copy.deepcopy(clean)
        value["corrections"][0]["severity"] = "critical"
        malformed.append(("wrong_severity", value))

        value = copy.deepcopy(clean)
        value["corrections"][0].pop("detail", None)
        malformed.append(("missing_detail", value))

        value = copy.deepcopy(clean)
        value["corrections"][0]["detail"] = 7
        malformed.append(("invalid_detail", value))

        value = copy.deepcopy(clean)
        value["corrections"][0]["kind"] = "unknown_kind"
        malformed.append(("unknown_kind", value))

        value = copy.deepcopy(clean)
        value.pop("detection_note", None)
        malformed.append(("missing_detection_note", value))

        value = copy.deepcopy(clean)
        value["detection_note"] = None
        malformed.append(("invalid_detection_note", value))

        for name, injected in malformed:
            with self.subTest(case=name), \
                 mock.patch.object(candidate, "evaluate_correction", return_value=injected), \
                 mock.patch.object(candidate, "evaluate_reuse", wraps=candidate.evaluate_reuse) as reuse_mock:
                obs = self.invoke(fx.integration_case())
                self.assert_invalid_intermediate(obs, "strategic_correction")
                self.assertIsNone(obs.reuse, obs)
                self.assertEqual(reuse_mock.call_count, 0, "malformed C reached Strategic Reuse")

    def test_malformed_reuse_outputs_never_become_advisory_reuse(self):
        candidate = adapter.integration
        clean = candidate.evaluate_reuse({"material": fx.reusable_material(), "current": fx.reuse_current()})

        malformed = []
        value = copy.deepcopy(clean)
        value.pop("decision_detail", None)
        malformed.append(("missing_decision_detail", value))

        value = copy.deepcopy(clean)
        value.pop("reasons", None)
        malformed.append(("missing_reasons", value))

        value = copy.deepcopy(clean)
        value["reasons"] = ["not-an-object"]
        malformed.append(("malformed_reason", value))

        value = copy.deepcopy(clean)
        value["reasons"][0].pop("severity", None)
        malformed.append(("missing_reason_severity", value))

        value = copy.deepcopy(clean)
        value["reasons"][0]["severity"] = "critical"
        malformed.append(("wrong_reason_severity", value))

        value = copy.deepcopy(clean)
        value["reasons"][0].pop("detail", None)
        malformed.append(("missing_reason_detail", value))

        value = copy.deepcopy(clean)
        value["reasons"][0]["detail"] = None
        malformed.append(("invalid_reason_detail", value))

        value = copy.deepcopy(clean)
        value["reasons"][0]["kind"] = "unknown_reason"
        malformed.append(("unknown_reason_kind", value))

        value = copy.deepcopy(clean)
        value.pop("detection_note", None)
        malformed.append(("missing_detection_note", value))

        value = copy.deepcopy(clean)
        value["detection_note"] = 0
        malformed.append(("invalid_detection_note", value))

        for name, injected in malformed:
            with self.subTest(case=name), mock.patch.object(candidate, "evaluate_reuse", return_value=injected):
                obs = self.invoke(fx.integration_case())
                self.assert_invalid_intermediate(obs, "strategic_reuse")
                self.assertNotEqual(obs.final_status, "advisory_reuse", obs)

    def test_invalid_intermediate_results_and_exceptions_fail_closed(self):
        candidate = adapter.integration
        cases = [
            ("brain_none", "build_proposal", None, "strategic_brain", False),
            ("brain_raise", "build_proposal", RuntimeError("boom"), "strategic_brain", True),
            ("correction_none", "evaluate_correction", None, "strategic_correction", False),
            ("correction_raise", "evaluate_correction", RuntimeError("boom"), "strategic_correction", True),
            ("reuse_none", "evaluate_reuse", None, "strategic_reuse", False),
            ("reuse_raise", "evaluate_reuse", RuntimeError("boom"), "strategic_reuse", True),
        ]
        for name, target, injected, stage, raises in cases:
            with self.subTest(case=name):
                patcher = (mock.patch.object(candidate, target, side_effect=injected)
                           if raises else mock.patch.object(candidate, target, return_value=injected))
                with patcher:
                    obs = self.invoke(fx.integration_case())
                self.assert_invalid_intermediate(obs, stage)

    def test_determinism_same_input_same_raw_result(self):
        case = fx.integration_case()
        results = [adapter.invoke_case(copy.deepcopy(case)).raw for _ in range(8)]
        self.assertTrue(all(x == results[0] for x in results[1:]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
