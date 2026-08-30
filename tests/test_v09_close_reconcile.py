"""V0.9 CLOSE TASK-3 unit tests: canonical ``Controller.reconcile_effect``.

Covers CASE_ID V09-R22, V09-R23 and V09-R24 against V14-FROZEN §23 ACTION LEDGER,
§26 RECONCILE_REQUIRED / NEVER_AUTO_RETRY, §27 recovery chain and §105/§118.

The invariants that matter are that reconciliation never executes anything and
that neither a negative nor an indeterminate observation manufactures progress:
only a proven-succeeded reality moves the ledger.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "src"), str(ROOT / "runtime")):
    if p not in __import__("sys").path:
        __import__("sys").path.insert(0, p)

from aicontrol.store import GateDenied  # noqa: E402
from test_v09_close_fence import Harness  # noqa: E402


class ReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="v09-close-reconcile-")
        self.hx = Harness(self._tmp.name)

    def tearDown(self) -> None:
        self.hx.close()
        self._tmp.cleanup()

    def unresolved(self, slot: str):
        auth = self.hx.grant()
        intent = self.hx.intent(slot=slot)
        reservation = self.hx.reserve(auth, intent)
        self.hx.start(reservation)
        self.hx.controller.store.finish_effect(reservation, {"probe": "response_lost"}, unknown=True)
        self.assertEqual(self.hx.action_status(reservation.action_id), "OUTCOME_UNKNOWN")
        return reservation

    def probe_returning(self, state: str):
        return lambda _reservation: state

    def external_effect_rows(self) -> int:
        return self.hx.controller.store.connection.execute(
            "SELECT COUNT(*) AS c FROM actions WHERE task_id=?", (self.hx.task_id,)
        ).fetchone()["c"]

    # --- V09-R22 ------------------------------------------------------------
    def test_proven_success_commits_without_executing(self):
        reservation = self.unresolved("r22-committed")
        result = self.hx.controller.reconcile_effect(
            reservation=reservation, probe=self.probe_returning("SUCCEEDED"))
        self.assertEqual(result["status"], "ACTION_COMMITTED")
        self.assertEqual(self.hx.action_status(reservation.action_id), "ACTION_COMMITTED")
        self.assertIs(result["executed"], False)
        self.assertIs(result["ordinary_retry_permitted"], False)
        # the effect count never grows: reconciliation observed, it did not re-issue
        self.assertEqual(self.external_effect_rows(), 1)

    def test_committed_action_cannot_be_reconciled_again(self):
        reservation = self.unresolved("r22-twice")
        self.hx.controller.reconcile_effect(reservation=reservation, probe=self.probe_returning("SUCCEEDED"))
        with self.assertRaises(GateDenied):
            self.hx.controller.reconcile_effect(
                reservation=reservation, probe=self.probe_returning("SUCCEEDED"))

    # --- V09-R23 ------------------------------------------------------------
    def test_proven_not_occurred_grants_no_replay_authority(self):
        reservation = self.unresolved("r23-controlled-retry")
        result = self.hx.controller.reconcile_effect(
            reservation=reservation, probe=self.probe_returning("NOT_OCCURRED"))
        self.assertIs(result["executed"], False)
        self.assertIs(result["auto_retry_permitted"], False)
        self.assertIs(result["ordinary_retry_permitted"], False)
        self.assertIn("RETRY", result["reconciliation"])
        self.assertEqual(self.hx.action_status(reservation.action_id), "OUTCOME_UNKNOWN")
        self.assertEqual(self.external_effect_rows(), 1)

    # --- V09-R24 ------------------------------------------------------------
    def test_indeterminate_reality_stays_unknown_and_escalates(self):
        reservation = self.unresolved("r24-indeterminate")
        result = self.hx.controller.reconcile_effect(
            reservation=reservation, probe=self.probe_returning("INDETERMINATE"))
        self.assertEqual(result["status"], "OUTCOME_UNKNOWN")
        self.assertIs(result["human_gate_required"], True)
        self.assertIs(result["executed"], False)
        self.assertEqual(self.hx.action_status(reservation.action_id), "OUTCOME_UNKNOWN")
        self.assertEqual(self.external_effect_rows(), 1)

    def test_unrecognised_observation_is_treated_as_indeterminate(self):
        """Fail-closed: an unknown label may never look like a proven outcome."""
        reservation = self.unresolved("r24-unrecognised")
        result = self.hx.controller.reconcile_effect(
            reservation=reservation, probe=self.probe_returning("PARTIALLY_DONE"))
        self.assertEqual(result["status"], "OUTCOME_UNKNOWN")
        self.assertIs(result["human_gate_required"], True)
        self.assertEqual(self.hx.action_status(reservation.action_id), "OUTCOME_UNKNOWN")

    # --- preconditions ------------------------------------------------------
    def test_empty_evidence_is_rejected(self):
        reservation = self.unresolved("pre-empty")
        with self.assertRaises(GateDenied):
            self.hx.controller.reconcile_effect(reservation=reservation, evidence={})

    def test_missing_observation_is_rejected(self):
        reservation = self.unresolved("pre-missing")
        with self.assertRaises(GateDenied):
            self.hx.controller.reconcile_effect(
                reservation=reservation, evidence={"source": "provider-report", "observed_state": "   "})

    def test_non_unknown_action_cannot_be_reconciled(self):
        auth = self.hx.grant()
        intent = self.hx.intent(slot="pre-settled")
        reservation = self.hx.reserve(auth, intent)
        self.hx.start(reservation)
        self.hx.controller.store.finish_effect(reservation, {"adapter_status": "SUCCESS"}, unknown=False)
        with self.assertRaises(GateDenied):
            self.hx.controller.reconcile_effect(
                reservation=reservation, probe=self.probe_returning("SUCCEEDED"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
