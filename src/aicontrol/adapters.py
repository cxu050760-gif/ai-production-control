from __future__ import annotations

"""M1 Adapter contract layer.

Defines the stable, high-level contract boundary that all interchangeable
Brain / Worker / Reviewer / Tool / Provider adapters observe, plus the
per-artifact digest proof that any Worker result must satisfy.

Goals (M1):
- `BrainProvider.propose(capsule) -> proposal`
- `WorkerAdapter.execute(task_capsule, capability_grant) -> result/evidence/proposals`
- `ReviewerProvider.review(acceptance_bundle) -> PASS|REWORK|BLOCKED + findings`
- `ToolAdapter.execute(effect_intent) -> source-bound outcome` (stable error codes)
- API-model and web-session providers are two distinct provider kinds.
- Weak Workers see only this high-level contract; Bridge/daemon/session/marker
  internals never surface here and are never required to interpret a result.
"""

from typing import Any, Callable

from .store import GateDenied
from .util import sha256_file


class AdapterContractError(RuntimeError):
    """A result violates the stable high-level adapter contract."""


ADAPTER_CONTRACT_VERSION = 1

# Provider kinds. Web-session providers (a logged-in browser conversation) are
# NOT interchangeable with API-model providers; they are routed separately.
PROVIDER_KIND_API_MODEL = "API_MODEL"
PROVIDER_KIND_WEB_SESSION = "WEB_SESSION"
PROVIDER_KINDS = (PROVIDER_KIND_API_MODEL, PROVIDER_KIND_WEB_SESSION)

# Reviewer lifecycle roles. R-PROD handles meaningful milestones and Evidence;
# E-LAB handles transport / upload / failure-injection experiments only.
REVIEWER_ROLE_R_PROD = "R_PROD"
REVIEWER_ROLE_E_LAB = "E_LAB"

# The ONLY status codes a weak Worker needs to understand from a ToolAdapter.
# Bridge/daemon/session/marker/yz_lib/lower-layer reasons never cross this
# boundary. The Controller's blocked-recovery responsibility stays hidden.
STABLE_TOOL_ERROR_CODES = frozenset(
    {
        "OK",
        "PERMISSION_DENIED",
        "RESOURCE_NOT_FOUND",
        "RESOURCE_STALE",
        "TIMEOUT",
        "UNKNOWN",
        "BUDGET_EXCEEDED",
        "HARD_BLOCKED",
    }
)

# Internal-transport tokens that MUST NOT be handed to a weak Worker in a task
# capsule, nor be required to interpret its result/source. Keeps the Bridge
# black-box invariant complete.
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
        "dom hack",
        "click internals",
    }
)


def build_task_capsule(
    *,
    task_id: str,
    objective: str,
    goal_contract_hash: str,
    state_revision: int,
    context_fence: str,
    capability_grant: dict[str, Any],
    allowed_roots: list[str],
) -> dict[str, Any]:
    """The minimal high-level contract a weak Worker receives.

    Deliberately contains no internal transport knowledge. If future code ever
    adds an internal field here, the Fresh-Weak-Worker black-box test fails.
    """
    return {
        "adapter_contract_version": ADAPTER_CONTRACT_VERSION,
        "role": "WORKER",
        "task_id": task_id,
        "objective": objective,
        "goal_contract_hash": goal_contract_hash,
        "state_revision": state_revision,
        "context_fence": context_fence,
        "allowed_roots": [str(item) for item in allowed_roots],
        "capabilities": sorted(capability_grant.get("capabilities", [])),
        "allowed_effects": sorted(capability_grant.get("allowed_effects", [])),
        "allow_network": capability_grant.get("network_scope", "NONE") != "NONE",
    }


def validate_capability_grant(grant: dict[str, Any]) -> None:
    """A capability grant must be a stable, high-level shape."""
    if not isinstance(grant, dict):
        raise AdapterContractError("capability grant must be an object")
    required = {"capabilities", "allowed_effects", "network_scope"}
    missing = sorted(required - set(grant))
    if missing:
        raise AdapterContractError(f"capability grant missing: {missing}")
    if not isinstance(grant.get("capabilities"), list) or not isinstance(grant.get("allowed_effects"), list):
        raise AdapterContractError("grant capabilities/allowed_effects must be lists")
    if grant.get("network_scope") not in ("NONE", "MODEL_PROVIDER_ONLY", "ALLOW_SCOPED"):
        raise AdapterContractError(f"unknown network_scope: {grant.get('network_scope')}")


def assert_no_forbidden_terms(payload: str) -> None:
    """Fail closed if internal-transport terms leak past the contract boundary."""
    lowered = payload.lower()
    for token in sorted(FORBIDDEN_WEAK_WORKER_TERMS):
        if token in lowered:
            raise AdapterContractError(f"weak-worker contract leaked internal term: {token}")


def validate_worker_artifacts(
    envelope: dict[str, Any],
    workspace_root: str,
    *,
    resolve: Callable[..., Any],
) -> dict[str, Any]:
    """Prove every declared `artifact_path` has a matching, correct digest.

    This is the per-item proof (not just an `isinstance(x, dict)` check) that
    the M0.5 Reviewer required for the generic worker contract: the second
    adapter must recompute SHA-256 for every artifact path, exactly as the
    brokered local worker already does, and reject any missing or wrong hash.
    """
    if not isinstance(envelope, dict):
        raise AdapterContractError("worker result must be an object")
    paths = envelope.get("artifact_paths")
    hashes = envelope.get("artifact_hashes")
    if not isinstance(paths, list) or not paths:
        raise AdapterContractError("worker result has no non-empty artifact_paths")
    if not isinstance(hashes, dict):
        raise AdapterContractError("worker artifact_hashes must be a mapping")
    proven: list[dict[str, str]] = []
    declared: set[str] = set()
    for raw in paths:
        if not isinstance(raw, str):
            raise AdapterContractError("artifact_path entry is not a string")
        target = resolve(raw, [workspace_root], must_exist=True)
        resolved = str(target)
        declared.add(resolved)
        expected = hashes.get(resolved)
        if expected is None:
            raise AdapterContractError(f"artifact_path has no artifact digest: {resolved}")
        if not isinstance(expected, str) or expected != sha256_file(target):
            raise AdapterContractError(f"artifact digest mismatch for {resolved}")
        proven.append({"path": resolved, "sha256": expected})
    if set(hashes.keys()) != declared:
        raise AdapterContractError("artifact_hashes keys must exactly match resolved artifact_paths")
    return {"artifact_count": len(proven), "artifacts": proven}


def validate_reviewer_verdict_guard(envelope: dict[str, Any]) -> None:
    """Reviewer fail-closed: verdict is required and must be explicit."""
    if not isinstance(envelope, dict) or "verdict" not in envelope:
        raise GateDenied("Reviewer verdict is missing")
    if envelope.get("verdict") not in ("PASS", "REWORK", "BLOCKED"):
        raise GateDenied("Reviewer verdict is invalid")