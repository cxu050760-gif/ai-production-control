from __future__ import annotations

"""M2 durable Workflow tests.

Proves the invariants the FINAL product depends on:
- atomic, fenced step claim (no double-claim by a different owner),
- dependency gate (a step is not claimable until its deps are DONE),
- REWORK feedback edge auto-requeues the step for re-execution,
- retry budget exhausted -> fail-closed BLOCKED,
- a step WAITING on an external result does NOT stop unrelated READY work
  (non-blocking pipeline),
- crash reconciliation makes a stale-claimed step READY again (idempotent resume),
- unknown/malformed outcome is fail-closed BLOCKED.
"""

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aicontrol.store import ControlStore  # noqa: E402
from aicontrol.workflow import (  # noqa: E402
    OUTCOME_DONE,
    OUTCOME_REWORK,
    OUTCOME_UNKNOWN,
    OUTCOME_WAIT,
    STEP_BLOCKED,
    STEP_CLAIMED,
    STEP_DONE,
    STEP_READY,
    STEP_REWORK,
    STEP_WAITING,
    StepNotClaimable,
    Workflow,
)


class WorkflowFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="aicontrol-wf-")
        self.root = Path(self.temporary.name)
        self.store = ControlStore(self.root / "control.db", state_root=self.root / "state")
        self.store.set_meta("tcb_status", "VERIFIED")
        self.wf = Workflow(self.store, heartbeat_ttl_sec=0.2)
        self.project = self.wf.create_workflow("build final product")
        self.owner = f"controller-{uuid.uuid4()}"
        self.psi = uuid.uuid4().hex

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()


class WorkflowTests(WorkflowFixture):
    def test_atomic_claim_is_fenced(self) -> None:
        step = self.wf.add_step(self.project["workflow_id"], "execute")
        self.wf.claim_step(step["step_id"], owner=self.owner, process_start_identity=self.psi)
        other = {"owner": "other-controller", "psi": uuid.uuid4().hex}
        with self.assertRaises(StepNotClaimable):
            self.wf.claim_step(step["step_id"], owner=other["owner"], process_start_identity=other["psi"])

    def test_dependency_gate(self) -> None:
        wfid = self.project["workflow_id"]
        a = self.wf.add_step(wfid, "plan")
        b = self.wf.add_step(wfid, "execute", depends_on=[a["step_id"]])
        with self.assertRaises(StepNotClaimable):
            self.wf.claim_step(b["step_id"], owner=self.owner, process_start_identity=self.psi)
        claim_a = self.wf.claim_step(a["step_id"], owner=self.owner, process_start_identity=self.psi)
        self.wf.finish_step(a["step_id"], fence=claim_a["claim"], outcome={"kind": OUTCOME_DONE})
        self.wf.claim_step(b["step_id"], owner=self.owner, process_start_identity=self.psi)

    def test_run_done(self) -> None:
        step = self.wf.add_step(self.project["workflow_id"], "execute")
        claim = self.wf.claim_step(step["step_id"], owner=self.owner, process_start_identity=self.psi)
        self.assertEqual(self.wf.run_status(self.project["workflow_id"])["steps"][0]["status"], STEP_CLAIMED)
        out = self.wf.finish_step(step["step_id"], fence=claim["claim"], outcome={"kind": OUTCOME_DONE})
        self.assertEqual(out["status"], STEP_DONE)

    def test_rework_done_and_budget_exhausted(self) -> None:
        wfid = self.project["workflow_id"]
        step = self.wf.add_step(wfid, "build", retry_budget=2)
        # first attempt -> REWORK, auto-requeued
        c1 = self.wf.claim_step(step["step_id"], owner=self.owner, process_start_identity=self.psi)
        r1 = self.wf.finish_step(step["step_id"], fence=c1["claim"], outcome={"kind": OUTCOME_REWORK, "findings": ["fix 1"]})
        self.assertEqual(r1["status"], STEP_REWORK)
        runnable = self.wf.next_runnable(wfid)
        self.assertTrue(any(s["step_id"] == step["step_id"] for s in runnable), "REWORK step must be requeued")
        # second attempt -> DONE
        c2 = self.wf.claim_step(step["step_id"], owner=self.owner, process_start_identity=self.psi)
        r2 = self.wf.finish_step(step["step_id"], fence=c2["claim"], outcome={"kind": OUTCOME_DONE})
        self.assertEqual(r2["status"], STEP_DONE)

    def test_rework_over_budget_fail_closed(self) -> None:
        wfid = self.project["workflow_id"]
        step = self.wf.add_step(wfid, "fragile", retry_budget=2)
        final = None
        for _ in range(3):
            claim = self.wf.claim_step(step["step_id"], owner=self.owner, process_start_identity=self.psi)
            final = self.wf.finish_step(step["step_id"], fence=claim["claim"],
                                        outcome={"kind": OUTCOME_REWORK, "findings": ["again"]})
        self.assertEqual(final["status"], STEP_BLOCKED)

    def test_wait_does_not_block_unrelated_ready_work(self) -> None:
        wfid = self.project["workflow_id"]
        w = self.wf.add_step(wfid, "upload-to-website")
        independent = self.wf.add_step(wfid, "local-transform")
        claim_w = self.wf.claim_step(w["step_id"], owner=self.owner, process_start_identity=self.psi)
        self.wf.finish_step(w["step_id"], fence=claim_w["claim"], outcome={"kind": OUTCOME_WAIT, "reason": "await external result"})
        runnable = [s["step_id"] for s in self.wf.next_runnable(wfid)]
        # the independent step is still runnable even though another step is WAITING
        self.assertIn(independent["step_id"], runnable)
        self.assertNotIn(w["step_id"], runnable)

    def test_crash_reconcile_resumes_claim(self) -> None:
        step = self.wf.add_step(self.project["workflow_id"], "task")
        self.wf.claim_step(step["step_id"], owner="dead-controller", process_start_identity="dead-psi")
        # wait past the stale heartbeat threshold, then reconcile from a new owner
        import time as _t

        _t.sleep(0.25)
        result = self.wf.reconcile(owner=self.owner, process_start_identity=self.psi)
        self.assertIn(step["step_id"], result["reclaimed"])
        # now idempotently re-claimable
        self.wf.claim_step(step["step_id"], owner=self.owner, process_start_identity=self.psi)

    def test_unknown_outcome_fail_closed(self) -> None:
        step = self.wf.add_step(self.project["workflow_id"], "task")
        claim = self.wf.claim_step(step["step_id"], owner=self.owner, process_start_identity=self.psi)
        out = self.wf.finish_step(step["step_id"], fence=claim["claim"],
                                  outcome={"kind": OUTCOME_UNKNOWN, "detail": "no verdict"})
        self.assertEqual(out["status"], STEP_BLOCKED)


if __name__ == "__main__":
    unittest.main()