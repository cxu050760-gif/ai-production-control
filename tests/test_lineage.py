from __future__ import annotations

"""M2/M5 stable / candidate lineage tests.

Proves: Stable is separate from Candidate; promotion requires an independent
PASS review (fails closed otherwise); a failed development line never breaks the
current Stable; rollback is durable + traceable and restores the prior Stable.
"""

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aicontrol.lineage import PromotionRequiresReview, StableLineage  # noqa: E402
from aicontrol.store import ControlStore  # noqa: E402


class LineageFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="aicontrol-lineage-")
        self.root = Path(self.temporary.name)
        self.store = ControlStore(self.root / "control.db", state_root=self.root / "state")
        self.store.set_meta("tcb_status", "VERIFIED")
        self.lineage = StableLineage(self.store)

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def candidate(self, commit: str, digest: str):
        return self.lineage.create_candidate(controller_commit=commit, tree_digest=digest)

    def independent_pass(self):
        return {"verdict": "PASS", "reviewer": "independent-r"}


class StableLineageTests(LineageFixture):
    def test_promotion_requires_independent_review_pass(self) -> None:
        c = self.candidate("c1", "d1")
        with self.assertRaises(PromotionRequiresReview):
            self.lineage.promote(c["record_id"], independent_review={"verdict": "REWORK"})

    def test_promotion_advances_stable_and_supersedes_prior(self) -> None:
        c1 = self.candidate("c1", "d1")
        self.lineage.promote(c1["record_id"], independent_review=self.independent_pass())
        cur = self.lineage.current_stable()
        self.assertEqual(cur["controller_commit"], "c1")
        v1 = cur["version"]
        c2 = self.candidate("c2", "d2")
        self.lineage.promote(c2["record_id"], independent_review=self.independent_pass())
        cur = self.lineage.current_stable()
        self.assertEqual(cur["controller_commit"], "c2")
        self.assertNotEqual(cur["version"], v1)
        by_version = {r["version"]: r["status"] for r in self.lineage.lineage()}
        self.assertEqual(by_version[v1], "SUPERSEDED")

    def test_development_failure_does_not_break_stable(self) -> None:
        c1 = self.candidate("c1", "d1")
        self.lineage.promote(c1["record_id"], independent_review=self.independent_pass())
        stable_before = self.lineage.current_stable()["version"]
        # a failed development candidate that never passes review
        c2 = self.candidate("c2", "d2")
        with self.assertRaises(PromotionRequiresReview):
            self.lineage.promote(c2["record_id"], independent_review={"verdict": "REWORK"})
        self.assertEqual(self.lineage.current_stable()["version"], stable_before)
        self.assertEqual(self.lineage.current_stable()["controller_commit"], "c1")

    def test_rollback_restores_previous_stable(self) -> None:
        c1 = self.candidate("c1", "d1")
        self.lineage.promote(c1["record_id"], independent_review=self.independent_pass())
        v1 = self.lineage.current_stable()["version"]
        c2 = self.candidate("c2", "d2")
        self.lineage.promote(c2["record_id"], independent_review=self.independent_pass())
        v2 = self.lineage.current_stable()["version"]
        self.assertNotEqual(v2, v1)
        result = self.lineage.rollback(v2, reason="build failed")
        self.assertEqual(result["rolled_back_stable"], v2)
        cur = self.lineage.current_stable()
        self.assertEqual(cur["version"], v1)
        self.assertEqual(cur["controller_commit"], "c1")
        by_version = {r["version"]: r["status"] for r in self.lineage.lineage()}
        self.assertEqual(by_version[v2], "ROLLED_BACK")
        # success after rollback: future promotion from the restored Stable still works
        c3 = self.candidate("c3", "d3")
        self.lineage.promote(c3["record_id"], independent_review=self.independent_pass())
        self.assertEqual(self.lineage.current_stable()["controller_commit"], "c3")

    def test_lineage_traceable_by_commit(self) -> None:
        c1 = self.candidate("cccccc", "d1")
        self.lineage.promote(c1["record_id"], independent_review=self.independent_pass())
        recs = [r for r in self.lineage.lineage() if r["controller_commit"] == "cccccc"]
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["status"], "STABLE")
        self.assertEqual(recs[0]["kind"], "STABLE")


if __name__ == "__main__":
    unittest.main()