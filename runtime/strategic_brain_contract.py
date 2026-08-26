"""V0.7 Strategic Brain — minimal deterministic contract (V07-STRATEGIC-BRAIN-CONTRACT-1).

Boundary contract (verbatim scope from task):
- Accepts a *bounded* planning input and emits a *structured, machine-parseable
  proposal*. It has NO mechanism to edit controller state, route, permissions,
  budget, verdicts, promotion state, or production effects.
- C / Strategic Reuse / Brain_URL / C_URL are explicitly OUT of scope and MUST
  NOT appear in this slice.
- Deterministic: identical input produces an identical proposal (same
  proposal_id).

REWORK v2 applied (verdict_v07_strategic_brain_contract_1 NEXT_ACTION):
1. ``context`` is **fail closed on every non-object value**: a present context
   that is not a real ``dict`` (including ``[]``, ``""``, ``0``, ``False``)
   is rejected with ``CONTEXT_NOT_OBJECT``. Falsey values are no longer
   coerced to ``{}``. Only a genuinely absent ``context`` key defaults to ``{}``.
2. **Deterministic finite bounds on the complete accepted context**:
   key count <= 16, key length in [1, 64], string value length <= 512,
   integer magnitude <= 10**18, floats must be finite, plus a canonical
   serialized-size bound (<= 8192 chars). Members outside these bounds are
   rejected with structured, deterministic codes.
3. **Canonicalization/serialization failures become structured deterministic
   rejection results** (``CONTEXT_SERIALIZATION_FAILED`` / ``CONTEXT_SERIALIZED_TOO_LARGE``):
   ``json.dumps(..., allow_nan=False)`` is guarded so any non-finite value or
   non-serializable member yields a rejection, never an exception to the caller.

Design invariants (provable by test_strategic_brain_contract_offline.py):
1. Pure computation only: no IO, no subprocess, no eval/exec, no global state,
   no imports from the runtime internals. The only observable effect of any call
   is the returned dict.
2. Every proposal carries ``"non_authority": true`` — it is inert data.
3. Unsatisfiable/oversized/ill-typed input is rejected with a machine-parseable
   ``{"valid": false, "error": "<code>"}`` and stores nothing.
4. Any authority-bearing text inside an input (e.g. "crown", "advance_milestone",
   "exec(...)") is treated strictly as inert data: it is never executed and never
   emitted as an executable action.

Input contract (strict, bounded):
    {
      "goal": str,                # 1..256 chars
      "constraints": [            # 0..8 items
        {"kind": "must_have" | "must_not_have", "value": str}   # value 1..128 chars
      ],
      "context": {str: <json scalar>, ...}   # dict ONLY; <= 16 keys; see BOUNDS below
    }

Context membership bounds:
    keys: str, 1..64 chars, count <= 16
    values: bool | None | int (-10**18..10**18) | float (finite) | str (0..512 chars)
    canonical serialized size <= 8192 chars

Output contract (on valid input):
    {
      "schema": "v0.7-strategic-brain-proposal",
      "proposal_id": str,          # sha256(goal|constraints|context_canonical) truncated 16
      "goal": str,
      "plan": [{"step": int, "action": "plan_item", "detail": str}, ...],
      "non_authority": True,
      "origin": "strategic-brain"
    }
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = "v0.7-strategic-brain-proposal"
MAX_GOAL = 256
MAX_CONSTRAINTS = 8
MAX_VALUE = 128

# Deterministic finite bounds on the complete accepted context (REWORK v2).
MAX_CTX_KEYS = 16
MAX_CTX_KEY_LEN = 64
MAX_CTX_STR_LEN = 512
MAX_INT_MAG = 10 ** 18
MAX_CTX_SERIALIZED = 8192

# Authority-bearing directive vocabulary that must NEVER be emitted as an action
# (used by tests to prove non-execution of authority-bearing outputs).
_AUTHORITY_LEXICON = (
    "crown", "advance_milestone", "promotion", "route", "permission",
    "budget", "verdict", "exec", "eval", "subprocess", "write", "delete",
    "milestone_crown", "controller_state",
)


def _bounded_error(code: str) -> Dict[str, Any]:
    return {"valid": False, "schema": SCHEMA, "error": code, "proposal_id": None}


def _canonical_context(context: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """Canonicalize context deterministically; bounded size. Returns a structured
    failure code instead of raising when serialization cannot be completed."""
    try:
        canonical = json.dumps(context, sort_keys=True, separators=(",", ":"),
                               allow_nan=False)
    except (TypeError, ValueError):
        return "", "CONTEXT_SERIALIZATION_FAILED"
    if len(canonical) > MAX_CTX_SERIALIZED:
        return "", "CONTEXT_SERIALIZED_TOO_LARGE"
    return canonical, None


def _proposal_id(goal: str, constraints: List[Dict[str, str]], ctx_canonical: str) -> str:
    payload = json.dumps(
        {"goal": goal, "constraints": constraints, "context": ctx_canonical},
        sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _validate_context_members(context: Dict[str, Any]) -> Optional[str]:
    """Validate every context member against the deterministic finite bounds.
    Returns a structured rejection code or None when the whole context is valid."""
    if len(context) > MAX_CTX_KEYS:
        return "CONTEXT_TOO_MANY_KEYS"
    for k, v in context.items():
        if not isinstance(k, str) or not (1 <= len(k) <= MAX_CTX_KEY_LEN):
            return "CONTEXT_KEY_INVALID"
        if isinstance(v, bool):            # bool is an int subclass; allow explicitly
            continue
        if isinstance(v, str):
            if not (0 <= len(v) <= MAX_CTX_STR_LEN):
                return "CONTEXT_STRING_TOO_LONG"
        elif isinstance(v, int):
            if not (-MAX_INT_MAG <= v <= MAX_INT_MAG):
                return "CONTEXT_INT_OVERFLOW"
        elif isinstance(v, float):
            if not math.isfinite(v):
                return "CONTEXT_FLOAT_NOT_FINITE"
        elif v is None:
            continue
        else:
            return "CONTEXT_MEMBER_INVALID"
    return None


def build_proposal(input_: Any) -> Dict[str, Any]:
    """Boundary function: bounded input -> structured (non-authority) proposal."""
    if not isinstance(input_, dict):
        return _bounded_error("INPUT_NOT_OBJECT")
    goal = input_.get("goal")
    if not isinstance(goal, str) or not (1 <= len(goal) <= MAX_GOAL):
        return _bounded_error("GOAL_INVALID")

    constraints = input_.get("constraints")
    if constraints is None:
        constraints = []
    if not isinstance(constraints, list) or not (0 <= len(constraints) <= MAX_CONSTRAINTS):
        return _bounded_error("CONSTRAINTS_INVALID")
    clean_constraints: List[Dict[str, str]] = []
    for c in constraints:
        if not isinstance(c, dict):
            return _bounded_error("CONSTRAINT_NOT_OBJECT")
        kind = c.get("kind")
        value = c.get("value")
        if kind not in ("must_have", "must_not_have"):
            return _bounded_error("CONSTRAINT_KIND_UNKNOWN")
        if not isinstance(value, str) or not (1 <= len(value) <= MAX_VALUE):
            return _bounded_error("CONSTRAINT_VALUE_INVALID")
        clean_constraints.append({"kind": kind, "value": value})

    # FAIL CLOSED on every non-object context (REWORK v2): only a genuinely
    # absent key defaults to {}; a present non-dict (incl. falsey) is rejected.
    if "context" in input_:
        context = input_["context"]
    else:
        context = {}
    if not isinstance(context, dict):
        return _bounded_error("CONTEXT_NOT_OBJECT")
    member_err = _validate_context_members(context)
    if member_err is not None:
        return _bounded_error(member_err)
    ctx_canonical, canon_err = _canonical_context(dict(context))
    if canon_err is not None:
        return _bounded_error(canon_err)

    # Planning: deterministic, purely conditional on the bound-checked input.
    plan: List[Dict[str, Any]] = []
    for c in clean_constraints:
        action = "ensure_presence" if c["kind"] == "must_have" else "ensure_absence"
        plan.append({"step": len(plan) + 1, "action": "plan_item",
                     "detail": f"{action}:{c['value']}"})
    if not plan:
        plan.append({"step": 1, "action": "plan_item", "detail": "assemble_proposal"})

    return {
        "schema": SCHEMA,
        "proposal_id": _proposal_id(goal, clean_constraints, ctx_canonical),
        "goal": goal,
        "plan": plan,
        "non_authority": True,
        "origin": "strategic-brain",
    }


def contains_authority_lexicon(text: str) -> bool:
    """Expose the authority lexicon for tests; returns True if any prohibited
    directive vocabulary appears. The contract never emits these as actions."""
    low = text.lower()
    return any(word in low for word in _AUTHORITY_LEXICON)