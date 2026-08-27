"""Shared V07-INTEGRATE-2 verification fixtures.

TEST-ONLY. This module deliberately contains no production integration logic.
It supplies frozen semantic inputs and copies for contract/candidate tests.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict

BASE_COMMIT = "a9d4ba60bbc43f7abf93cf8e5042c653871dc78e"
SUCCESS_MARKER = "V07_INTEGRATE2_EVIDENCE_SUCCESS"


def brain_input(detail: str = "assemble current V0.7 strategic proposal") -> Dict[str, Any]:
    return {
        "goal": "Prepare a bounded strategic plan for the current V0.7 task",
        "constraints": [{"kind": "must_have", "value": detail}],
        "context": {"milestone": "V0.7", "role": "Builder", "mode": "advisory-only"},
    }


def frozen_route() -> Dict[str, Any]:
    return {
        "current_milestone": "V0.7",
        "allowed_milestones": ["V0.7"],
        "premature_milestones": ["V0.8", "V0.9", "V1.0"],
        "controller_owned_actions": [
            "modify controller route", "write verdict", "crown milestone",
            "promotion", "change permission", "change budget",
        ],
    }


def reuse_current() -> Dict[str, Any]:
    return {
        "milestone": "V0.7",
        "allowed_milestones": ["V0.7"],
        "scope_allowlist": ["strategic-brain", "strategic-correction", "strategic-reuse"],
        "acceptance_requirements": ["deterministic", "fail-closed", "advisory-only"],
        "authority_constraints": [
            "modify controller route", "write verdict", "crown milestone",
            "promotion", "change permission", "change budget",
        ],
        "role_separation_terms": ["builder self-review", "assign verdict"],
    }


def reusable_material() -> Dict[str, Any]:
    return {
        "id": "v07-compatible-history",
        "strategy": "reuse only compatible V0.7 planning material",
        "claimed_milestone": "V0.7",
        "requested_scope": ["strategic-brain", "strategic-correction", "strategic-reuse"],
        "promises": ["deterministic", "fail-closed", "advisory-only"],
    }


def integration_case() -> Dict[str, Any]:
    """Semantic packet for candidate tests; adapter binds this to B1's final API."""
    return {
        "brain_input": brain_input(),
        "frozen_route": frozen_route(),
        "reuse_input": {"material": reusable_material(), "current": reuse_current()},
    }


def clone(value: Any) -> Any:
    return copy.deepcopy(value)


def load_attack_matrix() -> Dict[str, Any]:
    path = Path(__file__).with_name("fixtures") / "v07_integration_attack_cases.json"
    return json.loads(path.read_text(encoding="utf-8"))
