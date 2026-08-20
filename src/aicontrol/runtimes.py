from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .process import ProcessResult, run_structured
from .store import ControlStore, GateDenied
from .util import (
    atomic_write,
    canonical_json,
    read_json,
    safe_resolve,
    sha256_file,
    sha256_text,
    utc_now,
    write_json,
)
from .adapters import build_task_capsule, validate_capability_grant, validate_worker_artifacts


class RuntimeFailure(RuntimeError):
    pass


def _json_from_stdout(stdout: str) -> dict[str, Any]:
    for line in reversed([line.strip() for line in stdout.splitlines() if line.strip()]):
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    try:
        value = json.loads(stdout)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    raise RuntimeFailure("structured JSON result missing")


def _extract_model_result(stdout: str) -> str:
    candidates: list[dict[str, Any]] = []
    try:
        root = json.loads(stdout)
        if isinstance(root, dict):
            candidates.append(root)
        elif isinstance(root, list):
            candidates.extend(item for item in root if isinstance(item, dict))
    except json.JSONDecodeError:
        for line in stdout.splitlines():
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    candidates.append(item)
            except json.JSONDecodeError:
                continue
    for item in reversed(candidates):
        if item.get("type") == "result" and isinstance(item.get("result"), str):
            return item["result"]
        if isinstance(item.get("result"), str):
            return item["result"]
    return stdout.strip()


def _embedded_json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise RuntimeFailure("model result JSON missing")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise RuntimeFailure("model result is not an object")
    return value


