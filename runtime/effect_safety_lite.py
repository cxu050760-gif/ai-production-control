#!/usr/bin/env python3
"""V0.9 speculative hardening of the existing Runtime Effect Safety Lite layer.

This is deliberately NOT a second Authority / Effect subsystem. It hardens the
existing Runtime Lite authority records and logical-effect log so they preserve
the same core invariants already present in ``src/aicontrol/store.py``:

Prepare -> durable write-ahead intent -> authority/fence recheck -> Execute ->
Observe -> Commit. If Execute may have happened but the response is lost, the
logical effect becomes OUTCOME_UNKNOWN. Ordinary retry is then forbidden until
reality is reconciled, and a reconciled success can never cross the external
boundary a second time.

Executor self-grant is forbidden. Authorization must be provisioned by an
explicit Authority identity before an external effect is prepared.
"""
from __future__ import annotations

import importlib.util
import json
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
    human_gate_allowed,
    normalized_classification,
    require_credential_isolation,
)
from aicontrol.util import canonical_json, sha256_text  # noqa: E402

EFFECT_SCHEMA_VERSION = 2
AUTHORIZED_ISSUER_ROLES = {"AUTHORITY", "HUMAN_AUTHORITY", "CONTROLLER_AUTHORITY"}
TERMINAL_SUCCESS = {"SUCCESS", "ACTION_COMMITTED"}
UNRESOLVED_EFFECT_STATES = {"INTENT_WRITTEN", "EXECUTE_STARTED", "OUTCOME_UNKNOWN", "RECONCILED_NOT_OCCURRED"}


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
    # Preserve the existing logical-effect identity so V0.9 hardening does not
    # fork or invalidate already-written Lite records.
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
    """Provision a durable authorization from a distinct Authority identity.

    The executor cannot use this function as a convenience fallback: callers
    must state an Authority role, and the issuer identity must differ from the
    execution holder. Raw credentials are rejected; only references belong in
    authorization scope.
    """
    role = str(issuer_role or "").strip().upper()
    issuer = str(issuer_identity or "").strip()
    if role not in AUTHORIZED_ISSUER_ROLES:
        raise EffectDenied("authorization issuer is not an Authority role")
    if not issuer:
        raise EffectDenied("authorization issuer identity missing")
    if issuer == holder:
        raise EffectDenied("executor self-grant is forbidden")
    if max_effect_count < 1:
        raise EffectDenied("authorization effect count must be positive")
    scope = dict(scope or {})
    try:
        require_credential_isolation(scope)
    except Exception as exc:  # GateDenied derives from RuntimeError outside this Lite API.
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
        "identity": scope.get("identity", holder),
        "provider": scope.get("provider"),
        "resource": scope.get("resource"),
        "purpose": scope.get("purpose"),
        "destination": scope.get("destination"),
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
) -> dict[str, Any]:
    auths = state.get("effect_authorizations") or {}
    candidates: list[dict[str, Any]]
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
        if int(rec.get("consumed_effect_count", 0)) >= int(rec.get("max_effect_count", 0)):
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
    """Compatibility name with V0.8 behavior removed: this never grants.

    Callers must pre-provision authority. Missing or stale authority fails closed.
    """
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
    """Prepare and durably write the effect intent before Execute."""
    if not payload_hash or len(payload_hash) != 64:
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

    logical_effect_id = effect_identity(state["run_id"], slot, payload_hash)
    for prior in reversed(_effect_log(state)):
        if prior.get("logical_effect_id") != logical_effect_id:
            continue
        status = str(prior.get("status") or "")
        if status in TERMINAL_SUCCESS:
            prior["deduplicated"] = True
            state["effect_safety"] = prior
            return prior
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
    )
    consumed = int(auth.get("consumed_effect_count", 0)) + 1
    if consumed > int(auth.get("max_effect_count", 0)):
        raise EffectDenied("authorization effect count exhausted")
    auth["consumed_effect_count"] = consumed

    # FakeRuntime and the official runtime both increment revision exactly once
    # inside save_state(), so this is the revision the durable intent will own.
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
        "payload_hash": payload_hash,
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
        "human_gate_required": bool(human_gate_required),
        "human_gate_reference": human_gate_reference,
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
    """Final fence immediately before crossing the external boundary."""
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
    if not human_gate_allowed(required=bool(record.get("human_gate_required")), reference=gate_ref):
        raise EffectDenied("required Human Gate missing before Execute")

    # Reuse the same Authority Matrix at the last possible safe point.
    auth = _valid_authorization(
        state,
        record.get("authorization_id"),
        provider=str(record["provider"]),
        resource=str(record["resource"]),
        purpose=str(record["purpose"]),
        identity=str(record["identity"]),
        destination=str(record["destination"]),
        classification=str(record["classification"]),
    )
    if int(auth.get("generation", -1)) != int(record["authorization_generation"]):
        raise EffectDenied("authorization changed after Write Intent")
    if int(auth.get("revocation_epoch", -1)) != int(record["revocation_epoch"]):
        raise EffectDenied("authorization revoked after Write Intent")

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


def commit_effect_success(rt, state: dict, logical_effect_id: str, *, observation: dict[str, Any] | None = None) -> dict[str, Any]:
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
        # A negative inspection does not itself authorize replay. A new explicit
        # authority decision / policy can be added in a later version; V0.9 is
        # intentionally fail-closed.
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
    """Compatibility facade for callers that only used reservation semantics.

    V0.9 callers should use prepare_effect/begin_effect explicitly. This facade
    still refuses missing authorization and never self-grants.
    """
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


def _runtime_preconditions(state: dict[str, Any]) -> dict[str, Any]:
    tcb_verified = bool(
        state.get("effect_tcb_verified") is True
        or state.get("tcb_status") == "VERIFIED"
        or state.get("controller_tcb_status") == "VERIFIED"
    )
    return {
        "capability_permitted": bool(state.get("effect_capability_permitted", True)),
        "egress_permitted": bool(state.get("effect_egress_permitted", False)),
        "resource_fresh": bool(state.get("effect_resource_fresh", True)),
        "tcb_verified": tcb_verified,
        "human_gate_required": bool(state.get("effect_human_gate_required", False)),
        "human_gate_reference": state.get("effect_human_gate_reference"),
        "classification": str(state.get("effect_data_classification") or "INTERNAL"),
    }


def _prepare_runtime_send(rt, state: dict[str, Any], *, operation: str, destination: str, payload_hash: str, slot: str, purpose: str) -> dict[str, Any]:
    provider = str(state.get("effect_provider") or "chatgpt-web")
    identity = str(state.get("effect_executor_identity") or "runtime-v1")
    resource = str(state.get("effect_resource") or destination)
    checks = _runtime_preconditions(state)
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
    checks = _runtime_preconditions(state)
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
                # The underlying Runtime may already have transitioned itself to
                # a terminal failure state, but ordinary replay remains denied by
                # the durable logical-effect record.
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


def main(argv: list | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    rt = _load_runtime()
    install(rt, {})
    sys.argv = [str(HERE / "runtime.py"), *argv]
    return rt.main()


if __name__ == "__main__":
    sys.exit(main())
