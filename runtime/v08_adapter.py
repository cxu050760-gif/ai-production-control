from __future__ import annotations

"""V0.8 Generic Worker Adapter for the Official Runtime boundary."""

import argparse
import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from v08_adapter_contract import (
    CONTRACT_VERSION,
    ERROR_ARTIFACT_INTEGRITY,
    ERROR_MALFORMED_RESULT,
    ERROR_REGISTRY_INVALID,
    ERROR_REGISTRY_MISSING,
    ERROR_UNKNOWN_WORKER,
    ERROR_WORKER_FAILED,
    ERROR_WORKER_TIMEOUT,
    ERROR_WORKER_UNAVAILABLE,
    NETWORK_SCOPES,
    PROVIDER_KIND_API_MODEL,
    PROVIDER_KIND_WEB_SESSION,
    PROVIDER_KINDS,
    RESULT_DONE,
    AdapterContractError,
    build_task_capsule,
    validate_registry,
    validate_source_binding,
    validate_task_capsule,
    validate_worker_artifacts,
    validate_worker_result_envelope,
)

BOOTSTRAP_REGISTRY_POINTER = "adapter_registry"
DEFAULT_BOOTSTRAP = Path(__file__).with_name("bootstrap.json")
TEST_ONLY_EXECUTION_BINDING = "TEST_ONLY_EXECUTION_BINDING"

def strict_json_loads(text: str, *, error_code: str = ERROR_MALFORMED_RESULT, label: str = "JSON") -> Any:
    def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise AdapterContractError(error_code, f"{label} has duplicate JSON key: {key}")
            result[key] = value
        return result
    try:
        return json.loads(text, object_pairs_hook=reject_duplicate_pairs)
    except AdapterContractError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise AdapterContractError(error_code, f"{label} is malformed JSON") from exc

def _read_json_file(path: Path, *, missing_code: str, malformed_code: str, label: str) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AdapterContractError(missing_code, f"{label} does not exist: {path}") from exc
    except OSError as exc:
        raise AdapterContractError(missing_code, f"{label} cannot be read: {path}") from exc
    return strict_json_loads(text, error_code=malformed_code, label=label)

def load_registry(registry_path: str | Path) -> dict[str, Any]:
    path = Path(registry_path)
    value = _read_json_file(
        path,
        missing_code=ERROR_REGISTRY_MISSING,
        malformed_code=ERROR_REGISTRY_INVALID,
        label="adapter registry",
    )
    return validate_registry(value)

def _resolve_relative_registry_pointer(bootstrap: Path, pointer: str) -> Path:
    """Resolve both local-bootstrap-relative and canonical repo-relative pointers.

    The canonical B2 bootstrap lives at runtime/bootstrap.json and points to
    runtime/v08_adapter_registry.json, which is repository-root-relative.
    Existing isolated bootstrap fixtures may still point to a sibling file.
    No alias key or duplicated Registry is introduced.
    """
    relative = Path(pointer)
    candidates = (bootstrap.parent / relative, bootstrap.parent.parent / relative)
    for candidate in candidates:
        try:
            return candidate.resolve(strict=True)
        except FileNotFoundError:
            continue
    raise AdapterContractError(
        ERROR_REGISTRY_MISSING,
        f"adapter registry does not exist for bootstrap pointer: {pointer}",
    )

def resolve_registry_from_bootstrap(bootstrap_path: str | Path = DEFAULT_BOOTSTRAP) -> tuple[Path, dict[str, Any]]:
    path = Path(bootstrap_path)
    bootstrap = _read_json_file(
        path,
        missing_code=ERROR_REGISTRY_MISSING,
        malformed_code=ERROR_REGISTRY_INVALID,
        label="runtime bootstrap",
    )
    if not isinstance(bootstrap, dict):
        raise AdapterContractError(ERROR_REGISTRY_INVALID, "runtime bootstrap must be an object")
    pointer = bootstrap.get(BOOTSTRAP_REGISTRY_POINTER)
    if not isinstance(pointer, str) or not pointer.strip():
        raise AdapterContractError(
            ERROR_REGISTRY_MISSING,
            f"runtime bootstrap missing required registry pointer: {BOOTSTRAP_REGISTRY_POINTER}",
        )
    registry_path = Path(pointer)
    if registry_path.is_absolute():
        try:
            registry_path = registry_path.resolve(strict=True)
        except FileNotFoundError as exc:
            raise AdapterContractError(ERROR_REGISTRY_MISSING, f"adapter registry does not exist: {registry_path}") from exc
    else:
        registry_path = _resolve_relative_registry_pointer(path, pointer)
    return registry_path, load_registry(registry_path)

