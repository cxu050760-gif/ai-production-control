#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parallel_scheduler.py — D4 多 Worker 并行调度 + 资源锁 + 项目隔离 + 失效权
(执衡 v1.1-blackbox)

覆盖宪法条款（机器可完成部分，真实多 Worker 生产并行留业主 L3）：
  §56 多 Worker      任务队列 -> 并发分派到多个 Worker（CLI 型，复用 worker_adapter
                      的协议概念；调度器经子进程或线程池调用 Worker）。
  §57 Resource Lock   每资源互斥锁（mkdir 原子 + token/age stale 接管，与
                      D1/D2 已验证锁模式同源）；冲突排队（LOCK_WAITING）不失败。
  §58 Project Isolation  每个任务独立工作目录，Worker 只能写自己的目录；
                      调度器校验"无越界写"（sandbox 边界检查 + symlink 逃逸扫描）。
  §16 WAIT 局部性     任务 A 等待锁 / 等待审查时，调度器自动分派其他 READY 任务
                      （不睡死）。
  §23/§41 失效权      STOP/REVOKE directive -> 正在跑的执行单元被标记失效（REVOKED）
                      -> 后续结果拒绝接受（STALE_EPOCH / REVOKED_EPOCH）。
  §40 Revocation 单调性 每个授权/任务有递增 epoch；回滚/复活的旧任务（低 epoch）
                      被拒绝。
  §30 Stale Safety   超时/无心跳的执行单元 -> STALE -> 回收并释放资源。
  §38 OUTCOME_UNKNOWN 执行结果状态不明（子进程被杀/超时无明确结果）-> 不猜测：
                      标记 OUTCOME_UNKNOWN + 人工/重试决策入口，不自动判定成败。

命令:
  run --tasks-file F [--directives-file F] [--stop-task T] [--max-concurrent N]
      [--mode mock|cli] [--state-root DIR] [--timeout SEC] [--stale-after SEC]
      [--lock-ttl SEC] [--worker-config F]
      运行调度直至队列收敛；结构化 JSON 输出；退出码 0/1/2。
  status [--state-root DIR]
      打印最近一次 run 摘要（只读）。
  directive --task-id X --action STOP|REVOKE|WAIT|RESUME [--state-root DIR]
      对运行中的调度状态施加 directive（供人工/L2 操作）。
  reset [--state-root DIR]
      清空调度状态（state-root 下 tasks/locks/last-run；不碰真实项目状态）。

退出码约定（与 D2 cost_router 一致）：
  0 = 成功（全部结果被接受，无失效拒绝、无 OUTCOME_UNKNOWN）
  1 = 配置/输入错误
  2 = 硬停（存在被拒绝的旧结果 / OUTCOME_UNKNOWN 需人工决策 / directive 失效）

红线：
  1) 真实 AI worker 调用消耗真实额度，属 L3 业主；本模块 mock 模式零消耗，
     cli 模式仅用于本地运行时/无害命令（如 worker_adapter mock 通道）。
  2) 凭据不入仓；worker 只登记路径/命令，不携带 token。
  3) 输出为 inert 数据（non_authority）。
  4) 不改 src/aicontrol/、config/production.json、runtime/runtime.py、
     config/capability-registry.json、runtime/adapters/ 既有文件（只读衔接）。
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCHEMA = "PARALLEL_SCHEDULER"
TASKS_SCHEMA = "PARALLEL_SCHEDULER_TASKS"
DIRECTIVES_SCHEMA = "PARALLEL_SCHEDULER_DIRECTIVES"
MOCK_RESULT_SCHEMA = "PARALLEL_SCHEDULER_MOCK_RESULT"

# 默认状态根（运行时工件；测试/生产可 --state-root 覆盖）
DEFAULT_STATE_DIR = os.path.join("state", "parallel-scheduler")

DEFAULT_MAX_CONCURRENT = 2
DEFAULT_TIMEOUT_SEC = 300.0
DEFAULT_STALE_AFTER_SEC = 120.0
DEFAULT_LOCK_TTL_SEC = 300.0
DEFAULT_SLEEP_INTERVAL = 0.02
DEFAULT_MAX_ROUNDS = 100000
DEFAULT_HEARTBEAT_INTERVAL = 0.05

# 退出码约定（与 D2 cost_router 一致）
EXIT_OK = 0
EXIT_CONFIG_ERROR = 1
EXIT_HARD_STOP = 2

# 任务状态
TASK_PENDING = "PENDING"                    # 入队未分派
TASK_READY = "READY"                        # 可分派
TASK_RUNNING = "RUNNING"                    # 执行单元运行中
TASK_LOCK_WAITING = "LOCK_WAITING"          # 资源锁冲突排队（§57）
TASK_WAITING = "WAITING"                    # 等待审查/人工（§16，不阻塞队列）
TASK_COMPLETED = "COMPLETED"                # 结果被接受
TASK_FAILED = "FAILED"                      # 明确失败（退出码非零且结果明确）
TASK_OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"    # §38 结果不明，不猜测
TASK_REVOKED = "REVOKED"                    # §23/§41 授权失效
TASK_STALE = "STALE"                        # §30 心跳超时回收
TASK_ABORTED = "ABORTED"                    # 调度级中止
TASK_SANDBOX_VIOLATION = "SANDBOX_VIOLATION"  # §58 越界写

STATE_TERMINAL = frozenset({
    TASK_COMPLETED, TASK_FAILED, TASK_OUTCOME_UNKNOWN, TASK_REVOKED,
    TASK_STALE, TASK_ABORTED, TASK_SANDBOX_VIOLATION,
})

# 结果判定
VERDICT_SUCCESS = "SUCCESS"
VERDICT_FAILURE = "FAILURE"
VERDICT_OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"

# 接受/拒绝原因
ACCEPT_OK = "ACCEPTED"
REJECT_NOT_ACTIVE = "TASK_NOT_ACTIVE"
REJECT_STALE_EPOCH = "STALE_EPOCH"
REJECT_REVOKED_EPOCH = "REVOKED_EPOCH"
REJECT_STALE_HEARTBEAT = "STALE_HEARTBEAT"
REJECT_SANDBOX = "SANDBOX_VIOLATION"
REJECT_TASK_NOT_FOUND = "TASK_NOT_FOUND"

# directive 动作
ACTION_STOP = "STOP"
ACTION_REVOKE = "REVOKE"
ACTION_WAIT = "WAIT"
ACTION_RESUME = "RESUME"
VALID_ACTIONS = frozenset({ACTION_STOP, ACTION_REVOKE, ACTION_WAIT, ACTION_RESUME})

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
RESOURCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")

_MAX_TAIL = 2000


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def _safe_text(value: Any, limit: int = 2000) -> str:
    if value is None:
        return ""
    text = str(value)
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return text[:limit]


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _now_epoch() -> float:
    return time.time()


def _stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d%H%M%S")


def _age_seconds(at_iso: Optional[str], now_epoch: Optional[float] = None) -> Optional[float]:
    """ISO 时间差（秒）；解析失败返回 None。"""
    if not at_iso:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(at_iso).replace("Z", "+00:00"))
        now = datetime.datetime.now(datetime.timezone.utc) if now_epoch is None else \
            datetime.datetime.fromtimestamp(now_epoch, datetime.timezone.utc)
        return (now - dt).total_seconds()
    except (ValueError, TypeError, OverflowError):
        return None


def ensure_id(value: Any, fallback_prefix: str = "TASK") -> str:
    """把任意字符串规范成符合 ID_RE 的 id（与 relay_autopilot 同源）。"""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", str(value or ""))
    cleaned = re.sub(r"-+", "-", cleaned).strip(".-_")
    if not cleaned:
        cleaned = fallback_prefix
    if not re.match(r"^[A-Za-z0-9]", cleaned):
        cleaned = "A" + cleaned
    if len(cleaned) > 119:
        cleaned = cleaned[:119]
    return cleaned


def _safe_resource_name(value: Any) -> str:
    """资源名清洗：只允许 [A-Za-z0-9._-]，禁止 '.'/'..' 与路径分隔。"""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", str(value or ""))
    cleaned = cleaned.strip(".-_")
    if not cleaned or cleaned in (".", ".."):
        raise ValueError(f"invalid resource name: {value!r}")
    if not RESOURCE_RE.match(cleaned):
        raise ValueError(f"invalid resource name after sanitize: {cleaned!r}")
    return cleaned