class RuntimeManager:
    def __init__(
        self,
        *,
        store: ControlStore,
        config: dict[str, Any],
        code_root: str | Path,
        controller_instance_id: str,
    ) -> None:
        self.store = store
        self.config = config
        self.code_root = Path(code_root).resolve(strict=True)
        self.controller_instance_id = controller_instance_id
        self.state_root = Path(config["state_root"])
        self.output_root = Path(config["output_root"])
        self.allowed_roots = list(config["allowed_roots"])

    def register_defaults(self) -> None:
        workers = [
            {
                "worker_id": "local-python",
                "type": "LOCAL_PROCESS",
                "invocation": str(self.code_root / "scripts" / "local_worker.py"),
                "capabilities": ["artifact-write", "local-transform"],
                "speed_class": "FAST",
                "quality_class": "DETERMINISTIC",
                "cost_class": "LOCAL",
                "availability": "AVAILABLE",
                "execution_trust_class": "BROKERED",
                "allowed_roots": [str(self.output_root / "tasks")],
                "allowed_effects": ["LOCAL_REVERSIBLE_WRITE"],
                "network_scope": "NONE",
                "workspace_mode": "ISOLATED",
                "concurrency": 4,
            },
            {
                "worker_id": "workbuddy-cli",
                "type": "AI_CLI",
                "invocation": self.config["workers"]["workbuddy_cli"],
                "capabilities": ["analysis", "mechanical-read", "proposal"],
                "speed_class": "MEDIUM",
                "quality_class": "MODEL_DEPENDENT",
                "cost_class": "ACCOUNT_SERVICE",
                "availability": "UNVERIFIED_CURRENT",
                "execution_trust_class": "PRIVILEGED_UNBROKERED",
                "allowed_roots": [],
                "allowed_effects": ["ACTION_PROPOSAL"],
                "network_scope": "MODEL_PROVIDER_ONLY",
                "workspace_mode": "ISOLATED",
                "concurrency": 5,
            },
            {
                "worker_id": "codex-cli",
                "type": "AI_CLI",
                "invocation": self.config["workers"]["codex_cli"],
                "capabilities": ["analysis", "code-review", "proposal"],
                "speed_class": "MEDIUM",
                "quality_class": "HIGH",
                "cost_class": "ACCOUNT_SERVICE",
                "availability": "UNVERIFIED_CURRENT",
                "execution_trust_class": "SANDBOXED",
                "allowed_roots": [],
                "allowed_effects": ["ACTION_PROPOSAL"],
                "network_scope": "MODEL_PROVIDER_ONLY",
                "workspace_mode": "READ_ONLY_ISOLATED",
                "concurrency": 2,
            },
        ]
        for worker in workers:
            self.store.upsert_registry("worker_registry", "worker_id", worker["worker_id"], worker)
        brains = [
            {
                "brain_id": "chatgpt-web",
                "provider": "ChatGPT",
                "account_profile": "browser-credential-ref:authenticated-profile",
                "role": "MAIN",
                "health": "UNVERIFIED_CURRENT",
                "continuity_status": "SUSPECTED_STALE",
                "canonical_browser_resource": "chatgpt-authenticated-profile",
            },
            {
                "brain_id": "workbuddy-deepseek-v4-flash",
                "provider": "WorkBuddy",
                "account_profile": "credential-ref:workbuddy-existing-auth",
                "role": "FALLBACK",
                "health": "UNVERIFIED_CURRENT",
                "continuity_status": "SUSPECTED_STALE",
            },
            {
                "brain_id": "codex-local",
                "provider": "Codex CLI",
                "account_profile": "credential-ref:codex-existing-login",
                "role": "REVIEWER",
                "health": "UNVERIFIED_CURRENT",
                "continuity_status": "SUSPECTED_STALE",
            },
        ]
        for brain in brains:
            self.store.upsert_registry("brain_registry", "brain_id", brain["brain_id"], brain)
        providers = [
            {
                "provider_id": "chatgpt-web",
                "kind": "WEB_SESSION",
                "class": "WebSessionProvider",
                "transport_identity_owner": "CONTROLLER",
                "account_profile": "browser-credential-ref:authenticated-profile",
                "default_retry_semantics": "RECONCILE_REQUIRED",
            },
            {
                "provider_id": "workbuddy-cli",
                "kind": "API_MODEL",
                "class": "APIModelProvider",
                "transport_identity_owner": "CONTROLLER",
                "account_profile": "credential-ref:workbuddy-existing-auth",
                "default_retry_semantics": "RECONCILE_REQUIRED",
            },
            {
                "provider_id": "codex-cli",
                "kind": "API_MODEL",
                "class": "APIModelProvider",
                "transport_identity_owner": "CONTROLLER",
                "account_profile": "credential-ref:codex-existing-login",
                "default_retry_semantics": "RECONCILE_REQUIRED",
            },
        ]
        for provider in providers:
            self.store.upsert_registry("provider_registry", "provider_id", provider["provider_id"], provider)
        reviewers = [
            {
                "reviewer_id": "chatgpt-web",
                "role": "R_PROD",
                "provider": "ChatGPT",
                "contract": "REVIEWER",
                "health": "UNVERIFIED_CURRENT",
            },
            {
                "reviewer_id": "codex-local",
                "role": "E_LAB",
                "provider": "Codex CLI",
                "contract": "REVIEWER",
                "health": "UNVERIFIED_CURRENT",
            },
        ]
        for reviewer in reviewers:
            self.store.upsert_registry("reviewer_registry", "reviewer_id", reviewer["reviewer_id"], reviewer)

    def _invocation(
        self,
        *,
        task_id: str,
        actor_id: str,
        actor_type: str,
        trust_class: str,
        capability: dict[str, Any],
        context_fence: str,
        result_channel: str,
        ttl_seconds: int = 900,
    ) -> dict[str, Any]:
        goal = self.store.latest_goal(task_id)
        receipt = {
            "invocation_id": str(uuid.uuid4()),
            "request_nonce": secrets_token(),
            "expected_actor_id": actor_id,
            "actor_type": actor_type,
            "task_id": task_id,
            "goal_contract_hash": goal["contract_hash"],
            "state_revision": self.store.state_head(),
            "context_fence": context_fence,
            "trust_class": trust_class,
            "capability": capability,
            "result_channel": result_channel,
            "process_session_identity": f"planned:{uuid.uuid4()}",
            "created_at": utc_now(),
            "expires_at": (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "status": "CREATED",
        }
        self.store.record_invocation(receipt)
        return receipt

    def _register_callback(self, *, task_id: str, invocation_id: str, effect_class: str = "LOCAL"):
        def register(process: dict[str, Any]) -> None:
            self.store.register_process(
                {
                    **process,
                    "invocation_id": invocation_id,
                    "controller_instance_id": self.controller_instance_id,
                    "task_id": task_id,
                    "effect_class": effect_class,
                    "lifetime": "INVOCATION",
                }
            )
        return register

    def invoke_local_worker(
        self,
        *,
        task_id: str,
        goal_text: str,
        context_fence: str,
        cold_start: bool = False,
        browser_observation: str | None = None,
    ) -> dict[str, Any]:
        workspace = self.output_root / "tasks" / task_id / f"worker-{uuid.uuid4().hex[:8]}"
        workspace.mkdir(parents=True, exist_ok=False)
        artifact = workspace / "worker-artifact.md"
        result_channel = workspace / "result.json"
        receipt = self._invocation(
            task_id=task_id,
            actor_id="local-python",
            actor_type="WORKER",
            trust_class="BROKERED",
            capability={"allowed_roots": [str(workspace)], "allowed_effects": ["LOCAL_REVERSIBLE_WRITE"]},
            context_fence=context_fence,
            result_channel=str(result_channel),
        )
        goal = self.store.latest_goal(task_id)
        request_value = {
            "invocation_id": receipt["invocation_id"],
            "request_nonce": receipt["request_nonce"],
            "task_id": task_id,
            "goal_contract_version": goal["contract_version"],
            "goal_contract_hash": goal["contract_hash"],
            "request_state_revision": receipt["state_revision"],
            "request_context_fence": context_fence,
            "goal": goal_text,
            "workspace": str(workspace),
            "artifact_path": str(artifact),
            "browser_observation": browser_observation,
            "start_here_path": str(self.code_root / "NEW_WORKER_START_HERE.md") if cold_start else None,
        }
        request_path = workspace / "request.json"
        write_json(request_path, request_value)
        result = run_structured(
            self.config["workers"]["local_python"],
            [str(self.code_root / "scripts" / "local_worker.py"), str(request_path)],
            cwd=str(workspace),
            allowed_cwd_roots=[str(self.output_root)],
            timeout_seconds=60,
            register=self._register_callback(task_id=task_id, invocation_id=receipt["invocation_id"]),
        )
        if result.exit_code != 0 or result.timed_out:
            raise RuntimeFailure(f"local worker failed: {result.safe_record()}")
        envelope = _json_from_stdout(result.stdout)
        for raw in envelope.get("artifact_paths", []):
            target = safe_resolve(raw, [str(workspace)], must_exist=True)
            expected = envelope.get("artifact_hashes", {}).get(str(target))
            if not expected or sha256_file(target) != expected:
                raise RuntimeFailure("worker artifact hash mismatch")
        source = {
            "actor_id": "local-python",
            "process_id": result.pid,
            "process_start_identity": result.process_start_identity,
            "controlled_stdout_hash": sha256_text(result.stdout),
            "result_channel": str(result_channel),
        }
        verification = self.store.verify_and_record_result(receipt["invocation_id"], envelope, source)
        return {"envelope": envelope, "source_binding": source, "verification": verification, "process": result.safe_record()}

    def invoke_browser(self, *, task_id: str, context_fence: str, command: str, options: dict[str, Any]) -> dict[str, Any]:
        workspace = self.output_root / "tasks" / task_id / f"browser-{uuid.uuid4().hex[:8]}"
        workspace.mkdir(parents=True, exist_ok=False)
        result_channel = workspace / "browser-result.json"
        actor_id = "browser-playwright"
        receipt = self._invocation(
            task_id=task_id,
            actor_id=actor_id,
            actor_type="BROWSER",
            trust_class="BROKERED",
            capability={"command": command, "browser_profile_access": True},
            context_fence=context_fence,
            result_channel=str(result_channel),
            ttl_seconds=600,
        )
        request_value = {
            "command": command,
            "invocation_id": receipt["invocation_id"],
            "request_nonce": receipt["request_nonce"],
            "task_id": task_id,
            "goal_contract_hash": receipt["goal_contract_hash"],
            "request_state_revision": receipt["state_revision"],
            "request_context_fence": context_fence,
            "actor_id": actor_id,
            "chrome_executable": self.config["browser"]["chrome_executable"],
            **options,
        }
        request_path = workspace / "browser-request.json"
        write_json(request_path, request_value)
        result = run_structured(
            "C:\\Program Files\\nodejs\\node.exe",
            [str(self.code_root / "scripts" / "browser_runtime.mjs"), str(request_path)],
            cwd=str(self.code_root),
            allowed_cwd_roots=[str(self.code_root)],
            timeout_seconds=float(options.get("controller_timeout_seconds", 480)),
            register=self._register_callback(task_id=task_id, invocation_id=receipt["invocation_id"], effect_class="BROWSER"),
        )
        envelope = _json_from_stdout(result.stdout)
        source = {
            "actor_id": actor_id,
            "process_id": result.pid,
            "process_start_identity": result.process_start_identity,
            "controlled_stdout_hash": sha256_text(result.stdout),
            "browser_profile_identity_hash": envelope.get("data", {}).get("profile_identity_hash"),
        }
        verification = self.store.verify_and_record_result(receipt["invocation_id"], envelope, source)
        if result.exit_code != 0 or result.timed_out or envelope.get("status") not in ("DONE", "AUTH_EXPIRED", "TIMEOUT", "UI_CHANGED"):
            raise RuntimeFailure(f"browser runtime failed: {envelope.get('errors') or result.safe_record()}")
        return {"envelope": envelope, "source_binding": source, "verification": verification, "process": result.safe_record()}

    def invoke_workbuddy_brain(self, *, task_id: str, context_fence: str, prompt: str, role: str = "FALLBACK") -> dict[str, Any]:
        workspace = self.output_root / "tasks" / task_id / f"workbuddy-{uuid.uuid4().hex[:8]}"
        workspace.mkdir(parents=True, exist_ok=False)
        result_channel = workspace / "workbuddy.jsonl"
        actor_id = "workbuddy-deepseek-v4-flash"
        receipt = self._invocation(
            task_id=task_id,
            actor_id=actor_id,
            actor_type="BRAIN",
            trust_class="PRIVILEGED_UNBROKERED",
            capability={"allowed_effects": ["ACTION_PROPOSAL"], "tools": []},
            context_fence=context_fence,
            result_channel=str(result_channel),
        )
        requested = {
            "invocation_id": receipt["invocation_id"],
            "request_nonce": receipt["request_nonce"],
            "task_id": task_id,
            "goal_contract_hash": receipt["goal_contract_hash"],
            "request_state_revision": receipt["state_revision"],
            "request_context_fence": context_fence,
            "role": role,
        }
        machine_prompt = (
            "You are a proposal-only Brain. Do not use tools and do not perform external actions. "
            "Return exactly one JSON object, no markdown, containing all supplied binding fields, status='DONE', "
            "decision, assumptions, findings, recommended_actions, and human_readable_content.\n"
            f"BINDING={canonical_json(requested)}\nTASK={prompt}"
        )
        session_id = f"APC_WB_{uuid.uuid4().hex}"
        result = run_structured(
            self.config["workers"]["workbuddy_node"],
            [
                self.config["workers"]["workbuddy_cli"],
                "-p",
                "--session-id",
                session_id,
                "--model",
                "deepseek-v4-flash",
                "--output-format",
                "json",
                "--tools",
                "Read",
                machine_prompt,
            ],
            cwd=str(workspace),
            allowed_cwd_roots=[str(self.output_root)],
            env={"CODEBUDDY_CONFIG_DIR": "C:\\Users\\17838\\.workbuddy"},
            timeout_seconds=180,
            register=self._register_callback(task_id=task_id, invocation_id=receipt["invocation_id"], effect_class="BRAIN"),
        )
        if result.exit_code != 0 or result.timed_out:
            raise RuntimeFailure(f"WorkBuddy call failed: {result.safe_record()}")
        model_result = _extract_model_result(result.stdout)
        envelope = _embedded_json(model_result)
        envelope.setdefault("schema_version", 1)
        source = {
            "actor_id": actor_id,
            "process_id": result.pid,
            "process_start_identity": result.process_start_identity,
            "controlled_stdout_hash": sha256_text(result.stdout),
            "session_id": session_id,
            "executable_hash": sha256_file(self.config["workers"]["workbuddy_node"]),
        }
        verification = self.store.verify_and_record_result(receipt["invocation_id"], envelope, source)
        return {"envelope": envelope, "source_binding": source, "verification": verification, "process": result.safe_record()}

    def invoke_codex_brain(
        self,
        *,
        task_id: str,
        context_fence: str,
        prompt: str,
        role: str = "REVIEWER",
        artifact_digest: str = "NOT_APPLICABLE",
        acceptance_evidence_id: str = "NOT_APPLICABLE",
    ) -> dict[str, Any]:
        workspace = self.output_root / "tasks" / task_id / f"codex-{uuid.uuid4().hex[:8]}"
        workspace.mkdir(parents=True, exist_ok=False)
        result_channel = workspace / "codex-final.json"
        events_path = workspace / "codex-events.jsonl"
        actor_id = "codex-local"
        receipt = self._invocation(
            task_id=task_id,
            actor_id=actor_id,
            actor_type="BRAIN",
            trust_class="SANDBOXED",
            capability={"allowed_effects": ["ACTION_PROPOSAL"], "sandbox": "read-only"},
            context_fence=context_fence,
            result_channel=str(result_channel),
            ttl_seconds=1200,
        )
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version", "invocation_id", "request_nonce", "task_id", "goal_contract_hash", "request_state_revision", "request_context_fence", "artifact_digest", "acceptance_evidence_id", "status", "role", "verdict", "findings", "recommended_actions", "human_readable_content"],
            "properties": {
                "schema_version": {"const": 1},
                "invocation_id": {"type": "string"}, "request_nonce": {"type": "string"}, "task_id": {"type": "string"},
                "goal_contract_hash": {"type": "string"}, "request_state_revision": {"type": "integer"}, "request_context_fence": {"type": "string"},
                "artifact_digest": {"const": artifact_digest}, "acceptance_evidence_id": {"const": acceptance_evidence_id},
                "status": {"const": "DONE"}, "role": {"const": "REVIEWER"}, "verdict": {"type": "string", "enum": ["PASS", "REWORK", "BLOCKED"]},
                "findings": {"type": "array", "items": {"type": "string"}},
                "recommended_actions": {"type": "array", "items": {"type": "string"}}, "human_readable_content": {"type": "string"}
            }
        }
        schema_path = workspace / "result-schema.json"; write_json(schema_path, schema)
        binding = {
            "invocation_id": receipt["invocation_id"], "request_nonce": receipt["request_nonce"], "task_id": task_id,
            "goal_contract_hash": receipt["goal_contract_hash"], "request_state_revision": receipt["state_revision"],
            "request_context_fence": context_fence, "artifact_digest": artifact_digest,
            "acceptance_evidence_id": acceptance_evidence_id, "role": role,
        }
        machine_prompt = (
            "Act only as a read-only proposal/review Brain. Do not modify files and do not perform external writes. "
            "Return the requested JSON schema, copy every binding field exactly, and set an explicit verdict. "
            "PASS requires an empty findings list; otherwise use REWORK or BLOCKED.\n"
            f"BINDING={canonical_json(binding)}\nTASK={prompt}"
        )
        result = run_structured(
            self.config["workers"]["codex_cli"],
            [
                "exec", "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check", "--color", "never",
                "--output-schema", str(schema_path), "--output-last-message", str(result_channel), "--json", machine_prompt,
            ],
            cwd=str(workspace),
            allowed_cwd_roots=[str(self.output_root)],
            timeout_seconds=300,
            register=self._register_callback(task_id=task_id, invocation_id=receipt["invocation_id"], effect_class="BRAIN"),
        )
        atomic_write(events_path, result.stdout)
        if result.exit_code != 0 or result.timed_out or not result_channel.exists():
            raise RuntimeFailure(f"Codex call failed: {result.safe_record()}")
        envelope = read_json(result_channel)
        source = {
            "actor_id": actor_id,
            "process_id": result.pid,
            "process_start_identity": result.process_start_identity,
            "controlled_stdout_hash": sha256_text(result.stdout),
            "result_file_hash": sha256_file(result_channel),
        }
        verification = self.store.verify_and_record_result(receipt["invocation_id"], envelope, source)
        return {"envelope": envelope, "source_binding": source, "verification": verification, "process": result.safe_record()}

    def invoke_worker_adapter(
        self,
        *,
        task_id: str,
        context_fence: str,
        worker_id: str,
        objective: str | None = None,
        capability_grant: dict[str, Any] | None = None,
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        """Run any registered Worker through one generic high-level path.

        Two different worker registrations (scripts) are interchangeable here:
        there is no per-worker code branch. The worker only sees the stable task
        capsule and capability grant; its result must satisfy the per-artifact
        digest proof exactly like the brokered local worker.
        """
        registrations = self.store.registry("worker_registry")
        registration = next((item for item in registrations if item.get("worker_id") == worker_id), None)
        if not registration:
            raise RuntimeFailure(f"worker adapter not registered: {worker_id}")
        workspace = self.output_root / "tasks" / task_id / f"adapter-{worker_id}-{uuid.uuid4().hex[:8]}"
        workspace.mkdir(parents=True, exist_ok=False)
        artifact = workspace / "worker-artifact.md"
        result_channel = workspace / "result.json"
        grant = capability_grant or {
            "capabilities": registration.get("capabilities", []),
            "allowed_effects": registration.get("allowed_effects", []),
            "network_scope": registration.get("network_scope", "NONE"),
        }
        validate_capability_grant(grant)
        receipt = self._invocation(
            task_id=task_id,
            actor_id=worker_id,
            actor_type="WORKER",
            trust_class=registration.get("execution_trust_class", "BROKERED"),
            capability=grant,
            context_fence=context_fence,
            result_channel=str(result_channel),
        )
        goal = self.store.latest_goal(task_id)
        capsule = build_task_capsule(
            task_id=task_id,
            objective=objective or str(goal.get("goal", "")),
            goal_contract_hash=goal["contract_hash"],
            state_revision=receipt["state_revision"],
            context_fence=context_fence,
            capability_grant=grant,
            allowed_roots=[str(workspace)],
        )
        request = {
            "invocation_id": receipt["invocation_id"],
            "request_nonce": receipt["request_nonce"],
            "task_id": task_id,
            "goal_contract_hash": capsule["goal_contract_hash"],
            "request_state_revision": capsule["state_revision"],
            "request_context_fence": context_fence,
            "worker_id": worker_id,
            "variant": registration.get("variant"),
            "capsule": capsule,
            "workspace": str(workspace),
            "artifact_path": str(artifact),
        }
        request_path = workspace / "request.json"
        write_json(request_path, request)
        result = run_structured(
            self.config["workers"]["local_python"],
            [registration["invocation"], str(request_path)],
            cwd=str(workspace),
            allowed_cwd_roots=[str(self.output_root)],
            timeout_seconds=timeout_seconds,
            register=self._register_callback(task_id=task_id, invocation_id=receipt["invocation_id"]),
        )
        if result.exit_code != 0 or result.timed_out:
            raise RuntimeFailure(f"worker adapter failed: {result.safe_record()}")
        envelope = _json_from_stdout(result.stdout)
        validate_worker_artifacts(envelope, str(workspace), resolve=safe_resolve)
        source = {
            "actor_id": worker_id,
            "worker_id": worker_id,
            "process_id": result.pid,
            "process_start_identity": result.process_start_identity,
            "controlled_stdout_hash": sha256_text(result.stdout),
            "result_channel": str(result_channel),
        }
        verification = self.store.verify_and_record_result(receipt["invocation_id"], envelope, source)
        return {
            "envelope": envelope,
            "capsule": capsule,
            "source_binding": source,
            "verification": verification,
            "process": result.safe_record(),
        }

    def bsk_status(self) -> dict[str, Any]:
        bsk = self.config["browser"]["bsk_executable"]
        home = self.config["browser"]["bsk_home"]
        result = run_structured(
            bsk,
            ["status"],
            cwd=str(self.code_root),
            allowed_cwd_roots=[str(self.code_root)],
            env={"BSK_HOME": home},
            timeout_seconds=15,
        )
        return {"ready": result.exit_code == 0, "status": result.stdout, "process": result.safe_record()}


def secrets_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex[:8]
