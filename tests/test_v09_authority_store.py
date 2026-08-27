from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aicontrol.security import (  # noqa: E402
    authority_scope_allowed,
    egress_allowed,
    human_gate_allowed,
    require_credential_isolation,
)
from aicontrol.store import ControlStore, GateDenied  # noqa: E402


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
