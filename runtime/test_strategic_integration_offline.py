"""Small B1 smoke tests for V07-INTEGRATE-2 core composition."""
import copy
import unittest

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


class TestStrategicIntegration(unittest.TestCase):
    def test_clean_path_reaches_reuse(self):
        out = integration.evaluate(clean_input())
        self.assertTrue(out["valid"])
        self.assertEqual(out["stage"], "complete")
        self.assertEqual(out["outcome"], "advisory_reuse")
        self.assertEqual(out["reuse"]["decision"], "reuse")
        self.assertTrue(out["advisory_only"])
        self.assertTrue(out["non_authority"])
        self.assertFalse(out["mutated_external_state"])

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
                self.assertFalse(out["valid"])
                self.assertEqual(out["outcome"], "advisory_reject")
                self.assertTrue(out["advisory_only"])
                self.assertTrue(out["non_authority"])
                self.assertFalse(out["mutated_external_state"])

    def test_deterministic(self):
        data = clean_input()
        self.assertEqual(integration.evaluate(copy.deepcopy(data)),
                         integration.evaluate(copy.deepcopy(data)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