def _worker_record(registry: dict[str, Any], worker_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    workers = {item["worker_id"]: item for item in registry["workers"]}
    worker = workers.get(worker_id)
    if worker is None:
        raise AdapterContractError(ERROR_UNKNOWN_WORKER, f"worker is not registered: {worker_id}")
    providers = {item["provider_id"]: item for item in registry["providers"]}
    return worker, providers[worker["provider_id"]]

def _validate_provider_kind_runtime(provider: dict[str, Any], expected_kind: str) -> None:
    if expected_kind not in PROVIDER_KINDS:
        raise AdapterContractError(ERROR_REGISTRY_INVALID, f"invalid invocation ProviderKind: {expected_kind!r}")
    actual_kind = provider.get("kind")
    if actual_kind != expected_kind:
        raise AdapterContractError(
            ERROR_WORKER_FAILED,
            f"provider kind mismatch: invocation expects {expected_kind}, registry binds {actual_kind}",
        )

def _validate_test_only_execution_binding(binding: Any, worker_id: str) -> dict[str, Any]:
    if not isinstance(binding, dict):
        raise AdapterContractError(ERROR_WORKER_UNAVAILABLE, f"worker runtime binding unavailable: {worker_id}")
    expected = {
        "binding_type", "worker_id", "command", "allowed_effects",
        "network_scope", "timeout_seconds",
    }
    if set(binding) != expected or binding.get("binding_type") != TEST_ONLY_EXECUTION_BINDING:
        raise AdapterContractError(ERROR_WORKER_UNAVAILABLE, f"invalid test-only execution binding: {worker_id}")
    if binding.get("worker_id") != worker_id:
        raise AdapterContractError(ERROR_WORKER_UNAVAILABLE, f"test-only execution binding worker mismatch: {worker_id}")
    command = binding.get("command")
    if not isinstance(command, list) or not command or any(not isinstance(part, str) or not part for part in command):
        raise AdapterContractError(ERROR_WORKER_UNAVAILABLE, f"test-only execution command invalid: {worker_id}")
    effects = binding.get("allowed_effects")
    if not isinstance(effects, list) or any(not isinstance(item, str) or not item for item in effects):
        raise AdapterContractError(ERROR_WORKER_UNAVAILABLE, f"test-only allowed_effects invalid: {worker_id}")
    if binding.get("network_scope") not in NETWORK_SCOPES:
        raise AdapterContractError(ERROR_WORKER_UNAVAILABLE, f"test-only network_scope invalid: {worker_id}")
    timeout = binding.get("timeout_seconds")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise AdapterContractError(ERROR_WORKER_UNAVAILABLE, f"test-only timeout invalid: {worker_id}")
    return binding

def _execution_binding(
    registry: dict[str, Any],
    worker: dict[str, Any],
    explicit: dict[str, Any] | None,
) -> dict[str, Any]:
    binding = explicit
    if binding is None:
        overlays = getattr(registry, "test_only_execution_bindings", None)
        if isinstance(overlays, dict):
            binding = overlays.get(worker["worker_id"])
    if binding is None:
        raise AdapterContractError(
            ERROR_WORKER_UNAVAILABLE,
            f"worker runtime binding unavailable: {worker['worker_id']} (registry availability={worker['availability']})",
        )
    return _validate_test_only_execution_binding(binding, worker["worker_id"])

def _workspace_snapshot(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            snapshot[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot

def _assert_only_declared_workspace_mutations(
    before: dict[str, str],
    after: dict[str, str],
    capsule: dict[str, Any],
) -> None:
    declared = {item["path"] for item in capsule["artifact_declarations"]}
    changed = {path for path in set(before) | set(after) if before.get(path) != after.get(path)}
    undeclared = sorted(changed - declared)
    if undeclared:
        raise AdapterContractError(
            ERROR_ARTIFACT_INTEGRITY,
            f"worker mutated undeclared workspace paths: {undeclared}",
        )

def invoke_worker(
    *,
    worker_id: str,
    task_id: str,
    context_id: str,
    objective: str,
    workspace: str | Path,
    artifact_declarations: list[dict[str, str]],
    registry: dict[str, Any] | None = None,
    bootstrap_path: str | Path = DEFAULT_BOOTSTRAP,
    timeout_seconds: float | None = None,
    provider_kind: str = PROVIDER_KIND_API_MODEL,
    test_only_execution_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if registry is None:
        registry_path, registry = resolve_registry_from_bootstrap(bootstrap_path)
        registry_source = str(registry_path)
    else:
        registry = validate_registry(registry)
        registry_source = "INJECTED_CANONICAL_REGISTRY"

    worker, provider = _worker_record(registry, worker_id)
    # ProviderKind is checked before execution availability/binding. This keeps
    # F01/F02 fail-closed BEFORE WORKER and avoids masking a kind mismatch as an
    # availability failure.
    _validate_provider_kind_runtime(provider, provider_kind)
    binding = _execution_binding(registry, worker, test_only_execution_binding)

    root = Path(workspace).resolve(strict=True)
    if not root.is_dir():
        raise AdapterContractError(ERROR_WORKER_FAILED, "workspace must be an existing directory")

    invocation_id = str(uuid.uuid4())
    capsule = build_task_capsule(
        task_id=task_id,
        invocation_id=invocation_id,
        worker_id=worker_id,
        context_id=context_id,
        objective=objective,
        artifact_declarations=artifact_declarations,
        capabilities=list(worker["capabilities"]),
        allowed_effects=list(binding["allowed_effects"]),
        network_scope=binding["network_scope"],
    )
    validate_task_capsule(capsule)

    command = list(binding["command"])
    configured_timeout = binding["timeout_seconds"]
    effective_timeout = float(timeout_seconds if timeout_seconds is not None else configured_timeout)
    if effective_timeout <= 0:
        raise AdapterContractError(ERROR_WORKER_UNAVAILABLE, "worker timeout_seconds must be positive")

    before_workspace = _workspace_snapshot(root)
    try:
        process = subprocess.run(
            command,
            input=json.dumps(capsule, ensure_ascii=False),
            text=True,
            capture_output=True,
            cwd=str(root),
            timeout=effective_timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AdapterContractError(ERROR_WORKER_TIMEOUT, "worker invocation timed out") from exc
    except OSError as exc:
        raise AdapterContractError(ERROR_WORKER_FAILED, "worker process could not be started") from exc

    after_workspace = _workspace_snapshot(root)
    _assert_only_declared_workspace_mutations(before_workspace, after_workspace, capsule)

    raw_stdout = process.stdout.strip()
    result = strict_json_loads(raw_stdout, label="worker result")
    validate_worker_result_envelope(result)
    validate_source_binding(result, capsule)
    if result["status"] != RESULT_DONE or process.returncode != 0:
        raise AdapterContractError(ERROR_WORKER_FAILED, "worker did not return a successful result")

    artifact_proof = validate_worker_artifacts(result, capsule, root)
    return {
        "contract_version": CONTRACT_VERSION,
        "status": RESULT_DONE,
        "worker_result": result,
        "capsule": capsule,
        "artifact_proof": artifact_proof,
        "source_binding": dict(result["source_binding"]),
        "provider_metadata": {"provider_id": provider["provider_id"], "kind": provider["kind"]},
        "invocation_provider_kind": provider_kind,
        "registry_source": registry_source,
        "execution_binding_source": TEST_ONLY_EXECUTION_BINDING,
        "process": {"exit_code": process.returncode},
    }

def adapter_check(*, bootstrap_path: str | Path = DEFAULT_BOOTSTRAP) -> dict[str, Any]:
    registry_path, registry = resolve_registry_from_bootstrap(bootstrap_path)
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "OK",
        "registry_path": str(registry_path),
        "provider_count": len(registry["providers"]),
        "reviewer_count": len(registry["reviewers"]),
        "worker_count": len(registry["workers"]),
    }

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="V0.8 Generic Worker Adapter")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("adapter-check")
    check.add_argument("--bootstrap", default=str(DEFAULT_BOOTSTRAP))
    invoke = sub.add_parser("adapter-invoke")
    invoke.add_argument("--bootstrap", default=str(DEFAULT_BOOTSTRAP))
    invoke.add_argument("--worker-id", required=True)
    invoke.add_argument("--task-id", required=True)
    invoke.add_argument("--context-id", required=True)
    invoke.add_argument("--objective", required=True)
    invoke.add_argument("--workspace", required=True)
    invoke.add_argument("--artifact", action="append", required=True)
    invoke.add_argument("--media-type", default="application/octet-stream")
    invoke.add_argument(
        "--provider-kind",
        choices=(PROVIDER_KIND_API_MODEL, PROVIDER_KIND_WEB_SESSION),
        default=PROVIDER_KIND_API_MODEL,
    )
    invoke.add_argument("--timeout-seconds", type=float, default=None)
    return parser

def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "adapter-check":
            output = adapter_check(bootstrap_path=args.bootstrap)
        else:
            declarations = [{"path": item, "media_type": args.media_type} for item in args.artifact]
            output = invoke_worker(
                worker_id=args.worker_id,
                task_id=args.task_id,
                context_id=args.context_id,
                objective=args.objective,
                workspace=args.workspace,
                artifact_declarations=declarations,
                bootstrap_path=args.bootstrap,
                timeout_seconds=args.timeout_seconds,
                provider_kind=args.provider_kind,
            )
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
        return 0
    except AdapterContractError as exc:
        print(json.dumps(
            {"contract_version": CONTRACT_VERSION, "status": "FAILED", "error": exc.as_dict()},
            ensure_ascii=False, sort_keys=True,
        ))
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
