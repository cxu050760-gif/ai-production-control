#!/usr/bin/env python3
import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness_verify as hv

BASE = "1" * 40
CAND = "2" * 40
REMOTE = "https://github.com/example/repo.git"


class HarnessOfflineTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.env = mock.patch.dict(os.environ, {"APC_RUNTIME_STATE_ROOT": str(self.root / "state")}, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.td.cleanup()

    def args(self, **kw):
        d = dict(accepted_base=BASE, candidate_commit=CAND, canonical_remote=REMOTE, timeout=30)
        d.update(kw)
        return argparse.Namespace(**d)

    def test_tasks_satisfy_frozen_launcher_contract(self):
        doc = hv._make_worker_tasks(
            Path("C:/x/runtime/harness_verify.py"),
            self.args(),
            Path("C:/e/machine_evidence.json"),
        )
        self.assertEqual(len(doc["tasks"]), 2)
        self.assertEqual(
            [t["id"] for t in doc["tasks"]],
            ["candidate_verifier", "candidate_witness"],
        )
        allowed = {"Read", "Glob", "Grep", "Bash", "Write", "Edit", "WebSearch", "WebFetch"}
        for task in doc["tasks"]:
            self.assertTrue(set(task["tools"]) <= allowed)
            self.assertNotIn("PowerShell", task["tools"])
            self.assertIn(BASE, task["inputs"])
            self.assertIn(CAND, task["inputs"])
            self.assertIn(REMOTE, task["inputs"])
        verifier = doc["tasks"][0]
        self.assertIn("Bash", verifier["tools"])
        self.assertIn(BASE, verifier["task"])
        self.assertIn(CAND, verifier["task"])
        self.assertIn(REMOTE, verifier["task"])
        self.assertEqual(doc["tasks"][1]["tools"], ["Read"])

    def test_worker_directories_are_independent_and_non_overlapping(self):
        script = Path("C:/x/runtime/harness_verify.py")
        doc = hv._make_worker_tasks(
            script,
            self.args(),
            Path("C:/e/machine_evidence.json"),
        )
        verifier_cwd = Path(doc["tasks"][0]["working_directory"])
        witness_cwd = Path(doc["tasks"][1]["working_directory"])
        self.assertNotEqual(str(verifier_cwd), str(witness_cwd))
        self.assertFalse(hv._paths_overlap(verifier_cwd, witness_cwd))
        self.assertTrue(str(verifier_cwd).replace("\\", "/").endswith("/runtime"))
        self.assertTrue(str(witness_cwd).replace("\\", "/").endswith("/docs"))
        witness_task = doc["tasks"][1]["task"].replace("\\", "/")
        self.assertIn("C:/x/runtime/run.cmd", witness_task)

    def test_invalid_candidate_sha_is_fail_closed(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = hv.main([
                "harness-verify", "--accepted-base", BASE,
                "--candidate-commit", "latest", "--canonical-remote", REMOTE,
            ])
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(buf.getvalue())["HARNESS_STATUS"], "HARD_BLOCKED")

    def test_missing_launcher_persists_hard_block(self):
        with mock.patch.dict(os.environ, {"APC_HARNESS_LAUNCHER": str(self.root / "missing.ps1")}, clear=False):
            rc = hv._invoke(self.args())
        self.assertEqual(rc, 21)
        states = list((self.root / "state" / "harness").glob("*/harness_state.json"))
        self.assertEqual(len(states), 1)
        st = json.loads(states[0].read_text())
        self.assertEqual(st["HARNESS_STATUS"], "HARD_BLOCKED")
        self.assertEqual(st["CANDIDATE_COMMIT"], CAND)
        self.assertEqual(st["ACCEPTED_BASE"], BASE)
        self.assertIsNotNone(st["HARNESS_STARTED_AT"])
        self.assertIsNotNone(st["HARNESS_FINISHED_AT"])
        self.assertEqual(st["HARNESS_EXIT_CODE"], 21)
        self.assertTrue(st["EVIDENCE_ID"])
        self.assertTrue(st["EVIDENCE_PATH"])

    def test_launcher_timeout_is_fail_closed(self):
        launcher = self.root / "launcher.ps1"
        launcher.write_text("# stub")
        with mock.patch.dict(os.environ, {"APC_HARNESS_LAUNCHER": str(launcher)}, clear=False), \
             mock.patch.object(hv, "_run", side_effect=subprocess.TimeoutExpired(["ps"], 1)):
            rc = hv._invoke(self.args())
        self.assertEqual(rc, 22)

    def _fake_launcher(
        self,
        *,
        evidence_status="SUCCEEDED",
        evidence_candidate=CAND,
        check_status="SUCCEEDED",
        worker_ids=("candidate_verifier", "candidate_witness"),
        failed_worker=None,
        timed_out_worker=None,
    ):
        def fake_run(cmd, **kwargs):
            self.assertEqual(cmd[cmd.index("-MaxWorkers") + 1], "2")
            out_index = cmd.index("-OutputRoot") + 1
            output_root = Path(cmd[out_index])
            for wid in worker_ids:
                wdir = output_root / "job_x" / "workers" / wid
                wdir.mkdir(parents=True, exist_ok=True)
                (wdir / "worker.json").write_text(json.dumps({
                    "worker_id": wid,
                    "status": "failed" if failed_worker == wid else "succeeded",
                    "exit_code": 1 if failed_worker == wid else 0,
                    "timed_out": timed_out_worker == wid,
                }))
            evidence_path = output_root.parent / "machine_evidence.json"
            evidence_path.write_text(json.dumps({
                "status": evidence_status,
                "candidate_commit": evidence_candidate,
                "accepted_base": BASE,
                "harness_exit_code": 0 if evidence_status == "SUCCEEDED" else 20,
                "checks": [{"name": "x", "status": check_status}],
            }))
            return 0, "ok", "", 0.01
        return fake_run

    def test_success_requires_two_workers_and_bound_machine_evidence(self):
        launcher = self.root / "launcher.ps1"
        launcher.write_text("# stub")
        with mock.patch.dict(os.environ, {"APC_HARNESS_LAUNCHER": str(launcher)}, clear=False), \
             mock.patch.object(hv, "_run", side_effect=self._fake_launcher()):
            rc = hv._invoke(self.args())
        self.assertEqual(rc, 0)
        state = json.loads(next((self.root / "state" / "harness").glob("*/harness_state.json")).read_text())
        self.assertEqual(state["HARNESS_STATUS"], "SUCCEEDED")
        self.assertEqual(state["HARNESS_EXIT_CODE"], 0)
        self.assertEqual(len(state["WORKER_METADATA_PATHS"]), 2)
        self.assertIn("candidate_verifier", state["WORKER_METADATA_PATH"])
        tasks = json.loads(next((self.root / "state" / "harness").glob("*/tasks.json")).read_text())
        self.assertEqual(len(tasks["tasks"]), 2)

    def test_missing_second_worker_is_fail_closed(self):
        launcher = self.root / "launcher.ps1"
        launcher.write_text("# stub")
        with mock.patch.dict(os.environ, {"APC_HARNESS_LAUNCHER": str(launcher)}, clear=False), \
             mock.patch.object(
                 hv, "_run",
                 side_effect=self._fake_launcher(worker_ids=("candidate_verifier",)),
             ):
            rc = hv._invoke(self.args())
        self.assertEqual(rc, 25)

    def test_witness_failure_is_fail_closed(self):
        launcher = self.root / "launcher.ps1"
        launcher.write_text("# stub")
        with mock.patch.dict(os.environ, {"APC_HARNESS_LAUNCHER": str(launcher)}, clear=False), \
             mock.patch.object(
                 hv, "_run",
                 side_effect=self._fake_launcher(failed_worker="candidate_witness"),
             ):
            rc = hv._invoke(self.args())
        self.assertEqual(rc, 28)

    def test_evidence_binding_mismatch_is_fail_closed(self):
        launcher = self.root / "launcher.ps1"
        launcher.write_text("# stub")
        with mock.patch.dict(os.environ, {"APC_HARNESS_LAUNCHER": str(launcher)}, clear=False), \
             mock.patch.object(hv, "_run", side_effect=self._fake_launcher(evidence_candidate="3" * 40)):
            rc = hv._invoke(self.args())
        self.assertEqual(rc, 31)

    def test_unknown_check_is_fail_closed(self):
        launcher = self.root / "launcher.ps1"
        launcher.write_text("# stub")
        with mock.patch.dict(os.environ, {"APC_HARNESS_LAUNCHER": str(launcher)}, clear=False), \
             mock.patch.object(hv, "_run", side_effect=self._fake_launcher(check_status="UNKNOWN")):
            rc = hv._invoke(self.args())
        self.assertEqual(rc, 33)

    def test_worker_verify_real_git_isolated_chain(self):
        src = self.root / "src"
        src.mkdir()
        subprocess.run(["git", "init"], cwd=src, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.email", "t@example.invalid"], cwd=src, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=src, check=True)
        rt = src / "runtime"
        rt.mkdir()
        (rt / "entry_consistency_check.py").write_text("print('ENTRY_CONSISTENCY_CHECK=PASS')\n")
        (rt / "test_runtime_offline.py").write_text("print('TOTAL=1 PASS=1 FAIL=0')\n")
        (rt / "test_router_offline.py").write_text("print('TOTAL=1 PASS=1 FAIL=0')\n")
        (rt / "runtime.py").write_text("import argparse\np=argparse.ArgumentParser();p.parse_args()\n")
        (rt / "run.cmd").write_text("@echo off\n")
        subprocess.run(["git", "add", "."], cwd=src, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=src, check=True, stdout=subprocess.DEVNULL)
        base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src, text=True).strip()
        (src / "candidate.txt").write_text("candidate\n")
        subprocess.run(["git", "add", "."], cwd=src, check=True)
        subprocess.run(["git", "commit", "-m", "candidate"], cwd=src, check=True, stdout=subprocess.DEVNULL)
        cand = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src, text=True).strip()
        evidence = self.root / "evidence.json"
        args = argparse.Namespace(
            accepted_base=base, candidate_commit=cand,
            canonical_remote=str(src), evidence_path=str(evidence),
        )
        with mock.patch.dict(os.environ, {"APC_HARNESS_TEST_RUNTIME_CHECK": "PYTHON_HELP"}, clear=False):
            rc = hv._worker_verify(args)
        self.assertEqual(rc, 0)
        ev = json.loads(evidence.read_text())
        self.assertEqual(ev["status"], "SUCCEEDED")
        self.assertEqual(ev["candidate_commit"], cand)
        self.assertIn("candidate.txt", ev["changed_files"])
        self.assertTrue(Path(ev["isolated_worktree"]).exists())
        self.assertTrue(all(c["status"] == "SUCCEEDED" for c in ev["checks"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)