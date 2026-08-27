"""V0.7 core integration wiring for Strategic Brain -> C -> Strategic Reuse.

This module is intentionally thin and pure. It composes the three already
accepted V0.7 contracts without changing them and without importing Runtime
state/transport/controller internals.

The integration is fail-closed:
- an invalid or malformed Strategic Brain result stops the chain;
- any invalid or malformed C result stops the chain;
- any non-``none`` C correction stops before Strategic Reuse (C remains
  advisory-only; this layer never applies a correction or mutates authority);
- an invalid or malformed Strategic Reuse result stops the chain;
- a Strategic Reuse ``reject`` remains an advisory rejection.

No result from this module grants PASS, promotion, milestone crown, Controller
mutation authority, or external-effect authority.
"""
from __future__ import annotations

import json
from typing import Any, Dict

try:  # Existing runtime tests import modules directly from runtime/.
    import strategic_brain_contract as brain_contract
    import strategic_correction as correction_contract
    import strategic_reuse_contract as reuse_contract
except ModuleNotFoundError:  # Also support project-root namespace imports.
    from runtime import strategic_brain_contract as brain_contract
    from runtime import strategic_correction as correction_contract
    from runtime import strategic_reuse_contract as reuse_contract

# Preserve the public seams used by the existing B2 boundary-injection tests.
build_proposal = brain_contract.build_proposal
evaluate_correction = correction_contract.evaluate
evaluate_reuse = reuse_contract.evaluate

SCHEMA = "v0.7-strategic-integration-advisory"
MAX_SERIALIZED_INPUT = 65536
MAX_OUTPUT_TEXT = 1024

_BRAIN_KEYS = {"schema", "proposal_id", "goal", "plan", "non_authority", "origin"}
_BRAIN_PLAN_KEYS = {"step", "action", "detail"}
_BRAIN_HEX = frozenset("0123456789abcdef")
_BRAIN_PLAN_DETAIL_MAX = max(len("ensure_presence:"), len("ensure_absence:")) + brain_contract.MAX_VALUE

_CORRECTION_KEYS = {
    "schema", "corrections", "advisory_only", "non_authority",
    "mutated_external_state", "detection_note",
}
_CORRECTION_ITEM_KEYS = {"kind", "severity", "detail"}
_CORRECTION_KINDS = frozenset({
    "none", "scope_drift", "premature_milestone",
    "builder_role_self_review", "promotion_assumption",
})
_CORRECTION_ACTIVE_KINDS = _CORRECTION_KINDS - {"none"}

_REUSE_KEYS = {
    "schema", "decision", "decision_detail", "reasons", "advisory_only",
    "non_authority", "mutated_external_state", "detection_note",
}
_REUSE_REASON_KEYS = {"kind", "severity", "detail"}
_REUSE_REASON_KINDS = frozenset({
    "none", "milestone_incompatible", "scope_incompatible",
    "acceptance_unsatisfied", "role_separation_violation", "authority_violation",
})
_REUSE_REJECT_KINDS = _REUSE_REASON_KINDS - {"none"}


def _result(*, valid: bool, outcome: str, stage: str, error: str | None,
            proposal: Dict[str, Any] | None = None,
            correction: Dict[str, Any] | None = None,
            reuse: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "valid": valid,
        "outcome": outcome,
        "stage": stage,
        "error": error,
        "proposal": proposal,
        "correction": correction,
        "reuse": reuse,
        "advisory_only": True,
        "non_authority": True,
        "mutated_external_state": False,
        "detection_note": (
            "pure V0.7 composition only; no Controller/state/route/permission/"
            "budget/verdict/crown/promotion/evidence/external mutation authority"
        ),
    }


