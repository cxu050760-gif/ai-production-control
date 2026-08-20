from __future__ import annotations

"""M2/M3 Goal pipeline E2E tests (deterministic, offline).

Proves the whole-loop mechanics with injected worker + reviewer stand-ins:
happy path, auto-REWORK (返工 -> 重测 -> 重审) until PASS, fail-closed when the
retry budget is exceeded, resumability from durable state after a partial run,
the directive gate (PAUSE blocks dispatch), and fail-closed on UNKNOWN/BLOCKED.

A run's PASS here is mechanism/E2E evidence (stand-in reviewer), NOT an
independent review; no milestone is claimed independently reviewed.
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

from aicontrol.directives import commit_directive  # noqa: E402
from aicontrol.pipeline import ContinuationDriver, GoalPipeline  # noqa: E402
from aicontrol.store import ControlStore  # noqa: E402
from aicontrol.util import read_json, write_json  # noqa: E402


class PipelineFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="aicontrol-pl-")
        self.root = Path(self.temporary.name)
        self.store = ControlStore(self.root / "control.db", state_root=self.root / "state")
        self.store.set_meta("tcb_status", "VERIFIED")
        self.task_id = "task-e2e"
        self.artifact = self.root / "work" / "artifact.md"
        self.release = self.root / "release"

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def make_reviewer(self, *, always_pass=False, bad_token="BAD", blocked=False, always_rework=False):
        def review(artifact: Path) -> dict:
            content = artifact.read_text(encoding="utf-8") if artifact.exists() else ""
            if blocked:
                return {"verdict": "BLOCKED", "findings": ["reviewer cannot proceed"]}
            if always_rework:
                return {"verdict": "REWORK", "findings": ["always rework"]}
            if always_pass:
                return {"verdict": "PASS"}
            if bad_token in content:
                return {"verdict": "REWORK", "findings": [f"contains {bad_token}"]}
            return {"verdict": "PASS"}

        return review

    def p(self, *, work, test, review, retry_budget=3, task_id=None):
        return GoalPipeline(
            self.store,
            task_id=task_id or self.task_id,
            objective="e2e goal",
            artifact=self.artifact,
            release_root=self.release,
            work=work,
            test=test,
            review=review,
            retry_budget=retry_budget,
        )


class GoalPipelineE2ETests(PipelineFixture):
    def test_happy_path_delivers(self) -> None:
        def work(attempt, artifact):
            artifact.write_text("ok", encoding="utf-8")

        def test(artifact):
            return True, []

        pipeline = self.p(work=work, test=test, review=self.make_reviewer(always_pass=True))
        report = pipeline.run()
        self.assertEqual(report["status"], "COMPLETE")
        self.assertTrue(report["delivered"])
        delivered_files = list(self.release.glob("delivery-*.md"))
        self.assertEqual(len(delivered_files), 1)
        self.assertTrue(delivered_files[0].stat().st_size > 0)

    def test_rework_auto_requeues_until_pass(self) -> None:
        calls = []

        def work(attempt, artifact):
            calls.append(attempt)
            artifact.write_text("BAD" if attempt == 0 else "OK", encoding="utf-8")

        def test(artifact):
            return True, []

        pipeline = self.p(work=work, test=test, review=self.make_reviewer())
        report = pipeline.run()
        self.assertEqual(report["status"], "COMPLETE")
        # attempt 0 -> REWORK (contains BAD); attempt 1 -> PASS. Two executions = auto返工 + 重测 + 重审.
        self.assertEqual(calls, [0, 1])

    def test_rework_over_budget_fail_closed(self) -> None:
        def work(attempt, artifact):
            artifact.write_text("BAD", encoding="utf-8")

        def test(artifact):
            return True, []

        pipeline = self.p(work=work, test=test, review=self.make_reviewer(), retry_budget=1)
        report = pipeline.run()
        self.assertEqual(report["status"], "BLOCKED")
        self.assertNotIn("delivered", report)

    def test_resume_from_partial_durable_state(self) -> None:
        calls = []

        def work(attempt, artifact):
            calls.append(attempt)
            artifact.write_text("BAD" if attempt == 0 else "OK", encoding="utf-8")

        def test(artifact):
            return True, []

        pipeline = self.p(work=work, test=test, review=self.make_reviewer())
        # simulate: builder ran only the PLAN step then crashed
        first = pipeline.run(limit_steps=1)
        self.assertEqual(first["handled"], 1)
        # a fresh handle continues from durable state (plan is NOT redone)
        pipeline2 = self.p(work=work, test=test, review=self.make_reviewer())
        report = pipeline2.run()
        self.assertEqual(report["status"], "COMPLETE")
        self.assertEqual(len(calls), 2, "iterate executed twice (rework); plan must not have been redone")

    def test_directive_gate_blocks_dispatch(self) -> None:
        gated = False

        def work(attempt, artifact):
            nonlocal gated
            gated = True
            artifact.write_text("ok", encoding="utf-8")

        def test(artifact):
            return True, []

        commit_directive(self.store, task_id=self.task_id, action="PAUSE")
        pipeline = self.p(work=work, test=test, review=self.make_reviewer(always_pass=True))
        report = pipeline.run()
        self.assertEqual(report["status"], "BLOCKED_BY_DIRECTIVE")
        self.assertFalse(gated, "no work should be dispatched while PAUSE is pending")

    def test_unknown_reviewer_fail_closed(self) -> None:
        def work(attempt, artifact):
            artifact.write_text("x", encoding="utf-8")

        def test(artifact):
            return True, []

        pipeline = self.p(work=work, test=test, review=self.make_reviewer(blocked=True))
        report = pipeline.run()
        self.assertEqual(report["status"], "BLOCKED")
        self.assertNotIn("delivered", report)


    def test_reviewer_gate_refuses_delivery_when_reviewer_unavailable(self) -> None:
        self.store.upsert_registry("reviewer_registry", "reviewer_id", "r-prod-temp",
                                   {"reviewer_id": "r-prod-temp", "availability": "PENDING"})

        def work(attempt, artifact):
            artifact.write_text("ok", encoding="utf-8")

        def test(artifact):
            return True, []

        pipeline = GoalPipeline(
            self.store, task_id="task-reviewgate", objective="gate",
            artifact=self.root / "art.md", release_root=self.root / "release",
            work=work, test=test, review=self.make_reviewer(always_pass=True),
            required_reviewer_id="r-prod-temp",
        )
        report = pipeline.run()
        self.assertEqual(report["status"], "READY_FOR_REVIEW")
        self.assertFalse(report["reviewer_available"])
        self.assertEqual(list((self.root / "release").glob("delivery-*.md")), [])

        self.store.upsert_registry("reviewer_registry", "reviewer_id", "r-prod-temp",
                                   {"reviewer_id": "r-prod-temp", "availability": "AVAILABLE"})
        report2 = pipeline.run()
        self.assertEqual(report2["status"], "COMPLETE")
        self.assertEqual(len(list((self.root / "release").glob("delivery-*.md"))), 1)


class ContinuationDriverTests(PipelineFixture):
    def test_single_goal_auto_continues_without_user(self) -> None:
        calls = []

        def work(attempt, artifact):
            calls.append(attempt)
            artifact.write_text("ok", encoding="utf-8")

        def test(produced):
            return True, []

        driver = ContinuationDriver(self.store)
        result = driver.advance(
            task_id="task-driver-ok", objective="g",
            artifact=self.root / "a.md", release_root=self.root / "release",
            work=work, test=test, review=self.make_reviewer(always_pass=True),
            per_invocation_step_budget=1, max_invocations=50,
        )
        # one submission -> multiple automatic invocations -> delivery; no user "continue".
        self.assertEqual(result["status"], "COMPLETE")
        self.assertGreaterEqual(len(result["invocations"]), 3)
        self.assertEqual(len(list((self.root / "release").glob("delivery-*.md"))), 1)

    def test_driver_gate_no_delivery_without_reviewer(self) -> None:
        self.store.upsert_registry("reviewer_registry", "reviewer_id", "rdr",
                                   {"reviewer_id": "rdr", "availability": "PENDING"})

        def work(attempt, artifact):
            artifact.write_text("x", encoding="utf-8")

        def test(produced):
            return True, []

        driver = ContinuationDriver(self.store)
        result = driver.advance(
            task_id="task-driver-gate", objective="g",
            artifact=self.root / "a.md", release_root=self.root / "release",
            work=work, test=test, review=self.make_reviewer(always_pass=True),
            required_reviewer_id="rdr", per_invocation_step_budget=1, max_invocations=5,
        )
        self.assertEqual(result["status"], "READY_FOR_REVIEW")
        self.assertEqual(len(result["invocations"]), 1)
        self.assertEqual(list((self.root / "release").glob("delivery-*.md")), [])


if __name__ == "__main__":
    unittest.main()