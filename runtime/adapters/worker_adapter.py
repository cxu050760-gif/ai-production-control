"""Worker-Adapter — CLI 型弱模型 Worker 适配层（宪法 §5 / §63，v1.1-blackbox D1）。

背景：当前 Worker 只适配 TRAE（Trae CDP）。宪法 §5 要求 AI 是资源可替换。
本模块把「CLI 型弱模型 Worker」泛化为统一协议（stdin 传 goal / stdout 收结果 /
stderr 收日志 / 统一退出码），并内置 mock 执行器供 L2 测试（不消耗真实 worker）。

CLI 型协议：
    python worker_adapter.py run --config <F> --goal-file <F> \
            [--mode mock|cli] [--timeout SEC] [--worker <id>] \
            [--mock-result <json>] [--mock-exit-code N]
    python worker_adapter.py list   --config <F>     # 按注册表结构列出 Worker 接口
    python worker_adapter.py health --config <F>     # 入口/健康探测（无 AI 调用）

统一退出码（worker 级，与 CLI 退出码一致）：
    0 = 成功
    1 = 执行失败（子进程非零退出 / 输入错误）
    2 = 超时

Web 型 / GUI 型（本模块不实现，只登记说明）：
  - 网页型：复用 chatgpt_bridge 模式（已存在，见 capability-registry 的
    adapter-web-session / tool-chatgpt-bridge）。
  - GUI 型：登记 Experimental（如 provider-catpaw 登录态 / browser 型执行面），
    依赖人工登录，不做 CLI 协议。

红线：
  1) 真实 AI worker（codebuddy/codex 等）调用消耗真实额度，属 L3 业主；
     本模块 mock 模式零消耗；CLI 模式仅用于本地运行时/无害命令（测试同款）。
  2) 凭据不入仓；worker entry 只登记路径/命令，不携带 token。
  3) 输出为 inert 数据（non_authority）。
  4) 不改 src/aicontrol/、config/production.json、runtime/runtime.py、
     config/capability-registry.json（只读衔接）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "v1.1-d1-worker-adapter"
CONFIG_SCHEMA = "WORKER_ADAPTER_CONFIG"

_MAX_TAIL = 2000
_DEFAULT_TIMEOUT = 300


def _safe_text(value: Any, limit: int = 2000) -> str:
    if value is None:
        return ""
    text = str(value)
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return text[:limit]


def _tail(text: Optional[str], limit: int = _MAX_TAIL) -> str:
    """取 stdout/stderr 尾部（限长），None 视为 ''。"""
    if not text:
        return ""
    return text[-limit:]


# ---------------------------------------------------------------------------
# Config 加载 / 校验
# ---------------------------------------------------------------------------
def load_config(path: str) -> Dict[str, Any]:
    """读 Worker-Adapter JSON 配置（worker 列表，结构对齐 capability-registry workers 节）。

    {
      "schema": "WORKER_ADAPTER_CONFIG",
      "schema_version": 1,
      "default_timeout_sec": 300,
      "workers": [
        {
          "id": "worker-local-python",
          "name": "Local Python 3.12",
          "role": "worker",
          "type": "LOCAL_RUNTIME",
          "status": "official",
          "entry": {"kind": "command",
                    "command": ["C:/Users/17838/AppData/Local/Programs/Python/Python312/python.exe", "-"],
                    "cwd": null},
          "health_check": {"kind": "file",
                           "path": "C:/Users/17838/AppData/Local/Programs/Python/Python312/python.exe"},
          "timeout_sec": 60,
          "adapter": "adapter-local-command",
          "capabilities": ["cap-local-python"]
        }
      ]
    }
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config not found: {p}")
    try:
        cfg = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"config unreadable: {p} ({e})") from e
    if not isinstance(cfg, dict) or "workers" not in cfg:
        raise ValueError(f"config missing 'workers' list: {p}")
    if not isinstance(cfg["workers"], list) or not cfg["workers"]:
        raise ValueError(f"config 'workers' must be non-empty list: {p}")
    return cfg


