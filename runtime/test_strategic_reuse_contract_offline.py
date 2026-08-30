"""Offline deterministic tests for the V0.7 Strategic Reuse contract.

Proves (per V07-STRATEGIC-REUSE-CONTRACT-6 acceptance):
- at least one passing valid-reuse case;
- at least one passing stale-or-out-of-scope rejection case;
- at least one passing case proving CURRENT supplied constraints override an
  incompatible HISTORICAL task shape (stale milestone / missing acceptance);
- role-separation and authority violation rejection cases;
- advisory-only: no mutation occurs (pure dict return; no IO/state);
- evaluate() NEVER raises: explicit null / non-list list-typed fields are
  rejected with structured advisory envelopes;
- every result, INCLUDING every rejection envelope, carries advisory_only=true,
  non_authority=true, and mutated_external_state=false;
- deterministic, machine-parseable, fail-closed on invalid/bounded input.
"""
import json
import unittest
from importlib import import_module

c = import_module("strategic_reuse_contract")

CURRENT = {
    "milestone": "V0.7",
    "allowed_milestones": ["V0.7"],
    "scope_allowlist": ["strategic", "correction"],
    "acceptance_requirements": ["deterministic_itf", "advisory_only"],
    "authority_constraints": ["crown_milestone"],
    "role_separation_terms": ["builder_self_review"],
}

VALID_MATERIAL = {
    "schema": "v0.7-strategic-reuse-material",
    "id": "mat-01",
    "strategy": "reuse the accepted strategic framing for the C contract slice",
    "claimed_milestone": "V0.7",
    "requested_scope": ["strategic"],
    "promises": ["deterministic_itf", "advisory_only"],
}


def payload(material=None, current=None):
    return {"material": material if material is not None else VALID_MATERIAL,
            "current": current if current is not None else CURRENT}


def kinds(out):
    return [r["kind"] for r in out["reasons"]]


class TestValidReuse(unittest.TestCase):
    def test_valid_reuse_case(self):
        out = c.evaluate(payload())
        self.assertEqual(out["decision"], "reuse")
        self.assertEqual(kinds(out), ["none"])
        self.assertEqual(out["schema"], "v0.7-strategic-reuse-advisory")

    def test_machine_parseable(self):
        out = c.evaluate(payload())
        self.assertEqual(json.loads(json.dumps(out)), out)

    def test_deterministic(self):
        self.assertEqual(c.evaluate(payload()), c.evaluate(payload()))


class TestStaleOrOutOfScope(unittest.TestCase):
    def test_stale_milestone_rejected(self):
        mat = dict(VALID_MATERIAL, claimed_milestone="V0.6")
        out = c.evaluate(payload(material=mat))
        self.assertEqual(out["decision"], "reject")
        self.assertIn("milestone_incompatible", kinds(out))

    def test_out_of_scope_rejected(self):
        mat = dict(VALID_MATERIAL, requested_scope=["integration"])
        out = c.evaluate(payload(material=mat))
        self.assertEqual(out["decision"], "reject")
        self.assertIn("scope_incompatible", kinds(out))

    def test_unclaimed_milestone_ok(self):
        mat = {k: v for k, v in VALID_MATERIAL.items() if k != "claimed_milestone"}
        out = c.evaluate(payload(material=mat))
        self.assertEqual(out["decision"], "reuse")


class TestCurrentOverridesHistoricalShapeAndMore(unittest.TestCase):
    def test_historical_shape_cannot_override_current_acceptance(self):
        # historical promise set does not satisfy CURRENT acceptance requirements
        mat = dict(VALID_MATERIAL, promises=["deterministic_itf"])
        out = c.evaluate(payload(material=mat))
        self.assertEqual(out["decision"], "reject")
        self.assertIn("acceptance_unsatisfied", kinds(out))

    def test_historical_promises_ignored_when_acceptance_satisfied(self):
        out = c.evaluate(payload())
        self.assertEqual(out["decision"], "reuse")

    def test_role_separation_violation_rejected(self):
        mat = dict(VALID_MATERIAL,
                   strategy="reuse material that says builder self-review is fine")
        out = c.evaluate(payload(material=mat))
        self.assertEqual(out["decision"], "reject")
        self.assertIn("role_separation_violation", kinds(out))

    def test_authority_violation_rejected_promotion(self):
        mat = dict(VALID_MATERIAL, strategy="material proposes to crown and promote now")
        out = c.evaluate(payload(material=mat))
        self.assertEqual(out["decision"], "reject")
        self.assertIn("authority_violation", kinds(out))

    def test_authority_violation_rejected_constraint_term(self):
        mat = dict(VALID_MATERIAL, strategy="material requests crown_milestone authority")
        out = c.evaluate(payload(material=mat))
        self.assertEqual(out["decision"], "reject")
        self.assertIn("authority_violation", kinds(out))


class TestAdvisoryFlags(unittest.TestCase):
    def test_all_results_advisory_only_and_no_mutation(self):
        inputs = (
            payload(),
            payload(material=dict(VALID_MATERIAL, claimed_milestone="V0.6")),
            payload(material=dict(VALID_MATERIAL, requested_scope=["integration"])),
            payload(material=dict(VALID_MATERIAL, promises=["deterministic_itf"])),
            payload(material=dict(VALID_MATERIAL,
                                  strategy="reuse material that says builder self-review is fine")),
            payload(material=dict(VALID_MATERIAL, strategy="material proposes to crown and promote now")),
        )
        for inp in inputs:
            out = c.evaluate(inp)
            self.assertIs(out["advisory_only"], True)
            self.assertIs(out["non_authority"], True)
            self.assertIs(out["mutated_external_state"], False)
            self.assertEqual(set(out.keys()),
                             {"schema", "decision", "decision_detail", "reasons",
                              "advisory_only", "non_authority", "mutated_external_state",
                              "detection_note"})

    def test_rejection_envelopes_retain_advisory_flags(self):
        for bad in (None, [], "x", 3, {},
                    {"material": None, "current": CURRENT},
                    {"material": VALID_MATERIAL},
                    {"material": [], "current": CURRENT},
                    {"material": VALID_MATERIAL, "current": []}):
            out = c.evaluate(bad)
            assert_advisory_envelope(self, out)


