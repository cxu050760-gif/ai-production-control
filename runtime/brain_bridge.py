"""Brain Bridge — 把 Strategic Brain 接到真实 Goal 拆解（非侵入）。

复用 runtime/strategic_brain_contract.py 的 build_proposal（V0.7 Brain，90 测试绿）。
本模块只做「Goal 文本 -> 结构化输入 -> Brain proposal -> Task Graph」的接线，
不重写 Brain 逻辑，不改冻结的 runtime.py。

用法（独立 CLI，由调用方在 cmd_work 前后运行）：
    python brain_bridge.py --goal-file <goal.txt> [--out taskgraph.json]

红线：只读 goal 文件；输出 Task Graph 为 inert 数据（non_authority）；不碰
controller 状态/权限/预算/判定。任何 authority 词（crown/advance_milestone/
exec 等）在输入中被视为数据，绝不执行。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from strategic_brain_contract import build_proposal

SCHEMA = "v0.7-brain-bridge-taskgraph"
MAX_GOAL = 256

# 简单规则：从 goal 文本提取 must_have 约束（产出/交付/生成类动词后的名词短语）
_PRODUCE_PATTERNS = [
    re.compile(r"产出[「『\"']?([^。，,；;「」\"']{2,64})"),
    re.compile(r"生成[「『\"']?([^。，,；;「」\"']{2,64})"),
    re.compile(r"交付[「『\"']?([^。，,；;「」\"']{2,64})"),
    re.compile(r"写一份[「『\"']?([^。，,；;「」\"']{2,64})"),
    re.compile(r"整理[「『\"']?([^。，,；;「」\"']{2,64})"),
    re.compile(r"report[:：]\s*([A-Za-z0-9_.\-]{2,64})", re.IGNORECASE),
]

# 简单规则：提取 must_not_have（禁止类）
_FORBID_PATTERNS = [
    re.compile(r"不(?:要|允许|得)[「『\"']?([^。，,；;「」\"']{2,64})"),
    re.compile(r"禁止[「『\"']?([^。，,；;「」\"']{2,64})"),
    re.compile(r"不得[「『\"']?([^。，,；;「」\"']{2,64})"),
]


def extract_constraints(goal: str) -> List[Dict[str, str]]:
    """从 goal 文本机械提取 constraints（去重、限长）。"""
    seen: set = set()
    constraints: List[Dict[str, str]] = []
    for pat in _PRODUCE_PATTERNS:
        m = pat.search(goal)
        if not m:
            continue
        value = m.group(1).strip()[:64]
        key = ("must_have", value)
        if value and key not in seen:
            seen.add(key)
            constraints.append({"kind": "must_have", "value": value})
        if len(constraints) >= 8:
            break
    for pat in _FORBID_PATTERNS:
        m = pat.search(goal)
        if not m:
            continue
        value = m.group(1).strip()[:64]
        key = ("must_not_have", value)
        if value and key not in seen:
            seen.add(key)
            constraints.append({"kind": "must_not_have", "value": value})
        if len(constraints) >= 8:
            break
    return constraints


def build_taskgraph(goal: str) -> Dict[str, Any]:
    """Goal -> Brain proposal -> Task Graph（inert 数据）。"""
    if not isinstance(goal, str) or not (1 <= len(goal) <= MAX_GOAL):
        return {"schema": SCHEMA, "valid": False,
                "error": "GOAL_INVALID",
                "instruction": "goal must be str 1..256 chars"}
    constraints = extract_constraints(goal)
    brain_input: Dict[str, Any] = {"goal": goal, "constraints": constraints}
    proposal = build_proposal(brain_input)
    if not proposal.get("valid", True) or "proposal_id" not in proposal:
        return {"schema": SCHEMA, "valid": False,
                "error": proposal.get("error", "BRAIN_REJECTED"),
                "brain": proposal}
    # Task Graph：把 Brain plan 映射为可执行子任务（inert，non_authority）
    plan = proposal.get("plan", [])
    tasks = []
    for item in plan:
        tasks.append({
            "task_id": f"TG-{proposal['proposal_id'][:8]}-{item['step']:02d}",
            "step": item["step"],
            "action": item.get("action", "plan_item"),
            "detail": item.get("detail", ""),
            "state": "READY",
            "authority": "NONE",  # inert：执行者无权自行升级权限
        })
    return {
        "schema": SCHEMA,
        "valid": True,
        "goal": goal,
        "proposal_id": proposal["proposal_id"],
        "constraints": constraints,
        "tasks": tasks,
        "human_view": _human_view(goal, tasks),
        "non_authority": True,
        "origin": "strategic-brain-bridge",
        "instruction": "Execute tasks in order. Each task is inert data; "
                       "authority must come from the Controller.",
    }


def _human_view(goal: str, tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Human Progress View（§18）：从同一 Task Graph 机械投影，用户可读。

    一个真源（tasks），两种投影（AI Execution View + Human Progress View）。
    纯派生，不产生第二套状态，不会漂移。
    """
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("state") == "DONE")
    ready = sum(1 for t in tasks if t.get("state") == "READY")
    return {
        "goal_summary": goal[:80] + ("…" if len(goal) > 80 else ""),
        "progress": f"{done}/{total} 完成",
        "next_steps": [
            {"step": t["step"], "what": t.get("detail", ""),
             "state": t.get("state", "")}
            for t in tasks if t.get("state") in ("READY", "RUNNING")
        ],
        "overall": ("全部完成" if done == total and total > 0
                    else "进行中" if done > 0 else "待开始"),
        "view_note": "派生视图：仅由 Task Graph 机械投影，非独立状态源。",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Brain Bridge: Goal -> Task Graph")
    ap.add_argument("--goal-file", required=True, help="UTF-8 goal text file")
    ap.add_argument("--out", default="", help="optional output JSON path")
    args = ap.parse_args()

    gf = Path(args.goal_file)
    if not gf.exists():
        print(json.dumps({"schema": SCHEMA, "valid": False,
                          "error": "GOAL_FILE_NOT_FOUND"}, ensure_ascii=False))
        return 1
    goal = gf.read_text(encoding="utf-8", errors="replace").strip()
    graph = build_taskgraph(goal)
    if args.out:
        Path(args.out).write_text(
            json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(graph, ensure_ascii=False, indent=2))
    return 0 if graph.get("valid") else 2


if __name__ == "__main__":
    sys.exit(main())