def resolve_worker(cfg: Dict[str, Any], worker_id: str) -> Dict[str, Any]:
    """按 id 解析 worker；找不到时抛 ValueError（调用方转结构化错误）。"""
    for w in cfg["workers"]:
        if _safe_text(w.get("id"), 128) == worker_id:
            return w
    ids = [w.get("id", "?") for w in cfg["workers"]]
    raise ValueError(f"worker id '{worker_id}' not found; available: {ids}")


def _worker_entry_command(worker: Dict[str, Any]) -> List[str]:
    entry = worker.get("entry") or {}
    cmd = entry.get("command")
    if not isinstance(cmd, list) or not cmd:
        raise ValueError(f"worker '{_safe_text(worker.get('id'), 80)}' entry.command "
                         "缺失/非法（必须是非空字符串列表）")
    return [str(c) for c in cmd]


def _worker_timeout(cfg: Dict[str, Any], worker: Dict[str, Any],
                    cli_timeout: Optional[float]) -> float:
    if cli_timeout is not None and cli_timeout > 0:
        return float(cli_timeout)
    wto = worker.get("timeout_sec")
    if wto:
        return float(wto)
    return float(cfg.get("default_timeout_sec") or _DEFAULT_TIMEOUT)


# ---------------------------------------------------------------------------
# Mock 执行器（L2 测试通道，零消耗）
# ---------------------------------------------------------------------------
def _run_mock(worker: Dict[str, Any], goal: str, timeout: float,
              mock_result: Dict[str, Any], mock_exit_code: int) -> Dict[str, Any]:
    """内置假 worker：sleep 短时 + 返回预设结果。不消耗真实 worker/额度。"""
    start = time.monotonic()
    sleep_sec = min(0.05, max(0.0, timeout - 0.01)) if timeout > 0 else 0.0
    if sleep_sec > 0:
        time.sleep(sleep_sec)
    result = dict(mock_result or {})
    result.setdefault("result", "mock worker completed")
    result.setdefault("goal_excerpt", _safe_text(goal, 200))
    result.setdefault("worker_id", _safe_text(worker.get("id"), 128))
    stdout = json.dumps(result, ensure_ascii=False)
    elapsed = round(time.monotonic() - start, 4)
    return {
        "schema": SCHEMA, "command": "run", "ok": mock_exit_code == 0,
        "mode": "mock", "worker_id": _safe_text(worker.get("id"), 128),
        "exit_code": mock_exit_code, "timed_out": False,
        "result": result, "stdout_tail": _tail(stdout),
        "stderr_tail": "", "elapsed_sec": elapsed,
        "non_authority": True,
        "note": "mock 执行器：不消耗真实 worker（L2 测试通道）。",
    }


# ---------------------------------------------------------------------------
# CLI 型执行器（stdin 传 goal / stdout 收结果 / stderr 收日志）
# ---------------------------------------------------------------------------
def _run_cli(worker: Dict[str, Any], goal: str, timeout: float) -> Dict[str, Any]:
    cmd = _worker_entry_command(worker)
    entry = worker.get("entry") or {}
    cwd = entry.get("cwd") or None
    start = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            cmd,
            input=goal or "",
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
            encoding="utf-8",
            errors="replace",
        )
        exit_code = int(proc.returncode)
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
    except subprocess.TimeoutExpired as e:
        timed_out = True
        exit_code = 2
        stdout = _safe_text(getattr(e, "stdout", None) or "", 8000)
        stderr = _safe_text(getattr(e, "stderr", None) or "", 8000)
    except OSError as e:
        exit_code = 1
        stdout = ""
        stderr = f"spawn failed: {e}"
    elapsed = round(time.monotonic() - start, 4)

    # 结果字段：stdout 若为 JSON 则解析为对象；否则保留文本（限长）
    result: Any = None
    if stdout.strip():
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError:
            result = {"text": _safe_text(stdout, 4000)}

    return {
        "schema": SCHEMA, "command": "run", "ok": (not timed_out and exit_code == 0),
        "mode": "cli", "worker_id": _safe_text(worker.get("id"), 128),
        "exit_code": exit_code, "timed_out": timed_out,
        "result": result,
        "stdout_tail": _tail(stdout), "stderr_tail": _tail(stderr),
        "elapsed_sec": elapsed,
        "command": cmd,
        "non_authority": True,
        "note": "CLI 型协议：stdin 传 goal、stdout 收结果、stderr 收日志；"
                "退出码 0=成功/1=执行失败/2=超时。",
    }


