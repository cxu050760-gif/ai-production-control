from __future__ import annotations

"""V0.8 Official Runtime adapter contract.

This is a semantic port of the historical M1 high-level adapter boundary. It
is deliberately fail-closed and does not grant permissions or authorize
external effects; capability/effect/network fields are descriptive metadata.
"""

import hashlib
import json
from enum import Enum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable

CONTRACT_VERSION = "V0.8-ADAPTER-CORE-1"
REGISTRY_VERSION = 1


class ProviderKind(str, Enum):
    API_MODEL = "API_MODEL"
    WEB_SESSION = "WEB_SESSION"


PROVIDER_KIND_API_MODEL = ProviderKind.API_MODEL.value
PROVIDER_KIND_WEB_SESSION = ProviderKind.WEB_SESSION.value
PROVIDER_KINDS = frozenset(item.value for item in ProviderKind)
NETWORK_SCOPES = frozenset({"NONE", "MODEL_PROVIDER_ONLY", "ALLOW_SCOPED"})

RESULT_DONE = "DONE"
RESULT_FAILED = "FAILED"
RESULT_STATUSES = frozenset({RESULT_DONE, RESULT_FAILED})

ERROR_OK = "OK"
ERROR_INVALID_CAPSULE = "INVALID_CAPSULE"
ERROR_FORBIDDEN_INTERNAL_TERM = "FORBIDDEN_INTERNAL_TERM"
ERROR_REGISTRY_MISSING = "REGISTRY_MISSING"
ERROR_REGISTRY_INVALID = "REGISTRY_INVALID"
ERROR_UNKNOWN_WORKER = "UNKNOWN_WORKER"
ERROR_WORKER_UNAVAILABLE = "WORKER_UNAVAILABLE"
ERROR_WORKER_FAILED = "WORKER_FAILED"
ERROR_WORKER_TIMEOUT = "WORKER_TIMEOUT"
ERROR_MALFORMED_RESULT = "MALFORMED_RESULT"
ERROR_SOURCE_BINDING_MISMATCH = "SOURCE_BINDING_MISMATCH"
ERROR_ARTIFACT_INTEGRITY = "ARTIFACT_INTEGRITY_ERROR"
ERROR_ARTIFACT_OUTSIDE_WORKSPACE = "ARTIFACT_OUTSIDE_WORKSPACE"
ERROR_CODES = frozenset(
    {
        ERROR_OK,
        ERROR_INVALID_CAPSULE,
        ERROR_FORBIDDEN_INTERNAL_TERM,
        ERROR_REGISTRY_MISSING,
        ERROR_REGISTRY_INVALID,
        ERROR_UNKNOWN_WORKER,
        ERROR_WORKER_UNAVAILABLE,
        ERROR_WORKER_FAILED,
        ERROR_WORKER_TIMEOUT,
        ERROR_MALFORMED_RESULT,
        ERROR_SOURCE_BINDING_MISMATCH,
        ERROR_ARTIFACT_INTEGRITY,
        ERROR_ARTIFACT_OUTSIDE_WORKSPACE,
    }
)

WORKER_ERROR_CODES = frozenset(
    {
        "OK",
        "PERMISSION_DENIED",
        "RESOURCE_NOT_FOUND",
        "RESOURCE_STALE",
        "TIMEOUT",
        "UNKNOWN",
        "BUDGET_EXCEEDED",
        "HARD_BLOCKED",
        "INVALID_TASK",
    }
)

# Historical M1 black-box isolation vocabulary. These terms may exist here as
# the guard definition, but are rejected from capsules, worker results, error
# details and artifact bytes crossing the weak-worker boundary.
FORBIDDEN_WEAK_WORKER_TERMS = frozenset(
    {
        "bsk",
        "daemon",
        "marker",
        "yz_lib",
        "bridge",
        "cft_executable",
        "bsk_daemon_port",
        "52900",
        "chrome-extension",
        "session internals",
        "runtime recovery internals",
    }
)


