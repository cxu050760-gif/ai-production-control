#!/usr/bin/env python3
"""GATE-1#2/#3/#4 (hardening 2026-08-31) offline tests for relay_autopilot.

Covers:
  C1  relay submit without candidate_commit is refused (no fabricated commit
      may reach the real reviewer inbox)
  C2  relay submit with an explicit 40-hex commit builds the event unchanged
  C3  mock sandbox without candidate_commit gets a deterministic goal-derived
      placeholder (reproducible, hex40) — never a random impersonation
  C4  malformed candidate_commit (not 40 hex) is refused in any mode
  F1  admission_checks refuses a FROZEN cost verdict (frozen goals must not
      re-enter by re-submitting; previously only SAFE_HALT was intercepted)
  F2  admission_checks with require_gates=True refuses when a gate blows up
      (fail-closed: relay never skips a broken gate)
  F3  admission_checks with require_gates=False records but tolerates gate
      errors (mock sandbox stays usable)
  F4  admission_checks with require_gates=True refuses when wiring modules
      are unavailable (no "gates unavailable = gates open" on relay)

All offline: no real inbox, no real relay state, no network. The module's
E:\\WB path constants are only read by functions under test that we patch or
never call (load_relay_config etc.), and build_event/admission_checks are
exercised with injected fixtures via unittest.mock.
"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
for p in (str(HERE), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import relay_autopilot as ra  # noqa: E402

GOAL = {"goal_id": "G-TEST-1", "title": "Gate test", "objective": "Do the thing."}


class ResolveCommitTests(unittest.TestCase):
    def test_c1_relay_without_commit_refused(self):
        with self.assertRaises(ValueError) as cm:
            ra._resolve_commit(GOAL, 1, None, relay_mode=True)
        self.assertIn("GATE-1#2", str(cm.exception))

    def test_c2_relay_with_explicit_commit_passthrough(self):
        hex40 = "a" * 40
        self.assertEqual(ra._resolve_commit(GOAL, 1, hex40, relay_mode=True), hex40)

    def test_c3_mock_placeholder_deterministic(self):
        c1 = ra._resolve_commit(GOAL, 7, None, relay_mode=False)
        c2 = ra._resolve_commit(GOAL, 7, None, relay_mode=False)
        self.assertEqual(c1, c2)                      # reproducible
        self.assertRegex(c1, r"^[0-9a-f]{40}$")       # hex40
        self.assertNotEqual(c1, ra._resolve_commit(GOAL, 8, None, relay_mode=False))

    def test_c4_malformed_commit_refused(self):
        with self.assertRaises(ValueError):
            ra._resolve_commit(GOAL, 1, "z" * 40, relay_mode=False)
        with self.assertRaises(ValueError):
            ra._resolve_commit(GOAL, 1, "a" * 41, relay_mode=True)


class AdmissionGateTests(unittest.TestCase):
    def setUp(self):
        # Never touch real relay/config state in tests.
        self._wiring = ra._WIRING_AVAILABLE

    def tearDown(self):
        ra._WIRING_AVAILABLE = self._wiring

    def test_f1_frozen_cost_verdict_refused(self):
        with mock.patch.object(ra.cost_router, "load_policy", return_value={}), \
             mock.patch.object(ra.cost_router, "load_registry_costs", return_value={}), \
             mock.patch.object(ra.cost_router, "load_state", return_value={}), \
             mock.patch.object(ra.cost_router, "do_route",
                               return_value={"verdict": "FROZEN", "recommended_route": "cheap"}):
            res = ra.admission_checks(GOAL, require_gates=False)
        self.assertFalse(res["admitted"])
        self.assertTrue(any("cost-gate FROZEN" in r for r in res["reasons"]), res["reasons"])

    def test_f1b_safe_halt_still_refused(self):
        with mock.patch.object(ra.cost_router, "load_policy", return_value={}), \
             mock.patch.object(ra.cost_router, "load_registry_costs", return_value={}), \
             mock.patch.object(ra.cost_router, "load_state", return_value={}), \
             mock.patch.object(ra.cost_router, "do_route",
                               return_value={"verdict": "SAFE_HALT", "safe_halt": {"record_id": "SH-1"}}):
            res = ra.admission_checks(GOAL, require_gates=False)
        self.assertFalse(res["admitted"])

    def test_f2_gate_error_fail_closed_when_required(self):
        with mock.patch.object(ra.cost_router, "load_policy", side_effect=RuntimeError("cfg broken")):
            res = ra.admission_checks(GOAL, require_gates=True)
        self.assertFalse(res["admitted"])
        self.assertTrue(any("cost-gate error (fail-closed)" in r for r in res["reasons"]), res["reasons"])

    def test_f3_gate_error_tolerated_in_mock(self):
        # Isolate lease/context gates (real lease file on disk is expired) so the
        # test isolates the cost-gate tolerance behaviour only.
        with mock.patch.object(ra.controller_lease, "load_lease",
                               return_value={"generation": 9, "holder": "relay_autopilot",
                                             "expires_at": "2099-01-01T00:00:00Z"}), \
             mock.patch.object(ra.controller_lease, "check_execute_right",
                               return_value={"ok": True}), \
             mock.patch.object(ra.context_sufficiency, "route",
                               return_value={"decision": "PROCEED"}), \
             mock.patch.object(ra.cost_router, "load_policy", side_effect=RuntimeError("cfg broken")):
            res = ra.admission_checks(GOAL, require_gates=False)
        self.assertTrue(res["admitted"])
        self.assertTrue(any("cost-gate error" in r for r in res["reasons"]))

    def test_f4_wiring_unavailable_fail_closed_when_required(self):
        ra._WIRING_AVAILABLE = False
        res = ra.admission_checks(GOAL, require_gates=True)
        self.assertFalse(res["admitted"])
        self.assertTrue(any("wiring modules unavailable" in r for r in res["reasons"]))
        # mock stays usable
        res2 = ra.admission_checks(GOAL, require_gates=False)
        self.assertTrue(res2["admitted"])


if __name__ == "__main__":
    unittest.main()
