#!/usr/bin/env python3
"""Regression tests for state_doctor ref-classification (R5).

Guards against the `refs/remotes/<remote>` bare-leaf false positive: a stale
repo-ref-layout artifact (e.g. `refs/remotes/origin`) must NOT be reported as
an unregistered branch, while genuine local and remote-tracking branches must
still be classified as branches.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import state_doctor as doc  # noqa: E402


class StateDoctorRefClassificationTests(unittest.TestCase):
    def test_local_branch_maps_by_path(self):
        self.assertEqual(doc._ref_to_branch("refs/heads/master"), "master")

    def test_local_nested_branch_maps_by_path(self):
        self.assertEqual(
            doc._ref_to_branch("refs/heads/v0.9-b2/authority-effect-evidence"),
            "v0.9-b2/authority-effect-evidence",
        )

    def test_remote_tracking_branch_maps_without_remote_prefix(self):
        self.assertEqual(
            doc._ref_to_branch("refs/remotes/origin/v0.9-b2/authority-effect-evidence"),
            "v0.9-b2/authority-effect-evidence",
        )

    def test_symbolic_head_is_not_a_branch(self):
        self.assertIsNone(doc._ref_to_branch("refs/remotes/origin/HEAD"))
        self.assertIsNone(doc._ref_to_branch("refs/heads/HEAD"))

    def test_bare_remote_leaf_ref_is_not_a_branch(self):
        # stale repo-ref-layout leaf; the origin remote itself is not a branch.
        self.assertIsNone(doc._ref_to_branch("refs/remotes/origin"))

    def test_non_branch_namespace_is_ignored(self):
        self.assertIsNone(doc._ref_to_branch("refs/tags/v1.0"))
        self.assertIsNone(doc._ref_to_branch("refs/notes/commits"))


class StateDoctorDevHeadPolicyTests(unittest.TestCase):
    """Phase 0 Seal ruling A: physical HEAD may be ahead of CURRENT_DEVELOPMENT_HEAD
    ONLY by state-only/governance commits; real code/dev commits ahead = DRIFT."""

    def _gov(self, commit):
        return commit in {"SEAL"}

    def test_case1_development_head_equals_physical_head(self):
        ok, _ = doc._classify_dev_head("abc", "abc", lambda a, b: True, [], self._gov)
        self.assertTrue(ok)

    def test_case2_physical_ahead_by_state_only_seal_commit(self):
        ok, _ = doc._classify_dev_head("abc", "def", lambda a, b: True, ["SEAL"], self._gov)
        self.assertTrue(ok)

    def test_case3_physical_ahead_by_real_code_commit_drifts(self):
        ok, detail = doc._classify_dev_head("abc", "def", lambda a, b: True, ["CODE-COMMIT"], self._gov)
        self.assertFalse(ok)
        self.assertIn("CODE-COMMIT", detail)

    def test_case4_unregistered_branch_reported(self):
        unreg = doc._unregistered_branches({"master", "extra/unregistered"}, {"master"})
        self.assertEqual(unreg, ["extra/unregistered"])

    def test_case5_recorded_development_head_unresolvable_drifts(self):
        ok, _ = doc._classify_dev_head(None, "def", lambda a, b: True, [], self._gov)
        self.assertFalse(ok)

    def test_unregistered_empty_when_none(self):
        self.assertEqual(doc._unregistered_branches({"master", "dev"}, {"master", "dev"}), [])

    def test_governance_path_whitelist_discriminates_paths(self):
        # governance-only path set -> allowed
        self.assertTrue(doc._all_in(["PROJECT_STATE.json", "state/branch_registry.json"], doc.GOVERNANCE_PATHS))
        # a real code path -> not allowed (CASE 3 discrimination mechanism)
        self.assertFalse(doc._all_in(["runtime/v08_adapter.py"], doc.GOVERNANCE_PATHS))
        # empty change set -> fail closed (not governance-only)
        self.assertFalse(doc._all_in([], doc.GOVERNANCE_PATHS))


if __name__ == "__main__":
    unittest.main(verbosity=2)