class AdapterContractError(RuntimeError):
    def __init__(self, code: str, detail: str):
        if code not in ERROR_CODES:
            code = ERROR_MALFORMED_RESULT
        super().__init__(detail)
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require_keys(value: dict[str, Any], required: Iterable[str], *, label: str, code: str) -> None:
    missing = sorted(set(required) - set(value))
    if missing:
        raise AdapterContractError(code, f"{label} missing required fields: {missing}")


def _require_exact_keys(value: dict[str, Any], required: Iterable[str], *, label: str, code: str) -> None:
    expected = set(required)
    _require_keys(value, expected, label=label, code=code)
    extra = sorted(set(value) - expected)
    if extra:
        raise AdapterContractError(code, f"{label} has unexpected fields: {extra}")


def _require_string_list(value: Any, *, label: str, code: str) -> list[str]:
    if not isinstance(value, list) or any(not _is_nonempty_str(item) for item in value):
        raise AdapterContractError(code, f"{label} must be a list of non-empty strings")
    if len(set(value)) != len(value):
        raise AdapterContractError(code, f"{label} must not contain duplicates")
    return list(value)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def artifact_set_id(declarations: list[dict[str, str]]) -> str:
    canonical = sorted(declarations, key=lambda item: (item["path"], item["media_type"]))
    return sha256_bytes(canonical_json(canonical).encode("utf-8"))


def _contains_forbidden_bytes(payload: bytes) -> str | None:
    lowered = payload.lower()
    for term in sorted(FORBIDDEN_WEAK_WORKER_TERMS):
        if term.encode("utf-8").lower() in lowered:
            return term
    return None


def assert_no_forbidden_terms(payload: Any, *, label: str) -> None:
    raw = canonical_json(payload).encode("utf-8") if not isinstance(payload, (bytes, bytearray)) else bytes(payload)
    term = _contains_forbidden_bytes(raw)
    if term is not None:
        raise AdapterContractError(
            ERROR_FORBIDDEN_INTERNAL_TERM,
            f"{label} contains forbidden weak-worker internal term: {term}",
        )


def validate_artifact_declarations(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise AdapterContractError(ERROR_INVALID_CAPSULE, "artifact_declarations must be a non-empty list")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise AdapterContractError(ERROR_INVALID_CAPSULE, f"artifact declaration {index} must be an object")
        _require_exact_keys(item, {"path", "media_type"}, label=f"artifact declaration {index}", code=ERROR_INVALID_CAPSULE)
        path = item.get("path")
        media_type = item.get("media_type")
        if not _is_nonempty_str(path) or not _is_nonempty_str(media_type):
            raise AdapterContractError(ERROR_INVALID_CAPSULE, f"artifact declaration {index} has invalid fields")
        slash_path = path.replace("\\", "/")
        posix = PurePosixPath(slash_path)
        windows = PureWindowsPath(path)
        if (
            posix.is_absolute()
            or windows.is_absolute()
            or bool(windows.drive)
            or slash_path in (".", "..")
            or ".." in posix.parts
        ):
            raise AdapterContractError(ERROR_INVALID_CAPSULE, f"artifact declaration path is not workspace-relative: {path}")
        normalized = str(posix)
        if normalized in seen:
            raise AdapterContractError(ERROR_INVALID_CAPSULE, f"duplicate artifact declaration: {normalized}")
        seen.add(normalized)
        out.append({"path": normalized, "media_type": media_type})
    return out


def build_task_capsule(
    *,
    task_id: str,
    invocation_id: str,
    worker_id: str,
    context_id: str,
    objective: str,
    artifact_declarations: list[dict[str, str]],
    capabilities: list[str],
    allowed_effects: list[str],
    network_scope: str,
) -> dict[str, Any]:
    declarations = validate_artifact_declarations(artifact_declarations)
    base: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "capsule_type": "TASK_CAPSULE",
        "role": "WORKER",
        "task_id": task_id,
        "invocation_id": invocation_id,
        "worker_id": worker_id,
        "context_id": context_id,
        "objective": objective,
        "artifact_declarations": declarations,
        "artifact_set_id": artifact_set_id(declarations),
        "metadata": {
            "capabilities": capabilities,
            "allowed_effects": allowed_effects,
            "network_scope": network_scope,
            "authority_grant": False,
            "effect_authorization": False,
        },
    }
    validate_task_capsule({**base, "capsule_id": "0" * 64}, verify_identity=False)
    capsule_id = sha256_bytes(canonical_json(base).encode("utf-8"))
    capsule = {**base, "capsule_id": capsule_id}
    validate_task_capsule(capsule)
    return capsule


