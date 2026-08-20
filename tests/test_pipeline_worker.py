from __future__ import annotations

"""M3: real Worker through the Goal pipeline via the M1 worker adapter.

A real, zero-internal-knowledge fixture worker (scripts/fixture_worker.py) runs
as a subprocess through RuntimeManager.invoke_worker_adapter inside the
pipeline's ITERATE step, producing a source-bound, per-path digest-verified
artifact that then flows through test -> review -> deliver. Two registrations
(fixture-alpha / fixture-beta) prove Worker replacement through the same
pipeline with no code branch. A worker-produced PASS here is mechanism/E2E
evidence only, not an independent review.
"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aicontrol.controller import Controller  # noqa: E402
from aicontrol.pipeline import GoalPipeline  # noqa: E402
from aicontrol.util import read_json, write_json  # noqa: E402


class RealWorkerPipelineFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="aicontrol-rwp-")
        self.root = Path(self.temporary.name)
        config = copy.deepcopy(read_json(ROOT / "config" / "production.json"))
        config["code_root"] = str(ROOT)
        config["state_root"] = str(self.root / "state")
        config["output_root"] = str(self.root / "output")
        config["release_root"] = str(self.root / "release")
        config["evidence_root"] = str(self.root / "evidence")
        config["database_path"] = str(self.root / "state" / "control.db")
        self.config_path = self.root / "config.json"
        write_json(self.config_path, config)
        self.controller = Controller(self.config_path)
        self.controller.store.set_meta("tcb_status", "VERIFIED")
        self.controller.store.set_meta("authority_status", "VERIFIED")
        self.task = self.controller.bootstrap_task(
            goal="real worker pipeline", expected_final_artifact="fixture",
            acceptance_criteria=["A01"], data_classification="PUBLIC",
        )
        self.task_id = self.task["task_id"]
        self.context_fence = self.task["context_fence"]

    def tearDown(self) -> None:
        self.controller.close()
        self.temporary.cleanup()

    def register_fixture_worker(self, worker_id: str, variant: str) -> None:
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

    def make_pipeline(self, *, worker_id: str, task_id: str, context_fence: str, produced_tracker: list) -> GoalPipeline:
        def work(attempt, artifact):
            res = self.controller.runtime.invoke_worker_adapter(
                task_id=task_id,
                context_fence=context_fence,
                worker_id=worker_id,
                objective="produce a conformance fixture",
            )
            produced_tracker.append(res)
            assert res["verification"]["verification_status"] == "VERIFIED"
            return Path(res["envelope"]["artifact_paths"][0])

        def test(produced):
            return produced.exists() and produced.stat().st_size > 0, []

        def review(produced):
            if produced.exists() and produced.stat().st_size > 0:
                return {"verdict": "PASS"}
            return {"verdict": "REWORK", "findings": ["artifact missing"]}

        return GoalPipeline(
            self.controller.store,
            task_id=task_id,
            objective="real worker e2e",
            artifact=self.root / "placeholder.md",
            release_root=self.root / "release",
            work=work,
            test=test,
            review=review,
            retry_budget=3,
        )


class RealWorkerPipelineTests(RealWorkerPipelineFixture):
    def test_real_fresh_weak_worker_runs_through_pipeline(self) -> None:
        self.register_fixture_worker("fixture-alpha", "alpha")
        tracker = []
        pipeline = self.make_pipeline(worker_id="fixture-alpha", task_id=self.task_id,
                                      context_fence=self.context_fence, produced_tracker=tracker)
        report = pipeline.run()
        self.assertEqual(report["status"], "COMPLETE")
        delivered = list((self.root / "release").glob("delivery-*.md"))
        self.assertEqual(len(delivered), 1)
        # the worker result was source-bound and digest-verified by the adapter
        self.assertEqual(len(tracker), 1)
        self.assertEqual(tracker[0]["source_binding"]["worker_id"], "fixture-alpha")
        # the delivered content is the real worker's artifact (no placeholder)
        self.assertIn("variant: alpha", delivered[0].read_text(encoding="utf-8"))

    def test_worker_replacement_two_workers_same_pipeline(self) -> None:
        self.register_fixture_worker("fixture-alpha", "alpha")
        self.register_fixture_worker("fixture-beta", "beta")
        outputs = {}
        for worker_id, variant in (("fixture-alpha", "alpha"), ("fixture-beta", "beta")):
            tid = f"task-{worker_id}"
            task = self.controller.bootstrap_task(
                goal="real worker replacement", expected_final_artifact="fixture",
                acceptance_criteria=["A01"], data_classification="PUBLIC", task_id=tid,
            )
            tracker = []
            pipeline = self.make_pipeline(worker_id=worker_id, task_id=tid,
                                          context_fence=task["context_fence"], produced_tracker=tracker)
            report = pipeline.run()
            self.assertEqual(report["status"], "COMPLETE", worker_id)
            delivered = list((self.root / "release").glob("delivery-*.md"))
            outputs[variant] = sorted(delivered)[-1].read_text(encoding="utf-8")
            self.assertEqual(len(tracker), 1)
            self.assertEqual(tracker[0]["source_binding"]["worker_id"], worker_id)
        self.assertIn("variant: alpha", outputs["alpha"])
        self.assertIn("variant: beta", outputs["beta"])
        self.assertNotEqual(outputs["alpha"], outputs["beta"])


if __name__ == "__main__":
    unittest.main()