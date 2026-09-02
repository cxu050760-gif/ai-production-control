#!/usr/bin/env python3
"""V0.9 speculative hardening of the existing Runtime Effect Safety Lite layer.

This is NOT a second Authority / Effect subsystem. It hardens the existing
Runtime Lite authority records and logical-effect log with the same invariants
already represented by ControlStore's authority journal, reservations, fences,
and effect WAL:

Prepare -> Write Intent -> Capture Preconditions -> Check Authority -> Execute
-> Observe -> Commit.

If Execute may have happened but the response is lost, the effect becomes
OUTCOME_UNKNOWN. Ordinary retry is forbidden until reality is reconciled. A
reconciled success is permanently deduplicated and never Executes twice.
"""
from __future__ import annotations

import importlib.util
import json
import string
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aicontrol.security import (  # noqa: E402
    authority_scope_allowed,
    egress_allowed,
    human_gate_allowed,
    normalized_classification,
    require_credential_isolation,
)
from aicontrol.util import canonical_json, sha256_text  # noqa: E402

EFFECT_SCHEMA_VERSION = 2
AUTHORIZED_ISSUER_ROLES = {"AUTHORITY", "HUMAN_AUTHORITY", "CONTROLLER_AUTHORITY"}
TERMINAL_SUCCESS = {"SUCCESS", "ACTION_COMMITTED"}
UNRESOLVED_EFFECT_STATES = {
    "INTENT_WRITTEN",
    "EXECUTE_STARTED",
    "OUTCOME_UNKNOWN",
    "RECONCILED_NOT_OCCURRED",
}


class EffectSafetyError(RuntimeError):
    pass


class EffectDenied(EffectSafetyError):
    pass


def _load_runtime():
    spec = importlib.util.spec_from_file_location("apc_runtime_core_i", HERE / "runtime.py")
    if spec is None or spec.loader is None:
        raise EffectSafetyError("runtime.py loader unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def effect_identity(run_id: str, slot: str, payload_hash: str) -> str:
    # Preserve the existing V0.8 logical identity. V0.9 hardening must not fork
    # previously recorded logical effects.
    core = {"task_id": run_id, "logical_effect_slot": slot, "payload_hash": payload_hash}
    return sha256_text(canonical_json(core))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _next_authority_generation(state: dict[str, Any]) -> int:
    generation = int(state.get("effect_authorization_generation", 0)) + 1
    state["effect_authorization_generation"] = generation
    return generation


def _current_revocation_epoch(state: dict[str, Any]) -> int:
    return int(state.get("effect_revocation_epoch", 0))


def grant_authorization(
    rt,
    state: dict,
    *,
    issuer_role: str | None = None,
    issuer_identity: str | None = None,
    holder: str = "runtime-v1",
    scope: dict | None = None,
    ttl_seconds: int = 3600,
    max_effect_count: int = 1,
) -> dict[str, Any]:
    """Provision authority from an identity distinct from the executor.

    The old Runtime Lite convenience path that silently self-granted authority
    is intentionally gone. Missing authority now fails closed.
    """
    role = str(issuer_role or "").strip().upper()
    issuer = str(issuer_identity or "").strip()
    holder = str(holder or "").strip()
    if role not in AUTHORIZED_ISSUER_ROLES:
        raise EffectDenied("authorization issuer is not an Authority role")
    if not issuer:
        raise EffectDenied("authorization issuer identity missing")
    if not holder:
        raise EffectDenied("authorization holder identity missing")
    if issuer == holder:
        raise EffectDenied("executor self-grant is forbidden")
    if max_effect_count < 1:
        raise EffectDenied("authorization effect count must be positive")

    scope = dict(scope or {})
    try:
        require_credential_isolation(scope)
    except Exception as exc:
        raise EffectDenied(str(exc)) from exc

    required_scope = {"provider", "resource", "purpose", "identity", "destination", "data_classes"}
    missing = sorted(required_scope - scope.keys())
    if missing:
        raise EffectDenied(f"authorization scope incomplete: {missing}")
    if str(scope.get("identity")) != holder:
        raise EffectDenied("authorization scope identity must equal execution holder")
    classes = scope.get("data_classes")
    if not isinstance(classes, list) or not classes:
        raise EffectDenied("authorization data_classes must be a non-empty list")
    for value in classes:
        try:
            normalized_classification(str(value))
        except Exception as exc:
            raise EffectDenied(str(exc)) from exc

    scope_digest = sha256_text(canonical_json(scope))
    generation = _next_authority_generation(state)
    revocation_epoch = _current_revocation_epoch(state)
    issued_at = _now_iso()
    authorization_id = sha256_text(
        canonical_json(
            {
                "run_id": state["run_id"],
                "holder": holder,
                "issuer_identity": issuer,
                "scope_digest": scope_digest,
                "generation": generation,
                "issued_at": issued_at,
            }
        )
    )
    record = {
        "authorization_id": authorization_id,
        "task_id": state["run_id"],
        "holder": holder,
        "identity": scope["identity"],
        "provider": scope["provider"],
        "resource": scope["resource"],
        "purpose": scope["purpose"],
        "destination": scope["destination"],
        "scope": scope,
        "scope_digest": scope_digest,
        "status": "GRANTED",
        "generation": generation,
        "revocation_epoch": revocation_epoch,
        "max_effect_count": int(max_effect_count),
        "consumed_effect_count": 0,
        "issuer_role": role,
        "issuer_identity": issuer,
        "issued_at": issued_at,
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds))
        .isoformat(timespec="seconds"),
    }
    auths = dict(state.get("effect_authorizations") or {})
    auths[authorization_id] = record
    state["effect_authorizations"] = auths
    rt.save_state(state)
    rt.journal(
        state["run_id"],
        "EFFECT_AUTHORIZATION_GRANTED",
        authorization_id=authorization_id,
        holder=holder,
        issuer_role=role,
        issuer_identity=issuer,
        generation=generation,
        revocation_epoch=revocation_epoch,
        max_effect_count=max_effect_count,
    )
    return record


