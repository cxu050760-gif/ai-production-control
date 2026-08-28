from __future__ import annotations

import contextlib
import ctypes
import json
import os
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from .util import (
    atomic_write,
    canonical_json,
    fsync_file,
    is_expired,
    parse_iso,
    sha256_file,
    sha256_text,
    utc_now,
    windows_boot_session_id,
)


class ControlError(RuntimeError):
    pass


class GateDenied(ControlError):
    pass


class AuthorityStateUncertain(ControlError):
    pass


class StorageDurabilityUnavailable(ControlError):
    pass


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@dataclass(frozen=True)
class Reservation:
    action_id: str
    logical_effect_id: str
    effect_intent_hash: str
    logical_effect_slot: str
    attempt_id: str
    execution_fence_token: str
    deduplicated: bool
    status: str


SCHEMA = r"""
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_revisions (
  revision INTEGER PRIMARY KEY,
  parent_revision INTEGER,
  committed_at TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  snapshot_path TEXT NOT NULL,
  state_hash TEXT NOT NULL,
  reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS state_head (
  singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
  revision INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS goal_contracts (
  task_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  contract_hash TEXT NOT NULL,
  security_generation INTEGER NOT NULL,
  contract_json TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(task_id, version)
);

CREATE TABLE IF NOT EXISTS decision_nonces (
  decision_nonce TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  scope_digest TEXT NOT NULL,
  issued_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  user_decision_reference TEXT NOT NULL,
  status TEXT NOT NULL,
  consumed_at TEXT
);

CREATE TABLE IF NOT EXISTS authorizations (
  authorization_id TEXT PRIMARY KEY,
  decision_nonce TEXT NOT NULL,
  task_id TEXT NOT NULL,
  goal_contract_version INTEGER NOT NULL,
  goal_contract_hash TEXT NOT NULL,
  scope_json TEXT NOT NULL,
  scope_digest TEXT NOT NULL,
  provider TEXT NOT NULL,
  resource TEXT NOT NULL,
  purpose TEXT NOT NULL,
  effect_type TEXT NOT NULL,
  max_effect_count INTEGER NOT NULL,
  consumed_effect_count INTEGER NOT NULL,
  generation INTEGER NOT NULL,
  revocation_epoch INTEGER NOT NULL,
  granted_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  revoked_at TEXT,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS revocation_epochs (
  task_id TEXT PRIMARY KEY,
  epoch INTEGER NOT NULL,
  generation INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS authority_events (
  journal_sequence INTEGER PRIMARY KEY,
  authority_event_id TEXT UNIQUE NOT NULL,
  event_type TEXT NOT NULL,
  task_id TEXT NOT NULL,
  goal_contract_version INTEGER,
  goal_contract_hash TEXT,
  authorization_id TEXT,
  decision_nonce TEXT,
  previous_generation INTEGER NOT NULL,
  new_generation INTEGER NOT NULL,
  scope_digest TEXT NOT NULL,
  state_revision_at_commit INTEGER NOT NULL,
  committed_at TEXT NOT NULL,
  event_json TEXT NOT NULL,
  event_hash TEXT NOT NULL,
  previous_event_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS context_capsules (
  task_id TEXT NOT NULL,
  capsule_version INTEGER NOT NULL,
  capsule_hash TEXT NOT NULL,
  state_revision INTEGER NOT NULL,
  goal_contract_hash TEXT NOT NULL,
  checkpoint TEXT NOT NULL,
  capsule_json TEXT NOT NULL,
  continuity_status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(task_id, capsule_version)
);

CREATE TABLE IF NOT EXISTS locks (
  resource_id TEXT PRIMARY KEY,
  controller_instance_id TEXT NOT NULL,
  owner TEXT NOT NULL,
  pid INTEGER NOT NULL,
  process_start_identity TEXT NOT NULL,
  boot_session_id TEXT NOT NULL,
  lease_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  heartbeat_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS actions (
  action_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  logical_effect_id TEXT NOT NULL,
  effect_intent_hash TEXT NOT NULL,
  logical_effect_slot TEXT NOT NULL,
  attempt_id TEXT NOT NULL,
  execution_fence_token TEXT NOT NULL,
  status TEXT NOT NULL,
  retry_semantics TEXT NOT NULL,
  impact TEXT NOT NULL,
  reversibility TEXT NOT NULL,
  effect_scope TEXT NOT NULL,
  provider TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  outcome_json TEXT,
  UNIQUE(task_id, logical_effect_id)
);

CREATE TABLE IF NOT EXISTS reservations (
  logical_effect_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  action_id TEXT NOT NULL,
  effect_intent_hash TEXT NOT NULL,
  logical_effect_slot TEXT NOT NULL,
  authorization_id TEXT NOT NULL,
  controller_instance_id TEXT NOT NULL,
  lease_id TEXT NOT NULL,
  state_revision INTEGER NOT NULL,
  goal_contract_hash TEXT NOT NULL,
  authorization_generation INTEGER NOT NULL,
  revocation_epoch INTEGER NOT NULL,
  context_fence TEXT NOT NULL,
  resource_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS effect_wal (
  wal_sequence INTEGER PRIMARY KEY,
  wal_id TEXT UNIQUE NOT NULL,
  action_id TEXT NOT NULL,
  logical_effect_id TEXT NOT NULL,
  status TEXT NOT NULL,
  record_json TEXT NOT NULL,
  record_hash TEXT NOT NULL,
  previous_record_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invocations (
  invocation_id TEXT PRIMARY KEY,
  request_nonce TEXT NOT NULL,
  expected_actor_id TEXT NOT NULL,
  actor_type TEXT NOT NULL,
  task_id TEXT NOT NULL,
  goal_contract_hash TEXT NOT NULL,
  state_revision INTEGER NOT NULL,
  context_fence TEXT NOT NULL,
  trust_class TEXT NOT NULL,
  capability_json TEXT NOT NULL,
  result_channel TEXT NOT NULL,
  process_session_identity TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS results (
  result_id TEXT PRIMARY KEY,
  invocation_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  source_binding_json TEXT NOT NULL,
  envelope_json TEXT NOT NULL,
  envelope_hash TEXT NOT NULL,
  verification_status TEXT NOT NULL,
  received_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS processes (
  process_record_id TEXT PRIMARY KEY,
  invocation_id TEXT,
  process_id INTEGER NOT NULL,
  process_start_identity TEXT NOT NULL,
  controller_instance_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  action_id TEXT,
  logical_effect_id TEXT,
  parent_process_id INTEGER NOT NULL,
  job_or_group TEXT NOT NULL,
  lifetime TEXT NOT NULL,
  effect_class TEXT NOT NULL,
  record_json TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT
);

CREATE TABLE IF NOT EXISTS worker_registry (
  worker_id TEXT PRIMARY KEY,
  registry_json TEXT NOT NULL,
  generation INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS brain_registry (
  brain_id TEXT PRIMARY KEY,
  registry_json TEXT NOT NULL,
  generation INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_ledger (
  decision_id TEXT PRIMARY KEY,
  decision_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS failed_approaches (
  approach_id TEXT PRIMARY KEY,
  approach_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS progress_signatures (
  task_id TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  signature TEXT NOT NULL,
  substantive_progress INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(task_id, sequence)
);

CREATE TABLE IF NOT EXISTS migration_history (
  migration_id TEXT PRIMARY KEY,
  from_version INTEGER NOT NULL,
  to_version INTEGER NOT NULL,
  status TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
  evidence_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  classification TEXT NOT NULL,
  kind TEXT NOT NULL,
  path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_executions (
  test_execution_id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  definition_version TEXT NOT NULL,
  task_id TEXT NOT NULL,
  goal_contract_hash TEXT NOT NULL,
  state_revision INTEGER NOT NULL,
  tested_artifact_digest TEXT NOT NULL,
  controller_instance_id TEXT NOT NULL,
  process_browser_identity TEXT NOT NULL,
  invocation_json TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  exit_or_observed_result TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  evidence_hashes_json TEXT NOT NULL,
  verification_status TEXT NOT NULL,
  requirement_class TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS release_candidates (
  release_candidate_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  goal_contract_hash TEXT NOT NULL,
  state_revision INTEGER NOT NULL,
  artifact_kind TEXT NOT NULL,
  artifact_path TEXT NOT NULL,
  artifact_digest TEXT NOT NULL,
  artifact_size INTEGER NOT NULL,
  tree_manifest_json TEXT NOT NULL,
  test_evidence_json TEXT NOT NULL,
  review_evidence_json TEXT NOT NULL,
  acceptance_manifest_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL,
  delivered_digest TEXT
);

CREATE TRIGGER IF NOT EXISTS authority_events_no_update
BEFORE UPDATE ON authority_events BEGIN SELECT RAISE(ABORT, 'authority journal is append-only'); END;
CREATE TRIGGER IF NOT EXISTS authority_events_no_delete
BEFORE DELETE ON authority_events BEGIN SELECT RAISE(ABORT, 'authority journal is append-only'); END;
CREATE TRIGGER IF NOT EXISTS effect_wal_no_update
BEFORE UPDATE ON effect_wal BEGIN SELECT RAISE(ABORT, 'effect WAL is append-only'); END;
CREATE TRIGGER IF NOT EXISTS effect_wal_no_delete
BEFORE DELETE ON effect_wal BEGIN SELECT RAISE(ABORT, 'effect WAL is append-only'); END;
CREATE TRIGGER IF NOT EXISTS canonical_revisions_no_update
BEFORE UPDATE ON canonical_revisions BEGIN SELECT RAISE(ABORT, 'canonical revisions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS canonical_revisions_no_delete
BEFORE DELETE ON canonical_revisions BEGIN SELECT RAISE(ABORT, 'canonical revisions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS evidence_no_update
BEFORE UPDATE ON evidence BEGIN SELECT RAISE(ABORT, 'evidence records are append-only'); END;
CREATE TRIGGER IF NOT EXISTS evidence_no_delete
BEFORE DELETE ON evidence BEGIN SELECT RAISE(ABORT, 'evidence records are append-only'); END;
CREATE TRIGGER IF NOT EXISTS test_executions_no_update
BEFORE UPDATE ON test_executions BEGIN SELECT RAISE(ABORT, 'test executions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS test_executions_no_delete
BEFORE DELETE ON test_executions BEGIN SELECT RAISE(ABORT, 'test executions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS results_no_update
BEFORE UPDATE ON results BEGIN SELECT RAISE(ABORT, 'actor results are append-only'); END;
CREATE TRIGGER IF NOT EXISTS results_no_delete
BEFORE DELETE ON results BEGIN SELECT RAISE(ABORT, 'actor results are append-only'); END;

CREATE TABLE IF NOT EXISTS provider_registry (
  provider_id TEXT PRIMARY KEY,
  registry_json TEXT NOT NULL,
  generation INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviewer_registry (
  reviewer_id TEXT PRIMARY KEY,
  registry_json TEXT NOT NULL,
  generation INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tool_registry (
  tool_id TEXT PRIMARY KEY,
  registry_json TEXT NOT NULL,
  generation INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);
"""


