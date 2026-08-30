"""CostRouter — 成本路由 + 安全熔断（宪法 §2/§59/§61，v1.1-blackbox D2）。

背景（已实测确认）：
  - 宪法 §59 成本路由：成本感知——按任务价值路由到合适的 AI
    （弱模型便宜干活、强模型贵审查）；
  - 宪法 §61 Hard Fuse：安全熔断 SAFE_HALT 从未真实触发（本模块要触发 1 次）；
  - 宪法 §2 成本感知：系统此前无 Expected Total Cost 核算；
  - 宪法 §19 NO_PROGRESS：计数器此前未真实触发。

本模块（机器可完成部分）实现：
  A. Expected Total Cost 路由 v1（§59/§2）
     route --goal <简述或类型> [--tokens-est N] [--rework-risk low|mid|high]
       -> 计算 Expected Total Cost = Σ(各阶段 AI 调用成本 × 概率权重)
          （弱 Worker 执行 + 强 R 审查 + 可能的 REWORK 循环），
          输出成本分解表（阶段/模型/单价/期望次数/期望成本）+ 推荐路由
          （weak|strong|hybrid）+ 可解释说明。
     budget --goal ... --max-cost N
       -> 预算熔断检查：期望成本 > 阈值 -> BLOCKED（返回 SAFE_HALT 建议）。
  B. SAFE_HALT 真实触发（§61）
     内置 SAFE_HALT 状态机，触发条件（cost_policy.json 可配置）：
       ① BUDGET_BREACH        ：期望成本超预算阈值
       ② NO_PROGRESS          ：NO_PROGRESS 计数器超限（连续 REWORK 无进展）
       ③ CONSECUTIVE_BREACH   ：连续熔断标记超限
     触发后输出 SAFE_HALT 记录（结构化 JSON：原因/时间/上下文/恢复建议），
     冻结该任务（不自动重试）；人工审查后 reset 解冻。

与 D1 衔接（只读）：
  - 成本表 model id 对齐 runtime/adapters/r_adapter.py 的 provider 结构
    （r-prod-chatgpt-web / r-deepseek-v4-flash / r-codex-local）与
    runtime/adapters/worker_adapter.py 的 worker id
    （worker-workbuddy-cli / worker-codex-cli）；
  - 成本数据来源：config/cost_policy.json（模型单价表）+ 
    config/capability-registry.json costs 节（只读衔接）；单价缺失的模型
    输出"待校准"并跳过其成本计算。

红线：
  1) 输出为 inert 数据（non_authority）；任何 authority 词只作数据呈现，绝不代执行；
  2) 本模块不发起任何真实 AI 调用（L2 用 mock / 纯计算；L3 留业主）；
  3) 不改 src/aicontrol/、config/production.json、runtime/runtime.py、
     runtime/adapters/ 既有文件（只读衔接 r_adapter/worker_adapter）；
  4) 状态文件默认落在 state/cost_router_state.json（运行时工件，不入仓凭据）。

用法（CLI 桥模式，JSON 输出 / 退出码 0/1/2）：
    python cost_router.py route --goal '机械读取任务' [--rework-risk low|mid|high] [--tokens-est N]
    python cost_router.py budget --goal '...' --max-cost 0.5
    python cost_router.py safe-halt --goal '...' --reason-detail '...'
    python cost_router.py simulate-rework --goal '...' --cycles 3
    python cost_router.py status
    python cost_router.py reset [--goal '...']
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = "v1.1-d2-cost-router"
STATE_SCHEMA = "COST_ROUTER_STATE"
SAFE_HALT_SCHEMA = "SAFE_HALT_RECORD"

# 退出码约定（与既有 bridge 一致）：0=成功；1=配置/输入错误；2=硬停（SAFE_HALT/BLOCKED）
EXIT_OK = 0
EXIT_CONFIG_ERROR = 1
EXIT_HARD_STOP = 2

_DEFAULT_STATE = "state/cost_router_state.json"


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _safe_text(value: Any, limit: int = 2000) -> str:
    """任意值 -> 干净 str，限长，剔除不可打印控制符。"""
    if value is None:
        return ""
    text = str(value)
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return text[:limit]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(value: Any, default: float = 0.0) -> float:
    """任意值 -> float；None/非法 -> default。"""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _repo_root() -> Path:
    """仓库根 = 本文件上两级（runtime/ -> 仓库根）。"""
    return Path(__file__).resolve().parents[1]


def goal_hash(goal_text: str) -> str:
    """goal 文本 -> 稳定短哈希（用于冻结任务的键）。"""
    return hashlib.sha256(_safe_text(goal_text, 8000).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 配置加载（cost_policy.json + capability-registry.json costs 节，只读）
# ---------------------------------------------------------------------------
def load_policy(path: Optional[str] = None) -> Dict[str, Any]:
    """读 cost_policy.json；缺失/非法抛 ValueError（调用方转结构化错误）。"""
    p = Path(path) if path else (_repo_root() / "config" / "cost_policy.json")
    if not p.exists():
        raise FileNotFoundError(f"cost policy not found: {p}")
    try:
        policy = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"cost policy unreadable: {p} ({e})") from e
    if not isinstance(policy, dict) or "unit_prices" not in policy:
        raise ValueError(f"cost policy missing 'unit_prices': {p}")
    if "route_options" not in policy or not isinstance(policy.get("route_options"), dict):
        raise ValueError(f"cost policy missing 'route_options': {p}")
    if "circuit_breaker" not in policy or not isinstance(policy.get("circuit_breaker"), dict):
        raise ValueError(f"cost policy missing 'circuit_breaker': {p}")
    return policy


def load_registry_costs(path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """读 capability-registry.json 的 costs 节（只读衔接），返回
    {capability_id: {cost_per_call, cost_model, source, note}}。"""
    p = Path(path) if path else (_repo_root() / "config" / "capability-registry.json")
    if not p.exists():
        raise FileNotFoundError(f"capability registry not found: {p}")
    try:
        reg = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"capability registry unreadable: {p} ({e})") from e
    costs: Dict[str, Dict[str, Any]] = {}
    for entry in reg.get("sections", {}).get("costs", []) or []:
        if not isinstance(entry, dict):
            continue
        cid = entry.get("capability_id")
        if cid:
            costs[cid] = {
                "cost_per_call": entry.get("cost_per_call"),
                "cost_model": entry.get("cost_model"),
                "source": entry.get("source"),
                "note": entry.get("note"),
            }
    return costs


def resolve_unit_price(capability_id: str, policy: Dict[str, Any],
                       registry_costs: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """解析某 capability 的单次调用单价。

    优先级：cost_policy.json unit_prices[capability_id].unit_price（模型单价表）
            -> capability-registry.json costs 节 cost_per_call。
    单价缺失（None / 待校准）返回 None（调用方输出"待校准"并跳过成本计算）。
    """
    up = policy.get("unit_prices", {}).get(capability_id)
    if isinstance(up, dict) and up.get("unit_price") is not None:
        return {
            "unit_price": _num(up.get("unit_price")),
            "model": _safe_text(up.get("model"), 128),
            "source": _safe_text(up.get("source") or "估算", 32),
            "note": _safe_text(up.get("note"), 400),
        }
    rc = registry_costs.get(capability_id)
    if rc and rc.get("cost_per_call") is not None:
        return {
            "unit_price": _num(rc.get("cost_per_call")),
            "model": capability_id,
            "source": _safe_text(rc.get("source") or "估算", 32),
            "note": _safe_text(rc.get("note"), 400),
        }
    return None


# ---------------------------------------------------------------------------
# 路由计算（Expected Total Cost v1）
# ---------------------------------------------------------------------------
def classify_goal(goal_text: str, policy: Dict[str, Any]) -> str:
    """goal 文本 -> 目标价值档（high|mid|low）。

    规则（机械，不猜）：命中 high 关键字 -> high；否则 mid；否则 low；
    全不命中 -> mid（保守中间档，不猜高也不猜低）。
    """
    text = _safe_text(goal_text, 8000).lower()
    kw = policy.get("goal_type_keywords", {}) or {}
    for gtype in ("high", "mid", "low"):
        for k in kw.get(gtype, []) or []:
            if k and k.lower() in text:
                return gtype
    return "mid"


def rework_probability(rework_risk: str, policy: Dict[str, Any]) -> float:
    """rework-risk -> 单轮 REWORK 概率（cost_policy.json rework_probability）。"""
    table = policy.get("rework_probability", {}) or {}
    risk = _safe_text(rework_risk or "mid", 16).strip().lower()
    if risk in table:
        return _num(table[risk], 0.3)
    return _num(table.get("mid", 0.3), 0.3)


def geometric_sum(p_rework: float, max_review_cycles: int) -> float:
    """几何级数和 E[calls] = Σ_{i=0}^{max_cycles-1} p^i。

    语义：第 1 次调用必发生；第 2 次发生在第 1 次 REWORK 时（概率 p）；
    第 3 次发生在连续 2 次 REWORK 时（概率 p^2）；…… 直到 max_review_cycles。
    """
    cycles = max(1, int(max_review_cycles or 1))
    total = 0.0
    p_pow = 1.0
    for _ in range(cycles):
        total += p_pow
        p_pow *= p_rework
    return round(total, 4)


def expected_call_counts(p_rework: float, max_review_cycles: int) -> Tuple[float, float]:
    """返回 (worker_calls, review_calls)。

    弱 Worker 执行 + 强 R 审查管道：每次 REWORK 触发一次重新执行 + 一次重新审查，
    因此 worker_calls == review_calls == 几何级数和。
    """
    n = geometric_sum(p_rework, max_review_cycles)
    return n, n


def _stage_cost(unit_price: Optional[Dict[str, Any]], expected_calls: float,
                tokens_scale: float) -> Dict[str, Any]:
    """构造单个阶段成本行；单价缺失 -> 待校准（跳过成本计算）。"""
    if unit_price is None:
        return {
            "unit_price": None,
            "expected_calls": round(expected_calls, 4),
            "expected_cost": None,
            "status": "待校准",
            "note": "单价缺失（source=待实测/未校准），跳过其成本计算",
        }
    return {
        "unit_price": round(unit_price["unit_price"], 4),
        "expected_calls": round(expected_calls, 4),
        "expected_cost": round(unit_price["unit_price"] * expected_calls * tokens_scale, 6),
        "status": "已定价",
        "note": unit_price.get("note", ""),
    }


def compute_route_option(option_name: str, option_spec: Dict[str, Any],
                         p_rework: float, max_review_cycles: int,
                         policy: Dict[str, Any],
                         registry_costs: Dict[str, Dict[str, Any]],
                         tokens_est: int, reference_tokens: int) -> Dict[str, Any]:
    """计算单个路由选项的 Expected Total Cost 与成本分解表。"""
    worker_id = _safe_text(option_spec.get("worker"), 128)
    reviewer_id = _safe_text(option_spec.get("reviewer") or "", 128)
    tokens_scale = tokens_est / reference_tokens if reference_tokens > 0 else 1.0

    if not reviewer_id:
        # weak：弱 Worker 直接交付，无强审查 -> 单次执行，无 REWORK 循环
        worker_calls = 1.0
        review_calls = 0.0
    else:
        worker_calls, review_calls = expected_call_counts(p_rework, max_review_cycles)

    stages: List[Dict[str, Any]] = []

    worker_price = resolve_unit_price(worker_id, policy, registry_costs)
    worker_stage = {
        "stage": "worker_execute",
        "stage_name": "执行（Worker）",
        "model": worker_id,
        "unit_price": worker_price["unit_price"] if worker_price else None,
        "expected_calls": round(worker_calls, 4),
        "expected_cost": None,
        "status": "已定价" if worker_price else "待校准",
        "note": worker_price.get("note", "") if worker_price else "单价缺失，跳过成本计算",
    }
    if worker_price:
        worker_stage["expected_cost"] = round(
            worker_price["unit_price"] * worker_calls * tokens_scale, 6)
    stages.append(worker_stage)

    review_stage: Optional[Dict[str, Any]] = None
    if reviewer_id:
        review_price = resolve_unit_price(reviewer_id, policy, registry_costs)
        review_stage = {
            "stage": "r_review",
            "stage_name": "审查（强 R）",
            "model": reviewer_id,
            "unit_price": review_price["unit_price"] if review_price else None,
            "expected_calls": round(review_calls, 4),
            "expected_cost": None,
            "status": "已定价" if review_price else "待校准",
            "note": review_price.get("note", "") if review_price else "单价缺失，跳过成本计算",
        }
        if review_price:
            review_stage["expected_cost"] = round(
                review_price["unit_price"] * review_calls * tokens_scale, 6)
        stages.append(review_stage)

    rework_stage: Optional[Dict[str, Any]] = None
    if reviewer_id:
        rework_stage = {
            "stage": "rework_loop",
            "stage_name": "REWORK 循环（概率）",
            "model": "-",
            "unit_price": None,
            "expected_calls": round(worker_calls - 1.0, 4),
            "expected_cost": None,
            "status": "概率信息",
            "note": f"单轮 REWORK 概率 p={p_rework:.2f}；期望额外执行/审查次数 "
                    f"= {worker_calls - 1.0:.2f}（上限 max_review_cycles={max_review_cycles}）",
        }
        stages.append(rework_stage)

    # 期望总成本 = 有单价的阶段期望成本之和；全待校准 -> None
    priced = [s["expected_cost"] for s in stages if s.get("expected_cost") is not None]
    etc: Optional[float] = round(sum(priced), 6) if priced else None

    return {
        "route": option_name,
        "note": _safe_text(option_spec.get("note"), 400),
        "worker": worker_id,
        "reviewer": reviewer_id or None,
        "expected_total_cost": etc,
        "etc_status": "已定价" if etc is not None else "待校准",
        "stages": stages,
    }


def recommend_route(goal_type: str, rework_risk: str, policy: Dict[str, Any]) -> str:
    """推荐路由 v1（机械，按任务价值）：
      - high 价值档 -> strong（强干活 + 强审查，成本最高档）；
      - mid 价值档 -> hybrid（弱干活 + 强审查，宪法默认管道）；
      - low 价值档 -> weak（弱干活直接交付）；但 low + rework-risk=high
        时升为 hybrid（重做风险高，仍需强审查兜底）。
    """
    risk = _safe_text(rework_risk or "mid", 16).strip().lower()
    if goal_type == "high":
        return "strong"
    if goal_type == "low":
        return "weak" if risk in ("low", "mid") else "hybrid"
    return "hybrid"


def _budget_threshold(policy: Dict[str, Any], max_cost: Optional[float]) -> float:
    """预算阈值：显式 --max-cost 优先；否则 policy budget.default_budget_threshold。"""
    if max_cost is not None and max_cost > 0:
        return float(max_cost)
    budget = policy.get("budget", {}) or {}
    return _num(budget.get("default_budget_threshold"), 0.5)


# ---------------------------------------------------------------------------
# SAFE_HALT 状态机（宪法 §61 Hard Fuse）
# ---------------------------------------------------------------------------
def default_state() -> Dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "schema_version": 1,
        "status": "FREE",          # FREE | SAFE_HALT
        "tripped": False,
        "no_progress": {},         # goal_hash -> int（连续 REWORK 无进展计数）
        "consecutive_breach": 0,   # 连续熔断标记计数（budget BLOCKED 累计）
        "frozen_tasks": {},        # goal_hash -> SAFE_HALT record（冻结任务，不自动重试）
        "history": [],             # SAFE_HALT records（证据留存）
        "updated_at": _now_iso(),
    }


def load_state(path: Optional[str] = None) -> Dict[str, Any]:
    """读状态文件；不存在 -> 默认状态；非法 JSON -> 备份后重建默认状态。"""
    p = Path(path) if path else (_repo_root() / _DEFAULT_STATE)
    if not p.exists():
        return default_state()
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        # 状态文件损坏：不崩溃，重建默认（原文件重命名为 .corrupt-<ts> 留证）
        try:
            backup = p.with_name(f"{p.name}.corrupt-{int(datetime.now().timestamp())}")
            p.rename(backup)
        except OSError:
            pass
        return default_state()
    if not isinstance(data, dict):
        return default_state()
    merged = default_state()
    for key in ("status", "tripped", "no_progress", "consecutive_breach",
                "frozen_tasks", "history", "updated_at"):
        if key in data:
            merged[key] = data[key]
    return merged


def save_state(state: Dict[str, Any], path: Optional[str] = None) -> Path:
    """写状态文件（目录自动创建）。"""
    p = Path(path) if path else (_repo_root() / _DEFAULT_STATE)
    p.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _now_iso()
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _cb(policy: Dict[str, Any]) -> Dict[str, Any]:
    cb = policy.get("circuit_breaker", {}) or {}
    return cb


def _next_record_id(state: Dict[str, Any]) -> str:
    seq = len(state.get("history", []) or []) + 1
    return f"SAFE_HALT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{seq:03d}"


def trigger_safe_halt(state: Dict[str, Any], policy: Dict[str, Any],
                      reason: str, reason_detail: str, context: Dict[str, Any],
                      state_path: Optional[str] = None) -> Dict[str, Any]:
    """触发 SAFE_HALT：生成结构化记录、冻结任务、持久化状态。

    reason 枚举：BUDGET_BREACH | NO_PROGRESS | CONSECUTIVE_BREACH | MANUAL
    冻结 = 该任务（goal_hash）不再自动重试；只有 reset（人工审查后）解冻。
    """
    record: Dict[str, Any] = {
        "schema": SAFE_HALT_SCHEMA,
        "record_id": _next_record_id(state),
        "triggered_at": _now_iso(),
        "reason": reason,
        "reason_detail": _safe_text(reason_detail, 1200),
        "context": context or {},
        "freeze": True,
        "recovery": ("人工审查（owner）后执行 `cost_router.py reset --goal <goal>` "
                     "解冻；或调整成本策略（预算阈值 / rework-risk / 单价校准）后重路由。"
                     "宪法 §61 Hard Fuse：触发后冻结，不自动重试。"),
        "non_authority": True,
    }
    gh = _safe_text((context or {}).get("goal_hash"), 64)
    if gh:
        state.setdefault("frozen_tasks", {})[gh] = record
    state["status"] = "SAFE_HALT"
    state["tripped"] = True
    state.setdefault("history", []).append(record)
    save_state(state, state_path)
    return record


def _is_frozen(state: Dict[str, Any], gh: str) -> Optional[Dict[str, Any]]:
    """该任务是否已冻结（SAFE_HALT 未解冻）；是则返回冻结记录。"""
    frozen = state.get("frozen_tasks", {}) or {}
    return frozen.get(gh)


def _frozen_result(record: Dict[str, Any], gh: str) -> Dict[str, Any]:
    return {
        "schema": SCHEMA, "ok": False, "verdict": "FROZEN",
        "goal_hash": gh, "frozen": True,
        "detail": "该任务已因 SAFE_HALT 冻结（宪法 §61）：不自动重试。",
        "safe_halt": record,
        "recovery": record.get("recovery", ""),
        "non_authority": True,
    }


# ---------------------------------------------------------------------------
# 核心动作：route / budget / simulate-rework / safe-halt / status / reset
# ---------------------------------------------------------------------------
def _route_context(goal_text: str, goal_type: str, rework_risk: str,
                   tokens_est: int, threshold: float, route: str,
                   etc: Optional[float]) -> Dict[str, Any]:
    return {
        "goal": _safe_text(goal_text, 800),
        "goal_hash": goal_hash(goal_text),
        "goal_type": goal_type,
        "rework_risk": rework_risk,
        "tokens_est": tokens_est,
        "budget_threshold": threshold,
        "recommended_route": route,
        "expected_total_cost": etc,
    }


def do_route(goal_text: str, rework_risk: str, tokens_est: Optional[int],
             max_cost: Optional[float], policy: Dict[str, Any],
             registry_costs: Dict[str, Dict[str, Any]],
             state: Dict[str, Any], state_path: Optional[str] = None) -> Dict[str, Any]:
    """route 主逻辑：成本分解 + 推荐路由 + 预算熔断（SAFE_HALT 触发点 ①）。"""
    gh = goal_hash(goal_text)
    frozen = _is_frozen(state, gh)
    if frozen:
        return _frozen_result(frozen, gh)

    goal_type = classify_goal(goal_text, policy)
    p_rework = rework_probability(rework_risk, policy)
    max_cycles = int(policy.get("max_review_cycles", 3) or 3)
    reference_tokens = int(policy.get("reference_tokens_per_call", 2000) or 2000)
    tokens_est_v = int(tokens_est) if tokens_est is not None and tokens_est > 0 \
        else int(policy.get("tokens_est_default", 2000) or 2000)

    options = policy.get("route_options", {}) or {}
    option_results: Dict[str, Dict[str, Any]] = {}
    for name, spec in options.items():
        option_results[name] = compute_route_option(
            name, spec, p_rework, max_cycles, policy, registry_costs,
            tokens_est_v, reference_tokens)

    recommended = recommend_route(goal_type, rework_risk, policy)
    rec = option_results.get(recommended, next(iter(option_results.values())))

    threshold = _budget_threshold(policy, max_cost)
    etc = rec.get("expected_total_cost")
    breach = etc is not None and etc > threshold

    explanations = [
        f"目标价值档（keyword 分类）={goal_type}；rework-risk={rework_risk} "
        f"-> 单轮 REWORK 概率 p={p_rework:.2f}",
        f"推荐路由={recommended}：{rec.get('note', '')}",
        f"Expected Total Cost = Σ(各阶段 AI 调用成本 × 概率权重)：",
    ]
    for st in rec.get("stages", []):
        if st.get("expected_cost") is not None:
            explanations.append(
                f"  {st['stage_name']}({st['model']}) = {st['unit_price']} × "
                f"{st['expected_calls']} = {st['expected_cost']}")
        else:
            explanations.append(
                f"  {st['stage_name']}({st['model']}) 待校准：单价缺失，跳过成本计算")
    if etc is None:
        explanations.append("期望总成本无法判定（全部待校准）：预算熔断检查跳过（UNDETERMINED）。")
    elif breach:
        explanations.append(
            f"期望总成本 {etc:.4f} > 预算阈值 {threshold:.4f} -> 触发 SAFE_HALT "
            f"（宪法 §61 Hard Fuse：成本超预算，冻结任务，不自动重试）。")
    else:
        explanations.append(
            f"期望总成本 {etc:.4f} <= 预算阈值 {threshold:.4f} -> 允许执行。")

    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "command": "route",
        "ok": not breach,
        "verdict": "SAFE_HALT" if breach else "ALLOWED",
        "goal": _safe_text(goal_text, 800),
        "goal_hash": gh,
        "goal_type": goal_type,
        "rework_risk": rework_risk,
        "p_rework": p_rework,
        "tokens_est": tokens_est_v,
        "tokens_scale": round(tokens_est_v / reference_tokens, 4) if reference_tokens > 0 else 1.0,
        "max_review_cycles": max_cycles,
        "recommended_route": recommended,
        "recommended_route_note": rec.get("note", ""),
        "expected_total_cost": etc,
        "etc_status": rec.get("etc_status"),
        "budget_threshold": threshold,
        "stages": rec.get("stages", []),
        "options": {
            name: {
                "route": r.get("route"),
                "worker": r.get("worker"),
                "reviewer": r.get("reviewer"),
                "expected_total_cost": r.get("expected_total_cost"),
                "etc_status": r.get("etc_status"),
            }
            for name, r in option_results.items()
        },
        "explanations": explanations,
        "non_authority": True,
    }

    if breach:
        context = _route_context(goal_text, goal_type, rework_risk, tokens_est_v,
                                 threshold, recommended, etc)
        record = trigger_safe_halt(state, policy, "BUDGET_BREACH",
                                   f"期望总成本 {etc:.4f} 超预算阈值 {threshold:.4f} "
                                   f"（goal_type={goal_type}, rework_risk={rework_risk}, "
                                   f"recommended_route={recommended}）",
                                   context, state_path)
        result["verdict"] = "SAFE_HALT"
        result["ok"] = False
        result["safe_halt"] = record
        result["frozen"] = True
        result["recovery"] = record.get("recovery", "")
    elif etc is None:
        # 全部阶段待校准：无法判定预算，不误伤（ok=True，明确 UNDETERMINED）
        result["verdict"] = "UNDETERMINED"
        result["ok"] = True
        save_state(state, state_path)
        return result
    else:
        # 允许通过：连续熔断计数清零（成功即解除连续标记）
        if etc is not None:
            state["consecutive_breach"] = 0
        save_state(state, state_path)

    return result


def do_budget(goal_text: str, max_cost: Optional[float], rework_risk: str,
              tokens_est: Optional[int], policy: Dict[str, Any],
              registry_costs: Dict[str, Dict[str, Any]],
              state: Dict[str, Any], state_path: Optional[str] = None) -> Dict[str, Any]:
    """budget 主逻辑：预算熔断检查。

    ETC > 阈值 -> BLOCKED（返回 SAFE_HALT 建议）；连续 BLOCKED 达到
    circuit_breaker.consecutive_breach_limit -> 触发 SAFE_HALT（条件 ③）。
    """
    gh = goal_hash(goal_text)
    frozen = _is_frozen(state, gh)
    if frozen:
        return _frozen_result(frozen, gh)

    goal_type = classify_goal(goal_text, policy)
    p_rework = rework_probability(rework_risk, policy)
    max_cycles = int(policy.get("max_review_cycles", 3) or 3)
    reference_tokens = int(policy.get("reference_tokens_per_call", 2000) or 2000)
    tokens_est_v = int(tokens_est) if tokens_est is not None and tokens_est > 0 \
        else int(policy.get("tokens_est_default", 2000) or 2000)

    options = policy.get("route_options", {}) or {}
    recommended = recommend_route(goal_type, rework_risk, policy)
    spec = options.get(recommended, next(iter(options.values())))
    rec = compute_route_option(recommended, spec, p_rework, max_cycles,
                               policy, registry_costs, tokens_est_v, reference_tokens)

    threshold = _budget_threshold(policy, max_cost)
    etc = rec.get("expected_total_cost")
    breach = etc is not None and etc > threshold

    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "command": "budget",
        "ok": not breach,
        "verdict": "BLOCKED" if breach else "ALLOWED",
        "goal": _safe_text(goal_text, 800),
        "goal_hash": gh,
        "goal_type": goal_type,
        "rework_risk": rework_risk,
        "recommended_route": recommended,
        "expected_total_cost": etc,
        "etc_status": rec.get("etc_status"),
        "budget_threshold": threshold,
        "max_cost_provided": max_cost is not None,
        "suggest_safe_halt": breach,
        "stages": rec.get("stages", []),
        "explanations": [
            f"预算检查（recommended_route={recommended}）："
            f"期望总成本 {etc:.4f} vs 预算阈值 {threshold:.4f}。"
            if etc is not None else
            "期望总成本无法判定（全部待校准）：跳过预算熔断检查（UNDETERMINED）。",
        ],
        "non_authority": True,
    }

    if etc is None:
        result["verdict"] = "UNDETERMINED"
        result["ok"] = True
        result["suggest_safe_halt"] = False
        save_state(state, state_path)
        return result

    if breach:
        state["consecutive_breach"] = int(state.get("consecutive_breach", 0)) + 1
        cb = _cb(policy)
        limit = int(cb.get("consecutive_breach_limit", 2) or 2)
        if state["consecutive_breach"] >= limit:
            # 条件 ③：连续熔断标记超限 -> SAFE_HALT 真实触发
            context = _route_context(goal_text, goal_type, rework_risk, tokens_est_v,
                                     threshold, recommended, etc)
            record = trigger_safe_halt(
                state, policy, "CONSECUTIVE_BREACH",
                f"连续 {state['consecutive_breach']} 次预算 BLOCKED（limit={limit}）："
                f"期望总成本 {etc:.4f} 超阈值 {threshold:.4f}",
                context, state_path)
            result["verdict"] = "SAFE_HALT"
            result["ok"] = False
            result["safe_halt"] = record
            result["frozen"] = True
            result["recovery"] = record.get("recovery", "")
        else:
            result["verdict"] = "BLOCKED"
            result["ok"] = False
            result["consecutive_breach"] = state["consecutive_breach"]
            result["detail"] = ("预算熔断检查未通过：期望成本超阈值，返回 SAFE_HALT 建议；"
                                "连续 BLOCKED 将升级为 SAFE_HALT（宪法 §61）。")
            result["explanations"].append(
                f"连续 BLOCKED {state['consecutive_breach']}/{limit} 次；"
                f"达到 {limit} 次将触发 SAFE_HALT。")
        save_state(state, state_path)
        return result

    state["consecutive_breach"] = 0
    save_state(state, state_path)
    return result


def do_simulate_rework(goal_text: str, cycles: int, no_progress_limit: Optional[int],
                       policy: Dict[str, Any], state: Dict[str, Any],
                       state_path: Optional[str] = None) -> Dict[str, Any]:
    """NO_PROGRESS 场景：连续 REWORK（mock）无进展 -> 触发熔断（条件 ②，§19 呼应）。

    cycles=连续 REWORK 轮数；no_progress_limit 缺省取 policy
    circuit_breaker.no_progress_limit。达到/超过 limit -> SAFE_HALT(NO_PROGRESS)。
    """
    gh = goal_hash(goal_text)
    frozen = _is_frozen(state, gh)
    if frozen:
        return _frozen_result(frozen, gh)

    cb = _cb(policy)
    limit = int(no_progress_limit) if no_progress_limit is not None and no_progress_limit > 0 \
        else int(cb.get("no_progress_limit", 3) or 3)
    cycles_v = max(1, int(cycles or 1))
    np_map = state.setdefault("no_progress", {})
    np_map[gh] = int(np_map.get(gh, 0)) + cycles_v
    count = np_map[gh]

    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "command": "simulate-rework",
        "ok": count < limit,
        "verdict": "SAFE_HALT" if count >= limit else "MONITORING",
        "goal": _safe_text(goal_text, 800),
        "goal_hash": gh,
        "goal_type": classify_goal(goal_text, policy),
        "no_progress_count": count,
        "no_progress_limit": limit,
        "detail": f"连续 REWORK 无进展计数 = {count}/{limit}（宪法 §19 NO_PROGRESS）。",
        "non_authority": True,
    }

    if count >= limit:
        context = {
            "goal": _safe_text(goal_text, 800),
            "goal_hash": gh,
            "goal_type": result["goal_type"],
            "no_progress_count": count,
            "no_progress_limit": limit,
        }
        record = trigger_safe_halt(
            state, policy, "NO_PROGRESS",
            f"连续 {count} 次 REWORK 无进展（limit={limit}）：NO_PROGRESS 计数器超限",
            context, state_path)
        result["verdict"] = "SAFE_HALT"
        result["ok"] = False
        result["safe_halt"] = record
        result["frozen"] = True
        result["recovery"] = record.get("recovery", "")
    save_state(state, state_path)
    return result


def do_safe_halt_manual(goal_text: str, reason_detail: str, policy: Dict[str, Any],
                        state: Dict[str, Any],
                        state_path: Optional[str] = None) -> Dict[str, Any]:
    """受控/手动触发 SAFE_HALT（MANUAL，L2 实测通道；不猜原因）。"""
    gh = goal_hash(goal_text)
    context = {
        "goal": _safe_text(goal_text, 800),
        "goal_hash": gh,
        "goal_type": classify_goal(goal_text, policy),
    }
    record = trigger_safe_halt(state, policy, "MANUAL",
                               _safe_text(reason_detail or "人工受控触发（L2 实测）", 800),
                               context, state_path)
    return {
        "schema": SCHEMA, "command": "safe-halt", "ok": False,
        "verdict": "SAFE_HALT", "goal": _safe_text(goal_text, 800),
        "goal_hash": gh, "safe_halt": record, "frozen": True,
        "recovery": record.get("recovery", ""), "non_authority": True,
    }


def do_status(state: Dict[str, Any], state_path: Optional[str] = None) -> Dict[str, Any]:
    """当前熔断状态快照（含冻结任务与历史记录数）。"""
    frozen = state.get("frozen_tasks", {}) or {}
    return {
        "schema": SCHEMA, "command": "status", "ok": True,
        "status": state.get("status", "FREE"),
        "tripped": bool(state.get("tripped", False)),
        "no_progress": state.get("no_progress", {}) or {},
        "consecutive_breach": int(state.get("consecutive_breach", 0)),
        "frozen_count": len(frozen),
        "frozen_tasks": [
            {
                "goal_hash": gh,
                "reason": rec.get("reason"),
                "triggered_at": rec.get("triggered_at"),
                "record_id": rec.get("record_id"),
            }
            for gh, rec in frozen.items()
        ],
        "history_count": len(state.get("history", []) or []),
        "state_file": str(Path(state_path) if state_path else (_repo_root() / _DEFAULT_STATE)),
        "non_authority": True,
    }


def do_reset(state: Dict[str, Any], goal_text: Optional[str],
             state_path: Optional[str] = None) -> Dict[str, Any]:
    """人工审查后解冻：--goal 指定只解冻该任务；否则解冻全部（保留 history 证据）。"""
    frozen = state.get("frozen_tasks", {}) or {}
    if goal_text:
        gh = goal_hash(goal_text)
        removed = frozen.pop(gh, None)
        state.setdefault("no_progress", {}).pop(gh, None)
        detail = (f"任务 {gh} 已解冻" if removed else f"任务 {gh} 未处于冻结态（无操作）")
    else:
        removed_count = len(frozen)
        frozen.clear()
        state.setdefault("no_progress", {}).clear()
        detail = f"全部 {removed_count} 个冻结任务已解冻"
    state["consecutive_breach"] = 0
    state["status"] = "SAFE_HALT" if frozen else "FREE"
    state["tripped"] = bool(frozen)
    save_state(state, state_path)
    return {
        "schema": SCHEMA, "command": "reset", "ok": True,
        "detail": detail,
        "status": state["status"], "tripped": state["tripped"],
        "frozen_count": len(frozen),
        "history_count": len(state.get("history", []) or []),
        "note": "SAFE_HALT 历史记录保留（证据留存）；reset 只解冻，不删除记录。",
        "non_authority": True,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _load_inputs(args: argparse.Namespace):
    """加载 policy + registry + state；配置错误抛 ValueError。"""
    policy = load_policy(args.policy or None)
    registry_costs = load_registry_costs(args.registry or None)
    state = load_state(args.state or None)
    return policy, registry_costs, state


def _print(result: Dict[str, Any]) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _exit_code(result: Dict[str, Any]) -> int:
    """0=成功；1=配置/输入错误；2=硬停（SAFE_HALT/BLOCKED/FROZEN）。"""
    if result.get("ok"):
        return EXIT_OK
    verdict = str(result.get("verdict", ""))
    if verdict in ("SAFE_HALT", "BLOCKED", "FROZEN", "UNDETERMINED"):
        return EXIT_HARD_STOP
    return EXIT_CONFIG_ERROR


def cmd_route(args: argparse.Namespace) -> int:
    try:
        policy, registry_costs, state = _load_inputs(args)
    except (FileNotFoundError, ValueError) as e:
        _print({"schema": SCHEMA, "command": "route", "ok": False,
                "error": "CONFIG_ERROR", "detail": _safe_text(e, 600)})
        return EXIT_CONFIG_ERROR
    result = do_route(args.goal, args.rework_risk, args.tokens_est, args.max_cost,
                      policy, registry_costs, state, args.state or None)
    _print(result)
    return _exit_code(result)


def cmd_budget(args: argparse.Namespace) -> int:
    try:
        policy, registry_costs, state = _load_inputs(args)
    except (FileNotFoundError, ValueError) as e:
        _print({"schema": SCHEMA, "command": "budget", "ok": False,
                "error": "CONFIG_ERROR", "detail": _safe_text(e, 600)})
        return EXIT_CONFIG_ERROR
    result = do_budget(args.goal, args.max_cost, args.rework_risk, args.tokens_est,
                       policy, registry_costs, state, args.state or None)
    _print(result)
    return _exit_code(result)


def cmd_safe_halt(args: argparse.Namespace) -> int:
    try:
        policy, _, state = _load_inputs(args)
    except (FileNotFoundError, ValueError) as e:
        _print({"schema": SCHEMA, "command": "safe-halt", "ok": False,
                "error": "CONFIG_ERROR", "detail": _safe_text(e, 600)})
        return EXIT_CONFIG_ERROR
    result = do_safe_halt_manual(args.goal, args.reason_detail or "",
                                 policy, state, args.state or None)
    _print(result)
    return EXIT_HARD_STOP


def cmd_simulate_rework(args: argparse.Namespace) -> int:
    try:
        policy, _, state = _load_inputs(args)
    except (FileNotFoundError, ValueError) as e:
        _print({"schema": SCHEMA, "command": "simulate-rework", "ok": False,
                "error": "CONFIG_ERROR", "detail": _safe_text(e, 600)})
        return EXIT_CONFIG_ERROR
    result = do_simulate_rework(args.goal, args.cycles, args.no_progress_limit,
                                policy, state, args.state or None)
    _print(result)
    return _exit_code(result)


def cmd_status(args: argparse.Namespace) -> int:
    try:
        _, _, state = _load_inputs(args)
    except (FileNotFoundError, ValueError) as e:
        _print({"schema": SCHEMA, "command": "status", "ok": False,
                "error": "CONFIG_ERROR", "detail": _safe_text(e, 600)})
        return EXIT_CONFIG_ERROR
    _print(do_status(state, args.state or None))
    return EXIT_OK


def cmd_reset(args: argparse.Namespace) -> int:
    try:
        _, _, state = _load_inputs(args)
    except (FileNotFoundError, ValueError) as e:
        _print({"schema": SCHEMA, "command": "reset", "ok": False,
                "error": "CONFIG_ERROR", "detail": _safe_text(e, 600)})
        return EXIT_CONFIG_ERROR
    _print(do_reset(state, args.goal or None, args.state or None))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="CostRouter: Expected Total Cost 路由 + SAFE_HALT 安全熔断（宪法 §2/§59/§61）")
    sub = ap.add_subparsers(dest="command", required=True)

    def add_common(p, need_max_cost: bool = False) -> None:
        p.add_argument("--goal", dest="goal", required=True,
                       help="任务简述或类型（如 'high-risk 生产发布' / '机械读取任务'）")
        p.add_argument("--rework-risk", dest="rework_risk", default="mid",
                       choices=("low", "mid", "high"),
                       help="REWORK 风险档（默认 mid）")
        p.add_argument("--tokens-est", dest="tokens_est", type=int, default=None,
                       help="任务预估 token 量（默认 cost_policy.json tokens_est_default=2000）")
        if need_max_cost:
            p.add_argument("--max-cost", dest="max_cost", type=float, default=None,
                           help="预算阈值（元）；缺省取 cost_policy.json budget.default_budget_threshold")
        p.add_argument("--policy", dest="policy", default="",
                       help="cost_policy.json 路径（默认 config/cost_policy.json）")
        p.add_argument("--registry", dest="registry", default="",
                       help="capability-registry.json 路径（默认 config/capability-registry.json）")
        p.add_argument("--state", dest="state", default="",
                       help="熔断状态文件路径（默认 state/cost_router_state.json）")

    p_route = sub.add_parser("route", help="Expected Total Cost 路由：成本分解 + 推荐路由 + 预算熔断")
    add_common(p_route, need_max_cost=True)

    p_budget = sub.add_parser("budget", help="预算熔断检查：ETC 超阈值 -> BLOCKED（SAFE_HALT 建议）")
    add_common(p_budget, need_max_cost=True)

    p_safe = sub.add_parser("safe-halt", help="受控/手动触发 SAFE_HALT（L2 实测通道）")
    add_common(p_safe, need_max_cost=False)
    p_safe.add_argument("--reason-detail", dest="reason_detail", default="",
                        help="触发原因说明（默认：人工受控触发）")

    p_sim = sub.add_parser("simulate-rework", help="NO_PROGRESS 场景：连续 REWORK 无进展 -> 熔断")
    add_common(p_sim, need_max_cost=False)
    p_sim.add_argument("--cycles", dest="cycles", type=int, default=1,
                       help="本次追加的连续 REWORK 轮数（默认 1）")
    p_sim.add_argument("--no-progress-limit", dest="no_progress_limit", type=int, default=None,
                       help="NO_PROGRESS 上限（默认 cost_policy.json circuit_breaker.no_progress_limit=3）")

    p_status = sub.add_parser("status", help="当前熔断状态快照")
    p_status.add_argument("--policy", dest="policy", default="")
    p_status.add_argument("--registry", dest="registry", default="")
    p_status.add_argument("--state", dest="state", default="")

    p_reset = sub.add_parser("reset", help="人工审查后解冻（可指定 --goal 只解冻该任务）")
    p_reset.add_argument("--goal", dest="goal", default="",
                         help="只解冻该任务；缺省解冻全部")
    p_reset.add_argument("--policy", dest="policy", default="")
    p_reset.add_argument("--registry", dest="registry", default="")
    p_reset.add_argument("--state", dest="state", default="")
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    # 控制台统一 UTF-8 输出，避免 GBK console UnicodeEncodeError
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    ap = build_parser()
    args = ap.parse_args(argv)
    handlers = {
        "route": cmd_route,
        "budget": cmd_budget,
        "safe-halt": cmd_safe_halt,
        "simulate-rework": cmd_simulate_rework,
        "status": cmd_status,
        "reset": cmd_reset,
    }
    handler = handlers.get(args.command)
    if handler is None:
        ap.print_help()
        return EXIT_CONFIG_ERROR
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
