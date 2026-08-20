from __future__ import annotations

import copy
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
import sys

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aicontrol.controller import Controller, validate_reviewer_envelope  # noqa: E402
from aicontrol.runtimes import RuntimeFailure  # noqa: E402
from aicontrol.store import GateDenied, validate_actor_trajectory  # noqa: E402
from aicontrol.util import read_json, sha256_text, tree_manifest, utc_now, write_json  # noqa: E402


class M05ControllerFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="aicontrol-m05-")
        self.root = Path(self.temporary.name)
        config = copy.deepcopy(read_json(ROOT / "config" / "production.json"))
        config["code_root"] = str(ROOT)
        config["state_root"] = str(self.root / "state")
        config["output_root"] = str(self.root / "output")
        config["release_root"] = str(self.root / "release")
        config["evidence_root"] = str(self.root / "evidence")
        config["database_path"] = str(self.root / "state" / "control.db")
        self.config_path = self.root / "config.json"
        write_json(self.config_path, config)
        self.controller = Controller(self.config_path)
        self.controller.store.set_meta("tcb_status", "VERIFIED")
        self.controller.store.set_meta("authority_status", "VERIFIED")
        self.task = self.controller.bootstrap_task(
            goal="M0.5 adversarial fixture",
            expected_final_artifact="fixture",
            acceptance_criteria=["A01"],
            data_classification="PUBLIC",
        )
        self.task_id = self.task["task_id"]
        self.context_fence = self.task["context_fence"]
        self.goal = self.controller.store.latest_goal(self.task_id)
        _, self.artifact_digest, _ = tree_manifest(ROOT)

    def tearDown(self) -> None:
        self.controller.close()
        self.temporary.cleanup()

    def authorization(self, *, provider: str = "test-provider", purpose: str = "unit-effect") -> dict:
        return self.controller.scoped_authorization(
            task_id=self.task_id,
            provider=provider,
            destination=provider,
            purpose=purpose,
            effect_type="AI_MESSAGE",
            data_classes=["PUBLIC"],
            max_effect_count=1,
            user_decision_reference="m05-unit",
        )

    def intent(self, *, provider: str = "test-provider", slot: str = "M05_TEST") -> dict:
        return {
            "task_id": self.task_id,
            "operation": "TEST_EXTERNAL_EFFECT",
            "provider": provider,
            "destination": provider,
            "expected_account": "credential-ref:test",
            "resource": "test",
            "payload_hash": sha256_text("payload"),
            "critical_params": {},
            "purpose": "unit-effect",
            "logical_effect_slot": slot,
            "retry_semantics": "RECONCILE_REQUIRED",
            "impact": "LOW",
            "reversibility": "REVERSIBLE",
            "effect_scope": "EXTERNAL",
        }

    def acceptance_manifest(self, *, cases: list[dict] | None = None, task_id: str | None = None) -> tuple[Path, str]:
        task_id = task_id or self.task_id
        if cases is None:
            execution_id = str(uuid.uuid4())
            record = {
                "test_execution_id": execution_id,
                "case_id": "A01",
                "definition_version": "M0.5/UNIT",
                "task_id": self.task_id,
                "goal_contract_hash": self.goal["contract_hash"],
                "state_revision": self.controller.store.state_head(),
                "tested_artifact_digest": self.artifact_digest,
                "controller_instance_id": self.controller.controller_instance_id,
                "process_browser_identity": "controller:unit",
                "invocation": {"authority": "CONTROLLER_OWNED_EXECUTION"},
                "started_at": utc_now(),
                "finished_at": utc_now(),
                "exit_or_observed_result": "PASS",
                "evidence": [],
                "evidence_hashes": {},
                "verification_status": "VERIFIED",
                "requirement_class": "REQUIRED",
            }
            self.controller.store.record_test(record)
            cases = [
                {
                    "case_id": "A01",
                    "requirement_class": "REQUIRED",
                    "result": "PASS",
                    "test_execution_id": execution_id,
                    "evidence_hashes": {},
                    "tested_artifact_digest": self.artifact_digest,
                }
            ]
        manifest = {
            "schema_version": 1,
            "definition_version": "M0.5/UNIT",
            "task_id": task_id,
            "goal_contract_hash": self.goal["contract_hash"],
            "state_revision": self.controller.store.state_head(),
            "context_fence": self.context_fence,
            "tested_artifact_digest": self.artifact_digest,
            "cases": cases,
            "known_blocking_defects": 0,
            "known_core_path_defects": 0,
            "final_status": "READY_FOR_USER_ACCEPTANCE",
        }
        path = self.root / f"acceptance-{uuid.uuid4().hex}.json"
        write_json(path, manifest)
        from aicontrol.util import sha256_file

        digest = sha256_file(path)
        evidence_id = self.controller.store.record_evidence(
            task_id=self.task_id,
            classification="INTERNAL",
            kind="ACCEPTANCE_MANIFEST",
            path=str(path),
            sha256=digest,
            metadata={
                "schema_version": 1,
                "goal_contract_hash": manifest["goal_contract_hash"],
                "state_revision": manifest["state_revision"],
                "context_fence": manifest["context_fence"],
                "tested_artifact_digest": manifest["tested_artifact_digest"],
            },
        )
        return path, evidence_id

    def canonical_review(self, acceptance_evidence_id: str) -> Path:
        lease = self.controller.acquire_lease()
        authorization = self.authorization(provider="TestReviewer", purpose="release-review")
        intent = self.intent(provider="TestReviewer", slot=f"M05_REVIEW_{uuid.uuid4().hex}")
        intent["purpose"] = "release-review"

        def adapter(_):
            receipt = self.controller.runtime._invocation(
                task_id=self.task_id,
                actor_id="reviewer-test",
                actor_type="BRAIN",
                trust_class="SANDBOXED",
                capability={"allowed_effects": ["ACTION_PROPOSAL"]},
                context_fence=self.context_fence,
                result_channel="memory",
            )
            envelope = {
                "schema_version": 1,
                "invocation_id": receipt["invocation_id"],
                "request_nonce": receipt["request_nonce"],
                "task_id": self.task_id,
                "goal_contract_hash": self.goal["contract_hash"],
                "request_state_revision": receipt["state_revision"],
                "request_context_fence": self.context_fence,
                "artifact_digest": self.artifact_digest,
                "acceptance_evidence_id": acceptance_evidence_id,
                "status": "DONE",
                "role": "REVIEWER",
                "verdict": "PASS",
                "findings": [],
                "recommended_actions": [],
                "human_readable_content": "unit PASS",
            }
            source = {"actor_id": "reviewer-test", "process_start_identity": "unit"}
            verification = self.controller.store.verify_and_record_result(receipt["invocation_id"], envelope, source)
            return {"envelope": envelope, "source_binding": source, "verification": verification}

        effect = self.controller.execute_effect(
            task_id=self.task_id,
            lease=lease,
            authorization_id=authorization["authorization_id"],
            context_fence=self.context_fence,
            resource_id=f"review:{uuid.uuid4()}",
            resource_hash=sha256_text("review"),
            intent=intent,
            adapter=adapter,
            egress_permitted=True,
        )
        reservation = effect["reservation"]
        envelope = effect["adapter_result"]["envelope"]
        document = {
            "schema_version": 1,
            "task_id": self.task_id,
            "goal_contract_hash": self.goal["contract_hash"],
            "state_revision": self.controller.store.state_head(),
            "context_fence": self.context_fence,
            "artifact_digest": self.artifact_digest,
            "acceptance_evidence_id": acceptance_evidence_id,
            "reviews": [
                {
                    "schema_version": 1,
                    "reviewer": "reviewer-test",
                    "provider": "TestReviewer",
                    "task_id": self.task_id,
                    "goal_contract_hash": self.goal["contract_hash"],
                    "state_revision": self.controller.store.state_head(),
                    "context_fence": self.context_fence,
                    "artifact_digest": self.artifact_digest,
                    "verdict": "PASS",
                    "findings": [],
                    "result_id": effect["adapter_result"]["verification"]["result_id"],
                    "invocation_id": envelope["invocation_id"],
                    "action_id": reservation.action_id,
                    "logical_effect_id": reservation.logical_effect_id,
                }
            ],
        }
        path = self.root / "reviews.json"
        write_json(path, document)
        from aicontrol.util import sha256_file

        self.controller.store.record_evidence(
            task_id=self.task_id,
            classification="INTERNAL",
            kind="INDEPENDENT_REVIEW_MANIFEST",
            path=str(path),
            sha256=sha256_file(path),
            metadata={
                "schema_version": 1,
                "goal_contract_hash": self.goal["contract_hash"],
                "state_revision": self.controller.store.state_head(),
                "context_fence": self.context_fence,
                "artifact_digest": self.artifact_digest,
                "acceptance_evidence_id": acceptance_evidence_id,
            },
        )
        return path

    def test_empty_acceptance_cannot_vacuously_pass(self) -> None:
        acceptance, _ = self.acceptance_manifest(cases=[])
        with self.assertRaises(GateDenied):
            self.controller.validate_acceptance_manifest(
                task_id=self.task_id,
                acceptance_manifest_path=acceptance,
                artifact_digest=self.artifact_digest,
            )

    def test_cross_task_acceptance_is_rejected(self) -> None:
        acceptance, _ = self.acceptance_manifest(task_id=f"other-{uuid.uuid4()}")
        with self.assertRaises(GateDenied):
            self.controller.validate_acceptance_manifest(
                task_id=self.task_id,
                acceptance_manifest_path=acceptance,
                artifact_digest=self.artifact_digest,
            )

    def test_cross_digest_acceptance_is_rejected(self) -> None:
        acceptance, _ = self.acceptance_manifest()
        document = read_json(acceptance)
        document["tested_artifact_digest"] = "0" * 64
        write_json(acceptance, document)
        from aicontrol.util import sha256_file

        self.controller.store.record_evidence(
            task_id=self.task_id,
            classification="INTERNAL",
            kind="ACCEPTANCE_MANIFEST",
            path=str(acceptance),
            sha256=sha256_file(acceptance),
            metadata={
                "schema_version": 1,
                "goal_contract_hash": document["goal_contract_hash"],
                "state_revision": document["state_revision"],
                "context_fence": document["context_fence"],
                "tested_artifact_digest": document["tested_artifact_digest"],
            },
        )
        with self.assertRaises(GateDenied):
            self.controller.validate_acceptance_manifest(
                task_id=self.task_id,
                acceptance_manifest_path=acceptance,
                artifact_digest=self.artifact_digest,
            )

    def test_forged_test_execution_is_rejected(self) -> None:
        cases = [
            {
                "case_id": "A01",
                "requirement_class": "REQUIRED",
                "result": "PASS",
                "test_execution_id": "forged",
                "evidence_hashes": {},
                "tested_artifact_digest": self.artifact_digest,
            }
        ]
        acceptance, _ = self.acceptance_manifest(cases=cases)
        with self.assertRaises(GateDenied):
            self.controller.validate_acceptance_manifest(
                task_id=self.task_id,
                acceptance_manifest_path=acceptance,
                artifact_digest=self.artifact_digest,
            )

    def test_forged_review_result_is_rejected(self) -> None:
        acceptance_path, acceptance_evidence_id = self.acceptance_manifest()
        acceptance, _ = self.controller.validate_acceptance_manifest(
            task_id=self.task_id,
            acceptance_manifest_path=acceptance_path,
            artifact_digest=self.artifact_digest,
        )
        review_path = self.canonical_review(acceptance_evidence_id)
        document = read_json(review_path)
        document["reviews"][0]["result_id"] = "forged-result"
        write_json(review_path, document)
        from aicontrol.util import sha256_file

        self.controller.store.record_evidence(
            task_id=self.task_id,
            classification="INTERNAL",
            kind="INDEPENDENT_REVIEW_MANIFEST",
            path=str(review_path),
            sha256=sha256_file(review_path),
            metadata={
                "schema_version": 1,
                "goal_contract_hash": self.goal["contract_hash"],
                "state_revision": self.controller.store.state_head(),
                "context_fence": self.context_fence,
                "artifact_digest": self.artifact_digest,
                "acceptance_evidence_id": acceptance_evidence_id,
            },
        )
        with self.assertRaises(GateDenied):
            self.controller.validate_review_manifest(
                task_id=self.task_id,
                review_manifest_path=review_path,
                acceptance=acceptance,
                acceptance_evidence_id=acceptance_evidence_id,
                artifact_digest=self.artifact_digest,
            )

    def test_canonical_acceptance_and_review_chain_validates(self) -> None:
        acceptance_path, acceptance_evidence_id = self.acceptance_manifest()
        acceptance, _ = self.controller.validate_acceptance_manifest(
            task_id=self.task_id,
            acceptance_manifest_path=acceptance_path,
            artifact_digest=self.artifact_digest,
        )
        review_path = self.canonical_review(acceptance_evidence_id)
        document, _ = self.controller.validate_review_manifest(
            task_id=self.task_id,
            review_manifest_path=review_path,
            acceptance=acceptance,
            acceptance_evidence_id=acceptance_evidence_id,
            artifact_digest=self.artifact_digest,
        )
        self.assertEqual(document["reviews"][0]["verdict"], "PASS")

    def test_empty_review_set_cannot_vacuously_pass(self) -> None:
        acceptance_path, acceptance_evidence_id = self.acceptance_manifest()
        acceptance, _ = self.controller.validate_acceptance_manifest(
            task_id=self.task_id,
            acceptance_manifest_path=acceptance_path,
            artifact_digest=self.artifact_digest,
        )
        review_path = self.canonical_review(acceptance_evidence_id)
        document = read_json(review_path)
        document["reviews"] = []
        write_json(review_path, document)
        from aicontrol.util import sha256_file

        self.controller.store.record_evidence(
            task_id=self.task_id,
            classification="INTERNAL",
            kind="INDEPENDENT_REVIEW_MANIFEST",
            path=str(review_path),
            sha256=sha256_file(review_path),
            metadata={
                "schema_version": 1,
                "goal_contract_hash": document["goal_contract_hash"],
                "state_revision": document["state_revision"],
                "context_fence": document["context_fence"],
                "artifact_digest": document["artifact_digest"],
                "acceptance_evidence_id": document["acceptance_evidence_id"],
            },
        )
        with self.assertRaises(GateDenied):
            self.controller.validate_review_manifest(
                task_id=self.task_id,
                review_manifest_path=review_path,
                acceptance=acceptance,
                acceptance_evidence_id=acceptance_evidence_id,
                artifact_digest=self.artifact_digest,
            )

    def test_malformed_adapter_result_finishes_unknown(self) -> None:
        lease = self.controller.acquire_lease()
        authorization = self.authorization()
        with self.assertRaises(RuntimeFailure):
            self.controller.execute_effect(
                task_id=self.task_id,
                lease=lease,
                authorization_id=authorization["authorization_id"],
                context_fence=self.context_fence,
                resource_id="malformed-adapter",
                resource_hash=sha256_text("malformed"),
                intent=self.intent(slot="MALFORMED"),
                adapter=lambda _: None,
                egress_permitted=True,
            )
        row = self.controller.store.connection.execute(
            "SELECT status FROM actions WHERE task_id=? AND logical_effect_slot='MALFORMED'", (self.task_id,)
        ).fetchone()
        self.assertEqual(row["status"], "OUTCOME_UNKNOWN")

    def test_workbuddy_fallback_has_own_authorization_and_effect_wal(self) -> None:
        lease = self.controller.acquire_lease()
        with mock.patch.object(
            self.controller.runtime,
            "invoke_workbuddy_brain",
            return_value={"envelope": {"status": "DONE"}},
        ):
            effect = self.controller.execute_workbuddy_fallback(
                task_id=self.task_id,
                goal="public fallback fixture",
                data_classification="PUBLIC",
                lease=lease,
                context_fence=self.context_fence,
            )
        reservation = effect["reservation"]
        reservation_row = self.controller.store.connection.execute(
            "SELECT authorization_id FROM reservations WHERE logical_effect_id=?", (reservation.logical_effect_id,)
        ).fetchone()
        auth = self.controller.store.connection.execute(
            "SELECT provider,purpose,status FROM authorizations WHERE authorization_id=?",
            (reservation_row["authorization_id"],),
        ).fetchone()
        action = self.controller.store.connection.execute(
            "SELECT provider,status FROM actions WHERE action_id=?", (reservation.action_id,)
        ).fetchone()
        wal = self.controller.store.connection.execute(
            "SELECT COUNT(*) AS n FROM effect_wal WHERE action_id=?", (reservation.action_id,)
        ).fetchone()["n"]
        self.assertEqual((auth["provider"], auth["purpose"]), ("WorkBuddy", "goal-planning"))
        self.assertEqual((action["provider"], action["status"]), ("WorkBuddy", "ACTION_COMMITTED"))
        self.assertGreaterEqual(wal, 3)

    def test_primary_exception_does_not_invoke_fallback(self) -> None:
        with (
            mock.patch("aicontrol.controller.verify_tcb", return_value={"status": "VERIFIED"}),
            mock.patch.object(self.controller.runtime, "register_defaults"),
            mock.patch.object(self.controller.runtime, "invoke_browser", side_effect=RuntimeFailure("primary failed")),
            mock.patch.object(self.controller.runtime, "invoke_workbuddy_brain") as fallback,
        ):
            with self.assertRaises(RuntimeFailure):
                self.controller.run_goal("public controlled failure", data_classification="PUBLIC")
        fallback.assert_not_called()
        row = self.controller.store.connection.execute(
            "SELECT status FROM actions WHERE provider='ChatGPT' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(row["status"], "OUTCOME_UNKNOWN")


class M05PureInvariantTests(unittest.TestCase):
    def reviewer(self) -> dict:
        return {
            "schema_version": 1,
            "invocation_id": "i",
            "request_nonce": "n",
            "task_id": "t",
            "goal_contract_hash": "g",
            "request_state_revision": 1,
            "request_context_fence": "c",
            "artifact_digest": "a",
            "acceptance_evidence_id": "e",
            "status": "DONE",
            "role": "REVIEWER",
            "verdict": "PASS",
            "findings": [],
            "recommended_actions": [],
            "human_readable_content": "ok",
        }

    def test_reviewer_missing_findings_is_fail_closed(self) -> None:
        envelope = self.reviewer()
        del envelope["findings"]
        with self.assertRaises(GateDenied):
            validate_reviewer_envelope(
                envelope,
                task_id="t",
                goal_contract_hash="g",
                state_revision=1,
                context_fence="c",
                artifact_digest="a",
                acceptance_evidence_id="e",
            )

    def test_reviewer_pass_with_findings_is_rejected(self) -> None:
        envelope = self.reviewer()
        envelope["findings"] = ["not actually pass"]
        with self.assertRaises(GateDenied):
            validate_reviewer_envelope(
                envelope,
                task_id="t",
                goal_contract_hash="g",
                state_revision=1,
                context_fence="c",
                artifact_digest="a",
                acceptance_evidence_id="e",
            )

    def test_actor_cannot_claim_product_done_or_change_goal(self) -> None:
        with self.assertRaises(GateDenied):
            validate_actor_trajectory("WORKER", {"status": "PRODUCT_DONE"})
        with self.assertRaises(GateDenied):
            validate_actor_trajectory(
                "WORKER",
                {"status": "RUNNING", "action_proposals": [{"operation": "CHANGE_HIGHEST_GOAL"}]},
            )

    def test_worker_done_requires_evidence_delta(self) -> None:
        with self.assertRaises(GateDenied):
            validate_actor_trajectory(
                "WORKER",
                {"status": "DONE", "artifact_paths": ["x"], "artifact_hashes": {"x": "digest"}},
            )


if __name__ == "__main__":
    unittest.main()
