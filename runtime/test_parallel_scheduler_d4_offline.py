"""D4 并行调度离线测试：多 Worker 并行 / 资源锁 / 项目隔离 / WAIT 局部性 / 失效权。

覆盖（测试内模拟并行：mock worker sleep+预设结果，零真实 AI 调用）：
  §56 多 Worker 并发分派（2-3 mock worker 并行，断言都完成且结果正确）
  §57 Resource Lock 冲突排队（两任务抢同一资源 -> 一个 LOCK_WAITING 排队后完成）
  §58 Project Isolation（任务 A 写目录不污染 B；越界写被 SANDBOX_VIOLATION 拒绝）
  §16 WAIT 局部性（A 等待锁/等待审查时 B/C 被分派，不睡死）
  §23/§41 STOP->旧权失效端到端（发起->跑->STOP->旧结果拒绝接受）
  §40 epoch 单调性 / 回滚复活（旧代低 epoch 结果拒绝）
  §30 stale 回收（心跳超时 -> STALE -> 回收并释放资源）
  §38 OUTCOME_UNKNOWN（子进程被杀/超时无明确结果 -> 不猜测，人工/重试入口）

全部离线：tmp 目录构造 state-root；不触真实网络、不消耗真实额度、不读凭据。
"""

import datetime
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from importlib import import_module
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
ps = import_module("parallel_scheduler")


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _parse_iso(value: str) -> float:
    """ISO(带 Z) -> epoch 秒。"""
    if not value:
        return 0.0
    dt = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt.timestamp()


class SchedulerFixture:
    """每用例独立 tmp state-root + 短 sleep 的调度器。"""

    def __init__(self, tmp: Path, **kwargs):
        kwargs.setdefault("sleep_interval", 0.005)
        kwargs.setdefault("max_rounds", 40000)
        self.tmp = tmp
        self.state_root = tmp / "ps-state"
        self.sched = ps.ParallelScheduler(state_root=str(self.state_root), **kwargs)

    def run(self):
        return self.sched.run_until_idle()


def _new_fixture(tmp: Path, **kwargs) -> SchedulerFixture:
    return SchedulerFixture(tmp, **kwargs)


# ---------------------------------------------------------------------------
# §56 多 Worker 并发分派
# ---------------------------------------------------------------------------
class TestConcurrentDispatch(unittest.TestCase):
    def test_concurrent_dispatch_2_workers(self):
        fx = _new_fixture(Path(tempfile.mkdtemp()), max_concurrent=2)
        s = fx.sched
        for i in range(3):
            s.submit({
                "task_id": f"T{i}",
                "goal": f"goal {i}",
                "mock": {"sleep_sec": 0.10, "result": {"value": i, "tag": f"r{i}"}},
            })
        started = time.monotonic()
        summary = fx.run()
        elapsed = time.monotonic() - started
        for i in range(3):
            t = s.tasks[f"T{i}"]
            self.assertEqual(t["state"], ps.TASK_COMPLETED, t)
            self.assertTrue(t["accepted"], t)
            self.assertEqual(t["result"]["result"]["value"], i)
        self.assertEqual(summary["accepted"], 3)
        self.assertEqual(summary["rejected"], 0)
        # 并行证据：3×0.10 顺序=0.30；2 worker 并行应明显小于顺序时间。
        # （v16 §4-A：0.26 阈值仅留 0.04s 裕量，全套件负载下实测 0.266 偶发
        # 越线=假失败；放宽至顺序时间的 95%（0.285），仍保并发判别力。）
        self.assertLess(elapsed, 0.285, f"elapsed={elapsed:.3f}s 应体现并发（顺序约 0.30s）")

    def test_epoch_monotonic_increases(self):
        fx = _new_fixture(Path(tempfile.mkdtemp()), max_concurrent=2)
        s = fx.sched
        s.submit({"task_id": "T-EP", "goal": "g1", "mock": {"sleep_sec": 0.01}})
        fx.run()
        self.assertEqual(s.tasks["T-EP"]["epoch"], 1)
        self.assertEqual(s.current_epoch("T-EP"), 1)
        s.submit({"task_id": "T-EP", "goal": "g2", "mock": {"sleep_sec": 0.01}})
        fx.run()
        self.assertEqual(s.tasks["T-EP"]["epoch"], 2)
        self.assertEqual(s.current_epoch("T-EP"), 2)


