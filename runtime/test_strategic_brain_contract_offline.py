"""Offline deterministic tests for the V0.7 Strategic Brain contract slice (REWORK v2).

Proves (per task acceptance + verdict NEXT_ACTION):
- a valid structured proposal is produced for valid input (exit-code-0 passing case);
- controller-owned state / authority actions are NOT executed by the component;
- rejection is deterministic and machine-parseable for invalid/bounded input;
- identical input -> identical proposal_id (deterministic);
- REWORK v2: non-object context fails closed (context=[], "", 0, False, str),
  oversized context strings / keys / integers and non-finite floats are rejected,
  canonical serialization failures become structured rejections.
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

    def test_absent_context_defaults_to_empty_dict(self):
        out = sb.build_proposal({"goal": "g"})
        self.assertEqual(out["schema"], "v0.7-strategic-brain-proposal")
        self.assertIs(out["non_authority"], True)


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
        if out.get("valid") is False:
            return  # deterministic rejection is acceptable
        for p in out["plan"]:
            self.assertTrue(sb.contains_authority_lexicon(p["detail"]) is False
                            or p["action"] == "plan_item", p)

    def test_component_has_no_state_mutation_mechanism(self):
        out = sb.build_proposal(VALID)
        self.assertIs(out["non_authority"], True)
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

    def test_rejection_is_deterministic_and_side_effect_free(self):
        o1 = sb.build_proposal({"goal": "g", "constraints": [{"kind": "nope", "value": "v"}]})
        o2 = sb.build_proposal({"goal": "g", "constraints": [{"kind": "nope", "value": "v"}]})
        self.assertEqual(o1, o2)
        self.assertIs(o1["valid"], False)


class TestContextFailClosed(unittest.TestCase):
    """REWORK v2: every non-object context is rejected; falsey values are not coerced."""

    def test_non_object_context_rejected_fail_closed(self):
        for bad in ([], "", 0, False, "ctx", 42, 3.5, ("t",)):
            out = sb.build_proposal({"goal": "g", "context": bad})
            self.assertIs(out["valid"], False, f"context={bad!r} must fail closed")
            self.assertEqual(out["error"], "CONTEXT_NOT_OBJECT")

    def test_oversized_context_string_rejected(self):
        out = sb.build_proposal({"goal": "g", "context": {"k": "x" * (sb.MAX_CTX_STR_LEN + 1)}})
        self.assertIs(out["valid"], False)
        self.assertEqual(out["error"], "CONTEXT_STRING_TOO_LONG")

    def test_oversized_context_key_rejected(self):
        out = sb.build_proposal({"goal": "g", "context": {"k" * (sb.MAX_CTX_KEY_LEN + 1): "v"}})
        self.assertIs(out["valid"], False)
        self.assertEqual(out["error"], "CONTEXT_KEY_INVALID")

    def test_oversized_integer_rejected(self):
        positive = sb.build_proposal({"goal": "g", "context": {"n": sb.MAX_INT_MAG + 1}})
        self.assertIs(positive["valid"], False)
        self.assertEqual(positive["error"], "CONTEXT_INT_OVERFLOW")
        negative = sb.build_proposal({"goal": "g", "context": {"n": -(sb.MAX_INT_MAG) - 1}})
        self.assertIs(negative["valid"], False)
        self.assertEqual(negative["error"], "CONTEXT_INT_OVERFLOW")

    def test_non_finite_float_rejected(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            out = sb.build_proposal({"goal": "g", "context": {"f": bad}})
            self.assertIs(out["valid"], False, f"float={bad!r} must be rejected")
            self.assertEqual(out["error"], "CONTEXT_FLOAT_NOT_FINITE",
                             f"bad float {bad!r} must use CONTEXT_FLOAT_NOT_FINITE, got {out}")

    def test_serialized_size_bound_rejected(self):
        ctx = {f"k{i}": "v" * (sb.MAX_CTX_STR_LEN) for i in range(sb.MAX_CTX_KEYS)}
        out = sb.build_proposal({"goal": "g", "context": ctx})
        self.assertIs(out["valid"], False)
        self.assertEqual(out["error"], "CONTEXT_SERIALIZED_TOO_LARGE")

    def test_bool_none_int_finite_float_allowed(self):
        out = sb.build_proposal({"goal": "g", "context": {
            "flag": True, "opt": None, "i": 10 ** 18, "neg": -10 ** 18, "f": 1.5, "s": "x"}})
        self.assertEqual(out["schema"], "v0.7-strategic-brain-proposal", out)
        self.assertIs(out["non_authority"], True)


if __name__ == "__main__":
    unittest.main(verbosity=2)