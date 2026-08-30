"""Offline deterministic tests for the V0.7 C strategic-correction contract.

Proves (per V07-C-CONTRACT-2 acceptance + REWORK v2 NEXT_ACTION):
- at least one passing no-correction case;
- at least one passing premature-milestone correction case (route-fact derived);
- at least one passing Builder-role-separation (self-review/verdict) correction case;
- promotion-assumption and scope-drift correction cases, including DIRECT
  "promote"-only detection without a second trigger such as "crown";
- fact-driven premature-milestone detection: an explicitly allowed milestone
  (e.g. allowed V0.8/V0.9) must NOT be corrected as premature, while a
  route-declared premature milestone outside the allowed set IS corrected;
- evaluate() NEVER raises: explicit null or non-list proposal.plan,
  allowed_milestones, premature_milestones, and controller_owned_actions are
  rejected with structured advisory rejection envelopes (REWORK v2);
- advisory-only: no mutation occurs (pure dict return; no IO/state);
- every result, INCLUDING every rejection envelope, carries advisory_only=true,
  non_authority=true, and mutated_external_state=false;
- deterministic, machine-parseable, fail-closed on invalid/bounded input.
"""
import json
import unittest
from importlib import import_module

c = import_module("strategic_correction")

ROUTE = {
    "current_milestone": "V0.7",
    "allowed_milestones": ["V0.7"],
    "premature_milestones": ["V0.8", "V0.9"],
    "controller_owned_actions": ["crown_milestone", "advance_milestone"],
}


def proposal(goal="deliver the C contract slice", plan=None, context=None):
    p = {"goal": goal,
         "plan": plan or [{"step": 1, "action": "plan_item", "detail": "assemble_proposal"}],
         "context": context if context is not None else {"milestone": "V0.7"}}
    return {"proposal": p, "frozen_route": ROUTE}


def kinds(out):
    return [cor["kind"] for cor in out["corrections"]]


def with_plan(goal, detail):
    return proposal(goal=goal, plan=[{"step": 1, "action": "plan_item", "detail": detail}])


def with_route(route, goal="deliver the C contract slice", plan=None, context=None):
    p = {"goal": goal,
         "plan": plan if plan is not None else [{"step": 1, "action": "plan_item", "detail": "assemble_proposal"}],
         "context": context if context is not None else {"milestone": "V0.7"}}
    return {"proposal": p, "frozen_route": route}


def assert_advisory_envelope(tc, out, error=None):
    tc.assertIs(out["advisory_only"], True)
    tc.assertIs(out["non_authority"], True)
    tc.assertIs(out["mutated_external_state"], False)
    tc.assertIs(out["valid"], False)
    if error is not None:
        tc.assertEqual(out["error"], error)


class TestNoCorrection(unittest.TestCase):
    def test_no_correction_case(self):
        out = c.evaluate(proposal())
        self.assertEqual(out["schema"], "v0.7-c-advisory")
        self.assertEqual(kinds(out), ["none"])
        # machine-parseable
        self.assertEqual(json.loads(json.dumps(out)), out)
        self.assertIs(out["advisory_only"], True)
        self.assertIs(out["non_authority"], True)
        self.assertIs(out["mutated_external_state"], False)

    def test_deterministic(self):
        self.assertEqual(c.evaluate(proposal()), c.evaluate(proposal()))


