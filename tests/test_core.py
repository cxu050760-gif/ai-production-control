from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aicontrol.controller import worker_result_is_delivery_candidate  # noqa: E402
from aicontrol.store import ControlStore, GateDenied  # noqa: E402
from aicontrol.util import BoundaryError, safe_resolve, sha256_text, utc_now  # noqa: E402


class StoreFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="aicontrol-test-")
        self.root = Path(self.temporary.name)
        self.store = ControlStore(self.root / "control.db", state_root=self.root / "state")
        self.store.set_meta("tcb_status", "VERIFIED")
        self.task_id = f"task-{uuid.uuid4()}"
        self.goal = self.store.create_goal_contract(
            self.task_id,
            {
                "goal": "unit fixture",
                "expected_final_artifact": "fixture",
                "acceptance_criteria": ["safe"],
                "non_goals": [],
                "constraints": [],
                "network_permission": "ALLOW_SCOPED",
                "installation_permission": "DENY",
                "data_egress_policy": {"test": ["PUBLIC"], "default": []},
                "external_side_effect_policy": "SCOPED_AUTHORIZATION_REQUIRED",
                "parallelism_policy": {},
                "user_acceptance_method": "unit test",
                "inferred_defaults": {},
                "resource_budget": {},
                "resource_scope": [str(self.root)],
            },
            change_reason="UNIT",
        )
        self.capsule = self.store.create_context_capsule(self.task_id, "UNIT", {})

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def authorization(self, maximum: int = 1) -> dict:
        scope = {
            "provider": "test-provider",
            "destination": "test",
            "purpose": "unit-effect",
            "effect_type": "TEST",
            "data_classes": ["PUBLIC"],
        }
        nonce = self.store.issue_decision_nonce(self.task_id, scope, user_decision_reference="unit")
        return self.store.grant_authorization(
            self.task_id,
            nonce["decision_nonce"],
            scope,
            provider="test-provider",
            resource="test",
            purpose="unit-effect",
            effect_type="TEST",
            max_effect_count=maximum,
        )

    def lease_and_lock(self) -> tuple[str, dict]:
        controller_id = f"controller-{uuid.uuid4()}"
        lease = self.store.acquire_controller_lease(
            controller_id,
            pid=os.getpid(),
            process_start_identity=uuid.uuid4().hex,
            ttl_seconds=300,
        )
        self.store.acquire_lock(
            "unit:resource",
            controller_instance_id=controller_id,
            owner="unit",
            pid=os.getpid(),
            process_start_identity="unit",
            ttl_seconds=300,
        )
        return controller_id, lease

    def intent(self) -> dict:
        return {
            "task_id": self.task_id,
            "operation": "TEST_EXTERNAL_WRITE",
            "provider": "test-provider",
            "destination": "test",
            "expected_account": "test",
            "resource": "unit",
            "payload_hash": sha256_text("payload"),
            "critical_params": {},
            "purpose": "unit-effect",
            "logical_effect_slot": "slot",
            "retry_semantics": "RECONCILE_REQUIRED",
            "impact": "LOW",
            "reversibility": "REVERSIBLE",
            "effect_scope": "EXTERNAL",
        }

    def test_canonical_state_is_hash_verified(self) -> None:
        state = self.store.read_state()
        state["unit"] = True
        revision = self.store.commit_state(state, reason="UNIT_COMMIT")
        self.assertTrue(self.store.read_revision(revision)["unit"])

    def test_atomic_reservation_deduplicates_logical_effect(self) -> None:
        auth = self.authorization()
        controller_id, lease = self.lease_and_lock()
        values = []
        for _ in range(2):
            values.append(
                self.store.reserve_effect(
                    self.intent(),
                    controller_instance_id=controller_id,
                    controller_lease_id=lease["lease_id"],
                    authorization_id=auth["authorization_id"],
                    context_fence=self.capsule["context_fence"],
                    resource_id="unit:resource",
                    resource_hash=sha256_text("resource"),
                    capability_permitted=True,
                    egress_permitted=True,
                    resource_fresh=True,
                )
            )
        self.assertFalse(values[0].deduplicated)
        self.assertTrue(values[1].deduplicated)
        self.assertEqual(values[0].action_id, values[1].action_id)

    def test_stale_result_is_rejected(self) -> None:
        invocation = {
            "invocation_id": str(uuid.uuid4()),
            "request_nonce": uuid.uuid4().hex,
            "expected_actor_id": "unit-worker",
            "actor_type": "WORKER",
            "task_id": self.task_id,
            "goal_contract_hash": self.goal["hash"],
            "state_revision": self.store.state_head(),
            "context_fence": self.capsule["context_fence"],
            "trust_class": "BROKERED",
            "capability": {},
            "result_channel": "memory",
            "process_session_identity": "planned",
            "created_at": utc_now(),
            "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
            "status": "CREATED",
        }
        self.store.record_invocation(invocation)
        state = self.store.read_state()
        state["changed"] = True
        self.store.commit_state(state, reason="STALE_INVOCATION")
        envelope = {
            "invocation_id": invocation["invocation_id"],
            "request_nonce": invocation["request_nonce"],
            "task_id": self.task_id,
            "goal_contract_hash": self.goal["hash"],
            "request_state_revision": invocation["state_revision"],
            "request_context_fence": invocation["context_fence"],
        }
        with self.assertRaises(GateDenied):
            self.store.verify_and_record_result(
                invocation["invocation_id"], envelope, {"actor_id": "unit-worker"}
            )


class BoundaryTests(unittest.TestCase):
    def test_path_boundary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aicontrol-path-") as temporary:
            root = Path(temporary).resolve()
            inside = root / "safe.txt"
            inside.write_text("ok", encoding="utf-8")
            self.assertEqual(safe_resolve(inside, [root], must_exist=True), inside)
            with self.assertRaises(BoundaryError):
                safe_resolve(root / ".." / "escape.txt", [root])
            with self.assertRaises(BoundaryError):
                safe_resolve("relative.txt", [root])


class DeliveryContractTests(unittest.TestCase):
    def test_capability_probe_cannot_claim_goal_delivery(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aicontrol-delivery-") as temporary:
            artifact = Path(temporary) / "artifact.md"
            artifact.write_text("probe only", encoding="utf-8")
            digest = sha256_text("probe only")
            envelope = {
                "status": "DONE",
                "execution_class": "CAPABILITY_PROBE",
                "goal_satisfied": False,
                "artifact_hashes": {str(artifact): digest},
            }
            self.assertFalse(worker_result_is_delivery_candidate(envelope, artifact, digest))

    def test_general_goal_claim_is_only_a_digest_bound_delivery_candidate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aicontrol-delivery-") as temporary:
            artifact = Path(temporary) / "artifact.md"
            artifact.write_text("completed result", encoding="utf-8")
            digest = sha256_text("completed result")
            envelope = {
                "status": "DONE",
                "execution_class": "GENERAL_GOAL_EXECUTION",
                "goal_satisfied": True,
                "artifact_hashes": {str(artifact): digest},
            }
            self.assertTrue(worker_result_is_delivery_candidate(envelope, artifact, digest))
            self.assertFalse(worker_result_is_delivery_candidate(envelope, artifact, "wrong-digest"))


if __name__ == "__main__":
    unittest.main()