def revoke_authorization(rt, state: dict, authorization_id: str) -> None:
    auths = state.get("effect_authorizations") or {}
    rec = auths.get(authorization_id)
    if not rec:
        raise EffectDenied("authorization missing")
    if rec.get("status") == "REVOKED":
        return
    state["effect_revocation_epoch"] = _current_revocation_epoch(state) + 1
    generation = _next_authority_generation(state)
    rec["status"] = "REVOKED"
    rec["revocation_epoch"] = state["effect_revocation_epoch"]
    rec["generation"] = generation
    rec["revoked_at"] = _now_iso()
    rt.save_state(state)
    rt.journal(
        state["run_id"],
        "EFFECT_AUTHORIZATION_REVOKED",
        authorization_id=authorization_id,
        generation=generation,
        revocation_epoch=state["effect_revocation_epoch"],
    )


def _is_live(rec: dict[str, Any]) -> bool:
    return rec.get("status") == "GRANTED" and not (
        rec.get("expires_at") and rec["expires_at"] < _now_iso()
    )


def _valid_authorization(
    state: dict,
    authorization_id: str | None,
    *,
    provider: str,
    resource: str,
    purpose: str,
    identity: str,
    destination: str,
    classification: str,
    require_capacity: bool = True,
) -> dict[str, Any]:
    auths = state.get("effect_authorizations") or {}
    if authorization_id:
        rec = auths.get(authorization_id)
        candidates = [rec] if isinstance(rec, dict) else []
    else:
        candidates = [rec for rec in auths.values() if isinstance(rec, dict) and _is_live(rec)]
    if not candidates:
        raise EffectDenied("no authorization bound to effect")

    current_generation = int(state.get("effect_authorization_generation", 0))
    current_epoch = _current_revocation_epoch(state)
    stale_reason = "authorization scope mismatch"
    for rec in candidates:
        if rec.get("status") != "GRANTED":
            stale_reason = "authorization revoked or not granted"
            continue
        if rec.get("expires_at") and rec["expires_at"] < _now_iso():
            stale_reason = "authorization expired"
            continue
        if int(rec.get("generation", -1)) != current_generation:
            stale_reason = "authorization generation stale"
            continue
        if int(rec.get("revocation_epoch", -1)) != current_epoch:
            stale_reason = "authorization revocation epoch stale"
            continue
        if str(rec.get("holder") or "") != identity:
            stale_reason = "authorization holder/identity mismatch"
            continue
        if not authority_scope_allowed(
            authorization=rec,
            task_id=state["run_id"],
            provider=provider,
            resource=resource,
            purpose=purpose,
            identity=identity,
            destination=destination,
            classification=classification,
        ):
            stale_reason = "authorization provider/resource/purpose/identity/egress scope mismatch"
            continue
        if require_capacity and int(rec.get("consumed_effect_count", 0)) >= int(rec.get("max_effect_count", 0)):
            stale_reason = "authorization effect count exhausted"
            continue
        return rec
    raise EffectDenied(stale_reason)


def ensure_valid_authorization(
    rt,
    state: dict,
    *,
    holder: str = "runtime-v1",
    scope: dict | None = None,
    authorization_id: str | None = None,
) -> dict[str, Any]:
    """Compatibility name; unlike V0.8 this function NEVER grants authority."""
    del rt
    scope = dict(scope or {})
    classes = scope.get("data_classes") if isinstance(scope.get("data_classes"), list) else ["INTERNAL"]
    classification = str(classes[0] if classes else "INTERNAL")
    return _valid_authorization(
        state,
        authorization_id,
        provider=str(scope.get("provider") or ""),
        resource=str(scope.get("resource") or ""),
        purpose=str(scope.get("purpose") or ""),
        identity=str(scope.get("identity") or holder),
        destination=str(scope.get("destination") or ""),
        classification=classification,
        require_capacity=True,
    )