class TestFactDrivenPremature(unittest.TestCase):
    """REWORK NEXT_ACTION: detection derives from supplied frozen_route facts."""

    def test_allowed_v09_not_premature(self):
        route = {"current_milestone": "V0.9", "allowed_milestones": ["V0.9"],
                 "premature_milestones": [], "controller_owned_actions": []}
        out = c.evaluate(with_route(route, goal="finish V0.9 work"))
        self.assertNotIn("premature_milestone", kinds(out))
        self.assertIn("none", kinds(out))

    def test_allowed_v08_not_corrected_despite_premature_list(self):
        route = {"current_milestone": "V0.7", "allowed_milestones": ["V0.7", "V0.8"],
                 "premature_milestones": ["V0.8", "V0.9"], "controller_owned_actions": []}
        out = c.evaluate(with_route(route, goal="begin V0.8 approved work"))
        self.assertNotIn("premature_milestone", kinds(out))

    def test_unallowed_premature_still_corrected(self):
        route = {"current_milestone": "V0.7", "allowed_milestones": ["V0.7"],
                 "premature_milestones": ["V0.8"], "controller_owned_actions": []}
        out = c.evaluate(with_route(route, goal="begin V0.8 work now"))
        self.assertIn("premature_milestone", kinds(out))

    def test_premature_milestone_correction(self):
        out = c.evaluate(proposal(goal="begin V0.8 Brain work now"))
        self.assertIn("premature_milestone", kinds(out))


class TestPromotionDetection(unittest.TestCase):
    """REWORK NEXT_ACTION: direct promote detection without relying on crown."""

    def test_promote_only_detected(self):
        out = c.evaluate(proposal(goal="promote candidate now"))
        self.assertIn("promotion_assumption", kinds(out))

    def test_promotion_assumption_correction(self):
        out = c.evaluate(with_plan("deliver the C contract slice",
                                   "crown and promote V0.8 automatically"))
        self.assertIn("promotion_assumption", kinds(out))
        self.assertIn("premature_milestone", kinds(out))


class TestRoleAndScope(unittest.TestCase):
    def test_builder_self_review_correction(self):
        out = c.evaluate(proposal(goal="review and assign my own verdict on this slice"))
        self.assertIn("builder_role_self_review", kinds(out))

    def test_scope_drift_correction(self):
        out = c.evaluate(proposal(goal="add Strategic Reuse and C_URL integration"))
        self.assertIn("scope_drift", kinds(out))

    def test_controller_owned_action_usage_marked_scope_drift(self):
        out = c.evaluate(proposal(goal="use crown_milestone to advance"))
        self.assertIn("scope_drift", kinds(out))


class TestInvariants(unittest.TestCase):
    def test_all_results_advisory_only_and_no_mutation(self):
        for inp in (proposal(),
                    proposal(goal="begin V0.8 Brain work"),
                    proposal(goal="assign_verdict to myself"),
                    proposal(goal="promotion crown milestone"),
                    proposal(goal="promote candidate now"),
                    proposal(goal="Strategic Reuse implementation")):
            out = c.evaluate(inp)
            self.assertIs(out["advisory_only"], True)
            self.assertIs(out["non_authority"], True)
            self.assertIs(out["mutated_external_state"], False)
            self.assertEqual(set(out.keys()),
                             {"schema", "corrections", "advisory_only", "non_authority",
                              "mutated_external_state", "detection_note"})

    def test_rejection_envelopes_retain_advisory_flags(self):
        """REWORK NEXT_ACTION: rejection envelopes keep the all-results invariant."""
        for bad in (None, [], "x", 3, {},
                    {"proposal": {"goal": "g"}},
                    {"proposal": None, "frozen_route": ROUTE},
                    {"proposal": {"goal": "g"}, "frozen_route": []}):
            out = c.evaluate(bad)
            assert_advisory_envelope(self, out)


