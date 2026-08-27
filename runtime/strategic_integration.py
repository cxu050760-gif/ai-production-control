"""V0.7 core integration wiring for Strategic Brain -> C -> Strategic Reuse.

This module is intentionally thin and pure.  It composes the three already
accepted V0.7 contracts without changing them and without importing Runtime
state/transport/controller internals.

The integration is fail-closed:
- an invalid Strategic Brain result stops the chain;
- any invalid C result stops the chain;
- any non-``none`` C correction stops before Strategic Reuse (C remains
  advisory-only; this layer never applies a correction or mutates authority);
- an invalid Strategic Reuse result stops the chain;
- a Strategic Reuse ``reject`` remains an advisory rejection.

No result from this module grants PASS, promotion, milestone crown, Controller
mutation authority, or external-effect authority.
"""
from __future__ import annotations

import json
from typing import Any, Dict

try:  # Existing runtime tests import modules directly from runtime/.
    from strategic_brain_contract import build_proposal
    from strategic_correction import evaluate as evaluate_correction
    from strategic_reuse_contract import evaluate as evaluate_reuse
except ModuleNotFoundError:  # Also support project-root namespace imports.
    from runtime.strategic_brain_contract import build_proposal
    from runtime.strategic_correction import evaluate as evaluate_correction
    from runtime.strategic_reuse_contract import evaluate as evaluate_reuse

SCHEMA = "v0.7-strategic-integration-advisory"
MAX_SERIALIZED_INPUT = 65536


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
          correction: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return _result(valid=False, outcome="advisory_reject", stage=stage,
                   error=error, proposal=proposal, correction=correction)


def _copy_present(source: Dict[str, Any], destination: Dict[str, Any], *keys: str) -> None:
    """Copy only supplied frozen facts so downstream absent/null semantics survive."""
    for key in keys:
        if key in source:
            destination[key] = source[key]


def _correction_is_safe(result: Any) -> bool:
    return (
        isinstance(result, dict)
        and result.get("schema") == "v0.7-c-advisory"
        and result.get("advisory_only") is True
        and result.get("non_authority") is True
        and result.get("mutated_external_state") is False
        and isinstance(result.get("corrections"), list)
        and bool(result.get("corrections"))
    )


def _reuse_is_safe(result: Any) -> bool:
    return (
        isinstance(result, dict)
        and result.get("schema") == "v0.7-strategic-reuse-advisory"
        and result.get("advisory_only") is True
        and result.get("non_authority") is True
        and result.get("mutated_external_state") is False
        and result.get("decision") in ("reuse", "reject")
    )


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

    ``frozen_facts`` is the single supplied current-facts object.  This module
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
    if (proposal.get("schema") != "v0.7-strategic-brain-proposal"
            or proposal.get("non_authority") is not True
            or not isinstance(proposal.get("plan"), list)):
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

    correction_kinds = [item.get("kind") for item in correction["corrections"]
                        if isinstance(item, dict)]
    if (len(correction_kinds) != len(correction["corrections"])
            or any(kind != "none" for kind in correction_kinds)):
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
                     proposal=proposal, correction=correction)
    if not _reuse_is_safe(reuse):
        return _fail("strategic_reuse", "REUSE_RESULT_UNSAFE",
                     proposal=proposal, correction=correction)

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
