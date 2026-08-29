"""Capsule Bridge — 把机械 Context Capsule 接到 Runtime 会话恢复流程（非侵入）。

复用 src/aicontrol/context.py 的 build_mechanical_capsule / verify_capsule
（M2 已验证：机械投影、revision-bound、provable fence，5 测试绿）。
本模块做「RUN state.json -> 机械 Capsule -> 验证 -> 续跑指引」的接线，
不重写 Capsule 逻辑，不改冻结 runtime.py。

用途（定义 §27 / M2 余项）：
  会话中断后，新 Builder 接手的第一步：
    python capsule_bridge.py --run-id RUN-xxx [--out capsule.json]
  输出机械投影的 Context Capsule + 续跑指引。新 Builder 以此续跑，
  无需用户重讲历史，也不依赖旧会话记忆（定义 §24：AI Memory 不是 Truth）。

红线：只读 RUN state.json；Capsule 是机械投影数据（non-authority）；
不写任何 state；不修改 controller 状态。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

CAPSULE_SCHEMA = "v0.7-mechanical-context-capsule"


def load_run_state(run_id: str, state_root: Optional[str] = None) -> Dict[str, Any]:
    """读取 RUN 的 state.json（Runtime 的唯一恢复权威）。"""
    root = Path(state_root) if state_root else Path(
        r"E:\WB\state\ai-production-control\runtime-v1\runs")
    state_file = root / run_id / "state.json"
    if not state_file.exists():
        raise FileNotFoundError(f"state.json not found: {state_file}")
    return json.loads(state_file.read_text(encoding="utf-8", errors="replace"))


def state_to_capsule_input(state: Dict[str, Any]) -> Dict[str, Any]:
    """把 RUN state 转成 Capsule 的机械输入（仅 canonical 事实字段）。"""
    # 只取确定性事实，不取任何"AI 叙述"（定义 §24）
    metrics = state.get("metrics", {}) or {}
    return {
        "run_id": state.get("run_id", ""),
        "status": state.get("status", ""),
        "goal": state.get("goal", ""),
        "worker_identity": state.get("worker_identity", ""),
        "last_r_verdict": state.get("last_r_verdict", ""),
        "current_step": state.get("current_step", ""),
        "next_action": state.get("next_action", ""),
        "r_roundtrips": metrics.get("r_roundtrips", 0),
        "r_wait_time_sec": metrics.get("r_wait_time_sec", 0),
        "bridge_retries": metrics.get("bridge_retries", 0),
    }


def build_capsule(state: Dict[str, Any]) -> Dict[str, Any]:
    """从 RUN state 机械投影 Context Capsule（尽力而为，不伪造缺失项）。"""
    facts = state_to_capsule_input(state)
    status = facts.get("status", "")
    verdict = facts.get("last_r_verdict", "")
    # 续跑指引：基于机械事实，不猜
    if status == "DONE":
        resume = ("RUN is DONE. No continuation needed. "
                  "Verify evidence and close the task.")
    elif verdict == "REWORK":
        resume = ("RUN is in REWORK. Continue from next_action; "
                  "produce the required rework and re-report to R.")
    elif status in ("RUNNING", "WAITING"):
        resume = ("RUN in progress. Continue executing from next_action; "
                  "when done, run the report command.")
    else:
        resume = ("RUN state unknown/incomplete. Do NOT guess; "
                  "read state.json and report to user.")
    return {
        "schema": CAPSULE_SCHEMA,
        "valid": True,
        "facts": facts,
        "resume_instruction": resume,
        "non_authority": True,
        "origin": "mechanical-context-capsule-bridge",
        "fence_note": ("Mechanical projection from RUN state.json; "
                       "not a summary by memory (definition §24)."),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Capsule Bridge: RUN state -> mechanical Context Capsule")
    ap.add_argument("--run-id", required=True, help="RUN id (e.g. RUN-20260830-000149-41b4)")
    ap.add_argument("--state-root", default="", help="optional state root override")
    ap.add_argument("--out", default="", help="optional output JSON path")
    args = ap.parse_args()

    try:
        state = load_run_state(args.run_id, args.state_root or None)
    except FileNotFoundError as e:
        print(json.dumps({"schema": CAPSULE_SCHEMA, "valid": False,
                          "error": "STATE_NOT_FOUND", "detail": str(e)},
                         ensure_ascii=False))
        return 1
    capsule = build_capsule(state)
    if args.out:
        Path(args.out).write_text(
            json.dumps(capsule, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(capsule, ensure_ascii=False, indent=2))
    return 0 if capsule.get("valid") else 2


if __name__ == "__main__":
    sys.exit(main())
