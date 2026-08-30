"""V0.9 CLOSE TASK-5 unit tests: caller role binding on the execution path.

Covers CASE_ID V09-R06 (worker_role_mismatch) against V14-FROZEN §31 check 8
("caller capability permits effect") and §A64 Privileged Worker External-Effect
Bypass.

The role must be checked in the real execution decision path, not merely by a
helper that exists: every case here goes through ``execute_effect`` and asserts
whether the external effect actually happened.
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

from aicontrol.security import caller_role_allowed  # noqa: E402
from aicontrol.store import GateDenied  # noqa: E402
from aicontrol.util import sha256_text  # noqa: E402
from test_v09_close_fence import Harness  # noqa: E402


class CallerRoleBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="v09-close-role-")
        self.hx = Harness(self._tmp.name)
        self.crossed: list[str] = []

    def tearDown(self) -> None:
        self.hx.close()
        self._tmp.cleanup()

    def execute(self, auth, intent):
        def adapter(_reservation):
            self.crossed.append("external")
            return {"envelope": {"status": "SUCCESS"}}

        return self.hx.controller.execute_effect(
            task_id=self.hx.task_id, lease=self.hx.lease,
            authorization_id=auth["authorization_id"], context_fence=self.hx.context_fence,
            resource_id="resource-lock-a", resource_hash=sha256_text("resource-lock-a"),
            intent=intent, adapter=adapter, egress_permitted=True)

    def declaring(self, role: Any, slot: str) -> dict[str, Any]:
        intent = self.hx.intent(slot=slot)
        intent["critical_params"] = {"worker_id": "worker-b", "role": role}
        return intent

    # --- denial -------------------------------------------------------------
    def test_unauthorized_declared_role_is_denied_and_never_executes(self):
        auth = self.hx.grant()  # no role binding at all
        with self.assertRaises(GateDenied):
            self.execute(auth, self.declaring("UNAUTHORIZED_ROLE", "r06-denied"))
        self.assertEqual(self.crossed, [], "the external boundary must not be crossed")

    def test_declared_role_against_mismatched_role_list_is_denied(self):
        auth = self.hx.grant(roles=["READER"])
        with self.assertRaises(GateDenied):
            self.execute(auth, self.declaring("WRITER", "r06-mismatch"))
        self.assertEqual(self.crossed, [])

    def test_blank_role_list_still_denies_a_declared_role(self):
        auth = self.hx.grant(roles=[])
        with self.assertRaises(GateDenied):
            self.execute(auth, self.declaring("ANY_ROLE", "r06-empty-list"))
        self.assertEqual(self.crossed, [])

    # --- positive controls (minimal blast radius) ---------------------------
    def test_authorized_declared_role_executes(self):
        auth = self.hx.grant(roles=["WORKER_B"])
        result = self.execute(auth, self.declaring("WORKER_B", "r06-allowed"))
        self.assertEqual(self.hx.action_status(result["reservation"].action_id), "ACTION_COMMITTED")
        self.assertEqual(self.crossed, ["external"])

    def test_role_matching_is_case_insensitive(self):
        auth = self.hx.grant(roles=["worker_b"])
        result = self.execute(auth, self.declaring("WORKER_B", "r06-case"))
        self.assertEqual(self.crossed, ["external"])
        self.assertEqual(self.hx.action_status(result["reservation"].action_id), "ACTION_COMMITTED")

    def test_effect_declaring_no_role_is_unaffected(self):
        auth = self.hx.grant()
        result = self.execute(auth, self.hx.intent(slot="r06-no-role"))
        self.assertEqual(self.crossed, ["external"])
        self.assertEqual(self.hx.action_status(result["reservation"].action_id), "ACTION_COMMITTED")

    # --- pure predicate -----------------------------------------------------
    def test_predicate_is_pure_and_fail_closed_for_missing_binding(self):
        self.assertTrue(caller_role_allowed(declared_role=None, allowed_roles=None))
        self.assertTrue(caller_role_allowed(declared_role="   ", allowed_roles=None))
        self.assertFalse(caller_role_allowed(declared_role="WORKER", allowed_roles=None))
        self.assertTrue(caller_role_allowed(declared_role="WORKER", allowed_roles=["worker"]))
        self.assertFalse(caller_role_allowed(declared_role="WORKER", allowed_roles=["OTHER"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