def validate_task_capsule(capsule: Any, *, verify_identity: bool = True) -> dict[str, Any]:
    if not isinstance(capsule, dict):
        raise AdapterContractError(ERROR_INVALID_CAPSULE, "Task Capsule must be an object")
    required = {
        "contract_version",
        "capsule_type",
        "role",
        "task_id",
        "invocation_id",
        "worker_id",
        "context_id",
        "objective",
        "artifact_declarations",
        "artifact_set_id",
        "metadata",
        "capsule_id",
    }
    _require_exact_keys(capsule, required, label="Task Capsule", code=ERROR_INVALID_CAPSULE)
    if capsule.get("contract_version") != CONTRACT_VERSION:
        raise AdapterContractError(ERROR_INVALID_CAPSULE, "Task Capsule contract_version mismatch")
    if capsule.get("capsule_type") != "TASK_CAPSULE" or capsule.get("role") != "WORKER":
        raise AdapterContractError(ERROR_INVALID_CAPSULE, "Task Capsule fixed envelope fields are invalid")
    for field in ("task_id", "invocation_id", "worker_id", "context_id", "objective"):
        if not _is_nonempty_str(capsule.get(field)):
            raise AdapterContractError(ERROR_INVALID_CAPSULE, f"Task Capsule {field} must be a non-empty string")
    declarations = validate_artifact_declarations(capsule.get("artifact_declarations"))
    declared_set_id = capsule.get("artifact_set_id")
    if (
        not isinstance(declared_set_id, str)
        or len(declared_set_id) != 64
        or any(ch not in "0123456789abcdef" for ch in declared_set_id)
        or declared_set_id != artifact_set_id(declarations)
    ):
        raise AdapterContractError(ERROR_INVALID_CAPSULE, "Task Capsule artifact_set_id mismatch")
    metadata = capsule.get("metadata")
    if not isinstance(metadata, dict):
        raise AdapterContractError(ERROR_INVALID_CAPSULE, "Task Capsule metadata must be an object")
    _require_exact_keys(
        metadata,
        {"capabilities", "allowed_effects", "network_scope", "authority_grant", "effect_authorization"},
        label="Task Capsule metadata",
        code=ERROR_INVALID_CAPSULE,
    )
    _require_string_list(metadata.get("capabilities"), label="metadata.capabilities", code=ERROR_INVALID_CAPSULE)
    _require_string_list(metadata.get("allowed_effects"), label="metadata.allowed_effects", code=ERROR_INVALID_CAPSULE)
    if metadata.get("network_scope") not in NETWORK_SCOPES:
        raise AdapterContractError(ERROR_INVALID_CAPSULE, "metadata.network_scope is invalid")
    if metadata.get("authority_grant") is not False or metadata.get("effect_authorization") is not False:
        raise AdapterContractError(ERROR_INVALID_CAPSULE, "V0.8 metadata cannot carry authority/effect authorization")
    capsule_id = capsule.get("capsule_id")
    if not isinstance(capsule_id, str) or len(capsule_id) != 64 or any(ch not in "0123456789abcdef" for ch in capsule_id):
        raise AdapterContractError(ERROR_INVALID_CAPSULE, "Task Capsule capsule_id must be lowercase SHA-256")
    if verify_identity:
        base = {key: capsule[key] for key in capsule if key != "capsule_id"}
        expected = sha256_bytes(canonical_json(base).encode("utf-8"))
        if capsule_id != expected:
            raise AdapterContractError(ERROR_INVALID_CAPSULE, "Task Capsule capsule_id mismatch")
    if declarations != capsule.get("artifact_declarations"):
        raise AdapterContractError(ERROR_INVALID_CAPSULE, "Task Capsule artifact declarations are not canonical")
    assert_no_forbidden_terms(capsule, label="Task Capsule")
    return capsule


