from __future__ import annotations

"""M2/M5 durable Stable / Candidate lineage.

Keeps CURRENT_STABLE separate from CURRENT_DEVELOPMENT / CANDIDATE so a failed
development Candidate never breaks the Stable line, and every promotion /
rollback is traceable and revertible.

Invariants enforced here:
  - a Candidate becomes STABLE only with an INDEPENDENT review PASS; otherwise
    promotion fails closed (never self-promoted by this builder).
  - exactly ONE STABLE record is current (status='STABLE'); the rest are
    SUPERSEDED / ROLLED_BACK.
  - a STABLE can be rolled back to a previous STABLE that has not itself been
    rolled back; the failed version is durably marked ROLLED_BACK.
  - lineage is queryable by version / parent / commit / tree digest / state.
"""

import json
import uuid
from typing import Any

from .store import ControlStore
from .util import canonical_json, utc_now

KIND_CANDIDATE = "CANDIDATE"
KIND_STABLE = "STABLE"
KIND_ROLLBACK = "ROLLBACK_AUDIT"

STATUS_STABLE = "STABLE"           # the single current stable
STATUS_SUPERSEDED = "SUPERSEDED"   # an older stable
STATUS_ROLLED_BACK = "ROLLED_BACK" # a stable that was demoted
STATUS_CANDIDATE = "CANDIDATE"

LINEAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS stable_lineage (
  record_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  version INTEGER NOT NULL,
  controller_commit TEXT NOT NULL,
  tree_digest TEXT NOT NULL,
  parent_version INTEGER,
  status TEXT NOT NULL,
  review_verdict TEXT,
  reviewer TEXT,
  known_limitations_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


class LineageError(RuntimeError):
    pass


class PromotionRequiresReview(LineageError):
    pass


def _ensure_schema(store: ControlStore) -> None:
    store.connection.executescript(LINEAGE_SCHEMA)
    store.durable_barrier()


class StableLineage:
    def __init__(self, store: ControlStore) -> None:
        self.store = store
        _ensure_schema(store)

    def _next_version(self) -> int:
        row = self.store.connection.execute("SELECT MAX(version) AS v FROM stable_lineage").fetchone()
        return int(row["v"] or 0) + 1

    def current_stable(self) -> dict[str, Any] | None:
        row = self.store.connection.execute(
            "SELECT * FROM stable_lineage WHERE kind=? AND status=? ORDER BY version DESC LIMIT 1",
            (KIND_STABLE, STATUS_STABLE),
        ).fetchone()
        if not row:
            return None
        return dict(row)

    def create_candidate(self, *, controller_commit: str, tree_digest: str,
                         known_limitations: list[str] | None = None) -> dict[str, Any]:
        rec_id = f"lineage-{uuid.uuid4()}"
        version = self._next_version()
        parent = self.current_stable()
        parent_version = parent["version"] if parent else None
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO stable_lineage(record_id,kind,version,controller_commit,tree_digest,parent_version,status,review_verdict,reviewer,known_limitations_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (rec_id, KIND_CANDIDATE, version, controller_commit, tree_digest, parent_version,
                 STATUS_CANDIDATE, None, None, canonical_json(known_limitations or []), utc_now()),
            )
        self.store.durable_barrier()
        return dict(self.store.connection.execute(
            "SELECT * FROM stable_lineage WHERE record_id=?", (rec_id,)
        ).fetchone())

    def promote(self, record_id: str, *, independent_review: dict[str, Any]) -> dict[str, Any]:
        """Promote a Candidate to STABLE only with an independent review PASS."""
        verdict = str(independent_review.get("verdict", "")).upper()
        reviewer = independent_review.get("reviewer", "")
        if verdict != "PASS":
            raise PromotionRequiresReview("Stable promotion requires an independent review PASS")
        with self.store.transaction() as conn:
            row = conn.execute("SELECT * FROM stable_lineage WHERE record_id=?", (record_id,)).fetchone()
            if not row or row["kind"] != KIND_CANDIDATE or row["status"] != STATUS_CANDIDATE:
                raise LineageError("only an ACTIVE Candidate can be promoted")
            # demote the current stable
            conn.execute(
                "UPDATE stable_lineage SET status=? WHERE kind=? AND status=?",
                (STATUS_SUPERSEDED, KIND_STABLE, STATUS_STABLE),
            )
            conn.execute(
                "UPDATE stable_lineage SET kind=?,status=?,review_verdict=?,reviewer=? WHERE record_id=?",
                (KIND_STABLE, STATUS_STABLE, verdict, reviewer, record_id),
            )
        self.store.durable_barrier()
        return dict(self.store.connection.execute(
            "SELECT * FROM stable_lineage WHERE record_id=?", (record_id,)
        ).fetchone())

    def rollback(self, stable_version: int, *, reason: str) -> dict[str, Any]:
        """Roll CURRENT_STABLE back to an earlier STABLE that never failed."""
        with self.store.transaction() as conn:
            target = conn.execute(
                "SELECT * FROM stable_lineage WHERE kind=? AND status=? AND version=?",
                (KIND_STABLE, STATUS_STABLE, stable_version),
            ).fetchone()
            if not target:
                raise LineageError("no CURRENT_STABLE at the requested version to roll back")
            # newest previous STABLE-kind record that has not already been rolled back
            prev = conn.execute(
                "SELECT * FROM stable_lineage WHERE kind=? AND version<? AND status<>? ORDER BY version DESC LIMIT 1",
                (KIND_STABLE, stable_version, STATUS_ROLLED_BACK),
            ).fetchone()
            if not prev:
                raise LineageError("no previous Stable to restore; cannot roll back")
            conn.execute(
                "UPDATE stable_lineage SET status=? WHERE record_id=?",
                (STATUS_ROLLED_BACK, target["record_id"]),
            )
            conn.execute(
                "UPDATE stable_lineage SET status=? WHERE record_id=?",
                (STATUS_STABLE, prev["record_id"]),
            )
            conn.execute(
                "INSERT INTO stable_lineage(record_id,kind,version,controller_commit,tree_digest,parent_version,status,review_verdict,reviewer,known_limitations_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (f"lineage-{uuid.uuid4()}", KIND_ROLLBACK, self._next_version() + 1,
                 target["controller_commit"], target["tree_digest"], stable_version,
                 "AUDIT", None, None, canonical_json([reason]), utc_now()),
            )
        self.store.durable_barrier()
        return {"rolled_back_stable": stable_version, "current_stable": self.current_stable()}

    def lineage(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.store.connection.execute(
                "SELECT * FROM stable_lineage ORDER BY version"
            )
        ]