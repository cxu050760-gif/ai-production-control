from __future__ import annotations

"""M2 durable Workflow core on the Controller SQLite.

Implements the step-graph executor invariants the FINAL product needs:
atomic, fenced step CLAIM; heartbeat/lease; retry budget; REWORK feedback edge
(auto requeue, re-test, and BLOCKED when the budget is exhausted); non-blocking
WAIT (a step waiting on an external result does not stop unrelated READY work);
and crash reconciliation (a CLAIMED step whose heartbeat went stale is made
READY again and re-claimable, so a process/builder crash resumes idempotently).

This adds tables on the SAME Controller DB (no second canonical store) and
reuses the existing authority / Effect WAL / evidence layers; it does not
replace them.
"""

import json
import time
import uuid
from typing import Any, Callable

from .util import canonical_json

# step statuses
STEP_READY = "READY"
STEP_CLAIMED = "CLAIMED"
STEP_DONE = "DONE"
STEP_WAITING = "WAITING"
STEP_REWORK = "REWORK"
STEP_BLOCKED = "BLOCKED"
STEP_STATUSES = (STEP_READY, STEP_CLAIMED, STEP_DONE, STEP_WAITING, STEP_REWORK, STEP_BLOCKED)

# outcome kinds a worker returns
OUTCOME_DONE = "DONE"
OUTCOME_REWORK = "REWORK"
OUTCOME_WAIT = "WAIT"
OUTCOME_UNKNOWN = "UNKNOWN"
OUTCOME_KINDS = (OUTCOME_DONE, OUTCOME_REWORK, OUTCOME_WAIT, OUTCOME_UNKNOWN)

