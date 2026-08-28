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


if __name__ == "__main__":
    unittest.main(verbosity=2)