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


def _run(argv, env):
    proc = subprocess.run([sys.executable, str(RUNTIME), *argv], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=120)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {"_raw": proc.stdout}
    return proc.returncode, out, proc.stdout + proc.stderr


class TaskGraphTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.env = dict(os.environ)
        self.env["APC_RUNTIME_STATE_ROOT"] = str(self.root)

    def tearDown(self):
        self.td.cleanup()

    def test_t1_deps_gate_ready(self):
        _run(["task-add", "--task-id", "A"], self.env)
        _run(["task-add", "--task-id", "B", "--dep", "A"], self.env)
        code, out, raw = _run(["task-list"], self.env)
        self.assertEqual(out["ready"], ["A"])  # B blocked by A
        _run(["task-update", "--task-id", "A", "--state", "DONE"], self.env)
        code, out, raw = _run(["task-list"], self.env)
        self.assertEqual(out["ready"], ["B"])  # now B ready

    def test_t2_duplicate_denied(self):
        _run(["task-add", "--task-id", "X"], self.env)
        code, out, raw = _run(["task-add", "--task-id", "X"], self.env)
        self.assertEqual(out["status"], "DENIED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
