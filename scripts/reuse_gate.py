"""Reuse Gate — §48-51 Reuse 门禁工具化（v1.1-blackbox D3，S3 文件域）。

背景：§48-51 要求先搜 GitHub 现成方案（Reuse>Adapt>Compose>Build），
Decision 留痕，禁止重复造轮子。R1 起流程已人工走过但无系统级强制；
本工具把门禁机械化：

  - check : 执行四步流程——①本地已有方案搜索（capability-registry.json 的
            tools/capabilities 节 + docs/FAILED_APPROACH_LEDGER.md 已失败路线账本）
            ②GitHub 搜索（优先 gh CLI；无 gh 时输出搜索指引供调用方用 WebSearch）
            ③给出判定 Reuse>Adapt>Compose>Build + 理由 + Decision 记录模板
            ④（--require-decision）若该任务无对应 Decision 记录 -> BUILD_BLOCKED
            （退出码 1，强制"无 Decision 不得 BUILD"）
  - record: 生成结构化 Decision 留痕，追加到 docs/evidence/reuse-decisions.ndjson，
            供主理人汇总入 DECISION_LEDGER。

用法（独立 CLI，仿 blackbox_bridge / cost_router 模式；JSON 输出/退出码 0/1/2）：
    python scripts/reuse_gate.py check --task "守护层看门狗" --search watchdog keepalive
    python scripts/reuse_gate.py check --task "守护层看门狗" --require-decision
    python scripts/reuse_gate.py record --task "守护层看门狗" --decision compose \
            --evidence "docs/DECISION_LEDGER.md#D022" --note "复用 schtasks+端口探活"

红线：
  1) 本工具只做判定与留痕，不代主理人写 DECISION_LEDGER（Decision 汇总由主理人统一）；
  2) 输出为 inert 数据（non_authority）；BUILD_BLOCKED 是机械门禁，不是审查判决；
  3) 不改 src/aicontrol/、config/production.json、runtime/runtime.py、
     config/capability-registry.json（只读衔接）；凭据不入仓。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "v1.1-d3-reuse-gate"
RECORD_SCHEMA = "v1.1-d3-reuse-decision"

REUSE_LEVELS = ("reuse", "adapt", "compose", "build")
# 判定优先级（数字越小越优先，符合 §48 Reuse>Adapt>Compose>Build 顺序）
LEVEL_PRIORITY = {"reuse": 1, "adapt": 2, "compose": 3, "build": 4}

# 项目根（本文件位于 <root>/scripts/ 下）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = PROJECT_ROOT / "config" / "capability-registry.json"
DEFAULT_FAILED_LEDGER = PROJECT_ROOT / "docs" / "FAILED_APPROACH_LEDGER.md"
DEFAULT_DECISIONS = PROJECT_ROOT / "docs" / "evidence" / "reuse-decisions.ndjson"

# 关键词提取时剔除的停用词（中英；保持小写）
_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "task", "一个", "实现",
    "开发", "系统", "任务", "进行", "使用", "需要", "以及", "或者", "相关", "本次",
}


def _safe_text(value: Any, limit: int = 2000) -> str:
    """任意值 -> 干净 str，限长，剔除不可打印控制符。"""
    if value is None:
        return ""
    text = str(value)
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return text[:limit]


def _now_iso() -> str:
    """当前 UTC ISO 时间（留痕用）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize(text: str) -> str:
    """空白归一 + 去首尾。"""
    return re.sub(r"\s+", " ", _safe_text(text, 4000)).strip().lower()


