from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .runtimes import RuntimeFailure, RuntimeManager
from .pipeline import GoalPipeline
from .lineage import LineageError, PromotionRequiresReview, StableLineage


class IndependentReviewAdapter:
    """Authoritative independent-review adapter - the ONLY writer of durable
    review records. In production this consumes an R-PROD outcome via the
    Runtime V1 transport; a plain caller cannot mint a PASS here because the
    record is bound to an ACTIVE Candidate and stores the ACTUAL verdict."""
    def __init__(self, store: "ControlStore") -> None:
        self._store = store

    def record(self, *, candidate_record_id: str, reviewer_identity: str,
               review_source: str, verdict: str) -> dict[str, Any]:
        ready = False
        for entry in self._store.registry("reviewer_registry"):
            if entry.get("reviewer_id") == reviewer_identity:
                role = str(entry.get("role") or "").upper()
                availability = str(entry.get("availability") or entry.get("health") or "").upper()
                ready = role == "R_PROD" and availability in ("AVAILABLE", "VERIFIED")
                break
        if not ready:
            raise PromotionRequiresReview(f"reviewer {reviewer_identity!r} is not a ready R_PROD reviewer")
        return StableLineage(self._store).record_review(
            candidate_record_id=candidate_record_id,
            reviewer_identity=reviewer_identity,
            review_source=review_source,
            verdict=verdict,
        )
from .security import authority_scope_allowed, browser_profile_identity, egress_allowed, seal_tcb, verify_tcb
from .store import (
    AuthorityStateUncertain,
    ControlStore,
    GateDenied,
    Reservation,
    StorageDurabilityUnavailable,
)
from .util import canonical_json, is_expired, read_json, sha256_file, sha256_text, tree_manifest, utc_now, windows_boot_session_id, write_json


def worker_result_is_delivery_candidate(envelope: dict[str, Any], artifact: Path, artifact_digest: str) -> bool:
    """Validate a Worker's delivery claim without promoting that claim to canonical fact."""
    return (
        envelope.get("status") == "DONE"
        and envelope.get("execution_class") == "GENERAL_GOAL_EXECUTION"
        and envelope.get("goal_satisfied") is True
        and artifact.is_file()
        and artifact.stat().st_size > 0
        and envelope.get("artifact_hashes", {}).get(str(artifact)) == artifact_digest
    )


def validate_reviewer_envelope(
    envelope: dict[str, Any],
    *,
    task_id: str,
    goal_contract_hash: str,
    state_revision: int,
    context_fence: str,
    artifact_digest: str,
    acceptance_evidence_id: str,
) -> None:
    required = {
        "schema_version",
        "invocation_id",
        "request_nonce",
        "task_id",
        "goal_contract_hash",
        "request_state_revision",
        "request_context_fence",
        "artifact_digest",
        "acceptance_evidence_id",
        "status",
        "role",
        "verdict",
        "findings",
        "recommended_actions",
        "human_readable_content",
    }
    if not isinstance(envelope, dict) or not required.issubset(envelope):
        raise GateDenied("Reviewer envelope is incomplete")
    if envelope["schema_version"] != 1 or envelope["status"] != "DONE" or envelope["role"] != "REVIEWER":
        raise GateDenied("Reviewer envelope schema/status/role rejected")
    if envelope["task_id"] != task_id or envelope["goal_contract_hash"] != goal_contract_hash:
        raise GateDenied("Reviewer task/Goal binding mismatch")
    if envelope["request_state_revision"] != state_revision or envelope["request_context_fence"] != context_fence:
        raise GateDenied("Reviewer state/context binding mismatch")
    if envelope["artifact_digest"] != artifact_digest or envelope["acceptance_evidence_id"] != acceptance_evidence_id:
        raise GateDenied("Reviewer artifact/acceptance Evidence binding mismatch")
    if envelope["verdict"] not in ("PASS", "REWORK", "BLOCKED"):
        raise GateDenied("Reviewer verdict is invalid")
    if not isinstance(envelope["findings"], list) or not all(isinstance(item, str) for item in envelope["findings"]):
        raise GateDenied("Reviewer findings must be an explicit string list")
    if not isinstance(envelope["recommended_actions"], list) or not all(
        isinstance(item, str) for item in envelope["recommended_actions"]
    ):
        raise GateDenied("Reviewer recommended_actions must be an explicit string list")
    if not isinstance(envelope["human_readable_content"], str):
        raise GateDenied("Reviewer human_readable_content must be explicit")
    if envelope["verdict"] == "PASS" and envelope["findings"]:
        raise GateDenied("Reviewer PASS cannot contain findings")