def validate_registry(registry: Any) -> dict[str, Any]:
    if not isinstance(registry, dict):
        raise AdapterContractError(ERROR_REGISTRY_INVALID, "registry must be an object")
    _require_keys(
        registry,
        {"registry_version", "adapter_contract_version", "providers", "workers"},
        label="registry",
        code=ERROR_REGISTRY_INVALID,
    )
    if registry.get("registry_version") != REGISTRY_VERSION:
        raise AdapterContractError(ERROR_REGISTRY_INVALID, "registry_version mismatch")
    if registry.get("adapter_contract_version") != CONTRACT_VERSION:
        raise AdapterContractError(ERROR_REGISTRY_INVALID, "adapter_contract_version mismatch")
    providers = registry.get("providers")
    workers = registry.get("workers")
    if not isinstance(providers, list) or not isinstance(workers, list):
        raise AdapterContractError(ERROR_REGISTRY_INVALID, "providers/workers must be lists")
    if not providers or not workers:
        raise AdapterContractError(ERROR_REGISTRY_INVALID, "providers/workers must be non-empty")
    provider_map: dict[str, dict[str, Any]] = {}
    for index, provider in enumerate(providers):
        if not isinstance(provider, dict):
            raise AdapterContractError(ERROR_REGISTRY_INVALID, f"provider {index} must be an object")
        _require_keys(provider, {"provider_id", "kind"}, label=f"provider {index}", code=ERROR_REGISTRY_INVALID)
        provider_id = provider.get("provider_id")
        if not _is_nonempty_str(provider_id) or provider_id in provider_map:
            raise AdapterContractError(ERROR_REGISTRY_INVALID, f"provider {index} has invalid/duplicate provider_id")
        if provider.get("kind") not in PROVIDER_KINDS:
            raise AdapterContractError(ERROR_REGISTRY_INVALID, f"provider {provider_id} has invalid kind")
        provider_map[provider_id] = provider
    worker_ids: set[str] = set()
    for index, worker in enumerate(workers):
        if not isinstance(worker, dict):
            raise AdapterContractError(ERROR_REGISTRY_INVALID, f"worker {index} must be an object")
        _require_keys(
            worker,
            {"worker_id", "provider_id", "command", "capabilities", "allowed_effects", "network_scope", "availability"},
            label=f"worker {index}",
            code=ERROR_REGISTRY_INVALID,
        )
        worker_id = worker.get("worker_id")
        provider_id = worker.get("provider_id")
        if not _is_nonempty_str(worker_id) or worker_id in worker_ids:
            raise AdapterContractError(ERROR_REGISTRY_INVALID, f"worker {index} has invalid/duplicate worker_id")
        if not _is_nonempty_str(provider_id) or provider_id not in provider_map:
            raise AdapterContractError(ERROR_REGISTRY_INVALID, f"worker {worker_id} references unknown provider")
        command = worker.get("command")
        if not isinstance(command, list) or not command or any(not _is_nonempty_str(part) for part in command):
            raise AdapterContractError(ERROR_REGISTRY_INVALID, f"worker {worker_id} command must be a non-empty string list")
        _require_string_list(worker.get("capabilities"), label=f"worker {worker_id} capabilities", code=ERROR_REGISTRY_INVALID)
        _require_string_list(worker.get("allowed_effects"), label=f"worker {worker_id} allowed_effects", code=ERROR_REGISTRY_INVALID)
        if worker.get("network_scope") not in NETWORK_SCOPES:
            raise AdapterContractError(ERROR_REGISTRY_INVALID, f"worker {worker_id} network_scope is invalid")
        if worker.get("availability") not in ("AVAILABLE", "UNAVAILABLE"):
            raise AdapterContractError(ERROR_REGISTRY_INVALID, f"worker {worker_id} availability is invalid")
        if "timeout_seconds" in worker:
            timeout = worker["timeout_seconds"]
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
                raise AdapterContractError(ERROR_REGISTRY_INVALID, f"worker {worker_id} timeout_seconds must be positive numeric metadata")
        worker_ids.add(worker_id)
    return registry


