from __future__ import annotations

"""M2 user-directive durable-first control gate.

A user control instruction (PAUSE / STOP / RESUME / CHANGE_SCOPE / USER_OVERRIDE)
must be DURABLY committed to canonical storage BEFORE it is applied to
scheduling, so that an in-flight NEXT_ACTION can never override a fresh user
directive, and so a crash between "user said stop" and "work actually stops"
does not lose the directive.

Gate semantics (used by the scheduler before dispatching any new work):
  - a PENDING directive in {PAUSE, STOP, CHANGE_SCOPE} blocks new dispatch;
  - RESUME / USER_OVERRIDE are recorded and applied but do not by themselves
    block; applying USER_OVERRIDE is what re-enables a previously BLOCKED path.
"""

import json
import uuid
from typing import Any

from .store import ControlStore
from .util import canonical_json, sha256_text, utc_now

DIRECTIVE_SCHEMA = """
CREATE TABLE IF NOT EXISTS ctl_directives (
  directive_id TEXT PRIMARY KEY,
  scope_id TEXT NOT NULL,
  action TEXT NOT NULL,
  note TEXT,
  state_revision_at_commit INTEGER NOT NULL,
  directive_hash TEXT NOT NULL,
  committed_at TEXT NOT NULL,
  applied_at TEXT,
  status TEXT NOT NULL
);
"""

VALID_ACTIONS = ("PAUSE", "STOP", "RESUME", "CHANGE_SCOPE", "USER_OVERRIDE")
GATING_ACTIONS = ("PAUSE", "STOP", "CHANGE_SCOPE")
STATUS_PENDING = "PENDING"
STATUS_APPLIED = "APPLIED"


class DirectiveError(RuntimeError):
    pass


def _ensure_schema(store: ControlStore) -> None:
    store.connection.executescript(DIRECTIVE_SCHEMA)
    store.durable_barrier()


def commit_directive(
    store: ControlStore, *, task_id: str, action: str, note: str = ""
) -> dict[str, Any]:
    """Durably record a user directive BEFORE any transition is applied."""
    if action not in VALID_ACTIONS:
        raise DirectiveError(f"invalid directive action: {action}")
    _ensure_schema(store)
    directive_id = f"directive-{uuid.uuid4()}"
    revision = store.state_head()
    core = {
        "directive_id": directive_id,
        "scope_id": task_id,
        "action": action,
        "note": note,
        "state_revision_at_commit": revision,
    }
    directive_hash = sha256_text(canonical_json(core))
    now = utc_now()
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO ctl_directives(directive_id,scope_id,action,note,state_revision_at_commit,directive_hash,committed_at,status) VALUES(?,?,?,?,?,?,?,?)",
            (directive_id, task_id, action, note, revision, directive_hash, now, STATUS_PENDING),
        )
    store.durable_barrier()
    return {
        "directive_id": directive_id,
        "task_id": task_id,
        "action": action,
        "note": note,
        "state_revision_at_commit": revision,
        "directive_hash": directive_hash,
        "committed_at": now,
        "status": STATUS_PENDING,
    }


def pending_directives(store: ControlStore, *, task_id: str) -> list[dict[str, Any]]:
    _ensure_schema(store)
    rows = store.connection.execute(
        "SELECT * FROM ctl_directives WHERE scope_id=? AND status=? ORDER BY committed_at",
        (task_id, STATUS_PENDING),
    ).fetchall()
    return [dict(row) for row in rows]


def apply_directive(store: ControlStore, *, directive_id: str) -> dict[str, Any]:
    """Mark a committed directive as APPLIED (the caller then performs the
    actual transition). Refused if not PENDING."""
    row = store.connection.execute(
        "SELECT * FROM ctl_directives WHERE directive_id=?", (directive_id,)
    ).fetchone()
    if not row:
        raise DirectiveError("directive not found")
    if row["status"] != STATUS_PENDING:
        raise DirectiveError("directive is not PENDING")
    with store.transaction() as conn:
        conn.execute(
            "UPDATE ctl_directives SET status=?,applied_at=? WHERE directive_id=?",
            (STATUS_APPLIED, utc_now(), directive_id),
        )
    store.durable_barrier()
    value = dict(row)
    value["status"] = STATUS_APPLIED
    return value


def has_work_gate(store: ControlStore, *, task_id: str) -> tuple[bool, str]:
    """Return (blocked, reason) — a PENDING PAUSE/STOP/CHANGE_SCOPE directive
    means the scheduler must not dispatch new work for this task."""
    for directive in pending_directives(store, task_id=task_id):
        if directive["action"] in GATING_ACTIONS:
            return True, f"pending user directive {directive['action']}"
    return False, ""