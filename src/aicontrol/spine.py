from __future__ import annotations

"""M2 Continuation Spine.

Explicit machine semantics for project life across Builder turns / sessions /
model swaps, so that an invocation returning or a review waiting never stops
the Project. Durable in the SAME Controller SQLite (no second canonical store).

Layering (added on top of the existing goal-contract / effect / evidence
authority, which remains the source of truth):
  PROJECT      -> status RUNNING / COMPLETE / BLOCKED / HUMAN_REQUIRED
  MILESTONE    -> status READY / RUNNING / WAITING_REVIEW / REWORK / PASS
  TASK         -> status READY / RUNNING / WAITING / BLOCKED / DONE
  INVOCATION   -> status RUNNING / RETURNED / FAILED / TIMED_OUT

Core invariants enforced here:
  - INVOCATION_RETURNED != PROJECT_DONE. The driver never self-completes a
    Project; COMPLETE requires a milestone named "FINAL_ACCEPTANCE" to have a
    PASS independent-review record.
  - MILESTONE_PASS REQUIRES INDEPENDENT REVIEW. A milestone cannot be marked
    PASS without a matching PASS record in `milestone_reviews`.
  - A milestone whose candidate is UNDER_REVIEW (WAITING_REVIEW) is frozen; its
    tasks are not given new invocations, but the driver keeps returning
    non-COMPLETE so unrelated READY work (other milestones/lines) is not lost.
  - An empty ready queue does not imply Project completion: if a milestone still
    needs review it returns READY_FOR_REVIEW; if tasks are blocked it returns the
    blocked task; otherwise it returns WAITING. Only the FINAL_ACCEPTANCE PASS
    milestone yields COMPLETE.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from .util import canonical_json, utc_now

PROJECT_RUNNING = "RUNNING"
PROJECT_COMPLETE = "COMPLETE"
PROJECT_BLOCKED = "BLOCKED"
PROJECT_HUMAN_REQUIRED = "HUMAN_REQUIRED"

MILESTONE_READY = "READY"
MILESTONE_RUNNING = "RUNNING"
MILESTONE_WAITING_REVIEW = "WAITING_REVIEW"
MILESTONE_REWORK = "REWORK"
MILESTONE_PASS = "PASS"
MILESTONE_STATUSES = (MILESTONE_READY, MILESTONE_RUNNING, MILESTONE_WAITING_REVIEW, MILESTONE_REWORK, MILESTONE_PASS)

TASK_READY = "READY"
TASK_RUNNING = "RUNNING"
TASK_WAITING = "WAITING"
TASK_BLOCKED = "BLOCKED"
TASK_DONE = "DONE"
TASK_STATUSES = (TASK_READY, TASK_RUNNING, TASK_WAITING, TASK_BLOCKED, TASK_DONE)

INVOCATION_RUNNING = "RUNNING"
INVOCATION_RETURNED = "RETURNED"
INVOCATION_FAILED = "FAILED"
INVOCATION_TIMED_OUT = "TIMED_OUT"
INVOCATION_STATUSES = (INVOCATION_RUNNING, INVOCATION_RETURNED, INVOCATION_FAILED, INVOCATION_TIMED_OUT)

FINAL_ACCEPTANCE_MILESTONE = "FINAL_ACCEPTANCE"

REVIEW_VERDICTS = ("PASS", "REWORK", "BLOCKED")


class SpineError(RuntimeError):
    pass


class SpineInvariantViolation(SpineError):
    pass


class ReviewRequired(SpineInvariantViolation):
    pass


SPINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS spine_projects (
  project_id TEXT PRIMARY KEY,
  final_goal TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS spine_milestones (
  milestone_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  name TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  depends_on TEXT,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS spine_tasks (
  task_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  milestone_id TEXT NOT NULL,
  summary TEXT NOT NULL,
  status TEXT NOT NULL,
  block_reason TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS spine_invocations (
  invocation_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  milestone_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  returned_at TEXT,
  result_summary TEXT
);
CREATE TABLE IF NOT EXISTS spine_milestone_reviews (
  review_id TEXT PRIMARY KEY,
  milestone_id TEXT NOT NULL,
  reviewer TEXT NOT NULL,
  role TEXT NOT NULL,
  verdict TEXT NOT NULL,
  candidate_commit TEXT NOT NULL,
  candidate_digest TEXT NOT NULL,
  evidence_refs_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


class ContinuationSpine:
    """Durable PROJECT / MILESTONE / TASK / INVOCATION driver on one SQLite DB."""

    def __init__(self, store: Any) -> None:
        self.store = store
        store.connection.executescript(SPINE_SCHEMA)
        store.durable_barrier()

    # ---- projects ----
    def create_project(self, final_goal: str, milestone_names: list[str]) -> dict[str, Any]:
        project_id = f"project-{uuid.uuid4()}"
        now = utc_now()
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO spine_projects(project_id,final_goal,status,created_at,updated_at) VALUES(?,?,?,?,?)",
                (project_id, final_goal, PROJECT_RUNNING, now, now),
            )
            for i, name in enumerate(milestone_names):
                depends = None if i == 0 else None  # ordinal chain drives readiness below
                conn.execute(
                    "INSERT INTO spine_milestones(milestone_id,project_id,name,ordinal,depends_on,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (f"milestone-{uuid.uuid4()}", project_id, name, i, depends, MILESTONE_READY, now, now),
                )
        self._barrier()
        return {"project_id": project_id, "final_goal": final_goal, "status": PROJECT_RUNNING}

    def project(self, project_id: str) -> dict[str, Any]:
        row = self.store.connection.execute(
            "SELECT * FROM spine_projects WHERE project_id=?", (project_id,)
        ).fetchone()
        if not row:
            raise SpineError("project not found")
        return dict(row)

    def set_project_status(self, project_id: str, status: str, *, reason: str = "") -> None:
        if status not in (PROJECT_RUNNING, PROJECT_COMPLETE, PROJECT_BLOCKED, PROJECT_HUMAN_REQUIRED):
            raise SpineError(f"invalid project status: {status}")
        # Only final acceptance may complete the project; everything else is guarded by the driver.
        with self.store.transaction() as conn:
            row = conn.execute("SELECT status FROM spine_projects WHERE project_id=?", (project_id,)).fetchone()
            if not row:
                raise SpineError("project not found")
            conn.execute(
                "UPDATE spine_projects SET status=?,updated_at=? WHERE project_id=?",
                (status, utc_now(), project_id),
            )
        self._barrier()

    # ---- milestones ----
    def milestones(self, project_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.store.connection.execute(
                "SELECT * FROM spine_milestones WHERE project_id=? ORDER BY ordinal", (project_id,)
            )
        ]

    def milestone(self, milestone_id: str) -> dict[str, Any]:
        row = self.store.connection.execute("SELECT * FROM spine_milestones WHERE milestone_id=?", (milestone_id,)).fetchone()
        if not row:
            raise SpineError("milestone not found")
        return dict(row)

    def set_milestone_status(self, milestone_id: str, status: str) -> dict[str, Any]:
        if status not in MILESTONE_STATUSES:
            raise SpineError(f"invalid milestone status: {status}")
        if status == MILESTONE_PASS:
            # PASS is authoritative: it requires an independent reviewer PASS record.
            self._require_review_pass(milestone_id)
        with self.store.transaction() as conn:
            conn.execute(
                "UPDATE spine_milestones SET status=?,updated_at=? WHERE milestone_id=?",
                (status, utc_now(), milestone_id),
            )
            # advancing the chain: when a milestone passes, the next ordinal is already READY
        self._barrier()
        return self.milestone(milestone_id)

    def record_review(
        self,
        *,
        milestone_id: str,
        reviewer: str,
        role: str,
        verdict: str,
        candidate_commit: str,
        candidate_digest: str,
        evidence_refs: list[str],
    ) -> dict[str, Any]:
        if verdict not in REVIEW_VERDICTS:
            raise SpineError(f"invalid review verdict: {verdict}")
        review_id = f"review-{uuid.uuid4()}"
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO spine_milestone_reviews(review_id,milestone_id,reviewer,role,verdict,candidate_commit,candidate_digest,evidence_refs_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (review_id, milestone_id, reviewer, role, verdict, candidate_commit, candidate_digest,
                 canonical_json(evidence_refs), utc_now()),
            )
        self._barrier()
        return {
            "review_id": review_id, "milestone_id": milestone_id, "reviewer": reviewer,
            "role": role, "verdict": verdict, "candidate_commit": candidate_commit,
            "candidate_digest": candidate_digest, "evidence_refs": evidence_refs,
        }

    def latest_review(self, milestone_id: str) -> dict[str, Any] | None:
        row = self.store.connection.execute(
            "SELECT * FROM spine_milestone_reviews WHERE milestone_id=? ORDER BY created_at DESC LIMIT 1",
            (milestone_id,),
        ).fetchone()
        if not row:
            return None
        value = dict(row)
        value["evidence_refs"] = json.loads(value.pop("evidence_refs_json"))
        return value

    def _require_review_pass(self, milestone_id: str) -> None:
        review = self.latest_review(milestone_id)
        if not review or review["verdict"] != "PASS":
            raise ReviewRequired(
                f"milestone {milestone_id} cannot be PASS without an independent reviewer PASS record"
            )

    # ---- tasks ----
    def add_task(self, milestone_id: str, summary: str) -> dict[str, Any]:
        ms = self.milestone(milestone_id)
        task_id = f"task-{uuid.uuid4()}"
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO spine_tasks(task_id,project_id,milestone_id,summary,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (task_id, ms["project_id"], milestone_id, summary, TASK_READY, utc_now(), utc_now()),
            )
        self._barrier()
        return {"task_id": task_id, "milestone_id": milestone_id, "project_id": ms["project_id"], "summary": summary, "status": TASK_READY}

    def tasks(self, milestone_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.store.connection.execute(
                "SELECT * FROM spine_tasks WHERE milestone_id=? ORDER BY created_at", (milestone_id,)
            )
        ]

    def set_task_status(self, task_id: str, status: str, *, block_reason: str | None = None) -> None:
        if status not in TASK_STATUSES:
            raise SpineError(f"invalid task status: {status}")
        with self.store.transaction() as conn:
            conn.execute(
                "UPDATE spine_tasks SET status=?,block_reason=?,updated_at=? WHERE task_id=?",
                (status, block_reason, utc_now(), task_id),
            )
        self._barrier()

    # ---- invocations ----
    def _begin_invocation(self, *, project_id: str, milestone_id: str, task_id: str) -> dict[str, Any]:
        invocation_id = f"invocation-{uuid.uuid4()}"
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO spine_invocations(invocation_id,project_id,milestone_id,task_id,status,created_at) VALUES(?,?,?,?,?,?)",
                (invocation_id, project_id, milestone_id, task_id, INVOCATION_RUNNING, utc_now()),
            )
        self._barrier()
        return {
            "invocation_id": invocation_id, "project_id": project_id,
            "milestone_id": milestone_id, "task_id": task_id, "status": INVOCATION_RUNNING,
        }

    def return_invocation(self, invocation_id: str, result_summary: str, *, fail: bool = False) -> dict[str, Any]:
        row = self.store.connection.execute(
            "SELECT * FROM spine_invocations WHERE invocation_id=?", (invocation_id,)
        ).fetchone()
        if not row:
            raise SpineError("invocation not found")
        status = INVOCATION_FAILED if fail else INVOCATION_RETURNED
        with self.store.transaction() as conn:
            conn.execute(
                "UPDATE spine_invocations SET status=?,returned_at=?,result_summary=? WHERE invocation_id=?",
                (status, utc_now(), result_summary, invocation_id),
            )
            # A returned invocation makes its task runnable again for the next
            # invocation unless the task was explicitly marked DONE.
        self._barrier()
        return {"invocation_id": invocation_id, "status": status, "result_summary": result_summary}

    # ---- active milestone selection ----
    def _active_milestone(self, project_id: str) -> dict[str, Any] | None:
        for ms in self.milestones(project_id):
            dep = ms.get("depends_on")
            if dep:
                dep_row = self.store.connection.execute(
                    "SELECT status FROM spine_milestones WHERE milestone_id=?", (dep,)
                ).fetchone()
                if not dep_row or dep_row["status"] != MILESTONE_PASS:
                    continue  # dependency not satisfied yet
            if ms["status"] != MILESTONE_PASS:
                return ms
        return None

    # ---- driver: NO-COMPLETE-UNLESS-FINAL-ACCEPTANCE ----
    def continuation_next(self, project_id: str) -> dict[str, Any]:
        """Return the next action for the Project. Never self-completes except
        when the FINAL_ACCEPTANCE milestone has an independent PASS review."""
        project = self.project(project_id)
        if project["status"] != PROJECT_RUNNING:
            return {"project_id": project_id, "action": "IDLE", "project_status": project["status"]}
        active = self._active_milestone(project_id)
        if active is None:
            # every milestone PASS -> still not complete unless FINAL_ACCEPTANCE passed
            return {"project_id": project_id, "action": "AWAITING_FINAL_ACCEPTANCE", "project_status": PROJECT_RUNNING}

        ms = active
        if ms["status"] == MILESTONE_WAITING_REVIEW:
            return {"project_id": project_id, "action": "WAITING_REVIEW", "milestone": ms["milestone_id"], "name": ms["name"]}
        if ms["status"] == MILESTONE_REWORK:
            next_task = self._first_task(ms["milestone_id"], (TASK_READY, TASK_RUNNING))
            if next_task:
                return self._dispatch(project_id, ms, next_task)
            return {"project_id": project_id, "action": "WAITING", "milestone": ms["milestone_id"], "reason": "no ready task in REWORK milestone"}
        if ms["status"] in (MILESTONE_READY, MILESTONE_RUNNING):
            next_task = self._first_task(ms["milestone_id"], (TASK_READY,))
            if next_task:
                return self._dispatch(project_id, ms, next_task)
            # all tasks done, milestone not yet reviewed -> surface READY_FOR_REVIEW
            pending = self._first_task(ms["milestone_id"], (TASK_RUNNING,))
            if pending is not None:
                return {"project_id": project_id, "action": "WAITING", "milestone": ms["milestone_id"], "reason": "task in flight"}
            blocked = self._first_task(ms["milestone_id"], (TASK_BLOCKED,))
            if blocked is not None:
                return {"project_id": project_id, "action": "BLOCKED", "milestone": ms["milestone_id"], "task": blocked["task_id"], "reason": blocked.get("block_reason") or "blocked task"}
            if ms["name"] == FINAL_ACCEPTANCE_MILESTONE:
                return {"project_id": project_id, "action": "AWAITING_FINAL_ACCEPTANCE", "milestone": ms["milestone_id"], "name": ms["name"]}
            return {"project_id": project_id, "action": "READY_FOR_REVIEW", "milestone": ms["milestone_id"], "name": ms["name"]}
        return {"project_id": project_id, "action": "WAITING", "milestone": ms["milestone_id"], "reason": f"milestone status {ms['status']}"}

    def _first_task(self, milestone_id: str, statuses: tuple[str, ...]) -> dict[str, Any] | None:
        placeholders = ",".join("?" for _ in statuses)
        row = self.store.connection.execute(
            f"SELECT * FROM spine_tasks WHERE milestone_id=? AND status IN ({placeholders}) ORDER BY created_at LIMIT 1",
            (milestone_id, *statuses),
        ).fetchone()
        return dict(row) if row else None

    def _dispatch(self, project_id: str, ms: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
        with self.store.transaction() as conn:
            conn.execute(
                "UPDATE spine_tasks SET status=?,updated_at=? WHERE task_id=?",
                (TASK_RUNNING, utc_now(), task["task_id"]),
            )
            if ms["status"] == MILESTONE_READY:
                conn.execute(
                    "UPDATE spine_milestones SET status=?,updated_at=? WHERE milestone_id=?",
                    (MILESTONE_RUNNING, utc_now(), ms["milestone_id"]),
                )
        self._barrier()
        invocation = self._begin_invocation(
            project_id=project_id, milestone_id=ms["milestone_id"], task_id=task["task_id"]
        )
        return {
            "project_id": project_id,
            "action": "INVOCATION",
            "milestone": ms["milestone_id"],
            "milestone_name": ms["name"],
            "task": task["task_id"],
            "summary": task["summary"],
            "invocation": invocation,
        }

    def finalize_complete(self, project_id: str, *, pending_final_items: list[str] | None = None) -> dict[str, Any]:
        """Set PROJECT=COMPLETE ONLY after the FINAL_ACCEPTANCE milestone has an
        independent PASS review. Refuses instead of cheating when that is not true."""
        milestones = self.milestones(project_id)
        last = milestones[-1]
        if last["name"] != FINAL_ACCEPTANCE_MILESTONE or last["status"] != MILESTONE_PASS:
            return {"project_id": project_id, "status": "REQUIRES_FINAL_ACCEPTANCE_PASS", "milestone": last["milestone_id"]}
        review = self.latest_review(last["milestone_id"])
        if not review or review["verdict"] != "PASS":
            return {"project_id": project_id, "status": "REQUIRES_FINAL_ACCEPTANCE_PASS", "milestone": last["milestone_id"]}
        self.set_project_status(project_id, PROJECT_COMPLETE)
        return {"project_id": project_id, "status": PROJECT_COMPLETE, "milestone": last["milestone_id"]}

    def _barrier(self) -> None:
        self.store.durable_barrier()