from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from .store import ControlStore, GateDenied
from .util import canonical_json, read_json, redact, sha256_file, sha256_text, utc_now, write_json


DATA_CLASSES = ("PUBLIC", "INTERNAL", "PRIVATE_LOCAL", "SENSITIVE", "SECRET", "UNKNOWN")

# Raw credentials are never authority material. Authorization scopes may carry
# references to credentials, but not the credentials themselves.
RAW_CREDENTIAL_KEYS = {
    "password",
    "passwd",
    "secret",
    "client_secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "cookie",
    "cookies",
    "authorization",
    "authorization_header",
    "bearer",
}
CREDENTIAL_REFERENCE_KEYS = {"credential_ref", "secret_ref", "token_ref", "profile_ref", "account_ref"}

TCB_RELATIVE_FILES = (
    "ai-control.cmd",
    "scripts/ai_control.py",
    "scripts/browser_runtime.mjs",
    "scripts/local_worker.py",
    "src/aicontrol/__init__.py",
    "src/aicontrol/util.py",
    "src/aicontrol/process.py",
    "src/aicontrol/store.py",
    "src/aicontrol/security.py",
    "src/aicontrol/runtimes.py",
    "src/aicontrol/controller.py",
    "src/aicontrol/acceptance.py",
    "config/production.json",
    "package.json",
    "package-lock.json",
)


def normalized_classification(value: str) -> str:
    result = value.upper()
    if result not in DATA_CLASSES:
        raise GateDenied(f"unknown data classification: {value}")
    return "PRIVATE_LOCAL" if result == "UNKNOWN" else result


def _scope_dict(authorization: dict[str, Any]) -> dict[str, Any]:
    scope = authorization.get("scope")
    if isinstance(scope, dict):
        return scope
    raw = authorization.get("scope_json")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _matches_authorized(expected: Any, actual: Any, *, wildcard: bool = False) -> bool:
    if expected is None:
        return False
    if wildcard and expected == "*":
        return True
    return str(expected) == str(actual)


def authority_scope_allowed(
    *,
    authorization: dict[str, Any],
    task_id: str,
    provider: str,
    resource: str,
    purpose: str,
    identity: str,
    destination: str | None = None,
    classification: str | None = None,
) -> bool:
    """Pure Authority Matrix check used by both legacy ControlStore and Runtime Lite.

    The executor identity and purpose are deliberately exact-bound. Provider,
    resource, and destination may use an explicitly granted ``*`` wildcard.
    Missing bindings fail closed.
    """
    if not isinstance(authorization, dict):
        return False
    scope = _scope_dict(authorization)
    if not _matches_authorized(authorization.get("task_id"), task_id):
        return False
    expected_provider = authorization.get("provider", scope.get("provider"))
    expected_resource = authorization.get("resource", scope.get("resource"))
    expected_purpose = authorization.get("purpose", scope.get("purpose"))
    expected_identity = authorization.get("identity", scope.get("identity"))
    if not _matches_authorized(expected_provider, provider, wildcard=True):
        return False
    if not _matches_authorized(expected_resource, resource, wildcard=True):
        return False
    if not _matches_authorized(expected_purpose, purpose):
        return False
    if not _matches_authorized(expected_identity, identity):
        return False
    if destination is not None:
        expected_destination = scope.get("destination", authorization.get("destination"))
        if not _matches_authorized(expected_destination, destination, wildcard=True):
            return False
    if classification is not None:
        try:
            normalized = normalized_classification(classification)
        except GateDenied:
            return False
        allowed_classes = scope.get("data_classes")
        if not isinstance(allowed_classes, list) or normalized not in allowed_classes:
            return False
    return True


def require_credential_isolation(scope: dict[str, Any]) -> None:
    """Reject raw credential material; references are the only permitted form."""
    if not isinstance(scope, dict):
        raise GateDenied("authorization scope must be an object")

    def walk(value: Any, path: tuple[str, ...] = ()) -> None:
        if isinstance(value, dict):
            for raw_key, child in value.items():
                key = str(raw_key).strip().lower()
                if key in CREDENTIAL_REFERENCE_KEYS or key.endswith("_ref"):
                    continue
                if key in RAW_CREDENTIAL_KEYS:
                    dotted = ".".join((*path, str(raw_key)))
                    raise GateDenied(f"raw credential material forbidden in authority scope: {dotted}")
                walk(child, (*path, str(raw_key)))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, (*path, str(index)))

    walk(scope)


def human_gate_allowed(*, required: bool, reference: str | None) -> bool:
    if not required:
        return True
    return bool(isinstance(reference, str) and reference.strip())


def egress_allowed(
    *,
    classification: str,
    destination: str,
    provider: str,
    purpose: str,
    goal_contract: dict[str, Any],
    authorization_scope: dict[str, Any] | None,
) -> bool:
    classification = normalized_classification(classification)
    policy = goal_contract.get("data_egress_policy", {})
    if classification == "SECRET":
        return False
    destination_policy = policy.get(destination) or policy.get(provider) or policy.get("default", [])
    allowed_classes = set(destination_policy if isinstance(destination_policy, list) else [])
    if classification not in allowed_classes:
        return False
    if authorization_scope:
        if authorization_scope.get("provider") not in (provider, "*"):
            return False
        if authorization_scope.get("destination") not in (destination, "*"):
            return False
        if authorization_scope.get("purpose") != purpose:
            return False
        if classification not in authorization_scope.get("data_classes", []):
            return False
    if classification in ("PRIVATE_LOCAL", "SENSITIVE"):
        if not authorization_scope:
            return False
    return True


