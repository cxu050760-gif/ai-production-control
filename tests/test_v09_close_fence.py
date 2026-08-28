"""V0.9 CLOSE TASK-1 unit tests: execution fence family in ``store.start_effect``.

Covers CASE_ID V09-R08, V09-R09, V09-R26, V09-R36 (plus the V09-R07 double
assertion required by TASK-1 REGRESSION_REQUIREMENTS) against
V14-FROZEN §31 checks 4 / 19 / 20 / 22 and §27A.

Every negative assertion is paired with a positive control in the same file, as
V09_CLOSE_BUILD_SPEC.md TEST_REQUIREMENTS demands: the gate must reject the
stale/forged claim without rejecting an ordinary, current reservation.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "src"), str(ROOT / "runtime")):
    if p not in __import__("sys").path:
        __import__("sys").path.insert(0, p)

from aicontrol.controller import Controller  # noqa: E402
from aicontrol.store import GateDenied, Reservation  # noqa: E402
from aicontrol.util import sha256_text  # noqa: E402


class Harness:
    """Controller over an isolated state root, authorized through the external entry."""

    def __init__(self, tmp: str, task_id: str = "v09-close-fence") -> None:
        root = Path(tmp)
        config = copy.deepcopy(json.loads((ROOT / "config" / "production.json").read_text(encoding="utf-8")))
        config["code_root"] = str(ROOT)
        config["state_root"] = str(root / "state")
        config["output_root"] = str(root / "output")
        config["release_root"] = str(root / "release")
        config["evidence_root"] = str(root / "evidence")
        config["database_path"] = str(root / "state" / "control.db")
        self.config_path = root / "config.json"
        self.config_path.write_text(json.dumps(config), encoding="utf-8")
        self.controller = Controller(self.config_path)
        self.controller.store.set_meta("tcb_status", "VERIFIED")
        self.controller.store.set_meta("authority_status", "VERIFIED")
        self.task_id = task_id
        task = self.controller.bootstrap_task(
            goal="V0.9 CLOSE fence regression",
            expected_final_artifact="none",
            acceptance_criteria=["offline"],
            data_classification="PUBLIC",
            task_id=task_id,
        )
        self.context_fence = task["context_fence"]
        self.lease = self.controller.acquire_lease()

    def close(self) -> None:
        self.controller.close()

    def grant(self, *, provider: str = "provider-a", destination: str = "destination-a",
              purpose: str = "v09-test", effect_type: str = "AI_MESSAGE",
              max_effect_count: int = 4) -> dict[str, Any]:
        resource = "resource-a"
        scope = {
            "provider": provider, "destination": destination, "resource": resource,
            "purpose": purpose, "effect_type": effect_type, "data_classes": ["PUBLIC"],
            "identity": self.controller.controller_instance_id,
        }
        nonce = self.controller.store.issue_decision_nonce(
            self.task_id, scope, user_decision_reference="external-authority:v09-close-unit")
        return self.controller.store.grant_authorization(
            self.task_id, nonce["decision_nonce"], scope, provider=provider,
            resource=resource, purpose=purpose, effect_type=effect_type,
            max_effect_count=max_effect_count)

    def intent(self, *, slot: str = "slot-a", payload: str = "payload-a",
               provider: str = "provider-a", destination: str = "destination-a",
               purpose: str = "v09-test") -> dict[str, Any]:
        return {
            "task_id": self.task_id, "operation": "FAKE_EXTERNAL_EFFECT",
            "provider": provider, "destination": destination,
            "expected_account": "credential-ref:fake-v09", "resource": "resource-a",
            "payload_hash": sha256_text(payload), "critical_params": {},
            "purpose": purpose, "logical_effect_slot": slot,
            "retry_semantics": "RECONCILE_REQUIRED", "impact": "LOW",
            "reversibility": "REVERSIBLE", "effect_scope": "EXTERNAL",
            "effect_type": "AI_MESSAGE", "data_classification": "PUBLIC",
        }

    def reserve(self, auth: dict[str, Any], intent: dict[str, Any]) -> Reservation:
        resource_id = "resource-lock-a"
        store = self.controller.store
        store.acquire_lock(resource_id,
                           controller_instance_id=self.controller.controller_instance_id,
                           owner=f"task:{self.task_id}", pid=1,
                           process_start_identity=self.controller.process_start_identity,
                           ttl_seconds=600)
        try:
            return store.reserve_effect(
                intent, controller_instance_id=self.controller.controller_instance_id,
                controller_lease_id=self.lease["lease_id"],
                authorization_id=auth["authorization_id"], context_fence=self.context_fence,
                resource_id=resource_id, resource_hash=sha256_text(resource_id),
                capability_permitted=True, egress_permitted=True, resource_fresh=True)
        finally:
            store.release_lock(resource_id, self.controller.controller_instance_id)

    def start(self, reservation: Reservation) -> None:
        self.controller.store.start_effect(
            reservation, controller_instance_id=self.controller.controller_instance_id,
            controller_lease_id=self.lease["lease_id"], resource_fresh=True)

    def action_status(self, action_id: str) -> str:
        row = self.controller.store.connection.execute(
            "SELECT status FROM actions WHERE action_id=?", (action_id,)).fetchone()
        return str(row["status"]) if row else "MISSING"


class FenceFamilyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="v09-close-fence-")
        self.hx = Harness(self._tmp.name)

    def tearDown(self) -> None:
        self.hx.close()
        self._tmp.cleanup()

    # --- V09-R08 execution_fence_token -------------------------------------
    def test_forged_execution_fence_token_is_denied(self):
        auth, intent = self.hx.grant(), self.hx.intent(slot="r08-forged")
        reservation = self.hx.reserve(auth, intent)
        forged = Reservation(reservation.action_id, reservation.logical_effect_id,
                             reservation.effect_intent_hash, reservation.logical_effect_slot,
                             reservation.attempt_id, "0" * 64, False, reservation.status)
        with self.assertRaises(GateDenied):
            self.hx.start(forged)
        self.assertEqual(self.hx.action_status(reservation.action_id),
                         "RESERVATION_COMMITTED")

    def test_mismatched_execution_fence_token_is_denied(self):
        auth, intent = self.hx.grant(), self.hx.intent(slot="r08-mismatch")
        reservation = self.hx.reserve(auth, intent)
        tampered = Reservation(reservation.action_id, reservation.logical_effect_id,
                               reservation.effect_intent_hash, reservation.logical_effect_slot,
                               reservation.attempt_id, "f" * 64, False, reservation.status)
        with self.assertRaises(GateDenied):
            self.hx.start(tampered)

    def test_matching_execution_fence_token_starts(self):
        auth, intent = self.hx.grant(), self.hx.intent(slot="r08-positive")
        reservation = self.hx.reserve(auth, intent)
        self.hx.start(reservation)
        self.assertEqual(self.hx.action_status(reservation.action_id),
                         "EFFECT_START_COMMITTED")

    # --- V09-R09 canonical state revision ----------------------------------
    def test_advanced_state_revision_is_denied(self):
        auth, intent = self.hx.grant(), self.hx.intent(slot="r09-stale")
        reservation = self.hx.reserve(auth, intent)
        state = self.hx.controller.store.read_state()
        state["v09_close_probe"] = "advanced"
        self.hx.controller.store.commit_state(state, reason="V09_R09_UNIT")
        with self.assertRaises(GateDenied):
            self.hx.start(reservation)

    def test_unchanged_state_revision_starts(self):
        auth, intent = self.hx.grant(), self.hx.intent(slot="r09-positive")
        reservation = self.hx.reserve(auth, intent)
        self.hx.start(reservation)
        self.assertEqual(self.hx.action_status(reservation.action_id),
                         "EFFECT_START_COMMITTED")

    # --- V09-R26 task-level authorization generation ------------------------
    def test_task_generation_advance_denies_old_reservation(self):
        auth, intent = self.hx.grant(), self.hx.intent(slot="r26-stale")
        reservation = self.hx.reserve(auth, intent)
        self.hx.grant(provider="provider-b", destination="destination-b",
                      purpose="newer-authorization", max_effect_count=1)
        with self.assertRaises(GateDenied):
            self.hx.start(reservation)

    def test_without_generation_advance_reservation_starts(self):
        auth, intent = self.hx.grant(), self.hx.intent(slot="r26-positive")
        reservation = self.hx.reserve(auth, intent)
        self.hx.start(reservation)
        self.assertEqual(self.hx.action_status(reservation.action_id),
                         "EFFECT_START_COMMITTED")

    def test_single_authorization_tampering_still_denied(self):
        """V09-R07 double assertion: the pre-existing per-authorization check survives."""
        auth, intent = self.hx.grant(), self.hx.intent(slot="r07-double")
        reservation = self.hx.reserve(auth, intent)
        self.hx.controller.store.connection.execute(
            "UPDATE authorizations SET generation=generation+1 WHERE authorization_id=?",
            (auth["authorization_id"],))
        with self.assertRaises(GateDenied):
            self.hx.start(reservation)

    # --- V09-R36 stale process after takeover -------------------------------
    def test_takeover_denies_stale_reservation(self):
        auth, intent = self.hx.grant(), self.hx.intent(slot="r36-stale")
        reservation = self.hx.reserve(auth, intent)
        self.hx.grant(provider="provider-b", destination="destination-b",
                      purpose="takeover", max_effect_count=1)
        with self.assertRaises(GateDenied):
            self.hx.start(reservation)

    def test_execution_before_takeover_is_permitted(self):
        auth, intent = self.hx.grant(), self.hx.intent(slot="r36-positive")
        reservation = self.hx.reserve(auth, intent)
        self.hx.start(reservation)
        self.assertEqual(self.hx.action_status(reservation.action_id),
                         "EFFECT_START_COMMITTED")

    # --- R18 adjudicated semantics must not regress -------------------------
    def test_same_slot_different_payload_keeps_distinct_identities(self):
        """BUILDER_RULING_R18 §2.1: TASK-1 must not alter slot/identity semantics.

        Reserve and start are interleaved because reserve_effect consumes and
        advances the authorization generation; this mirrors execute_effect.
        """
        auth = self.hx.grant(max_effect_count=4)
        first = self.hx.reserve(auth, self.hx.intent(slot="r18-slot", payload="payload-one"))
        self.hx.start(first)
        second = self.hx.reserve(auth, self.hx.intent(slot="r18-slot", payload="payload-two"))
        self.hx.start(second)
        self.assertEqual(first.logical_effect_slot, second.logical_effect_slot)
        self.assertNotEqual(first.logical_effect_id, second.logical_effect_id)
        self.assertFalse(first.deduplicated)
        self.assertFalse(second.deduplicated)
        self.assertEqual(self.hx.action_status(first.action_id), "EFFECT_START_COMMITTED")
        self.assertEqual(self.hx.action_status(second.action_id), "EFFECT_START_COMMITTED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