def _effect_log(state: dict[str, Any]) -> list[dict[str, Any]]:
    log = state.get("effect_safety_log")
    if not isinstance(log, list):
        log = []
        state["effect_safety_log"] = log
    return log


def _find_effect(state: dict[str, Any], logical_effect_id: str) -> dict[str, Any]:
    for rec in reversed(_effect_log(state)):
        if rec.get("logical_effect_id") == logical_effect_id:
            return rec
    raise EffectDenied("logical effect intent missing")


def _execution_fence(record: dict[str, Any]) -> str:
    material = {
        "run_id": record["task_id"],
        "logical_effect_id": record["logical_effect_id"],
        "authorization_id": record["authorization_id"],
        "authorization_generation": record["authorization_generation"],
        "authorization_scope_digest": record["authorization_scope_digest"],
        "revocation_epoch": record["revocation_epoch"],
        "state_revision": record["state_revision"],
        "provider": record["provider"],
        "resource": record["resource"],
        "purpose": record["purpose"],
        "identity": record["identity"],
    }
    return sha256_text(canonical_json(material))


def prepare_effect(
    rt,
    state: dict,
    *,
    operation: str,
    destination: str,
    provider: str,
    resource: str,
    identity: str,
    payload_hash: str,
    slot: str,
    purpose: str,
    authorization_id: str | None = None,
    classification: str = "INTERNAL",
    capability_permitted: bool = True,
    egress_permitted: bool = True,
    resource_fresh: bool = True,
    tcb_verified: bool = False,
    human_gate_required: bool = False,
    human_gate_reference: str | None = None,
) -> dict[str, Any]:
    """Prepare, capture preconditions, and durably Write Intent before Execute."""
    if len(payload_hash or "") != 64 or any(ch not in string.hexdigits for ch in payload_hash):
        raise EffectDenied("payload_hash missing or invalid")
    try:
        classification = normalized_classification(classification)
    except Exception as exc:
        raise EffectDenied(str(exc)) from exc
    if classification == "SECRET":
        raise EffectDenied("SECRET data egress denied")
    if not capability_permitted:
        raise EffectDenied("capability precondition denied")
    if not egress_permitted:
        raise EffectDenied("data egress denied")
    if not resource_fresh:
        raise EffectDenied("resource precondition stale")
    if not tcb_verified:
        raise EffectDenied("Controller TCB is not VERIFIED for external effect")
    if not human_gate_allowed(required=human_gate_required, reference=human_gate_reference):
        raise EffectDenied("required Human Gate authorization missing")

    logical_effect_id = effect_identity(state["run_id"], slot, payload_hash.lower())
    for prior in reversed(_effect_log(state)):
        if prior.get("logical_effect_id") != logical_effect_id:
            continue
        status = str(prior.get("status") or "")
        if status in TERMINAL_SUCCESS:
            prior["deduplicated"] = True
            state["effect_safety"] = prior
            return prior
        if status == "RECONCILED_NOT_OCCURRED":
            # P0-0(2026-09-02 双复核 PASS): 已人工确认"未发生"(evidence 落库)。
            # 负向确认消除了"可能已发出"的不确定性, 允许以新授权重试同 payload
            # (重放仍需下方 _valid_authorization 显式授权); 防重复投递锁
            # (OUTCOME_UNKNOWN)语义不变。break 而非 continue: 同 id 在 effect log
            # 至多一条, 已处理当前记录无需再溯更旧记录。
            break
        if status == "OUTCOME_UNKNOWN":
            raise EffectDenied("OUTCOME_UNKNOWN requires reconciliation; ordinary retry denied")
        if status in UNRESOLVED_EFFECT_STATES:
            raise EffectDenied(f"existing logical effect is unresolved: {status}")
        raise EffectDenied(f"existing logical effect cannot be ordinarily retried: {status or 'UNKNOWN'}")

    auth = _valid_authorization(
        state,
        authorization_id,
        provider=provider,
        resource=resource,
        purpose=purpose,
        identity=identity,
        destination=destination,
        classification=classification,
        require_capacity=True,
    )
    consumed = int(auth.get("consumed_effect_count", 0)) + 1
    if consumed > int(auth.get("max_effect_count", 0)):
        raise EffectDenied("authorization effect count exhausted")
    auth["consumed_effect_count"] = consumed

    current_revision = int(state.get("revision", 0))
    durable_revision = current_revision + 1
    record = {
        "schema_version": EFFECT_SCHEMA_VERSION,
        "task_id": state["run_id"],
        "logical_effect_id": logical_effect_id,
        "logical_effect_slot": slot,
        "operation": operation,
        "destination": destination,
        "provider": provider,
        "resource": resource,
        "identity": identity,
        "payload_hash": payload_hash.lower(),
        "purpose": purpose,
        "classification": classification,
        "authorization_id": auth["authorization_id"],
        "authorization_holder": auth["holder"],
        "authorization_status": auth["status"],
        "authorization_scope_digest": auth["scope_digest"],
        "authorization_generation": int(auth["generation"]),
        "revocation_epoch": int(auth["revocation_epoch"]),
        "precondition_revision": current_revision,
        "state_revision": durable_revision,
        "preconditions": {
            "capability_permitted": True,
            "egress_permitted": True,
            "resource_fresh": True,
            "tcb_verified": True,
            "human_gate_required": bool(human_gate_required),
            "human_gate_reference": human_gate_reference,
        },
        "ordinary_retry_permitted": False,
        "deduplicated": False,
        "status": "INTENT_WRITTEN",
        "prepared_at": _now_iso(),
    }
    record["execution_fence_token"] = _execution_fence(record)
    _effect_log(state).append(record)
    state["effect_safety"] = record
    rt.save_state(state)
    if int(state.get("revision", -1)) != durable_revision:
        raise EffectDenied("durable state revision did not match prepared effect fence")
    rt.journal(
        state["run_id"],
        "EFFECT_WRITE_AHEAD_INTENT",
        logical_effect_id=logical_effect_id,
        slot=slot,
        authorization_id=auth["authorization_id"],
        authorization_generation=record["authorization_generation"],
        revocation_epoch=record["revocation_epoch"],
        state_revision=record["state_revision"],
        execution_fence_token=record["execution_fence_token"],
        operation=operation,
    )
    return record