def validate_worker_result_envelope(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise AdapterContractError(ERROR_MALFORMED_RESULT, "worker result must be an object")
    required = {
        "contract_version",
        "result_type",
        "status",
        "source_binding",
        "artifact_paths",
        "artifact_hashes",
        "error",
        "notes",
    }
    _require_exact_keys(result, required, label="worker result", code=ERROR_MALFORMED_RESULT)
    if result.get("contract_version") != CONTRACT_VERSION or result.get("result_type") != "WORKER_RESULT":
        raise AdapterContractError(ERROR_MALFORMED_RESULT, "worker result fixed envelope fields are invalid")
    if result.get("status") not in RESULT_STATUSES:
        raise AdapterContractError(ERROR_MALFORMED_RESULT, "worker result status is invalid")
    binding = result.get("source_binding")
    if not isinstance(binding, dict):
        raise AdapterContractError(ERROR_MALFORMED_RESULT, "worker result source_binding must be an object")
    _require_exact_keys(
        binding,
        {"task_id", "invocation_id", "worker_id", "context_id", "capsule_id", "artifact_set_id"},
        label="worker result source_binding",
        code=ERROR_MALFORMED_RESULT,
    )
    for field in ("task_id", "invocation_id", "worker_id", "context_id", "capsule_id", "artifact_set_id"):
        if not _is_nonempty_str(binding.get(field)):
            raise AdapterContractError(ERROR_MALFORMED_RESULT, f"source_binding.{field} must be non-empty")
    for field in ("capsule_id", "artifact_set_id"):
        value = binding[field]
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise AdapterContractError(ERROR_MALFORMED_RESULT, f"source_binding.{field} must be lowercase SHA-256")
    paths = result.get("artifact_paths")
    hashes = result.get("artifact_hashes")
    if not isinstance(paths, list) or any(not _is_nonempty_str(item) for item in paths):
        raise AdapterContractError(ERROR_MALFORMED_RESULT, "artifact_paths must be a string list")
    if len(set(paths)) != len(paths):
        raise AdapterContractError(ERROR_MALFORMED_RESULT, "artifact_paths must not contain duplicates")
    if not isinstance(hashes, dict) or any(not _is_nonempty_str(k) or not _is_nonempty_str(v) for k, v in hashes.items()):
        raise AdapterContractError(ERROR_MALFORMED_RESULT, "artifact_hashes must be a string mapping")
    if result.get("status") == RESULT_DONE:
        if not paths:
            raise AdapterContractError(ERROR_MALFORMED_RESULT, "DONE worker result must declare artifacts")
        if result.get("error") is not None:
            raise AdapterContractError(ERROR_MALFORMED_RESULT, "DONE worker result error must be null")
    else:
        error = result.get("error")
        if not isinstance(error, dict):
            raise AdapterContractError(ERROR_MALFORMED_RESULT, "FAILED worker result must include error object")
        _require_exact_keys(error, {"code", "detail"}, label="worker result error", code=ERROR_MALFORMED_RESULT)
        if error.get("code") not in WORKER_ERROR_CODES or not isinstance(error.get("detail"), str):
            raise AdapterContractError(ERROR_MALFORMED_RESULT, "worker result error fields are invalid")
    if not isinstance(result.get("notes"), str):
        raise AdapterContractError(ERROR_MALFORMED_RESULT, "worker result notes must be a string")
    assert_no_forbidden_terms(result, label="worker result")
    return result


def validate_source_binding(result: dict[str, Any], capsule: dict[str, Any]) -> None:
    binding = result["source_binding"]
    expected = {
        "task_id": capsule["task_id"],
        "invocation_id": capsule["invocation_id"],
        "worker_id": capsule["worker_id"],
        "context_id": capsule["context_id"],
        "capsule_id": capsule["capsule_id"],
        "artifact_set_id": capsule["artifact_set_id"],
    }
    if binding != expected:
        raise AdapterContractError(ERROR_SOURCE_BINDING_MISMATCH, "worker result source binding does not match invocation capsule")


def validate_worker_artifacts(result: dict[str, Any], capsule: dict[str, Any], workspace_root: str | Path) -> dict[str, Any]:
    workspace = Path(workspace_root).resolve(strict=True)
    declared = [item["path"] for item in capsule["artifact_declarations"]]
    if not isinstance(result, dict):
        raise AdapterContractError(ERROR_ARTIFACT_INTEGRITY, "worker artifact result must be an object")
    paths = result.get("artifact_paths")
    hashes = result.get("artifact_hashes")
    if not isinstance(paths, list) or any(not _is_nonempty_str(item) for item in paths):
        raise AdapterContractError(ERROR_ARTIFACT_INTEGRITY, "artifact_paths must be a string list")
    if len(set(paths)) != len(paths):
        raise AdapterContractError(ERROR_ARTIFACT_INTEGRITY, "artifact_paths must not contain duplicates")
    if not isinstance(hashes, dict):
        raise AdapterContractError(ERROR_ARTIFACT_INTEGRITY, "artifact_hashes must be a mapping")

    # Resolve every worker-supplied path before set comparison so traversal and
    # absolute-outside-workspace attempts are classified explicitly.
    resolved: dict[str, Path] = {}
    for raw in paths:
        target = Path(raw)
        if not target.is_absolute():
            target = workspace / target
        try:
            target = target.resolve(strict=True)
        except FileNotFoundError as exc:
            raise AdapterContractError(ERROR_ARTIFACT_INTEGRITY, f"artifact does not exist: {raw}") from exc
        if not target.is_relative_to(workspace):
            raise AdapterContractError(ERROR_ARTIFACT_OUTSIDE_WORKSPACE, f"artifact outside workspace: {raw}")
        resolved[raw] = target

    if set(paths) != set(declared):
        raise AdapterContractError(ERROR_ARTIFACT_INTEGRITY, "worker artifact set differs from Task Capsule declarations")
    if set(hashes) != set(paths):
        raise AdapterContractError(ERROR_ARTIFACT_INTEGRITY, "artifact_hashes keys must exactly match artifact_paths")
    if not hashes:
        raise AdapterContractError(ERROR_ARTIFACT_INTEGRITY, "artifact_hashes must not be empty")

    proofs: list[dict[str, str]] = []
    for raw in paths:
        expected = hashes.get(raw)
        if not isinstance(expected, str) or len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
            raise AdapterContractError(ERROR_ARTIFACT_INTEGRITY, f"invalid SHA-256 digest for artifact: {raw}")
        target = resolved[raw]
        actual = sha256_file(target)
        if actual != expected:
            raise AdapterContractError(ERROR_ARTIFACT_INTEGRITY, f"artifact digest mismatch: {raw}")
        data = target.read_bytes()
        term = _contains_forbidden_bytes(data)
        if term is not None:
            raise AdapterContractError(ERROR_FORBIDDEN_INTERNAL_TERM, f"artifact contains forbidden weak-worker internal term: {term}")
        proofs.append({"path": raw, "sha256": actual})
    return {"artifact_count": len(proofs), "artifacts": proofs}
