"""V0.7 Strategic Brain — minimal deterministic contract (V07-STRATEGIC-BRAIN-CONTRACT-1).

Boundary contract (verbatim scope from task):
- Accepts a *bounded* planning input and emits a *structured, machine-parseable
  proposal*. It has NO mechanism to edit controller state, route, permissions,
  budget, verdicts, promotion state, or production effects.
- C / Strategic Reuse / Brain_URL / C_URL are explicitly OUT of scope and MUST
  NOT appear in this slice.
- Deterministic: identical input produces an identical proposal (same
  proposal_id).

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
      "context": {str: <json scalar>, ...}   # <= 16 keys
    }

Output contract (on valid input):
    {
      "schema": "v0.7-strategic-brain-proposal",
      "proposal_id": str,          # sha256(goal|constraints|context) truncated 16
      "goal": str,
      "plan": [{"step": int, "action": "plan_item", "detail": str}, ...],
      "non_authority": true,
      "origin": "strategic-brain"
    }
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

SCHEMA = "v0.7-strategic-brain-proposal"
MAX_GOAL = 256
MAX_CONSTRAINTS = 8
MAX_VALUE = 128
MAX_CTX_KEYS = 16

# Bound-checked scalar types only; anything else is rejected.
_ALLOWED_CTX_TYPES = (str, int, float, bool, type(None))

# Authority-bearing directive vocabulary that must NEVER be emitted as an action
# (used by tests to prove non-execution of authority-bearing outputs).
_AUTHORITY_LEXICON = (
    "crown", "advance_milestone", "promotion", "route", "permission",
    "budget", "verdict", "exec", "eval", "subprocess", "write", "delete",
    "milestone_crown", "controller_state",
)


def _bounded_error(code: str) -> Dict[str, Any]:
    return {"valid": False, "schema": SCHEMA, "error": code, "proposal_id": None}


def _proposal_id(goal: str, constraints: List[Dict[str, str]], context: Optional[Dict[str, Any]]) -> str:
    payload = json.dumps(
        {"goal": goal, "constraints": constraints, "context": context or {}},
        sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


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

    context = input_.get("context") or {}
    if not isinstance(context, dict):
        return _bounded_error("CONTEXT_NOT_OBJECT")
    if len(context) > MAX_CTX_KEYS:
        return _bounded_error("CONTEXT_TOO_MANY_KEYS")
    for k, v in context.items():
        if not isinstance(k, str) or not isinstance(v, _ALLOWED_CTX_TYPES):
            return _bounded_error("CONTEXT_MEMBER_INVALID")

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
        "proposal_id": _proposal_id(goal, clean_constraints, dict(context)),
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