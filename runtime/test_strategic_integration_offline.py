"""B1 core tests for V07-INTEGRATE-2 strict intermediate-result validation."""
import copy
import unittest
from unittest import mock

import strategic_integration as integration


def clean_input():
    return {
        "brain_input": {
            "goal": "compose current contracts",
            "constraints": [{"kind": "must_have", "value": "core-wiring"}],
            "context": {"milestone": "V0.7"},
        },
        "frozen_facts": {
            "current_milestone": "V0.7",
            "allowed_milestones": ["V0.7"],
            "premature_milestones": ["V0.8"],
            "controller_owned_actions": ["promote"],
            "scope_allowlist": ["core-wiring"],
            "acceptance_requirements": ["tests-pass"],
            "authority_constraints": ["promote"],
            "role_separation_terms": ["builder self review"],
        },
        "reuse_material": {
            "id": "thin-wiring",
            "strategy": "reuse thin wiring helper",
            "claimed_milestone": "V0.7",
            "requested_scope": ["core-wiring"],
            "promises": ["tests-pass"],
        },
    }


def clean_proposal():
    return integration.build_proposal(copy.deepcopy(clean_input()["brain_input"]))


def clean_correction():
    data = clean_input()
    frozen = data["frozen_facts"]
    route = {key: copy.deepcopy(frozen[key]) for key in (
        "current_milestone", "allowed_milestones", "premature_milestones",
        "controller_owned_actions",
    )}
    return integration.evaluate_correction({"proposal": clean_proposal(), "frozen_route": route})


def clean_reuse():
    data = clean_input()
    frozen = data["frozen_facts"]
    current = {"milestone": frozen["current_milestone"]}
    for key in (
        "allowed_milestones", "scope_allowlist", "acceptance_requirements",
        "authority_constraints", "role_separation_terms",
    ):
        current[key] = copy.deepcopy(frozen[key])
    return integration.evaluate_reuse({"material": copy.deepcopy(data["reuse_material"]),
                                       "current": current})