class TestFailClosed(unittest.TestCase):
    def test_non_object_input_rejected(self):
        for bad in (None, [], "x", 3):
            out = c.evaluate(bad)
            self.assertEqual(out["error"], "INPUT_NOT_OBJECT")

    def test_missing_or_falsey_material_rejected(self):
        self.assertEqual(c.evaluate({})["error"], "MATERIAL_MISSING")
        self.assertEqual(c.evaluate({"material": None, "current": CURRENT})["error"], "MATERIAL_MISSING")

    def test_missing_current_rejected(self):
        self.assertEqual(c.evaluate({"material": VALID_MATERIAL})["error"], "CURRENT_MISSING")

    def test_non_object_material_rejected(self):
        out = c.evaluate({"material": "x", "current": CURRENT})
        self.assertEqual(out["error"], "MATERIAL_NOT_OBJECT")

    def test_non_object_current_rejected(self):
        out = c.evaluate({"material": VALID_MATERIAL, "current": "y"})
        self.assertEqual(out["error"], "CURRENT_NOT_OBJECT")

    def test_oversized_strategy_rejected(self):
        mat = dict(VALID_MATERIAL, strategy="x" * (c.MAX_STRATEGY + 1))
        out = c.evaluate(payload(material=mat))
        self.assertEqual(out["error"], "MATERIAL_STRATEGY_INVALID")

    def test_rejection_deterministic(self):
        a = c.evaluate({"material": [], "current": CURRENT})
        b = c.evaluate({"material": [], "current": CURRENT})
        self.assertEqual(a, b)


class TestExplicitNullAndNonList(unittest.TestCase):
    """NEVER-RAISES: explicit null / non-list list-typed fields rejected structurally."""

    def test_explicit_null_material_requested_scope(self):
        mat = dict(VALID_MATERIAL, requested_scope=None)
        assert_advisory_envelope(self, c.evaluate(payload(material=mat)),
                                 error="MATERIAL_REQUESTED_SCOPE_INVALID")

    def test_non_list_material_promises(self):
        mat = dict(VALID_MATERIAL, promises="ok")
        assert_advisory_envelope(self, c.evaluate(payload(material=mat)),
                                 error="MATERIAL_PROMISES_INVALID")

    def test_explicit_null_current_allowed_milestones(self):
        cur = dict(CURRENT, allowed_milestones=None)
        assert_advisory_envelope(self, c.evaluate(payload(current=cur)),
                                 error="CURRENT_ALLOWED_MILESTONES_INVALID")

    def test_explicit_null_current_scope_allowlist(self):
        cur = dict(CURRENT, scope_allowlist=None)
        assert_advisory_envelope(self, c.evaluate(payload(current=cur)),
                                 error="CURRENT_SCOPE_ALLOWLIST_INVALID")

    def test_explicit_null_current_acceptance_requirements(self):
        cur = dict(CURRENT, acceptance_requirements=None)
        assert_advisory_envelope(self, c.evaluate(payload(current=cur)),
                                 error="CURRENT_ACCEPTANCE_REQUIREMENTS_INVALID")

    def test_explicit_null_current_authority_constraints(self):
        cur = dict(CURRENT, authority_constraints=None)
        assert_advisory_envelope(self, c.evaluate(payload(current=cur)),
                                 error="CURRENT_AUTHORITY_CONSTRAINTS_INVALID")

    def test_explicit_null_current_role_separation_terms(self):
        cur = dict(CURRENT, role_separation_terms=None)
        assert_advisory_envelope(self, c.evaluate(payload(current=cur)),
                                 error="CURRENT_ROLE_SEPARATION_TERMS_INVALID")

    def test_all_null_four_cases_never_raise(self):
        cases = [
            payload(material=dict(VALID_MATERIAL, requested_scope=None)),
            payload(current=dict(CURRENT, allowed_milestones=None)),
            payload(current=dict(CURRENT, scope_allowlist=None)),
            payload(current=dict(CURRENT, acceptance_requirements=None)),
        ]
        for inp in cases:
            assert_advisory_envelope(self, c.evaluate(inp))

    def test_absent_list_fields_still_valid(self):
        # absent (omitted) list fields are allowed; an unrequesting material is reusable
        cur = {"milestone": "V0.7"}
        mat = {"strategy": "reuse heuristic from the C slice"}
        out = c.evaluate(payload(material=mat, current=cur))
        self.assertEqual(out["decision"], "reuse")
        self.assertIs(out["advisory_only"], True)

    def test_empty_scope_allowlist_rejects_requested_scope(self):
        # fail-closed: when current scope allowlist is empty, any requested scope is out-of-scope
        cur = dict(CURRENT, scope_allowlist=[])
        out = c.evaluate(payload(current=cur))
        self.assertEqual(out["decision"], "reject")
        self.assertIn("scope_incompatible", kinds(out))


def assert_advisory_envelope(tc, out, error=None):
    tc.assertIs(out["advisory_only"], True)
    tc.assertIs(out["non_authority"], True)
    tc.assertIs(out["mutated_external_state"], False)
    tc.assertIs(out["valid"], False)
    if error is not None:
        tc.assertEqual(out["error"], error)


if __name__ == "__main__":
    unittest.main(verbosity=2)