def run_worker(cfg: Dict[str, Any], worker_id: str, goal: str,
               mode: str, timeout: Optional[float],
               mock_result: Dict[str, Any], mock_exit_code: int) -> Dict[str, Any]:
    worker = resolve_worker(cfg, worker_id)
    to = _worker_timeout(cfg, worker, timeout)
    if mode == "mock":
        return _run_mock(worker, goal, to, mock_result, mock_exit_code)
    return _run_cli(worker, goal, to)


# ---------------------------------------------------------------------------
# list / health
# ---------------------------------------------------------------------------
def worker_interface(worker: Dict[str, Any]) -> Dict[str, Any]:
    """按 capability-registry workers 节结构投影 Worker 接入接口（只读）。"""
    return {
        "id": _safe_text(worker.get("id"), 128),
        "name": _safe_text(worker.get("name"), 200),
        "role": _safe_text(worker.get("role") or "worker", 32),
        "type": _safe_text(worker.get("type"), 64),
        "status": _safe_text(worker.get("status"), 32),
        "entry": worker.get("entry"),
        "health_check": worker.get("health_check"),
        "timeout_sec": worker.get("timeout_sec"),
        "adapter": _safe_text(worker.get("adapter"), 128),
        "capabilities": worker.get("capabilities") or [],
    }


def list_workers(cfg: Dict[str, Any]) -> Dict[str, Any]:
    interfaces = [worker_interface(w) for w in cfg["workers"]]
    return {
        "schema": SCHEMA, "command": "list", "ok": True,
        "workers": interfaces, "count": len(interfaces),
        "non_authority": True,
        "note": "Worker 接入接口投影：结构对齐 config/capability-registry.json workers 节。",
    }


def _probe_worker(worker: Dict[str, Any]) -> Dict[str, Any]:
    """worker 健康探测（机械：entry 存在性/health_check file/port/command，无 AI 调用）。"""
    wid = _safe_text(worker.get("id"), 128)
    hc = worker.get("health_check") or {}
    kind = _safe_text(hc.get("kind"), 64)
    if kind == "file":
        target = _safe_text(hc.get("path"), 1024)
        if not target:
            return {"id": wid, "status": "MISSING", "reason": "health_check.path missing"}
        exists = Path(target).exists()
        return {"id": wid, "status": "UP" if exists else "MISSING",
                "reason": f"file exists={exists}: {target}"}
    if kind == "port":
        import socket
        host = _safe_text(hc.get("host") or "127.0.0.1", 256)
        port = int(hc.get("port", 0) or 0)
        timeout = float(hc.get("timeout_sec") or 2)
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return {"id": wid, "status": "UP", "reason": f"port open {host}:{port}"}
        except OSError as e:
            return {"id": wid, "status": "DOWN", "reason": f"port closed {host}:{port} ({e})"}
    if kind == "command":
        cmd = hc.get("command")
        if isinstance(cmd, list) and cmd:
            try:
                proc = subprocess.run([str(c) for c in cmd], capture_output=True,
                                      timeout=float(hc.get("timeout_sec") or 10),
                                      encoding="utf-8", errors="replace")
                ok = proc.returncode == 0
                return {"id": wid, "status": "UP" if ok else "DOWN",
                        "reason": f"command exit={proc.returncode}: {cmd}"}
            except (subprocess.TimeoutExpired, OSError) as e:
                return {"id": wid, "status": "DOWN", "reason": f"command probe failed: {e}"}
    # 无 health_check / 未知 kind：退回 entry 首元素存在性探测
    try:
        cmd = _worker_entry_command(worker)
    except ValueError as e:
        return {"id": wid, "status": "MISSING", "reason": _safe_text(e, 400)}
    first = cmd[0]
    exists = Path(first).exists()
    return {"id": wid, "status": "UP" if exists else "MISSING",
            "reason": f"entry exists={exists}: {first}"}


