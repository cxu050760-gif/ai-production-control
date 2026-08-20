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




VOUCHER_SCHEMA = '''
CREATE TABLE IF NOT EXISTS review_vouchers (
  voucher_id TEXT PRIMARY KEY,
  candidate_record_id TEXT NOT NULL UNIQUE,
  reviewer_identity TEXT NOT NULL,
  reviewer_role TEXT NOT NULL,
  controller_commit TEXT NOT NULL,
  tree_digest TEXT NOT NULL,
  delivered_digest TEXT NOT NULL,
  verdict TEXT NOT NULL,
  created_at TEXT NOT NULL
);
'''


REVIEW_SCHEMA = '''CREATE TABLE IF NOT EXISTS review_records (
  review_record_id TEXT PRIMARY KEY,
  candidate_record_id TEXT NOT NULL,
  reviewer_identity TEXT NOT NULL,
  verdict TEXT NOT NULL,
  review_source TEXT NOT NULL,
  controller_commit TEXT NOT NULL,
  tree_digest TEXT NOT NULL,
  delivered_digest TEXT NOT NULL,
  created_at TEXT NOT NULL
);'''


class LineageError(RuntimeError):
    pass


class PromotionRequiresReview(LineageError):
    pass


def _ensure_schema(store: ControlStore) -> None:
    store.connection.executescript(LINEAGE_SCHEMA + "\n" + VOUCHER_SCHEMA + "\n" + REVIEW_SCHEMA)
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


    def get_candidate(self, record_id: str) -> dict[str, Any] | None:
        row = self.store.connection.execute(
            "SELECT * FROM stable_lineage WHERE record_id=? AND kind=?",
            (record_id, KIND_CANDIDATE),
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _parsed_delivered(candidate: dict[str, Any]) -> str | None:
        for entry in json.loads(candidate.get("known_limitations_json") or "[]"):
            if isinstance(entry, str) and entry.startswith("delivered_sha256="):
                return entry.split("=", 1)[1]
        return None

    def issue_voucher(self, *, candidate_record_id: str, reviewer_identity: str,
                      reviewer_role: str, delivered_digest: str) -> dict[str, Any]:
        cand = self.get_candidate(candidate_record_id)
        if not cand or cand["status"] != STATUS_CANDIDATE:
            raise LineageError("cannot voucher a non-active Candidate")
        if str(reviewer_role or "").upper() != "R_PROD":
            raise PromotionRequiresReview("independent review must come from an R_PROD reviewer")
        stored = self._parsed_delivered(cand)
        if stored is None or delivered_digest != stored:
            raise LineageError("review voucher delivered_digest does not match the Candidate release digest")
        vid = f"voucher-{uuid.uuid4()}"
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO review_vouchers(voucher_id,candidate_record_id,reviewer_identity,reviewer_role,controller_commit,tree_digest,delivered_digest,verdict,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (vid, cand["record_id"], reviewer_identity, str(reviewer_role).upper(),
                 cand["controller_commit"], cand["tree_digest"], delivered_digest, "PASS", utc_now()),
            )
        self.store.durable_barrier()
        return dict(self.store.connection.execute(
            "SELECT * FROM review_vouchers WHERE voucher_id=?", (vid,)
        ).fetchone())

    def promote_by_voucher(self, voucher_id: str) -> dict[str, Any]:
        v = self.store.connection.execute(
            "SELECT * FROM review_vouchers WHERE voucher_id=?", (voucher_id,)
        ).fetchone()
        if not v or v["verdict"] != "PASS":
            raise PromotionRequiresReview("no valid independent-review voucher for promotion")
        return self.promote(v["candidate_record_id"], independent_review={
            "verdict": "PASS", "reviewer": v["reviewer_identity"], "reviewer_role": v["reviewer_role"],
        })


    def record_review(self, *, candidate_record_id: str, reviewer_identity: str,
                     review_source: str, verdict: str) -> dict[str, Any]:
        """Authoritative independent-review record. Only the independent-review
        ADAPTER should call this (it is the 'source' of the review). Binds the
        record to an ACTIVE Candidate (commit/tree/digest are taken from the
        candidate, not the caller), requires an R_PROD reviewer, and stores the
        ACTUAL verdict (PASS/REWORK/BLOCKED). This is the thing that turns a
        real external review outcome into a promotion-eligible fact."""
        cand = self.get_candidate(candidate_record_id)
        if not cand or cand["status"] != STATUS_CANDIDATE:
            raise LineageError("cannot record review for a non-active Candidate")
        if not review_source or not isinstance(review_source, str):
            raise LineageError("review_source is required (authoritative transport identity)")
        if str(verdict or "").upper() not in ("PASS", "REWORK", "BLOCKED"):
            raise LineageError(f"invalid review verdict: {verdict!r}")
        rid = f"review-{uuid.uuid4()}"
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO review_records(review_record_id,candidate_record_id,reviewer_identity,verdict,review_source,controller_commit,tree_digest,delivered_digest,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (rid, cand["record_id"], reviewer_identity, str(verdict).upper(),
                 review_source, cand["controller_commit"], cand["tree_digest"],
                 self._parsed_delivered(cand) or "", utc_now()),
            )
        self.store.durable_barrier()
        return dict(self.store.connection.execute(
            "SELECT * FROM review_records WHERE review_record_id=?", (rid,)
        ).fetchone())

    def review_record(self, record_id: str) -> dict[str, Any] | None:
        row = self.store.connection.execute(
            "SELECT * FROM review_records WHERE review_record_id=?", (record_id,)
        ).fetchone()
        return dict(row) if row else None

    def promote_by_review(self, review_record_id: str) -> dict[str, Any]:
        """Promote to STABLE from a durable, source-bound review record. Never from
        a caller-supplied verdict dict or reviewer name+digest: the record must
        exist, be R_PROD, verdict PASS, and match the ACTIVE Candidate binding."""
        rec = self.review_record(review_record_id)
        if not rec:
            raise PromotionRequiresReview("no authoritative independent-review record for promotion")
        if rec["verdict"] != "PASS":
            raise PromotionRequiresReview("independent review record is not PASS (REWORK/BLOCKED cannot promote)")
        cand = self.get_candidate(rec["candidate_record_id"])
        if not cand or cand["status"] != STATUS_CANDIDATE:
            raise LineageError("bound Candidate is not active")
        # binding: candidate digest must equal the record's digest
        if rec["delivered_digest"] and (self._parsed_delivered(cand) or "") != rec["delivered_digest"]:
            raise LineageError("review record digest does not match the Candidate")
        return self.promote(rec["candidate_record_id"], independent_review={
            "verdict": "PASS", "reviewer": rec["reviewer_identity"], "review_source": rec["review_source"],
        })

    def lineage(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.store.connection.execute(
                "SELECT * FROM stable_lineage ORDER BY version"
            )
        ]