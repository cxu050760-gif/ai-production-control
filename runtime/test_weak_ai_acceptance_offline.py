#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime.py"
ACCEPT = HERE / "weak_ai_acceptance.py"
R1 = "https://chatgpt.com/c/1e1ebbbb-1111-2222-3333-000000000002"


def _run(script, argv, env):
    proc = subprocess.run([sys.executable, str(script), *argv], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=120)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {"_raw": proc.stdout}
    return proc.returncode, out, proc.stdout + proc.stderr


class WeakAiAcceptancePrepTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.env = dict(os.environ)
        self.env["APC_RUNTIME_STATE_ROOT"] = str(self.root / "state")

    def tearDown(self):
        self.td.cleanup()

    def test_w1_prepare_paused_then_resume(self):
        code, out, raw = _run(ACCEPT, ["prepare", "--r-url", R1], self.env)
        self.assertEqual(code, 0, raw)
        rid = out["run_id"]
        self.assertTrue(out["paused"])
        self.assertIn(rid, out["weak_worker_task"])
        # status must be PAUSED (weak worker Q1: refuse)
        code, st, raw = _run(RUNTIME, ["status", "--run-id", rid], self.env)
        self.assertEqual(code, 0, raw)
        self.assertEqual(st["status"], "PAUSED")
        # RESUME then RUNNING
        code, out, raw = _run(RUNTIME, ["directive", "--run-id", rid, "RESUME"], self.env)
        self.assertEqual(code, 0, raw)
        code, st, raw = _run(RUNTIME, ["status", "--run-id", rid], self.env)
        self.assertEqual(st["status"], "RUNNING")


if __name__ == "__main__":
    unittest.main(verbosity=2)