def health_workers(cfg: Dict[str, Any]) -> Dict[str, Any]:
    probes = [_probe_worker(w) for w in cfg["workers"]]
    return {
        "schema": SCHEMA, "command": "health", "ok": True,
        "workers": probes,
        "non_authority": True,
        "note": "worker 健康探测为机械存在性/端口探测，不调用真实 AI worker。",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def cmd_run(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        print(json.dumps({"schema": SCHEMA, "command": "run", "ok": False,
                          "error": "CONFIG_ERROR", "detail": _safe_text(e, 600)},
                         ensure_ascii=False, indent=2))
        return 1
    gf = Path(args.goal_file)
    if not gf.exists():
        print(json.dumps({"schema": SCHEMA, "command": "run", "ok": False,
                          "error": "GOAL_FILE_NOT_FOUND",
                          "goal_file": _safe_text(args.goal_file, 400),
                          "instruction": "goal 文件不存在；请检查路径。"},
                         ensure_ascii=False, indent=2))
        return 1
    goal = gf.read_text(encoding="utf-8", errors="replace")
    mock_result: Dict[str, Any] = {}
    if args.mock_result:
        try:
            parsed = json.loads(args.mock_result)
            if isinstance(parsed, dict):
                mock_result = parsed
            else:
                mock_result = {"result": parsed}
        except json.JSONDecodeError:
            mock_result = {"result": args.mock_result}
    try:
        worker_id = args.worker or _safe_text(cfg["workers"][0].get("id"), 128)
        result = run_worker(cfg, worker_id=worker_id, goal=goal, mode=args.mode,
                            timeout=args.timeout, mock_result=mock_result,
                            mock_exit_code=args.mock_exit_code)
    except ValueError as e:
        print(json.dumps({"schema": SCHEMA, "command": "run", "ok": False,
                          "error": "WORKER_RESOLVE_ERROR", "detail": _safe_text(e, 600)},
                         ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result.get("exit_code", 0)) if result.get("exit_code") in (0, 1, 2) else 1


def cmd_list(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        print(json.dumps({"schema": SCHEMA, "command": "list", "ok": False,
                          "error": "CONFIG_ERROR", "detail": _safe_text(e, 600)},
                         ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(list_workers(cfg), ensure_ascii=False, indent=2))
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        print(json.dumps({"schema": SCHEMA, "command": "health", "ok": False,
                          "error": "CONFIG_ERROR", "detail": _safe_text(e, 600)},
                         ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(health_workers(cfg), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Worker-Adapter: CLI 型弱模型 Worker 适配层（stdin/stdout 协议）")
    sub = ap.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="执行一个 worker（mock 或 CLI 型）")
    p_run.add_argument("--config", dest="config", required=True)
    p_run.add_argument("--goal-file", dest="goal_file", required=True)
    p_run.add_argument("--worker", dest="worker", default="",
                       help="worker id（缺省取 config 第一个）")
    p_run.add_argument("--mode", dest="mode", default="mock", choices=("mock", "cli"),
                       help="mock=内置假 worker；cli=按 entry 构造子进程")
    p_run.add_argument("--timeout", dest="timeout", type=float, default=None,
                       help="超时秒数（默认取 worker.timeout_sec / config.default_timeout_sec=300）")
    p_run.add_argument("--mock-result", dest="mock_result", default="",
                       help="mock 模式预设结果（JSON 字符串）")
    p_run.add_argument("--mock-exit-code", dest="mock_exit_code", type=int, default=0,
                       help="mock 模式预设退出码（默认 0）")

    p_list = sub.add_parser("list", help="按注册表结构列出 Worker 接入接口")
    p_list.add_argument("--config", dest="config", required=True)

    p_health = sub.add_parser("health", help="worker 健康探测（机械，无 AI 调用）")
    p_health.add_argument("--config", dest="config", required=True)
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "list":
        return cmd_list(args)
    if args.command == "health":
        return cmd_health(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