# ---------------------------------------------------------------------------
# §57 Resource Lock
# ---------------------------------------------------------------------------
class TestResourceLock(unittest.TestCase):
    def test_lock_conflict_queues_not_fails(self):
        fx = _new_fixture(Path(tempfile.mkdtemp()), max_concurrent=2)
        s = fx.sched
        s.submit({"task_id": "T1", "goal": "g1", "resources": ["shared-r"],
                  "mock": {"sleep_sec": 0.15, "result": {"v": 1}}})
        s.submit({"task_id": "T2", "goal": "g2", "resources": ["shared-r"],
                  "mock": {"sleep_sec": 0.05, "result": {"v": 2}}})
        summary = fx.run()
        self.assertEqual(s.tasks["T1"]["state"], ps.TASK_COMPLETED)
        self.assertEqual(s.tasks["T2"]["state"], ps.TASK_COMPLETED)
        self.assertTrue(s.tasks["T2"]["accepted"], "锁冲突应排队后完成，不失败")
        # T2 曾 LOCK_WAITING（A 持有 shared-r）
        lock_wait = [e for e in s.events
                     if e["task_id"] == "T2" and e["state"] == ps.TASK_LOCK_WAITING]
        self.assertTrue(lock_wait, "T2 应经历 LOCK_WAITING")
        self.assertEqual(summary["accepted"], 2)
        self.assertEqual(summary["rejected"], 0)
        # 锁已全部释放
        self.assertIsNone(s.locks.held_by("shared-r"))

    def test_distinct_resources_run_parallel(self):
        fx = _new_fixture(Path(tempfile.mkdtemp()), max_concurrent=2)
        s = fx.sched
        s.submit({"task_id": "T-A", "goal": "a", "resources": ["r-a"],
                  "mock": {"sleep_sec": 0.12}})
        s.submit({"task_id": "T-B", "goal": "b", "resources": ["r-b"],
                  "mock": {"sleep_sec": 0.12}})
        started = time.monotonic()
        fx.run()
        elapsed = time.monotonic() - started
        self.assertEqual(s.tasks["T-A"]["state"], ps.TASK_COMPLETED)
        self.assertEqual(s.tasks["T-B"]["state"], ps.TASK_COMPLETED)
        self.assertLess(elapsed, 0.22, "不同资源应并行（不因锁串行）")


