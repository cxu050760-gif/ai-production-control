from __future__ import annotations

"""M2/M3 Goal pipeline: recoverable, directive-gated, auto-REWORK E2E harness.

Assembles the durable primitives into a single Goal execution loop:
  PLAN -> ITERATE(execute -> test -> review) -> DELIVER

Mechanics:
  - step state is durable in the shared `Workflow` table (fenced claim, crash
    reconcile, REWORK edge), so calling run() again after a partial/crash
    continues from the same canonical state (idempotent resume) instead of
    restarting.
  - a PENDING PAUSE/STOP/CHANGE_SCOPE directive gates dispatch (durable-first).
  - ITERATE returns DONE only when test AND reviewer PASS; otherwise REWORK
    re-dispatches the same step (auto-返工 + retest + re-review). Exceeding the
    retry budget, or an UNKNOWN/BLOCKED reviewer outcome, fails closed to BLOCKED
    (never a fabricated pass).
  - DELIVER writes the artifact to a release dir and records canonical Evidence.

Reviewer/worker are injected callables so the mechanism is provable
deterministically offline; an injected reviewer is a TEST STAND-IN, never an
independent review, so a run's PASS here is E2E/mechanism evidence only and is
NOT used to mark any milestone independently reviewed.
"""

import shutil
import uuid
from pathlib import Path
from typing import Any, Callable

from .directives import has_work_gate
from .store import ControlStore
from .util import canonical_json, sha256_file, sha256_text, utc_now
from .workflow import OUTCOME_DONE, OUTCOME_REWORK, OUTCOME_UNKNOWN, Workflow

PLAN = "plan"
ITERATE = "iterate"
DELIVER = "deliver"


def _outcome_rework(findings: list[str]) -> dict[str, Any]:
    return {"kind": OUTCOME_REWORK, "findings": findings}


