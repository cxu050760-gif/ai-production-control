"""Thin TEST-ONLY binding point for the parallel B1 integration candidate.

B2 must not invent or reimplement B1's production API. Until B1 lands, this
adapter is intentionally unbound. After B1 supplies the final callable/output
shape, change ONLY this file as minimally as possible to expose raw stage results.
No policy, filtering, fallback-PASS, correction, or reuse logic belongs here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


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
    return False


def invoke_case(case: Any) -> Observation:
    del case
    raise B1InterfaceNotBound(
        "B1 final integration interface is not bound yet. Bind this test-only adapter "
        "to the B1 candidate without adding policy logic."
    )
