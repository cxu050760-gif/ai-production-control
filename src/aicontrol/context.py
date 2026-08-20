from __future__ import annotations

"""M2 mechanical Context Capsule projector.

A Context Capsule is the durable handoff a fresh / recovered Builder reads to
continue a task WITHOUT the user re-explaining history. It must be projectable
mechanically from canonical durable state — never built from a possibly-forgotten
AI's memory of "what was completed". This module derives every fact from the
Controller's own canonical tables:

  - Goal Contract (latest),
  - verified actor results (VERIFIED + COMPLETED),
  - evidence records,
  - canonical test executions,
  - unresolved / OUTCOME_UNKNOWN external effects (NEVER silently dropped).

Invariants enforced:
  - UNKNOWN effects are preserved in `unknown_effects` and never rewritten as done.
  - `completed_facts` are mechanical, deterministic DB-derived facts (counts +
    identity), not prose an AI invented.
  - the capsule carries a `state_revision` and a `provable_fence` computed from
    the stable core, so a recovered Builder can detect a stale/fabricated capsule.
"""

import json
from typing import Any

from .store import ControlStore
from .util import canonical_json, sha256_text, utc_now

CAPSULE_SCHEMA_VERSION = 1
FENCE_FIELD = "provable_fence"
STAMP_FIELDS = ("generated_at", FENCE_FIELD)

UNRESOLVED_STATUSES = ("EFFECT_START_COMMITTED", "OUTCOME_UNKNOWN")


def _unresolved_effects(store: ControlStore, task_id: str) -> list[dict[str, Any]]:
    rows = store.connection.execute(
        "SELECT action_id,logical_effect_id,status,outcome_json,provider FROM actions "
        "WHERE task_id=? AND status IN (?,?) ORDER BY updated_at",
        (task_id, *UNRESOLVED_STATUSES),
    ).fetchall()
    result = []
    for row in rows:
        entry = {
            "action_id": row["action_id"],
            "logical_effect_id": row["logical_effect_id"],
            "status": row["status"],  # EFFECT_START_COMMITTED or OUTCOME_UNKNOWN
            "provider": row["provider"],
        }
        try:
            entry["outcome"] = json.loads(row["outcome_json"]) if row["outcome_json"] else None
        except (ValueError, TypeError):
            entry["outcome"] = {"malformed": True}
        result.append(entry)
    return result


def _verified_result_count(store: ControlStore, task_id: str) -> int:
    row = store.connection.execute(
        "SELECT COUNT(*) AS n FROM results r JOIN invocations i ON i.invocation_id=r.invocation_id "
        "WHERE i.task_id=? AND r.verification_status='VERIFIED' AND i.status='COMPLETED'",
        (task_id,),
    ).fetchone()
    return int(row["n"])


def _evidence_records(store: ControlStore, task_id: str) -> list[dict[str, Any]]:
    return [
        {"evidence_id": r["evidence_id"], "kind": r["kind"], "path": r["path"], "sha256": r["sha256"]}
        for r in store.connection.execute(
            "SELECT evidence_id,kind,path,sha256 FROM evidence WHERE task_id=? ORDER BY created_at",
            (task_id,),
        )
    ]


def build_mechanical_capsule(store: ControlStore, task_id: str) -> dict[str, Any]:
    """Project a Context Capsule purely from canonical durable state."""
    goal = store.latest_goal(task_id)
    state_revision = store.state_head()
    unresolved = _unresolved_effects(store, task_id)
    evidence = _evidence_records(store, task_id)
    tests = store.tests(task_id)
    verified_results = _verified_result_count(store, task_id)
    revision_count = int(
        store.connection.execute("SELECT COUNT(*) AS n FROM canonical_revisions").fetchone()["n"]
    )

    # Mechanical, deterministic facts — never AI-invented prose.
    completed_facts = [
        f"goal_contract:version={goal['contract_version']}:hash={goal['contract_hash']}",
        f"state_revision={state_revision}",
        f"canonical_revisions={revision_count}",
        f"verified_results={verified_results}",
        f"evidence_records={len(evidence)}",
        f"test_executions={len(tests)}",
        f"unresolved_effects={len(unresolved)}",
    ]

    core = {
        "schema_version": CAPSULE_SCHEMA_VERSION,
        "kind": "CONTEXT_CAPSULE_MECHANICAL",
        "source": "CANONICAL_STATE_PROJECTION",
        "task_id": task_id,
        "objective": goal.get("goal", ""),
        "goal_contract_version": goal["contract_version"],
        "goal_contract_hash": goal["contract_hash"],
        "state_revision": state_revision,
        "completed_facts": sorted(completed_facts),
        # UNKNOWN is preserved verbatim; never omitted and never rewritten as done.
        "unknown_effects": unresolved,
        "evidence": [{"evidence_id": e["evidence_id"], "kind": e["kind"]} for e in evidence],
        "test_cases": [{"case_id": t["case_id"], "result": t["exit_or_observed_result"]} for t in tests],
    }
    fence = sha256_text(canonical_json(core))
    return {**core, "generated_at": utc_now(), FENCE_FIELD: fence}


def verify_capsule(capsule: dict[str, Any]) -> bool:
    """Return True iff the capsule's fence matches its stable core."""
    core = {k: v for k, v in capsule.items() if k not in STAMP_FIELDS}
    return sha256_text(canonical_json(core)) == capsule.get(FENCE_FIELD)