class TestFailClosed(unittest.TestCase):
    def test_non_object_input_rejected(self):
        for bad in (None, [], "x", 3):
            out = c.evaluate(bad)
            self.assertEqual(out["error"], "INPUT_NOT_OBJECT")

    def test_missing_proposal_or_route_rejected(self):
        self.assertEqual(c.evaluate({})["error"], "PROPOSAL_MISSING")
        self.assertEqual(c.evaluate({"proposal": {"goal": "g"}})["error"], "ROUTE_MISSING")

    def test_falsey_proposal_rejected(self):
        out = c.evaluate({"proposal": None, "frozen_route": ROUTE})
        self.assertEqual(out["error"], "PROPOSAL_MISSING")

    def test_non_object_route_rejected(self):
        out = c.evaluate({"proposal": {"goal": "g"}, "frozen_route": []})
        self.assertNotEqual(out.get("valid"), True)

    def test_oversized_plan_rejected(self):
        p = proposal(plan=[{"step": i, "action": "plan_item", "detail": "d"} for i in range(33)])
        out = c.evaluate(p)
        self.assertEqual(out["error"], "PROPOSAL_PLAN_INVALID")

    def test_bad_context_rejected(self):
        p = proposal(context={"k": "x" * (c.MAX_CTX_STR_LEN + 1)})
        out = c.evaluate(p)
        self.assertEqual(out["error"], "PROPOSAL_CONTEXT_CONTEXT_STRING_TOO_LONG")

    def test_rejection_deterministic(self):
        a = c.evaluate({"proposal": [], "frozen_route": ROUTE})
        b = c.evaluate({"proposal": [], "frozen_route": ROUTE})
        self.assertEqual(a, b)
        self.assertIs(a["valid"], False)


class TestExplicitNullAndNonList(unittest.TestCase):
    """REWORK v2: explicit null / non-list list-typed fields are structurally
    rejected with advisory envelopes; evaluate() NEVER raises."""

    def test_explicit_null_plan_rejected(self):
        out = c.evaluate({"proposal": {"goal": "g", "plan": None, "context": {}},
                          "frozen_route": ROUTE})
        assert_advisory_envelope(self, out, error="PROPOSAL_PLAN_INVALID")

    def test_non_list_plan_rejected(self):
        out = c.evaluate({"proposal": {"goal": "g", "plan": "not-a-list", "context": {}},
                          "frozen_route": ROUTE})
        assert_advisory_envelope(self, out, error="PROPOSAL_PLAN_INVALID")

    def test_explicit_null_allowed_milestones_rejected(self):
        route = dict(ROUTE, allowed_milestones=None)
        out = c.evaluate(with_route(route))
        assert_advisory_envelope(self, out, error="ROUTE_LIST_INVALID_ALLOWED_MILESTONES")

    def test_non_list_allowed_milestones_rejected(self):
        route = dict(ROUTE, allowed_milestones="V0.7")
        out = c.evaluate(with_route(route))
        assert_advisory_envelope(self, out, error="ROUTE_LIST_INVALID_ALLOWED_MILESTONES")

    def test_explicit_null_premature_milestones_rejected(self):
        route = dict(ROUTE, premature_milestones=None)
        out = c.evaluate(with_route(route))
        assert_advisory_envelope(self, out, error="ROUTE_LIST_INVALID_PREMATURE")

    def test_explicit_null_controller_owned_actions_rejected(self):
        route = dict(ROUTE, controller_owned_actions=None)
        out = c.evaluate(with_route(route))
        assert_advisory_envelope(self, out, error="ROUTE_LIST_INVALID_CONTROLLER_OWNED_ACTIONS")

    def test_all_four_null_cases_never_raise(self):
        inputs = [
            {"proposal": {"goal": "g", "plan": None}, "frozen_route": ROUTE},
            {"proposal": {"goal": "g"}, "frozen_route": dict(ROUTE, allowed_milestones=None)},
            {"proposal": {"goal": "g"}, "frozen_route": dict(ROUTE, premature_milestones=None)},
            {"proposal": {"goal": "g"}, "frozen_route": dict(ROUTE, controller_owned_actions=None)},
        ]
        for inp in inputs:
            out = c.evaluate(inp)  # must NOT raise
            assert_advisory_envelope(self, out)

    def test_absent_list_fields_still_valid(self):
        route = {"current_milestone": "V0.7"}
        out = c.evaluate(with_route(route, goal="deliver the C contract slice"))
        self.assertIn("none", kinds(out))
        self.assertIs(out["advisory_only"], True)


if __name__ == "__main__":
    unittest.main(verbosity=2)