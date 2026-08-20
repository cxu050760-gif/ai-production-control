from __future__ import annotations

"""M5: authoritative lineage release gate wired into the goal pipeline.

Proves:
  - a real delivery through Controller.run_pipeline_goal records a lineage
    CANDIDATE (never a self-promotion to STABLE when the review is a stand-in);
  - promote_release refuses non-PASS and promotes only on an independent PASS;
  - rollback_release restores the prior Stable durably.
"""

import copy
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aicontrol.controller import Controller  # noqa: E402
from aicontrol.lineage import PromotionRequiresReview  # noqa: E402
from aicontrol.util import read_json, write_json  # noqa: E402


class LineageReleaseFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="aicontrol-lr-")
        self.root = Path(self.temporary.name)
        config = copy.deepcopy(read_json(ROOT / "config" / "production.json"))
        config["code_root"] = str(ROOT)
        config["state_root"] = str(self.root / "state")
        config["output_root"] = str(self.root / "output")
        config["release_root"] = str(self.root / "output" / "release")
        config["evidence_root"] = str(self.root / "evidence")
        config["database_path"] = str(self.root / "state" / "control.db")
        self.config_path = self.root / "config.json"
        write_json(self.config_path, config)
        self.controller = Controller(self.config_path)
        self.controller.store.set_meta("tcb_status", "VERIFIED")
        self.controller.store.set_meta("authority_status", "VERIFIED")
        self.controller.store.upsert_registry(
            "worker_registry", "worker_id", "fixture-alpha",
            {
                "worker_id": "fixture-alpha",
                "type": "LOCAL_PROCESS_FIXTURE",
                "invocation": str(ROOT / "scripts" / "fixture_worker.py"),
                "variant": "alpha",
                "capabilities": ["artifact-write", "local-transform"],
                "allowed_effects": ["LOCAL_REVERSIBLE_WRITE"],
                "network_scope": "NONE",
                "execution_trust_class": "BROKERED",
                "availability": "AVAILABLE",
            },
        )
        self.controller.store.upsert_registry(
            "reviewer_registry", "reviewer_id", "r-prod-temp",
            {"reviewer_id": "r-prod-temp", "role": "R_PROD", "availability": "AVAILABLE"},
        )

    def tearDown(self) -> None:
        self.controller.close()
        self.temporary.cleanup()

    def stand_in_pass(self, produced):  # TEST STAND-IN, never independent
        return {"verdict": "PASS"}

    def run_delivered(self):
        return self.controller.run_pipeline_goal(
            "release a sample artifact",
            worker_id="fixture-alpha",
            required_reviewer_id="r-prod-temp",
            review=self.stand_in_pass,
        )


class LineageReleaseGateTests(LineageReleaseFixture):
    def test_delivery_records_candidate_not_stable(self) -> None:
        result = self.run_delivered()
        self.assertEqual(result["status"], "COMPLETE")
        li = result.get("lineage_release")
        self.assertIsNotNone(li, "delivery must record an authoritative lineage Candidate")
        self.assertEqual(li["lineage_status"], "CANDIDATE")
        # no Stable yet (review was a stand-in)
        self.assertIsNone(self.controller.release_lineage() and
                          next((r for r in self.controller.release_lineage() if r["status"] == "STABLE"), None))

    def test_promote_fails_closed_on_non_pass(self) -> None:
        rec = self.run_delivered()["lineage_release"]["lineage_record_id"]
        with self.assertRaises(PromotionRequiresReview):
            self.controller.promote_release(rec, independent_review={"verdict": "REWORK", "reviewer": "r"})

    def test_promote_requires_independent_pass_and_advances_stable(self) -> None:
        rec = self.run_delivered()["lineage_release"]["lineage_record_id"]
        out = self.controller.promote_release(rec, independent_review={"verdict": "PASS", "reviewer": "independent-r"})
        self.assertEqual(out["lineage_status"], "STABLE")
        stables = [r for r in self.controller.release_lineage() if r["status"] == "STABLE"]
        self.assertEqual(len(stables), 1)
        self.assertEqual(stables[0]["kind"], "STABLE")

    def test_rollback_restores_previous_stable(self) -> None:
        r1 = self.run_delivered()["lineage_release"]
        self.controller.promote_release(r1["lineage_record_id"], independent_review={"verdict": "PASS", "reviewer": "r"})
        v1 = [r["version"] for r in self.controller.release_lineage() if r["status"] == "STABLE"][0]
        r2 = self.run_delivered()["lineage_release"]
        self.controller.promote_release(r2["lineage_record_id"], independent_review={"verdict": "PASS", "reviewer": "r"})
        v2 = [r["version"] for r in self.controller.release_lineage() if r["status"] == "STABLE"][-1]
        self.assertNotEqual(v2, v1)
        self.controller.rollback_release(v2, reason="build failed")
        cur = self.controller.release_lineage()
        current_stable = [r for r in cur if r["status"] == "STABLE"]
        self.assertEqual(len(current_stable), 1)
        self.assertEqual(current_stable[0]["version"], v1)
        rolled = [r for r in cur if r["version"] == v2]
        self.assertEqual(rolled[0]["status"], "ROLLED_BACK")


if __name__ == "__main__":
    unittest.main()
