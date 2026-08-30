"""Thin TEST-ONLY binding to B1's real V0.7 integration callable.

The adapter performs no fact reconciliation, translation, policy, filtering,
correction, reuse decision, fallback-PASS, or authority logic. Candidate tests
use the production-native input shape directly:
  brain_input + frozen_facts + reuse_material
Legacy dual-fact packets are passed through unchanged and therefore must fail
closed in the real integration rather than being silently merged here.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    import strategic_integration as integration
except ModuleNotFoundError:
    from runtime import strategic_integration as integration


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


def invoke_case(case: Any) -> Observation:
    # Deep-copy solely to protect the test fixture from a production mutation.
    # No semantic translation or fact-source merging is permitted here.
    raw = integration.evaluate(copy.deepcopy(case))
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