# ---------------------------------------------------------------------------
# §58 Project Isolation
# ---------------------------------------------------------------------------
class TestProjectIsolation(unittest.TestCase):
    def test_isolation_no_cross_contamination(self):
        fx = _new_fixture(Path(tempfile.mkdtemp()), max_concurrent=2)
        s = fx.sched
        s.submit({"task_id": "T-ISO-A", "goal": "a", "mock": {"sleep_sec": 0.02}})
        s.submit({"task_id": "T-ISO-B", "goal": "b", "mock": {"sleep_sec": 0.02}})
        fx.run()
        wa = Path(s.tasks["T-ISO-A"]["work_dir"])
        wb = Path(s.tasks["T-ISO-B"]["work_dir"])
        self.assertNotEqual(wa, wb, "每个任务必须有独立工作目录")
        # 工作目录位于 state-root/tasks/<id>/epoch-N/work 下
        self.assertTrue(str(wa).replace("\\", "/").startswith(
            str(fx.state_root / "tasks" / "T-ISO-A").replace("\\", "/")))
        self.assertTrue((wa / "evidence.json").exists())
        self.assertTrue((wb / "evidence.json").exists())
        # A 不污染 B：A 的证据只出现在 A 目录
        a_files = {str(p.relative_to(wa)) for p in wa.rglob("*") if p.is_file()}
        b_files = {str(p.relative_to(wb)) for p in wb.rglob("*") if p.is_file()}
        self.assertIn("evidence.json", a_files)
        self.assertIn("evidence.json", b_files)
        self.assertNotEqual((wa / "evidence.json").read_text(encoding="utf-8"),
                            (wb / "evidence.json").read_text(encoding="utf-8"))
        # 隔离目录之外无任务产物
        self.assertFalse((wa.parent.parent / "outside-leak.txt").exists())

    def test_sandbox_violation_detected(self):
        tmp = Path(tempfile.mkdtemp())
        leak = tmp / "outside-leak.txt"
        fx = _new_fixture(tmp, max_concurrent=1)
        s = fx.sched
        s.submit({"task_id": "T-LEAK", "goal": "g",
                  "mock": {"sleep_sec": 0.02, "write_outside": True,
                           "outside_path": str(leak)}})
        summary = fx.run()
        t = s.tasks["T-LEAK"]
        self.assertEqual(t["state"], ps.TASK_SANDBOX_VIOLATION, t)
        self.assertFalse(t["accepted"])
        self.assertTrue(t["rejected"])
        self.assertEqual(t["rejected"][0]["reason"], ps.REJECT_SANDBOX)
        self.assertEqual(summary["rejected"], 1)

    def test_symlink_escape_detected(self):
        """worker 在 work_dir 内建指向外部的 symlink -> SANDBOX_VIOLATION。"""
        tmp = Path(tempfile.mkdtemp())
        outside = tmp / "secret.txt"
        outside.write_text("secret", encoding="utf-8")
        fx = _new_fixture(tmp, max_concurrent=1)
        s = fx.sched
        # 直接构造一个含 symlink 逃逸的结果（模拟 worker 越界行为）
        s.submit({"task_id": "T-LNK", "goal": "g", "mock": {"sleep_sec": 0.01}})
        fx.run()
        t = s.tasks["T-LNK"]
        work = Path(t["work_dir"])
        link = work / "escape"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("symlink 创建不可用（权限/平台）")
        res = s.accept_external_result("T-LNK", {"epoch": 1, "result": {"x": 1}})
        # 任务已 COMPLETED -> 先命中 TASK_NOT_ACTIVE；单独构造 RUNNING 态验证逃逸检测
        self.assertIn(res["verdict"], (ps.REJECT_NOT_ACTIVE, ps.REJECT_SANDBOX))
        # 直接测 _check_sandbox 原语
        verdict = s._check_sandbox(t, {"writes": []})
        self.assertIsNotNone(verdict, "symlink 逃逸应被检出")
        self.assertIn("symlink", verdict)


# ---------------------------------------------------------------------------
# §16 WAIT 局部性
# ---------------------------------------------------------------------------
class TestWaitLocality(unittest.TestCase):
    def test_wait_lock_does_not_block_others(self):
        fx = _new_fixture(Path(tempfile.mkdtemp()), max_concurrent=3)
        s = fx.sched
        s.submit({"task_id": "T-A", "goal": "a", "resources": ["r-w"],
                  "mock": {"sleep_sec": 0.25}})
        s.submit({"task_id": "T-B", "goal": "b", "resources": ["r-w"],
                  "mock": {"sleep_sec": 0.05}})
        s.submit({"task_id": "T-C", "goal": "c", "mock": {"sleep_sec": 0.05}})
        fx.run()
        a, b, c = s.tasks["T-A"], s.tasks["T-B"], s.tasks["T-C"]
        self.assertEqual(a["state"], ps.TASK_COMPLETED)
        self.assertEqual(b["state"], ps.TASK_COMPLETED)
        self.assertEqual(c["state"], ps.TASK_COMPLETED)
        lock_wait = [e for e in s.events
                     if e["task_id"] == "T-B" and e["state"] == ps.TASK_LOCK_WAITING]
        self.assertTrue(lock_wait, "B 应因资源锁进入 LOCK_WAITING")
        # WAIT 局部性：C（无锁）先于 A 完成 —— A 等待/运行不阻塞其余任务
        self.assertLess(_parse_iso(c["finished_at"]), _parse_iso(a["finished_at"]),
                        "C 应在 A 之前完成（等待不阻塞队列）")
        # B 在 A 释放锁后完成
        self.assertLess(_parse_iso(a["finished_at"]), _parse_iso(b["finished_at"]))

    def test_wait_directive_does_not_block_others(self):
        fx = _new_fixture(Path(tempfile.mkdtemp()), max_concurrent=2)
        s = fx.sched
        s.submit({"task_id": "T-W", "goal": "wait-me",
                  "mock": {"sleep_sec": 0.15}})
        s.submit({"task_id": "T-Q", "goal": "quick",
                  "mock": {"sleep_sec": 0.03}})
        # T-W 启动后 0.02s 置 WAITING（等待审查/人工，§16）
        s.add_directive("after_start", "T-W", ps.ACTION_WAIT,
                        reason="waiting review", delay_sec=0.02)
        fx.run()
        w = s.tasks["T-W"]
        q = s.tasks["T-Q"]
        self.assertEqual(q["state"], ps.TASK_COMPLETED)
        # T-W 曾 WAITING；RESUME 后继续完成
        self.assertIn(ps.TASK_WAITING, [e["state"] for e in s.events
                                        if e["task_id"] == "T-W"])
        self.assertEqual(w["state"], ps.TASK_COMPLETED, "RESUME 后应完成")
        self.assertLess(_parse_iso(q["finished_at"]), _parse_iso(w["finished_at"]))


