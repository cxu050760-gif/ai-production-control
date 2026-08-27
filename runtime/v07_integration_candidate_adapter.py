"""Thin TEST-ONLY binding to the parallel B1 integration candidate.

This file performs shape translation only. It contains no strategic policy,
filtering, correction, reuse decision, fallback-PASS, or authority logic.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    import strategic_integration as integration
except ModuleNotFoundError:
    from runtime import strategic_integration as integration


class B1InterfaceNotBound(RuntimeError):
    pass


@dataclass(frozen=True)
class Observation:
    raw: Any
    brain: Optional[Dict[str, Any]]
    correction: Optional[Dict[str, Any]]
    reuse: Optional[Dict[str, Any]]
    final_status: Optional[str]
    advisory_only: Optional[bool]
    non_authority: Optional[bool]
    mutated_external_state: Optional[bool]


def is_bound() -> bool:
    return True


def _to_candidate_input(case: Any) -> Any:
    """Translate B2's semantic fixture keys to B1's landed input shape only."""
    if not isinstance(case, dict):
        return copy.deepcopy(case)

    # Already-native B1 input: preserve exactly.
    if "frozen_facts" in case or "reuse_material" in case:
        return copy.deepcopy(case)

    payload: Dict[str, Any] = {}
    if "brain_input" in case:
        payload["brain_input"] = copy.deepcopy(case["brain_input"])

    if "frozen_route" in case:
        route = case["frozen_route"]
        if isinstance(route, dict):
            frozen = copy.deepcopy(route)
            reuse_input = case.get("reuse_input")
            current = reuse_input.get("current") if isinstance(reuse_input, dict) else None
            if isinstance(current, dict):
                if "milestone" in current and "current_milestone" not in frozen:
                    frozen["current_milestone"] = copy.deepcopy(current["milestone"])
                for key in (
                    "allowed_milestones",
                    "scope_allowlist",
                    "acceptance_requirements",
                    "authority_constraints",
                    "role_separation_terms",
                ):
                    if key in current:
                        frozen[key] = copy.deepcopy(current[key])
            payload["frozen_facts"] = frozen
        else:
            payload["frozen_facts"] = copy.deepcopy(route)

    if "reuse_input" in case:
        reuse_input = case["reuse_input"]
        if isinstance(reuse_input, dict) and "material" in reuse_input:
            payload["reuse_material"] = copy.deepcopy(reuse_input["material"])
        else:
            payload["reuse_material"] = copy.deepcopy(reuse_input)

    return payload


def invoke_case(case: Any) -> Observation:
    raw = integration.evaluate(_to_candidate_input(case))
    if not isinstance(raw, dict):
        return Observation(raw=raw, brain=None, correction=None, reuse=None,
                           final_status=None, advisory_only=None,
                           non_authority=None, mutated_external_state=None)
    return Observation(
        raw=raw,
        brain=raw.get("proposal"),
        correction=raw.get("correction"),
        reuse=raw.get("reuse"),
        final_status=raw.get("outcome"),
        advisory_only=raw.get("advisory_only"),
        non_authority=raw.get("non_authority"),
        mutated_external_state=raw.get("mutated_external_state"),
    )
