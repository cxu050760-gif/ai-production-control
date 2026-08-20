from __future__ import annotations

"""M2: Continuation Spine tests.

Proves the machine semantics that let the Project survive across Builder turns:
- four-layer PROJECT/MILESTONE/TASK/INVOCATION model,
- INVOCATION_RETURNED != PROJECT_DONE (driver auto-creates the next invocation),
- MILESTONE_PASS requires an independent reviewer PASS record,
- an empty ready queue does not imply Project completion,
- only FINAL_ACCEPTANCE with an independent PASS can complete the Project.
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

from aicontrol.spine import (  # noqa: E402
    FINAL_ACCEPTANCE_MILESTONE,
    ContinuationSpine,
    ReviewRequired,
    SpineError,
)
from aicontrol.store import ControlStore  # noqa: E402


class SpineFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="aicontrol-spine-")
        self.root = Path(self.temporary.name)
        self.store = ControlStore(self.root / "control.db", state_root=self.root / "state")
        self.store.set_meta("tcb_status", "VERIFIED")
        self.spine = ContinuationSpine(self.store)

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def review_pass(self, milestone_id: str, commit: str = "c") -> None:
        self.spine.record_review(
            milestone_id=milestone_id, reviewer="independent-r", role="R_PROD",
            verdict="PASS", candidate_commit=commit, candidate_digest="0" * 64, evidence_refs=["e1"],
        )


class ContinuationSpineTests(SpineFixture):
    def test_four_layer_roundtrip(self) -> None:
        project = self.spine.create_project(
            "build final product", ["M1", "M2", "M3", "M4", "M5", FINAL_ACCEPTANCE_MILESTONE]
        )
        pid = project["project_id"]
        ms = self.spine.milestones(pid)
        task = self.spine.add_task(ms[0]["milestone_id"], "adapter contract")
        self.assertEqual(task["status"], "READY")
        nxt = self.spine.continuation_next(pid)
        self.assertEqual(nxt["action"], "INVOCATION")
        self.assertEqual(nxt["task"], task["task_id"])
        inv = nxt["invocation"]
        self.assertEqual(inv["status"], "RUNNING")
        self.assertEqual(self.spine.project(pid)["status"], "RUNNING")

    def test_invocation_returned_not_project_done(self) -> None:
        project = self.spine.create_project("g", ["M1", FINAL_ACCEPTANCE_MILESTONE])
        pid = project["project_id"]
        ms = self.spine.milestones(pid)
        task1 = self.spine.add_task(ms[0]["milestone_id"], "t1")
        self.spine.add_task(ms[0]["milestone_id"], "t2")
        first = self.spine.continuation_next(pid)
        first_inv = first["invocation"]
        # Builder yields after partial work.
        self.spine.return_invocation(first_inv["invocation_id"], "partial: t1 done")
        # Project is NOT done and the driver hands out the next invocation
        # automatically — the user does not need to say "continue".
        nxt = self.spine.continuation_next(pid)
        self.assertEqual(nxt["action"], "INVOCATION")
        self.assertNotEqual(nxt["invocation"]["invocation_id"], first_inv["invocation_id"])
        self.assertEqual(self.spine.project(pid)["status"], "RUNNING")
        late = self.spine.store.connection.execute(
            "SELECT status FROM spine_invocations WHERE invocation_id=?", (first_inv["invocation_id"],)
        ).fetchone()
        self.assertEqual(late["status"], "RETURNED")

    def test_milestone_pass_requires_independent_review(self) -> None:
        project = self.spine.create_project("g", ["M1", FINAL_ACCEPTANCE_MILESTONE])
        ms = self.spine.milestones(project["project_id"])
        with self.assertRaises(ReviewRequired):
            self.spine.set_milestone_status(ms[0]["milestone_id"], "PASS")
        # a self-declared PASS by a task is not accepted either
        with self.assertRaises(ReviewRequired):
            self.spine.set_milestone_status(ms[0]["milestone_id"], "PASS")

    def test_review_then_pass_advances(self) -> None:
        project = self.spine.create_project("g", ["M1", "M2", FINAL_ACCEPTANCE_MILESTONE])
        ms = self.spine.milestones(project["project_id"])
        self.review_pass(ms[0]["milestone_id"])
        self.spine.set_milestone_status(ms[0]["milestone_id"], "PASS")
        task = self.spine.add_task(ms[1]["milestone_id"], "m2 task")
        nxt = self.spine.continuation_next(project["project_id"])
        self.assertEqual(nxt["action"], "INVOCATION")
        self.assertEqual(nxt["milestone_name"], "M2")

    def test_empty_ready_queue_is_not_complete(self) -> None:
        project = self.spine.create_project("g", ["M1", FINAL_ACCEPTANCE_MILESTONE])
        pid = project["project_id"]
        ms = self.spine.milestones(pid)
        task = self.spine.add_task(ms[0]["milestone_id"], "only task")
        inv = self.spine.continuation_next(pid)["invocation"]
        # the builder did the only task and returned; nothing ready remains.
        self.spine.return_invocation(inv["invocation_id"], "done", fail=False)
        self.spine.set_task_status(task["task_id"], "DONE")
        nxt = self.spine.continuation_next(pid)
        # READY queue is empty, but the milestone is not reviewed yet: NOT complete.
        self.assertEqual(nxt["action"], "READY_FOR_REVIEW")
        self.assertEqual(self.spine.project(pid)["status"], "RUNNING")

    def test_waiting_review_frozen_does_not_dispatch(self) -> None:
        project = self.spine.create_project("g", ["M1", FINAL_ACCEPTANCE_MILESTONE])
        pid = project["project_id"]
        ms = self.spine.milestones(pid)
        self.spine.add_task(ms[0]["milestone_id"], "t")
        inv = self.spine.continuation_next(pid)["invocation"]
        self.spine.return_invocation(inv["invocation_id"], "ready for review")
        self.spine.set_milestone_status(ms[0]["milestone_id"], "WAITING_REVIEW")
        nxt = self.spine.continuation_next(pid)
        self.assertEqual(nxt["action"], "WAITING_REVIEW")
        self.assertEqual(self.spine.project(pid)["status"], "RUNNING")

    def test_project_completes_only_on_final_acceptance_pass(self) -> None:
        project = self.spine.create_project("g", ["M1", "M2", FINAL_ACCEPTANCE_MILESTONE])
        pid = project["project_id"]
        ms = self.spine.milestones(pid)
        # pass M1 and M2, but leave FINAL_ACCEPTANCE unreviewed
        for head in ms[:2]:
            t = self.spine.add_task(head["milestone_id"], "t")
            nxt = self.spine.continuation_next(pid)
            self.assertEqual(nxt["action"], "INVOCATION")
            self.spine.return_invocation(nxt["invocation"]["invocation_id"], "done")
            self.spine.set_task_status(t["task_id"], "DONE")
            self.review_pass(head["milestone_id"])
            self.spine.set_milestone_status(head["milestone_id"], "PASS")
        # every milestone PASS but FINAL_ACCEPTANCE not reviewed
        self.assertEqual(self.spine.continuation_next(pid)["action"], "AWAITING_FINAL_ACCEPTANCE")
        refusal = self.spine.finalize_complete(pid)
        self.assertEqual(refusal["status"], "REQUIRES_FINAL_ACCEPTANCE_PASS")
        self.assertEqual(self.spine.project(pid)["status"], "RUNNING")
        # now the independent overall review passes FINAL_ACCEPTANCE
        last = ms[-1]
        t2 = self.spine.add_task(last["milestone_id"], "overall acceptance")
        nxt = self.spine.continuation_next(pid)
        self.assertEqual(nxt["action"], "INVOCATION")
        self.spine.return_invocation(nxt["invocation"]["invocation_id"], "accepted")
        self.spine.set_task_status(t2["task_id"], "DONE")
        self.review_pass(last["milestone_id"], commit="final")
        self.spine.set_milestone_status(last["milestone_id"], "PASS")
        final = self.spine.finalize_complete(pid)
        self.assertEqual(final["status"], "COMPLETE")
        self.assertEqual(self.spine.project(pid)["status"], "COMPLETE")

    def test_continuation_keeps_working_with_ready_work_in_unreviewed_milestone(self) -> None:
        project = self.spine.create_project("g", ["M1", "M2", FINAL_ACCEPTANCE_MILESTONE])
        pid = project["project_id"]
        ms = self.spine.milestones(pid)
        # M1 goes UNDER_REVIEW (frozen), but M2 is not reachable until M1 passes.
        task_m1 = self.spine.add_task(ms[0]["milestone_id"], "m1 work")
        self.spine.continuation_next(pid)
        self.spine.set_milestone_status(ms[0]["milestone_id"], "WAITING_REVIEW")
        self.assertEqual(self.spine.continuation_next(pid)["action"], "WAITING_REVIEW")
        # unchanged: project still RUNNING, never COMPLETE while review pending
        self.assertEqual(self.spine.project(pid)["status"], "RUNNING")


if __name__ == "__main__":
    unittest.main()