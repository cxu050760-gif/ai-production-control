"""V0.7 SR — minimal deterministic Strategic Reuse contract (V07-STRATEGIC-REUSE-CONTRACT-6).

Frozen-definition basis (V0.7):
  S = Strategic Reuse (战略复用): explicitly supplied mature strategy material may
  be reused only when compatible with the CURRENT frozen-route facts, scope,
  role boundaries, acceptance requirements, and authority constraints.

Boundary contract (per task scope):
- Consumes explicit reusable strategy material (bounded), plus current bounded
  route/task facts, and emits a machine-parseable reuse-or-reject result.
- Current supplied facts (milestone, scope allowlist, acceptance requirements,
  role-separation terms, authority constraints) OVERRIDE incompatible
  historical strategy material or historical task shapes.
- Advisory-only: has NO mechanism to mutate Controller route, task state,
  permissions, budget, verdicts, milestone crown, promotion state, evidence
  disposition, or external systems.
- DETECTS at minimum: stale-milestone material, out-of-scope reuse,
  acceptance requirements the historical shape cannot satisfy, role-separation
  violations (Builder self-review / verdict assignment), and authority
  violations (material assuming promotion/crowning or any current-forbidden
  controller-owned action).

Design invariants (provable by test_strategic_reuse_contract_offline.py):
1. Pure computation: no IO, no subprocess, no eval/exec, no global state, no
   imports from the runtime internals. The only observable effect is the
   returned dict (every returned dict, including every rejection envelope,
   carries "advisory_only": true, "non_authority": true, and
   "mutated_external_state": false).
2. Fail closed and NEVER raises: a present non-object / missing / falsey
   material or current is rejected with a machine-parseable
   {"valid": false, "error": "<code>"}; explicit null or non-list list-typed
   fields (requested_scope, promises, allowed_milestones, scope_allowlist,
   acceptance_requirements, authority_constraints, role_separation_terms) are
   structurally rejected before any iteration; bounds are deterministic.
3. Canonicalization/serialization failures become structured deterministic
   rejection results (json.dumps allow_nan=False guarded).
4. Deterministic: identical input -> identical reuse-or-reject result.

Input contract (strict, bounded):
    {
      "material": {                       # explicitly supplied reusable strategy material
        "schema": str,                    # optional; accepted as-is
        "id": str,                        # optional; 1..64 chars
        "strategy": str,                  # 1..1024 chars
        "claimed_milestone": str,         # optional; 1..32 chars
        "requested_scope": [str,...],     # list 0..16 items, each <=64 chars (explicit null rejected)
        "promises": [str,...]             # list 0..32 items, each <=128 chars (explicit null rejected)
      },
      "current": {
        "milestone": str,                 # 1..32 chars
        "allowed_milestones": [str,...],  # list 0..16 items, each <=32 chars (explicit null rejected)
        "scope_allowlist": [str,...],     # list 0..16 items, each <=64 chars (explicit null rejected)
        "acceptance_requirements": [str,...],  # list 0..32 items, each <=128 chars (explicit null rejected)
        "authority_constraints": [str,...],    # list 0..16 items, each <=64 chars (explicit null rejected)
        "role_separation_terms": [str,...]     # list 0..16 items, each <=64 chars (explicit null rejected)
      }
    }

Output contract (on valid input):
    {
      "schema": "v0.7-strategic-reuse-advisory",
      "decision": "reuse" | "reject",
      "decision_detail": str,
      "reasons": [{"kind": "none" | "milestone_incompatible" | "scope_incompatible" |
                            "acceptance_unsatisfied" | "role_separation_violation" |
                            "authority_violation",
                   "severity": "advisory", "detail": str}, ...],
      "advisory_only": true,
      "non_authority": true,
      "mutated_external_state": false,
      "detection_note": str
    }
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = "v0.7-strategic-reuse-advisory"

# Deterministic finite bounds.
MAX_ID = 64
MAX_STRATEGY = 1024
MAX_MILE = 32
MAX_LIST64 = 16
MAX_LIST128 = 32
MAX_CORPUS = 16 * 1024
MAX_SERIALIZED = 16384

# Detection lexicons (pure data; never executed).
_SELF_REVIEW_TERMS = ("self-report", "self review", "self-review", "self_report",
                      "assign_verdict", "assign verdict", "own verdict",
                      "builder self", "approve own", "verdict myself")
_AUTHORITY_TERMS = ("promote", "promotion", "crown", "advance_milestone",
                    "advance milestone", "milestone crown", "declare pass",
                    "declare_pass")


def _bounded_error(code: str) -> Dict[str, Any]:
    return {"valid": False, "schema": SCHEMA, "error": code, "corrections": None,
            "advisory_only": True, "non_authority": True,
            "mutated_external_state": False}


def _canonical(obj: Any) -> Tuple[str, Optional[str]]:
    try:
        canon = json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return "", "SERIALIZATION_FAILED"
    if len(canon) > MAX_SERIALIZED:
        return "", "SERIALIZED_TOO_LARGE"
    return canon, None


def _check_str_list(field: Any, max_items: int, max_len: int) -> Optional[str]:
    if not isinstance(field, list) or not (0 <= len(field) <= max_items):
        return "INVALID"
    for it in field:
        if not isinstance(it, str) or not (1 <= len(it) <= max_len):
            return "ITEM_INVALID"
    return None


def _validate_material(material: Any) -> Optional[str]:
    if not isinstance(material, dict):
        return "MATERIAL_NOT_OBJECT"
    strat = material.get("strategy")
    if not isinstance(strat, str) or not (1 <= len(strat) <= MAX_STRATEGY):
        return "MATERIAL_STRATEGY_INVALID"
    ident = material.get("id")
    if ident is not None:
        if not isinstance(ident, str) or not (1 <= len(ident) <= MAX_ID):
            return "MATERIAL_ID_INVALID"
    cm = material.get("claimed_milestone")
    if cm is not None:
        if not isinstance(cm, str) or not (1 <= len(cm) <= MAX_MILE):
            return "MATERIAL_CLAIMED_MILESTONE_INVALID"
    for field, cap, mlen in (("requested_scope", MAX_LIST64, 64), ("promises", MAX_LIST128, 128)):
        if field in material:
            err = _check_str_list(material.get(field), cap, mlen)
            if err is not None:
                return "MATERIAL_" + field.upper() + "_" + err
    return None


def _validate_current(current: Any) -> Optional[str]:
    if not isinstance(current, dict):
        return "CURRENT_NOT_OBJECT"
    ms = current.get("milestone")
    if not isinstance(ms, str) or not (1 <= len(ms) <= MAX_MILE):
        return "CURRENT_MILESTONE_INVALID"
    for field, cap, mlen in (("allowed_milestones", MAX_LIST64, MAX_MILE),
                             ("scope_allowlist", MAX_LIST64, 64),
                             ("authority_constraints", MAX_LIST64, 64),
                             ("role_separation_terms", MAX_LIST64, 64),
                             ("acceptance_requirements", MAX_LIST128, 128)):
        if field in current:
            err = _check_str_list(current.get(field), cap, mlen)
            if err is not None:
                return "CURRENT_" + field.upper() + "_" + err
    return None


def _material_corpus(material: Dict[str, Any]) -> str:
    parts = [material.get("strategy", "")]
    for p in material.get("promises", []):
        parts.append(p)
    for s in material.get("requested_scope", []):
        parts.append(s)
    return " ".join(parts)[:MAX_CORPUS].lower()


def _norm(s: str) -> str:
    return s.strip().lower()


def evaluate(input_: Any) -> Dict[str, Any]:
    """SR boundary function: reusable strategy material + current facts -> advisory result.

    Guaranteed to NEVER raise (invariant 2).
    """
    if not isinstance(input_, dict):
        return _bounded_error("INPUT_NOT_OBJECT")
    material = input_.get("material")
    current = input_.get("current")
    if "material" not in input_ or material is None:
        return _bounded_error("MATERIAL_MISSING")
    if "current" not in input_ or current is None:
        return _bounded_error("CURRENT_MISSING")
    err = _validate_material(material)
    if err is not None:
        return _bounded_error(err)
    err = _validate_current(current)
    if err is not None:
        return _bounded_error(err)
    _, cerr = _canonical(input_)
    if cerr is not None:
        return _bounded_error("CANONICAL_" + cerr)

    corpus = _material_corpus(material)
    allowed_miles = {_norm(m) for m in current.get("allowed_milestones", [])}
    scope_allow = {_norm(s) for s in current.get("scope_allowlist", [])}
    req_accept = [_norm(a) for a in current.get("acceptance_requirements", [])]
    promises = [_norm(p) for p in material.get("promises", [])]
    requested = [_norm(s) for s in material.get("requested_scope", [])]
    constr = [_norm(a) for a in current.get("authority_constraints", [])]
    rolterms = [_norm(r) for r in current.get("role_separation_terms", [])]

    reasons: List[Dict[str, Any]] = []
    cur_mile = _norm(current.get("milestone", ""))

    def add(kind: str, detail: str) -> None:
        reasons.append({"kind": kind, "severity": "advisory", "detail": detail})

    # stale milestone: material claims a milestone outside the CURRENT allowed set
    cm = material.get("claimed_milestone")
    if cm is not None and _norm(cm) not in allowed_miles:
        add("milestone_incompatible",
            "claimed milestone of reusable material is outside the current route's allowed set; current facts override")
    # out-of-scope reuse: any requested scope term not in the current allowlist
    if requested and not all(s in scope_allow for s in requested):
        add("scope_incompatible",
            "requested scope is not covered by the current scope allowlist; current scope facts override")
    # acceptance: current requirements must all be satisfiable by material promises;
    # an incompatible historical task shape (fewer/older promises) cannot override them
    if req_accept and any(a not in promises for a in req_accept):
        add("acceptance_unsatisfied",
            "material does not satisfy the current acceptance requirements; historical promises cannot override")
    # role separation: material implying Builder self-review/verdict assignment is not reusable
    if any(t in corpus for t in _SELF_REVIEW_TERMS) or any(r in corpus for r in rolterms):
        add("role_separation_violation",
            "reusable material implies Builder self-review or verdict assignment contrary to role separation")
    # authority: material assuming promotion/crowning or current-forbidden controller-owned actions
    if any(t in corpus for t in _AUTHORITY_TERMS) or any(a in corpus for a in constr):
        add("authority_violation",
            "reusable material assumes promotion/crowning or forbidden controller-owned authority")

    if reasons:
        return {
            "schema": SCHEMA,
            "decision": "reject",
            "decision_detail": "material incompatible with current route/scope/acceptance/role/authority facts",
            "reasons": reasons,
            "advisory_only": True,
            "non_authority": True,
            "mutated_external_state": False,
            "detection_note": "advisory only; Strategic Reuse holds no mutation mechanism for route/task/permission/"
                              "budget/verdict/crown/promotion/evidence/external state",
        }

    return {
        "schema": SCHEMA,
        "decision": "reuse",
        "decision_detail": f"material compatible with current facts (milestone {cur_mile or 'unknown'}, scope, acceptance, role, authority)",
        "reasons": [{"kind": "none", "severity": "advisory",
                     "detail": "material consistent with current route/scope/acceptance/role-separation/authority facts"}],
        "advisory_only": True,
        "non_authority": True,
        "mutated_external_state": False,
        "detection_note": "advisory only; Strategic Reuse holds no mutation mechanism for route/task/permission/"
                          "budget/verdict/crown/promotion/evidence/external state",
    }