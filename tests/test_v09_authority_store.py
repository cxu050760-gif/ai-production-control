from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aicontrol.controller import Controller  # noqa: E402
from aicontrol.security import (  # noqa: E402
    authority_scope_allowed,
    egress_allowed,
    human_gate_allowed,
    require_credential_isolation,
)
from aicontrol.store import ControlStore, GateDenied  # noqa: E402
from aicontrol.util import sha256_text  # noqa: E402


class V09AuthorityStoreTests(unittest.TestCase):
    def test_store_cannot_grant_without_real_decision_nonce(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with ControlStore(root / "control.db", state_root=root / "state") as store:
                store.create_goal_contract(
                    "task-v09",
                    {
                        "goal": "test",
                        "network_permission": "DENY",
                        "data_egress_policy": {"default": ["PUBLIC"]},
                        "external_side_effect_policy": "DENY",
                    },
                    change_reason="v09-test",
                )
                with self.assertRaises(GateDenied):
                    store.grant_authorization(
                        "task-v09",
                        "fake-executor-created-nonce",
                        {"provider": "p", "resource": "r", "purpose": "x"},
                        provider="p",
                        resource="r",
                        purpose="x",
                        effect_type="EXTERNAL",
                        max_effect_count=1,
                    )

    def test_authority_matrix_binds_provider_resource_purpose_identity(self):
        authorization = {
            "task_id": "task-v09",
            "provider": "provider-a",
            "resource": "resource-a",
            "purpose": "publish",
            "identity": "executor-a",
            "scope": {
                "provider": "provider-a",
                "resource": "resource-a",
                "purpose": "publish",
                "identity": "executor-a",
                "destination": "dest-a",
                "data_classes": ["INTERNAL"],
            },
        }
        self.assertTrue(
            authority_scope_allowed(
                authorization=authorization,
                task_id="task-v09",
                provider="provider-a",
                resource="resource-a",
                purpose="publish",
                identity="executor-a",
                destination="dest-a",
                classification="INTERNAL",
            )
        )
        for field, value in (
            ("provider", "provider-b"),
            ("resource", "resource-b"),
            ("purpose", "delete"),
            ("identity", "executor-b"),
        ):
            kwargs = {
                "task_id": "task-v09",
                "provider": "provider-a",
                "resource": "resource-a",
                "purpose": "publish",
                "identity": "executor-a",
                "destination": "dest-a",
                "classification": "INTERNAL",
            }
            kwargs[field] = value
            self.assertFalse(authority_scope_allowed(authorization=authorization, **kwargs))

    def test_missing_task_binding_fails_closed(self):
        authorization = {
            "provider": "provider-a",
            "resource": "resource-a",
            "purpose": "publish",
            "identity": "executor-a",
            "scope": {
                "destination": "dest-a",
                "data_classes": ["INTERNAL"],
            },
        }
        self.assertFalse(
            authority_scope_allowed(
                authorization=authorization,
                task_id="task-v09",
                provider="provider-a",
                resource="resource-a",
                purpose="publish",
                identity="executor-a",
                destination="dest-a",
                classification="INTERNAL",
            )
        )

    def test_secret_egress_is_always_denied(self):
        self.assertFalse(
            egress_allowed(
                classification="SECRET",
                destination="dest-a",
                provider="provider-a",
                purpose="publish",
                goal_contract={"data_egress_policy": {"dest-a": ["SECRET", "INTERNAL"]}},
                authorization_scope={
                    "provider": "provider-a",
                    "destination": "dest-a",
                    "purpose": "publish",
                    "data_classes": ["SECRET", "INTERNAL"],
                },
            )
        )

    def test_raw_credentials_cannot_be_embedded_in_authorization_scope(self):
        with self.assertRaises(GateDenied):
            require_credential_isolation({"provider": "p", "api_key": "raw-secret-value"})
        with self.assertRaises(GateDenied):
            require_credential_isolation({"nested": {"cookies": "session=abc"}})
        require_credential_isolation({"provider": "p", "credential_ref": "vault://provider/account"})

    def test_high_risk_human_gate_fails_closed(self):
        self.assertFalse(human_gate_allowed(required=True, reference=None))
        self.assertFalse(human_gate_allowed(required=True, reference=""))
        self.assertTrue(human_gate_allowed(required=True, reference="HG-20260827-001"))
        self.assertTrue(human_gate_allowed(required=False, reference=None))


class FakeWorkBuddyRuntime:
    def __init__(self) -> None:
        self.real_effect_count = 0

    def invoke_workbuddy_brain(self, **_kwargs):
        self.real_effect_count += 1
        return {"envelope": {"status": "DONE", "data": {"proposal": "ok"}}}


class V09ControllerAuthoritySeparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="v09-controller-authority-")
        self.root = Path(self.temporary.name)
        self.store = ControlStore(self.root / "control.db", state_root=self.root / "state")
        self.store.set_meta("tcb_status", "VERIFIED")
        self.task_id = "task-v09-controller"
        self.store.create_goal_contract(
            self.task_id,
            {
                "goal": "controller authority separation",
                "network_permission": "ALLOW_SCOPED",
                "data_egress_policy": {"WorkBuddy": ["PUBLIC", "INTERNAL"], "default": []},
                "external_side_effect_policy": "SCOPED_AUTHORIZATION_REQUIRED",
            },
            change_reason="v09-controller-test",
        )
        self.capsule = self.store.create_context_capsule(self.task_id, "V09_TEST", {})
        self.controller = Controller.__new__(Controller)
        self.controller.store = self.store
        self.controller.controller_instance_id = "controller-v09-executor"
        self.controller.process_start_identity = "v09-test-process"
        self.controller.config = {"policy": {"lock_lease_seconds": 300}}
        self.controller.runtime = FakeWorkBuddyRuntime()
        self.lease = self.store.acquire_controller_lease(
            self.controller.controller_instance_id,
            pid=os.getpid(),
            process_start_identity=self.controller.process_start_identity,
            ttl_seconds=300,
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def _count(self, table: str) -> int:
        return int(self.store.connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])

    def _preauthorize(
        self,
        *,
        provider: str = "WorkBuddy",
        resource: str = "fresh-workbuddy-session",
        purpose: str = "goal-planning",
        identity: str | None = None,
        effect_type: str = "AI_MESSAGE",
    ) -> dict:
        identity = identity or self.controller.controller_instance_id
        scope = {
            "provider": provider,
            "destination": "WorkBuddy",
            "resource": resource,
            "purpose": purpose,
            "effect_type": effect_type,
            "data_classes": ["INTERNAL"],
            "identity": identity,
            # V09-R06: execute_workbuddy_fallback declares critical_params.role
            # "FALLBACK", so the external authority must bind that role explicitly.
            "roles": ["FALLBACK"],
        }
        nonce = self.store.issue_decision_nonce(
            self.task_id,
            scope,
            user_decision_reference="external-authority:v09-test",
        )
        return self.store.grant_authorization(
            self.task_id,
            nonce["decision_nonce"],
            scope,
            provider=provider,
            resource=resource,
            purpose=purpose,
            effect_type=effect_type,
            max_effect_count=1,
        )

    def _fallback(self):
        return self.controller.execute_workbuddy_fallback(
            task_id=self.task_id,
            goal="plan safely",
            data_classification="INTERNAL",
            lease=self.lease,
            context_fence=self.capsule["context_fence"],
        )

    def test_missing_preauthorization_denies_without_minting_or_real_effect(self):
        before_auth = self._count("authorizations")
        before_nonces = self._count("decision_nonces")
        with self.assertRaises(GateDenied):
            self._fallback()
        self.assertEqual(self._count("authorizations"), before_auth)
        self.assertEqual(self._count("decision_nonces"), before_nonces)
        self.assertEqual(self.controller.runtime.real_effect_count, 0)

    def test_scoped_authorization_cannot_mint_nonce_grant_and_execute_for_itself(self):
        with self.assertRaises(GateDenied):
            self.controller.scoped_authorization(
                task_id=self.task_id,
                provider="WorkBuddy",
                destination="WorkBuddy",
                purpose="goal-planning",
                effect_type="AI_MESSAGE",
                data_classes=["INTERNAL"],
                max_effect_count=1,
                user_decision_reference="controller-self-grant-attempt",
            )
        self.assertEqual(self._count("decision_nonces"), 0)
        self.assertEqual(self._count("authorizations"), 0)
        self.assertEqual(self.controller.runtime.real_effect_count, 0)

    def test_valid_preauthorization_is_consumed_without_creating_another_authorization(self):
        authorization = self._preauthorize()
        before_auth = self._count("authorizations")
        result = self._fallback()
        self.assertEqual(self._count("authorizations"), before_auth)
        self.assertEqual(result["reservation"].status, "RESERVATION_COMMITTED")
        self.assertEqual(result["reservation"].deduplicated, False)
        self.assertEqual(self.controller.runtime.real_effect_count, 1)
        row = self.store.connection.execute(
            "SELECT authorization_id FROM reservations WHERE action_id=?",
            (result["reservation"].action_id,),
        ).fetchone()
        self.assertEqual(row["authorization_id"], authorization["authorization_id"])

    def _assert_scope_mismatch_denied(self, **kwargs) -> None:
        self._preauthorize(**kwargs)
        before_auth = self._count("authorizations")
        with self.assertRaises(GateDenied):
            self._fallback()
        self.assertEqual(self._count("authorizations"), before_auth)
        self.assertEqual(self.controller.runtime.real_effect_count, 0)

    def test_preauthorization_provider_mismatch_denies_without_replacement_grant(self):
        self._assert_scope_mismatch_denied(provider="OtherProvider")

    def test_preauthorization_resource_mismatch_denies_without_replacement_grant(self):
        self._assert_scope_mismatch_denied(resource="other-resource")

    def test_preauthorization_purpose_mismatch_denies_without_replacement_grant(self):
        self._assert_scope_mismatch_denied(purpose="other-purpose")

    def test_preauthorization_identity_mismatch_denies_without_replacement_grant(self):
        self._assert_scope_mismatch_denied(identity="other-controller")

    def test_revocation_between_reserve_and_execute_is_rechecked(self):
        self._preauthorize()
        before_auth = self._count("authorizations")
        original_reserve = self.store.reserve_effect

        def reserve_then_revoke(*args, **kwargs):
            reservation = original_reserve(*args, **kwargs)
            self.store.revoke_authorization(
                kwargs["authorization_id"],
                reason="v09-test-revoke-between-reserve-and-execute",
            )
            return reservation

        self.store.reserve_effect = reserve_then_revoke  # type: ignore[method-assign]
        with self.assertRaises(GateDenied):
            self._fallback()
        self.assertEqual(self._count("authorizations"), before_auth)
        self.assertEqual(self.controller.runtime.real_effect_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
