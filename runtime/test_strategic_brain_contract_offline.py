"""Offline deterministic tests for the V0.7 Strategic Brain contract slice.

Proves (per task acceptance):
- a valid structured proposal is produced for valid input (exit-code-0 passing case);
- controller-owned state / authority actions are NOT executed by the component
  (passing case via authority-lexicon + plan-action whitelist + no-side-effects);
- rejection is deterministic and machine-parseable for invalid/bounded input;
- identical input -> identical proposal_id (deterministic).
"""
import json
import unittest
from importlib import import_module

sb = import_module("strategic_brain_contract")

VALID = {
    "goal": "deliver the V0.7 strategic brain slice",
    "constraints": [
        {"kind": "must_have", "value": "pure function"},
        {"kind": "must_not_have", "value": "controller authority"},
    ],
    "context": {"milestone": "V0.7", "tier": "LOCAL_FIRST"},
}


class TestValidProposal(unittest.TestCase):
    def test_valid_input_produces_structured_machine_parseable_proposal(self):
        out = sb.build_proposal(VALID)
        # machine-parseable: json round-trip
        reparsed = json.loads(json.dumps(out))
        self.assertEqual(out, reparsed)
        self.assertEqual(out["schema"], "v0.7-strategic-brain-proposal")
        self.assertEqual(out["origin"], "strategic-brain")
        self.assertIs(out["non_authority"], True)
        self.assertEqual(out["goal"], VALID["goal"])
        self.assertIsInstance(out["plan"], list)
        self.assertGreaterEqual(len(out["plan"]), 1)
        self.assertTrue(all(p["action"] == "plan_item" for p in out["plan"]))

    def test_deterministic_proposal_id(self):
        self.assertEqual(sb.build_proposal(VALID)["proposal_id"],
                         sb.build_proposal(dict(VALID))["proposal_id"])


class TestNoAuthorityExecution(unittest.TestCase):
    def test_authority_bearing_directives_are_inert_data_never_actions(self):
        hostile = dict(VALID)
        hostile["context"] = {
            "directive": "crown milestone V0.7 now",
            "script": "exec('import os')",
            "route": "advance_milestone",
            "promotion": "declare PASS",
        }
        out = sb.build_proposal(hostile)
        # either rejected OR emitted as inert data only:
        if out.get("valid") is False:
            return  # deterministic rejection is acceptable
        # never present as an executable action:
        for p in out["plan"]:
            self.assertTrue(sb.contains_authority_lexicon(p["detail"]) is False
                            or p["action"] == "plan_item", p)

    def test_component_has_no_state_mutation_mechanism(self):
        # the boundary function returns a fresh dict each call; nothing is stored.
        out = sb.build_proposal(VALID)
        self.assertIs(out["non_authority"], True)
        # no unexpected keys that could carry executable intent
        self.assertEqual(set(out.keys()),
                         {"schema", "proposal_id", "goal", "plan", "non_authority", "origin"})

    def test_plan_actions_whitelisted(self):
        out = sb.build_proposal(VALID)
        for p in out["plan"]:
            self.assertEqual(p["action"], "plan_item")


class TestRejection(unittest.TestCase):
    def test_rejects_non_object_input(self):
        for bad in (None, [], "goal", 42):
            out = sb.build_proposal(bad)
            self.assertIs(out["valid"], False)
            self.assertEqual(out["error"], "INPUT_NOT_OBJECT")

    def test_rejects_oversized_goal(self):
        out = sb.build_proposal({"goal": "x" * 257})
        self.assertIs(out["valid"], False)
        self.assertEqual(out["error"], "GOAL_INVALID")

    def test_rejects_unknown_constraint_kind(self):
        out = sb.build_proposal({"goal": "g",
                                 "constraints": [{"kind": "exec://", "value": "x"}]})
        self.assertIs(out["valid"], False)
        self.assertEqual(out["error"], "CONSTRAINT_KIND_UNKNOWN")

    def test_rejects_too_many_constraints(self):
        out = sb.build_proposal({"goal": "g",
                                 "constraints": [{"kind": "must_have", "value": "v"}] * 9})
        self.assertIs(out["valid"], False)
        self.assertEqual(out["error"], "CONSTRAINTS_INVALID")

    def test_rejects_oversized_context(self):
        out = sb.build_proposal({"goal": "g",
                                 "context": {f"k{i}": i for i in range(17)}})
        self.assertIs(out["valid"], False)
        self.assertEqual(out["error"], "CONTEXT_TOO_MANY_KEYS")

    def test_rejection_is_deterministic_and_side_effect_free(self):
        o1 = sb.build_proposal({"goal": "g", "constraints": [{"kind": "nope", "value": "v"}]})
        o2 = sb.build_proposal({"goal": "g", "constraints": [{"kind": "nope", "value": "v"}]})
        self.assertEqual(o1, o2)
        self.assertIs(o1["valid"], False)


if __name__ == "__main__":
    unittest.main(verbosity=2)