def _manifest_body(code_root: Path, generation: int) -> dict[str, Any]:
    files = []
    for relative in TCB_RELATIVE_FILES:
        path = code_root / relative
        if not path.is_file():
            raise GateDenied(f"TCB file missing: {relative}")
        files.append({"path": relative, "sha256": sha256_file(path), "size": path.stat().st_size})
    return {
        "schema_version": 1,
        "controller_identity": "ai-production-control/python-sqlite",
        "generation": generation,
        "scope": list(TCB_RELATIVE_FILES),
        "files": files,
        "created_at": utc_now(),
        "same_user_limitation": "NTFS same-user code cannot provide a separate security principal; every external effect re-verifies hashes and workers are withheld from TCB paths.",
    }


def seal_tcb(store: ControlStore, code_root: str | Path, *, reason: str) -> dict[str, Any]:
    root = Path(code_root).resolve(strict=True)
    current = int(store.meta("tcb_generation", "0") or "0")
    generation = current + 1
    body = _manifest_body(root, generation)
    body["reason"] = reason
    manifest_hash = sha256_text(canonical_json(body))
    manifest = {**body, "manifest_hash": manifest_hash}
    manifest_path = root / "config" / "tcb-manifest.json"
    write_json(manifest_path, manifest)
    with store.transaction() as conn:
        store.set_meta("tcb_generation", str(generation), conn)
        store.set_meta("tcb_manifest_hash", manifest_hash, conn)
        store.set_meta("tcb_status", "VERIFIED", conn)
        previous, authority_generation = store._next_generation(conn, "__controller__", "tcb")
        store._append_authority_event(
            conn,
            event_type="CONTROLLER_TCB_VERIFIED",
            task_id="__controller__",
            goal_version=None,
            goal_hash=None,
            authorization_id=None,
            decision_nonce=None,
            previous_generation=previous,
            new_generation=authority_generation,
            scope_digest=sha256_text(canonical_json(TCB_RELATIVE_FILES)),
            state_revision=store.state_head(),
            data={
                "tcb_generation": generation,
                "manifest_hash": manifest_hash,
                "reason": reason,
                "status": "VERIFIED",
            },
        )
    store.durable_barrier()
    return {"status": "VERIFIED", "generation": generation, "manifest_hash": manifest_hash, "path": str(manifest_path)}


def verify_tcb(
    store: ControlStore,
    code_root: str | Path,
    *,
    manifest_path: str | Path | None = None,
    enforce_status: bool = True,
) -> dict[str, Any]:
    root = Path(code_root).resolve(strict=True)
    path = Path(manifest_path) if manifest_path else root / "config" / "tcb-manifest.json"
    if not path.is_file():
        if enforce_status:
            store.set_meta("tcb_status", "UNVERIFIED_AFTER_CONTROLLER_CHANGE")
        raise GateDenied("TCB manifest missing")
    manifest = read_json(path)
    manifest_hash = manifest.pop("manifest_hash", None)
    expected_hash = sha256_text(canonical_json(manifest))
    errors = []
    if manifest_hash != expected_hash:
        errors.append("manifest_hash")
    if manifest_hash != store.meta("tcb_manifest_hash"):
        errors.append("controller_record")
    for item in manifest.get("files", []):
        file_path = root / item["path"]
        if not file_path.is_file() or sha256_file(file_path) != item["sha256"] or file_path.stat().st_size != item["size"]:
            errors.append(item["path"])
    if errors:
        if enforce_status:
            store.set_meta("tcb_status", "UNVERIFIED_AFTER_CONTROLLER_CHANGE")
            store.durable_barrier()
        raise GateDenied(f"Controller TCB integrity failure: {errors}")
    if enforce_status and store.meta("tcb_status") != "VERIFIED":
        raise GateDenied("Controller TCB status is not VERIFIED")
    return {
        "status": "VERIFIED",
        "generation": manifest["generation"],
        "manifest_hash": manifest_hash,
        "verified_files": len(manifest.get("files", [])),
    }


def scan_evidence_privacy(paths: Iterable[str | Path]) -> dict[str, Any]:
    materialized = [Path(raw) for raw in paths]
    findings: list[dict[str, Any]] = []
    scanned = 0
    for path in materialized:
        if not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
            continue
        if path.suffix.lower() not in (".txt", ".md", ".json", ".log", ".csv", ".html", ".js", ".py"):
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        if redact(text) != text:
            findings.append({"path": str(path), "finding": "credential-like material"})
    return {"passed": not findings, "findings": findings, "scanned": scanned, "candidates": len(materialized)}


def credential_presence(environment_names: Iterable[str]) -> dict[str, str]:
    return {name: "PRESENT" if os.environ.get(name) else "MISSING" for name in environment_names}


def browser_profile_identity(profile_path: str | Path) -> str:
    profile = Path(profile_path).resolve(strict=True)
    return sha256_text(str(profile).lower())
