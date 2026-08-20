from __future__ import annotations

"""M3: Controller.run_pipeline_goal - goal-only entry behind the reviewer gate."""

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
from aicontrol.util import read_json, write_json  # noqa: E402


class RunPipelineGoalFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="aicontrol-rpg-")
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
        self.register_worker("fixture-alpha", "alpha")

    def tearDown(self) -> None:
        self.controller.close()
        self.temporary.cleanup()

    def register_worker(self, worker_id: str, variant: str) -> None:
        self.controller.store.upsert_registry(
            "worker_registry", "worker_id", worker_id,
            {
                "worker_id": worker_id,
                "type": "LOCAL_PROCESS_FIXTURE",
                "invocation": str(ROOT / "scripts" / "fixture_worker.py"),
                "variant": variant,
                "capabilities": ["artifact-write", "local-transform"],
                "allowed_effects": ["LOCAL_REVERSIBLE_WRITE"],
                "network_scope": "NONE",
                "execution_trust_class": "BROKERED",
                "availability": "AVAILABLE",
            },
        )

    def set_reviewer(self, reviewer_id: str, availability: str) -> None:
        self.controller.store.upsert_registry(
            "reviewer_registry", "reviewer_id", reviewer_id,
            {"reviewer_id": reviewer_id, "role": "R_PROD", "availability": availability},
        )

    def stand_in_pass(self, produced):
        return {"verdict": "PASS"}


class RunPipelineGoalTests(RunPipelineGoalFixture):
    def test_gate_returns_ready_for_review_without_reviewer(self) -> None:
        self.set_reviewer("r-prod-temp", "PENDING")
        result = self.controller.run_pipeline_goal(
            "do a real goal",
            worker_id="fixture-alpha",
            required_reviewer_id="r-prod-temp",
            review=self.stand_in_pass,
        )
        self.assertEqual(result["status"], "READY_FOR_REVIEW")
        self.assertFalse(result["reviewer_available"])
        # no delivery is written while the reviewer is unavailable
        deliver_root = Path(result["task_id"] and self.root / "output" / "tasks")
        produced = list(deliver_root.glob("*/release/delivery-*.md")) if deliver_root.exists() else []
        self.assertEqual(produced, [])

    def test_delivers_when_reviewer_available_with_real_worker(self) -> None:
        self.set_reviewer("r-prod-temp", "AVAILABLE")
        result = self.controller.run_pipeline_goal(
            "do a real goal",
            worker_id="fixture-alpha",
            required_reviewer_id="r-prod-temp",
            review=self.stand_in_pass,
        )
        self.assertEqual(result["status"], "COMPLETE")
        deliver_root = self.root / "output" / "tasks" / result["task_id"] / "release"
        delivered = list(deliver_root.glob("delivery-*.md"))
        self.assertEqual(len(delivered), 1)
        self.assertIn("variant: alpha", delivered[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()