CANONICAL_ACTOR_STATUSES = {
    "PRODUCT_DONE",
    "PROJECT_DONE",
    "STABLE_CANDIDATE",
    "READY_FOR_USER_ACCEPTANCE",
    "DELIVERED",
}
CANONICAL_ACTOR_FIELDS = {
    "canonical_state",
    "goal_contract",
    "highest_goal",
    "project_phase",
    "milestone",
    "release_status",
}
CANONICAL_MUTATION_PROPOSALS = {
    "CHANGE_GOAL",
    "CHANGE_HIGHEST_GOAL",
    "CHANGE_PHASE",
    "PROMOTE_MILESTONE",
    "MARK_PRODUCT_DONE",
    "MARK_PROJECT_DONE",
    "REWRITE_FROZEN_ASSET",
}


def validate_actor_trajectory(actor_type: str, envelope: dict[str, Any]) -> None:
    """Enforce the minimum invariants that must exist before the full workflow layer."""
    if not isinstance(envelope, dict):
        raise GateDenied("actor result envelope must be an object")
    reserved = sorted(CANONICAL_ACTOR_FIELDS.intersection(envelope))
    if reserved:
        raise GateDenied(f"actor result attempted canonical mutation fields: {reserved}")
    status = envelope.get("status")
    if status in CANONICAL_ACTOR_STATUSES:
        raise GateDenied("actor result status cannot promote product/project completion")
    proposals = envelope.get("action_proposals", [])
    if not isinstance(proposals, list):
        raise GateDenied("actor action_proposals must be a list")
    for proposal in proposals:
        if not isinstance(proposal, dict):
            raise GateDenied("actor action proposal must be an object")
        operation = str(proposal.get("operation") or proposal.get("action") or "").upper()
        if operation in CANONICAL_MUTATION_PROPOSALS:
            raise GateDenied(f"actor proposal cannot perform canonical transition: {operation}")
    if actor_type == "WORKER" and status == "DONE":
        evidence = envelope.get("evidence")
        artifact_paths = envelope.get("artifact_paths")
        artifact_hashes = envelope.get("artifact_hashes")
        if not isinstance(evidence, list) or not evidence:
            raise GateDenied("Worker DONE requires an evidence delta")
        if not isinstance(artifact_paths, list) or not artifact_paths or not isinstance(artifact_hashes, dict):
            raise GateDenied("Worker DONE requires digest-bound artifacts")


