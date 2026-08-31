#!/usr/bin/env python3
"""GATE-2#7/#8/#9 (hardening 2026-08-31) concurrency hardening offline tests.

  N1  _acquire_resources is all-or-nothing (partial failure rolls back —
      previously two opposite-order requesters could deadlock holding one
      resource each)
  N2  reap_stale actually terminates a stale CLI child (previously _stop_event
      had no consumer for CLI workers: heartbeat-dead worker kept running
      while its locks were handed to others — §57 breached)
  N3  accept_external_result refuses epoch-less straggler results (previously
      setdefault bound them to the CURRENT epoch — §40 bypass)
  N4  RunLock: a just-created empty lock file is NOT broken (age proves
      staleness, not parseability); an aged empty lock is reclaimed
  N5  relay drive-lock: a fresh lock dir without lock.json is initialization-
      in-progress -> SKIP_LOCKED (never evict); an aged dir is reclaimed

All offline: tmp state roots / tmp lock dirs; the relay test patches
LOCK_DIR away from the real relay queue. No real worker, no network.
"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from importlib import import_module
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

ps = import_module("parallel_scheduler")
SCRIPTS = HERE.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
ra = import_module("relay_autopilot")
rt_core = import_module("runtime")


class AcquireRollbackTests(unittest.TestCase):
    def test_n1_partial_failure_rolls_back_taken_locks(self):
        fx = ps.ParallelScheduler(state_root=str(Path(tempfile.mkdtemp()) / "ps"))
        # Someone else holds r2: our task wants r1+r2, r1 free, r2 taken.
        self.assertTrue(fx.locks.acquire("r2", "other-task"))
        task = {"task_id": "t1", "resources": ["r1", "r2"]}
        ok = fx._acquire_resources(task)
        self.assertFalse(ok)
        # THE FIX: r1 must have been released again (all-or-nothing).
        self.assertIsNone(fx.locks.held_by("r1"),
                          "partial acquire left r1 held -> opposite-order deadlock")


class StaleCliTerminationTests(unittest.TestCase):
    def test_n2_reap_stale_terminates_cli_child(self):
        tmp = Path(tempfile.mkdtemp())
        fx = ps.ParallelScheduler(state_root=str(tmp / "ps"), mode="cli",
                                  stale_after_sec=0.3, sleep_interval=0.02)
        sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]
        fx.submit({"task_id": "T-STALE", "goal": "sleep", "cli": {"command": sleeper}})
        # Dispatch (run_once) then wait for heartbeat staleness.
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            fx.run_once()
            t = fx.tasks["T-STALE"]
            if t["state"] == ps.TASK_RUNNING:
                break
            time.sleep(0.02)
        self.assertEqual(fx.tasks["T-STALE"]["state"], ps.TASK_RUNNING)
        # The dispatch thread stores the executor asynchronously: wait for it.
        executor = None
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            executor = fx._executors.get("T-STALE")
            if executor is not None:
                break
            time.sleep(0.02)
        self.assertIsNotNone(executor, "executor never registered")
        self.assertIsNotNone(executor.proc)
        # Simulate REAL heartbeat death: kill the worker's monitor thread (it
        # would otherwise keep refreshing heartbeat_at forever and the task
        # would never look stale). After the monitor dies, heartbeat freezes.
        executor._monitor_stop.set()
        # Simulate heartbeat death beyond stale_after_sec.
        time.sleep(0.5)
        changed = fx.reap_stale()
        self.assertEqual(changed, 1)
        self.assertEqual(fx.tasks["T-STALE"]["state"], ps.TASK_STALE)
        # THE FIX: the monitor consumes _stop_event and terminates the child.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if executor.proc.poll() is not None:
                break
            time.sleep(0.05)
        self.assertIsNotNone(executor.proc.poll(), "stale CLI child still running after reap (§57)")


class ExternalEpochTests(unittest.TestCase):
    def test_n3_epochless_external_result_refused(self):
        fx = ps.ParallelScheduler(state_root=str(Path(tempfile.mkdtemp()) / "ps"))
        fx.submit({"task_id": "T-EX", "goal": "g",
                   "mock": {"sleep_sec": 0.01, "result": {"ok": 1}}})
        # Let it finish so an (artificial) straggler arrives afterwards.
        fx.run_until_idle()
        res = fx.accept_external_result("T-EX", {"outcome": "SUCCESS", "ok": True})
        self.assertFalse(res.get("ok"), res)
        self.assertEqual(res.get("error"), "STALE_EPOCH")
        # With an explicit (current) epoch the normal path still works.
        epoch = fx.current_epoch("T-EX")
        res2 = fx.accept_external_result(
            "T-EX", {"outcome": "SUCCESS", "ok": True, "epoch": epoch})
        self.assertTrue(res2.get("ok", False) or "error" not in res2 or res2.get("ok") is True,
                        res2)


class RunLockAgeTests(unittest.TestCase):
    """RunLock builds its path as RUNS_ROOT/<run_id>/.lock with RUNS_ROOT read
    at IMPORT time — patch the module attribute, never pass a raw path."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.runs_root = Path(self.td.name) / "runs"
        self.runs_root.mkdir(parents=True)
        self._saved_root = rt_core.RUNS_ROOT
        rt_core.RUNS_ROOT = self.runs_root

    def tearDown(self):
        rt_core.RUNS_ROOT = self._saved_root
        self.td.cleanup()

    def _fresh_empty_lock(self) -> Path:
        run_dir = self.runs_root / "RUN-LOCKTEST"
        run_dir.mkdir(parents=True)
        lock_path = run_dir / ".lock"
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)  # empty file: owner is between O_CREAT and pid/ts write
        return lock_path

    def test_n4a_fresh_empty_lock_not_broken(self):
        lock_path = self._fresh_empty_lock()
        rl = rt_core.RunLock("RUN-LOCKTEST")
        rl._break_if_stale()
        self.assertTrue(lock_path.exists(),
                        "a JUST-CREATED empty lock was broken -> double holder")

    def test_n4b_aged_empty_lock_reclaimed(self):
        lock_path = self._fresh_empty_lock()
        old = time.time() - (rt_core.LOCK_STALE_SEC + 10)
        os.utime(lock_path, (old, old))
        rl = rt_core.RunLock("RUN-LOCKTEST")
        rl._break_if_stale()
        self.assertFalse(lock_path.exists(), "aged empty lock should be reclaimed")


class RelayLockWindowTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.lock_dir = Path(self.td.name) / "lock"
        self._saved = ra.LOCK_DIR
        ra.LOCK_DIR = str(self.lock_dir)

    def tearDown(self):
        ra.LOCK_DIR = self._saved
        self.td.cleanup()

    def test_n5a_empty_dir_is_claimable(self):
        """GATE-2#9 final semantics: an empty dir (no lock.json) is harmless —
        the lock file itself is the atomic claim, so anyone may claim it."""
        self.lock_dir.mkdir(parents=True)
        token = ra.acquire_lock()
        self.assertIsNotNone(token, "empty dir must be claimable (O_EXCL on lock.json)")
        self.assertTrue((self.lock_dir / "lock.json").exists())
        ra.release_lock(token)
        self.assertFalse(self.lock_dir.exists())

    def test_n5c_torn_claim_file_self_heals(self):
        """A crashed owner leaves a torn lock.json: next acquire reclaims."""
        self.lock_dir.mkdir(parents=True)
        (self.lock_dir / "lock.json").write_text('{"token": "hal', encoding="utf-8")
        token = ra.acquire_lock()
        self.assertIsNotNone(token, "torn claim file should self-heal")
        info = json.loads((self.lock_dir / "lock.json").read_text(encoding="utf-8"))
        self.assertEqual(info["token"], token)

    def test_n5d_concurrent_acquire_exactly_one_winner(self):
        """Two threads racing acquire_lock: exactly one holds the lock."""
        self.lock_dir.mkdir(parents=True)
        results = []
        barrier = threading.Barrier(2)

        def worker():
            barrier.wait(timeout=10)
            results.append(ra.acquire_lock())

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start(); t2.start(); t1.join(timeout=30); t2.join(timeout=30)
        winners = [t for t in results if t is not None]
        self.assertEqual(len(winners), 1, f"double holder! tokens={results}")
        ra.release_lock(winners[0])

    def test_n5b_aged_dir_without_lockjson_reclaimed(self):
        self.lock_dir.mkdir(parents=True)
        old = time.time() - 400
        os.utime(self.lock_dir, (old, old))
        token = ra.acquire_lock()
        self.assertIsNotNone(token, "aged lock dir should be reclaimed")
        self.assertTrue((self.lock_dir / "lock.json").exists())
        ra.release_lock(token)
        self.assertFalse(self.lock_dir.exists())


if __name__ == "__main__":
    unittest.main()
