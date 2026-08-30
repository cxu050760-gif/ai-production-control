"""capsule_bridge 测试：RUN state -> 机械 Context Capsule 的接线正确性。"""

import json
import os
import sys
import unittest
from importlib import import_module

sys.path.insert(0, os.path.dirname(__file__))
cb = import_module("capsule_bridge")


def _sample_state(status="DONE", verdict="PASS"):
    return {
        "run_id": "RUN-TEST-0001",
        "revision": 4,
        "status": status,
        "goal": "产出一份测试报告",
        "worker_identity": "test-worker",
        "last_r_verdict": verdict,
        "current_step": "review completed",
        "next_action": "",
        "metrics": {"r_roundtrips": 2, "r_wait_time_sec": 83.1, "bridge_retries": 0},
    }


class TestStateToCapsuleInput(unittest.TestCase):
    def test_mechanical_facts_only(self):
        facts = cb.state_to_capsule_input(_sample_state())
        self.assertEqual(facts["status"], "DONE")
        self.assertEqual(facts["last_r_verdict"], "PASS")
        self.assertEqual(facts["r_roundtrips"], 2)
        # 不包含任何 AI 叙述字段
        for banned in ("summary", "decision", "completed_by_memory"):
            self.assertNotIn(banned, facts)

    def test_metrics_default_empty(self):
        facts = cb.state_to_capsule_input({"run_id": "R", "status": "RUNNING"})
        self.assertEqual(facts["r_roundtrips"], 0)


class TestBuildCapsule(unittest.TestCase):
    def test_done_resume(self):
        c = cb.build_capsule(_sample_state("DONE", "PASS"))
        self.assertTrue(c["valid"])
        self.assertIn("DONE", c["resume_instruction"])

    def test_rework_resume(self):
        c = cb.build_capsule(_sample_state("RUNNING", "REWORK"))
        self.assertIn("REWORK", c["resume_instruction"])

    def test_running_resume(self):
        c = cb.build_capsule(_sample_state("RUNNING", ""))
        self.assertIn("in progress", c["resume_instruction"])

    def test_unknown_no_guess(self):
        c = cb.build_capsule({"run_id": "R", "status": "WEIRD"})
        self.assertIn("Do NOT guess", c["resume_instruction"])

    def test_non_authority(self):
        c = cb.build_capsule(_sample_state())
        self.assertTrue(c["non_authority"])

    def test_fence_note_present(self):
        c = cb.build_capsule(_sample_state())
        self.assertIn("Mechanical projection", c["fence_note"])



    def test_verify_integrity_ok(self):
        r = cb.verify_state_integrity(_sample_state())
        self.assertTrue(r["valid"])
        self.assertTrue(r["revision_ok"])
        self.assertTrue(r["recoverable"])

    def test_verify_missing_fields(self):
        r = cb.verify_state_integrity({"run_id": "R"})
        self.assertFalse(r["valid"])
        self.assertEqual(r["error"], "MISSING_FIELDS")

    def test_verify_bad_revision(self):
        r = cb.verify_state_integrity({"run_id": "R", "status": "RUNNING", "revision": -1})
        self.assertFalse(r["valid"])

    def test_verify_rework_recoverable(self):
        r = cb.verify_state_integrity(_sample_state("RUNNING", "REWORK"))
        self.assertTrue(r["recoverable"])


class TestLoadRunState(unittest.TestCase):
    def test_missing_state_raises(self):
        with self.assertRaises(FileNotFoundError):
            cb.load_run_state("RUN-DOES-NOT-EXIST",
                              state_root=r"C:\nonexistent\state")


if __name__ == "__main__":
    unittest.main()
