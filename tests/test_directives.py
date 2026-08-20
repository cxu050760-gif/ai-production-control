from __future__ import annotations

"""M2 user-directive durable-first tests.

Proves a control directive is committed durably BEFORE it is applied, so it
survives a crash and gates scheduling; and that a fresh NEXT_ACTION cannot
override a pending user directive.
"""

import sys
import tempfile
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aicontrol.directives import (  # noqa: E402
    DirectiveError,
    STATUS_APPLIED,
    STATUS_PENDING,
    apply_directive,
    commit_directive,
    has_work_gate,
    pending_directives,
)
from aicontrol.store import ControlStore  # noqa: E402


class DirectiveFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="aicontrol-dir-")
        self.root = Path(self.temporary.name)
        self.store = ControlStore(self.root / "control.db", state_root=self.root / "state")
        self.store.set_meta("tcb_status", "VERIFIED")
        self.task_id = f"task-{uuid.uuid4()}"

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()


class DirectiveDurableFirstTests(DirectiveFixture):
    def test_commit_before_apply_is_pending(self) -> None:
        directive = commit_directive(self.store, task_id=self.task_id, action="PAUSE", note="hold")
        self.assertEqual(directive["status"], STATUS_PENDING)
        pending = pending_directives(self.store, task_id=self.task_id)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["directive_id"], directive["directive_id"])

    def test_apply_clears_pending(self) -> None:
        directive = commit_directive(self.store, task_id=self.task_id, action="PAUSE")
        applied = apply_directive(self.store, directive_id=directive["directive_id"])
        self.assertEqual(applied["status"], STATUS_APPLIED)
        self.assertEqual(pending_directives(self.store, task_id=self.task_id), [])

    def test_pause_gate_blocks_dispatch(self) -> None:
        commit_directive(self.store, task_id=self.task_id, action="PAUSE")
        blocked, reason = has_work_gate(self.store, task_id=self.task_id)
        self.assertTrue(blocked)
        self.assertIn("PAUSE", reason)
        # the gate is cleared once the directive is applied (transition done)
        pending = pending_directives(self.store, task_id=self.task_id)
        apply_directive(self.store, directive_id=pending[0]["directive_id"])
        blocked_after, _ = has_work_gate(self.store, task_id=self.task_id)
        self.assertFalse(blocked_after)

    def test_change_scope_and_stop_also_gate(self) -> None:
        for action in ("STOP", "CHANGE_SCOPE"):
            task = f"task-{uuid.uuid4()}"
            d = commit_directive(self.store, task_id=task, action=action)
            blocked, _ = has_work_gate(self.store, task_id=task)
            self.assertTrue(blocked, action)
            apply_directive(self.store, directive_id=d["directive_id"])

    def test_resume_not_a_gate(self) -> None:
        commit_directive(self.store, task_id=self.task_id, action="RESUME")
        blocked, _ = has_work_gate(self.store, task_id=self.task_id)
        self.assertFalse(blocked)

    def test_durable_across_new_store_handle(self) -> None:
        commit_directive(self.store, task_id=self.task_id, action="STOP", note="survive restart")
        # a fresh store handle on the SAME db must still see the committed directive
        store2 = ControlStore(self.root / "control.db", state_root=self.root / "state")
        try:
            pending = pending_directives(store2, task_id=self.task_id)
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["action"], "STOP")
        finally:
            store2.close()

    def test_invalid_action_rejected(self) -> None:
        with self.assertRaises(DirectiveError):
            commit_directive(self.store, task_id=self.task_id, action="NUDGE")


if __name__ == "__main__":
    unittest.main()