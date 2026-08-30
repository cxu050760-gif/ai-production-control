"""V0.7 C — minimal deterministic strategic-correction contract (V07-C-CONTRACT-2).

Frozen-definition basis (V0.7):
  C = 战略纠偏 (strategic correction).

Boundary contract (per task scope):
- Consumes a *bounded* planning proposal (Strategic Brain proposal shape) plus
  supplied frozen-route facts, and emits a structured, machine-parseable
  strategic-correction result (advisory-only).
- DETECTS at minimum: scope drift, premature milestone work, Builder
  self-review or verdict assignment, and unauthorized promotion assumptions.
- Advisory-only: has NO mechanism to mutate Controller route, task state,
  permissions, budget, verdicts, milestone crown, promotion state, evidence
  disposition, or external systems.

Design invariants (provable by test_strategic_correction_offline.py):
1. Pure computation: no IO, no subprocess, no eval/exec, no global state, no
   imports from the runtime internals. The only observable effect is the
   returned dict (every returned dict, including every rejection envelope,
   carries "advisory_only": true, "non_authority": true, and
   "mutated_external_state": false).
2. Fail closed on ill-formed / out-of-bound input: a present non-object (incl.
   falsey) proposal or frozen_route is rejected with a machine-parseable
   {"valid": false, "error": "<code>"}; bounds are deterministic.
   evaluate() NEVER raises: explicit null or non-list values for
   proposal.plan, allowed_milestones, premature_milestones, and
   controller_owned_actions are structurally rejected (PROPOSAL_PLAN_INVALID /
   ROUTE_LIST_INVALID_*) before any iteration, so no TypeError can ever
   surface to the caller.
3. Canonicalization/serialization failures become structured deterministic
   rejection results (json.dumps allow_nan=False guarded).
4. Deterministic: identical input -> identical correction result.
5. Premature-milestone detection derives EXCLUSIVELY from the supplied
   frozen_route facts (premature_milestones minus explicitly allowed
   milestones); a milestone explicitly allowed by the route is never
   corrected as premature, and no hard-coded milestone token is treated as
   premature.

Input contract (strict, bounded):
    {
      "proposal": {                     # bounded Strategic-Brain-shaped proposal
        "schema": str,                  # optional; accepted as-is
        "goal": str,                    # 1..256 chars
        "plan": [                       # list 0..32 items (explicit null rejected)
          {"step": int, "action": str, "detail": str(1..128)}
        ],
        "context": {str: <json scalar>, ...}   # dict; <=16 keys; SB bounds apply
      },
      "frozen_route": {
        "current_milestone": str,       # 1..64 chars
        "allowed_milestones": [str,...] # list 0..16 items, each <=64 chars (explicit null rejected)
        "premature_milestones": [str,...]  # list 0..8 items, each <=64 chars (explicit null rejected)
        "controller_owned_actions": [str,...]  # list 0..16 items (explicit null rejected)
      }
    }

Output contract (on valid input):
    {
      "schema": "v0.7-c-advisory",
      "corrections": [{"kind": "none" | "scope_drift" | "premature_milestone" |
                                "builder_role_self_review" | "promotion_assumption",
                       "severity": "advisory", "detail": str}, ...],
      "advisory_only": true,
      "non_authority": true,
      "mutated_external_state": false,
      "detection_note": str
    }
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = "v0.7-c-advisory"
PROPOSAL_SCHEMA = "v0.7-strategic-brain-proposal"

# Deterministic finite bounds.
MAX_GOAL = 256
MAX_STEPS = 32
MAX_DETAIL = 128
MAX_CTX_KEYS = 16
MAX_CTX_KEY_LEN = 64
MAX_CTX_STR_LEN = 512
MAX_INT_MAG = 10 ** 18
MAX_CTX_SERIALIZED = 8192
MAX_CORPUS = 16 * 1024
MAX_MILES = 16
MAX_MILE_LEN = 64
MAX_PREMATURE = 8
MAX_OWNED = 16
MAX_ROUTE_SERIALIZED = 4096

# Detection lexicons (pure data; never executed).
# Premature-milestone detection derives EXCLUSIVELY from the supplied
# frozen_route facts (premature_milestones minus explicitly allowed
# milestones); no hard-coded milestone tokens are treated as premature.
_PROMOTION_TERMS = ("promote", "promotion", "crown", "advance_milestone",
                    "advance milestone", "milestone crown", "declare pass",
                    "declare_pass")
_SELF_REVIEW_TERMS = ("self-report", "self review", "self-review", "self_report",
                      "assign_verdict", "assign verdict", "own verdict",
                      "builder self", "declare_pass", "declare pass",
                      "approve own", "verdict myself")
_SCOPE_DRIFT_TERMS = ("strategic reuse", "strategic_reuse", "brain_url", "Brain_URL",
                      "c_url", "C_URL", "integration", "integrate", "implement cascade",
                      "provider adapter")


def _bounded_error(code: str) -> Dict[str, Any]:
    return {"valid": False, "schema": SCHEMA, "error": code, "corrections": None,
            "advisory_only": True, "non_authority": True,
            "mutated_external_state": False}


def _canonical(obj: Any, cap: int) -> Tuple[str, Optional[str]]:
    try:
        canon = json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return "", "SERIALIZATION_FAILED"
    if len(canon) > cap:
        return "", "SERIALIZED_TOO_LARGE"
    return canon, None


def _validate_context(context: Dict[str, Any]) -> Optional[str]:
    if len(context) > MAX_CTX_KEYS:
        return "CONTEXT_TOO_MANY_KEYS"
    for k, v in context.items():
        if not isinstance(k, str) or not (1 <= len(k) <= MAX_CTX_KEY_LEN):
            return "CONTEXT_KEY_INVALID"
        if isinstance(v, bool):
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


def _validate_proposal(proposal: Any) -> Optional[str]:
    if not isinstance(proposal, dict):
        return "PROPOSAL_NOT_OBJECT"
    goal = proposal.get("goal")
    if not isinstance(goal, str) or not (1 <= len(goal) <= MAX_GOAL):
        return "PROPOSAL_GOAL_INVALID"
    plan = proposal.get("plan")
    if plan is None:
        if "plan" in proposal:
            # explicit null plan is rejected (fail-closed; never iterated)
            return "PROPOSAL_PLAN_INVALID"
        plan = []
    if not isinstance(plan, list) or not (0 <= len(plan) <= MAX_STEPS):
        return "PROPOSAL_PLAN_INVALID"
    for s in plan:
        if not isinstance(s, dict):
            return "PROPOSAL_STEP_NOT_OBJECT"
        if not isinstance(s.get("step"), int) or not isinstance(s.get("action"), str) \
                or not isinstance(s.get("detail"), str) or not (1 <= len(s["detail"]) <= MAX_DETAIL):
            return "PROPOSAL_STEP_INVALID"
    if "context" in proposal:
        ctx = proposal["context"]
        if not isinstance(ctx, dict):
            return "PROPOSAL_CONTEXT_NOT_OBJECT"
        err = _validate_context(ctx)
        if err is not None:
            return "PROPOSAL_CONTEXT_" + err
    return None


def _validate_route(route: Any) -> Optional[str]:
    if not isinstance(route, dict):
        return "ROUTE_NOT_OBJECT"
    cur = route.get("current_milestone")
    if not isinstance(cur, str) or not (1 <= len(cur) <= MAX_MILE_LEN):
        return "ROUTE_CURRENT_INVALID"
    for field, cap in (("allowed_milestones", MAX_MILES), ("controller_owned_actions", MAX_OWNED)):
        items = route.get(field)
        if items is None and field not in route:
            continue  # absent list field is allowed (bounded to [] in evaluation)
        if not isinstance(items, list) or not (0 <= len(items) <= cap):
            # explicit null or non-list value is rejected (fail-closed)
            return "ROUTE_LIST_INVALID_" + field.upper()
        for it in items:
            if not isinstance(it, str) or not (1 <= len(it) <= MAX_MILE_LEN):
                return "ROUTE_ITEM_INVALID_" + field.upper()
    prem = route.get("premature_milestones")
    if prem is None and "premature_milestones" not in route:
        prem = []
    if not isinstance(prem, list) or not (0 <= len(prem) <= MAX_PREMATURE):
        # explicit null or non-list value is rejected (fail-closed)
        return "ROUTE_LIST_INVALID_PREMATURE"
    for it in prem:
        if not isinstance(it, str) or not (1 <= len(it) <= MAX_MILE_LEN):
            return "ROUTE_ITEM_INVALID_PREMATURE"
    return None


def _corpus(proposal: Dict[str, Any]) -> str:
    parts = [proposal.get("goal", "")]
    for s in proposal.get("plan", []):
        parts.append(str(s.get("action", "")))
        parts.append(str(s.get("detail", "")))
    ctx = proposal.get("context")
    if isinstance(ctx, dict):
        for k, v in ctx.items():
            parts.append(f"{k}={v}")
    corpus = " ".join(parts)
    return corpus[:MAX_CORPUS].lower()


def evaluate(input_: Any) -> Dict[str, Any]:
    """C boundary function: bounded proposal + frozen-route facts -> advisory result.

    Guaranteed to NEVER raise: every ill-formed or out-of-bound branch returns
    a structured rejection envelope (see invariant 2).
    """
    if not isinstance(input_, dict):
        return _bounded_error("INPUT_NOT_OBJECT")
    proposal = input_.get("proposal")
    route = input_.get("frozen_route")
    if "proposal" not in input_ or proposal is None:
        return _bounded_error("PROPOSAL_MISSING")
    if "frozen_route" not in input_ or route is None:
        return _bounded_error("ROUTE_MISSING")
    err = _validate_proposal(proposal)
    if err is not None:
        return _bounded_error(err)
    err = _validate_route(route)
    if err is not None:
        return _bounded_error(err)
    for key, obj, cap in (("proposal", proposal, 16384), ("frozen_route", route, MAX_ROUTE_SERIALIZED)):
        _, cerr = _canonical(obj, cap)
        if cerr is not None:
            return _bounded_error("CANONICAL_" + key.upper() + "_" + cerr)

    corpus = _corpus(proposal)
    allowed = [m.lower() for m in route.get("allowed_milestones", [])]
    premature = [m.lower() for m in route.get("premature_milestones", [])]
    owned = [a.lower() for a in route.get("controller_owned_actions", [])]

    corrections: List[Dict[str, Any]] = []
    cur_mile = str(route.get("current_milestone", "")).lower()

    def add(kind: str, detail: str) -> None:
        corrections.append({"kind": kind, "severity": "advisory", "detail": detail})

    # premature milestone work: derived ONLY from supplied frozen_route facts;
    # a milestone explicitly in the route's allowed set is never corrected.
    effective_premature = [p for p in premature if p not in allowed]
    if any(p in corpus for p in effective_premature):
        add("premature_milestone",
            "proposal references a route-declared premature milestone not in the allowed set")
    # unauthorized promotion assumptions (direct detection incl. "promote")
    if any(t in corpus for t in _PROMOTION_TERMS):
        add("promotion_assumption",
            "proposal assumes promotion/crowning/advance milestones contrary to Controller authority")
    # Builder self-review or verdict assignment (role separation)
    if any(t in corpus for t in _SELF_REVIEW_TERMS):
        add("builder_role_self_review",
            "proposal implies Builder self-review or verdict assignment (role separation violated)")
    # scope drift outside the frozen C/Strategic-Brain boundaries
    if any(t in corpus for t in _SCOPE_DRIFT_TERMS) or any(a.lower() in corpus for a in owned):
        add("scope_drift", "proposal drifts outside the accepted Strategic Brain / C scope or controller-owned actions")

    if not corrections:
        corrections.append({"kind": "none", "severity": "advisory",
                            "detail": f"no correction; current milestone {cur_mile or 'unknown'} within route"})

    return {
        "schema": SCHEMA,
        "corrections": corrections,
        "advisory_only": True,
        "non_authority": True,
        "mutated_external_state": False,
        "detection_note": "advisory only; C holds no mutation mechanism for route/task/permission/budget/"
                          "verdict/crown/promotion/evidence/external state",
    }