# ---------------------------------------------------------------------------
# §23/§41 STOP -> 旧权失效端到端
# ---------------------------------------------------------------------------
class TestStopRevocation(unittest.TestCase):
    def test_stop_revokes_old_result_end_to_end(self):
        """发起任务 -> 跑 -> STOP -> 旧结果不被接受（端到端）。"""
        fx = _new_fixture(Path(tempfile.mkdtemp()), max_concurrent=1)
        s = fx.sched
        s.submit({"task_id": "T-STOP", "goal": "g",
                  "mock": {"sleep_sec": 0.20, "result": {"value": 42}}})
        s.add_directive("after_start", "T-STOP", ps.ACTION_STOP,
                        reason="end-to-end STOP", delay_sec=0.04)
        summary = fx.run()
        t = s.tasks["T-STOP"]
        self.assertEqual(t["state"], ps.TASK_REVOKED, t)
        self.assertFalse(t["accepted"], "STOP 后结果不得被接受")
        self.assertTrue(t["rejected"], "旧结果应有拒绝记录")
        self.assertEqual(t["rejected"][0]["reason"], ps.REJECT_REVOKED_EPOCH,
                         t["rejected"])
        self.assertEqual(t["revoked_epoch"], 1)
        # 摘要证据
        self.assertEqual(summary["rejected"], 1)
        self.assertEqual(len(summary["revocations"]), 1)
        self.assertEqual(summary["revocations"][0]["rejected_count"], 1)
        # 执行器确实产出了结果（旧结果），只是被拒绝 —— 证明"结果产生但被拒"
        self.assertIsNotNone(t["rejected"][0]["result"])
        self.assertEqual(t["rejected"][0]["result"]["result"]["value"], 42)

    def test_revoke_kills_executor_unknown_outcome(self):
        """REVOKE（kill）-> 执行器提前退出 -> 结果仍被拒（REVOKED_EPOCH）。"""
        fx = _new_fixture(Path(tempfile.mkdtemp()), max_concurrent=1)
        s = fx.sched
        s.submit({"task_id": "T-KILL", "goal": "g",
                  "mock": {"sleep_sec": 0.30, "result": {"value": 7}}})
        s.add_directive("after_start", "T-KILL", ps.ACTION_REVOKE,
                        reason="kill executor", delay_sec=0.03)
        fx.run()
        t = s.tasks["T-KILL"]
        self.assertEqual(t["state"], ps.TASK_REVOKED, t)
        self.assertFalse(t["accepted"])
        self.assertTrue(t["rejected"])
        self.assertEqual(t["rejected"][0]["reason"], ps.REJECT_REVOKED_EPOCH)


