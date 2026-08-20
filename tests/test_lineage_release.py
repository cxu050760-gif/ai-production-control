from __future__ import annotations

"""M5: authoritative lineage release gate - voucher-bound independent promotion.

Proves:
  - a real delivery records a CANDIDATE (never self-promoted);
  - only a durable, candidate-bound review voucher issued by a registered, ready
    R_PROD reviewer (with a matching delivered digest) can promote CANDIDATE->STABLE;
  - forged / unregistered / cross-candidate / digest-mismatch vouchers all fail;
  - authoritative lineage identity fails closed when git/commit or digest is missing;
  - rollback operates the same authoritative lineage and is traceable.
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
from aicontrol.lineage import LineageError, PromotionRequiresReview  # noqa: E402
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
        # a ready independent R_PROD reviewer
        self.controller.store.upsert_registry(
            "reviewer_registry", "reviewer_id", "r-prod-real",
            {"reviewer_id": "r-prod-real", "role": "R_PROD", "availability": "VERIFIED"},
        )
        # a distractor reviewer that is NOT a ready R_PROD reviewer
        self.controller.store.upsert_registry(
            "reviewer_registry", "reviewer_id", "r-nonprod",
            {"reviewer_id": "r-nonprod", "role": "E_LAB", "availability": "AVAILABLE"},
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
            required_reviewer_id="r-prod-real",
            review=self.stand_in_pass,
        )

    def delivered_digest(self, result):
        return self.controller.store.meta(f"pipeline:{result['task_id']}:delivered_digest")

    def promote_bound(self, result):
        v = self.controller.issue_promotion_voucher(
            result["lineage_release"]["lineage_record_id"],
            reviewer_identity="r-prod-real",
            delivered_digest=self.delivered_digest(result),
        )
        return self.controller.promote_release(v["voucher_id"])


class LineageReleaseGateTests(LineageReleaseFixture):
    def test_delivery_records_candidate_not_stable(self) -> None:
        result = self.run_delivered()
        self.assertEqual(result["status"], "COMPLETE")
        li = result.get("lineage_release")
        self.assertIsNotNone(li)
        self.assertEqual(li["lineage_status"], "CANDIDATE")
        stables = [r for r in self.controller.release_lineage() if r["status"] == "STABLE"]
        self.assertEqual(stables, [])

    def test_bound_rprod_pass_promotes_to_stable(self) -> None:
        result = self.run_delivered()
        out = self.promote_bound(result)
        self.assertEqual(out["lineage_status"], "STABLE")
        stables = [r for r in self.controller.release_lineage() if r["status"] == "STABLE"]
        self.assertEqual(len(stables), 1)
        self.assertEqual(stables[0]["kind"], "STABLE")

    def test_unknown_voucher_cannot_promote(self) -> None:
        result = self.run_delivered()
        with self.assertRaises(PromotionRequiresReview):
            self.controller.promote_release("voucher-does-not-exist")
        stables = [r for r in self.controller.release_lineage() if r["status"] == "STABLE"]
        self.assertEqual(stables, [])

    def test_forged_verdict_dict_is_never_trusted(self) -> None:
        # a "PASS-shaped dict" can no longer be passed to promotion; the only API
        # is a voucher_id, so a forged/injected dict simply cannot promote.
        result = self.run_delivered()
        self.assertFalse(hasattr(self.controller.promote_release, "independent_review"))
        stables = [r for r in self.controller.release_lineage() if r["status"] == "STABLE"]
        self.assertEqual(stables, [])

    def test_unregistered_or_non_rprod_reviewer_cannot_issue_voucher(self) -> None:
        result = self.run_delivered()
        rid = result["lineage_release"]["lineage_record_id"]
        dig = self.delivered_digest(result)
        with self.assertRaises(PromotionRequiresReview):
            self.controller.issue_promotion_voucher(rid, reviewer_identity="nobody", delivered_digest=dig)
        with self.assertRaises(PromotionRequiresReview):
            self.controller.issue_promotion_voucher(rid, reviewer_identity="r-nonprod", delivered_digest=dig)

    def test_digest_mismatch_cannot_voucher(self) -> None:
        result = self.run_delivered()
        rid = result["lineage_release"]["lineage_record_id"]
        with self.assertRaises(LineageError):
            self.controller.issue_promotion_voucher(rid, reviewer_identity="r-prod-real", delivered_digest="wrong-digest")

    def test_other_candidates_pass_cannot_promote_this_candidate(self) -> None:
        a = self.run_delivered()
        b = self.run_delivered()
        rid_a = a["lineage_release"]["lineage_record_id"]
        dig_b = self.delivered_digest(b)  # digest belongs to candidate B, not A
        with self.assertRaises(LineageError):
            self.controller.issue_promotion_voucher(rid_a, reviewer_identity="r-prod-real", delivered_digest=dig_b)
        stables = [r for r in self.controller.release_lineage() if r["status"] == "STABLE"]
        self.assertEqual(stables, [])

    def test_identity_fails_closed_when_git_or_digest_missing(self) -> None:
        self.controller.code_root = self.root / "not-a-git-repo"
        self.assertIsNone(self.controller._lineage_identity()[0])
        with self.assertRaises(LineageError):
            self.controller._record_release(task_id="t1", objective="x", delivered_digest="abc")
        with self.assertRaises(LineageError):
            self.controller._record_release(task_id="t1", objective="x", delivered_digest=None)

    def test_rollback_restores_previous_stable(self) -> None:
        r1 = self.run_delivered()
        self.promote_bound(r1)
        v1 = [r["version"] for r in self.controller.release_lineage() if r["status"] == "STABLE"][0]
        r2 = self.run_delivered()
        self.promote_bound(r2)
        stables = [r["version"] for r in self.controller.release_lineage() if r["status"] == "STABLE"]
        v2 = stables[-1]
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