def _extract_keywords(text: str) -> List[str]:
    """从描述中提取显著关键词（中英）。

    规则：连续 CJK 片段（长度>=2）整体作为一词；ASCII 词（长度>=3）去停用词。
    返回去重小写列表。
    """
    if not text:
        return []
    norm = _normalize(text)
    tokens: List[str] = []
    # CJK 片段（>=2 字）
    for seg in re.findall(r"[\u4e00-\u9fff]{2,}", norm):
        tokens.append(seg)
    # ASCII 词（>=3 字母），排除停用词
    for w in re.findall(r"[a-z][a-z0-9-]{2,}", norm):
        if w not in _STOPWORDS:
            tokens.append(w)
    # 去重（保序）
    seen: set[str] = set()
    out: List[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


# ---------------------------------------------------------------------------
# 本地已有方案搜索（capability-registry + FAILED_APPROACH_LEDGER）
# ---------------------------------------------------------------------------
def load_registry(path: Optional[Path] = None) -> Dict[str, Any]:
    """读取 capability-registry.json（只读；不存在/损坏时返回空字典+警告）。"""
    p = Path(path) if path is not None else DEFAULT_REGISTRY
    if not p.exists():
        return {"_warning": f"registry not found: {p}"}
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(data, dict):
            return {"_warning": f"registry not a dict: {p}"}
        return data
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        return {"_warning": f"registry unreadable: {p} ({e})"}


def search_local_registry(registry: Dict[str, Any],
                          keywords: List[str]) -> List[Dict[str, Any]]:
    """在注册表 tools / capabilities / browsers 节中按关键词匹配已有方案。

    返回命中项列表（每项含 id/name/type/status/note）。
    """
    hits: List[Dict[str, Any]] = []
    sections = registry.get("sections", {}) if isinstance(registry, dict) else {}
    for sec_name in ("tools", "capabilities", "browsers", "adapters"):
        items = sections.get(sec_name, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            hay = " ".join([
                _safe_text(item.get("id"), 200),
                _safe_text(item.get("name"), 200),
                _safe_text(item.get("type"), 100),
                _safe_text(item.get("note"), 400),
                _safe_text(item.get("source"), 300),
            ]).lower()
            if not keywords:
                continue
            matched = [k for k in keywords if k in hay]
            if matched:
                hits.append({
                    "id": _safe_text(item.get("id"), 120),
                    "name": _safe_text(item.get("name"), 200),
                    "type": _safe_text(item.get("type"), 100),
                    "status": _safe_text(item.get("status"), 40),
                    "matched_keywords": matched,
                    "source": _safe_text(item.get("source"), 300),
                    "note": _safe_text(item.get("note"), 400),
                })
    return hits


def load_failed_approaches(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """解析 FAILED_APPROACH_LEDGER.md 的 F 系列条目。

    机械规则：`## F` 加数字开头为新条目；捕获 why_failed / do_not_retry_unless /
    status 键（`- key: value`）；条目文本参与关键词匹配。
    """
    p = Path(path) if path is not None else DEFAULT_FAILED_LEDGER
    if not p.exists():
        return []
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    entries: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    cur_lines: List[str] = []
    for line in text.splitlines():
        m = re.match(r"^##\s+(F\d+)\s*[-—–]\s*(.*)$", line.strip())
        if m:
            if cur is not None:
                cur["_text"] = " ".join(cur_lines).lower()
                entries.append(cur)
            cur = {"id": m.group(1), "title": _safe_text(m.group(2), 300),
                   "why_failed": "", "do_not_retry_unless": "", "status": "",
                   "_text": ""}
            cur_lines = [line]
            continue
        if cur is not None:
            cur_lines.append(line)
            km = re.match(r"^-\s*([a-z_]+)\s*:\s*(.*)$", line.strip())
            if km:
                key = km.group(1).strip()
                if key in ("why_failed", "do_not_retry_unless", "status"):
                    cur[key] = _safe_text(km.group(2).strip(), 600)
    if cur is not None:
        cur["_text"] = " ".join(cur_lines).lower()
        entries.append(cur)
    return entries


def search_failed_approaches(failed: List[Dict[str, Any]],
                             keywords: List[str]) -> List[Dict[str, Any]]:
    """检查已失败路线是否覆盖本次任务关键词。

    命中返回条目 id/title/status/do_not_retry_unless（避免重新发明失败方案）。
    """
    hits: List[Dict[str, Any]] = []
    for entry in failed:
        if not keywords:
            continue
        hay = (entry.get("_text") or "") + " " + (entry.get("title") or "").lower()
        matched = [k for k in keywords if k in hay]
        if matched:
            hits.append({
                "id": entry.get("id"),
                "title": entry.get("title"),
                "status": entry.get("status"),
                "why_failed": entry.get("why_failed"),
                "do_not_retry_unless": entry.get("do_not_retry_unless"),
                "matched_keywords": matched,
            })
    return hits


# ---------------------------------------------------------------------------
# GitHub 搜索（gh CLI 优先；无 gh 时输出搜索指引）
# ---------------------------------------------------------------------------
def try_gh_search(keywords: List[str], timeout: int = 30) -> Dict[str, Any]:
    """尝试用 gh CLI 搜 GitHub 仓库/代码（只读，不创建任何东西）。

    返回 {"ok": bool, "results": [...], "detail": str}。gh 不存在或失败时
    ok=False，调用方应回退到搜索指引。
    """
    gh = shutil.which("gh")
    if not gh:
        return {"ok": False, "detail": "gh CLI not found", "results": []}
    query = " ".join(keywords[:6]) or "python"
    try:
        proc = subprocess.run(
            [gh, "search", "repos", query, "--limit", "8", "--json",
             "fullName,description,stargazersCount,htmlUrl"],
            capture_output=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"ok": False, "detail": f"gh search failed: {_safe_text(e, 300)}",
                "results": []}
    if proc.returncode != 0:
        return {"ok": False,
                "detail": f"gh search exit={proc.returncode}: "
                          f"{_safe_text(proc.stderr, 300)}",
                "results": []}
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return {"ok": False, "detail": "gh search output unparseable",
                "results": []}
    results = []
    for item in data if isinstance(data, list) else []:
        results.append({
            "repo": _safe_text(item.get("fullName"), 200),
            "description": _safe_text(item.get("description"), 400),
            "stars": item.get("stargazersCount"),
            "url": _safe_text(item.get("htmlUrl"), 300),
        })
    return {"ok": True, "detail": f"gh search repos returned {len(results)} hits",
            "results": results}


def build_search_guidance(keywords: List[str]) -> Dict[str, Any]:
    """生成 GitHub/WebSearch 搜索指引（gh 不可用时输出给调用方 AI 执行）。

    返回包含推荐关键词、GitHub 搜索 URL、WebSearch 建议查询。
    """
    joined = " ".join(keywords[:6]) if keywords else "<关键词>"
    quoted = " ".join(f'"{k}"' for k in keywords[:6]) if keywords else '"<关键词>"'
    return {
        "engine": "github + websearch",
        "recommended_keywords": keywords[:6],
        "github_search_url": (
            "https://github.com/search?q=" +
            "+".join(keywords[:6]) if keywords else "https://github.com/search?q="
        ),
        "github_repo_search_url": (
            "https://github.com/search?q=" + "+".join(keywords[:6]) +
            "&type=repositories" if keywords else "https://github.com/search"
        ),
        "websearch_suggestion": f"GitHub 现成方案 {joined}",
        "note": ("调用方（弱 AI）应使用 WebSearch 按上述关键词实测搜索；"
                 "搜索结果与判定理由一并写入 Decision 留痕。"),
        "examples": [
            f"gh search repos {joined} --limit 8",
            f"gh search code {joined} --limit 8",
        ],
    }


# ---------------------------------------------------------------------------
# Decision 留痕（ndjson）
# ---------------------------------------------------------------------------
def load_decisions(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """读取 reuse-decisions.ndjson（每行一个 JSON 对象）。"""
    p = Path(path) if path is not None else DEFAULT_DECISIONS
    if not p.exists():
        return []
    decisions: List[Dict[str, Any]] = []
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                decisions.append(obj)
    except OSError:
        return []
    return decisions


def append_decision(record: Dict[str, Any],
                    path: Optional[Path] = None) -> Path:
    """把一条 Decision 记录以 ndjson 追加到留痕文件（原子写：先写临时文件再 rename）。"""
    p = Path(path) if path is not None else DEFAULT_DECISIONS
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    # 追加语义：tmp 只含新记录；若目标已存在则先合并
    if p.exists():
        combined = p.read_text(encoding="utf-8", errors="replace") + \
            tmp.read_text(encoding="utf-8", errors="replace")
        tmp.write_text(combined, encoding="utf-8")
    tmp.replace(p)
    return p


def decision_covers(decision: Dict[str, Any], task: str) -> bool:
    """判定一条 Decision 是否覆盖本次任务（门禁用，机械规则不猜）。

    覆盖条件（满足任一）：
      1) 精确匹配：decision.task 归一化后等于 task 归一化；
      2) 关键词重叠：decision.task 与 task 共享 >=1 个显著关键词。
    """
    task_norm = _normalize(task)
    if not task_norm:
        return False
    dec_task = _normalize(decision.get("task") or "")
    if dec_task and dec_task == task_norm:
        return True
    task_keys = set(_extract_keywords(task))
    dec_keys = set(_extract_keywords(decision.get("task") or ""))
    return bool(task_keys & dec_keys)


def find_covering_decisions(decisions: List[Dict[str, Any]],
                            task: str) -> List[Dict[str, Any]]:
    """返回覆盖本次 task 的全部 Decision 记录（含匹配方式说明）。"""
    hits: List[Dict[str, Any]] = []
    task_norm = _normalize(task)
    task_keys = set(_extract_keywords(task))
    for d in decisions:
        dec_task = _normalize(d.get("task") or "")
        exact = bool(dec_task) and dec_task == task_norm
        shared = list(task_keys & set(_extract_keywords(dec_task)))
        if exact or shared:
            copy = dict(d)
            copy["_match"] = {"exact": exact, "shared_keywords": shared[:8]}
            hits.append(copy)
    return hits


def _gate_verdict(covers: List[Dict[str, Any]], require: bool) -> str:
    """门禁判定：require 且无覆盖 -> BUILD_BLOCKED；否则 GATE_OK。"""
    if require and not covers:
        return "BUILD_BLOCKED"
    return "GATE_OK"


# ---------------------------------------------------------------------------
# check 主流程
# ---------------------------------------------------------------------------
def cmd_check(args: argparse.Namespace) -> int:
    """执行 Reuse 门禁四步流程，输出判定 + Decision 模板（或 BUILD_BLOCKED）。"""
    task = _safe_text(args.task, 2000).strip()
    if not task:
        print(json.dumps({"schema": SCHEMA, "command": "check", "ok": False,
                          "error": "TASK_REQUIRED",
                          "instruction": "--task 不能为空。"},
                         ensure_ascii=False, indent=2))
        return 2
    # 关键词 = --search 显式提供 + 从 task 自动提取（合并去重）
    keywords: List[str] = []
    for group in (args.search or []):
        for piece in (group if isinstance(group, list) else [group]):
            for token in str(piece).replace(",", " ").split():
                token = token.strip().lower()
                if len(token) >= 2 and token not in keywords:
                    keywords.append(token)
    for kw in _extract_keywords(task):
        if kw not in keywords:
            keywords.append(kw)
    keywords = keywords[:12]

    # ① 本地已有方案搜索
    registry = load_registry(Path(args.registry) if args.registry else None)
    local_hits = search_local_registry(registry, keywords)
    failed = load_failed_approaches(Path(args.failed_ledger) if args.failed_ledger
                                    else None)
    failed_hits = search_failed_approaches(failed, keywords)

    # ② GitHub 搜索（gh 优先；无 gh 给指引）
    gh_result = try_gh_search(keywords)
    if gh_result.get("ok"):
        github = {"status": "SEARCHED", "detail": gh_result.get("detail"),
                  "results": gh_result.get("results", []),
                  "guidance": None}
    else:
        github = {"status": "GUIDANCE_ONLY", "detail": gh_result.get("detail"),
                  "results": [],
                  "guidance": build_search_guidance(keywords)}

    # ③ 判定（机械规则，可解释）：
    #    - 本地已有同能力官方工具  -> Reuse
    #    - gh 命中高星现成方案     -> 建议 Adapt（需人工复核）
    #    - 有可组合既有组件        -> Compose
    #    - 无现成且无组件可组      -> Build
    reasons: List[str] = []
    verdict = "build"
    if local_hits:
        verdict = "reuse"
        reasons.append(f"本地 capability-registry 命中 {len(local_hits)} 项已有能力"
                       f"（首个：{local_hits[0].get('id')}）→ 应优先 Reuse")
    if gh_result.get("ok") and gh_result.get("results"):
        top = gh_result["results"][0]
        if verdict == "build":
            verdict = "adapt"
        reasons.append(f"GitHub 命中现成方案（最高星：{top.get('repo')} "
                       f"stars={top.get('stars')}）→ 至少 Adapt，需人工复核是否可接入")
    if not reasons:
        reasons.append("本地注册表无命中、GitHub 无直接可接入组件 → Build（自研，"
                       "须先走完本门禁并留痕）")
    else:
        reasons.append("判定取最优先的可行级别（Reuse>Adapt>Compose>Build），"
                       "最终 Decision 由执行方按证据裁定并 record")

    # ④ 门禁：--require-decision
    decisions = load_decisions(Path(args.decisions) if args.decisions else None)
    covers = find_covering_decisions(decisions, task)
    gate = _gate_verdict(covers, require=args.require_decision)

    # Decision 记录模板（供 record 命令使用）
    template = {
        "schema": RECORD_SCHEMA,
        "decision_id": f"D3-{uuid.uuid4().hex[:8].upper()}",
        "recorded_at": _now_iso(),
        "task": task,
        "decision": verdict,
        "evidence": "",
        "note": "",
        "gate_check_summary": {
            "local_hits": len(local_hits),
            "github_hits": len(gh_result.get("results", [])),
            "failed_approach_hits": len(failed_hits),
        },
    }

    result = {
        "schema": SCHEMA, "command": "check", "ok": True,
        "task": task,
        "keywords": keywords,
        "steps": {
            "local_registry_search": {
                "registry_path": str(Path(args.registry) if args.registry
                                     else DEFAULT_REGISTRY),
                "hits": local_hits[:10],
                "hit_count": len(local_hits),
            },
            "failed_approach_ledger": {
                "ledger_path": str(Path(args.failed_ledger) if args.failed_ledger
                                   else DEFAULT_FAILED_LEDGER),
                "hits": failed_hits[:10],
                "hit_count": len(failed_hits),
                "warning": ("本次任务关键词命中了已失败路线！重新实现前必须满足其 "
                            "do_not_retry_unless 条件，否则属于重复发明失败方案。"
                            if failed_hits else None),
            },
            "github_search": github,
        },
        "verdict": {
            "level": verdict,
            "priority": LEVEL_PRIORITY.get(verdict, 9),
            "reason": "；".join(reasons),
        },
        "gate": {
            "require_decision": bool(args.require_decision),
            "status": gate,
            "covering_decisions": covers[:10],
            "covering_count": len(covers),
            "instruction": (
                "该任务已有 Decision 留痕，门禁通过。"
                if covers else
                "该任务无对应 Decision 记录：先执行 record 完成留痕，"
                "再进入 BUILD。"
            ),
        },
        "decision_template": template,
        "record_command": (
            f'python scripts/reuse_gate.py record --task "{task}" '
            f'--decision {verdict} --evidence "<URL或路径>" '
            f'[--note "理由"]'
        ),
        "non_authority": True,
        "note": "Reuse 门禁是机械判定+留痕；BUILD_BLOCKED 仅表示缺 Decision 记录，"
                "不代行审查。最终 Decision 汇总入 DECISION_LEDGER 由主理人统一写。",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if gate == "BUILD_BLOCKED":
        return 1
    return 0


# ---------------------------------------------------------------------------
# record 命令
# ---------------------------------------------------------------------------
def cmd_record(args: argparse.Namespace) -> int:
    """生成结构化 Decision 留痕，追加到 docs/evidence/reuse-decisions.ndjson。"""
    task = _safe_text(args.task, 2000).strip()
    decision = (args.decision or "").strip().lower()
    evidence = _safe_text(args.evidence, 2000).strip()
    if not task:
        print(json.dumps({"schema": SCHEMA, "command": "record", "ok": False,
                          "error": "TASK_REQUIRED", "instruction": "--task 不能为空。"},
                         ensure_ascii=False, indent=2))
        return 2
    if decision not in REUSE_LEVELS:
        print(json.dumps({"schema": SCHEMA, "command": "record", "ok": False,
                          "error": "BAD_DECISION",
                          "detail": f"decision 必须是 {'|'.join(REUSE_LEVELS)}",
                          "instruction": f"重新指定 --decision {'|'.join(REUSE_LEVELS)}"},
                         ensure_ascii=False, indent=2))
        return 2
    if not evidence:
        print(json.dumps({"schema": SCHEMA, "command": "record", "ok": False,
                          "error": "EVIDENCE_REQUIRED",
                          "instruction": "--evidence 必须提供 URL 或本地路径。"},
                         ensure_ascii=False, indent=2))
        return 2

    decisions_path = Path(args.decisions) if args.decisions else DEFAULT_DECISIONS

    # 已失败路线衔接：若本次决策落入已失败路线，给出警告但不阻止（留痕为主）
    failed = load_failed_approaches(Path(args.failed_ledger) if args.failed_ledger
                                    else None)
    keywords = _extract_keywords(task)
    failed_hits = search_failed_approaches(failed, keywords)

    record = {
        "schema": RECORD_SCHEMA,
        "decision_id": f"D3-{uuid.uuid4().hex[:8].upper()}",
        "recorded_at": _now_iso(),
        "task": task,
        "decision": decision,
        "evidence": evidence,
        "note": _safe_text(args.note, 2000) if args.note else "",
        "gate_check_summary": {
            "local_hits": None,
            "github_hits": None,
            "failed_approach_hits": len(failed_hits),
        },
        "failed_approach_warning": (
            [{"id": h.get("id"), "title": h.get("title"),
              "do_not_retry_unless": h.get("do_not_retry_unless")}
             for h in failed_hits[:5]] or None
        ),
        "non_authority": True,
        "note_meta": "本记录供主理人汇总入 DECISION_LEDGER；主理人统一写正式 Decision。",
    }
    try:
        target = append_decision(record, decisions_path)
    except OSError as e:
        print(json.dumps({"schema": SCHEMA, "command": "record", "ok": False,
                          "error": "WRITE_FAILED", "detail": _safe_text(e, 400),
                          "instruction": "留痕文件写入失败；检查路径权限。"},
                         ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({
        "schema": SCHEMA, "command": "record", "ok": True,
        "decision": record,
        "decisions_file": str(target),
        "instruction": "Decision 已留痕。请主理人据此汇总入 docs/DECISION_LEDGER.md。",
    }, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# 辅助子命令：list（查看已有留痕，供门禁核对）
# ---------------------------------------------------------------------------
def cmd_list(args: argparse.Namespace) -> int:
    """列出已有 Decision 留痕（机械只读）。"""
    decisions = load_decisions(Path(args.decisions) if args.decisions else None)
    if args.task:
        covers = find_covering_decisions(decisions, args.task)
        print(json.dumps({
            "schema": SCHEMA, "command": "list", "ok": True,
            "task": args.task, "covering_count": len(covers),
            "covering": covers[:20],
            "decisions_file": str(Path(args.decisions) if args.decisions
                                  else DEFAULT_DECISIONS),
            "non_authority": True,
        }, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps({
        "schema": SCHEMA, "command": "list", "ok": True,
        "decision_count": len(decisions),
        "decisions": decisions[-50:],
        "decisions_file": str(Path(args.decisions) if args.decisions
                              else DEFAULT_DECISIONS),
        "non_authority": True,
    }, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Reuse Gate: §48-51 Reuse 门禁工具化（check/record/list）")
    sub = ap.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="四步流程：本地搜索+GitHub搜索+判定+门禁")
    p_check.add_argument("--task", dest="task", required=True,
                         help="任务描述（必填）")
    p_check.add_argument("--search", dest="search", action="append", nargs="+",
                         default=[],
                         help="显式搜索关键词（可多个/多次；缺省从 task 自动提取）")
    p_check.add_argument("--require-decision", dest="require_decision",
                         action="store_true",
                         help="门禁模式：无 Decision 记录 -> BUILD_BLOCKED(exit 1)")
    p_check.add_argument("--registry", dest="registry", default="",
                         help="capability-registry.json 路径（默认 config/ 下）")
    p_check.add_argument("--failed-ledger", dest="failed_ledger", default="",
                         help="FAILED_APPROACH_LEDGER.md 路径（默认 docs/ 下）")
    p_check.add_argument("--decisions", dest="decisions", default="",
                         help="reuse-decisions.ndjson 路径（默认 docs/evidence/ 下）")

    p_record = sub.add_parser("record", help="生成 Decision 留痕（追加 ndjson）")
    p_record.add_argument("--task", dest="task", required=True)
    p_record.add_argument("--decision", dest="decision", required=True,
                          choices=REUSE_LEVELS)
    p_record.add_argument("--evidence", dest="evidence", required=True,
                          help="证据 URL 或本地路径")
    p_record.add_argument("--note", dest="note", default="",
                          help="补充说明（可选）")
    p_record.add_argument("--failed-ledger", dest="failed_ledger", default="")
    p_record.add_argument("--decisions", dest="decisions", default="")

    p_list = sub.add_parser("list", help="列出已有 Decision 留痕（只读）")
    p_list.add_argument("--task", dest="task", default="",
                        help="可选：只看覆盖该 task 的 Decision")
    p_list.add_argument("--decisions", dest="decisions", default="")
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    # 控制台统一 UTF-8 输出，避免 GBK console UnicodeEncodeError
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.command == "check":
        return cmd_check(args)
    if args.command == "record":
        return cmd_record(args)
    if args.command == "list":
        return cmd_list(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