def begin_effect(
    rt,
    state: dict,
    logical_effect_id: str,
    *,
    execution_fence_token: str,
    capability_permitted: bool = True,
    egress_permitted: bool = True,
    resource_fresh: bool = True,
    tcb_verified: bool = True,
    human_gate_reference: str | None = None,
) -> dict[str, Any]:
    """Last fail-closed fence immediately before crossing the external boundary."""
    record = _find_effect(state, logical_effect_id)
    if record.get("status") != "INTENT_WRITTEN":
        raise EffectDenied(f"effect is not executable from {record.get('status')}")
    if execution_fence_token != record.get("execution_fence_token"):
        raise EffectDenied("stale or wrong execution fence token")
    if int(state.get("revision", -1)) != int(record.get("state_revision", -2)):
        raise EffectDenied("stale Canonical State revision before Execute")
    if int(state.get("effect_authorization_generation", 0)) != int(record.get("authorization_generation", -1)):
        raise EffectDenied("stale authorization generation before Execute")
    if _current_revocation_epoch(state) != int(record.get("revocation_epoch", -1)):
        raise EffectDenied("stale revocation fence before Execute")
    if not capability_permitted:
        raise EffectDenied("capability revoked before Execute")
    if not egress_permitted:
        raise EffectDenied("data egress denied before Execute")
    if not resource_fresh:
        raise EffectDenied("resource became stale before Execute")
    if not tcb_verified:
        raise EffectDenied("Controller TCB failed before Execute")
    gate_ref = human_gate_reference if human_gate_reference is not None else record.get("human_gate_reference")
    if gate_ref is None:
        gate_ref = (record.get("preconditions") or {}).get("human_gate_reference")
    if not human_gate_allowed(required=bool((record.get("preconditions") or {}).get("human_gate_required")), reference=gate_ref):
        raise EffectDenied("required Human Gate missing before Execute")

    # Quota is consumed at Prepare/reservation time. Execute must revalidate
    # identity/generation/revocation/scope, but must not reject the already
    # reserved final quota merely because consumed == max.
    auth = _valid_authorization(
        state,
        record.get("authorization_id"),
        provider=str(record["provider"]),
        resource=str(record["resource"]),
        purpose=str(record["purpose"]),
        identity=str(record["identity"]),
        destination=str(record["destination"]),
        classification=str(record["classification"]),
        require_capacity=False,
    )
    if int(auth.get("generation", -1)) != int(record["authorization_generation"]):
        raise EffectDenied("authorization changed after Write Intent")
    if int(auth.get("revocation_epoch", -1)) != int(record["revocation_epoch"]):
        raise EffectDenied("authorization revoked after Write Intent")
    if int(auth.get("consumed_effect_count", 0)) < 1 or int(auth.get("consumed_effect_count", 0)) > int(auth.get("max_effect_count", 0)):
        raise EffectDenied("authorization reservation accounting invalid before Execute")

    record["status"] = "EXECUTE_STARTED"
    record["execute_started_at"] = _now_iso()
    state["effect_safety"] = record
    rt.save_state(state)
    rt.journal(
        state["run_id"],
        "EFFECT_EXECUTE_STARTED",
        logical_effect_id=logical_effect_id,
        execution_fence_token=record["execution_fence_token"],
        authorization_generation=record["authorization_generation"],
        revocation_epoch=record["revocation_epoch"],
    )
    return record


