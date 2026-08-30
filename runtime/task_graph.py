#!/usr/bin/env python3
"""Task Graph — 宪法 §17 Task Graph（v1.1 D5，黑盒线）。

把线性任务列表升级为「依赖 / 并行 / Owner / 动态加任务」的结构化 DAG：
  - 任务节点：id / description / depends_on / parallel_with / owner / state
  - DAG 校验：环检测（Kahn 拓扑）、重复 id、悬空依赖、parallel_with 一致性
  - 拓扑排序 + 关键路径计算（est_cost 加权，默认 1）
  - 动态加任务：add_subtask（挂在已有节点之下，自动接依赖）
  - 结构化 JSON 输出（对齐 runtime/brain_bridge.py 的 human_view / non_authority 语义）
  - CLI：build / add / status / brain-pick

红线：输出为 inert 数据（non_authority=True），不碰 controller 状态/权限/预算/判定；
任何 authority 词（crown/advance_milestone/exec 等）在输入中被视为数据，绝不执行。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "v1.1-d5-task-graph"
MAX_GOAL = 2048

# 状态枚举（对齐 runtime/brain_bridge.py 的 READY/RUNNING/DONE 语义 + PENDING/BLOCKED）
STATES = ("PENDING", "READY", "RUNNING", "DONE", "BLOCKED")


# ---------------------------------------------------------------- 基础工具


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _safe_text(value: Any, limit: int = 2000) -> str:
    return "" if value is None else str(value)[:limit]


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------- 任务节点


@dataclass
class TaskNode:
    """一个任务节点。depends_on / parallel_with 存节点 id 列表。"""

    task_id: str
    description: str
    depends_on: List[str] = field(default_factory=list)
    parallel_with: List[str] = field(default_factory=list)
    owner: str = ""
    state: str = "PENDING"
    est_cost: float = 1.0
    subtasks: List["TaskNode"] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "depends_on": list(self.depends_on),
            "parallel_with": list(self.parallel_with),
            "owner": self.owner,
            "state": self.state,
            "est_cost": self.est_cost,
            "subtask_ids": [s.task_id for s in self.subtasks],
        }


# ---------------------------------------------------------------- Task Graph


class TaskGraph:
    """Task Graph：节点集 + 依赖 + 并行 + 动态加任务 + 拓扑/关键路径。"""

    def __init__(self, goal: str = "") -> None:
        self.goal = _safe_text(goal, MAX_GOAL)
        self.nodes: Dict[str, TaskNode] = {}
        self._order: List[str] = []

    # -- 增删 ---------------------------------------------------------

    def add_task(
        self,
        task_id: str,
        description: str,
        depends_on: Optional[List[str]] = None,
        parallel_with: Optional[List[str]] = None,
        owner: str = "",
        state: str = "PENDING",
        est_cost: float = 1.0,
    ) -> TaskNode:
        task_id = str(task_id).strip()
        if not task_id:
            raise ValueError("task_id must be non-empty")
        if task_id in self.nodes:
            raise ValueError(f"duplicate task_id: {task_id}")
        if state not in STATES:
            raise ValueError(f"invalid state: {state}")
        node = TaskNode(
            task_id=task_id,
            description=_safe_text(description, 512),
            depends_on=list(depends_on or []),
            parallel_with=list(parallel_with or []),
            owner=_safe_text(owner, 128),
            state=state,
            est_cost=max(0.0, float(est_cost or 1.0)),
        )
        self.nodes[task_id] = node
        # parallel_with 自动对称化：B parallel_with A => A 也 parallel_with B
        for par in node.parallel_with:
            if par in self.nodes and task_id not in self.nodes[par].parallel_with:
                self.nodes[par].parallel_with.append(task_id)
        return node

    def add_subtask(
        self,
        parent_id: str,
        task_id: str,
        description: str,
        owner: str = "",
        state: str = "PENDING",
        est_cost: float = 1.0,
    ) -> TaskNode:
        """动态加任务：挂在 parent 之下，自动依赖 parent（§17 动态加任务）。"""
        parent = self.nodes.get(parent_id)
        if parent is None:
            raise ValueError(f"parent task not found: {parent_id}")
        node = self.add_task(
            task_id=task_id,
            description=description,
            depends_on=[parent_id],
            owner=owner,
            state=state,
            est_cost=est_cost,
        )
        parent.subtasks.append(node)
        return node

    def update_state(self, task_id: str, state: str) -> TaskNode:
        if task_id not in self.nodes:
            raise ValueError(f"task not found: {task_id}")
        if state not in STATES:
            raise ValueError(f"invalid state: {state}")
        self.nodes[task_id].state = state
        return self.nodes[task_id]

    # -- DAG 校验 -------------------------------------------------------

    def validate(self) -> Dict[str, Any]:
        """DAG 校验：重复 id、悬空依赖、parallel 一致性、环检测。

        返回 {"valid": bool, "errors": [...], "cycles": [...]}。
        环检测用 Kahn 算法：无法消去的节点即环成员（按 id 排序，稳定输出）。
        """
        errors: List[str] = []
        ids = set(self.nodes)
        for nid, node in self.nodes.items():
            for dep in node.depends_on:
                if dep not in ids:
                    errors.append(f"task {nid} depends on missing task {dep}")
            for par in node.parallel_with:
                if par not in ids:
                    errors.append(f"task {nid} parallel_with missing task {par}")
            # 自依赖 / 自并行
            if nid in node.depends_on:
                errors.append(f"task {nid} depends on itself")
            if nid in node.parallel_with:
                errors.append(f"task {nid} parallel_with itself")
        # parallel_with 对称性
        for nid, node in self.nodes.items():
            for par in node.parallel_with:
                if nid not in self.nodes[par].parallel_with:
                    errors.append(f"parallel_with not symmetric: {nid} -> {par}")
        # 环检测（Kahn）
        indeg = {nid: 0 for nid in self.nodes}
        adj: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        for nid, node in self.nodes.items():
            for dep in node.depends_on:
                if dep in self.nodes:
                    adj[dep].append(nid)
                    indeg[nid] += 1
        queue = sorted([nid for nid, d in indeg.items() if d == 0])
        topo: List[str] = []
        while queue:
            nid = queue.pop(0)
            topo.append(nid)
            for m in sorted(adj[nid]):
                indeg[m] -= 1
                if indeg[m] == 0:
                    queue.append(m)
        cycles = sorted(set(self.nodes) - set(topo))
        if cycles:
            errors.append(f"cycle detected among tasks: {','.join(cycles)}")
        self._order = topo
        return {
            "valid": not errors,
            "errors": errors,
            "cycles": cycles,
            "topological_order": topo,
        }

    # -- 拓扑 + 关键路径 --------------------------------------------------

    def topological_sort(self) -> List[str]:
        if not self._order:
            self.validate()
        return list(self._order)

    def critical_path(self) -> Dict[str, Any]:
        """关键路径：est_cost 加权最长路径（拓扑序 DP）。

        dist[nid] = est_cost(nid) + max(dist[dep] for dep in depends_on)。
        多路径并列时取 id 字典序较小者，保证确定性。
        返回 {path: [...], length: float, by_owner: [...]}。
        """
        self.validate()
        topo = self.topological_sort()
        if not topo:
            return {"path": [], "length": 0.0, "by_owner": []}
        dist: Dict[str, float] = {}
        prev: Dict[str, Optional[str]] = {}
        for nid in topo:
            best_dep: Optional[str] = None
            best_val = 0.0
            for dep in self.nodes[nid].depends_on:
                if dep not in dist:
                    continue
                cand = dist[dep]
                if cand > best_val + 1e-9 or (
                    abs(cand - best_val) < 1e-9
                    and (best_dep is None or dep < best_dep)
                ):
                    best_val = cand
                    best_dep = dep
            dist[nid] = self.nodes[nid].est_cost + best_val
            prev[nid] = best_dep
        end = max(dist, key=lambda k: (dist[k], -len(k)))
        best = dist[end]
        end = min((k for k, v in dist.items() if abs(v - best) < 1e-9), key=lambda k: k)
        path: List[str] = []
        cur: Optional[str] = end
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        # by_owner：关键路径上的 owner 分布
        by_owner: Dict[str, int] = {}
        for nid in path:
            owner = self.nodes[nid].owner or "unassigned"
            by_owner[owner] = by_owner.get(owner, 0) + 1
        return {
            "path": path,
            "length": round(float(dist[end]), 4),
            "by_owner": [{"owner": k, "task_count": v} for k, v in sorted(by_owner.items())],
        }

    # -- 输出 -----------------------------------------------------------

    def _human_view(self) -> Dict[str, Any]:
        """Human Progress View（§18）：派生投影，与 brain_bridge 对齐。"""
        total = len(self.nodes)
        done = sum(1 for n in self.nodes.values() if n.state == "DONE")
        ready = sum(1 for n in self.nodes.values() if n.state in ("READY", "RUNNING"))
        return {
            "goal_summary": self.goal[:80] + ("…" if len(self.goal) > 80 else ""),
            "progress": f"{done}/{total} 完成",
            "next_steps": [
                {"task_id": n.task_id, "what": n.description, "state": n.state}
                for n in self.nodes.values()
                if n.state in ("READY", "RUNNING")
            ],
            "overall": (
                "全部完成" if total > 0 and done == total
                else "进行中" if done > 0 else "待开始"
            ),
            "view_note": "派生视图：仅由 Task Graph 机械投影，非独立状态源。",
        }

    def to_json(self, trace: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        v = self.validate()
        cp = self.critical_path()
        parallel_groups: List[List[str]] = []
        seen: set = set()
        for nid, node in self.nodes.items():
            members = sorted({nid, *node.parallel_with} - seen)
            if members:
                seen.update(members)
                parallel_groups.append(members)
        return {
            "schema": SCHEMA,
            "valid": v["valid"],
            "goal": self.goal,
            "node_count": len(self.nodes),
            "nodes": [self.nodes[nid].to_dict() for nid in sorted(self.nodes)],
            "dependencies": [
                {"task_id": nid, "depends_on": list(self.nodes[nid].depends_on)}
                for nid in sorted(self.nodes)
                if self.nodes[nid].depends_on
            ],
            "topological_order": v["topological_order"],
            "critical_path": cp,
            "parallel_groups": parallel_groups,
            "validation": {"errors": v["errors"], "cycles": v["cycles"]},
            "human_view": self._human_view(),
            "non_authority": True,
            "origin": "task-graph-d5",
            "trace": trace or {},
            "instruction": "Tasks are inert data; authority must come from the Controller.",
        }


# ---------------------------------------------------------------- Goal 拆解


_ACTION_VERBS = [
    "修复", "实现", "开发", "编写", "写", "生成", "创建", "新增", "添加",
    "重构", "更新", "修改", "删除", "移除", "验证", "测试", "检查", "审核",
    "评审", "构建", "部署", "运行", "导出", "整理", "拆解", "转换", "分析",
    "设计", "集成", "对接", "记录",
]
_VERIFY_VERBS = {"验证", "测试", "检查", "审核", "评审", "确认"}
_PARALLEL_HINTS = ("并行", "同时", "可并行", "互不依赖", "独立进行")
_SEQ_HINTS = ("随后", "然后", "再", "最后", "之后", "下一步")

_SENT_SPLIT = re.compile(r"[。；;\n]+")


def _split_sentences(goal: str) -> List[str]:
    parts = [p.strip() for p in _SENT_SPLIT.split(goal) if p and p.strip()]
    if not parts:
        parts = [goal.strip()]
    return [p for p in parts if p][:32]


def _first_verb(sentence: str) -> Optional[str]:
    for verb in _ACTION_VERBS:
        if verb in sentence:
            return verb
    return None


def build_from_goal(goal: str) -> TaskGraph:
    """规则式 Goal -> Task Graph（机械、确定性，无 AI 调用）。

    规则：
      1) 按 。；；\n 拆句；
      2) 每句生成一个任务（找不到动词也给任务，desc=整句）；
      3) 验证类句子依赖前一个非验证任务（若存在）；
      4) 句子含并行提示词 -> 与前一个任务 parallel_with（双向）且不依赖它；
      5) 其余情况任务 i 依赖任务 i-1（线性串行默认）；
      6) 显式 Owner 形如 "owner:xxx" / "负责人:xxx" 从句尾提取。
    """
    g = TaskGraph(goal=_safe_text(goal, MAX_GOAL))
    sentences = _split_sentences(g.goal)
    if not sentences:
        return g
    prev_non_verify: Optional[str] = None
    for idx, sent in enumerate(sentences):
        task_id = f"T{idx + 1:02d}"
        desc = _safe_text(sent, 512)
        owner = ""
        # owner 提取
        om = re.search(r"(?:owner|负责人|owner_id)\s*[:：]\s*([A-Za-z0-9_.\-]{1,64})", sent, re.IGNORECASE)
        if om:
            owner = om.group(1)
        verb = _first_verb(sent)
        is_verify = verb in _VERIFY_VERBS or "测试" in sent or "验证" in sent
        is_parallel = any(h in sent for h in _PARALLEL_HINTS)
        deps: List[str] = []
        parallel_with: List[str] = []
        if is_parallel and prev_non_verify is not None:
            parallel_with = [prev_non_verify]
        elif is_verify and prev_non_verify is not None:
            deps = [prev_non_verify]
        elif prev_non_verify is not None and not is_parallel:
            deps = [prev_non_verify]
        g.add_task(task_id, desc, depends_on=deps, parallel_with=parallel_with,
                   owner=owner, state="PENDING")
        if not is_verify:
            prev_non_verify = task_id
    # parallel_with 对称化
    for nid, node in g.nodes.items():
        for par in list(node.parallel_with):
            if nid not in g.nodes[par].parallel_with:
                g.nodes[par].parallel_with.append(nid)
    return g


# ---------------------------------------------------------------- Brain 选型


def _load_registry(path: Optional[str] = None) -> Dict[str, Any]:
    p = Path(path) if path else (_repo_root() / "config" / "capability-registry.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


_HIGH_COMPLEXITY = (
    "多文件", "集成", "重构", "安全", "审计", "分布式", "并发", "复杂",
    "权威矩阵", "attack", "攻防", "权限", "加密", "认证", "迁移", "架构",
)
_LOW_COMPLEXITY = (
    "机械", "简单", "单文件", "格式", "复制", "重命名", "文档", "整理",
    "导出", "模板", "占位", "复制粘贴", "格式转换",
)


def classify_complexity(goal_text: str) -> str:
    """规则式复杂度分档：high | mid | low（参考 D2 cost_router.classify_goal 语义）。"""
    text = _safe_text(goal_text, 8000).lower()
    for kw in _HIGH_COMPLEXITY:
        if kw.lower() in text:
            return "high"
    for kw in _LOW_COMPLEXITY:
        if kw.lower() in text:
            return "low"
    return "mid"


def brain_pick(goal_text: str, registry_path: Optional[str] = None,
               costs_path: Optional[str] = None) -> Dict[str, Any]:
    """按任务复杂度从 registry brains 节选 Brain（规则式：简单->弱、复杂->强）。

    选型映射（D2 路由语义）：
      low   -> 主脑回退链最弱可用（默认 brain-workbuddy-deepseek-v4-flash）
      mid   -> 中等（默认 brain-codex-local）
      high  -> 主脑（默认 brain-chatgpt-web）
    若 registry 缺失/为空则用默认映射；cost 从 registry costs 节只读取。
    """
    complexity = classify_complexity(goal_text)
    registry = _load_registry(registry_path)
    brains = (registry.get("sections") or {}).get("brains") or []
    brain_ids = [b.get("id") for b in brains if isinstance(b, dict) and b.get("id")]
    costs = (registry.get("sections") or {}).get("costs") or []
    cost_by_cap = {c.get("capability_id"): c.get("cost_per_call") for c in costs if isinstance(c, dict)}

    defaults = {
        "low": "brain-workbuddy-deepseek-v4-flash",
        "mid": "brain-codex-local",
        "high": "brain-chatgpt-web",
    }
    chosen = defaults.get(complexity, "brain-codex-local")
    # registry 优先：按优先级顺序找第一个存在的
    pref_order = {
        "low": ["brain-workbuddy-deepseek-v4-flash", "brain-codex-local", "brain-chatgpt-web"],
        "mid": ["brain-codex-local", "brain-chatgpt-web", "brain-workbuddy-deepseek-v4-flash"],
        "high": ["brain-chatgpt-web", "brain-codex-local", "brain-workbuddy-deepseek-v4-flash"],
    }
    if brain_ids:
        for cand in pref_order.get(complexity, []):
            if cand in brain_ids:
                chosen = cand
                break
    unit_cost = cost_by_cap.get(chosen)
    return {
        "schema": "v1.1-d5-brain-pick",
        "brain_id": chosen,
        "complexity": complexity,
        "reason": f"goal complexity={complexity}; selected brain {chosen}",
        "unit_cost_per_call": unit_cost,
        "non_authority": True,
        "trace": {
            "model": chosen,
            "ai": "rule-based-brain-pick",
            "tool": "task_graph.py brain-pick",
            "reason_retry": None,
            "cost": unit_cost,
        },
    }


# ---------------------------------------------------------------- CLI


def _cmd_build(args: argparse.Namespace) -> int:
    gf = Path(args.goal_file)
    if not gf.exists():
        print(json.dumps({"schema": SCHEMA, "valid": False,
                          "error": "GOAL_FILE_NOT_FOUND"}, ensure_ascii=False))
        return 1
    goal = gf.read_text(encoding="utf-8", errors="replace").strip()
    g = build_from_goal(goal)
    out = g.to_json(trace={
        "model": None,
        "ai": "rule-based-task-graph",
        "tool": "task_graph.py build",
        "reason_retry": None,
        "cost": None,
    })
    if args.out:
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["valid"] else 2


def _cmd_add(args: argparse.Namespace) -> int:
    # 从状态文件（上次 build 输出）加载，动态加任务后写回
    src = Path(args.state or "state/task_graph_state.json")
    if not src.exists():
        print(json.dumps({"schema": SCHEMA, "valid": False,
                          "error": "STATE_NOT_FOUND", "hint": "run build --out <state>"},
                         ensure_ascii=False))
        return 1
    data = json.loads(src.read_text(encoding="utf-8"))
    g = TaskGraph(goal=data.get("goal", ""))
    for n in data.get("nodes", []):
        g.add_task(n["task_id"], n["description"], depends_on=n.get("depends_on", []),
                   parallel_with=n.get("parallel_with", []), owner=n.get("owner", ""),
                   state=n.get("state", "PENDING"), est_cost=n.get("est_cost", 1.0))
    node = g.add_subtask(args.parent, args.task_id, args.desc, owner=args.owner or "")
    out = g.to_json(trace={
        "model": None,
        "ai": "rule-based-task-graph",
        "tool": "task_graph.py add",
        "reason_retry": None,
        "cost": None,
        "added_task": node.task_id,
    })
    if args.out:
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        src.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["valid"] else 2


def _cmd_status(args: argparse.Namespace) -> int:
    src = Path(args.state or "state/task_graph_state.json")
    if not src.exists():
        print(json.dumps({"schema": SCHEMA, "valid": False,
                          "error": "STATE_NOT_FOUND"}, ensure_ascii=False))
        return 1
    data = json.loads(src.read_text(encoding="utf-8"))
    g = TaskGraph(goal=data.get("goal", ""))
    for n in data.get("nodes", []):
        g.add_task(n["task_id"], n["description"], depends_on=n.get("depends_on", []),
                   parallel_with=n.get("parallel_with", []), owner=n.get("owner", ""),
                   state=n.get("state", "PENDING"), est_cost=n.get("est_cost", 1.0))
    print(json.dumps(g.to_json(trace={
        "model": None,
        "ai": "rule-based-task-graph",
        "tool": "task_graph.py status",
        "reason_retry": None,
        "cost": None,
    }), ensure_ascii=False, indent=2))
    return 0


def _cmd_brain_pick(args: argparse.Namespace) -> int:
    gf = Path(args.goal)
    if gf.exists():
        goal = gf.read_text(encoding="utf-8", errors="replace").strip()
    else:
        goal = args.goal
    print(json.dumps(brain_pick(goal, registry_path=args.registry), ensure_ascii=False, indent=2))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Task Graph (v1.1 D5)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="从 goal 文本拆解任务")
    p_build.add_argument("--goal-file", required=True)
    p_build.add_argument("--out", default="")
    p_build.set_defaults(func=_cmd_build)

    p_add = sub.add_parser("add", help="动态加任务")
    p_add.add_argument("--parent", required=True)
    p_add.add_argument("--task-id", required=True)
    p_add.add_argument("--desc", required=True)
    p_add.add_argument("--owner", default="")
    p_add.add_argument("--state", default="state/task_graph_state.json")
    p_add.add_argument("--out", default="")
    p_add.set_defaults(func=_cmd_add)

    p_status = sub.add_parser("status", help="输出当前 Task Graph 状态")
    p_status.add_argument("--state", default="state/task_graph_state.json")
    p_status.set_defaults(func=_cmd_status)

    p_brain = sub.add_parser("brain-pick", help="按复杂度选 Brain")
    p_brain.add_argument("--goal", required=True)
    p_brain.add_argument("--registry", default="")
    p_brain.set_defaults(func=_cmd_brain_pick)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