WORKFLOW_SCHEMA = """
CREATE TABLE IF NOT EXISTS wf_runs (
  workflow_id TEXT PRIMARY KEY,
  project_id TEXT,
  goal TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wf_steps (
  step_id TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  depends_on_json TEXT NOT NULL,
  attempt INTEGER NOT NULL,
  retry_budget INTEGER NOT NULL,
  claimed_by TEXT,
  claim_ts REAL,
  heartbeat_ts REAL,
  block_reason TEXT,
  outcome_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


class WorkflowError(RuntimeError):
    pass


class StepNotClaimable(WorkflowError):
    pass


class FenceMismatch(WorkflowError):
    pass


DEFAULT_HEARTBEAT_TTL_SEC = 120.0


class Workflow:
    """Durable, fenced, retryable, crash-resumable step executor."""

    def __init__(self, store: Any, *, heartbeat_ttl_sec: float = DEFAULT_HEARTBEAT_TTL_SEC) -> None:
        self.store = store
        self.heartbeat_ttl_sec = heartbeat_ttl_sec
        store.connection.executescript(WORKFLOW_SCHEMA)
        store.durable_barrier()

    # ---- model ----
    def create_workflow(self, goal: str, project_id: str | None = None) -> dict[str, Any]:
        workflow_id = f"wf-{uuid.uuid4()}"
        now = utc_now()
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO wf_runs(workflow_id,project_id,goal,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (workflow_id, project_id, goal, "RUNNING", now, now),
            )
        self._barrier()
        return {"workflow_id": workflow_id, "goal": goal, "status": "RUNNING"}

    def add_step(self, workflow_id: str, name: str, kind: str = "WORK", *, depends_on: list[str] | None = None,
                 retry_budget: int = 3) -> dict[str, Any]:
        step_id = f"step-{uuid.uuid4()}"
        now = utc_now()
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO wf_steps(step_id,workflow_id,name,kind,status,depends_on_json,attempt,retry_budget,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (step_id, workflow_id, name, kind, STEP_READY,
                 canonical_json([self._scoped(workflow_id, d) for d in (depends_on or [])]),
                 0, retry_budget, now, now),
            )
        self._barrier()
        return {"step_id": step_id, "workflow_id": workflow_id, "name": name, "status": STEP_READY}

    def _scoped(self, workflow_id: str, raw: str) -> str:
        # allow either a full step_id or a short name joined by workflow prefix
        return raw if raw.startswith("step-") else f"{workflow_id}:{raw}"

    # ---- claim (fenced, atomic) ----
    def claim_step(self, step_id: str, *, owner: str, process_start_identity: str) -> dict[str, Any]:
        now = time.time()
        with self.store.transaction() as conn:
            row = conn.execute("SELECT * FROM wf_steps WHERE step_id=?", (step_id,)).fetchone()
            if not row:
                raise WorkflowError("step not found")
            try:
                deps = json.loads(row["depends_on_json"])
            except ValueError:
                deps = []
            if row["status"] not in (STEP_READY, STEP_REWORK):
                raise StepNotClaimable(f"step {step_id} is {row['status']}; cannot claim")
            for dep in deps:
                dep_id = dep.split(":", 1)[1] if ":" in dep else dep
                drow = conn.execute("SELECT status FROM wf_steps WHERE step_id=?", (dep_id,)).fetchone()
                if not drow or drow["status"] != STEP_DONE:
                    raise StepNotClaimable(f"step {step_id} dependency {dep_id} not DONE")
            fence = f"{owner}::{process_start_identity}"
            conn.execute(
                "UPDATE wf_steps SET status=?,claimed_by=?,claim_ts=?,heartbeat_ts=?,updated_at=? WHERE step_id=?",
                (STEP_CLAIMED, fence, now, now, utc_now(), step_id),
            )
        self._barrier()
        return {"step_id": step_id, "status": STEP_CLAIMED, "claim": fence, "attempt": row["attempt"]}

    def heartbeat(self, step_id: str, *, fence: str) -> None:
        with self.store.transaction() as conn:
            row = conn.execute("SELECT claimed_by FROM wf_steps WHERE step_id=?", (step_id,)).fetchone()
            if not row or row["claimed_by"] != fence:
                raise FenceMismatch("heartbeat owner mismatch")
            conn.execute(
                "UPDATE wf_steps SET heartbeat_ts=? WHERE step_id=? AND claimed_by=?",
                (time.time(), step_id, fence),
            )
        self._barrier()

    # ---- finish (outcome -> transition) ----
    def finish_step(self, step_id: str, *, fence: str, outcome: dict[str, Any]) -> dict[str, Any]:
        kind = outcome.get("kind")
        if kind not in OUTCOME_KINDS:
            kind = OUTCOME_UNKNOWN
        now = utc_now()
        with self.store.transaction() as conn:
            row = conn.execute("SELECT * FROM wf_steps WHERE step_id=?", (step_id,)).fetchone()
            if not row or row["claimed_by"] != fence or row["status"] != STEP_CLAIMED:
                raise FenceMismatch("step not claimed by this fence")
            if kind == OUTCOME_DONE:
                new_status = STEP_DONE
                block_reason = None
            elif kind == OUTCOME_REWORK:
                new_attempt = int(row["attempt"]) + 1
                if new_attempt > int(row["retry_budget"]):
                    new_status = STEP_BLOCKED
                    block_reason = canonical_json(outcome.get("findings", []))
                else:
                    new_status = STEP_REWORK
                    block_reason = None
                conn.execute("UPDATE wf_steps SET attempt=?,claimed_by=NULL,claim_ts=NULL,heartbeat_ts=NULL WHERE step_id=?", (new_attempt, step_id))
            elif kind == OUTCOME_WAIT:
                new_status = STEP_WAITING
                block_reason = None
            else:  # UNKNOWN and any malformed outcome -> fail-closed BLOCKED
                new_status = STEP_BLOCKED
                block_reason = canonical_json({"reason": "fail-closed: unknown/malformed worker outcome", "outcome": outcome})
            conn.execute(
                "UPDATE wf_steps SET status=?,block_reason=?,outcome_json=?,claimed_by=NULL,claim_ts=NULL,heartbeat_ts=NULL,updated_at=? WHERE step_id=?",
                (new_status, block_reason, canonical_json(outcome), now, step_id),
            )
        self._barrier()
        return {"step_id": step_id, "status": new_status}

    def resume_wait(self, step_id: str, *, owner: str, process_start_identity: str) -> dict[str, Any]:
        """A WAITING step may be resumed (claim again) once its external result
        is ready; this is how a bounded WAIT returns to the REWORK/READY line."""
        with self.store.transaction() as conn:
            row = conn.execute("SELECT status FROM wf_steps WHERE step_id=?", (step_id,)).fetchone()
            if not row or row["status"] != STEP_WAITING:
                raise WorkflowError("only a WAITING step may be resumed")
            conn.execute(
                "UPDATE wf_steps SET status=?,block_reason=NULL WHERE step_id=?",
                (STEP_READY, step_id),
            )
        self._barrier()
        return self.claim_step(step_id, owner=owner, process_start_identity=process_start_identity)

    # ---- scheduler (non-blocking) ----
    def next_runnable(self, workflow_id: str) -> list[dict[str, Any]]:
        rows = [
            dict(row)
            for row in self.store.connection.execute(
                "SELECT * FROM wf_steps WHERE workflow_id=? ORDER BY created_at", (workflow_id,)
            )
        ]
        done = {r["step_id"] for r in rows if r["status"] == STEP_DONE}
        runnable = []
        for r in rows:
            if r["status"] not in (STEP_READY, STEP_REWORK):
                continue
            try:
                deps = json.loads(r["depends_on_json"])
            except ValueError:
                deps = []
            if all(_dep_step_id(d) in done for d in deps):
                runnable.append(r)
        return runnable

    # ---- crash reconciliation (idempotent resume) ----
    def reconcile(self, *, owner: str, process_start_identity: str) -> dict[str, Any]:
        """Any step CLAIMED by a live-but-stale heartbeat is released back to READY
        so a crash can resume. Claims owned by the current caller are left intact."""
        stale_before = time.time() - self.heartbeat_ttl_sec
        fence = f"{owner}::{process_start_identity}"
        reclaimed = []
        with self.store.transaction() as conn:
            for row in conn.execute(
                "SELECT step_id,claimed_by,heartbeat_ts FROM wf_steps WHERE status=?",
                (STEP_CLAIMED,),
            ):
                if row["claimed_by"] == fence:
                    continue  # our own live claim
                hb = row["heartbeat_ts"] or 0
                if hb < stale_before:
                    conn.execute(
                        "UPDATE wf_steps SET status=?,claimed_by=NULL,claim_ts=NULL,heartbeat_ts=NULL,updated_at=? WHERE step_id=? AND status=?",
                        (STEP_READY, utc_now(), row["step_id"], STEP_CLAIMED),
                    )
                    reclaimed.append(row["step_id"])
        self._barrier()
        return {"reclaimed": reclaimed}

    def run_status(self, workflow_id: str) -> dict[str, Any]:
        steps = [
            dict(row)
            for row in self.store.connection.execute(
                "SELECT step_id,name,kind,status,attempt,retry_budget,block_reason FROM wf_steps WHERE workflow_id=?", (workflow_id,)
            )
        ]
        return {
            "workflow_id": workflow_id,
            "steps": [{"step_id": s["step_id"], "name": s["name"], "kind": s["kind"], "status": s["status"],
                       "attempt": s["attempt"], "retry_budget": s["retry_budget"], "block_reason": s["block_reason"]} for s in steps],
            "done": sum(1 for s in steps if s["status"] == STEP_DONE),
            "waiting": sum(1 for s in steps if s["status"] == STEP_WAITING),
            "blocked": sum(1 for s in steps if s["status"] == STEP_BLOCKED),
        }

    def _barrier(self) -> None:
        self.store.durable_barrier()


def _dep_step_id(dep: str) -> str:
    return dep.split(":", 1)[1] if ":" in dep else dep


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")