class ControlStore:
    def __init__(self, database_path: str | Path, *, state_root: str | Path | None = None) -> None:
        self.database_path = Path(database_path)
        self.state_root = Path(state_root) if state_root else self.database_path.parent
        self.snapshot_root = self.state_root / "snapshots"
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_root.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA trusted_schema=OFF")
        self.connection.execute("PRAGMA busy_timeout=30000")
        self.connection.executescript(SCHEMA)
        if self.connection.execute("SELECT 1 FROM meta WHERE key='schema_version'").fetchone() is None:
            with self.transaction() as conn:
                conn.execute("INSERT INTO meta(key,value) VALUES('schema_version','1')")
                conn.execute("INSERT INTO meta(key,value) VALUES('tcb_status','UNVERIFIED_AFTER_CONTROLLER_CHANGE')")
                conn.execute("INSERT INTO meta(key,value) VALUES('authority_status','VERIFIED')")
        if self.connection.execute("SELECT 1 FROM state_head WHERE singleton=1").fetchone() is None:
            self.commit_state({"schema_version": 1, "tasks": {}, "authority_recovery": {}}, reason="INITIAL_STATE")

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "ControlStore":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    @contextlib.contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield self.connection
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise

    def durable_barrier(self, faults: set[str] | None = None) -> None:
        if faults and "flush" in faults:
            raise StorageDurabilityUnavailable("injected flush failure")
        self.connection.execute("PRAGMA wal_checkpoint(FULL)")
        if self.database_path.exists():
            fsync_file(self.database_path)
        wal = Path(f"{self.database_path}-wal")
        if wal.exists():
            fsync_file(wal)

    def confirm_security_durability(self, faults: set[str] | None = None) -> None:
        try:
            self.durable_barrier(faults)
        except StorageDurabilityUnavailable:
            self.set_meta("authority_status", "AUTHORITY_STATE_UNCERTAIN")
            self.durable_barrier()
            raise

    def meta(self, key: str, default: str | None = None) -> str | None:
        row = self.connection.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str, conn: sqlite3.Connection | None = None) -> None:
        target = conn or self.connection
        target.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def state_head(self) -> int:
        row = self.connection.execute("SELECT revision FROM state_head WHERE singleton=1").fetchone()
        if not row:
            raise ControlError("STATE_HEAD missing")
        return int(row["revision"])

    def commit_state(self, state: dict[str, Any], *, reason: str, faults: set[str] | None = None) -> int:
        if faults and "state_write" in faults:
            raise StorageDurabilityUnavailable("injected canonical state write failure")
        payload = canonical_json(state)
        snapshot_payload = payload + "\n"
        digest = sha256_text(snapshot_payload)
        current = self.connection.execute("SELECT MAX(revision) AS value FROM canonical_revisions").fetchone()
        revision = int(current["value"] or 0) + 1
        parent = self.state_head() if self.connection.execute("SELECT 1 FROM state_head").fetchone() else None
        snapshot_path = self.snapshot_root / f"revision-{revision:08d}.json"
        atomic_write(snapshot_path, snapshot_payload)
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO canonical_revisions(revision,parent_revision,committed_at,schema_version,snapshot_path,state_hash,reason) VALUES(?,?,?,?,?,?,?)",
                (revision, parent, utc_now(), 1, str(snapshot_path), digest, reason),
            )
            conn.execute(
                "INSERT INTO state_head(singleton,revision) VALUES(1,?) ON CONFLICT(singleton) DO UPDATE SET revision=excluded.revision",
                (revision,),
            )
        self.durable_barrier(faults)
        return revision

    def read_revision(self, revision: int) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM canonical_revisions WHERE revision=?", (revision,)).fetchone()
        if not row:
            raise ControlError(f"revision not found: {revision}")
        path = Path(row["snapshot_path"])
        if not path.exists() or sha256_file(path) != row["state_hash"]:
            raise ControlError(f"revision integrity failure: {revision}")
        return json.loads(path.read_text(encoding="utf-8"))

    def read_state(self) -> dict[str, Any]:
        return self.read_revision(self.state_head())

    def recover_state(self, *, faults: set[str] | None = None) -> dict[str, Any]:
        valid_revision = None
        state = None
        for row in self.connection.execute("SELECT revision FROM canonical_revisions ORDER BY revision DESC"):
            try:
                state = self.read_revision(int(row["revision"]))
                valid_revision = int(row["revision"])
                break
            except ControlError:
                continue
        if state is None or valid_revision is None:
            self.set_meta("authority_status", "AUTHORITY_STATE_UNCERTAIN")
            raise AuthorityStateUncertain("no known-good Canonical State revision")
        try:
            authority = self.reconstruct_authority()
            self.verify_authority_chain()
            self.verify_effect_wal()
        except Exception as error:
            self.set_meta("authority_status", "AUTHORITY_STATE_UNCERTAIN")
            raise AuthorityStateUncertain(str(error)) from error
        state["authority_recovery"] = authority
        state["recovered_from_revision"] = valid_revision
        new_revision = self.commit_state(state, reason="RECOVERY_REPLAY", faults=faults)
        self.set_meta("authority_status", "VERIFIED")
        self.durable_barrier(faults)
        return {"recovered_from": valid_revision, "new_revision": new_revision, "authority": authority}

    def _next_generation(self, conn: sqlite3.Connection, task_id: str, kind: str) -> tuple[int, int]:
        key = f"generation:{kind}:{task_id}"
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        previous = int(row["value"]) if row else 0
        current = previous + 1
        self.set_meta(key, str(current), conn)
        return previous, current

    def _append_authority_event(
        self,
        conn: sqlite3.Connection,
        *,
        event_type: str,
        task_id: str,
        goal_version: int | None,
        goal_hash: str | None,
        authorization_id: str | None,
        decision_nonce: str | None,
        previous_generation: int,
        new_generation: int,
        scope_digest: str,
        state_revision: int,
        data: dict[str, Any],
        faults: set[str] | None = None,
    ) -> dict[str, Any]:
        if faults and "authority_write" in faults:
            raise StorageDurabilityUnavailable("injected Authority Commit Journal write failure")
        last = conn.execute(
            "SELECT journal_sequence,event_hash FROM authority_events ORDER BY journal_sequence DESC LIMIT 1"
        ).fetchone()
        sequence = (int(last["journal_sequence"]) + 1) if last else 1
        previous_hash = last["event_hash"] if last else "0" * 64
        event = {
            "authority_event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "task_id": task_id,
            "goal_contract_version": goal_version,
            "goal_contract_hash": goal_hash,
            "authorization_id": authorization_id,
            "decision_nonce": decision_nonce,
            "previous_generation": previous_generation,
            "new_generation": new_generation,
            "scope_digest": scope_digest,
            "state_revision_at_commit": state_revision,
            "committed_at": utc_now(),
            "journal_sequence": sequence,
            "event": data,
            "previous_event_hash": previous_hash,
        }
        event_hash = sha256_text(canonical_json(event))
        conn.execute(
            """INSERT INTO authority_events(
              journal_sequence,authority_event_id,event_type,task_id,goal_contract_version,goal_contract_hash,
              authorization_id,decision_nonce,previous_generation,new_generation,scope_digest,
              state_revision_at_commit,committed_at,event_json,event_hash,previous_event_hash
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                sequence,
                event["authority_event_id"],
                event_type,
                task_id,
                goal_version,
                goal_hash,
                authorization_id,
                decision_nonce,
                previous_generation,
                new_generation,
                scope_digest,
                state_revision,
                event["committed_at"],
                canonical_json(data),
                event_hash,
                previous_hash,
            ),
        )
        event["event_hash"] = event_hash
        return event

    def verify_authority_chain(self, *, faults: set[str] | None = None) -> dict[str, Any]:
        if faults and "authority_integrity" in faults:
            raise AuthorityStateUncertain("injected Authority Commit Journal integrity failure")
        previous_hash = "0" * 64
        count = 0
        for row in self.connection.execute("SELECT * FROM authority_events ORDER BY journal_sequence"):
            if row["previous_event_hash"] != previous_hash:
                raise AuthorityStateUncertain("Authority Commit Journal link mismatch")
            event = {
                "authority_event_id": row["authority_event_id"],
                "event_type": row["event_type"],
                "task_id": row["task_id"],
                "goal_contract_version": row["goal_contract_version"],
                "goal_contract_hash": row["goal_contract_hash"],
                "authorization_id": row["authorization_id"],
                "decision_nonce": row["decision_nonce"],
                "previous_generation": row["previous_generation"],
                "new_generation": row["new_generation"],
                "scope_digest": row["scope_digest"],
                "state_revision_at_commit": row["state_revision_at_commit"],
                "committed_at": row["committed_at"],
                "journal_sequence": row["journal_sequence"],
                "event": json.loads(row["event_json"]),
                "previous_event_hash": previous_hash,
            }
            expected = sha256_text(canonical_json(event))
            if expected != row["event_hash"]:
                raise AuthorityStateUncertain("Authority Commit Journal event hash mismatch")
            previous_hash = row["event_hash"]
            count += 1
        return {"verified": True, "events": count, "head_hash": previous_hash}

    def reconstruct_authority(self, task_id: str | None = None) -> dict[str, Any]:
        authorizations: dict[str, dict[str, Any]] = {}
        tasks: dict[str, dict[str, Any]] = {}
        parameters: tuple[Any, ...] = ()
        clause = ""
        if task_id:
            clause = " WHERE task_id=?"
            parameters = (task_id,)
        rows = self.connection.execute(
            f"SELECT * FROM authority_events{clause} ORDER BY journal_sequence", parameters
        )
        for row in rows:
            data = json.loads(row["event_json"])
            task = tasks.setdefault(
                row["task_id"],
                {"revocation_epoch": 0, "authorization_generation": 0, "security_generation": 0},
            )
            task["authorization_generation"] = max(task["authorization_generation"], int(row["new_generation"]))
            if row["event_type"] == "GOAL_SECURITY_CHANGE":
                task["security_generation"] = max(task["security_generation"], int(row["new_generation"]))
                task["goal_security"] = data
            if row["event_type"] == "REVOCATION_FENCE":
                task["revocation_epoch"] = max(task["revocation_epoch"], int(data.get("revocation_epoch", 0)))
            authorization_id = row["authorization_id"]
            if authorization_id:
                auth = authorizations.setdefault(
                    authorization_id,
                    {
                        "authorization_id": authorization_id,
                        "task_id": row["task_id"],
                        "status": "UNKNOWN",
                        "consumed_effect_count": 0,
                        "generation": 0,
                        "revocation_epoch": 0,
                    },
                )
                auth["generation"] = max(auth["generation"], int(row["new_generation"]))
                if row["event_type"] == "AUTHORIZATION_GRANTED":
                    auth.update(data)
                    auth["status"] = "ACTIVE"
                elif row["event_type"] in ("AUTHORIZATION_RESERVED", "AUTHORIZATION_CONSUMED"):
                    auth["consumed_effect_count"] = max(
                        int(auth.get("consumed_effect_count", 0)), int(data.get("consumed_effect_count", 0))
                    )
                elif row["event_type"] == "AUTHORIZATION_REVOKED":
                    auth["status"] = "REVOKED"
                    auth["revoked_at"] = data.get("revoked_at")
                    auth["revocation_epoch"] = max(
                        int(auth.get("revocation_epoch", 0)), int(data.get("revocation_epoch", 0))
                    )
        return {"tasks": tasks, "authorizations": authorizations}

    def create_goal_contract(self, task_id: str, contract: dict[str, Any], *, change_reason: str) -> dict[str, Any]:
        latest = self.connection.execute(
            "SELECT MAX(version) AS value FROM goal_contracts WHERE task_id=?", (task_id,)
        ).fetchone()
        version = int(latest["value"] or 0) + 1
        value = dict(contract)
        value.update(
            {
                "contract_version": version,
                "task_id": task_id,
                "updated_at": utc_now(),
                "change_reason": change_reason,
            }
        )
        value.setdefault("created_at", value["updated_at"])
        digest = sha256_text(canonical_json(value))
        value["contract_hash"] = digest
        scope_digest = sha256_text(
            canonical_json(
                {
                    "network_permission": value.get("network_permission", "DENY"),
                    "installation_permission": value.get("installation_permission", "DENY"),
                    "data_egress_policy": value.get("data_egress_policy", {}),
                    "external_side_effect_policy": value.get("external_side_effect_policy", "DENY"),
                    "constraints": value.get("constraints", []),
                }
            )
        )
        with self.transaction() as conn:
            previous, generation = self._next_generation(conn, task_id, "goal_security")
            conn.execute(
                "INSERT INTO goal_contracts(task_id,version,contract_hash,security_generation,contract_json,status,created_at) VALUES(?,?,?,?,?,?,?)",
                (task_id, version, digest, generation, canonical_json(value), "ACTIVE", utc_now()),
            )
            self._append_authority_event(
                conn,
                event_type="GOAL_SECURITY_CHANGE",
                task_id=task_id,
                goal_version=version,
                goal_hash=digest,
                authorization_id=None,
                decision_nonce=None,
                previous_generation=previous,
                new_generation=generation,
                scope_digest=scope_digest,
                state_revision=self.state_head(),
                data={
                    "network_permission": value.get("network_permission", "DENY"),
                    "data_egress_policy": value.get("data_egress_policy", {}),
                    "external_side_effect_policy": value.get("external_side_effect_policy", "DENY"),
                    "resource_scope": value.get("resource_scope", []),
                    "security_generation": generation,
                },
            )
        state = self.read_state()
        tasks = state.setdefault("tasks", {})
        tasks.setdefault(task_id, {})["goal_contract"] = value
        revision = self.commit_state(state, reason=f"GOAL_CONTRACT_{version}")
        self.durable_barrier()
        return {"task_id": task_id, "version": version, "hash": digest, "security_generation": generation, "state_revision": revision, "contract": value}

    def latest_goal(self, task_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM goal_contracts WHERE task_id=? AND status='ACTIVE' ORDER BY version DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        if not row:
            raise GateDenied("active Goal Contract missing")
        value = json.loads(row["contract_json"])
        value["contract_hash"] = row["contract_hash"]
        value["security_generation"] = row["security_generation"]
        return value

    def issue_decision_nonce(
        self,
        task_id: str,
        scope: dict[str, Any],
        *,
        user_decision_reference: str,
        ttl_seconds: int = 900,
    ) -> dict[str, Any]:
        nonce = secrets.token_urlsafe(24)
        issued = utc_now()
        expires = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        digest = sha256_text(canonical_json(scope))
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO decision_nonces(decision_nonce,task_id,scope_digest,issued_at,expires_at,user_decision_reference,status) VALUES(?,?,?,?,?,?,?)",
                (nonce, task_id, digest, issued, expires, user_decision_reference, "ISSUED"),
            )
        self.durable_barrier()
        return {"decision_nonce": nonce, "task_id": task_id, "scope_digest": digest, "expires_at": expires}

    def grant_authorization(
        self,
        task_id: str,
        decision_nonce: str,
        scope: dict[str, Any],
        *,
        provider: str,
        resource: str,
        purpose: str,
        effect_type: str,
        max_effect_count: int,
        ttl_seconds: int = 3600,
        faults: set[str] | None = None,
    ) -> dict[str, Any]:
        if max_effect_count < 1:
            raise GateDenied("authorization quota must be positive")
        goal = self.latest_goal(task_id)
        scope_digest = sha256_text(canonical_json(scope))
        authorization_id = str(uuid.uuid4())
        now = utc_now()
        expires = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self.transaction() as conn:
            nonce = conn.execute("SELECT * FROM decision_nonces WHERE decision_nonce=?", (decision_nonce,)).fetchone()
            if not nonce or nonce["status"] != "ISSUED":
                raise GateDenied("decision nonce is fake, consumed, or unavailable")
            if nonce["task_id"] != task_id or nonce["scope_digest"] != scope_digest:
                raise GateDenied("decision nonce task/scope mismatch")
            if is_expired(nonce["expires_at"]):
                raise GateDenied("decision nonce expired")
            previous, generation = self._next_generation(conn, task_id, "authorization")
            epoch_row = conn.execute("SELECT epoch FROM revocation_epochs WHERE task_id=?", (task_id,)).fetchone()
            epoch = int(epoch_row["epoch"]) if epoch_row else 0
            conn.execute(
                "UPDATE decision_nonces SET status='CONSUMED',consumed_at=? WHERE decision_nonce=? AND status='ISSUED'",
                (now, decision_nonce),
            )
            conn.execute(
                """INSERT INTO authorizations(
                  authorization_id,decision_nonce,task_id,goal_contract_version,goal_contract_hash,scope_json,scope_digest,
                  provider,resource,purpose,effect_type,max_effect_count,consumed_effect_count,generation,revocation_epoch,
                  granted_at,expires_at,status
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    authorization_id,
                    decision_nonce,
                    task_id,
                    int(goal["contract_version"]),
                    goal["contract_hash"],
                    canonical_json(scope),
                    scope_digest,
                    provider,
                    resource,
                    purpose,
                    effect_type,
                    max_effect_count,
                    0,
                    generation,
                    epoch,
                    now,
                    expires,
                    "ACTIVE",
                ),
            )
            self._append_authority_event(
                conn,
                event_type="DECISION_NONCE_CONSUMED",
                task_id=task_id,
                goal_version=int(goal["contract_version"]),
                goal_hash=goal["contract_hash"],
                authorization_id=None,
                decision_nonce=decision_nonce,
                previous_generation=previous,
                new_generation=generation,
                scope_digest=scope_digest,
                state_revision=self.state_head(),
                data={"consumed_at": now},
                faults=faults,
            )
            auth_data = {
                "authorization_id": authorization_id,
                "decision_nonce": decision_nonce,
                "task_id": task_id,
                "goal_contract_version": int(goal["contract_version"]),
                "goal_contract_hash": goal["contract_hash"],
                "scope_digest": scope_digest,
                "provider": provider,
                "resource": resource,
                "purpose": purpose,
                "effect_type": effect_type,
                "max_effect_count": max_effect_count,
                "consumed_effect_count": 0,
                "generation": generation,
                "revocation_epoch": epoch,
                "granted_at": now,
                "expires_at": expires,
            }
            self._append_authority_event(
                conn,
                event_type="AUTHORIZATION_GRANTED",
                task_id=task_id,
                goal_version=int(goal["contract_version"]),
                goal_hash=goal["contract_hash"],
                authorization_id=authorization_id,
                decision_nonce=decision_nonce,
                previous_generation=previous,
                new_generation=generation,
                scope_digest=scope_digest,
                state_revision=self.state_head(),
                data=auth_data,
                faults=faults,
            )
        self.confirm_security_durability(faults)
        return auth_data

    def revoke_authorization(
        self, authorization_id: str, *, reason: str, faults: set[str] | None = None
    ) -> dict[str, Any]:
        now = utc_now()
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM authorizations WHERE authorization_id=?", (authorization_id,)).fetchone()
            if not row:
                raise GateDenied("authorization missing")
            task_id = row["task_id"]
            epoch_row = conn.execute("SELECT epoch,generation FROM revocation_epochs WHERE task_id=?", (task_id,)).fetchone()
            old_epoch = int(epoch_row["epoch"]) if epoch_row else 0
            new_epoch = old_epoch + 1
            previous, generation = self._next_generation(conn, task_id, "authorization")
            conn.execute(
                "INSERT INTO revocation_epochs(task_id,epoch,generation,updated_at) VALUES(?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET epoch=excluded.epoch,generation=excluded.generation,updated_at=excluded.updated_at",
                (task_id, new_epoch, generation, now),
            )
            conn.execute(
                "UPDATE authorizations SET status='REVOKED',revoked_at=?,generation=?,revocation_epoch=? WHERE authorization_id=?",
                (now, generation, new_epoch, authorization_id),
            )
            self._append_authority_event(
                conn,
                event_type="REVOCATION_FENCE",
                task_id=task_id,
                goal_version=row["goal_contract_version"],
                goal_hash=row["goal_contract_hash"],
                authorization_id=authorization_id,
                decision_nonce=None,
                previous_generation=previous,
                new_generation=generation,
                scope_digest=row["scope_digest"],
                state_revision=self.state_head(),
                data={"revocation_epoch": new_epoch, "raised_at": now, "reason": reason},
                faults=faults,
            )
            self._append_authority_event(
                conn,
                event_type="AUTHORIZATION_REVOKED",
                task_id=task_id,
                goal_version=row["goal_contract_version"],
                goal_hash=row["goal_contract_hash"],
                authorization_id=authorization_id,
                decision_nonce=None,
                previous_generation=previous,
                new_generation=generation,
                scope_digest=row["scope_digest"],
                state_revision=self.state_head(),
                data={"revoked_at": now, "revocation_epoch": new_epoch, "reason": reason},
                faults=faults,
            )
        self.confirm_security_durability(faults)
        return {"authorization_id": authorization_id, "status": "REVOKED", "revocation_epoch": new_epoch, "generation": generation}

    def acquire_controller_lease(
        self,
        controller_instance_id: str,
        *,
        pid: int,
        process_start_identity: str,
        ttl_seconds: int,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=ttl_seconds)
        lease_id = str(uuid.uuid4())
        with self.transaction() as conn:
            raw = self.meta("controller_lease")
            if raw:
                current = json.loads(raw)
                same_boot = current.get("boot_session_id") == windows_boot_session_id()
                process_alive = same_boot and _pid_is_alive(int(current.get("pid", 0)))
                if (
                    current["controller_instance_id"] != controller_instance_id
                    and parse_iso(current["expires_at"]) > now
                    and process_alive
                ):
                    raise GateDenied("another live Controller lease exists")
            lease = {
                "controller_instance_id": controller_instance_id,
                "lease_id": lease_id,
                "pid": pid,
                "process_start_identity": process_start_identity,
                "boot_session_id": windows_boot_session_id(),
                "created_at": utc_now(),
                "expires_at": expires.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            }
            self.set_meta("controller_lease", canonical_json(lease), conn)
        self.durable_barrier()
        return lease

    def release_controller_lease(self, controller_instance_id: str) -> None:
        with self.transaction() as conn:
            raw = self.meta("controller_lease")
            if raw and json.loads(raw).get("controller_instance_id") == controller_instance_id:
                conn.execute("DELETE FROM meta WHERE key='controller_lease'")
            conn.execute("DELETE FROM locks WHERE controller_instance_id=?", (controller_instance_id,))
        self.durable_barrier()

    def acquire_lock(
        self,
        resource_id: str,
        *,
        controller_instance_id: str,
        owner: str,
        pid: int,
        process_start_identity: str,
        ttl_seconds: int,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=ttl_seconds)
        lease_id = str(uuid.uuid4())
        with self.transaction() as conn:
            existing = conn.execute("SELECT * FROM locks WHERE resource_id=?", (resource_id,)).fetchone()
            if existing and parse_iso(existing["expires_at"]) > now and existing["controller_instance_id"] != controller_instance_id:
                raise GateDenied("resource lock is held by another Controller")
            conn.execute("DELETE FROM locks WHERE resource_id=?", (resource_id,))
            conn.execute(
                "INSERT INTO locks(resource_id,controller_instance_id,owner,pid,process_start_identity,boot_session_id,lease_id,created_at,heartbeat_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    resource_id,
                    controller_instance_id,
                    owner,
                    pid,
                    process_start_identity,
                    windows_boot_session_id(),
                    lease_id,
                    utc_now(),
                    utc_now(),
                    expires.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                ),
            )
        self.durable_barrier()
        return {"resource_id": resource_id, "lease_id": lease_id, "expires_at": expires.isoformat()}

    def release_lock(self, resource_id: str, controller_instance_id: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "DELETE FROM locks WHERE resource_id=? AND controller_instance_id=?",
                (resource_id, controller_instance_id),
            )
        self.durable_barrier()

    def create_context_capsule(self, task_id: str, checkpoint: str, details: dict[str, Any]) -> dict[str, Any]:
        goal = self.latest_goal(task_id)
        latest = self.connection.execute(
            "SELECT MAX(capsule_version) AS value FROM context_capsules WHERE task_id=?", (task_id,)
        ).fetchone()
        version = int(latest["value"] or 0) + 1
        capsule = {
            "capsule_version": version,
            "mission_id": details.get("mission_id"),
            "task_id": task_id,
            "goal_contract_version": goal["contract_version"],
            "goal_contract_hash": goal["contract_hash"],
            "state_revision": self.state_head(),
            "checkpoint": checkpoint,
            "current_objective": details.get("current_objective", goal.get("goal")),
            "completed_work": details.get("completed_work", []),
            "current_work": details.get("current_work", []),
            "next_required_steps": details.get("next_required_steps", []),
            "active_constraints": goal.get("constraints", []),
            "non_goals": goal.get("non_goals", []),
            "critical_decisions": details.get("critical_decisions", []),
            "failed_approaches": details.get("failed_approaches", []),
            "open_issues": details.get("open_issues", []),
            "blocking_issues": details.get("blocking_issues", []),
            "uncertain_external_effects": details.get("uncertain_external_effects", []),
            "active_action_ids": details.get("active_action_ids", []),
            "relevant_artifacts": details.get("relevant_artifacts", []),
            "worker_state": details.get("worker_state", {}),
            "last_verified_state": details.get("last_verified_state"),
            "created_at": utc_now(),
        }
        digest = sha256_text(canonical_json(capsule))
        context_fence = sha256_text(
            canonical_json(
                {
                    "task_id": task_id,
                    "state_revision": capsule["state_revision"],
                    "goal_contract_hash": goal["contract_hash"],
                    "checkpoint": checkpoint,
                    "capsule_hash": digest,
                }
            )
        )
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO context_capsules(task_id,capsule_version,capsule_hash,state_revision,goal_contract_hash,checkpoint,capsule_json,continuity_status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    task_id,
                    version,
                    digest,
                    capsule["state_revision"],
                    goal["contract_hash"],
                    checkpoint,
                    canonical_json(capsule),
                    "CURRENT",
                    capsule["created_at"],
                ),
            )
        self.durable_barrier()
        return {"capsule": capsule, "capsule_hash": digest, "context_fence": context_fence}

    def current_context_fence(self, task_id: str) -> str:
        row = self.connection.execute(
            "SELECT * FROM context_capsules WHERE task_id=? ORDER BY capsule_version DESC LIMIT 1", (task_id,)
        ).fetchone()
        if not row or row["continuity_status"] != "CURRENT":
            raise GateDenied("current Context Capsule missing")
        if int(row["state_revision"]) != self.state_head():
            raise GateDenied("Context Capsule is stale after Canonical State change")
        if row["goal_contract_hash"] != self.latest_goal(task_id)["contract_hash"]:
            raise GateDenied("Context Capsule is stale after Goal Contract change")
        return sha256_text(
            canonical_json(
                {
                    "task_id": task_id,
                    "state_revision": row["state_revision"],
                    "goal_contract_hash": row["goal_contract_hash"],
                    "checkpoint": row["checkpoint"],
                    "capsule_hash": row["capsule_hash"],
                }
            )
        )

    def _append_wal(
        self,
        conn: sqlite3.Connection,
        *,
        action_id: str,
        logical_effect_id: str,
        status: str,
        record: dict[str, Any],
        faults: set[str] | None = None,
    ) -> dict[str, Any]:
        if faults and "wal_write" in faults:
            raise StorageDurabilityUnavailable("injected Effect WAL write failure")
        last = conn.execute("SELECT wal_sequence,record_hash FROM effect_wal ORDER BY wal_sequence DESC LIMIT 1").fetchone()
        sequence = int(last["wal_sequence"]) + 1 if last else 1
        previous_hash = last["record_hash"] if last else "0" * 64
        value = {
            "wal_id": str(uuid.uuid4()),
            "wal_sequence": sequence,
            "action_id": action_id,
            "logical_effect_id": logical_effect_id,
            "status": status,
            "record": record,
            "created_at": utc_now(),
            "previous_record_hash": previous_hash,
        }
        record_hash = sha256_text(canonical_json(value))
        conn.execute(
            "INSERT INTO effect_wal(wal_sequence,wal_id,action_id,logical_effect_id,status,record_json,record_hash,previous_record_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                sequence,
                value["wal_id"],
                action_id,
                logical_effect_id,
                status,
                canonical_json(record),
                record_hash,
                previous_hash,
                value["created_at"],
            ),
        )
        value["record_hash"] = record_hash
        return value

    def verify_effect_wal(self) -> dict[str, Any]:
        previous_hash = "0" * 64
        count = 0
        for row in self.connection.execute("SELECT * FROM effect_wal ORDER BY wal_sequence"):
            if row["previous_record_hash"] != previous_hash:
                raise ControlError("Effect WAL link mismatch")
            value = {
                "wal_id": row["wal_id"],
                "wal_sequence": row["wal_sequence"],
                "action_id": row["action_id"],
                "logical_effect_id": row["logical_effect_id"],
                "status": row["status"],
                "record": json.loads(row["record_json"]),
                "created_at": row["created_at"],
                "previous_record_hash": previous_hash,
            }
            expected = sha256_text(canonical_json(value))
            if expected != row["record_hash"]:
                raise ControlError("Effect WAL hash mismatch")
            previous_hash = row["record_hash"]
            count += 1
        return {"verified": True, "records": count, "head_hash": previous_hash}

    def _lease(self, conn: sqlite3.Connection, controller_instance_id: str, lease_id: str) -> dict[str, Any]:
        raw = self.meta("controller_lease")
        if not raw:
            raise GateDenied("Controller lease missing")
        lease = json.loads(raw)
        if lease["controller_instance_id"] != controller_instance_id or lease["lease_id"] != lease_id:
            raise GateDenied("stale Controller lease/fence")
        if is_expired(lease["expires_at"]):
            raise GateDenied("Controller lease expired")
        if lease["boot_session_id"] != windows_boot_session_id():
            raise GateDenied("stale boot-session fence")
        return lease

    def reserve_effect(
        self,
        intent: dict[str, Any],
        *,
        controller_instance_id: str,
        controller_lease_id: str,
        authorization_id: str,
        context_fence: str,
        resource_id: str,
        resource_hash: str,
        capability_permitted: bool,
        egress_permitted: bool,
        resource_fresh: bool,
        faults: set[str] | None = None,
    ) -> Reservation:
        required = {
            "task_id",
            "operation",
            "provider",
            "destination",
            "expected_account",
            "resource",
            "payload_hash",
            "critical_params",
            "purpose",
            "logical_effect_slot",
            "retry_semantics",
            "impact",
            "reversibility",
            "effect_scope",
        }
        missing = sorted(required - intent.keys())
        if missing:
            raise GateDenied(f"incomplete effect intent: {missing}")
        if not capability_permitted or not egress_permitted or not resource_fresh:
            raise GateDenied("capability, egress, or resource precondition denied")
        task_id = str(intent["task_id"])
        goal = self.latest_goal(task_id)
        material = {
            "operation": intent["operation"],
            "provider": intent["provider"],
            "destination": intent["destination"],
            "expected_account": intent["expected_account"],
            "resource": intent["resource"],
            "payload_hash": intent["payload_hash"],
            "critical_params": intent["critical_params"],
            "purpose": intent["purpose"],
            "authorization_id": authorization_id,
            "goal_contract_hash": goal["contract_hash"],
            "logical_effect_slot": intent["logical_effect_slot"],
        }
        effect_intent_hash = sha256_text(canonical_json(material))
        logical_material = {
            "operation": intent["operation"],
            "provider": intent["provider"],
            "destination": intent["destination"],
            "expected_account": intent["expected_account"],
            "resource": intent["resource"],
            "payload_hash": intent["payload_hash"],
            "critical_params": intent["critical_params"],
            "purpose": intent["purpose"],
            "logical_effect_slot": intent["logical_effect_slot"],
        }
        logical_effect_id = sha256_text(
            canonical_json({"task_id": task_id, "logical_identity": logical_material})
        )
        existing = self.connection.execute(
            "SELECT a.* FROM actions a WHERE a.task_id=? AND a.logical_effect_id=?",
            (task_id, logical_effect_id),
        ).fetchone()
        if existing:
            if existing["status"] in ("OUTCOME_UNKNOWN", "RECONCILING"):
                recorded = self.connection.execute(
                    "SELECT controller_instance_id FROM reservations WHERE logical_effect_id=?",
                    (logical_effect_id,),
                ).fetchone()
                if recorded and recorded["controller_instance_id"] == controller_instance_id:
                    raise GateDenied(
                        "ordinary retry denied: the same logical effect has an unresolved "
                        "OUTCOME_UNKNOWN/RECONCILING action; reconciliation is required first"
                    )
            return Reservation(
                action_id=existing["action_id"],
                logical_effect_id=logical_effect_id,
                effect_intent_hash=existing["effect_intent_hash"],
                logical_effect_slot=existing["logical_effect_slot"],
                attempt_id=existing["attempt_id"],
                execution_fence_token=existing["execution_fence_token"],
                deduplicated=True,
                status=existing["status"],
            )

        action_id = str(uuid.uuid4())
        attempt_id = str(uuid.uuid4())
        now = utc_now()
        with self.transaction() as conn:
            self._lease(conn, controller_instance_id, controller_lease_id)
            if self.meta("authority_status") != "VERIFIED":
                raise AuthorityStateUncertain("authority recovery state is not VERIFIED")
            if self.meta("tcb_status") != "VERIFIED":
                raise GateDenied("Controller TCB is not VERIFIED")
            self.verify_authority_chain(faults=faults)
            # The optimistic pre-check above is only a latency shortcut. The
            # serialized transaction is the real atomic dedup authority.
            existing = conn.execute(
                "SELECT a.* FROM actions a WHERE a.task_id=? AND a.logical_effect_id=?",
                (task_id, logical_effect_id),
            ).fetchone()
            if existing:
                if existing["status"] in ("OUTCOME_UNKNOWN", "RECONCILING"):
                    recorded = conn.execute(
                        "SELECT controller_instance_id FROM reservations WHERE logical_effect_id=?",
                        (logical_effect_id,),
                    ).fetchone()
                    if recorded and recorded["controller_instance_id"] == controller_instance_id:
                        raise GateDenied(
                            "ordinary retry denied: the same logical effect has an unresolved "
                            "OUTCOME_UNKNOWN/RECONCILING action; reconciliation is required first"
                        )
                return Reservation(
                    action_id=existing["action_id"],
                    logical_effect_id=logical_effect_id,
                    effect_intent_hash=existing["effect_intent_hash"],
                    logical_effect_slot=existing["logical_effect_slot"],
                    attempt_id=existing["attempt_id"],
                    execution_fence_token=existing["execution_fence_token"],
                    deduplicated=True,
                    status=existing["status"],
                )
            revision = self.state_head()
            self.read_revision(revision)
            if self.current_context_fence(task_id) != context_fence:
                raise GateDenied("stale Context Fence")
            lock = conn.execute("SELECT * FROM locks WHERE resource_id=?", (resource_id,)).fetchone()
            if not lock or lock["controller_instance_id"] != controller_instance_id or is_expired(lock["expires_at"]):
                raise GateDenied("required resource lock/lease missing")
            auth = conn.execute("SELECT * FROM authorizations WHERE authorization_id=?", (authorization_id,)).fetchone()
            if not auth or auth["task_id"] != task_id:
                raise GateDenied("authorization missing or wrong task")
            reconstructed = self.reconstruct_authority(task_id)["authorizations"].get(authorization_id)
            if not reconstructed:
                raise AuthorityStateUncertain("authorization not reconstructable from Authority Journal")
            if auth["status"] != "ACTIVE" or reconstructed["status"] != "ACTIVE":
                raise GateDenied("authorization revoked or inactive")
            if is_expired(auth["expires_at"]):
                raise GateDenied("authorization expired")
            if auth["goal_contract_hash"] != goal["contract_hash"]:
                raise GateDenied("authorization bound to stale Goal Contract")
            if auth["provider"] not in (intent["provider"], "*"):
                raise GateDenied("authorization provider mismatch")
            if auth["purpose"] != intent["purpose"]:
                raise GateDenied("authorization purpose mismatch")
            epoch_row = conn.execute("SELECT epoch FROM revocation_epochs WHERE task_id=?", (task_id,)).fetchone()
            latest_epoch = int(epoch_row["epoch"]) if epoch_row else 0
            if int(auth["revocation_epoch"]) != latest_epoch:
                raise GateDenied("authorization revocation epoch stale")
            if int(auth["generation"]) != int(reconstructed["generation"]):
                raise AuthorityStateUncertain("authorization generation does not match latest durable journal")
            if int(auth["consumed_effect_count"]) != int(reconstructed["consumed_effect_count"]):
                raise AuthorityStateUncertain("authorization consumption does not match latest durable journal")
            if int(auth["consumed_effect_count"]) >= int(auth["max_effect_count"]):
                raise GateDenied("authorization capacity consumed")
            updated = conn.execute(
                "UPDATE authorizations SET consumed_effect_count=consumed_effect_count+1 WHERE authorization_id=? AND status='ACTIVE' AND consumed_effect_count<max_effect_count",
                (authorization_id,),
            )
            if updated.rowcount != 1:
                raise GateDenied("atomic authorization reservation lost race")
            consumed = int(auth["consumed_effect_count"]) + 1
            previous, generation = self._next_generation(conn, task_id, "authorization")
            conn.execute("UPDATE authorizations SET generation=? WHERE authorization_id=?", (generation, authorization_id))
            fence_material = {
                "controller_instance_id": controller_instance_id,
                "controller_lease_id": controller_lease_id,
                "state_revision": revision,
                "goal_contract_hash": goal["contract_hash"],
                "authorization_id": authorization_id,
                "authorization_generation": generation,
                "revocation_epoch": latest_epoch,
                "context_fence": context_fence,
                "resource_hash": resource_hash,
                "logical_effect_id": logical_effect_id,
                "attempt_id": attempt_id,
            }
            execution_fence_token = sha256_text(canonical_json(fence_material))
            self._append_authority_event(
                conn,
                event_type="AUTHORIZATION_CONSUMED",
                task_id=task_id,
                goal_version=int(goal["contract_version"]),
                goal_hash=goal["contract_hash"],
                authorization_id=authorization_id,
                decision_nonce=None,
                previous_generation=previous,
                new_generation=generation,
                scope_digest=auth["scope_digest"],
                state_revision=revision,
                data={
                    "consumed_effect_count": consumed,
                    "max_effect_count": int(auth["max_effect_count"]),
                    "logical_effect_id": logical_effect_id,
                    "attempt_id": attempt_id,
                },
                faults=faults,
            )
            conn.execute(
                "INSERT INTO actions(action_id,task_id,logical_effect_id,effect_intent_hash,logical_effect_slot,attempt_id,execution_fence_token,status,retry_semantics,impact,reversibility,effect_scope,provider,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    action_id,
                    task_id,
                    logical_effect_id,
                    effect_intent_hash,
                    intent["logical_effect_slot"],
                    attempt_id,
                    execution_fence_token,
                    "RESERVATION_COMMITTED",
                    intent["retry_semantics"],
                    intent["impact"],
                    intent["reversibility"],
                    intent["effect_scope"],
                    intent["provider"],
                    now,
                    now,
                ),
            )
            conn.execute(
                "INSERT INTO reservations(logical_effect_id,task_id,action_id,effect_intent_hash,logical_effect_slot,authorization_id,controller_instance_id,lease_id,state_revision,goal_contract_hash,authorization_generation,revocation_epoch,context_fence,resource_hash,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    logical_effect_id,
                    task_id,
                    action_id,
                    effect_intent_hash,
                    intent["logical_effect_slot"],
                    authorization_id,
                    controller_instance_id,
                    controller_lease_id,
                    revision,
                    goal["contract_hash"],
                    generation,
                    latest_epoch,
                    context_fence,
                    resource_hash,
                    "RESERVATION_COMMITTED",
                    now,
                    now,
                ),
            )
            self._append_wal(
                conn,
                action_id=action_id,
                logical_effect_id=logical_effect_id,
                status="RESERVATION_COMMITTED",
                record={**fence_material, "effect_intent_hash": effect_intent_hash},
                faults=faults,
            )
        self.confirm_security_durability(faults)
        return Reservation(
            action_id=action_id,
            logical_effect_id=logical_effect_id,
            effect_intent_hash=effect_intent_hash,
            logical_effect_slot=intent["logical_effect_slot"],
            attempt_id=attempt_id,
            execution_fence_token=execution_fence_token,
            deduplicated=False,
            status="RESERVATION_COMMITTED",
        )

    def start_effect(
        self,
        reservation: Reservation,
        *,
        controller_instance_id: str,
        controller_lease_id: str,
        resource_fresh: bool,
        faults: set[str] | None = None,
    ) -> None:
        if reservation.deduplicated:
            raise GateDenied("deduplicated effect must not cross external boundary again")
        with self.transaction() as conn:
            self._lease(conn, controller_instance_id, controller_lease_id)
            if self.meta("authority_status") != "VERIFIED" or self.meta("tcb_status") != "VERIFIED":
                raise GateDenied("authority or Controller TCB is not verified")
            self.verify_authority_chain(faults=faults)
            row = conn.execute(
                "SELECT r.*,a.status AS action_status,a.execution_fence_token AS durable_fence"
                " FROM reservations r JOIN actions a ON a.action_id=r.action_id WHERE r.logical_effect_id=?",
                (reservation.logical_effect_id,),
            ).fetchone()
            if not row or row["status"] != "RESERVATION_COMMITTED":
                raise GateDenied("reservation not executable")
            if row["durable_fence"] != reservation.execution_fence_token:
                raise GateDenied("execution fence token does not match the durable reservation")
            if not resource_fresh:
                raise GateDenied("resource became stale before external boundary")
            auth = conn.execute("SELECT * FROM authorizations WHERE authorization_id=?", (row["authorization_id"],)).fetchone()
            reconstructed = self.reconstruct_authority(row["task_id"])["authorizations"].get(row["authorization_id"])
            epoch_row = conn.execute("SELECT epoch FROM revocation_epochs WHERE task_id=?", (row["task_id"],)).fetchone()
            latest_epoch = int(epoch_row["epoch"]) if epoch_row else 0
            head_row = conn.execute("SELECT revision FROM state_head WHERE singleton=1").fetchone()
            goal = self.latest_goal(row["task_id"])
            if not auth or not reconstructed or auth["status"] != "ACTIVE" or reconstructed["status"] != "ACTIVE":
                raise GateDenied("authorization revoked before effect start")
            if head_row is None or int(row["state_revision"]) != int(head_row["revision"]):
                raise GateDenied("canonical state revision is no longer current")
            if int(row["revocation_epoch"]) != latest_epoch:
                raise GateDenied("stale execution fence after revocation")
            if int(row["authorization_generation"]) != int(auth["generation"]):
                raise GateDenied("stale execution fence after authority generation change")
            latest_generation = conn.execute(
                "SELECT MAX(generation) AS value FROM authorizations WHERE task_id=?", (row["task_id"],)
            ).fetchone()["value"]
            if latest_generation is not None and int(row["authorization_generation"]) != int(latest_generation):
                raise GateDenied("authorization generation is not the latest durable task generation")
            if row["goal_contract_hash"] != goal["contract_hash"]:
                raise GateDenied("Goal Contract changed before effect start")
            if row["controller_instance_id"] != controller_instance_id or row["lease_id"] != controller_lease_id:
                raise GateDenied("stale Controller execution fence")
            now = utc_now()
            conn.execute(
                "UPDATE reservations SET status='EFFECT_START_COMMITTED',updated_at=? WHERE logical_effect_id=?",
                (now, reservation.logical_effect_id),
            )
            conn.execute(
                "UPDATE actions SET status='EFFECT_START_COMMITTED',updated_at=? WHERE action_id=?",
                (now, reservation.action_id),
            )
            self._append_wal(
                conn,
                action_id=reservation.action_id,
                logical_effect_id=reservation.logical_effect_id,
                status="EFFECT_START_COMMITTED",
                record={
                    "execution_fence_token": reservation.execution_fence_token,
                    "authorization_generation": row["authorization_generation"],
                    "revocation_epoch": row["revocation_epoch"],
                    "state_revision": row["state_revision"],
                },
                faults=faults,
            )
        self.confirm_security_durability(faults)

    def finish_effect(self, reservation: Reservation, outcome: dict[str, Any], *, unknown: bool = False) -> None:
        status = "OUTCOME_UNKNOWN" if unknown else "ACTION_COMMITTED"
        with self.transaction() as conn:
            row = conn.execute("SELECT status FROM actions WHERE action_id=?", (reservation.action_id,)).fetchone()
            if not row or row["status"] != "EFFECT_START_COMMITTED":
                raise GateDenied("effect outcome cannot be committed from current state")
            now = utc_now()
            conn.execute(
                "UPDATE reservations SET status=?,updated_at=? WHERE logical_effect_id=?",
                (status, now, reservation.logical_effect_id),
            )
            conn.execute(
                "UPDATE actions SET status=?,updated_at=?,outcome_json=? WHERE action_id=?",
                (status, now, canonical_json(outcome), reservation.action_id),
            )
            self._append_wal(
                conn,
                action_id=reservation.action_id,
                logical_effect_id=reservation.logical_effect_id,
                status=status,
                record={"outcome": outcome, "auto_retry_permitted": False if unknown else None},
            )
        self.durable_barrier()

    def record_invocation(self, record: dict[str, Any]) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO invocations(invocation_id,request_nonce,expected_actor_id,actor_type,task_id,goal_contract_hash,state_revision,context_fence,trust_class,capability_json,result_channel,process_session_identity,created_at,expires_at,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record["invocation_id"],
                    record["request_nonce"],
                    record["expected_actor_id"],
                    record["actor_type"],
                    record["task_id"],
                    record["goal_contract_hash"],
                    record["state_revision"],
                    record["context_fence"],
                    record["trust_class"],
                    canonical_json(record.get("capability", {})),
                    record["result_channel"],
                    record["process_session_identity"],
                    record["created_at"],
                    record["expires_at"],
                    record.get("status", "CREATED"),
                ),
            )
        self.durable_barrier()

    def verify_and_record_result(
        self,
        invocation_id: str,
        envelope: dict[str, Any],
        source_binding: dict[str, Any],
    ) -> dict[str, Any]:
        invocation = self.connection.execute("SELECT * FROM invocations WHERE invocation_id=?", (invocation_id,)).fetchone()
        if not invocation or invocation["status"] not in ("CREATED", "RUNNING"):
            raise GateDenied("result has no live invocation receipt")
        if is_expired(invocation["expires_at"]):
            raise GateDenied("invocation receipt expired")
        if envelope.get("invocation_id") != invocation_id or envelope.get("request_nonce") != invocation["request_nonce"]:
            raise GateDenied("result invocation/nonce mismatch")
        if envelope.get("task_id") != invocation["task_id"]:
            raise GateDenied("result task mismatch")
        if envelope.get("goal_contract_hash") != invocation["goal_contract_hash"]:
            raise GateDenied("result Goal Contract stale")
        if envelope.get("request_state_revision") != invocation["state_revision"]:
            raise GateDenied("result Canonical State stale")
        if envelope.get("request_context_fence") != invocation["context_fence"]:
            raise GateDenied("result Context Fence stale")
        if self.state_head() != int(invocation["state_revision"]):
            raise GateDenied("result Canonical State is no longer current")
        current_goal = self.latest_goal(invocation["task_id"])
        if current_goal["contract_hash"] != invocation["goal_contract_hash"]:
            raise GateDenied("result Goal Contract is no longer current")
        if self.current_context_fence(invocation["task_id"]) != invocation["context_fence"]:
            raise GateDenied("result Context Fence is no longer current")
        if source_binding.get("actor_id") != invocation["expected_actor_id"]:
            raise GateDenied("result actor source mismatch")
        validate_actor_trajectory(str(invocation["actor_type"]), envelope)
        result_id = str(uuid.uuid4())
        digest = sha256_text(canonical_json(envelope))
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO results(result_id,invocation_id,actor_id,source_binding_json,envelope_json,envelope_hash,verification_status,received_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    result_id,
                    invocation_id,
                    source_binding["actor_id"],
                    canonical_json(source_binding),
                    canonical_json(envelope),
                    digest,
                    "VERIFIED",
                    utc_now(),
                ),
            )
            conn.execute("UPDATE invocations SET status='COMPLETED' WHERE invocation_id=?", (invocation_id,))
        self.durable_barrier()
        return {"result_id": result_id, "envelope_hash": digest, "verification_status": "VERIFIED"}

    def register_process(self, record: dict[str, Any]) -> str:
        process_record_id = str(uuid.uuid4())
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO processes(process_record_id,invocation_id,process_id,process_start_identity,controller_instance_id,task_id,action_id,logical_effect_id,parent_process_id,job_or_group,lifetime,effect_class,record_json,started_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    process_record_id,
                    record.get("invocation_id"),
                    record["pid"],
                    record["process_start_identity"],
                    record["controller_instance_id"],
                    record["task_id"],
                    record.get("action_id"),
                    record.get("logical_effect_id"),
                    os.getpid(),
                    "WINDOWS_JOB_OBJECT",
                    record.get("lifetime", "INVOCATION"),
                    record.get("effect_class", "LOCAL"),
                    canonical_json(record),
                    record["started_at"],
                ),
            )
        return process_record_id

    def upsert_registry(self, table: str, key_name: str, key_value: str, value: dict[str, Any]) -> None:
        if table not in ("worker_registry", "brain_registry", "provider_registry", "reviewer_registry", "tool_registry"):
            raise ValueError("invalid registry")
        with self.transaction() as conn:
            row = conn.execute(f"SELECT generation FROM {table} WHERE {key_name}=?", (key_value,)).fetchone()
            generation = int(row["generation"]) + 1 if row else 1
            conn.execute(
                f"INSERT INTO {table}({key_name},registry_json,generation,updated_at) VALUES(?,?,?,?) ON CONFLICT({key_name}) DO UPDATE SET registry_json=excluded.registry_json,generation=excluded.generation,updated_at=excluded.updated_at",
                (key_value, canonical_json(value), generation, utc_now()),
            )
        self.durable_barrier()

    def registry(self, table: str) -> list[dict[str, Any]]:
        if table not in ("worker_registry", "brain_registry", "provider_registry", "reviewer_registry", "tool_registry"):
            raise ValueError("invalid registry")
        return [
            {**json.loads(row["registry_json"]), "generation": row["generation"], "updated_at": row["updated_at"]}
            for row in self.connection.execute(f"SELECT * FROM {table} ORDER BY 1")
        ]

    def record_progress_signature(self, task_id: str, signature: str, *, substantive_progress: bool) -> dict[str, Any]:
        with self.transaction() as conn:
            row = conn.execute("SELECT MAX(sequence) AS value FROM progress_signatures WHERE task_id=?", (task_id,)).fetchone()
            sequence = int(row["value"] or 0) + 1
            conn.execute(
                "INSERT INTO progress_signatures(task_id,sequence,signature,substantive_progress,created_at) VALUES(?,?,?,?,?)",
                (task_id, sequence, signature, 1 if substantive_progress else 0, utc_now()),
            )
            recent = list(
                conn.execute(
                    "SELECT signature,substantive_progress FROM progress_signatures WHERE task_id=? ORDER BY sequence DESC LIMIT 3",
                    (task_id,),
                )
            )
        blocked = (
            len(recent) == 3
            and len({item["signature"] for item in recent}) == 1
            and all(int(item["substantive_progress"]) == 0 for item in recent)
        )
        return {"task_id": task_id, "sequence": sequence, "status": "BLOCKED_NO_PROGRESS" if blocked else "CONTINUE"}

    def migrate_schema(self, migration_id: str, from_version: int, to_version: int, statements: list[str]) -> dict[str, Any]:
        if int(self.meta("schema_version", "0") or "0") != from_version:
            raise ControlError("migration source version mismatch")
        try:
            with self.transaction() as conn:
                for statement in statements:
                    conn.execute(statement)
                self.set_meta("schema_version", str(to_version), conn)
                conn.execute(
                    "INSERT INTO migration_history(migration_id,from_version,to_version,status,evidence_json,created_at) VALUES(?,?,?,?,?,?)",
                    (migration_id, from_version, to_version, "COMMITTED", canonical_json({"statements": len(statements)}), utc_now()),
                )
        except Exception:
            if int(self.meta("schema_version", "0") or "0") != from_version:
                raise ControlError("migration failure did not preserve prior version")
            raise
        state = self.read_state()
        state["schema_version"] = to_version
        revision = self.commit_state(state, reason=f"SCHEMA_MIGRATION_{migration_id}")
        self.durable_barrier()
        return {"migration_id": migration_id, "from_version": from_version, "to_version": to_version, "state_revision": revision}

    def record_evidence(
        self,
        *,
        task_id: str,
        classification: str,
        kind: str,
        path: str,
        sha256: str,
        metadata: dict[str, Any],
    ) -> str:
        evidence_id = str(uuid.uuid4())
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO evidence(evidence_id,task_id,classification,kind,path,sha256,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (evidence_id, task_id, classification, kind, path, sha256, canonical_json(metadata), utc_now()),
            )
        self.durable_barrier()
        return evidence_id

    def evidence_for_path(self, *, task_id: str, kind: str, path: str, sha256: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM evidence WHERE task_id=? AND kind=? AND path=? AND sha256=? ORDER BY created_at DESC LIMIT 1",
            (task_id, kind, path, sha256),
        ).fetchone()
        if not row:
            raise GateDenied(f"canonical {kind} evidence record missing")
        value = dict(row)
        value["metadata"] = json.loads(value.pop("metadata_json"))
        return value

    def record_test(self, record: dict[str, Any]) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO test_executions(
                  test_execution_id,case_id,definition_version,task_id,goal_contract_hash,state_revision,tested_artifact_digest,
                  controller_instance_id,process_browser_identity,invocation_json,started_at,finished_at,exit_or_observed_result,
                  evidence_json,evidence_hashes_json,verification_status,requirement_class
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record["test_execution_id"],
                    record["case_id"],
                    record["definition_version"],
                    record["task_id"],
                    record["goal_contract_hash"],
                    record["state_revision"],
                    record["tested_artifact_digest"],
                    record["controller_instance_id"],
                    record["process_browser_identity"],
                    canonical_json(record.get("invocation", {})),
                    record["started_at"],
                    record["finished_at"],
                    record["exit_or_observed_result"],
                    canonical_json(record.get("evidence", [])),
                    canonical_json(record.get("evidence_hashes", {})),
                    record["verification_status"],
                    record["requirement_class"],
                ),
            )
        self.durable_barrier()

    def tests(self, task_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute("SELECT * FROM test_executions WHERE task_id=? ORDER BY case_id", (task_id,))]

    def test_execution(self, test_execution_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM test_executions WHERE test_execution_id=?", (test_execution_id,)
        ).fetchone()
        if not row:
            raise GateDenied("canonical test execution missing")
        value = dict(row)
        value["evidence"] = json.loads(value.pop("evidence_json"))
        value["evidence_hashes"] = json.loads(value.pop("evidence_hashes_json"))
        value["invocation"] = json.loads(value.pop("invocation_json"))
        return value

    def verified_result(self, result_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            """SELECT r.*,i.task_id AS invocation_task_id,i.goal_contract_hash AS invocation_goal_contract_hash,
                      i.state_revision AS invocation_state_revision,i.context_fence AS invocation_context_fence,
                      i.expected_actor_id,i.actor_type,i.status AS invocation_status
               FROM results r JOIN invocations i ON i.invocation_id=r.invocation_id
               WHERE r.result_id=?""",
            (result_id,),
        ).fetchone()
        if not row or row["verification_status"] != "VERIFIED" or row["invocation_status"] != "COMPLETED":
            raise GateDenied("verified canonical actor result missing")
        value = dict(row)
        value["source_binding"] = json.loads(value.pop("source_binding_json"))
        value["envelope"] = json.loads(value.pop("envelope_json"))
        return value

    def committed_effect(self, *, action_id: str, logical_effect_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            """SELECT a.*,r.task_id AS reservation_task_id,r.goal_contract_hash,r.state_revision,
                      r.context_fence,r.authorization_id,r.status AS reservation_status
               FROM actions a JOIN reservations r ON r.action_id=a.action_id AND r.logical_effect_id=a.logical_effect_id
               WHERE a.action_id=? AND a.logical_effect_id=?""",
            (action_id, logical_effect_id),
        ).fetchone()
        if not row or row["status"] != "ACTION_COMMITTED" or row["reservation_status"] != "ACTION_COMMITTED":
            raise GateDenied("review is not bound to a committed external effect")
        value = dict(row)
        value["outcome"] = json.loads(value.pop("outcome_json"))
        return value

    def create_release_candidate(self, record: dict[str, Any]) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO release_candidates(
                  release_candidate_id,task_id,goal_contract_hash,state_revision,artifact_kind,artifact_path,artifact_digest,
                  artifact_size,tree_manifest_json,test_evidence_json,review_evidence_json,acceptance_manifest_hash,created_at,status
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record["release_candidate_id"],
                    record["task_id"],
                    record["goal_contract_hash"],
                    record["state_revision"],
                    record["artifact_kind"],
                    record["artifact_path"],
                    record["artifact_digest"],
                    record["artifact_size"],
                    canonical_json(record["tree_manifest"]),
                    canonical_json(record["test_evidence"]),
                    canonical_json(record["review_evidence"]),
                    record["acceptance_manifest_hash"],
                    record["created_at"],
                    record["status"],
                ),
            )
        self.durable_barrier()

    def mark_delivered(self, release_candidate_id: str, delivered_digest: str) -> None:
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT artifact_digest,status FROM release_candidates WHERE release_candidate_id=?", (release_candidate_id,)
            ).fetchone()
            if not row or row["status"] != "VERIFIED" or row["artifact_digest"] != delivered_digest:
                raise GateDenied("delivered digest does not match a VERIFIED release candidate")
            conn.execute(
                "UPDATE release_candidates SET status='DELIVERED',delivered_digest=? WHERE release_candidate_id=?",
                (delivered_digest, release_candidate_id),
            )
        self.durable_barrier()
