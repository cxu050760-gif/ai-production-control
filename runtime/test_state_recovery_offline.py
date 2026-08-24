#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import runtime as rt


class StateRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        rt.RUNS_ROOT = self.root / "runs"

    def tearDown(self):
        self.td.cleanup()

    def _mk(self, rid):
        state = {"run_id": rid, "schema_version": 1, "revision": 0, "status": "RUNNING",
                 "goal": "g", "r_url": "https://chatgpt.com/c/x"}
        return state

    def test_v3_verify_and_recover(self):
        rid = "RUN-20260824-180000-aaaa"
        (self.root / "runs" / rid).mkdir(parents=True, exist_ok=True)
        st = self._mk(rid)
        rt.save_state(st)   # rev1
        rt.save_state(st)   # rev2 (rev1 becomes known-good)
        self.assertTrue(rt.verify_state(rid)["ok"])
        # corrupt current state.json
        sp = self.root / "runs" / rid / "state.json"
        sp.write_text("{ not valid json", encoding="utf-8")
        self.assertFalse(rt.verify_state(rid)["ok"])
        rec = rt.recover_state(rid)
        self.assertTrue(rec["recovered"], rec)
        self.assertTrue(rt.verify_state(rid)["ok"])
        cur = rt.load_state(rid)
        self.assertEqual(cur["revision"], 1)  # recovered previous known-good (rev1)

    def test_v3_no_known_good_no_recover(self):
        rid = "RUN-20260824-180001-bbbb"
        (self.root / "runs" / rid).mkdir(parents=True, exist_ok=True)
        sp = self.root / "runs" / rid / "state.json"
        sp.write_text("{ broken", encoding="utf-8")
        rec = rt.recover_state(rid)
        self.assertFalse(rec["recovered"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