# ---------------------------------------------------------------------------
# §40 epoch 单调性 / 回滚复活
# ---------------------------------------------------------------------------
class TestEpochMonotonic(unittest.TestCase):
    def test_rollback_revive_rejected(self):
        fx = _new_fixture(Path(tempfile.mkdtemp()), max_concurrent=1)
        s = fx.sched
        # 1) epoch1 任务运行后被 STOP（revoked_epoch=1）
        s.submit({"task_id": "T-RB", "goal": "g1",
                  "mock": {"sleep_sec": 0.15, "result": {"v": 1}}})
        s.add_directive("after_start", "T-RB", ps.ACTION_STOP,
                        reason="rollback", delay_sec=0.03)
        summary1 = fx.run()
        self.assertEqual(s.tasks["T-RB"]["revoked_epoch"], 1)
        self.assertEqual(summary1["rejected"], 1)
        # 2) 复活：重新授权（epoch 单调 +1 -> 2），结果被接受
        s.submit({"task_id": "T-RB", "goal": "g2",
                  "mock": {"sleep_sec": 0.05, "result": {"v": 2}}})
        summary2 = fx.run()
        t = s.tasks["T-RB"]
        self.assertEqual(t["epoch"], 2)
        self.assertEqual(t["state"], ps.TASK_COMPLETED, t)
        self.assertTrue(t["accepted"])
        self.assertEqual(summary2["accepted"], 1)
        # 3) 回滚复活：旧代结果迟到（epoch0/epoch1）-> 拒绝
        r1 = s.accept_external_result("T-RB", {"epoch": 1, "result": {"v": 1}})
        self.assertEqual(r1["verdict"], ps.REJECT_STALE_EPOCH, r1)
        r0 = s.accept_external_result("T-RB", {"epoch": 0, "result": {"v": 0}})
        self.assertEqual(r0["verdict"], ps.REJECT_STALE_EPOCH, r0)
        # 4) 同代重复投递 -> 拒绝（不重复接受）
        r2 = s.accept_external_result("T-RB", {"epoch": 2, "result": {"v": 2}})
        self.assertEqual(r2["verdict"], ps.REJECT_NOT_ACTIVE, r2)
        # 拒绝记录已累积（旧代 + 重复）
        self.assertGreaterEqual(len(t["rejected"]), 2)


# ---------------------------------------------------------------------------
# §30 stale 回收
# ---------------------------------------------------------------------------
class TestStaleReap(unittest.TestCase):
    def test_stale_heartbeat_reaped(self):
        fx = _new_fixture(Path(tempfile.mkdtemp()), max_concurrent=1,
                          stale_after_sec=0.1)
        s = fx.sched
        # 模拟挂死：0.08s 后停止心跳，但仍在"运行" -> reaper 回收
        s.submit({"task_id": "T-STALE", "goal": "g",
                  "mock": {"sleep_sec": 0.50, "heartbeat_interval_sec": 0.02,
                           "heartbeat_stop_after_sec": 0.08}})
        fx.run()
        t = s.tasks["T-STALE"]
        self.assertEqual(t["state"], ps.TASK_STALE, t)
        self.assertFalse(t["accepted"])
        self.assertTrue(t["rejected"])
        self.assertEqual(t["rejected"][0]["reason"], ps.REJECT_STALE_HEARTBEAT,
                         t["rejected"])
        self.assertIn("心跳超时", t["detail"])

    def test_stale_releases_resource_lock(self):
        fx = _new_fixture(Path(tempfile.mkdtemp()), max_concurrent=1,
                          stale_after_sec=0.1)
        s = fx.sched
        s.submit({"task_id": "T-S1", "goal": "g1", "resources": ["r-st"],
                  "mock": {"sleep_sec": 0.50, "heartbeat_interval_sec": 0.02,
                           "heartbeat_stop_after_sec": 0.08}})
        s.submit({"task_id": "T-S2", "goal": "g2", "resources": ["r-st"],
                  "mock": {"sleep_sec": 0.03}})
        fx.run()
        self.assertEqual(s.tasks["T-S1"]["state"], ps.TASK_STALE)
        self.assertEqual(s.tasks["T-S2"]["state"], ps.TASK_COMPLETED,
                         "stale 回收释放资源锁后，排队任务应能继续")
        self.assertIsNone(s.locks.held_by("r-st"))


