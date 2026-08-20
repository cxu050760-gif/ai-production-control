from __future__ import annotations

"""M3/M5: goal survives process restart via durable state + ContinuationDriver.

Submits a single GOAL, runs it partway, then CLOSES the Controller (process exit).
A NEW Controller on the SAME durable DB resumes the SAME task via the outer
ContinuationDriver and completes delivery with NO new user input - proving
AI_STOP_DOES_NOT_STOP_PROJECT across a real process restart (goal submitted once).

The reviewer is an injected stand-in => mechanism evidence only, not independent.
"""

import copy
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aicontrol.controller import Controller  # noqa: E402
from aicontrol.pipeline import ContinuationDriver  # noqa: E402
from aicontrol.util import read_json, write_json  # noqa: E402


def _rmtree_quiet(path: Path) -> None:
    for _ in range(6):
        try:
            shutil.rmtree(path)
            return
        except OSError:
            time.sleep(0.3)
    pass


class RestartResumeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="aicontrol-restart-"))

    def tearDown(self) -> None:
        _rmtree_quiet(self.root)

    def test_goal_survives_process_restart_single_submission(self) -> None:
        config = copy.deepcopy(read_json(ROOT / "config" / "production.json"))
        config["code_root"] = str(ROOT)
        config["state_root"] = str(self.root / "state")
        config["output_root"] = str(self.root / "output")
        config["release_root"] = str(self.root / "output" / "release")
        config["evidence_root"] = str(self.root / "evidence")
        config["database_path"] = str(self.root / "state" / "control.db")
        config_path = self.root / "config.json"
        write_json(config_path, config)

        task_id = "task-restart"
        objective = "restart-resume goal"
        artifact = self.root / "work" / "a.md"
        release = self.root / "output" / "release"

        def build_controller():
            c = Controller(config_path)
            c.store.set_meta("tcb_status", "VERIFIED")
            c.store.set_meta("authority_status", "VERIFIED")
            return c

        c1 = build_controller()
        c1.store.upsert_registry(
            "worker_registry", "worker_id", "fixture-alpha",
            {"worker_id": "fixture-alpha", "type": "LOCAL_PROCESS_FIXTURE",
             "invocation": str(ROOT / "scripts" / "fixture_worker.py"), "variant": "alpha",
             "capabilities": ["artifact-write", "local-transform"],
             "allowed_effects": ["LOCAL_REVERSIBLE_WRITE"], "network_scope": "NONE",
             "execution_trust_class": "BROKERED", "availability": "AVAILABLE"},
        )
        c1.store.upsert_registry(
            "reviewer_registry", "reviewer_id", "r-prod",
            {"reviewer_id": "r-prod", "role": "R_PROD", "availability": "AVAILABLE"},
        )
        task = c1.bootstrap_task(
            goal=objective, expected_final_artifact="fixture",
            acceptance_criteria=["A01"], data_classification="PUBLIC", task_id=task_id,
        )
        fence = task["context_fence"]

        def advance(controller, max_inv):
            def work(attempt, a):
                res = controller.runtime.invoke_worker_adapter(
                    task_id=task_id, context_fence=fence, worker_id="fixture-alpha",
                    objective=objective,
                )
                return Path(res["envelope"]["artifact_paths"][0])

            def test(p):
                return p.exists() and p.stat().st_size > 0, []

            def review(p):
                return {"verdict": "PASS"}

            return (ContinuationDriver(controller.store)).advance(
                task_id=task_id, objective=objective, artifact=artifact, release_root=release,
                work=work, test=test, review=review, required_reviewer_id="r-prod",
                per_invocation_step_budget=1, max_invocations=max_inv,
            )

        # run partway (ONE invocation), then simulate process exit
        r1 = advance(c1, max_inv=1)
        self.assertNotEqual(r1["status"], "COMPLETE")  # still RUNNING (plan done only)
        c1.close()

        # process restart: new Controller on SAME durable DB resumes the same task
        c2 = build_controller()
        r2 = advance(c2, max_inv=50)
        self.assertEqual(r2["status"], "COMPLETE")
        delivered = list(release.glob("delivery-*.md"))
        self.assertEqual(len(delivered), 1)
        self.assertIn("variant: alpha", delivered[0].read_text(encoding="utf-8"))
        c2.close()


if __name__ == "__main__":
    unittest.main()