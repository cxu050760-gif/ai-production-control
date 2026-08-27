"""V07-INTEGRATE-2 preflight verification against the three frozen V0.7 contracts.

This is NOT a replacement integration implementation. It attacks the accepted
contracts at their public boundaries so the later B1 candidate can be checked
against an already-fixed semantic matrix.
"""
from __future__ import annotations

import copy
import json
import unittest
from importlib import import_module

import v07_integration_verify_support as fx

sb = import_module("strategic_brain_contract")
cmod = import_module("strategic_correction")
sr = import_module("strategic_reuse_contract")


class ContractMatrix(unittest.TestCase):
    def assert_advisory(self, result):
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("non_authority"), result)
        if "advisory_only" in result:
            self.assertTrue(result.get("advisory_only"), result)
        if "mutated_external_state" in result:
            self.assertFalse(result.get("mutated_external_state"), result)

    def test_normal_three_contract_path(self):
        proposal = sb.build_proposal(fx.brain_input())
        self.assertEqual(proposal.get("schema"), "v0.7-strategic-brain-proposal")
        self.assert_advisory(proposal)

        correction = cmod.evaluate({"proposal": proposal, "frozen_route": fx.frozen_route()})
        self.assertEqual([c["kind"] for c in correction["corrections"]], ["none"])
        self.assert_advisory(correction)

        reuse = sr.evaluate({"material": fx.reusable_material(), "current": fx.reuse_current()})
        self.assertEqual(reuse.get("decision"), "reuse", reuse)
        self.assertEqual([r["kind"] for r in reuse["reasons"]], ["none"])
        self.assert_advisory(reuse)

    def test_c_attack_matrix_detected(self):
        matrix = fx.load_attack_matrix()["c_attacks"]
        for attack in matrix:
            with self.subTest(attack=attack["id"]):
                proposal = sb.build_proposal(fx.brain_input(attack["detail"]))
                result = cmod.evaluate({"proposal": proposal, "frozen_route": fx.frozen_route()})
                kinds = {item["kind"] for item in result.get("corrections") or []}
                self.assertIn(attack["expected_kind"], kinds, result)
                self.assertNotEqual(kinds, {"none"}, result)
                self.assert_advisory(result)

    def test_reuse_reject_matrix(self):
        cases = []

        material = fx.reusable_material(); material["claimed_milestone"] = "V0.6"
        cases.append(("stale_milestone", material, fx.reuse_current(), "milestone_incompatible"))

        material = fx.reusable_material(); material["requested_scope"] = ["provider-adapter"]
        cases.append(("out_of_scope", material, fx.reuse_current(), "scope_incompatible"))

        material = fx.reusable_material(); material["promises"] = ["deterministic"]
        cases.append(("acceptance", material, fx.reuse_current(), "acceptance_unsatisfied"))

        material = fx.reusable_material(); material["strategy"] = "Builder self-review and assign verdict"
        cases.append(("role", material, fx.reuse_current(), "role_separation_violation"))

        material = fx.reusable_material(); material["strategy"] = "promotion and crown milestone"
        cases.append(("authority", material, fx.reuse_current(), "authority_violation"))

        for name, material, current, expected in cases:
            with self.subTest(case=name):
                result = sr.evaluate({"material": material, "current": current})
                self.assertEqual(result.get("decision"), "reject", result)
                kinds = {item["kind"] for item in result.get("reasons") or []}
                self.assertIn(expected, kinds, result)
                self.assert_advisory(result)

    def test_current_facts_override_historical_material(self):
        current = fx.reuse_current()
        material = fx.reusable_material()
        material["claimed_milestone"] = "V0.6"
        material["requested_scope"] = ["provider-adapter"]
        material["promises"] = ["historical-acceptance"]
        result = sr.evaluate({"material": material, "current": current})
        kinds = {x["kind"] for x in result["reasons"]}
        self.assertTrue({"milestone_incompatible", "scope_incompatible", "acceptance_unsatisfied"} <= kinds)
        self.assertEqual(result["decision"], "reject")

    def test_authority_text_never_becomes_authority(self):
        route_before = copy.deepcopy(fx.frozen_route())
        current_before = copy.deepcopy(fx.reuse_current())
        matrix = fx.load_attack_matrix()["authority_attacks"]
        for text in matrix:
            with self.subTest(text=text):
                proposal = sb.build_proposal(fx.brain_input(text))
                self.assert_advisory(proposal)
                self.assertTrue(all(step.get("action") == "plan_item" for step in proposal.get("plan", [])))
                correction = cmod.evaluate({"proposal": proposal, "frozen_route": route_before})
                self.assert_advisory(correction)
                material = fx.reusable_material(); material["strategy"] = text
                reuse = sr.evaluate({"material": material, "current": current_before})
                self.assert_advisory(reuse)
        self.assertEqual(route_before, fx.frozen_route())
        self.assertEqual(current_before, fx.reuse_current())

    def test_fail_closed_malformed_null_oversized(self):
        bad_brain = [None, [], {"goal": ""}, {"goal": "x" * 257}, {"goal": "ok", "context": None}]
        for value in bad_brain:
            with self.subTest(stage="brain", value=repr(value)[:40]):
                result = sb.build_proposal(value)
                self.assertFalse(result.get("valid", True), result)
                self.assertIsNotNone(result.get("error"), result)

        bad_c = [None, {}, {"proposal": None, "frozen_route": fx.frozen_route()},
                 {"proposal": sb.build_proposal(fx.brain_input()), "frozen_route": None}]
        for value in bad_c:
            with self.subTest(stage="c", value=repr(value)[:40]):
                result = cmod.evaluate(value)
                self.assertFalse(result.get("valid", True), result)
                self.assertIsNotNone(result.get("error"), result)
                self.assert_advisory(result)

        bad_sr = [None, {}, {"material": None, "current": fx.reuse_current()},
                  {"material": fx.reusable_material(), "current": None}]
        for value in bad_sr:
            with self.subTest(stage="reuse", value=repr(value)[:40]):
                result = sr.evaluate(value)
                self.assertFalse(result.get("valid", True), result)
                self.assertIsNotNone(result.get("error"), result)
                self.assert_advisory(result)

    def test_determinism_repeated_identical_inputs(self):
        binput = fx.brain_input()
        b_results = [sb.build_proposal(copy.deepcopy(binput)) for _ in range(8)]
        self.assertTrue(all(x == b_results[0] for x in b_results[1:]))

        cinput = {"proposal": b_results[0], "frozen_route": fx.frozen_route()}
        c_results = [cmod.evaluate(copy.deepcopy(cinput)) for _ in range(8)]
        self.assertTrue(all(x == c_results[0] for x in c_results[1:]))

        rinput = {"material": fx.reusable_material(), "current": fx.reuse_current()}
        r_results = [sr.evaluate(copy.deepcopy(rinput)) for _ in range(8)]
        self.assertTrue(all(x == r_results[0] for x in r_results[1:]))

    def test_results_are_machine_serializable(self):
        proposal = sb.build_proposal(fx.brain_input())
        correction = cmod.evaluate({"proposal": proposal, "frozen_route": fx.frozen_route()})
        reuse = sr.evaluate({"material": fx.reusable_material(), "current": fx.reuse_current()})
        for result in (proposal, correction, reuse):
            encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
            self.assertTrue(encoded.startswith("{"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