# ---------------------------------------------------------------------------
# §38 OUTCOME_UNKNOWN
# ---------------------------------------------------------------------------
class TestOutcomeUnknown(unittest.TestCase):
    def test_outcome_unknown_no_guess(self):
        fx = _new_fixture(Path(tempfile.mkdtemp()), max_concurrent=1)
        s = fx.sched
        s.submit({"task_id": "T-UNK", "goal": "g",
                  "mock": {"sleep_sec": 0.02, "outcome": ps.VERDICT_OUTCOME_UNKNOWN,
                           "exit_code": None}})
        summary = fx.run()
        t = s.tasks["T-UNK"]
        self.assertEqual(t["state"], ps.TASK_OUTCOME_UNKNOWN, t)
        self.assertEqual(t["outcome"], ps.VERDICT_OUTCOME_UNKNOWN)
        self.assertEqual(t["decision_entry"], "MANUAL_OR_RETRY",
                         "结果不明必须提供人工/重试决策入口，不自动判定成败")
        self.assertFalse(t["accepted"])
        self.assertEqual(summary["outcome_unknown"][0]["decision_entry"],
                         "MANUAL_OR_RETRY")

    def test_unknown_not_counted_as_success_or_failure(self):
        fx = _new_fixture(Path(tempfile.mkdtemp()), max_concurrent=2)
        s = fx.sched
        s.submit({"task_id": "T-OK", "goal": "ok", "mock": {"sleep_sec": 0.02}})
        s.submit({"task_id": "T-UNK2", "goal": "unk",
                  "mock": {"sleep_sec": 0.02, "outcome": ps.VERDICT_OUTCOME_UNKNOWN}})
        summary = fx.run()
        states = summary["states"]
        self.assertEqual(states.get(ps.TASK_COMPLETED), 1)
        self.assertEqual(states.get(ps.TASK_OUTCOME_UNKNOWN), 1)
        self.assertNotIn(ps.TASK_FAILED, states)
        self.assertEqual(summary["accepted"], 1)


# ---------------------------------------------------------------------------
# CLI 型执行器（真实子进程，零真实 AI）
# ---------------------------------------------------------------------------
class TestCliExecutor(unittest.TestCase):
    def _worker_config(self, tmp: Path) -> str:
        cfg = {
            "schema": "WORKER_ADAPTER_CONFIG",
            "schema_version": 1,
            "default_timeout_sec": 30,
            "workers": [{
                "id": "worker-mock-cli", "name": "Mock CLI",
                "role": "worker", "type": "LOCAL_RUNTIME", "status": "official",
                "entry": {"kind": "command",
                          "command": [sys.executable, "-"], "cwd": None},
                "health_check": {"kind": "file", "path": sys.executable},
                "timeout_sec": 30, "adapter": "adapter-local-command",
                "capabilities": ["cap-local-python"],
            }],
        }
        p = tmp / "worker_config.json"
        p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        return str(p)

    def test_cli_executor_subprocess_mock(self):
        """CLI 执行器经真实子进程调用 worker_adapter（mock 通道，零 AI 消耗）。"""
        tmp = Path(tempfile.mkdtemp())
        fx = _new_fixture(tmp, max_concurrent=1, mode="cli",
                          worker_config=self._worker_config(tmp))
        s = fx.sched
        s.submit({"task_id": "T-CLI", "goal": "cli goal",
                  "worker_id": "worker-mock-cli",
                  "cli": {"timeout_sec": 20}})
        summary = fx.run()
        t = s.tasks["T-CLI"]
        self.assertEqual(t["state"], ps.TASK_COMPLETED, t)
        self.assertTrue(t["accepted"])
        self.assertEqual(summary["accepted"], 1)
        self.assertEqual(summary["rejected"], 0)
        # goal 文件位于隔离 work_dir 内
        self.assertTrue((Path(t["work_dir"]) / "goal.txt").exists())
        # 隔离校验通过（writes 为空时 symlink 扫描无异常）
        self.assertIsNone(s._check_sandbox(t, {"writes": []}))

    def test_cli_executor_timeout_unknown(self):
        """CLI 超时无明确结果 -> OUTCOME_UNKNOWN（§38，不猜测）。"""
        tmp = Path(tempfile.mkdtemp())
        fx = _new_fixture(tmp, max_concurrent=1, mode="cli")
        s = fx.sched
        # 子进程 sleep 0.3 > 超时 0.1 -> 被杀 -> OUTCOME_UNKNOWN
        cmd = [sys.executable, "-c",
               "import time; time.sleep(0.3); print('late result')"]
        s.submit({"task_id": "T-CLIT", "goal": "g",
                  "cli": {"command": cmd, "timeout_sec": 0.1}})
        fx.run()
        t = s.tasks["T-CLIT"]
        self.assertEqual(t["state"], ps.TASK_OUTCOME_UNKNOWN, t)
        self.assertEqual(t["decision_entry"], "MANUAL_OR_RETRY")
        self.assertFalse(t["accepted"])


