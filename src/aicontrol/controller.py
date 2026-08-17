from __future__ import annotations

import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .runtimes import RuntimeFailure, RuntimeManager
from .security import browser_profile_identity, egress_allowed, seal_tcb, verify_tcb
from .store import (
    AuthorityStateUncertain,
    ControlStore,
    GateDenied,
    Reservation,
    StorageDurabilityUnavailable,
)
from .util import canonical_json, read_json, sha256_file, sha256_text, tree_manifest, utc_now, windows_boot_session_id, write_json


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
    ) -> dict[str, Any]:
        scope = {
            "provider": provider,
            "destination": destination,
            "purpose": purpose,
            "effect_type": effect_type,
            "data_classes": data_classes,
        }
        nonce = self.store.issue_decision_nonce(
            task_id,
            scope,
            user_decision_reference=user_decision_reference,
            ttl_seconds=900,
        )
        return self.store.grant_authorization(
            task_id,
            nonce["decision_nonce"],
            scope,
            provider=provider,
            resource=destination,
            purpose=purpose,
            effect_type=effect_type,
            max_effect_count=max_effect_count,
            ttl_seconds=7200,
        )

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
                return {"reservation": reservation, "deduplicated": True, "adapter_result": None}
            self.store.start_effect(
                reservation,
                controller_instance_id=self.controller_instance_id,
                controller_lease_id=lease["lease_id"],
                resource_fresh=resource_fresh,
            )
            try:
                adapter_result = adapter(reservation)
                if expected_account.startswith("profile-sha256:"):
                    returned_identity = adapter_result.get("envelope", {}).get("data", {}).get("profile_identity_hash")
                    if returned_identity != expected_account.removeprefix("profile-sha256:"):
                        raise GateDenied("browser returned a different account/profile identity")
            except Exception as error:
                self.store.finish_effect(
                    reservation,
                    {"error_type": type(error).__name__, "message": str(error), "reconciliation_required": True},
                    unknown=True,
                )
                raise
            status = adapter_result.get("envelope", {}).get("status")
            unknown = status in ("TIMEOUT", "UNKNOWN")
            self.store.finish_effect(reservation, {"adapter_status": status, "result": adapter_result}, unknown=unknown)
            return {"reservation": reservation, "deduplicated": False, "adapter_result": adapter_result, "unknown": unknown}
        finally:
            self.store.release_lock(resource_id, self.controller_instance_id)

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
            auth = self.scoped_authorization(
                task_id=task_id,
                provider="ChatGPT",
                destination="chatgpt.com",
                purpose="goal-planning",
                effect_type="AI_MESSAGE",
                data_classes=[data_classification],
                max_effect_count=1,
                user_decision_reference=f"controlled-cli-run:{sha256_text(goal)}",
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
                "resource": "new-chat-session",
                "payload_hash": sha256_text(goal),
                "critical_params": {"role": "MAIN"},
                "purpose": "goal-planning",
                "logical_effect_slot": "PRIMARY_BRAIN_PLAN",
                "retry_semantics": "RECONCILE_REQUIRED",
                "impact": "LOW",
                "reversibility": "PARTIALLY_REVERSIBLE",
                "effect_scope": "EXTERNAL",
            }
            try:
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
                brain_result = effect["adapter_result"]
                brain_route = "chatgpt-web"
            except Exception:
                brain_result = self.runtime.invoke_workbuddy_brain(
                    task_id=task_id,
                    context_fence=context_fence,
                    prompt=f"Produce a concise proposal for: {goal}",
                )
                brain_route = "workbuddy-deepseek-v4-flash"

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
        review = {
            "reviewer": "controller-deterministic",
            "passed": artifact.exists() and artifact.stat().st_size > 0 and artifact_digest == worker["envelope"]["artifact_hashes"][str(artifact)],
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

    def create_release_candidate(
        self,
        *,
        task_id: str,
        acceptance_manifest_path: str | Path,
        review_evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        manifest_path = Path(acceptance_manifest_path).resolve(strict=True)
        acceptance = read_json(manifest_path)
        entries, artifact_digest, artifact_size = tree_manifest(self.code_root)
        failures = [
            case for case in acceptance.get("cases", [])
            if case["requirement_class"] == "REQUIRED" and case["result"] != "PASS"
        ]
        conditional_failures = [
            case for case in acceptance.get("cases", [])
            if case["requirement_class"] == "CONDITIONAL" and case["result"] not in ("PASS", "SKIPPED_CONDITION_NOT_MET")
        ]
        if failures or conditional_failures:
            raise GateDenied("Release Gate: acceptance failures remain")
        if acceptance.get("known_blocking_defects") != 0 or acceptance.get("known_core_path_defects") != 0:
            raise GateDenied("Release Gate: known blocking/core defects remain")
        if any(case.get("tested_artifact_digest") != artifact_digest for case in acceptance.get("cases", [])):
            raise GateDenied("Release Gate: acceptance tested a different artifact digest")
        if not review_evidence or any(item.get("artifact_digest") != artifact_digest or item.get("status") != "PASS" for item in review_evidence):
            raise GateDenied("Release Gate: independent reviews do not bind the candidate digest")
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
        acceptance_hash = sha256_file(manifest_path)
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
            "test_evidence": [{"case_id": case["case_id"], "test_execution_id": case["test_execution_id"], "evidence_hashes": case.get("evidence_hashes", {})} for case in acceptance["cases"]],
            "review_evidence": review_evidence,
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