def commit_effect_success(
    rt,
    state: dict,
    logical_effect_id: str,
    *,
    observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = _find_effect(state, logical_effect_id)
    if record.get("status") != "EXECUTE_STARTED":
        raise EffectDenied("effect success cannot be committed from current state")
    record["status"] = "SUCCESS"
    record["observation"] = dict(observation or {})
    record["committed_at"] = _now_iso()
    record["ordinary_retry_permitted"] = False
    state["effect_safety"] = record
    rt.save_state(state)
    rt.journal(state["run_id"], "EFFECT_COMMITTED_SUCCESS", logical_effect_id=logical_effect_id)
    return record


def mark_outcome_unknown(
    rt,
    state: dict,
    logical_effect_id: str,
    *,
    observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = _find_effect(state, logical_effect_id)
    if record.get("status") != "EXECUTE_STARTED":
        raise EffectDenied("OUTCOME_UNKNOWN is valid only after Execute started")
    record["status"] = "OUTCOME_UNKNOWN"
    record["observation"] = dict(observation or {})
    record["outcome_unknown_at"] = _now_iso()
    record["ordinary_retry_permitted"] = False
    state["effect_safety"] = record
    rt.save_state(state)
    rt.journal(
        state["run_id"],
        "EFFECT_OUTCOME_UNKNOWN",
        logical_effect_id=logical_effect_id,
        ordinary_retry_permitted=False,
    )
    return record


def reconcile_effect(
    rt,
    state: dict,
    logical_effect_id: str,
    *,
    observed_succeeded: bool,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    record = _find_effect(state, logical_effect_id)
    if record.get("status") != "OUTCOME_UNKNOWN":
        raise EffectDenied("reconciliation requires OUTCOME_UNKNOWN")
    if not isinstance(evidence, dict) or not evidence:
        raise EffectDenied("reconciliation evidence missing")
    record["reconciliation_evidence"] = dict(evidence)
    record["reconciled_at"] = _now_iso()
    record["ordinary_retry_permitted"] = False
    if observed_succeeded:
        record["status"] = "SUCCESS"
        event = "EFFECT_RECONCILED_SUCCESS"
    else:
        # Negative inspection is not itself replay authority, but (2026-09-02,
        # dual-review PASS) it must not permanently block an ordinary resend of
        # the same payload: evidence confirms the effect never occurred, so the
        # uncertainty that justifies the anti-duplication lock is gone. Replay
        # still requires a NEW explicit authorization via prepare_effect.
        record["status"] = "RECONCILED_NOT_OCCURRED"
        event = "EFFECT_RECONCILED_NOT_OCCURRED"
    state["effect_safety"] = record
    rt.save_state(state)
    rt.journal(
        state["run_id"],
        event,
        logical_effect_id=logical_effect_id,
        ordinary_retry_permitted=False,
    )
    return record


def record_effect(
    rt,
    state: dict,
    *,
    operation: str,
    destination: str,
    payload_hash: str,
    slot: str,
    purpose: str,
    authorization_id: str | None = None,
    capability_permitted: bool = True,
    egress_permitted: bool = True,
    resource_fresh: bool = True,
) -> dict[str, Any]:
    """Compatibility facade for old reservation-only callers; never self-grants."""
    auths = state.get("effect_authorizations") or {}
    if authorization_id:
        auth = auths.get(authorization_id)
    else:
        live = [rec for rec in auths.values() if isinstance(rec, dict) and _is_live(rec)]
        auth = live[0] if len(live) == 1 else None
    if not isinstance(auth, dict):
        raise EffectDenied("record_effect requires one explicit live authorization")
    scope = auth.get("scope") if isinstance(auth.get("scope"), dict) else {}
    classes = scope.get("data_classes") if isinstance(scope.get("data_classes"), list) else ["INTERNAL"]
    return prepare_effect(
        rt,
        state,
        operation=operation,
        destination=destination,
        provider=str(auth.get("provider") or scope.get("provider") or ""),
        resource=str(auth.get("resource") or scope.get("resource") or destination),
        identity=str(auth.get("identity") or scope.get("identity") or auth.get("holder") or ""),
        payload_hash=payload_hash,
        slot=slot,
        purpose=purpose,
        authorization_id=auth.get("authorization_id"),
        classification=str(classes[0] if classes else "INTERNAL"),
        capability_permitted=capability_permitted,
        egress_permitted=egress_permitted,
        resource_fresh=resource_fresh,
        tcb_verified=True,
    )


def _runtime_egress_permitted(
    state: dict[str, Any],
    *,
    destination: str,
    provider: str,
    purpose: str,
    classification: str,
) -> bool:
    """T11b: open the egress gate only from the Goal Contract's own permission.

    The decision is made entirely by the canonical ``security.egress_allowed``
    predicate (anchored by matrix R27-R29); this function only supplies its
    inputs. Every missing or inconsistent input denies, so a pre-T11b state file
    loads and stays blocked instead of crashing or defaulting open. Passing no
    authorization scope keeps SECRET, UNKNOWN, PRIVATE_LOCAL and SENSITIVE denied.
    """
    projection = state.get("egress_policy_projection")
    if not isinstance(projection, dict):
        return False
    stored_hash = str(state.get("goal_contract_hash") or "")
    if not stored_hash or str(projection.get("source_contract_hash") or "") != stored_hash:
        return False
    policy = projection.get("data_egress_policy")
    if not isinstance(policy, dict) or not policy:
        return False
    if not (destination and provider and purpose):
        return False
    return egress_allowed(
        classification=classification,
        destination=destination,
        provider=provider,
        purpose=purpose,
        goal_contract={"data_egress_policy": policy},
        authorization_scope=None,
    )


def _runtime_preconditions(
    state: dict[str, Any],
    *,
    destination: str = "",
    provider: str = "",
    purpose: str = "",
) -> dict[str, Any]:
    tcb_verified = bool(
        state.get("effect_tcb_verified") is True
        or state.get("tcb_status") == "VERIFIED"
        or state.get("controller_tcb_status") == "VERIFIED"
    )
    classification = str(state.get("effect_data_classification") or "INTERNAL")
    return {
        "capability_permitted": bool(state.get("effect_capability_permitted", True)),
        "egress_permitted": _runtime_egress_permitted(
            state, destination=destination, provider=provider,
            purpose=purpose, classification=classification),
        "resource_fresh": bool(state.get("effect_resource_fresh", True)),
        "tcb_verified": tcb_verified,
        "human_gate_required": bool(state.get("effect_human_gate_required", False)),
        "human_gate_reference": state.get("effect_human_gate_reference"),
        "classification": classification,
    }


def _prepare_runtime_send(
    rt,
    state: dict[str, Any],
    *,
    operation: str,
    destination: str,
    payload_hash: str,
    slot: str,
    purpose: str,
) -> dict[str, Any]:
    provider = str(state.get("effect_provider") or "chatgpt-web")
    identity = str(state.get("effect_executor_identity") or "runtime-v1")
    resource = str(state.get("effect_resource") or destination)
    checks = _runtime_preconditions(
        state, destination=destination, provider=provider, purpose=purpose)
    return prepare_effect(
        rt,
        state,
        operation=operation,
        destination=destination,
        provider=provider,
        resource=resource,
        identity=identity,
        payload_hash=payload_hash,
        slot=slot,
        purpose=purpose,
        classification=checks["classification"],
        capability_permitted=checks["capability_permitted"],
        egress_permitted=checks["egress_permitted"],
        resource_fresh=checks["resource_fresh"],
        tcb_verified=checks["tcb_verified"],
        human_gate_required=checks["human_gate_required"],
        human_gate_reference=checks["human_gate_reference"],
    )


def _begin_runtime_send(rt, state: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    checks = _runtime_preconditions(
        state,
        destination=str(record.get("destination") or ""),
        provider=str(record.get("provider") or ""),
        purpose=str(record.get("purpose") or ""),
    )
    return begin_effect(
        rt,
        state,
        record["logical_effect_id"],
        execution_fence_token=record["execution_fence_token"],
        capability_permitted=checks["capability_permitted"],
        egress_permitted=checks["egress_permitted"],
        resource_fresh=checks["resource_fresh"],
        tcb_verified=checks["tcb_verified"],
        human_gate_reference=checks["human_gate_reference"],
    )


def install(rt, options: dict) -> None:
    del options
    original_cmd_send = rt.cmd_send

    def gated_cmd_send(args):
        state = rt.load_state(args.run_id)
        message = str(getattr(args, "message", "") or "")
        message_file = str(getattr(args, "message_file", "") or "")
        files = sorted(getattr(args, "file", None) or [])
        payload = message + message_file + json.dumps(files, ensure_ascii=False)
        payload_hash = sha256_text(payload)
        destination = str(state.get("r_url") or "")
        record = None
        try:
            # P0-0(2026-09-02 双复核 PASS): 桥健康预检前置到 effect WAL 之前。
            # "执行前失败"(桥不可用/浏览器未就绪)不写 INTENT/不 begin/不落
            # OUTCOME_UNKNOWN 锁——弱 AI 在桥自愈后可按预算重试同一条命令,
            # 避免"第一次桥抖动即锁死、必须人工"的自动化断裂。仅 RUNNING 态预检。
            if state.get("status") == "RUNNING":
                _pre_health = rt.ensure_bridge_ready(force=True)
                if not _pre_health.get("ready"):
                    _mm = state.setdefault("metrics", {})
                    _mm["bridge_retries"] = int(_mm.get("bridge_retries", 0)) + 1
                    rt.save_state(state)
                    _detail = str(_pre_health.get("detail", ""))
                    if _mm["bridge_retries"] > getattr(rt, "MAX_BRIDGE_RETRIES", 3):
                        rt.hard_block(state, "bridge health failed beyond retry budget: " + _detail)
                        rt.emit({"status": "HARD_BLOCKED",
                                 "reason": str(state.get("blocked_reason") or _detail)})
                        return rt.EXIT_HARD_BLOCKED
                    rt.journal(state["run_id"], "BRIDGE_UNHEALTHY",
                               detail=_detail, bridge_retries=_mm["bridge_retries"])
                    rt.emit({"status": "BRIDGE_UNHEALTHY", "detail": _detail,
                             "bridge_retries": _mm["bridge_retries"],
                             "instruction": "Bridge unhealthy. Retry the same command later "
                                            "(budget limited); do not open the bridge internals."})
                    return rt.EXIT_ERR
            # P0-1(2026-09-02 双复核 PASS): 审查者就位校验与桥健康预检同级——
            # 必须位于 _prepare_runtime_send 之前,否则握手失败会被 effect gate
            # 记成 OUTCOME_UNKNOWN,把"审查者未就位→可重试"变成死锁(违背用户
            # "不新增锁/不要动不动就停"诉求)。未就位直接 return,不写 INTENT/
            # 不 begin/不落 OU 锁;弱 AI 在用户修好审查者后可重试同一条 send。
            if state.get("status") == "RUNNING":
                _hs = getattr(rt, "_ensure_reviewer_ready", None)
                if _hs is not None:
                    _hs_code = _hs(state, rt.run_dir(args.run_id),
                                   (state.get("session") or {}).get("sid") or "")
                    if _hs_code != rt.EXIT_OK:
                        return _hs_code
            record = _prepare_runtime_send(
                rt,
                state,
                operation="send",
                destination=destination,
                payload_hash=payload_hash,
                slot=f"send:{state.get('review_epoch', 1)}",
                purpose="review transport",
            )
            if record.get("deduplicated") and record.get("status") in TERMINAL_SUCCESS:
                rt.journal(
                    state["run_id"],
                    "EFFECT_DEDUP_SUPPRESSED",
                    logical_effect_id=record["logical_effect_id"],
                    operation="send",
                )
                return rt.EXIT_OK
            _begin_runtime_send(rt, state, record)
        except EffectDenied as exc:
            rt.hard_block(state, f"EFFECT_SAFETY_DENIED: {exc}")
            rt.emit({"status": "HARD_BLOCKED", "reason": f"EFFECT_SAFETY_DENIED: {exc}"})
            return rt.EXIT_HARD_BLOCKED
        except Exception as exc:  # noqa: BLE001
            rt.hard_block(state, f"EFFECT_SAFETY_ERROR: {type(exc).__name__}: {exc}")
            rt.emit({"status": "HARD_BLOCKED", "reason": f"EFFECT_SAFETY_ERROR: {exc}"})
            return rt.EXIT_HARD_BLOCKED

        try:
            code = original_cmd_send(args)
        except Exception as exc:  # noqa: BLE001
            current = rt.load_state(args.run_id)
            try:
                mark_outcome_unknown(
                    rt,
                    current,
                    record["logical_effect_id"],
                    observation={"transport": "exception_after_execute", "error_type": type(exc).__name__},
                )
            finally:
                rt.hard_block(current, f"EFFECT_OUTCOME_UNKNOWN: {type(exc).__name__}")
            rt.emit({"status": "HARD_BLOCKED", "reason": "EFFECT_OUTCOME_UNKNOWN: reconcile reality before any retry"})
            return rt.EXIT_HARD_BLOCKED

        current = rt.load_state(args.run_id)
        if code == rt.EXIT_OK:
            commit_effect_success(
                rt,
                current,
                record["logical_effect_id"],
                observation={"transport_exit_code": code},
            )
        else:
            try:
                mark_outcome_unknown(
                    rt,
                    current,
                    record["logical_effect_id"],
                    observation={"transport_exit_code": code},
                )
            except EffectDenied:
                pass
        return code

    rt.cmd_send = gated_cmd_send

    original_router_send = getattr(rt, "_router_send_to_role", None)
    if original_router_send is not None:
        def gated_router_send(state, role, message, timeout):
            payload_hash = sha256_text(message)
            destination = str((state.get("role_urls") or {}).get(role) or state.get("r_url") or "")
            record = _prepare_runtime_send(
                rt,
                state,
                operation="router-send",
                destination=destination,
                payload_hash=payload_hash,
                slot=f"router:{role}:{state.get('router', {}).get('round', 0)}",
                purpose="router transport",
            )
            if record.get("deduplicated") and record.get("status") in TERMINAL_SUCCESS:
                raise EffectDenied("deduplicated router effect already succeeded; second Execute denied")
            _begin_runtime_send(rt, state, record)
            try:
                result = original_router_send(state, role, message, timeout)
            except Exception as exc:
                mark_outcome_unknown(
                    rt,
                    state,
                    record["logical_effect_id"],
                    observation={"transport": "router_exception_after_execute", "error_type": type(exc).__name__},
                )
                raise
            commit_effect_success(
                rt,
                state,
                record["logical_effect_id"],
                observation={"transport": "router_reply_observed"},
            )
            return result

        rt._router_send_to_role = gated_router_send


def cmd_effect_reconcile(rt, argv: list) -> int:
    """GATE-1#5 (hardening 2026-08-31): CLI reconciliation exit for
    EFFECT_OUTCOME_UNKNOWN. reconcile_effect previously had no caller, so one
    transient transport failure permanently self-locked a RUN (dedupe refuses
    ordinary retry while OUTCOME_UNKNOWN is unresolved, and nothing could ever
    resolve it).

    Fail-closed semantics preserved:
    - --succeeded: operator-verified evidence that the effect really happened
      -> commit SUCCESS (permanently deduplicated; a duplicate send returns
      the dedup record instead of re-executing) and resume the RUN lifecycle
      so the normal flow (report -> verdict -> done) can continue.
    - --not-occurred: record the negative inspection, keep the RUN
      hard-blocked; any later replay still needs a new explicit authority
      decision (frozen V0.9 rule, unchanged).
    """
    import argparse as _argparse
    p = _argparse.ArgumentParser(prog="effect-reconcile")
    p.add_argument("--run-id", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--succeeded", action="store_true")
    g.add_argument("--not-occurred", action="store_true")
    p.add_argument("--evidence-file", required=True,
                   help="JSON object with observation evidence for the reconciliation")
    args = p.parse_args(argv)
    # P2-2 (internal review): all other state-mutating commands hold the
    # per-RUN RunLock; without it two concurrent reconciles could both pass
    # the OUTCOME_UNKNOWN pre-check and double-commit/double-resume, and a
    # racing directive/report could lose updates via the prev-rotation.
    lock = rt.RunLock(args.run_id)
    with lock:
        state = rt.load_state(args.run_id)
        record = state.get("effect_safety") or {}
        if record.get("status") != "OUTCOME_UNKNOWN":
            rt.emit({"status": "DENIED",
                     "reason": ("reconciliation requires OUTCOME_UNKNOWN; "
                                f"current={record.get('status')!r}"),
                     "run_id": args.run_id})
            return rt.EXIT_DENIED
        try:
            evidence = json.loads(Path(args.evidence_file).read_text(encoding="utf-8") or "{}")
        except Exception as exc:  # noqa: BLE001
            rt.emit({"status": "DENIED", "reason": f"evidence file unreadable: {exc}",
                     "run_id": args.run_id})
            return rt.EXIT_DENIED
        try:
            record = reconcile_effect(rt, state, str(record.get("logical_effect_id") or ""),
                                      observed_succeeded=bool(args.succeeded), evidence=evidence)
        except EffectDenied as exc:
            rt.emit({"status": "DENIED", "reason": str(exc), "run_id": args.run_id})
            return rt.EXIT_DENIED
        if args.succeeded and state.get("status") == "HARD_BLOCKED":
            # Effect confirmed delivered: resume the lifecycle (auditable), so the
            # normal flow can continue. NOT applied for --not-occurred (fail-closed:
            # replay needs a new explicit authority decision).
            state["status"] = "RUNNING"
            state["blocked_reason"] = ""
            state["next_action"] = "reconciled: effect confirmed delivered; continue the normal flow"
            rt.save_state(state)
            rt.journal(state["run_id"], "EFFECT_RECONCILE_RESUME",
                       logical_effect_id=record.get("logical_effect_id"))
    rt.emit({"status": "OK", "run_id": state.get("run_id"),
             "effect_status": record.get("status"),
             "run_status": state.get("status")})
    return rt.EXIT_OK


def main(argv: list | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    rt = _load_runtime()
    if argv and argv[0] == "effect-reconcile":
        return cmd_effect_reconcile(rt, argv[1:])
    install(rt, {})
    sys.argv = [str(HERE / "runtime.py"), *argv]
    return rt.main()


if __name__ == "__main__":
    sys.exit(main())