def load_json(path: str, default: Any = None) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def save_json(path: str, value: Any) -> None:
    """原子写 JSON（tmp + os.replace）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.tmp-{os.getpid()}-{random.randint(1000, 9999)}")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def _path_within(root: Path, target: Path) -> bool:
    """target 是否位于 root 内（解析 symlink 后判断，防逃逸）。"""
    try:
        root_res = root.resolve()
        tgt = target if target.is_absolute() else (root / target)
        tgt_res = tgt.resolve()
        tgt_res.relative_to(root_res)
        return True
    except (ValueError, OSError):
        return False


def _repo_root() -> Path:
    """仓库根 = 本文件上一级（runtime/..）。"""
    return Path(__file__).resolve().parent.parent


def _default_state_root() -> Path:
    return _repo_root() / DEFAULT_STATE_DIR


# ---------------------------------------------------------------------------
# 单实例锁（调度器互斥；mkdir 原子 + token/age stale 接管）
# ---------------------------------------------------------------------------
class SingleInstanceLock:
    """调度器单实例锁：防止两个 parallel_scheduler 并行。

    锁语义与 relay_autopilot.acquire_lock / D2 cost_router 同源：
      - mkdir 原子占用（os.mkdir 失败即已占用）；
      - lock.json 记录 token + at；age 在 [0, ttl] 视为新鲜（他人持有）；
      - age > ttl 或解析失败/未来时间 -> stale -> 回收重建（接管）。
    """

    def __init__(self, lock_dir: str, ttl_sec: float = DEFAULT_LOCK_TTL_SEC):
        self.lock_dir = Path(lock_dir)
        self.ttl_sec = float(ttl_sec)
        self.token = f"{_stamp()}-{random.randint(1000, 9999)}{random.randint(1000, 9999)}"

    def acquire(self) -> bool:
        try:
            self.lock_dir.parent.mkdir(parents=True, exist_ok=True)
            os.mkdir(self.lock_dir)
        except FileExistsError:
            info = load_json(str(self.lock_dir / "lock.json"))
            if info:
                age = _age_seconds(info.get("at"))
                if age is not None and 0 <= age <= self.ttl_sec:
                    return False  # 新鲜锁：他人持有，绝不覆盖
            # stale / 解析失败 / 未来时间 -> 回收重建
            shutil.rmtree(self.lock_dir, ignore_errors=True)
            try:
                os.mkdir(self.lock_dir)
            except FileExistsError:
                return False
        save_json(str(self.lock_dir / "lock.json"),
                  {"token": self.token, "at": _now_iso(), "owner": "parallel_scheduler"})
        return True

    def release(self) -> None:
        info = load_json(str(self.lock_dir / "lock.json"))
        if info and info.get("token") == self.token:
            try:
                os.remove(self.lock_dir / "lock.json")
            except OSError:
                pass
            try:
                os.rmdir(self.lock_dir)
            except OSError:
                pass

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()


# ---------------------------------------------------------------------------
# 资源锁（§57）：每资源互斥；冲突排队（LOCK_WAITING）不失败
# ---------------------------------------------------------------------------
class ResourceLockManager:
    """每资源互斥锁：进程内快表 + 磁盘 mkdir 原子锁（跨进程可见）。

    acquire 语义：
      - 资源已由他人持有（新鲜锁）-> False（调用方置 LOCK_WAITING 排队）；
      - 资源锁 stale（age>ttl 或损坏）-> 回收重建接管；
      - 同任务重复 acquire 同一资源 -> 幂等 True（任务内不自己卡自己）。
    """

    def __init__(self, lock_root: str, ttl_sec: float = DEFAULT_LOCK_TTL_SEC):
        self.lock_root = Path(lock_root)
        self.ttl_sec = float(ttl_sec)
        self._held: Dict[str, str] = {}  # resource -> task_id（进程内快表）
        self._guard = threading.Lock()

    def _res_dir(self, resource: str) -> Path:
        name = _safe_resource_name(resource)
        return self.lock_root / name

    def acquire(self, resource: str, task_id: str) -> bool:
        name = _safe_resource_name(resource)
        with self._guard:
            holder = self._held.get(name)
            if holder is not None and holder != task_id:
                return False
        d = self._res_dir(name)
        try:
            d.parent.mkdir(parents=True, exist_ok=True)
            os.mkdir(d)
        except FileExistsError:
            info = load_json(str(d / "lock.json"))
            if info:
                age = _age_seconds(info.get("at"))
                if age is not None and 0 <= age <= self.ttl_sec:
                    other = info.get("task_id")
                    if other and other != task_id:
                        return False  # 新鲜锁，他人持有
                    # 同一任务重入 / 无 task_id 的残留 -> 视为可接管（同任务幂等）
                # stale / 损坏 -> 回收接管
            shutil.rmtree(d, ignore_errors=True)
            try:
                os.mkdir(d)
            except FileExistsError:
                return False
        save_json(str(d / "lock.json"), {
            "resource": name, "task_id": task_id,
            "token": f"{_stamp()}-{random.randint(1000, 9999)}",
            "at": _now_iso(),
        })
        with self._guard:
            self._held[name] = task_id
        return True

    def release(self, resource: str, task_id: str) -> None:
        name = _safe_resource_name(resource)
        d = self._res_dir(name)
        info = load_json(str(d / "lock.json"))
        if info and info.get("task_id") == task_id:
            try:
                os.remove(d / "lock.json")
            except OSError:
                pass
            try:
                os.rmdir(d)
            except OSError:
                pass
        with self._guard:
            if self._held.get(name) == task_id:
                del self._held[name]

    def held_by(self, resource: str) -> Optional[str]:
        name = _safe_resource_name(resource)
        with self._guard:
            if name in self._held:
                return self._held[name]
        info = load_json(str(self._res_dir(name) / "lock.json"))
        if info:
            age = _age_seconds(info.get("at"))
            if age is not None and 0 <= age <= self.ttl_sec:
                return _safe_text(info.get("task_id"), 128) or None
        return None


# ---------------------------------------------------------------------------
# Worker 执行器（CLI 型协议概念：goal -> 执行 -> 结构化结果）
# ---------------------------------------------------------------------------
class MockWorkerExecutor:
    """内置假 Worker：心跳循环 sleep + 返回预设结果（测试内模拟并行，零 AI 调用）。

    行为由 task['mock'] 控制：
      sleep_sec             模拟执行时长
      heartbeat_interval_sec 心跳间隔（reaper 观察）
      result / exit_code / outcome  预设结果（SUCCESS|FAILURE|OUTCOME_UNKNOWN）
      write_outside / outside_path  模拟 §58 越界写（测试 sandbox 检查）
      note                  附加说明
    """

    def __init__(self, scheduler: "ParallelScheduler", task: Dict[str, Any]):
        self.scheduler = scheduler
        self.task = task
        spec = task.get("mock") or {}
        self.sleep_sec = float(spec.get("sleep_sec", 0.05))
        self.heartbeat_interval = float(spec.get("heartbeat_interval_sec", 0.01))
        raw_hb_stop = spec.get("heartbeat_stop_after_sec")
        self.heartbeat_stop_after_sec = (float(raw_hb_stop)
                                         if raw_hb_stop is not None else None)
        self.result = dict(spec.get("result") or {})
        # exit_code：缺省 0（成功）；显式 None = 无明确退出码（OUTCOME_UNKNOWN）
        if "exit_code" in spec and spec.get("exit_code") is None:
            self.exit_code = None
        else:
            raw_exit = spec.get("exit_code")
            self.exit_code = int(raw_exit) if raw_exit is not None else 0
        self.outcome = str(spec.get("outcome") or
                           (VERDICT_SUCCESS if self.exit_code == 0 else VERDICT_FAILURE))
        self.write_outside = bool(spec.get("write_outside", False))
        self.outside_path = str(spec.get("outside_path", ""))
        self.note = str(spec.get("note", ""))

    def run(self) -> Dict[str, Any]:
        start = time.monotonic()
        work_dir = Path(self.task["work_dir"])
        work_dir.mkdir(parents=True, exist_ok=True)
        stop_event = self.task.get("_stop_event")
        deadline = start + self.sleep_sec
        stop_heartbeat_at = None
        if self.heartbeat_stop_after_sec is not None:
            stop_heartbeat_at = start + self.heartbeat_stop_after_sec
        while True:
            now = time.monotonic()
            # 模拟挂死：超过 heartbeat_stop_after_sec 后不再心跳（reaper 可回收）
            if stop_heartbeat_at is None or now < stop_heartbeat_at:
                self.scheduler._touch_heartbeat(self.task)
            if stop_event is not None and stop_event.is_set():
                break
            remaining = deadline - now
            if remaining <= 0:
                break
            time.sleep(min(self.heartbeat_interval, remaining))
        stopped = stop_event is not None and stop_event.is_set()

        # 写入证据（隔离演示：只写自己的 work_dir）
        evidence = {
            "task_id": self.task["task_id"],
            "epoch": int(self.task["epoch"]),
            "worker_id": _safe_text(self.task.get("worker_id"), 128),
            "produced_at": self.scheduler._now(),
            "mock": True,
            "checks": ["mock_exec: PASS"],
        }
        evidence_file = work_dir / "evidence.json"
        evidence_file.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
        writes = [str(evidence_file)]

        if self.write_outside:
            outside = Path(self.outside_path) if self.outside_path \
                else (work_dir.parent.parent / "outside-leak.txt")
            try:
                outside.parent.mkdir(parents=True, exist_ok=True)
                outside.write_text("leak", encoding="utf-8")
                writes.append(str(outside))
            except OSError as exc:  # 越界写失败也记录（sandbox 校验仍会拒）
                writes.append(f"<write-failed: {exc}>")

        self.scheduler._touch_heartbeat(self.task)
        elapsed = round(time.monotonic() - start, 4)
        result = dict(self.result)
        result.setdefault("result", f"mock worker completed for {self.task['task_id']}")
        result.setdefault("goal_excerpt", _safe_text(self.task.get("goal", ""), 200))
        if stopped:
            result["stopped"] = True
        outcome = self.outcome if not stopped else VERDICT_OUTCOME_UNKNOWN
        return {
            "schema": MOCK_RESULT_SCHEMA,
            "ok": (self.exit_code == 0 and not stopped),
            "exit_code": self.exit_code,
            "timed_out": False,
            "outcome": outcome,
            "result": result,
            "writes": writes,
            "elapsed_sec": elapsed,
            "worker_id": _safe_text(self.task.get("worker_id"), 128),
            "note": self.note or "mock 执行器（测试内模拟并行，零真实 AI 调用）",
            "non_authority": True,
        }


class CliWorkerExecutor:
    """CLI 型 Worker 执行器：经子进程调用 Worker CLI（worker_adapter 协议概念）。

    命令模板（task['cli']['command']，占位符会被替换）：
      {work_dir} / {goal_file} / {task_id}
    缺省模板 = worker_adapter.py run --mode mock（零真实 AI 调用，纯子进程通道）。

    超时/被杀：terminate 子进程 -> 结果 OUTCOME_UNKNOWN（§38，不猜测）。
    心跳：监视线程每 heartbeat_interval 秒更新 task['heartbeat_at']。
    """

    def __init__(self, scheduler: "ParallelScheduler", task: Dict[str, Any],
                 worker_config: Optional[str] = None):
        self.scheduler = scheduler
        self.task = task
        self.worker_config = worker_config
        self.proc: Optional[subprocess.Popen] = None
        self._monitor_stop = threading.Event()
        self._monitor: Optional[threading.Thread] = None
        self.timeout_sec = float((task.get("cli") or {}).get("timeout_sec")
                                 or scheduler.timeout_sec)

    def _command(self) -> List[str]:
        cli = self.task.get("cli") or {}
        cmd = cli.get("command")
        work_dir = str(Path(self.task["work_dir"]))
        goal_file = str(Path(self.task["work_dir"]) / "goal.txt")
        repl = {"{work_dir}": work_dir, "{goal_file}": goal_file,
                "{task_id}": self.task["task_id"]}
        if isinstance(cmd, list) and cmd:
            return [str(c).format_map(repl) for c in cmd]
        # 缺省：worker_adapter.py run --mode mock（零真实 AI 调用）
        adapter = Path(__file__).resolve().parent / "adapters" / "worker_adapter.py"
        if not adapter.exists():
            raise FileNotFoundError(f"worker_adapter.py not found: {adapter}")
        base = [sys.executable, str(adapter), "run",
                "--goal-file", goal_file, "--mode", "mock",
                "--mock-result", json.dumps({"result": "cli worker completed",
                                             "task_id": self.task["task_id"]},
                                            ensure_ascii=False)]
        if self.worker_config:
            base += ["--config", self.worker_config]
        return base

    def _write_goal_file(self) -> Path:
        work_dir = Path(self.task["work_dir"])
        work_dir.mkdir(parents=True, exist_ok=True)
        goal_file = work_dir / "goal.txt"
        goal_file.write_text(_safe_text(self.task.get("goal", ""), 4000), encoding="utf-8")
        return goal_file

    def _monitor_loop(self, proc: subprocess.Popen) -> None:
        stop = self.task.get("_stop_event")
        while not self._monitor_stop.is_set():
            # GATE-2#7: reap_stale() sets _stop_event; the monitor is the only
            # component positioned to actually terminate a stale CLI child.
            # Previously nothing consumed _stop_event for CLI workers, so a
            # heartbeat-dead worker kept running while reap_stale had already
            # released its resource locks to other tasks (§57 breached).
            if stop is not None and stop.is_set():
                self._terminate()
                break
            if proc.poll() is not None:
                break
            self.scheduler._touch_heartbeat(self.task)
            time.sleep(DEFAULT_HEARTBEAT_INTERVAL)
        self.scheduler._touch_heartbeat(self.task)

    def run(self) -> Dict[str, Any]:
        work_dir = Path(self.task["work_dir"])
        work_dir.mkdir(parents=True, exist_ok=True)
        self._write_goal_file()
        cmd = self._command()
        start = time.monotonic()
        timed_out = False
        killed = False
        stdout = ""
        stderr = ""
        exit_code: Optional[int] = None
        try:
            self.proc = subprocess.Popen(
                cmd, cwd=str(work_dir), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
            )
            self._monitor = threading.Thread(target=self._monitor_loop,
                                             args=(self.proc,), daemon=True)
            self._monitor.start()
            try:
                stdout, stderr = self.proc.communicate(timeout=self.timeout_sec)
                exit_code = int(self.proc.returncode)
            except subprocess.TimeoutExpired:
                timed_out = True
                self._terminate()
                stdout, stderr = self.proc.communicate(timeout=5)
                exit_code = int(self.proc.returncode) if self.proc.returncode is not None else None
        except OSError as exc:
            stderr = f"spawn failed: {exc}"
            exit_code = None
        finally:
            self._monitor_stop.set()
            if self._monitor is not None:
                self._monitor.join(timeout=1)
        self.scheduler._touch_heartbeat(self.task)

        # 解析 stdout JSON（worker_adapter 协议）
        result: Any = None
        if stdout.strip():
            try:
                result = json.loads(stdout)
            except json.JSONDecodeError:
                result = {"text": _safe_text(stdout, 4000)}
        if exit_code is None or (timed_out and not stdout.strip()):
            # §38：子进程被杀 / 超时无明确结果 -> 不猜测
            return {
                "schema": SCHEMA, "ok": False, "exit_code": exit_code,
                "timed_out": timed_out, "outcome": VERDICT_OUTCOME_UNKNOWN,
                "result": result,
                "stdout_tail": _safe_text(stdout, 2000),
                "stderr_tail": _safe_text(stderr, 2000),
                "elapsed_sec": round(time.monotonic() - start, 4),
                "worker_id": _safe_text(self.task.get("worker_id"), 128),
                "command": cmd,
                "note": "CLI 执行器：子进程被杀/超时无明确结果 -> OUTCOME_UNKNOWN（不猜测）。",
                "non_authority": True,
            }
        outcome = VERDICT_SUCCESS if exit_code == 0 else VERDICT_FAILURE
        return {
            "schema": SCHEMA, "ok": exit_code == 0, "exit_code": exit_code,
            "timed_out": timed_out, "outcome": outcome,
            "result": result,
            "stdout_tail": _safe_text(stdout, 2000),
            "stderr_tail": _safe_text(stderr, 2000),
            "elapsed_sec": round(time.monotonic() - start, 4),
            "worker_id": _safe_text(self.task.get("worker_id"), 128),
            "command": cmd,
            "note": "CLI 型协议：stdin 传 goal / stdout 收结果 / stderr 收日志。",
            "non_authority": True,
        }

    def _terminate(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        try:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=2)
        except OSError:
            pass


class RelaySubmitExecutor:
    """GATE-6 转真（批次 C）：relay_autopilot 主链真执行器。

    经子进程调用 scripts/relay_autopilot.py submit，把任务送入真实主链：
    admission 三闸（cost/context/lease，require_gates 按模式）+ 显式输入
    契约（repo/packet/evidence 存在性）+ candidate_commit Git 对象校验。
    任务配置 task['relay']：
      mode            "mock"（零真实额度，走同一主链与闸门）| "relay"
      repo_path       仓库根（relay 必填且必须存在）
      review_packet   审查包路径（relay 必填且必须存在）
      evidence_paths  证据路径列表（relay 必填，至少一项且全部存在）
      candidate_commit 40-hex（relay 必须为 repo 内真实 Git 提交对象）
      timeout_sec     超时（缺省 scheduler.timeout_sec）

    红线：mode="relay" 需环境变量 APC_RELAY_REAL=1（真实额度属 L3 业主；
    主链内 §61 cost 门仍会独立拦截）；未设即拒派（fail-closed），mock 不受限。
    退出码映射：0 -> SUCCESS；非零 -> FAILURE（闸门/契约拒绝）；超时/被杀 ->
    OUTCOME_UNKNOWN（§38 不猜测）。
    """

    def __init__(self, scheduler: "ParallelScheduler", task: Dict[str, Any]):
        self.scheduler = scheduler
        self.task = task
        self.proc: Optional[subprocess.Popen] = None
        self._monitor_stop = threading.Event()
        self._monitor: Optional[threading.Thread] = None
        self.timeout_sec = float((task.get("relay") or {}).get("timeout_sec")
                                 or scheduler.timeout_sec)

    def _command(self) -> List[str]:
        relay = self.task.get("relay") or {}
        mode = _safe_text(relay.get("mode"), 16) or "mock"
        if mode not in ("mock", "relay"):
            raise RuntimeError(f"RELAY_MODE_INVALID: {mode}")
        if mode == "relay" and os.environ.get("APC_RELAY_REAL") != "1":
            raise RuntimeError(
                "RELAY_REAL_NOT_ARMED: mode=relay 需 APC_RELAY_REAL=1（真实额度属 L3 业主）")
        script = Path(__file__).resolve().parent.parent / "scripts" / "relay_autopilot.py"
        if not script.exists():
            raise FileNotFoundError(f"relay_autopilot.py not found: {script}")
        work_dir = Path(self.task["work_dir"])
        goal_file = work_dir / "goal.txt"
        cmd = [sys.executable, "-B", str(script), "submit",
               "--goal-file", str(goal_file), "--mode", mode]
        if relay.get("repo_path"):
            cmd += ["--repo-path", str(relay["repo_path"])]
        if relay.get("review_packet"):
            cmd += ["--review-packet", str(relay["review_packet"])]
        for p in (relay.get("evidence_paths") or []):
            cmd += ["--evidence-path", str(p)]
        if relay.get("candidate_commit"):
            cmd += ["--candidate-commit", str(relay["candidate_commit"])]
        return cmd

    def _write_goal_file(self) -> Path:
        # relay_autopilot 主链的 goal 契约是 JSON（goal_id/title/objective），
        # 与 CLI 执行器的纯文本 goal 不同——此处写结构化 goal。
        work_dir = Path(self.task["work_dir"])
        work_dir.mkdir(parents=True, exist_ok=True)
        goal_file = work_dir / "goal.txt"
        goal_text = _safe_text(self.task.get("goal", ""), 4000)
        payload = {
            "goal_id": f"GOAL-{self.task['task_id']}",
            "title": goal_text[:80] or "relay task",
            "objective": goal_text,
        }
        goal_file.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                             encoding="utf-8")
        return goal_file

    def _monitor_loop(self, proc: subprocess.Popen) -> None:
        stop = self.task.get("_stop_event")
        while not self._monitor_stop.is_set():
            if stop is not None and stop.is_set():
                self._terminate()
                break
            if proc.poll() is not None:
                break
            self.scheduler._touch_heartbeat(self.task)
            time.sleep(DEFAULT_HEARTBEAT_INTERVAL)
        self.scheduler._touch_heartbeat(self.task)

    def _terminate(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        try:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=2)
        except OSError:
            pass

    def run(self) -> Dict[str, Any]:
        work_dir = Path(self.task["work_dir"])
        work_dir.mkdir(parents=True, exist_ok=True)
        self._write_goal_file()
        try:
            cmd = self._command()
        except RuntimeError as exc:
            # L3 武装门/模式校验拒绝：fail-closed，不 spawn 子进程。
            return {
                "schema": SCHEMA, "ok": False, "exit_code": None,
                "timed_out": False, "outcome": VERDICT_FAILURE,
                "result": {"error": str(exc)},
                "stdout_tail": "", "stderr_tail": str(exc),
                "elapsed_sec": 0.0,
                "worker_id": _safe_text(self.task.get("worker_id"), 128),
                "command": None,
                "note": "Relay 执行器：L3 武装门/模式校验拒绝（未 spawn 子进程）。",
                "non_authority": True,
            }
        start = time.monotonic()
        timed_out = False
        stdout = ""
        stderr = ""
        exit_code: Optional[int] = None
        try:
            self.proc = subprocess.Popen(
                cmd, cwd=str(work_dir), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
            )
            self._monitor = threading.Thread(target=self._monitor_loop,
                                             args=(self.proc,), daemon=True)
            self._monitor.start()
            try:
                stdout, stderr = self.proc.communicate(timeout=self.timeout_sec)
                exit_code = int(self.proc.returncode)
            except subprocess.TimeoutExpired:
                timed_out = True
                self._terminate()
                stdout, stderr = self.proc.communicate(timeout=5)
                exit_code = int(self.proc.returncode) if self.proc.returncode is not None else None
        except OSError as exc:
            stderr = f"spawn failed: {exc}"
            exit_code = None
        finally:
            self._monitor_stop.set()
            if self._monitor is not None:
                self._monitor.join(timeout=1)
        self.scheduler._touch_heartbeat(self.task)

        result: Any = None
        if stdout.strip():
            try:
                result = json.loads(stdout)
            except json.JSONDecodeError:
                result = {"text": _safe_text(stdout, 4000)}
        if exit_code is None or (timed_out and not stdout.strip()):
            return {
                "schema": SCHEMA, "ok": False, "exit_code": exit_code,
                "timed_out": timed_out, "outcome": VERDICT_OUTCOME_UNKNOWN,
                "result": result,
                "stdout_tail": _safe_text(stdout, 2000),
                "stderr_tail": _safe_text(stderr, 2000),
                "elapsed_sec": round(time.monotonic() - start, 4),
                "worker_id": _safe_text(self.task.get("worker_id"), 128),
                "command": cmd,
                "note": "Relay 执行器：子进程被杀/超时无明确结果 -> OUTCOME_UNKNOWN（§38 不猜测）。",
                "non_authority": True,
            }
        outcome = VERDICT_SUCCESS if exit_code == 0 else VERDICT_FAILURE
        return {
            "schema": SCHEMA, "ok": exit_code == 0, "exit_code": exit_code,
            "timed_out": timed_out, "outcome": outcome,
            "result": result,
            "stdout_tail": _safe_text(stdout, 2000),
            "stderr_tail": _safe_text(stderr, 2000),
            "elapsed_sec": round(time.monotonic() - start, 4),
            "worker_id": _safe_text(self.task.get("worker_id"), 128),
            "command": cmd,
            "note": "GATE-6 转真：relay_autopilot 主链（admission 三闸+显式输入契约+"
                    "candidate_commit 存在性校验）；mock 模式零真实额度，relay 模式需 APC_RELAY_REAL=1。",
            "non_authority": True,
        }


# ---------------------------------------------------------------------------
# 并行调度器（§56/§57/§58/§16/§23/§41/§40/§30/§38）
# ---------------------------------------------------------------------------
class ParallelScheduler:
    """多 Worker 并行调度核心。

    职责：
      - 任务队列 -> 并发分派（max_concurrent 可配）；
      - 资源锁冲突排队（LOCK_WAITING）不失败；
      - 每任务独立工作目录 + 越界写校验（sandbox）；
      - WAIT 局部性：等待任务不阻塞其余 READY 任务；
      - STOP/REVOKE directive 失效旧权，旧结果拒绝接受；
      - epoch 单调性：回滚/复活的低 epoch 结果拒绝；
      - 心跳超时 -> STALE 回收并释放资源；
      - 结果不明 -> OUTCOME_UNKNOWN（不猜测）。
    """

    def __init__(self, state_root: Optional[str] = None,
                 max_concurrent: int = DEFAULT_MAX_CONCURRENT,
                 timeout_sec: float = DEFAULT_TIMEOUT_SEC,
                 stale_after_sec: float = DEFAULT_STALE_AFTER_SEC,
                 lock_ttl_sec: float = DEFAULT_LOCK_TTL_SEC,
                 mode: str = "mock",
                 worker_config: Optional[str] = None,
                 sleep_interval: float = DEFAULT_SLEEP_INTERVAL,
                 max_rounds: int = DEFAULT_MAX_ROUNDS,
                 now_fn: Optional[Any] = None) -> None:
        self.state_root = Path(state_root) if state_root else _default_state_root()
        self.tasks_root = self.state_root / "tasks"
        self.locks_root = self.state_root / "locks"
        self.scheduler_lock_dir = self.state_root / "scheduler.lock"
        self.max_concurrent = max(1, int(max_concurrent))
        self.timeout_sec = float(timeout_sec)
        self.stale_after_sec = float(stale_after_sec)
        self.lock_ttl_sec = float(lock_ttl_sec)
        self.mode = mode if mode in ("mock", "cli") else "mock"
        self.worker_config = worker_config
        self.sleep_interval = float(sleep_interval)
        self.max_rounds = max(1, int(max_rounds))
        self._now_fn = now_fn

        self._guard = threading.RLock()
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.epochs: Dict[str, int] = {}
        self.locks = ResourceLockManager(str(self.locks_root), ttl_sec=self.lock_ttl_sec)
        self._active: Dict[str, threading.Thread] = {}
        self._executors: Dict[str, Any] = {}
        self._directives: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []   # (at, task_id, state) 观测
        self.instance_lock = SingleInstanceLock(str(self.scheduler_lock_dir),
                                                ttl_sec=self.lock_ttl_sec)

    # -- 时间 -------------------------------------------------------------
    def _now(self) -> str:
        if self._now_fn is not None:
            return self._now_fn()
        return _now_iso()

    def _now_float(self) -> float:
        if self._now_fn is not None:
            try:
                return float(self._now_fn())
            except (TypeError, ValueError):
                return _now_epoch()
        return _now_epoch()

    # -- 心跳 -------------------------------------------------------------
    def _touch_heartbeat(self, task: Dict[str, Any]) -> None:
        with self._guard:
            task["heartbeat_at"] = self._now()

    # -- epoch 单调（§40） ------------------------------------------------
    def next_epoch(self, task_id: str) -> int:
        with self._guard:
            cur = int(self.epochs.get(task_id, 0))
            nxt = cur + 1
            self.epochs[task_id] = nxt
            return nxt

    def current_epoch(self, task_id: str) -> int:
        with self._guard:
            return int(self.epochs.get(task_id, 0))

    # -- 任务提交 -----------------------------------------------------------
    def submit(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """提交任务。spec 字段：
          task_id, goal, worker_id, resources(list), epoch(可空=自动),
          mock{...} 或 cli{command,timeout_sec} 或 relay{mode,repo_path,
          review_packet,evidence_paths,candidate_commit,timeout_sec}
          （GATE-6：relay_autopilot 主链真执行器；mode=relay 需
          APC_RELAY_REAL=1，真实额度属 L3 业主）, wait_initial(bool)
        返回 TaskRecord。
        """
        with self._guard:
            task_id = ensure_id(spec.get("task_id") or spec.get("id"), "TASK")
            epoch = int(spec.get("epoch") or self.next_epoch(task_id))
            self.epochs[task_id] = max(int(self.epochs.get(task_id, 0)), epoch)
            resources = [str(r) for r in (spec.get("resources") or [])]
            work_dir = self.tasks_root / task_id / f"epoch-{epoch}" / "work"
            task: Dict[str, Any] = {
                "task_id": task_id,
                "goal": _safe_text(spec.get("goal") or spec.get("objective") or "", 4000),
                "worker_id": _safe_text(spec.get("worker_id") or "mock", 128),
                "resources": resources,
                "epoch": epoch,
                "state": TASK_PENDING,
                "work_dir": str(work_dir),
                "created_at": self._now(),
                "started_at": None,
                "finished_at": None,
                "heartbeat_at": None,
                "revoked_epoch": None,
                "revoked_at": None,
                "revoke_reason": "",
                "accepted": False,
                "rejected": [],
                "outcome": None,
                "result": None,
                "decision_entry": None,
                "detail": "",
                "mock": dict(spec.get("mock") or {}),
                "cli": dict(spec.get("cli") or {}),
                # GATE-6（批次 C）：relay 真执行器配置（relay_autopilot 主链，
                # 真实额度属 L3 业主，APC_RELAY_REAL 武装门在执行器内）。
                "relay": dict(spec.get("relay") or {}),
                "_stop_event": threading.Event(),
            }
            if spec.get("wait_initial"):
                task["state"] = TASK_WAITING
            self.tasks[task_id] = task
            self._record_event(task_id, TASK_PENDING)
            self._persist_task(task)
            return dict(task)

    def _record_event(self, task_id: str, state: str, detail: str = "") -> None:
        self.events.append({"at": self._now(), "task_id": task_id,
                            "state": state, "detail": detail})

    def _persist_task(self, task: Dict[str, Any]) -> None:
        try:
            save_json(str(Path(task["work_dir"]).parent / "task.json"),
                      self._public_task(task))
        except OSError:
            pass

    def _public_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """任务记录的可序列化视图（剔除线程内部字段）。"""
        pub = {k: v for k, v in task.items() if not k.startswith("_")}
        return pub

    def load_persisted(self) -> int:
        """从磁盘加载已持久化任务记录（tasks/<id>/epoch-*/task.json）。

        同 task_id 只保留最新 epoch（旧代不覆盖）；供 status/directive 只读衔接。
        """
        n = 0
        if not self.tasks_root.exists():
            return 0
        for task_dir in sorted(self.tasks_root.iterdir()):
            if not task_dir.is_dir():
                continue
            for ep_dir in sorted(task_dir.iterdir()):
                if not ep_dir.is_dir():
                    continue
                data = load_json(str(ep_dir / "task.json"))
                if not isinstance(data, dict) or not data.get("task_id"):
                    continue
                task_id = str(data["task_id"])
                epoch = int(data.get("epoch", 0))
                cur = self.tasks.get(task_id)
                if cur is None or epoch > int(cur.get("epoch", 0)):
                    data["_stop_event"] = threading.Event()
                    self.tasks[task_id] = data
                    self.epochs[task_id] = max(int(self.epochs.get(task_id, 0)), epoch)
                    n += 1
        return n

    # -- directive（§23/§41/§16） -----------------------------------------
    def apply_directive(self, action: str, task_id: str,
                        reason: str = "", by: str = "operator") -> Dict[str, Any]:
        """对任务施加 directive。返回结构化结果。
        STOP   = 失效旧权：task -> REVOKED（revoked_epoch=当前 epoch），
                 后续结果拒绝接受；mock 执行器跑完以便产生可拒绝的"旧结果"，
                 CLI 子进程立即 terminate。
        REVOKE = STOP + 立即 kill 执行单元（mock 提前退出 -> OUTCOME_UNKNOWN）。
        WAIT   = 置 WAITING（§16：等待审查/人工，不阻塞队列其余任务）。
        RESUME = WAITING -> READY（继续可分派）。
        """
        with self._guard:
            task = self.tasks.get(task_id)
            if task is None:
                return {"ok": False, "error": REJECT_TASK_NOT_FOUND,
                        "detail": f"task not found: {task_id}"}
            if action not in VALID_ACTIONS:
                return {"ok": False, "error": "INVALID_ACTION",
                        "detail": f"action must be one of {sorted(VALID_ACTIONS)}"}
            if action in (ACTION_STOP, ACTION_REVOKE):
                if task["state"] in STATE_TERMINAL:
                    return {"ok": False, "error": "TASK_ALREADY_TERMINAL",
                            "detail": f"task {task_id} already {task['state']}"}
                task["state"] = TASK_REVOKED
                task["revoked_epoch"] = int(task["epoch"])
                task["revoked_at"] = self._now()
                task["revoke_reason"] = _safe_text(reason, 400)
                task["detail"] = f"directive {action} by {by}"
                self._record_event(task_id, TASK_REVOKED, f"{action} {reason}")
                if action == ACTION_REVOKE:
                    task["_stop_event"].set()  # 立即 kill（mock 提前退出）
                # STOP：不 set stop_event —— mock 跑完产生可拒绝的旧结果；
                # CLI 由执行器 terminate（见 _terminate_running_cli）。
                self._terminate_running_cli(task)
                self._persist_task(task)
                return {"ok": True, "action": action, "task_id": task_id,
                        "state": TASK_REVOKED, "revoked_epoch": int(task["epoch"]),
                        "revoke_reason": task["revoke_reason"], "non_authority": True}
            if action == ACTION_WAIT:
                if task["state"] not in (TASK_PENDING, TASK_READY, TASK_LOCK_WAITING,
                                         TASK_RUNNING, TASK_WAITING):
                    return {"ok": False, "error": "TASK_NOT_WAITABLE",
                            "detail": f"task {task_id} state={task['state']}"}
                task["state"] = TASK_WAITING
                task["detail"] = f"directive {action} by {by} ({reason})"
                self._record_event(task_id, TASK_WAITING, reason)
                self._persist_task(task)
                return {"ok": True, "action": action, "task_id": task_id,
                        "state": TASK_WAITING, "non_authority": True}
            if action == ACTION_RESUME:
                if task["state"] != TASK_WAITING:
                    return {"ok": False, "error": "TASK_NOT_WAITING",
                            "detail": f"task {task_id} state={task['state']}"}
                task["state"] = TASK_READY
                task["detail"] = f"directive {action} by {by} ({reason})"
                self._record_event(task_id, TASK_READY, reason)
                self._persist_task(task)
                return {"ok": True, "action": action, "task_id": task_id,
                        "state": TASK_READY, "non_authority": True}
            return {"ok": False, "error": "UNREACHABLE", "detail": action}

    def _terminate_running_cli(self, task: Dict[str, Any]) -> None:
        """CLI 执行器 terminate（STOP/REVOKE 时立即杀子进程）。"""
        # 执行器线程持有 self._executors[task_id]；terminate 由线程自身在
        # 完成后释放；此处仅触发 proc terminate（见 CliWorkerExecutor）。
        ex = self._executors.get(task["task_id"])
        if ex is not None and isinstance(ex, CliWorkerExecutor):
            try:
                ex._terminate()
            except Exception:  # noqa: BLE001
                pass

    def add_directive(self, when: str, task_id: str, action: str,
                      reason: str = "", delay_sec: float = 0.0) -> Dict[str, Any]:
        """注册一个调度内 directive（run 循环按 when 触发）。
        when: after_start（任务启动 delay_sec 秒后触发）。
        """
        if action not in VALID_ACTIONS:
            return {"ok": False, "error": "INVALID_ACTION",
                    "detail": f"action must be one of {sorted(VALID_ACTIONS)}"}
        self._directives.append({
            "when": when, "task_id": ensure_id(task_id, "TASK"),
            "action": action, "reason": _safe_text(reason, 400),
            "delay_sec": float(delay_sec), "applied": False,
        })
        return {"ok": True, "registered": True, "when": when,
                "task_id": task_id, "action": action}

    def _apply_pending_directives(self) -> int:
        changed = 0
        for d in self._directives:
            if d.get("applied"):
                continue
            task = self.tasks.get(d["task_id"])
            if task is None:
                continue
            if d["when"] == "after_start":
                if task.get("started_at") is None:
                    continue
                started = task["started_at"]
                if self._age_iso(started) is not None and \
                        self._age_iso(started) < d.get("delay_sec", 0.0):
                    continue
            d["applied"] = True
            res = self.apply_directive(d["action"], d["task_id"], reason=d.get("reason", ""))
            if res.get("ok"):
                changed += 1
        return changed

    def _age_iso(self, at_iso: str) -> Optional[float]:
        return _age_seconds(at_iso, self._now_float())

    # -- 分派（§56/§57/§16） ----------------------------------------------
    def _resource_busy(self, task: Dict[str, Any]) -> Optional[str]:
        for r in task.get("resources") or []:
            holder = self.locks.held_by(r)
            if holder is not None and holder != task["task_id"]:
                return r
        return None

    def _acquire_resources(self, task: Dict[str, Any]) -> bool:
        """GATE-2#7: all-or-nothing resource acquisition.

        Previously a failed second lock left the task HOLDING the first one
        while LOCK_WAITING; two tasks requesting the same two resources in
        opposite order could then deadlock (each holds one, each waits for
        the other, and nothing rolls back). Partial failure now releases
        everything taken before returning False.
        """
        taken = []
        for r in task.get("resources") or []:
            if self.locks.acquire(r, task["task_id"]):
                taken.append(r)
                continue
            for r2 in taken:
                try:
                    self.locks.release(r2, task["task_id"])
                except ValueError:
                    pass
            return False
        return True

    def _release_resources(self, task: Dict[str, Any]) -> None:
        for r in task.get("resources") or []:
            try:
                self.locks.release(r, task["task_id"])
            except ValueError:
                pass

    def _promote_pending(self) -> int:
        """PENDING -> READY（入队任务变为可分派）。"""
        changed = 0
        with self._guard:
            for task in self.tasks.values():
                if task["state"] == TASK_PENDING:
                    task["state"] = TASK_READY
                    self._record_event(task["task_id"], TASK_READY)
                    changed += 1
        return changed

    def _dispatch_ready(self) -> int:
        """把一个 READY/LOCK_WAITING 任务分派为 RUNNING（若并发与资源允许）。"""
        changed = 0
        with self._guard:
            running = sum(1 for t in self.tasks.values()
                          if t["state"] == TASK_RUNNING and t["task_id"] in self._active)
            for task in list(self.tasks.values()):
                if task["state"] not in (TASK_READY, TASK_LOCK_WAITING):
                    continue
                if running >= self.max_concurrent:
                    break
                busy = self._resource_busy(task)
                if busy is not None:
                    if task["state"] != TASK_LOCK_WAITING:
                        task["state"] = TASK_LOCK_WAITING
                        task["detail"] = f"resource lock busy: {busy}"
                        self._record_event(task["task_id"], TASK_LOCK_WAITING, busy)
                        self._persist_task(task)
                        changed += 1
                    continue
                if not self._acquire_resources(task):
                    if task["state"] != TASK_LOCK_WAITING:
                        task["state"] = TASK_LOCK_WAITING
                        task["detail"] = "resource lock acquire failed"
                        self._record_event(task["task_id"], TASK_LOCK_WAITING, "acquire-failed")
                        self._persist_task(task)
                        changed += 1
                    continue
                task["state"] = TASK_RUNNING
                task["started_at"] = self._now()
                task["heartbeat_at"] = self._now()
                task["_stop_event"] = threading.Event()
                task["detail"] = f"dispatched (worker={task['worker_id']})"
                self._record_event(task["task_id"], TASK_RUNNING, task["worker_id"])
                self._persist_task(task)
                t = threading.Thread(target=self._execute, args=(task,), daemon=True)
                self._active[task["task_id"]] = t
                t.start()
                running += 1
                changed += 1
        return changed

    def _make_executor(self, task: Dict[str, Any]):
        if task.get("relay"):
            return RelaySubmitExecutor(self, task)
        if self.mode == "cli" or task.get("cli"):
            return CliWorkerExecutor(self, task, self.worker_config)
        return MockWorkerExecutor(self, task)

    def _execute(self, task: Dict[str, Any]) -> None:
        """执行单元线程体：跑执行器 -> 收结果 -> 接受/拒绝 -> 释放资源。"""
        try:
            executor = self._make_executor(task)
            with self._guard:
                self._executors[task["task_id"]] = executor
            result = executor.run()
            result["epoch"] = int(task["epoch"])
            result["task_id"] = task["task_id"]
            with self._guard:
                self._accept_result(task, result)
        except Exception as exc:  # noqa: BLE001
            with self._guard:
                # 执行器异常：结果不明（§38）-> OUTCOME_UNKNOWN，不猜测成败
                self._accept_result(task, {
                    "schema": SCHEMA, "ok": False,
                    "outcome": VERDICT_OUTCOME_UNKNOWN,
                    "result": {"error": _safe_text(str(exc), 400)},
                    "exit_code": None, "timed_out": False,
                    "note": f"executor raised: {exc}",
                })
        finally:
            with self._guard:
                self._release_resources(task)
                self._executors.pop(task["task_id"], None)
                self._active.pop(task["task_id"], None)
                task["finished_at"] = self._now()
                task["_done"] = True
                self._persist_task(task)

    # -- 结果接受/拒绝（§23/§41/§40/§30/§58/§38） ---------------------------
    def _accept_result(self, task: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """核心裁决：接受或拒绝执行结果。返回结构化记录。"""
        rec = self._adjudicate(task, result)
        if rec["verdict"] == ACCEPT_OK:
            outcome = str(result.get("outcome") or VERDICT_SUCCESS)
            if outcome == VERDICT_OUTCOME_UNKNOWN:
                # §38：结果不明，不自动判定成败；提供人工/重试决策入口
                task["state"] = TASK_OUTCOME_UNKNOWN
                task["outcome"] = VERDICT_OUTCOME_UNKNOWN
                task["decision_entry"] = "MANUAL_OR_RETRY"
                task["detail"] = "结果不明（§38）：不自动判定成败，人工/重试决策。"
                task["accepted"] = False
            elif outcome == VERDICT_FAILURE:
                task["state"] = TASK_FAILED
                task["outcome"] = VERDICT_FAILURE
                task["decision_entry"] = None
                task["detail"] = "worker 明确失败（exit_code 非零且结果明确）。"
                task["accepted"] = True
            else:
                task["state"] = TASK_COMPLETED
                task["outcome"] = VERDICT_SUCCESS
                task["decision_entry"] = None
                task["detail"] = "worker 成功，结果被接受。"
                task["accepted"] = True
            task["result"] = result
            task["finished_at"] = self._now()
            self._record_event(task["task_id"], task["state"])
        else:
            self._reject_result(task, result, rec["reason"], rec["detail"])
            # 拒绝 -> 落终态（若尚未终态），避免任务卡在 RUNNING
            if task["state"] not in STATE_TERMINAL:
                if rec["reason"] == REJECT_SANDBOX:
                    task["state"] = TASK_SANDBOX_VIOLATION
                elif rec["reason"] == REJECT_STALE_EPOCH:
                    task["state"] = TASK_ABORTED
                elif rec["reason"] == REJECT_REVOKED_EPOCH:
                    task["state"] = TASK_REVOKED
                elif rec["reason"] == REJECT_STALE_HEARTBEAT:
                    task["state"] = TASK_STALE
                else:
                    task["state"] = TASK_ABORTED
                self._record_event(task["task_id"], task["state"],
                                   f"rejected:{rec['reason']}")
        self._persist_task(task)
        return rec

    def _adjudicate(self, task: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """裁决规则（顺序即优先级）：
          1) 结果 epoch != 任务当前 epoch        -> STALE_EPOCH（§40 单调性/回滚复活）
          2) 结果 epoch <= revoked_epoch         -> REVOKED_EPOCH（§41 失效权）
          3) 任务已被 stale 回收                 -> STALE_HEARTBEAT（§30）
          4) 任务已失效/终态（REVOKED/COMPLETED/…）-> TASK_NOT_ACTIVE（旧结果拒绝）
          5) sandbox 越界写                      -> SANDBOX_VIOLATION（§58）
          否则接受。
        """
        res_epoch = result.get("epoch")
        try:
            res_epoch_int = int(res_epoch) if res_epoch is not None else None
        except (TypeError, ValueError):
            res_epoch_int = None
        if res_epoch_int is None or res_epoch_int != int(task["epoch"]):
            return {"verdict": REJECT_STALE_EPOCH, "reason": REJECT_STALE_EPOCH,
                    "detail": (f"结果 epoch={res_epoch} != 任务 epoch={task['epoch']} "
                               "（§40 epoch 单调性）：旧/错代结果拒绝。")}
        revoked = task.get("revoked_epoch")
        if revoked is not None and res_epoch_int <= int(revoked):
            return {"verdict": REJECT_REVOKED_EPOCH, "reason": REJECT_REVOKED_EPOCH,
                    "detail": (f"结果 epoch={res_epoch_int} <= revoked_epoch={revoked} "
                               "（§41 失效权/§40 回滚复活）：被撤销代的结果拒绝。")}
        if task["state"] == TASK_STALE:
            return {"verdict": REJECT_STALE_HEARTBEAT, "reason": REJECT_STALE_HEARTBEAT,
                    "detail": (f"任务已被 stale 回收（§30 心跳超时）："
                               f"结果 epoch={res_epoch_int} 拒绝接受。")}
        if task["state"] in (TASK_REVOKED, TASK_ABORTED, TASK_SANDBOX_VIOLATION,
                             TASK_OUTCOME_UNKNOWN, TASK_COMPLETED, TASK_FAILED):
            return {"verdict": REJECT_NOT_ACTIVE, "reason": REJECT_NOT_ACTIVE,
                    "detail": f"task 已失效/终态（state={task['state']}）：旧结果拒绝接受。"}
        violation = self._check_sandbox(task, result)
        if violation is not None:
            return {"verdict": REJECT_SANDBOX, "reason": REJECT_SANDBOX,
                    "detail": f"越界写（§58 项目隔离）：{violation}"}
        return {"verdict": ACCEPT_OK, "reason": ACCEPT_OK,
                "detail": "结果有效，接受。"}

    def _reject_result(self, task: Dict[str, Any], result: Dict[str, Any],
                       reason: str, detail: str) -> Dict[str, Any]:
        rec = {
            "rejected_at": self._now(),
            "reason": reason,
            "detail": _safe_text(detail, 800),
            "epoch": result.get("epoch"),
            "result_summary": _safe_text(
                json.dumps(result.get("result") or {}, ensure_ascii=False), 400),
            "result": result,   # 完整旧结果留存（证据：结果确实产生但被拒）
        }
        task["rejected"] = list(task.get("rejected") or []) + [rec]
        task["accepted"] = False
        task["finished_at"] = self._now()
        self._record_event(task["task_id"], task["state"], f"rejected:{reason}")
        self._persist_task(task)
        return rec

    def accept_external_result(self, task_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """外部迟到结果入口（L3：straggler 进程晚到报告）。
        复用同一裁决规则：epoch/revoke/stale/sandbox 全查。
        """
        with self._guard:
            task = self.tasks.get(task_id)
            if task is None:
                return {"ok": False, "error": REJECT_TASK_NOT_FOUND,
                        "detail": f"task not found: {task_id}"}
            result = dict(result or {})
            # GATE-2#7: a straggler result WITHOUT an epoch was previously
            # bound to the CURRENT epoch via setdefault — validating a result
            # that may predate a revoke/rollback (§40 STALE_EPOCH bypass).
            # External results must carry their own epoch.
            if "epoch" not in result:
                return {"ok": False, "error": "STALE_EPOCH",
                        "detail": ("external result must carry its own epoch "
                                   "(§40); binding to current epoch would "
                                   "validate a possibly-revoked result")}
            result.setdefault("task_id", task_id)
            return self._accept_result(task, result)

    # -- sandbox 校验（§58） ----------------------------------------------
    def _check_sandbox(self, task: Dict[str, Any], result: Dict[str, Any]) -> Optional[str]:
        work_dir = Path(task["work_dir"])
        if not work_dir.exists():
            return None
        # 1) 执行器报告的写入路径必须都在 work_dir 内
        for w in result.get("writes") or []:
            if str(w).startswith("<"):
                return f"写入异常记录: {w}"
            if not _path_within(work_dir, Path(str(w))):
                return f"worker 报告越界写: {w} (work_dir={work_dir})"
        # 2) symlink 逃逸扫描（work_dir 内任何 symlink 目标必须在 work_dir 内）
        try:
            for p in work_dir.rglob("*"):
                if p.is_symlink():
                    target = p.resolve()
                    if not _path_within(work_dir, target):
                        return f"symlink 逃逸: {p} -> {target}"
        except OSError:
            pass
        return None

    # -- stale 回收（§30） -------------------------------------------------
    def reap_stale(self) -> int:
        """心跳超时的 RUNNING 任务 -> STALE -> kill 执行单元 -> 释放资源。"""
        changed = 0
        with self._guard:
            now = self._now_float()
            for task in list(self.tasks.values()):
                if task["state"] != TASK_RUNNING:
                    continue
                hb = task.get("heartbeat_at")
                age = _age_seconds(hb, now) if hb else None
                if age is not None and age > self.stale_after_sec:
                    task["state"] = TASK_STALE
                    task["detail"] = (f"心跳超时 {age:.2f}s > stale_after "
                                      f"{self.stale_after_sec:.2f}s（§30）")
                    task["_stop_event"].set()
                    self._record_event(task["task_id"], TASK_STALE, f"age={age:.2f}")
                    # GATE-2#7: heartbeat death usually means the worker's own
                    # monitor thread is dead/stuck too — setting _stop_event
                    # alone had NO consumer for CLI workers, so the orphaned
                    # child kept running while its locks were handed to other
                    # tasks (§57 breached). Terminate the child here directly;
                    # _stop_event stays set for executor types that poll it.
                    ex = self._executors.get(task["task_id"])
                    if ex is not None and hasattr(ex, "_terminate"):
                        try:
                            ex._terminate()
                        except Exception:  # noqa: BLE001 — already dead/racing
                            pass
                    self._release_resources(task)
                    self._persist_task(task)
                    changed += 1
        return changed

    # -- 收集完成 -----------------------------------------------------------
    def _collect_finished(self) -> int:
        changed = 0
        with self._guard:
            for task in list(self.tasks.values()):
                if task.get("_done"):
                    if task["task_id"] not in self._active:
                        continue
                    self._active.pop(task["task_id"], None)
                    changed += 1
        return changed

    # -- 主循环 -------------------------------------------------------------
    def run_once(self) -> int:
        """推进一轮调度。返回状态变化次数。"""
        changed = 0
        changed += self._apply_pending_directives()
        changed += self.reap_stale()
        changed += self._promote_pending()
        changed += self._dispatch_ready()
        changed += self._collect_finished()
        return changed

    def run_until_idle(self, interval: Optional[float] = None,
                       max_rounds: Optional[int] = None) -> Dict[str, Any]:
        """轮询直至收敛（无进行中任务且无状态变化）。返回 summary。"""
        interval = self.sleep_interval if interval is None else float(interval)
        rounds = self.max_rounds if max_rounds is None else max(1, int(max_rounds))
        n = 0
        while n < rounds:
            n += 1
            changed = self.run_once()
            with self._guard:
                active = len(self._active)
            if changed == 0 and active == 0:
                break
            time.sleep(interval)
        return self.summary()

    # -- 状态/摘要 -----------------------------------------------------------
    def status(self) -> Dict[str, Any]:
        with self._guard:
            tasks = [self._public_task(t) for t in self.tasks.values()]
        return {
            "schema": SCHEMA, "command": "status", "ok": True,
            "state_root": str(self.state_root),
            "max_concurrent": self.max_concurrent,
            "mode": self.mode,
            "total_tasks": len(tasks),
            "tasks": tasks,
            "non_authority": True,
        }

    def summary(self) -> Dict[str, Any]:
        with self._guard:
            tasks = [self._public_task(t) for t in self.tasks.values()]
            states: Dict[str, int] = {}
            accepted = 0
            rejected = 0
            outcome_unknown = []
            revocations = []
            for t in tasks:
                states[t["state"]] = states.get(t["state"], 0) + 1
                if t.get("accepted"):
                    accepted += 1
                rejected += len(t.get("rejected") or [])
                if t["state"] == TASK_OUTCOME_UNKNOWN:
                    outcome_unknown.append({"task_id": t["task_id"],
                                            "epoch": t["epoch"],
                                            "decision_entry": t.get("decision_entry")})
                if t.get("revoked_epoch") is not None:
                    revocations.append({"task_id": t["task_id"],
                                        "revoked_epoch": t["revoked_epoch"],
                                        "revoke_reason": t.get("revoke_reason"),
                                        "rejected_count": len(t.get("rejected") or [])})
        ok = accepted == len(tasks) and len(tasks) > 0 and rejected == 0
        return {
            "schema": SCHEMA, "command": "run", "ok": ok,
            "state_root": str(self.state_root),
            "max_concurrent": self.max_concurrent,
            "mode": self.mode,
            "total_tasks": len(tasks),
            "states": states,
            "accepted": accepted,
            "rejected": rejected,
            "outcome_unknown": outcome_unknown,
            "revocations": revocations,
            "tasks": tasks,
            "rounds_hint": None,
            "non_authority": True,
            "note": "并行调度结果（inert 数据）：真实多 Worker 生产并行 = 业主 L3。",
        }

    def save_last_run(self) -> None:
        try:
            save_json(str(self.state_root / "last-run.json"), self.summary())
        except OSError:
            pass


# ---------------------------------------------------------------------------
# CLI 输入校验
# ---------------------------------------------------------------------------
def _load_tasks_file(path: str) -> Dict[str, Any]:
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"tasks 文件非法 JSON 或非对象: {path}")
    if data.get("schema") != TASKS_SCHEMA:
        raise ValueError(f"tasks 文件 schema 必须为 {TASKS_SCHEMA}: {path}")
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError(f"tasks 文件必须含非空 tasks 列表: {path}")
    return data


def _load_directives_file(path: str) -> List[Dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"directives 文件非法 JSON: {path}")
    if data.get("schema") != DIRECTIVES_SCHEMA:
        raise ValueError(f"directives 文件 schema 必须为 {DIRECTIVES_SCHEMA}: {path}")
    directives = data.get("directives")
    if not isinstance(directives, list):
        raise ValueError(f"directives 文件必须含 directives 列表: {path}")
    return directives


def _exit_code_from_summary(summary: Dict[str, Any]) -> int:
    """0=全部接受；2=存在被拒绝旧结果 / OUTCOME_UNKNOWN / 撤销；1 由上层配置错误抛。"""
    if summary.get("rejected", 0) > 0:
        return EXIT_HARD_STOP
    if summary.get("outcome_unknown"):
        return EXIT_HARD_STOP
    if summary.get("revocations"):
        return EXIT_HARD_STOP
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def cmd_run(args: argparse.Namespace) -> int:
    try:
        data = _load_tasks_file(args.tasks_file)
    except ValueError as exc:
        print(json.dumps({"schema": SCHEMA, "command": "run", "ok": False,
                          "error": "CONFIG_ERROR", "detail": _safe_text(str(exc), 600)},
                         ensure_ascii=False, indent=2))
        return EXIT_CONFIG_ERROR

    state_root = args.state_root or str(_default_state_root())
    sched = ParallelScheduler(
        state_root=state_root,
        max_concurrent=args.max_concurrent,
        timeout_sec=args.timeout,
        stale_after_sec=args.stale_after,
        lock_ttl_sec=args.lock_ttl,
        mode=args.mode,
        worker_config=args.worker_config,
    )

    single = SingleInstanceLock(str(sched.scheduler_lock_dir), ttl_sec=sched.lock_ttl_sec)
    if not single.acquire():
        print(json.dumps({"schema": SCHEMA, "command": "run", "ok": False,
                          "error": "SKIP_LOCKED",
                          "detail": "另一个 parallel_scheduler 实例持有调度锁"},
                         ensure_ascii=False, indent=2))
        return EXIT_HARD_STOP
    try:
        for spec in data["tasks"]:
            sched.submit(spec)
        if args.stop_task:
            sched.add_directive("after_start", args.stop_task, ACTION_STOP,
                                reason="CLI --stop-task", delay_sec=0.0)
        if args.directives_file:
            for d in _load_directives_file(args.directives_file):
                sched.add_directive(d.get("when", "after_start"), d.get("task_id"),
                                    d.get("action"), reason=d.get("reason", ""),
                                    delay_sec=float(d.get("delay_sec", 0.0)))
        summary = sched.run_until_idle()
        sched.save_last_run()
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return _exit_code_from_summary(summary)
    except (ValueError, OSError) as exc:
        print(json.dumps({"schema": SCHEMA, "command": "run", "ok": False,
                          "error": "CONFIG_ERROR", "detail": _safe_text(str(exc), 600)},
                         ensure_ascii=False, indent=2))
        return EXIT_CONFIG_ERROR
    finally:
        single.release()


def cmd_status(args: argparse.Namespace) -> int:
    state_root = args.state_root or str(_default_state_root())
    sched = ParallelScheduler(state_root=state_root, mode="mock")
    sched.load_persisted()
    print(json.dumps(sched.status(), ensure_ascii=False, indent=2))
    return EXIT_OK


def cmd_directive(args: argparse.Namespace) -> int:
    state_root = args.state_root or str(_default_state_root())
    sched = ParallelScheduler(state_root=state_root, mode="mock")
    sched.load_persisted()
    res = sched.apply_directive(args.action, args.task_id, reason=args.reason)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return EXIT_OK if res.get("ok") else EXIT_HARD_STOP


def cmd_reset(args: argparse.Namespace) -> int:
    state_root = Path(args.state_root) if args.state_root else _default_state_root()
    for sub in ("tasks", "locks"):
        shutil.rmtree(state_root / sub, ignore_errors=True)
    for f in ("last-run.json",):
        try:
            os.remove(state_root / f)
        except OSError:
            pass
    try:
        os.rmdir(state_root)  # 若已空则整体移除
    except OSError:
        pass
    print(json.dumps({"schema": SCHEMA, "command": "reset", "ok": True,
                      "state_root": str(state_root), "non_authority": True},
                     ensure_ascii=False, indent=2))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="D4 多 Worker 并行调度 + 资源锁 + 项目隔离 + 失效权")
    sub = ap.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="运行调度直至队列收敛")
    p_run.add_argument("--tasks-file", dest="tasks_file", required=True)
    p_run.add_argument("--directives-file", dest="directives_file", default="")
    p_run.add_argument("--stop-task", dest="stop_task", default="",
                       help="任务启动后立即 STOP（失效旧权端到端演示）")
    p_run.add_argument("--max-concurrent", dest="max_concurrent", type=int,
                       default=DEFAULT_MAX_CONCURRENT)
    p_run.add_argument("--mode", dest="mode", default="mock", choices=("mock", "cli"))
    p_run.add_argument("--state-root", dest="state_root", default="")
    p_run.add_argument("--timeout", dest="timeout", type=float, default=DEFAULT_TIMEOUT_SEC)
    p_run.add_argument("--stale-after", dest="stale_after", type=float,
                       default=DEFAULT_STALE_AFTER_SEC)
    p_run.add_argument("--lock-ttl", dest="lock_ttl", type=float,
                       default=DEFAULT_LOCK_TTL_SEC)
    p_run.add_argument("--worker-config", dest="worker_config", default="")

    p_status = sub.add_parser("status", help="调度状态视图（只读）")
    p_status.add_argument("--state-root", dest="state_root", default="")

    p_directive = sub.add_parser("directive", help="对运行中的调度施加 directive")
    p_directive.add_argument("--task-id", dest="task_id", required=True)
    p_directive.add_argument("--action", dest="action", required=True,
                             choices=sorted(VALID_ACTIONS))
    p_directive.add_argument("--reason", dest="reason", default="")
    p_directive.add_argument("--state-root", dest="state_root", default="")

    p_reset = sub.add_parser("reset", help="清空调度状态（只动 state-root）")
    p_reset.add_argument("--state-root", dest="state_root", default="")
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        if args.command == "run":
            return cmd_run(args)
        if args.command == "status":
            return cmd_status(args)
        if args.command == "directive":
            return cmd_directive(args)
        if args.command == "reset":
            return cmd_reset(args)
        ap.print_help()
        return EXIT_CONFIG_ERROR
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"schema": SCHEMA, "command": args.command, "ok": False,
                          "error": "UNEXPECTED", "detail": _safe_text(str(exc), 600)},
                         ensure_ascii=False, indent=2))
        return EXIT_CONFIG_ERROR


if __name__ == "__main__":
    sys.exit(main())
