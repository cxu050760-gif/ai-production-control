"""V0.9 CLOSE TASK-4 unit tests: high-impact human gate and the closed effect model.

Covers CASE_ID V09-R32 (a HIGH / IRREVERSIBLE effect may not execute without an
explicit Human Gate reference) and V09-R34 (an effect_type outside the closed set
is refused on the issuance side AND on the execution side), against
V14-FROZEN §29/§30, §105/§118 and §27A.

Each denial is paired with the positive control the spec demands, because the
point of these gates is to stop the dangerous claim, not to widen the blast
radius onto ordinary LOW/reversible effects or already-known types.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "src"), str(ROOT / "runtime")):
    if p not in __import__("sys").path:
        __import__("sys").path.insert(0, p)

from aicontrol.security import known_effect_type_allowed  # noqa: E402
from aicontrol.store import GateDenied  # noqa: E402
from aicontrol.util import sha256_text  # noqa: E402
from test_v09_close_fence import Harness  # noqa: E402

UNKNOWN_TYPE = "TOTALLY_UNKNOWN_EFFECT_TYPE"


def ok_adapter(_reservation) -> dict[str, Any]:
    return {"envelope": {"status": "SUCCESS"}}


class ClassificationGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="v09-close-classification-")
        self.hx = Harness(self._tmp.name)

    def tearDown(self) -> None:
        self.hx.close()
        self._tmp.cleanup()

    def run_effect(self, auth, intent):
        return self.hx.controller.execute_effect(
            task_id=self.hx.task_id, lease=self.hx.lease,
            authorization_id=auth["authorization_id"], context_fence=self.hx.context_fence,
            resource_id="resource-lock-a", resource_hash=sha256_text("resource-lock-a"),
            intent=intent, adapter=ok_adapter, egress_permitted=True)

    def risky_intent(self, **kwargs):
        base = self.hx.intent(slot=kwargs.pop("slot", "high-risk"))
        base["impact"] = kwargs.pop("impact", "HIGH")
        base["reversibility"] = kwargs.pop("reversibility", "IRREVERSIBLE")
        base.update(kwargs)
        return base

    # --- V09-R32 ------------------------------------------------------------
    def test_high_impact_irreversible_without_reference_is_denied(self):
        auth = self.hx.grant()
        with self.assertRaises(GateDenied):
            self.run_effect(auth, self.risky_intent())

    def test_high_impact_with_reference_executes(self):
        auth = self.hx.grant()
        intent = self.risky_intent(slot="high-gated", human_gate_reference="user-decision:gate-1")
        result = self.run_effect(auth, intent)
        self.assertIs(result["deduplicated"], False)
        self.assertEqual(self.hx.action_status(result["reservation"].action_id), "ACTION_COMMITTED")

    def test_high_impact_with_blank_reference_is_denied(self):
        auth = self.hx.grant()
        intent = self.risky_intent(slot="high-blank", human_gate_reference="   ")
        with self.assertRaises(GateDenied):
            self.run_effect(auth, intent)

    def test_low_reversible_without_reference_is_unaffected(self):
        """Positive control: the gate must not widen onto ordinary effects."""
        auth = self.hx.grant()
        result = self.run_effect(auth, self.hx.intent(slot="low-safe"))
        self.assertEqual(self.hx.action_status(result["reservation"].action_id), "ACTION_COMMITTED")

    def test_high_impact_reversible_still_gated(self):
        auth = self.hx.grant()
        intent = self.risky_intent(slot="high-reversible", impact="HIGH", reversibility="REVERSIBLE")
        with self.assertRaises(GateDenied):
            self.run_effect(auth, intent)

    # --- V09-R34: closed set ------------------------------------------------
    def test_unknown_effect_type_cannot_be_issued(self):
        with self.assertRaises(GateDenied):
            self.hx.grant(effect_type=UNKNOWN_TYPE)
        self.assertEqual(
            self.hx.controller.store.connection.execute(
                "SELECT COUNT(*) AS c FROM authorizations WHERE effect_type=?", (UNKNOWN_TYPE,)
            ).fetchone()["c"], 0)

    def test_unknown_effect_type_cannot_execute_even_with_a_valid_authorization(self):
        """Second layer: an old authorization must not revive a now-unknown type."""
        auth = self.hx.grant()
        intent = self.hx.intent(slot="exec-side-unknown")
        intent["effect_type"] = UNKNOWN_TYPE
        with self.assertRaises(GateDenied):
            self.run_effect(auth, intent)

    def test_known_effect_type_end_to_end(self):
        configured = self.hx.controller.store.known_effect_types or []
        self.assertIn("AI_MESSAGE", [str(t).upper() for t in configured])
        auth = self.hx.grant(effect_type="AI_MESSAGE")
        result = self.run_effect(auth, self.hx.intent(slot="known-type"))
        self.assertEqual(self.hx.action_status(result["reservation"].action_id), "ACTION_COMMITTED")

    def test_closed_set_membership_is_pure_and_case_insensitive(self):
        self.assertTrue(known_effect_type_allowed(effect_type="ai_message", known_effect_types=["AI_MESSAGE"]))
        self.assertFalse(known_effect_type_allowed(effect_type=UNKNOWN_TYPE, known_effect_types=["AI_MESSAGE"]))
        self.assertFalse(known_effect_type_allowed(effect_type=None, known_effect_types=["AI_MESSAGE"]))
        self.assertFalse(known_effect_type_allowed(effect_type="  ", known_effect_types=["AI_MESSAGE"]))
        self.assertTrue(known_effect_type_allowed(effect_type=UNKNOWN_TYPE, known_effect_types=None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