class GoalPipeline:
    """A resumable, directive-gated Goal pipeline over the shared workflow."""

    def __init__(
        self,
        store: ControlStore,
        *,
        task_id: str,
        objective: str,
        artifact: Path,
        release_root: Path,
        work: Callable[[int, Path], None],
        test: Callable[[Path], tuple[bool, list[str]]],
        review: Callable[[Path], dict[str, Any]],
        retry_budget: int = 3,
    ) -> None:
        self.store = store
        self.task_id = task_id
        self.objective = objective
        self.artifact = Path(artifact)
        self.release_root = Path(release_root)
        self.work = work
        self.test = test
        self.review = review
        self.retry_budget = retry_budget
        self.workflow = Workflow(store)
        self._artifact = str(self.artifact)
        self._wfid = None

    def _meta(self, key: str, default: str | None = None) -> str | None:
        return self.store.meta(f"pipeline:{self.task_id}:{key}", default)

    def _set_meta(self, key: str, value: str) -> None:
        self.store.set_meta(f"pipeline:{self.task_id}:{key}", value)
        self.store.durable_barrier()

    def _ensure(self) -> str:
        wfid = self._meta("workflow_id")
        if wfid:
            return wfid
        wfid = self.workflow.create_workflow(self.objective, project_id=self.task_id)["workflow_id"]
        plan = self.workflow.add_step(wfid, PLAN, kind="PLAN")
        iterate = self.workflow.add_step(
            wfid, ITERATE, kind=ITERATE, depends_on=[plan["step_id"]], retry_budget=self.retry_budget
        )
        self.workflow.add_step(wfid, DELIVER, kind="DELIVER", depends_on=[iterate["step_id"]])
        self._set_meta("workflow_id", wfid)
        return wfid

    def run(self, *, limit_steps: int | None = None) -> dict[str, Any]:
        wfid = self._ensure()
        artifact = Path(self._artifact)
        artifact.parent.mkdir(parents=True, exist_ok=True)
        delivered = 0
        handled = 0
        while limit_steps is None or handled < limit_steps:
            blocked, reason = has_work_gate(self.store, task_id=self.task_id)
            if blocked:
                return {"status": "BLOCKED_BY_DIRECTIVE", "reason": reason, "handled": handled}
            runnable = self.workflow.next_runnable(wfid)
            if not runnable:
                break
            step = runnable[0]
            name = step["name"]
            if name == PLAN:
                self.workflow.claim_step(step["step_id"], owner=self.task_id, process_start_identity="pipeline")
                self.workflow.finish_step(step["step_id"], fence=f"{self.task_id}::pipeline", outcome={"kind": OUTCOME_DONE})
                handled += 1
                continue
            if name == ITERATE:
                claim = self.workflow.claim_step(step["step_id"], owner=self.task_id, process_start_identity="pipeline")
                attempt = int(step["attempt"])
                self.work(attempt, artifact)
                outcome = self._iterate_outcome(artifact)
                self.workflow.finish_step(step["step_id"], fence=claim["claim"], outcome=outcome)
                handled += 1
                if outcome.get("kind") == OUTCOME_UNKNOWN:
                    return {"status": "BLOCKED", "reason": "iterate failed closed", "handled": handled}
                continue
            if name == DELIVER:
                claim = self.workflow.claim_step(step["step_id"], owner=self.task_id, process_start_identity="pipeline")
                self._deliver(artifact)
                self.workflow.finish_step(step["step_id"], fence=claim["claim"], outcome={"kind": OUTCOME_DONE})
                delivered += 1
                handled += 1
                continue
        status = self.workflow.run_status(wfid)
        if delivered:
            return {"status": "COMPLETE", "delivered": True, "run_status": status, "handled": handled}
        blocked_step = next((s for s in status["steps"] if s["status"] == "BLOCKED"), None)
        if blocked_step:
            return {"status": "BLOCKED", "step": blocked_step["step_id"], "run_status": status, "handled": handled}
        waiting = next((s for s in status["steps"] if s["status"] in ("WAITING",)), None)
        if waiting:
            return {"status": "WAITING", "step": waiting["step_id"], "run_status": status, "handled": handled}
        return {"status": "RUNNING", "run_status": status, "handled": handled}

    def _iterate_outcome(self, artifact: Path) -> dict[str, Any]:
        ok, test_findings = self.test(artifact)
        if not ok:
            return _outcome_rework(test_findings or ["test failed"])
        verdict = self.review(artifact)
        v = str(verdict.get("verdict", "")).upper()
        if v == "PASS":
            return {"kind": OUTCOME_DONE}
        if v == "REWORK":
            return _outcome_rework(verdict.get("findings") or ["review feedback"])
        # BLOCKED or any unknown verdict -> fail-closed
        return {"kind": OUTCOME_UNKNOWN, "detail": f"reviewer non-pass/non-rework: {v}"}

    def _deliver(self, artifact: Path) -> str:
        self.release_root.mkdir(parents=True, exist_ok=True)
        delivered = self.release_root / ("delivery-" + uuid.uuid4().hex[:8] + artifact.suffix)
        shutil.copy2(artifact, delivered)
        digest = sha256_file(delivered)
        record = {
            "pipeline": "goal",
            "task_id": self.task_id,
            "objective": self.objective,
            "delivered_path": str(delivered),
            "delivered_sha256": digest,
            "delivered_at": utc_now(),
            # This is E2E / mechanism evidence. It is NOT an independent review.
            "review_status": "MECHANISM_E2E_STAND_IN_REVIEWER",
        }
        evidence_path = self.release_root / ("delivery-evidence-" + uuid.uuid4().hex[:8] + ".json")
        from .util import write_json

        write_json(evidence_path, record)
        self.store.record_evidence(
            task_id=self.task_id,
            classification="INTERNAL",
            kind="GOAL_PIPELINE_DELIVERY",
            path=str(evidence_path),
            sha256=sha256_file(evidence_path),
            metadata={"delivered_sha256": digest, "objective": self.objective},
        )
        self._set_meta("delivered_digest", digest)
        return str(delivered)