class Controller:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path).resolve(strict=True)
        self.config = read_json(self.config_path)
        self.code_root = Path(self.config["code_root"]).resolve(strict=True)
        self.state_root = Path(self.config["state_root"])
        self.output_root = Path(self.config["output_root"])
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.store = ControlStore(self.config["database_path"], state_root=self.state_root)
        self.controller_instance_id = f"controller-{uuid.uuid4()}"
        self.process_start_identity = sha256_text(f"{os.getpid()}:{time.time_ns()}:{self.code_root}")[:24]
        self.runtime = RuntimeManager(
            store=self.store,
            config=self.config,
            code_root=self.code_root,
            controller_instance_id=self.controller_instance_id,
        )
        self.review_adapter = IndependentReviewAdapter(self.store)

    def close(self) -> None:
        try:
            self.store.release_controller_lease(self.controller_instance_id)
        finally:
            self.store.close()

    def __enter__(self) -> "Controller":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def acquire_lease(self) -> dict[str, Any]:
        return self.store.acquire_controller_lease(
            self.controller_instance_id,
            pid=os.getpid(),
            process_start_identity=self.process_start_identity,
            ttl_seconds=int(self.config["policy"]["controller_lease_seconds"]),
        )

    def bootstrap_task(
        self,
        *,
        goal: str,
        expected_final_artifact: str,
        acceptance_criteria: list[str],
        data_classification: str = "PRIVATE_LOCAL",
        task_id: str | None = None,
    ) -> dict[str, Any]:
        task_id = task_id or f"task-{uuid.uuid4()}"
        contract = {
            "goal": goal,
            "expected_final_artifact": expected_final_artifact,
            "acceptance_criteria": acceptance_criteria,
            "non_goals": ["payment", "public publishing", "credential export", "destructive system changes"],
            "constraints": ["structured execution", "no secret egress", "same-user Windows limitation disclosed"],
            "quality_expectations": ["controller-observed tests", "digest-bound release", "zero known core defects"],
            "network_permission": "ALLOW_SCOPED",
            "installation_permission": "PINNED_LOW_RISK_ONLY",
            "data_egress_policy": {
                "chatgpt.com": ["PUBLIC", "INTERNAL"],
                "WorkBuddy": ["PUBLIC", "INTERNAL"],
                "Codex CLI": ["PUBLIC", "INTERNAL", "PRIVATE_LOCAL"],
                "public-web": ["PUBLIC"],
                "default": [],
            },
            "external_side_effect_policy": "SCOPED_AUTHORIZATION_REQUIRED",
            "parallelism_policy": {"max_workers": 5, "shared_write": "DENY"},
            "user_acceptance_method": "artifact review after READY_FOR_USER_ACCEPTANCE",
            "inferred_defaults": {"data_classification": data_classification, "browser_profile": "dedicated"},
            "resource_budget": self.config["policy"],
            "resource_scope": self.config["allowed_roots"],
        }
        result = self.store.create_goal_contract(task_id, contract, change_reason="CONTROLLED_RUN_ENTRY")
        capsule = self.store.create_context_capsule(
            task_id,
            "GOAL_COMMITTED",
            {
                "current_objective": goal,
                "completed_work": ["Goal Contract committed"],
                "next_required_steps": ["route Brain", "route Worker", "test", "review", "release"],
                "last_verified_state": result["state_revision"],
            },
        )
        return {**result, **capsule}

    def _require_existing_authorization(
        self,
        *,
        authorization_id: str,
        task_id: str,
        provider: str,
        resource: str,
        purpose: str,
        effect_type: str,
        identity: str,
        destination: str,
        data_classes: list[str],
    ) -> dict[str, Any]:
        if not authorization_id:
            raise GateDenied("pre-existing authorization id required")
        row = self.store.connection.execute(
            "SELECT * FROM authorizations WHERE authorization_id=? AND task_id=?",
            (authorization_id, task_id),
        ).fetchone()
        if not row:
            raise GateDenied("pre-existing authorization missing or wrong task")
        authorization = dict(row)
        try:
            scope = json.loads(authorization["scope_json"])
        except (TypeError, ValueError) as error:
            raise AuthorityStateUncertain("authorization scope is not reconstructable") from error
        if not isinstance(scope, dict):
            raise AuthorityStateUncertain("authorization scope is not an object")
        authorization["scope"] = scope
        if authorization["status"] != "ACTIVE":
            raise GateDenied("authorization revoked or inactive")
        if is_expired(authorization["expires_at"]):
            raise GateDenied("authorization expired")
        goal = self.store.latest_goal(task_id)
        if authorization["goal_contract_hash"] != goal["contract_hash"]:
            raise GateDenied("authorization bound to stale Goal Contract")
        epoch_row = self.store.connection.execute(
            "SELECT epoch FROM revocation_epochs WHERE task_id=?", (task_id,)
        ).fetchone()
        latest_epoch = int(epoch_row["epoch"]) if epoch_row else 0
        if int(authorization["revocation_epoch"]) != latest_epoch:
            raise GateDenied("authorization revocation epoch stale")
        reconstructed = self.store.reconstruct_authority(task_id)["authorizations"].get(authorization_id)
        if not reconstructed or reconstructed["status"] != "ACTIVE":
            raise AuthorityStateUncertain("authorization not reconstructable as ACTIVE from Authority Journal")
        if int(authorization["generation"]) != int(reconstructed["generation"]):
            raise AuthorityStateUncertain("authorization generation does not match durable Authority Journal")
        if int(authorization["consumed_effect_count"]) != int(reconstructed["consumed_effect_count"]):
            raise AuthorityStateUncertain("authorization consumption does not match durable Authority Journal")
        if int(authorization["consumed_effect_count"]) >= int(authorization["max_effect_count"]):
            raise GateDenied("authorization effect count exhausted")
        if authorization["effect_type"] != effect_type:
            raise GateDenied("authorization effect type mismatch")
        scoped_effect_type = scope.get("effect_type")
        if scoped_effect_type is not None and scoped_effect_type != effect_type:
            raise GateDenied("authorization scoped effect type mismatch")
        if not data_classes:
            raise GateDenied("authorization data classification binding missing")
        for classification in data_classes:
            if not authority_scope_allowed(
                authorization=authorization,
                task_id=task_id,
                provider=provider,
                resource=resource,
                purpose=purpose,
                identity=identity,
                destination=destination,
                classification=classification,
            ):
                raise GateDenied("authorization provider/resource/purpose/identity/data binding mismatch")
        return authorization

    def scoped_authorization(
        self,
        *,
        task_id: str,
        provider: str,
        destination: str,
        purpose: str,
        effect_type: str,
        data_classes: list[str],
        max_effect_count: int,
        user_decision_reference: str,
        resource: str | None = None,
        identity: str | None = None,
    ) -> dict[str, Any]:
        """Return a pre-existing scoped authorization; never mint or grant one.

        The compatibility arguments ``max_effect_count`` and
        ``user_decision_reference`` remain so existing Controller call sites do
        not become an implicit authority-creation API. They are intentionally
        not used to create authority.
        """
        del max_effect_count, user_decision_reference
        bound_resource = resource or destination
        bound_identity = identity or self.controller_instance_id
        rows = self.store.connection.execute(
            "SELECT authorization_id FROM authorizations WHERE task_id=? ORDER BY granted_at DESC",
            (task_id,),
        )
        for row in rows:
            try:
                return self._require_existing_authorization(
                    authorization_id=str(row["authorization_id"]),
                    task_id=task_id,
                    provider=provider,
                    resource=bound_resource,
                    purpose=purpose,
                    effect_type=effect_type,
                    identity=bound_identity,
                    destination=destination,
                    data_classes=data_classes,
                )
            except GateDenied:
                continue
        raise GateDenied("pre-existing scoped authorization required; Controller self-grant is forbidden")

    def execute_effect(
        self,
        *,
        task_id: str,
        lease: dict[str, Any],
        authorization_id: str,
        context_fence: str,
        resource_id: str,
        resource_hash: str,
        intent: dict[str, Any],
        adapter: Callable[[Reservation], dict[str, Any]],
        egress_permitted: bool,
        capability_permitted: bool = True,
        resource_fresh: bool = True,
        observed_account_identity: str | None = None,
    ) -> dict[str, Any]:
        if intent.get("task_id") != task_id:
            raise GateDenied("effect intent task binding mismatch")
        effect_type = str(intent.get("effect_type") or "")
        data_classification = str(intent.get("data_classification") or "")
        if not effect_type:
            raise GateDenied("effect intent type binding missing")
        if not data_classification:
            raise GateDenied("effect intent data classification binding missing")
        if not (capability_permitted and egress_permitted and resource_fresh):
            raise GateDenied("capability, egress, or resource precondition denied")
        self._require_existing_authorization(
            authorization_id=authorization_id,
            task_id=task_id,
            provider=str(intent.get("provider") or ""),
            resource=str(intent.get("resource") or ""),
            purpose=str(intent.get("purpose") or ""),
            effect_type=effect_type,
            identity=str(intent.get("executor_identity") or self.controller_instance_id),
            destination=str(intent.get("destination") or ""),
            data_classes=[data_classification],
        )
        expected_account = str(intent.get("expected_account", ""))
        if expected_account.startswith("profile-sha256:"):
            if observed_account_identity != expected_account.removeprefix("profile-sha256:"):
                raise GateDenied("expected account/profile identity mismatch: DO NOT EXECUTE")
        lock = self.store.acquire_lock(
            resource_id,
            controller_instance_id=self.controller_instance_id,
            owner=f"task:{task_id}",
            pid=os.getpid(),
            process_start_identity=self.process_start_identity,
            ttl_seconds=int(self.config["policy"]["lock_lease_seconds"]),
        )
        try:
            reservation = self.store.reserve_effect(
                intent,
                controller_instance_id=self.controller_instance_id,
                controller_lease_id=lease["lease_id"],
                authorization_id=authorization_id,
                context_fence=context_fence,
                resource_id=resource_id,
                resource_hash=resource_hash,
                capability_permitted=capability_permitted,
                egress_permitted=egress_permitted,
                resource_fresh=resource_fresh,
            )
            if reservation.deduplicated:
                if reservation.status in ("OUTCOME_UNKNOWN", "RECONCILING"):
                    # Same-instance ordinary retries are denied inside reserve_effect, so an
                    # unresolved dedup hit can only be a replay from a different controller
                    # instance (restart/recovery). Never present it as a settled dedup.
                    return {
                        "reservation": reservation,
                        "deduplicated": True,
                        "reconciliation_required": True,
                        "executed": False,
                        "adapter_result": None,
                    }
                return {"reservation": reservation, "deduplicated": True, "adapter_result": None}
            self.store.start_effect(
                reservation,
                controller_instance_id=self.controller_instance_id,
                controller_lease_id=lease["lease_id"],
                resource_fresh=resource_fresh,
            )
            try:
                adapter_result = adapter(reservation)
                if not isinstance(adapter_result, dict):
                    raise RuntimeFailure("adapter result must be an object")
                envelope = adapter_result.get("envelope")
                if not isinstance(envelope, dict) or not isinstance(envelope.get("status"), str):
                    raise RuntimeFailure("adapter result envelope/status is malformed")
                if expected_account.startswith("profile-sha256:"):
                    returned_identity = envelope.get("data", {}).get("profile_identity_hash")
                    if returned_identity != expected_account.removeprefix("profile-sha256:"):
                        raise GateDenied("browser returned a different account/profile identity")
                status = envelope["status"]
            except Exception as error:
                self.store.finish_effect(
                    reservation,
                    {"error_type": type(error).__name__, "message": str(error), "reconciliation_required": True},
                    unknown=True,
                )
                raise
            unknown = status in ("TIMEOUT", "UNKNOWN")
            self.store.finish_effect(reservation, {"adapter_status": status, "result": adapter_result}, unknown=unknown)
            return {"reservation": reservation, "deduplicated": False, "adapter_result": adapter_result, "unknown": unknown}
        finally:
            self.store.release_lock(resource_id, self.controller_instance_id)

    def reconcile_effect(
        self,
        *,
        reservation,
        probe=None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Reconcile an unresolved action against observed external reality.

        V09-R22 / V09-R23 / V09-R24. The conservative rules are inherited from the
        existing ``runtime/effect_safety_lite.reconcile_effect``: only an
        OUTCOME_UNKNOWN action may be reconciled, evidence is mandatory, ordinary
        retry is never permitted, and a negative observation is not replay
        authority. Nothing here ever executes an effect.
        """
        row = self.store.connection.execute(
            "SELECT status FROM actions WHERE action_id=?", (reservation.action_id,)
        ).fetchone()
        if not row or row["status"] != "OUTCOME_UNKNOWN":
            raise GateDenied("reconciliation requires an OUTCOME_UNKNOWN action")
        if evidence is not None and (not isinstance(evidence, dict) or not evidence):
            raise GateDenied("reconciliation evidence must be a non-empty object")
        observed = probe(reservation) if callable(probe) else (evidence or {}).get("observed_state")
        if observed is None or not str(observed).strip():
            raise GateDenied("reconciliation evidence missing: external reality was not observed")
        state = str(observed).strip().upper()

        if state not in ("SUCCEEDED", "NOT_OCCURRED"):
            # Indeterminate reality: stay unresolved and escalate. No new lawful
            # status is invented and no execution is upgraded (V14 §105/§118, §31 check 17).
            return {
                "status": "OUTCOME_UNKNOWN",
                "reconciliation": "INDETERMINATE_HUMAN_GATE_REQUIRED",
                "human_gate_required": True,
                "executed": False,
                "auto_retry_permitted": False,
                "ordinary_retry_permitted": False,
                "observed_state": state,
                "detail": (
                    "external reality is indeterminate; the action stays OUTCOME_UNKNOWN "
                    "and requires a Human Gate decision before any further effect"
                ),
            }

        occurred = state == "SUCCEEDED"
        record = dict(evidence or {})
        record.setdefault("observed_state", state)
        record.setdefault("reconciled_by", self.controller_instance_id)
        status = self.store.reconcile_effect_outcome(reservation, evidence=record, occurred=occurred)
        if occurred:
            return {
                "status": status,
                "reconciliation": "COMMITTED_NO_EXECUTE",
                "executed": False,
                "auto_retry_permitted": False,
                "ordinary_retry_permitted": False,
                "observed_state": state,
                "evidence": record,
            }
        return {
            "status": status,
            "reconciliation": "NOT_OCCURRED_CONTROLLED_RETRY_ONLY",
            "executed": False,
            "auto_retry_permitted": False,
            "ordinary_retry_permitted": False,
            "observed_state": state,
            "evidence": record,
            "detail": (
                "negative observation grants no replay authority; any retry requires a "
                "new explicit authorization and a new attempt"
            ),
        }

    def execute_workbuddy_fallback(
        self,
        *,
        task_id: str,
        goal: str,
        data_classification: str,
        lease: dict[str, Any],
        context_fence: str,
    ) -> dict[str, Any]:
        """Invoke the fallback Brain only with a pre-existing authorization."""
        provider = "WorkBuddy"
        purpose = "goal-planning"
        effect_resource = "fresh-workbuddy-session"
        authorization = self.scoped_authorization(
            task_id=task_id,
            provider=provider,
            destination=provider,
            purpose=purpose,
            effect_type="AI_MESSAGE",
            data_classes=[data_classification],
            max_effect_count=1,
            user_decision_reference=f"controlled-cli-fallback:{sha256_text(goal)}",
            resource=effect_resource,
            identity=self.controller_instance_id,
        )
        scope_row = self.store.connection.execute(
            "SELECT scope_json FROM authorizations WHERE authorization_id=?",
            (authorization["authorization_id"],),
        ).fetchone()
        allowed = egress_allowed(
            classification=data_classification,
            destination=provider,
            provider=provider,
            purpose=purpose,
            goal_contract=self.store.latest_goal(task_id),
            authorization_scope=json.loads(scope_row["scope_json"]),
        )
        intent = {
            "task_id": task_id,
            "operation": "INVOKE_PROPOSAL_ONLY_BRAIN",
            "provider": provider,
            "destination": provider,
            "expected_account": "credential-ref:workbuddy-existing-auth",
            "resource": effect_resource,
            "effect_type": "AI_MESSAGE",
            "data_classification": data_classification,
            "executor_identity": self.controller_instance_id,
            "payload_hash": sha256_text(goal),
            "critical_params": {"role": "FALLBACK"},
            "purpose": purpose,
            "logical_effect_slot": "FALLBACK_BRAIN_PLAN_WORKBUDDY",
            "retry_semantics": "RECONCILE_REQUIRED",
            "impact": "LOW",
            "reversibility": "PARTIALLY_REVERSIBLE",
            "effect_scope": "EXTERNAL",
        }
        effect = self.execute_effect(
            task_id=task_id,
            lease=lease,
            authorization_id=authorization["authorization_id"],
            context_fence=context_fence,
            resource_id="brain:workbuddy-fallback",
            resource_hash=sha256_text(provider),
            intent=intent,
            egress_permitted=allowed,
            adapter=lambda _: self.runtime.invoke_workbuddy_brain(
                task_id=task_id,
                context_fence=context_fence,
                prompt=f"Produce a concise proposal for: {goal}",
            ),
        )
        if effect.get("deduplicated"):
            raise AuthorityStateUncertain("fallback Brain Effect was deduplicated; reconcile its canonical outcome")
        if effect.get("unknown"):
            raise AuthorityStateUncertain("fallback Brain outcome is unknown; reconcile before any retry")
        if effect["adapter_result"]["envelope"]["status"] != "DONE":
            raise RuntimeFailure("fallback Brain did not produce a DONE result")
        return effect

    def run_goal(self, goal: str, *, data_classification: str = "PRIVATE_LOCAL") -> dict[str, Any]:
        lease = self.acquire_lease()
        self.runtime.register_defaults()
        task = self.bootstrap_task(
            goal=goal,
            expected_final_artifact="verified Markdown artifact",
            acceptance_criteria=["artifact exists", "artifact digest verified", "review completed", "release digest matches"],
            data_classification=data_classification,
        )
        task_id = task["task_id"]
        context_fence = task["context_fence"]
        brain_result = None
        brain_route = "LOCAL_ONLY"
        if data_classification in ("PUBLIC", "INTERNAL"):
            verify_tcb(self.store, self.code_root)
            effect_resource = "new-chat-session"
            auth = self.scoped_authorization(
                task_id=task_id,
                provider="ChatGPT",
                destination="chatgpt.com",
                purpose="goal-planning",
                effect_type="AI_MESSAGE",
                data_classes=[data_classification],
                max_effect_count=1,
                user_decision_reference=f"controlled-cli-run:{sha256_text(goal)}",
                resource=effect_resource,
                identity=self.controller_instance_id,
            )
            goal_contract = self.store.latest_goal(task_id)
            allowed = egress_allowed(
                classification=data_classification,
                destination="chatgpt.com",
                provider="ChatGPT",
                purpose="goal-planning",
                goal_contract=goal_contract,
                authorization_scope=json.loads(self.store.connection.execute("SELECT scope_json FROM authorizations WHERE authorization_id=?", (auth["authorization_id"],)).fetchone()["scope_json"]),
            )
            intent = {
                "task_id": task_id,
                "operation": "SEND_AI_MESSAGE",
                "provider": "ChatGPT",
                "destination": "chatgpt.com",
                "expected_account": f"profile-sha256:{browser_profile_identity(self.config['browser']['authenticated_profile'])}",
                "resource": effect_resource,
                "effect_type": "AI_MESSAGE",
                "data_classification": data_classification,
                "executor_identity": self.controller_instance_id,
                "payload_hash": sha256_text(goal),
                "critical_params": {"role": "MAIN"},
                "purpose": "goal-planning",
                "logical_effect_slot": "PRIMARY_BRAIN_PLAN",
                "retry_semantics": "RECONCILE_REQUIRED",
                "impact": "LOW",
                "reversibility": "PARTIALLY_REVERSIBLE",
                "effect_scope": "EXTERNAL",
            }
            effect = self.execute_effect(
                task_id=task_id,
                lease=lease,
                authorization_id=auth["authorization_id"],
                context_fence=context_fence,
                resource_id="browser:chatgpt-authenticated-profile",
                resource_hash=sha256_text(self.config["browser"]["authenticated_profile"]),
                intent=intent,
                egress_permitted=allowed,
                observed_account_identity=browser_profile_identity(self.config["browser"]["authenticated_profile"]),
                adapter=lambda reservation: self.runtime.invoke_browser(
                    task_id=task_id,
                    context_fence=context_fence,
                    command="chatgpt",
                    options={
                        "profile_path": self.config["browser"]["authenticated_profile"],
                        "authenticated_executable": self.config["browser"]["cft_executable"],
                        "logical_effect_id": reservation.logical_effect_id,
                        "outgoing_nonce": uuid.uuid4().hex,
                        "response_nonce": uuid.uuid4().hex,
                        "prompt": f"Produce a concise implementation plan for this public goal: {goal}",
                        "controller_timeout_seconds": 420,
                    },
                ),
            )
            if effect.get("unknown"):
                raise AuthorityStateUncertain("primary Brain outcome is unknown; reconcile before fallback")
            primary_status = effect["adapter_result"]["envelope"]["status"]
            if primary_status == "DONE":
                brain_result = effect["adapter_result"]
                brain_route = "chatgpt-web"
            elif primary_status in ("AUTH_EXPIRED", "UI_CHANGED"):
                fallback = self.execute_workbuddy_fallback(
                    task_id=task_id,
                    goal=goal,
                    data_classification=data_classification,
                    lease=lease,
                    context_fence=context_fence,
                )
                brain_result = fallback["adapter_result"]
                brain_route = "workbuddy-deepseek-v4-flash"
            else:
                raise RuntimeFailure(f"primary Brain returned unsupported status: {primary_status}")

        observation = None
        if brain_result:
            observation = canonical_json(brain_result.get("envelope", {}).get("data", brain_result.get("envelope", {})))[:4000]
        worker = self.runtime.invoke_local_worker(
            task_id=task_id,
            goal_text=goal,
            context_fence=context_fence,
            browser_observation=observation,
        )
        artifact = Path(worker["envelope"]["artifact_paths"][0])
        artifact_digest = sha256_file(artifact)
        delivery_candidate = worker_result_is_delivery_candidate(worker["envelope"], artifact, artifact_digest)
        if not delivery_candidate:
            reason_code = "GENERAL_GOAL_WORKER_NOT_CONFIGURED"
        else:
            reason_code = "UNIFIED_REVIEWER_NOT_CONFIGURED"
        if reason_code:
            state = self.store.read_state()
            state["tasks"][task_id].update(
                {
                    "status": "BLOCKED_CAPABILITY",
                    "reason_code": reason_code,
                    "worker_evidence_artifact": str(artifact),
                    "worker_evidence_digest": artifact_digest,
                    "brain_route": brain_route,
                }
            )
            revision = self.store.commit_state(state, reason="TASK_BLOCKED_CAPABILITY")
            capsule = self.store.create_context_capsule(
                task_id,
                "BLOCKED_CAPABILITY",
                {
                    "current_objective": goal,
                    "completed_work": ["Goal Contract committed", "worker capability probe recorded"],
                    "next_required_steps": ["configure general Goal execution and an independent source-bound Reviewer"],
                    "open_issues": [reason_code],
                    "last_verified_state": revision,
                },
            )
            return {
                "task_id": task_id,
                "status": "PRODUCT_NOT_READY",
                "reason_code": reason_code,
                "brain_route": brain_route,
                "evidence_artifact": str(artifact),
                "evidence_artifact_digest": artifact_digest,
                "state_revision": revision,
                "context_fence": capsule["context_fence"],
                "review": {
                    "reviewer": "controller-delivery-contract-gate",
                    "passed": False,
                    "findings": [
                        "A Worker result is evidence or a delivery candidate, not canonical proof that the requested Goal was completed."
                    ],
                },
            }
        review = {
            "reviewer": "controller-deterministic",
            "passed": False,
            "findings": [],
        }
        if not review["passed"]:
            raise RuntimeFailure("artifact review failed")
        release_dir = self.output_root / "tasks" / task_id / "release"
        release_dir.mkdir(parents=True, exist_ok=True)
        delivered = release_dir / artifact.name
        shutil.copy2(artifact, delivered)
        if sha256_file(delivered) != artifact_digest:
            raise RuntimeFailure("delivered digest mismatch")
        state = self.store.read_state()
        state["tasks"][task_id].update(
            {"status": "READY_FOR_USER_ACCEPTANCE", "artifact": str(delivered), "artifact_digest": artifact_digest, "brain_route": brain_route}
        )
        revision = self.store.commit_state(state, reason="TASK_READY_FOR_USER_ACCEPTANCE")
        return {
            "task_id": task_id,
            "status": "READY_FOR_USER_ACCEPTANCE",
            "brain_route": brain_route,
            "artifact": str(delivered),
            "artifact_digest": artifact_digest,
            "state_revision": revision,
            "review": review,
        }

    def run_pipeline_goal(
        self,
        goal: str,
        *,
        worker_id: str = "fixture-alpha",
        required_reviewer_id: str | None = None,
        review: Callable[[Path], dict[str, Any]] | None = None,
        objective: str | None = None,
    ) -> dict[str, Any]:
        """Goal-only entry over the resumable Goal pipeline.

        A single Goal drives PLAN -> ITERATE(real worker -> test -> review) ->
        DELIVER. Delivery is gated: if `required_reviewer_id` is set but no such
        reviewer is registered as AVAILABLE/VERIFIED, the pipeline returns
        READY_FOR_REVIEW and writes NO delivery (honest, never a fake PASS).
        """
        lease = self.acquire_lease()
        self.runtime.register_defaults()
        task = self.bootstrap_task(
            goal=goal,
            expected_final_artifact="delivered artifact",
            acceptance_criteria=["worker produced artifact", "review completed", "delivery digest bound"],
            data_classification="PRIVATE_LOCAL",
        )
        task_id = task["task_id"]
        context_fence = task["context_fence"]
        release_root = self.output_root / "tasks" / task_id / "release"
        artifact = self.output_root / "tasks" / task_id / "workspace" / "artifact.md"

        def work(attempt, artifact):
            result = self.runtime.invoke_worker_adapter(
                task_id=task_id,
                context_fence=context_fence,
                worker_id=worker_id,
                objective=objective or goal,
            )
            produced = Path(result["envelope"]["artifact_paths"][0])
            return produced

        def review_with_provider(produced):
            if review is not None:
                return review(produced)
            return {"verdict": "REWORK", "findings": ["no reviewer provider configured"]}

        pipeline = GoalPipeline(
            self.store,
            task_id=task_id,
            objective=objective or goal,
            artifact=artifact,
            release_root=release_root,
            work=work,
            test=lambda p: (p.exists() and p.stat().st_size > 0, []),
            review=review_with_provider,
            required_reviewer_id=required_reviewer_id,
        )
        result = pipeline.run()
        out = {"task_id": task_id, **result}
        if result.get("status") == "COMPLETE" and result.get("delivered"):
            out["lineage_release"] = self._record_release(
                task_id=task_id,
                objective=objective or goal,
                delivered_digest=self.store.meta(f"pipeline:{task_id}:delivered_digest"),
            )
        return out

    def _lineage_identity(self) -> tuple[str | None, str | None]:
        try:
            proc = subprocess.run(
                ["git", "-C", str(self.code_root), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
        except Exception:  # noqa
            return None, None
        commit = proc.stdout.strip()
        if proc.returncode != 0 or not commit:
            return None, None
        try:
            _, tree_digest, _ = tree_manifest(self.code_root)
        except Exception:  # noqa
            return None, None
        return commit, tree_digest

    def _record_release(self, *, task_id: str, objective: str, delivered_digest: str | None) -> dict[str, Any]:
        """Record an authoritative release Candidate in the Stable/Candidate
        lineage whenever the goal pipeline actually delivers an artifact.

        Honest boundary: this is a CANDIDATE, never a self-promotion to STABLE.
        Promotion to STABLE requires an independent PASS via promote_release().
        """
        commit, tree_digest = self._lineage_identity()
        if not commit or not tree_digest or not delivered_digest:
            raise LineageError("authoritative lineage identity unresolved; refusing to record release")
        cand = StableLineage(self.store).create_candidate(
            controller_commit=commit,
            tree_digest=tree_digest,
            known_limitations=[
                f"task={task_id}",
                f"objective={objective}",
                f"delivered_sha256={delivered_digest}",
            ],
        )
        return {
            "lineage_record_id": cand["record_id"],
            "lineage_version": cand["version"],
            "lineage_status": cand["status"],
            "lineage_controller_commit": commit,
            "lineage_tree_digest": tree_digest,
        }

    def promote_release(self, review_record_id: str) -> dict[str, Any]:
        """Promote a released CANDIDATE to STABLE from a durable, source-bound
        independent review record. There is NO API that mints a PASS from a
        reviewer name + digest; the record must already exist (written by the
        authoritative independent-review adapter from a real review outcome).
        Only verdict==PASS + R_PROD + matching candidate binding can promote."""
        record = StableLineage(self.store).promote_by_review(review_record_id)
        return {"review_record_id": review_record_id, "lineage_status": record["status"], "lineage_version": record["version"]}

    def rollback_release(self, stable_version: int, *, reason: str) -> dict[str, Any]:
        return StableLineage(self.store).rollback(stable_version, reason=reason)

    def release_lineage(self) -> list[dict[str, Any]]:
        return StableLineage(self.store).lineage()

    def doctor(self, *, live_browser: bool = False) -> dict[str, Any]:
        checks: dict[str, Any] = {}
        try:
            checks["canonical_state"] = {"status": "PASS", "revision": self.store.state_head(), "hash_valid": bool(self.store.read_state())}
        except Exception as error:
            checks["canonical_state"] = {"status": "FAIL", "error": str(error)}
        try:
            checks["effect_wal"] = {"status": "PASS", **self.store.verify_effect_wal()}
        except Exception as error:
            checks["effect_wal"] = {"status": "FAIL", "error": str(error)}
        try:
            checks["authority_journal"] = {"status": "PASS", **self.store.verify_authority_chain()}
        except Exception as error:
            checks["authority_journal"] = {"status": "FAIL", "error": str(error)}
        checks["authority_status"] = {"status": "PASS" if self.store.meta("authority_status") == "VERIFIED" else "FAIL", "value": self.store.meta("authority_status")}
        try:
            checks["tcb"] = {"status": "PASS", **verify_tcb(self.store, self.code_root)}
        except Exception as error:
            checks["tcb"] = {"status": "FAIL", "error": str(error), "value": self.store.meta("tcb_status")}
        checks["production_entry"] = {"status": "PASS" if (self.code_root / "ai-control.cmd").is_file() else "FAIL"}
        checks["config"] = {"status": "PASS", "path": str(self.config_path), "schema_version": self.config["schema_version"]}
        checks["workers"] = {"status": "PASS", "registry": self.store.registry("worker_registry")}
        checks["brains"] = {"status": "PASS", "registry": self.store.registry("brain_registry")}
        checks["locks"] = {"status": "PASS", "count": self.store.connection.execute("SELECT COUNT(*) AS n FROM locks").fetchone()["n"]}
        checks["logical_effects"] = {"status": "PASS", "count": self.store.connection.execute("SELECT COUNT(*) AS n FROM reservations").fetchone()["n"]}
        checks["credential_refs"] = {"status": "PASS", "values": ["browser-profile-ref", "workbuddy-existing-auth", "codex-existing-login"]}
        checks["release_area"] = {"status": "PASS" if Path(self.config["release_root"]).is_dir() else "FAIL", "path": self.config["release_root"]}
        checks["versions"] = self.version_drift()
        if live_browser:
            task = self.bootstrap_task(
                goal="Controller-owned browser doctor",
                expected_final_artifact="browser doctor evidence",
                acceptance_criteria=["browser launches", "page title observed"],
                data_classification="PUBLIC",
            )
            checks["browser"] = self.runtime.invoke_browser(
                task_id=task["task_id"],
                context_fence=task["context_fence"],
                command="doctor",
                options={"profile_path": str(self.state_root / "browser-doctor-profile"), "controller_timeout_seconds": 90},
            )["envelope"]
        else:
            checks["browser"] = {"status": "NOT_RUN", "primary": self.config["browser"]["primary"], "fallback": self.config["browser"]["fallback"]}
        failed = [name for name, value in checks.items() if isinstance(value, dict) and value.get("status") == "FAIL"]
        return {"status": "PASS" if not failed else "FAIL", "failed": failed, "checks": checks}

    def version_drift(self) -> dict[str, Any]:
        paths = {
            "chrome": self.config["browser"]["chrome_executable"],
            "bsk": self.config["browser"]["bsk_executable"],
            "node": "C:\\Program Files\\nodejs\\node.exe",
            "python": self.config["workers"]["local_python"],
            "workbuddy": "C:\\Program Files\\WorkBuddy\\WorkBuddy.exe",
            "codex": self.config["workers"]["codex_cli"],
        }
        result = {}
        for name, raw in paths.items():
            path = Path(raw)
            result[name] = {"present": path.exists(), "path": str(path), "sha256": sha256_file(path) if path.is_file() else None}
        lock = self.code_root / "package-lock.json"
        result["controller_dependencies"] = {"package_lock_sha256": sha256_file(lock) if lock.exists() else None, "playwright_core": read_json(self.code_root / "package.json")["dependencies"]["playwright-core"]}
        result["status"] = "PASS"
        return result

    def status(self, task_id: str | None = None) -> dict[str, Any]:
        state = self.store.read_state()
        if task_id:
            return {"task_id": task_id, "state": state.get("tasks", {}).get(task_id), "state_revision": self.store.state_head()}
        return {
            "state_revision": self.store.state_head(),
            "tasks": state.get("tasks", {}),
            "authority_status": self.store.meta("authority_status"),
            "tcb_status": self.store.meta("tcb_status"),
            "unresolved_effects": [dict(row) for row in self.store.connection.execute("SELECT action_id,logical_effect_id,status FROM actions WHERE status IN ('EFFECT_START_COMMITTED','OUTCOME_UNKNOWN')")],
        }

    def seal_tcb(self, reason: str) -> dict[str, Any]:
        return seal_tcb(self.store, self.code_root, reason=reason)

    def validate_acceptance_manifest(
        self,
        *,
        task_id: str,
        acceptance_manifest_path: str | Path,
        artifact_digest: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        manifest_path = Path(acceptance_manifest_path).resolve(strict=True)
        manifest_hash = sha256_file(manifest_path)
        evidence_record = self.store.evidence_for_path(
            task_id=task_id,
            kind="ACCEPTANCE_MANIFEST",
            path=str(manifest_path),
            sha256=manifest_hash,
        )
        acceptance = read_json(manifest_path)
        required_fields = {
            "schema_version",
            "definition_version",
            "task_id",
            "goal_contract_hash",
            "state_revision",
            "context_fence",
            "tested_artifact_digest",
            "cases",
            "known_blocking_defects",
            "known_core_path_defects",
            "final_status",
        }
        if not isinstance(acceptance, dict) or not required_fields.issubset(acceptance):
            raise GateDenied("Release Gate: acceptance manifest schema is incomplete")
        goal = self.store.latest_goal(task_id)
        if acceptance["schema_version"] != 1 or acceptance["task_id"] != task_id:
            raise GateDenied("Release Gate: acceptance task/schema mismatch")
        if acceptance["goal_contract_hash"] != goal["contract_hash"]:
            raise GateDenied("Release Gate: acceptance Goal Contract mismatch")
        if acceptance["tested_artifact_digest"] != artifact_digest:
            raise GateDenied("Release Gate: acceptance tested a different artifact digest")
        if acceptance["state_revision"] != self.store.state_head():
            raise GateDenied("Release Gate: acceptance Canonical State is stale")
        if acceptance["context_fence"] != self.store.current_context_fence(task_id):
            raise GateDenied("Release Gate: acceptance Context Fence is stale")
        metadata = evidence_record["metadata"]
        expected_metadata = {
            "schema_version": acceptance["schema_version"],
            "goal_contract_hash": acceptance["goal_contract_hash"],
            "state_revision": acceptance["state_revision"],
            "context_fence": acceptance["context_fence"],
            "tested_artifact_digest": acceptance["tested_artifact_digest"],
        }
        if any(metadata.get(key) != value for key, value in expected_metadata.items()):
            raise GateDenied("Release Gate: acceptance evidence metadata mismatch")
        cases = acceptance["cases"]
        if not isinstance(cases, list) or not cases:
            raise GateDenied("Release Gate: acceptance case set cannot be empty")
        expected_case_ids = goal.get("acceptance_criteria", [])
        actual_case_ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
        if (
            not isinstance(expected_case_ids, list)
            or not expected_case_ids
            or len(actual_case_ids) != len(cases)
            or len(set(actual_case_ids)) != len(actual_case_ids)
            or set(actual_case_ids) != set(expected_case_ids)
        ):
            raise GateDenied("Release Gate: acceptance cases do not match the Goal Contract")
        blocking = 0
        core = 0
        for case in cases:
            required_case_fields = {
                "case_id",
                "requirement_class",
                "result",
                "test_execution_id",
                "evidence_hashes",
                "tested_artifact_digest",
            }
            if not required_case_fields.issubset(case):
                raise GateDenied("Release Gate: acceptance case schema is incomplete")
            canonical_test = self.store.test_execution(str(case["test_execution_id"]))
            if (
                canonical_test["case_id"] != case["case_id"]
                or canonical_test["task_id"] != task_id
                or canonical_test["goal_contract_hash"] != goal["contract_hash"]
                or canonical_test["tested_artifact_digest"] != artifact_digest
                or canonical_test["definition_version"] != acceptance["definition_version"]
                or canonical_test["requirement_class"] != case["requirement_class"]
                or canonical_test["exit_or_observed_result"] != case["result"]
                or canonical_test["evidence_hashes"] != case["evidence_hashes"]
                or case["tested_artifact_digest"] != artifact_digest
            ):
                raise GateDenied("Release Gate: acceptance case is not bound to its canonical test execution")
            revision = self.store.connection.execute(
                "SELECT 1 FROM canonical_revisions WHERE revision=?", (canonical_test["state_revision"],)
            ).fetchone()
            if not revision or int(canonical_test["state_revision"]) > int(acceptance["state_revision"]):
                raise GateDenied("Release Gate: test execution state revision is invalid")
            for evidence_path, expected_hash in canonical_test["evidence_hashes"].items():
                path = Path(evidence_path)
                if not path.is_file() or sha256_file(path) != expected_hash:
                    raise GateDenied("Release Gate: test evidence file digest mismatch")
            if case["requirement_class"] == "REQUIRED":
                if case["result"] != "PASS" or canonical_test["verification_status"] != "VERIFIED":
                    blocking += 1
                    if case["result"] == "FAIL":
                        core += 1
            elif case["requirement_class"] == "CONDITIONAL":
                if case["result"] not in ("PASS", "SKIPPED_CONDITION_NOT_MET"):
                    blocking += 1
            else:
                raise GateDenied("Release Gate: unknown requirement class")
        if (
            blocking != acceptance["known_blocking_defects"]
            or core != acceptance["known_core_path_defects"]
            or blocking != 0
            or core != 0
            or acceptance["final_status"] != "READY_FOR_USER_ACCEPTANCE"
        ):
            raise GateDenied("Release Gate: acceptance defect/final status mismatch")
        return acceptance, evidence_record

    def validate_review_manifest(
        self,
        *,
        task_id: str,
        review_manifest_path: str | Path,
        acceptance: dict[str, Any],
        acceptance_evidence_id: str,
        artifact_digest: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        review_path = Path(review_manifest_path).resolve(strict=True)
        review_hash = sha256_file(review_path)
        evidence_record = self.store.evidence_for_path(
            task_id=task_id,
            kind="INDEPENDENT_REVIEW_MANIFEST",
            path=str(review_path),
            sha256=review_hash,
        )
        document = read_json(review_path)
        required_fields = {
            "schema_version",
            "task_id",
            "goal_contract_hash",
            "state_revision",
            "context_fence",
            "artifact_digest",
            "acceptance_evidence_id",
            "reviews",
        }
        if not isinstance(document, dict) or not required_fields.issubset(document):
            raise GateDenied("Release Gate: review manifest schema is incomplete")
        if (
            document["schema_version"] != 1
            or document["task_id"] != task_id
            or document["goal_contract_hash"] != acceptance["goal_contract_hash"]
            or document["state_revision"] != acceptance["state_revision"]
            or document["context_fence"] != acceptance["context_fence"]
            or document["artifact_digest"] != artifact_digest
            or document["acceptance_evidence_id"] != acceptance_evidence_id
        ):
            raise GateDenied("Release Gate: review manifest binding mismatch")
        metadata = evidence_record["metadata"]
        for key in ("schema_version", "goal_contract_hash", "state_revision", "context_fence", "artifact_digest", "acceptance_evidence_id"):
            if metadata.get(key) != document[key]:
                raise GateDenied("Release Gate: review evidence metadata mismatch")
        reviews = document["reviews"]
        if not isinstance(reviews, list) or not reviews:
            raise GateDenied("Release Gate: independent review set cannot be empty")
        for review in reviews:
            required_review_fields = {
                "schema_version",
                "reviewer",
                "provider",
                "task_id",
                "goal_contract_hash",
                "state_revision",
                "context_fence",
                "artifact_digest",
                "verdict",
                "findings",
                "result_id",
                "invocation_id",
                "action_id",
                "logical_effect_id",
            }
            if not isinstance(review, dict) or not required_review_fields.issubset(review):
                raise GateDenied("Release Gate: review entry schema is incomplete")
            if (
                review["schema_version"] != 1
                or review["task_id"] != task_id
                or review["goal_contract_hash"] != acceptance["goal_contract_hash"]
                or review["state_revision"] != acceptance["state_revision"]
                or review["context_fence"] != acceptance["context_fence"]
                or review["artifact_digest"] != artifact_digest
                or review["verdict"] != "PASS"
                or review["findings"] != []
            ):
                raise GateDenied("Release Gate: independent review did not explicitly PASS this candidate")
            result = self.store.verified_result(str(review["result_id"]))
            if (
                result["invocation_id"] != review["invocation_id"]
                or result["actor_id"] != review["reviewer"]
                or result["expected_actor_id"] != review["reviewer"]
                or result["actor_type"] != "BRAIN"
            ):
                raise GateDenied("Release Gate: review result source mismatch")
            validate_reviewer_envelope(
                result["envelope"],
                task_id=task_id,
                goal_contract_hash=acceptance["goal_contract_hash"],
                state_revision=acceptance["state_revision"],
                context_fence=acceptance["context_fence"],
                artifact_digest=artifact_digest,
                acceptance_evidence_id=acceptance_evidence_id,
            )
            if result["envelope"]["verdict"] != "PASS" or result["envelope"]["findings"] != []:
                raise GateDenied("Release Gate: canonical Reviewer result did not PASS")
            effect = self.store.committed_effect(
                action_id=str(review["action_id"]), logical_effect_id=str(review["logical_effect_id"])
            )
            result_in_outcome = effect["outcome"].get("result", {}).get("verification", {}).get("result_id")
            if (
                effect["task_id"] != task_id
                or effect["reservation_task_id"] != task_id
                or effect["goal_contract_hash"] != acceptance["goal_contract_hash"]
                or effect["state_revision"] != acceptance["state_revision"]
                or effect["context_fence"] != acceptance["context_fence"]
                or effect["provider"] != review["provider"]
                or result_in_outcome != review["result_id"]
            ):
                raise GateDenied("Release Gate: review is not source-bound to its committed Effect")
        return document, evidence_record

    def create_release_candidate(
        self,
        *,
        task_id: str,
        acceptance_manifest_path: str | Path,
        review_manifest_path: str | Path,
    ) -> dict[str, Any]:
        entries, artifact_digest, artifact_size = tree_manifest(self.code_root)
        acceptance, acceptance_evidence = self.validate_acceptance_manifest(
            task_id=task_id,
            acceptance_manifest_path=acceptance_manifest_path,
            artifact_digest=artifact_digest,
        )
        review_document, review_evidence_record = self.validate_review_manifest(
            task_id=task_id,
            review_manifest_path=review_manifest_path,
            acceptance=acceptance,
            acceptance_evidence_id=acceptance_evidence["evidence_id"],
            artifact_digest=artifact_digest,
        )
        verify_tcb(self.store, self.code_root)
        candidate_id = f"rc-{uuid.uuid4()}"
        candidate_root = Path(self.config["release_root"]) / candidate_id
        artifact_root = candidate_root / "artifact"
        artifact_root.mkdir(parents=True, exist_ok=False)
        for item in entries:
            source = self.code_root / item["path"]
            destination = artifact_root / item["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        copied_entries, copied_digest, copied_size = tree_manifest(artifact_root)
        if copied_digest != artifact_digest or copied_size != artifact_size or copied_entries != entries:
            raise GateDenied("Release Candidate copy digest mismatch")
        acceptance_hash = acceptance_evidence["sha256"]
        record = {
            "release_candidate_id": candidate_id,
            "task_id": task_id,
            "goal_contract_hash": self.store.latest_goal(task_id)["contract_hash"],
            "state_revision": self.store.state_head(),
            "artifact_kind": "DIRECTORY_TREE",
            "artifact_path": str(artifact_root),
            "artifact_digest": artifact_digest,
            "artifact_size": artifact_size,
            "tree_manifest": entries,
            "test_evidence": [
                {
                    "case_id": case["case_id"],
                    "test_execution_id": case["test_execution_id"],
                    "evidence_hashes": case.get("evidence_hashes", {}),
                    "acceptance_evidence_id": acceptance_evidence["evidence_id"],
                }
                for case in acceptance["cases"]
            ],
            "review_evidence": [
                {**review, "review_evidence_id": review_evidence_record["evidence_id"]}
                for review in review_document["reviews"]
            ],
            "acceptance_evidence_id": acceptance_evidence["evidence_id"],
            "review_evidence_id": review_evidence_record["evidence_id"],
            "acceptance_manifest_hash": acceptance_hash,
            "created_at": utc_now(),
            "status": "VERIFIED",
        }
        self.store.create_release_candidate(record)
        candidate_manifest = candidate_root / "release-candidate-manifest.json"
        write_json(candidate_manifest, record)
        delivered_entries, delivered_digest, _ = tree_manifest(artifact_root)
        if delivered_digest != artifact_digest or delivered_entries != entries:
            raise GateDenied("delivered digest verification failed")
        self.store.mark_delivered(candidate_id, delivered_digest)
        record["status"] = "DELIVERED"
        record["delivered_digest"] = delivered_digest
        write_json(candidate_manifest, record)
        return {**record, "manifest_path": str(candidate_manifest)}