class TestStrategicIntegration(unittest.TestCase):
    def assert_fail_closed(self, out, stage, error):
        self.assertFalse(out["valid"], out)
        self.assertEqual(out["outcome"], "advisory_reject", out)
        self.assertEqual(out["stage"], stage, out)
        self.assertEqual(out["error"], error, out)
        self.assertTrue(out["advisory_only"], out)
        self.assertTrue(out["non_authority"], out)
        self.assertFalse(out["mutated_external_state"], out)
        self.assertNotEqual(out["outcome"], "advisory_reuse", out)

    def test_clean_path_reaches_reuse(self):
        out = integration.evaluate(clean_input())
        self.assertTrue(out["valid"])
        self.assertEqual(out["stage"], "complete")
        self.assertEqual(out["outcome"], "advisory_reuse")
        self.assertEqual(out["reuse"]["decision"], "reuse")
        self.assertTrue(out["advisory_only"])
        self.assertTrue(out["non_authority"])
        self.assertFalse(out["mutated_external_state"])

    def test_malformed_brain_missing_required_field_fails_closed(self):
        malformed = clean_proposal()
        malformed.pop("proposal_id")
        with mock.patch.object(integration, "build_proposal", return_value=malformed):
            out = integration.evaluate(clean_input())
        self.assert_fail_closed(out, "strategic_brain", "BRAIN_RESULT_UNSAFE")

    def test_malformed_brain_plan_item_fails_closed(self):
        malformed = clean_proposal()
        malformed["plan"][0] = {"step": 1, "action": "plan_item"}
        with mock.patch.object(integration, "build_proposal", return_value=malformed):
            out = integration.evaluate(clean_input())
        self.assert_fail_closed(out, "strategic_brain", "BRAIN_RESULT_UNSAFE")

    def test_malformed_c_none_missing_severity_detail_fails_closed(self):
        malformed = clean_correction()
        malformed["corrections"] = [{"kind": "none"}]
        with mock.patch.object(integration, "evaluate_correction", return_value=malformed), \
             mock.patch.object(integration, "evaluate_reuse") as reuse_mock:
            out = integration.evaluate(clean_input())
        self.assert_fail_closed(out, "strategic_correction", "CORRECTION_RESULT_UNSAFE")
        reuse_mock.assert_not_called()

    def test_malformed_c_unknown_kind_fails_closed(self):
        malformed = clean_correction()
        malformed["corrections"] = [{
            "kind": "unknown", "severity": "advisory", "detail": "looks safe",
        }]
        with mock.patch.object(integration, "evaluate_correction", return_value=malformed):
            out = integration.evaluate(clean_input())
        self.assert_fail_closed(out, "strategic_correction", "CORRECTION_RESULT_UNSAFE")

    def test_malformed_c_never_executes_reuse(self):
        malformed = clean_correction()
        malformed.pop("detection_note")
        with mock.patch.object(integration, "evaluate_correction", return_value=malformed), \
             mock.patch.object(integration, "evaluate_reuse",
                               side_effect=AssertionError("Reuse must not execute")) as reuse_mock:
            out = integration.evaluate(clean_input())
        self.assert_fail_closed(out, "strategic_correction", "CORRECTION_RESULT_UNSAFE")
        reuse_mock.assert_not_called()

    def test_malformed_reuse_decision_reuse_missing_required_fields_fails_closed(self):
        malformed = {
            "schema": "v0.7-strategic-reuse-advisory",
            "decision": "reuse",
            "advisory_only": True,
            "non_authority": True,
            "mutated_external_state": False,
        }
        with mock.patch.object(integration, "evaluate_reuse", return_value=malformed):
            out = integration.evaluate(clean_input())
        self.assert_fail_closed(out, "strategic_reuse", "REUSE_RESULT_UNSAFE")

    def test_malformed_reuse_reason_fails_closed(self):
        malformed = clean_reuse()
        malformed["reasons"] = [{"kind": "none", "severity": "advisory"}]
        with mock.patch.object(integration, "evaluate_reuse", return_value=malformed):
            out = integration.evaluate(clean_input())
        self.assert_fail_closed(out, "strategic_reuse", "REUSE_RESULT_UNSAFE")

    def test_malformed_reuse_unknown_reason_kind_fails_closed(self):
        malformed = clean_reuse()
        malformed["reasons"] = [{
            "kind": "unknown", "severity": "advisory", "detail": "looks safe",
        }]
        with mock.patch.object(integration, "evaluate_reuse", return_value=malformed):
            out = integration.evaluate(clean_input())
        self.assert_fail_closed(out, "strategic_reuse", "REUSE_RESULT_UNSAFE")

    def test_malformed_intermediate_never_advisory_reuse(self):
        malformed_brain = clean_proposal(); malformed_brain["origin"] = "other"
        malformed_c = clean_correction(); malformed_c["corrections"][0]["severity"] = "info"
        malformed_reuse = clean_reuse(); malformed_reuse["reasons"] = []
        cases = (
            ("build_proposal", malformed_brain, "strategic_brain", "BRAIN_RESULT_UNSAFE"),
            ("evaluate_correction", malformed_c, "strategic_correction", "CORRECTION_RESULT_UNSAFE"),
            ("evaluate_reuse", malformed_reuse, "strategic_reuse", "REUSE_RESULT_UNSAFE"),
        )
        for target, value, stage, error in cases:
            with self.subTest(target=target), mock.patch.object(integration, target, return_value=value):
                out = integration.evaluate(clean_input())
            self.assert_fail_closed(out, stage, error)

    def test_correction_short_circuits_reuse(self):
        data = clean_input()
        data["brain_input"]["constraints"] = [
            {"kind": "must_have", "value": "provider adapter"}
        ]
        out = integration.evaluate(data)
        self.assertTrue(out["valid"])
        self.assertEqual(out["stage"], "strategic_correction")
        self.assertEqual(out["outcome"], "advisory_reject")
        self.assertIsNone(out["reuse"])
        self.assertTrue(any(
            item["kind"] == "scope_drift" for item in out["correction"]["corrections"]
        ))

    def test_reuse_rejection_is_preserved(self):
        data = clean_input()
        data["reuse_material"]["claimed_milestone"] = "V0.8"
        out = integration.evaluate(data)
        self.assertTrue(out["valid"])
        self.assertEqual(out["stage"], "complete")
        self.assertEqual(out["outcome"], "advisory_reject")
        self.assertEqual(out["reuse"]["decision"], "reject")
        self.assertTrue(any(
            item["kind"] == "milestone_incompatible" for item in out["reuse"]["reasons"]
        ))

    def test_malformed_input_fails_closed(self):
        for bad in (None, [], "", 0, False):
            with self.subTest(value=bad):
                out = integration.evaluate(bad)
                self.assert_fail_closed(out, "integration", "INPUT_NOT_OBJECT")

    def test_deterministic(self):
        data = clean_input()
        self.assertEqual(integration.evaluate(copy.deepcopy(data)),
                         integration.evaluate(copy.deepcopy(data)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