def _fail(stage: str, error: str, *, proposal: Dict[str, Any] | None = None,
          correction: Dict[str, Any] | None = None,
          reuse: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return _result(valid=False, outcome="advisory_reject", stage=stage,
                   error=error, proposal=proposal, correction=correction, reuse=reuse)


def _copy_present(source: Dict[str, Any], destination: Dict[str, Any], *keys: str) -> None:
    """Copy only supplied frozen facts so downstream absent/null semantics survive."""
    for key in keys:
        if key in source:
            destination[key] = source[key]


def _plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _bounded_text(value: Any, *, max_len: int = MAX_OUTPUT_TEXT) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= max_len


def _brain_is_safe(result: Any) -> bool:
    """Validate the exact frozen Strategic Brain success envelope."""
    if not isinstance(result, dict) or set(result) != _BRAIN_KEYS:
        return False
    proposal_id = result.get("proposal_id")
    if (result.get("schema") != brain_contract.SCHEMA
            or result.get("non_authority") is not True
            or result.get("origin") != "strategic-brain"
            or not isinstance(proposal_id, str)
            or len(proposal_id) != 16
            or any(ch not in _BRAIN_HEX for ch in proposal_id)
            or not _bounded_text(result.get("goal"), max_len=brain_contract.MAX_GOAL)):
        return False

    plan = result.get("plan")
    if not isinstance(plan, list) or not (1 <= len(plan) <= brain_contract.MAX_CONSTRAINTS):
        return False
    for expected_step, item in enumerate(plan, start=1):
        if not isinstance(item, dict) or set(item) != _BRAIN_PLAN_KEYS:
            return False
        if (not _plain_int(item.get("step"))
                or item["step"] != expected_step
                or item.get("action") != "plan_item"
                or not _bounded_text(item.get("detail"), max_len=_BRAIN_PLAN_DETAIL_MAX)):
            return False
    return True


def _correction_is_safe(result: Any) -> bool:
    """Validate the exact frozen C success envelope and every correction item."""
    if not isinstance(result, dict) or set(result) != _CORRECTION_KEYS:
        return False
    if (result.get("schema") != correction_contract.SCHEMA
            or result.get("advisory_only") is not True
            or result.get("non_authority") is not True
            or result.get("mutated_external_state") is not False
            or not _bounded_text(result.get("detection_note"))):
        return False

    corrections = result.get("corrections")
    if not isinstance(corrections, list) or not corrections:
        return False
    if len(corrections) > len(_CORRECTION_ACTIVE_KINDS):
        # The frozen implementation emits either one "none" item or at most one
        # item for each of its four active correction detectors.
        return False

    kinds = []
    for item in corrections:
        if not isinstance(item, dict) or set(item) != _CORRECTION_ITEM_KEYS:
            return False
        kind = item.get("kind")
        if (kind not in _CORRECTION_KINDS
                or item.get("severity") != "advisory"
                or not _bounded_text(item.get("detail"), max_len=correction_contract.MAX_DETAIL)):
            return False
        kinds.append(kind)

    if len(set(kinds)) != len(kinds):
        return False
    if "none" in kinds:
        return kinds == ["none"]
    return all(kind in _CORRECTION_ACTIVE_KINDS for kind in kinds)


def _reuse_is_safe(result: Any) -> bool:
    """Validate the exact frozen Strategic Reuse success envelope and reasons."""
    if not isinstance(result, dict) or set(result) != _REUSE_KEYS:
        return False
    decision = result.get("decision")
    if (result.get("schema") != reuse_contract.SCHEMA
            or decision not in ("reuse", "reject")
            or not _bounded_text(result.get("decision_detail"))
            or result.get("advisory_only") is not True
            or result.get("non_authority") is not True
            or result.get("mutated_external_state") is not False
            or not _bounded_text(result.get("detection_note"))):
        return False

    reasons = result.get("reasons")
    if not isinstance(reasons, list) or not reasons:
        return False
    if len(reasons) > len(_REUSE_REJECT_KINDS):
        return False

    kinds = []
    for item in reasons:
        if not isinstance(item, dict) or set(item) != _REUSE_REASON_KEYS:
            return False
        kind = item.get("kind")
        if (kind not in _REUSE_REASON_KINDS
                or item.get("severity") != "advisory"
                or not _bounded_text(item.get("detail"))):
            return False
        kinds.append(kind)

    if len(set(kinds)) != len(kinds):
        return False
    if decision == "reuse":
        return kinds == ["none"]
    return "none" not in kinds and all(kind in _REUSE_REJECT_KINDS for kind in kinds)


def evaluate(input_: Any) -> Dict[str, Any]:
    """Compose the accepted V0.7 strategic contracts into one advisory path.

    Input::
        {
          "brain_input": <Strategic Brain input>,
          "frozen_facts": {
            "current_milestone": str,
            "allowed_milestones": [...],
            "premature_milestones": [...],
            "controller_owned_actions": [...],
            "scope_allowlist": [...],
            "acceptance_requirements": [...],
            "authority_constraints": [...],
            "role_separation_terms": [...]
          },
          "reuse_material": <Strategic Reuse material>
        }

    ``frozen_facts`` is the single supplied current-facts object. This module
    only projects it into each accepted contract's existing input shape; it does
    not create or persist another canonical state.
    """
    if not isinstance(input_, dict):
        return _fail("integration", "INPUT_NOT_OBJECT")

    try:
        canonical = json.dumps(input_, sort_keys=True, separators=(",", ":"),
                               allow_nan=False)
    except (TypeError, ValueError):
        return _fail("integration", "INPUT_SERIALIZATION_FAILED")
    if len(canonical) > MAX_SERIALIZED_INPUT:
        return _fail("integration", "INPUT_SERIALIZED_TOO_LARGE")

    if "brain_input" not in input_:
        return _fail("strategic_brain", "BRAIN_INPUT_MISSING")
    if "frozen_facts" not in input_:
        return _fail("integration", "FROZEN_FACTS_MISSING")
    if "reuse_material" not in input_:
        return _fail("strategic_reuse", "REUSE_MATERIAL_MISSING")

    frozen = input_.get("frozen_facts")
    if not isinstance(frozen, dict):
        return _fail("integration", "FROZEN_FACTS_NOT_OBJECT")

    try:
        proposal = build_proposal(input_.get("brain_input"))
    except Exception:  # Defensive fail-closed guard; never exposes exception text.
        return _fail("strategic_brain", "BRAIN_UNEXPECTED_FAILURE")
    if not isinstance(proposal, dict):
        return _fail("strategic_brain", "BRAIN_RESULT_NOT_OBJECT")
    if proposal.get("valid") is False:
        return _fail("strategic_brain", "BRAIN_CONTRACT_REJECTED", proposal=proposal)
    if not _brain_is_safe(proposal):
        return _fail("strategic_brain", "BRAIN_RESULT_UNSAFE", proposal=proposal)

    frozen_route: Dict[str, Any] = {}
    _copy_present(
        frozen,
        frozen_route,
        "current_milestone",
        "allowed_milestones",
        "premature_milestones",
        "controller_owned_actions",
    )
    try:
        correction = evaluate_correction({
            "proposal": proposal,
            "frozen_route": frozen_route,
        })
    except Exception:
        return _fail("strategic_correction", "CORRECTION_UNEXPECTED_FAILURE",
                     proposal=proposal)
    if isinstance(correction, dict) and correction.get("valid") is False:
        return _fail("strategic_correction", "CORRECTION_CONTRACT_REJECTED",
                     proposal=proposal, correction=correction)
    if not _correction_is_safe(correction):
        return _fail("strategic_correction", "CORRECTION_RESULT_UNSAFE",
                     proposal=proposal,
                     correction=correction if isinstance(correction, dict) else None)

    correction_kinds = [item["kind"] for item in correction["corrections"]]
    if any(kind != "none" for kind in correction_kinds):
        return _result(
            valid=True,
            outcome="advisory_reject",
            stage="strategic_correction",
            error=None,
            proposal=proposal,
            correction=correction,
            reuse=None,
        )

    current: Dict[str, Any] = {}
    if "current_milestone" in frozen:
        current["milestone"] = frozen["current_milestone"]
    _copy_present(
        frozen,
        current,
        "allowed_milestones",
        "scope_allowlist",
        "acceptance_requirements",
        "authority_constraints",
        "role_separation_terms",
    )
    try:
        reuse = evaluate_reuse({
            "material": input_.get("reuse_material"),
            "current": current,
        })
    except Exception:
        return _fail("strategic_reuse", "REUSE_UNEXPECTED_FAILURE",
                     proposal=proposal, correction=correction)
    if isinstance(reuse, dict) and reuse.get("valid") is False:
        return _fail("strategic_reuse", "REUSE_CONTRACT_REJECTED",
                     proposal=proposal, correction=correction, reuse=reuse)
    if not _reuse_is_safe(reuse):
        return _fail("strategic_reuse", "REUSE_RESULT_UNSAFE",
                     proposal=proposal, correction=correction,
                     reuse=reuse if isinstance(reuse, dict) else None)

    outcome = "advisory_reuse" if reuse["decision"] == "reuse" else "advisory_reject"
    return _result(
        valid=True,
        outcome=outcome,
        stage="complete",
        error=None,
        proposal=proposal,
        correction=correction,
        reuse=reuse,
    )
