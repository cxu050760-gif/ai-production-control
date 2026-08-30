"""V0.9 CLOSE TASK-2 unit tests: the UNKNOWN-outcome retry gate.

Covers CASE_ID V09-R20 (same-instance ordinary retry of an unresolved logical
effect must be denied) and V09-R21 (a replay from a different controller
instance must surface reconciliation_required instead of a silent dedup),
against V14-FROZEN §23, §26, §27 and §31 check 17.

The positive controls are the point of this file: a *settled* prior action must
still deduplicate exactly as before (R16/R17 semantics), and the gate must not
invent a second external effect.
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

from aicontrol.controller import Controller  # noqa: E402
from aicontrol.store import GateDenied  # noqa: E402
from aicontrol.util import sha256_text  # noqa: E402
from test_v09_close_fence import Harness  # noqa: E402


def ok_adapter(_reservation) -> dict[str, Any]:
    return {"envelope": {"status": "SUCCESS"}}


class UnknownOutcomeGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="v09-close-unknown-")
        self.hx = Harness(self._tmp.name)

    def tearDown(self) -> None:
        self.hx.close()
        self._tmp.cleanup()

    def leave_unknown(self, slot: str):
        auth = self.hx.grant()
        intent = self.hx.intent(slot=slot)
        reservation = self.hx.reserve(auth, intent)
        self.hx.start(reservation)
        self.hx.controller.store.finish_effect(reservation, {"probe": "response_lost"}, unknown=True)
        return auth, intent, reservation

    # --- V09-R20 ------------------------------------------------------------
    def test_same_instance_retry_of_unknown_outcome_is_denied(self):
        auth, intent, reservation = self.leave_unknown("r20-denied")
        self.assertEqual(self.hx.action_status(reservation.action_id), "OUTCOME_UNKNOWN")
        with self.assertRaises(GateDenied):
            self.hx.reserve(auth, intent)
        # denied before any state transition: the unresolved action is untouched
        self.assertEqual(self.hx.action_status(reservation.action_id), "OUTCOME_UNKNOWN")

    def test_denied_retry_does_not_create_a_second_action(self):
        auth, intent, reservation = self.leave_unknown("r20-count")
        before = self.hx.controller.store.connection.execute(
            "SELECT COUNT(*) AS c FROM actions WHERE task_id=?", (self.hx.task_id,)).fetchone()["c"]
        with self.assertRaises(GateDenied):
            self.hx.reserve(auth, intent)
        after = self.hx.controller.store.connection.execute(
            "SELECT COUNT(*) AS c FROM actions WHERE task_id=?", (self.hx.task_id,)).fetchone()["c"]
        self.assertEqual(before, after)

    def test_settled_action_replay_still_deduplicates(self):
        """Positive control protecting V09-R16/R17: a committed outcome dedups."""
        auth = self.hx.grant()
        intent = self.hx.intent(slot="r16-positive", payload="same-payload")
        reservation = self.hx.reserve(auth, intent)
        self.hx.start(reservation)
        self.hx.controller.store.finish_effect(reservation, {"adapter_status": "SUCCESS"}, unknown=False)
        self.assertEqual(self.hx.action_status(reservation.action_id), "ACTION_COMMITTED")
        replay = self.hx.reserve(auth, intent)
        self.assertTrue(replay.deduplicated)
        self.assertEqual(replay.status, "ACTION_COMMITTED")

    def test_unresolved_retry_from_another_instance_is_not_denied_as_retry(self):
        """A different instance is the R21 path, not the R20 denial."""
        auth, intent, reservation = self.leave_unknown("r21-other-instance")
        replay = self.hx.controller.store.reserve_effect(
            intent, controller_instance_id="controller-a-restarted",
            controller_lease_id=self.hx.lease["lease_id"],
            authorization_id=auth["authorization_id"], context_fence=self.hx.context_fence,
            resource_id="resource-lock-a", resource_hash=sha256_text("resource-lock-a"),
            capability_permitted=True, egress_permitted=True, resource_fresh=True)
        self.assertTrue(replay.deduplicated)
        self.assertEqual(replay.status, "OUTCOME_UNKNOWN")

    # --- V09-R21 ------------------------------------------------------------
    def test_restarted_replay_reports_reconciliation_required_and_never_executes(self):
        auth, intent, reservation = self.leave_unknown("r21-restart")
        calls: list[str] = []

        def counting_adapter(_reservation):
            calls.append("crossed")
            return ok_adapter(_reservation)

        # AD-4 equivalent: a new Controller instance over the same state root.
        self.hx.controller.close()
        restarted = Controller(self.hx.config_path)
        restarted.store.set_meta("tcb_status", "VERIFIED")
        restarted.store.set_meta("authority_status", "VERIFIED")
        self.hx.controller = restarted
        self.hx.lease = restarted.acquire_lease()
        replay_auth = self.hx.grant()
        result = restarted.execute_effect(
            task_id=self.hx.task_id, lease=self.hx.lease,
            authorization_id=replay_auth["authorization_id"],
            context_fence=self.hx.context_fence, resource_id="resource-lock-restart",
            resource_hash=sha256_text("resource-lock-restart"),
            intent=self.hx.intent(slot="r21-restart"), adapter=counting_adapter,
            egress_permitted=True)
        self.assertTrue(result.get("reconciliation_required") is True)
        self.assertFalse(result.get("deduplicated") is False)
        self.assertIsNone(result.get("adapter_result"))
        self.assertEqual(calls, [], "the external boundary must not be crossed again")
        self.assertEqual(self.hx.action_status(reservation.action_id), "OUTCOME_UNKNOWN")


if __name__ == "__main__":
    unittest.main(verbosity=2)