# ---------------------------------------------------------------------------
# 单实例锁 / CLI 集成
# ---------------------------------------------------------------------------
class TestSingleInstanceLock(unittest.TestCase):
    def test_single_instance_lock(self):
        tmp = Path(tempfile.mkdtemp())
        lock_dir = tmp / "scheduler.lock"
        a = ps.SingleInstanceLock(str(lock_dir), ttl_sec=10)
        b = ps.SingleInstanceLock(str(lock_dir), ttl_sec=10)
        self.assertTrue(a.acquire(), "第一实例应获得锁")
        self.assertFalse(b.acquire(), "第二实例应 SKIP_LOCKED")
        a.release()
        self.assertTrue(b.acquire(), "释放后第三实例应获得锁")
        b.release()
        self.assertFalse(lock_dir.exists(), "锁释放后目录应删除")

    def test_stale_lock_takeover(self):
        tmp = Path(tempfile.mkdtemp())
        lock_dir = tmp / "scheduler.lock"
        a = ps.SingleInstanceLock(str(lock_dir), ttl_sec=0.01)
        self.assertTrue(a.acquire())
        # 篡改 lock.json 的 at 为过去 -> stale -> 接管
        info = ps.load_json(str(lock_dir / "lock.json"))
        info["at"] = "2000-01-01T00:00:00.000Z"
        ps.save_json(str(lock_dir / "lock.json"), info)
        b = ps.SingleInstanceLock(str(lock_dir), ttl_sec=10)
        self.assertTrue(b.acquire(), "stale 锁应被接管（token/age 接管）")
        b.release()


class TestCliRunIntegration(unittest.TestCase):
    def _tasks_file(self, tmp: Path) -> str:
        tasks = {
            "schema": ps.TASKS_SCHEMA,
            "schema_version": 1,
            "tasks": [
                {"task_id": "I1", "goal": "t1",
                 "mock": {"sleep_sec": 0.05, "result": {"v": 1}}},
                {"task_id": "I2", "goal": "t2",
                 "mock": {"sleep_sec": 0.05, "result": {"v": 2}}},
            ],
        }
        p = tmp / "tasks.json"
        p.write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")
        return str(p)

    def test_cli_run_exit0(self):
        tmp = Path(tempfile.mkdtemp())
        code = ps.main(["run", "--tasks-file", self._tasks_file(tmp),
                        "--state-root", str(tmp / "state"),
                        "--max-concurrent", "2"])
        self.assertEqual(code, ps.EXIT_OK)
        summary = ps.load_json(str(tmp / "state" / "last-run.json"))
        self.assertIsNotNone(summary)
        self.assertEqual(summary["accepted"], 2)
        self.assertEqual(summary["rejected"], 0)

    def test_cli_run_stop_exit2(self):
        """CLI run 含 STOP directive -> 旧结果被拒 -> 退出码 2（硬停）。"""
        tmp = Path(tempfile.mkdtemp())
        tasks = {
            "schema": ps.TASKS_SCHEMA, "schema_version": 1,
            "tasks": [{"task_id": "S1", "goal": "g",
                       "mock": {"sleep_sec": 0.20, "result": {"v": 1}}}],
        }
        tf = tmp / "tasks.json"
        tf.write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")
        code = ps.main(["run", "--tasks-file", str(tf),
                        "--state-root", str(tmp / "state"),
                        "--stop-task", "S1"])
        self.assertEqual(code, ps.EXIT_HARD_STOP)
        summary = ps.load_json(str(tmp / "state" / "last-run.json"))
        self.assertEqual(summary["rejected"], 1)
        self.assertEqual(len(summary["revocations"]), 1)

    def test_cli_config_error_exit1(self):
        tmp = Path(tempfile.mkdtemp())
        bad = tmp / "bad.json"
        bad.write_text('{"schema": "WRONG"}', encoding="utf-8")
        code = ps.main(["run", "--tasks-file", str(bad),
                        "--state-root", str(tmp / "state")])
        self.assertEqual(code, ps.EXIT_CONFIG_ERROR)

    def test_reset_status(self):
        tmp = Path(tempfile.mkdtemp())
        state = str(tmp / "state")
        ps.main(["run", "--tasks-file", self._tasks_file(tmp),
                 "--state-root", state])
        code = ps.main(["status", "--state-root", state])
        self.assertEqual(code, ps.EXIT_OK)
        code = ps.main(["reset", "--state-root", state])
        self.assertEqual(code, ps.EXIT_OK)
        self.assertFalse(Path(state).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
