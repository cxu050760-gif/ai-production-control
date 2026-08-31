"""Human Progress View — productized concise UI projection (Canonical §71).

Canonical requirement (docs/canonical/CANONICAL_PRODUCT_DEFINITION_V1.0.md:2127-2141):

    用户默认不需要看完整 Trace。默认只需要看到：
    当前状态 / 当前进度 / 重要阻塞 / 关键变化 / 必要 Human Gate /
    最终成果 / 必要 Evidence / 最终 Acceptance。

Prior state: brain_bridge.py / task_graph.py each embed a small
``_human_view`` projection inside their full JSON output — real but not a
product surface.  This module is the productized §71 view:

1.  ``build_view`` derives the 8 canonical sections from a Task Graph JSON
    (the brain_bridge / task_graph output) — one truth source, one more
    projection, still zero second state.
2.  Conciseness is enforced structurally: empty sections are omitted
    entirely, lists are capped (default 5), and the full AI trace /
    instruction payloads are never copied in (the whole point of §71).
3.  ``render_text`` renders a fixed-width plain-text panel for terminals.
4.  CLI: ``python human_view.py --graph graph.json [--out view.json]``
    prints the concise view; exit 0 on any valid graph, 2 on bad input.
    ``--format text`` gives the terminal panel.

Non-authority: pure derived projection; every payload carries
non_authority=True and a view_note.  It never mutates the graph and never
grants authority.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "v1.0-human-view-71"
MAX_LIST = 5
GOAL_SUMMARY_CHARS = 80

# The 8 canonical §71 sections, in display order.
SECTIONS = ("current_state", "progress", "blockers", "key_changes",
            "human_gates", "final_result", "evidence", "final_acceptance")

# The only node states that map to a visible "in progress" step.
_ACTIVE_STATES = ("READY", "RUNNING")
# Node states that surface as blockers/attention items.
_BLOCKED_STATES = ("BLOCKED", "FAILED")


def _clip(text: Any, limit: int = GOAL_SUMMARY_CHARS) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _cap(items: List[Any], limit: int = MAX_LIST) -> List[Any]:
    return items[:limit]


def build_view(graph: Dict[str, Any]) -> Dict[str, Any]:
    """Derive the §71 concise view from a Task Graph JSON.

    Accepted inputs: brain_bridge.build_taskgraph output (``tasks`` list)
    or task_graph.to_json output (``task_graph`` with node objects).
    """
    tasks = graph.get("tasks")
    if tasks is None and isinstance(graph.get("task_graph"), dict):
        raw = graph["task_graph"].get("nodes") or {}
        tasks = [
            {"step": k, "detail": (v or {}).get("description", ""),
             "state": (v or {}).get("state", "")}
            for k, v in raw.items()
        ]
    if not isinstance(tasks, list):
        raise ValueError("GRAPH_TASKS_NOT_FOUND")
    if any(not isinstance(t, dict) for t in tasks):
        raise ValueError("GRAPH_TASKS_MUST_BE_OBJECTS")

    total = len(tasks)
    done = [t for t in tasks if t.get("state") == "DONE"]
    active = [t for t in tasks if t.get("state") in _ACTIVE_STATES]
    blocked = [t for t in tasks if t.get("state") in _BLOCKED_STATES]
    failed = [t for t in tasks if t.get("state") == "FAILED"]

    # -- 当前状态 -------------------------------------------------------
    if total > 0 and len(done) == total:
        current_state = "全部完成"
    elif failed:
        current_state = "有任务失败，需处理"
    elif blocked:
        current_state = "有阻塞，等待解除"
    elif len(done) > 0:
        current_state = "进行中"
    else:
        current_state = "待开始"

    # -- 当前进度 -------------------------------------------------------
    progress = {"done": len(done), "total": total,
                "percent": round(100.0 * len(done) / total, 1) if total else 0.0}

    # -- 重要阻塞 -------------------------------------------------------
    blockers = _cap([
        {"task": _clip(t.get("step") or t.get("task_id"), 40),
         "state": t.get("state", ""),
         "why": _clip(t.get("blocker") or t.get("detail"), 100)}
        for t in blocked
    ])

    # -- 关键变化（仅状态跨越事件，若图携带 changes） ---------------------
    key_changes = _cap([
        {"task": _clip(c.get("task", ""), 40),
         "change": _clip(c.get("change", ""), 80)}
        for c in (graph.get("changes") or [])
        if isinstance(c, dict) and c.get("change")
    ])

    # -- 必要 Human Gate -------------------------------------------------
    human_gates = _cap([
        {"gate": _clip(g.get("title") or g.get("gate") or g.get("name"), 60),
         "reason": _clip(g.get("reason"), 100)}
        for g in (graph.get("human_gates") or [])
        if isinstance(g, dict) and (g.get("title") or g.get("gate") or g.get("name"))
    ])

    # -- 最终成果 / 必要 Evidence / 最终 Acceptance ----------------------
    final_result = _clip(graph.get("final_result")) if graph.get("final_result") else None
    evidence = _cap([_clip(e, 120) for e in (graph.get("evidence") or [])
                     if str(e or "").strip()])
    acceptance = graph.get("final_acceptance")
    if isinstance(acceptance, dict):
        acceptance = {
            "verdict": acceptance.get("verdict") or acceptance.get("result"),
            "bound_to": acceptance.get("commit") or acceptance.get("bound_to"),
        }

    view: Dict[str, Any] = {
        "schema": SCHEMA,
        "goal_summary": _clip(graph.get("goal") or graph.get("goal_summary")),
        "current_state": current_state,
        "progress": progress,
        "non_authority": True,
        "view_note": "§71 简洁投影：由 Task Graph 机械派生，非独立状态源；完整 Trace 默认不展示。",
    }
    # 空节省略（简洁是结构性要求，不是格式选择）。
    if blockers:
        view["blockers"] = blockers
    if key_changes:
        view["key_changes"] = key_changes
    if human_gates:
        view["human_gates"] = human_gates
    if final_result:
        view["final_result"] = final_result
    if evidence:
        view["evidence"] = evidence
    if acceptance:
        view["final_acceptance"] = acceptance
    if active:
        view["next_steps"] = _cap([
            {"task": _clip(t.get("step") or t.get("task_id"), 40),
             "what": _clip(t.get("detail") or t.get("what"), 80)}
            for t in active
        ])
    return view


def render_text(view: Dict[str, Any]) -> str:
    """Fixed-width plain-text panel (no external deps, terminal friendly)."""
    lines: List[str] = []
    w = 60
    lines.append("=" * w)
    lines.append(f" 执衡 · Human View ({view.get('schema', SCHEMA)})")
    lines.append("=" * w)
    if view.get("goal_summary"):
        lines.append(f" 目标     : {view['goal_summary']}")
    lines.append(f" 状态     : {view.get('current_state', '未知')}")
    p = view.get("progress") or {}
    if p:
        lines.append(f" 进度     : {p.get('done', 0)}/{p.get('total', 0)}"
                     f" ({p.get('percent', 0)}%)")
    for label, key in (("阻塞", "blockers"), ("关键变化", "key_changes"),
                      ("Human Gate", "human_gates"), ("下一步", "next_steps")):
        for item in view.get(key) or []:
            if isinstance(item, dict):
                head = item.get("task") or item.get("gate") or ""
                sub = item.get("why") or item.get("what") or item.get("reason") or item.get("change") or ""
                lines.append(f" {label:<7}: {head}" + (f" — {sub}" if sub else ""))
            else:
                lines.append(f" {label:<7}: {item}")
    if view.get("final_result"):
        lines.append(f" 最终成果 : {view['final_result']}")
    for e in view.get("evidence") or []:
        lines.append(f" 证据     : {e}")
    acc = view.get("final_acceptance")
    if isinstance(acc, dict):
        lines.append(f" 验收     : {acc.get('verdict', '未裁定')}"
                     + (f" (bound: {acc['bound_to']})" if acc.get("bound_to") else ""))
    lines.append("-" * w)
    lines.append(f" {view.get('view_note', '')}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="§71 concise Human Progress View (derived, non-authority)")
    ap.add_argument("--graph", required=True, help="Task Graph JSON file")
    ap.add_argument("--out", default="", help="optional output JSON path")
    ap.add_argument("--format", choices=("json", "text"), default="json")
    args = ap.parse_args(argv)

    gp = Path(args.graph)
    if not gp.exists():
        print(json.dumps({"schema": SCHEMA, "ok": False,
                          "problem": "GRAPH_FILE_NOT_FOUND",
                          "non_authority": True}, ensure_ascii=False))
        return 2
    try:
        graph = json.loads(gp.read_text(encoding="utf-8"))
        view = build_view(graph)
    except Exception as exc:  # fail-closed: 任何畸形输入一律 exit 2，不漏 traceback
        print(json.dumps({"schema": SCHEMA, "ok": False,
                          "problem": f"GRAPH_INVALID:{exc}",
                          "non_authority": True}, ensure_ascii=False))
        return 2

    if args.out:
        Path(args.out).write_text(
            json.dumps(view, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.format == "text":
        print(render_text(view))
    else:
        print(json.dumps(view, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
