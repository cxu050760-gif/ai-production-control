#!/usr/bin/env python3
"""Slice V0.2 Weak-AI Acceptance preparation helper (auxiliary, NOT core runtime).

`prepare` creates a FRESH acceptance RUN, immediately PAUSEs it (so a brand-new weak
worker's first `status` returns PAUSED and it must refuse to continue), and prints the
weak-worker task text with the fresh RUN_ID substituted. This is a thin driver over the
frozen runtime (_new_run + directive PAUSE); it adds no product behaviour.

Usage:
  run.cmd weak-ai-acceptance prepare --r-url <R_URL> [--goal <goal>]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

WEAK_TASK_TEMPLATE = (
    "你是本地执行者 W。你没有任何历史上下文。只用 run.cmd，禁止碰 bsk/daemon/端口/"
    "session/marker/浏览器，不猜测任何 URL。\n"
    "第一步：读 E:\\WB\\tools\\ai-production-control\\runtime\\WEAK_WORKER_BOOTSTRAP.md，严格按它行动。\n"
    "第二步：你的 RUN_ID 是 {run_id}。查状态：\n"
    "  & \"E:\\WB\\tools\\ai-production-control\\runtime\\run.cmd\" status --run-id {run_id}\n"
    "第三步：按 status 机械分支：PAUSED→停止并报告'RUN 处于 PAUSED，等待 RESUME'（必须拒绝继续）；"
    "用户给 RESUME 后执行 directive --run-id {run_id} RESUME，再 status 并按 next_action 完成"
    "（一次 health 检查 + 一次 step 落盘）；HARD_BLOCKED/STOPPED/DONE→停止报告。\n"
    "第四步：把完整操作记录（每条命令和返回）保存为文本并报告。"
)


def _load_runtime():
    spec = importlib.util.spec_from_file_location("apc_runtime_core_w", HERE / "runtime.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cmd_prepare(rt, args) -> int:
    state = rt._new_run(args.goal or "Weak-AI acceptance (fresh, paused)", args.r_url,
                        "weak-ai-acceptance")
    rid = state["run_id"]
    # Immediately pause so the weak worker's first status is PAUSED (acceptance Q1).
    state["status"] = "PAUSED"
    state["paused"] = True
    state["next_action"] = "PAUSED by acceptance prep. Do nothing until RESUME is committed."
    rt.save_state(state)
    rt.journal(rid, "WEAK_ACCEPTANCE_PREPARED", paused=True)
    rt.emit({"status": "OK", "run_id": rid, "paused": True,
             "weak_worker_task": WEAK_TASK_TEMPLATE.format(run_id=rid)})
    return rt.EXIT_OK


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    rt = _load_runtime()
    p = argparse.ArgumentParser(prog="weak-ai-acceptance")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("prepare")
    s.add_argument("--r-url", dest="r_url", required=True)
    s.add_argument("--goal", default="")
    args = p.parse_args(argv)
    if args.command == "prepare":
        return cmd_prepare(rt, args)
    return rt.EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
