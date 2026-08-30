"""Blackbox Bridge — 补齐 §65 唯一入口四动词（RESULT / HUMAN_GATE），非侵入。

生产黑盒 = E:\\WB\\tools\\ai-production-control\\runtime\\（run.cmd + runtime.py，
现役冻结，弱模型实测走它）。本模块是施工线 runtime/ 的只读查询桥：
不改生产 runtime.py 结构，不写任何 state，只把「RUN 状态根」机械投影为
弱 AI 可直接读懂的 RESULT / HUMAN_GATE 文档（§65 / §71）。

用法（独立 CLI，仿 brain_bridge / capsule_bridge 模式）：
    python blackbox_bridge.py result --run-id RUN-xxx
    python blackbox_bridge.py human-gate [--run-id RUN-xxx]
    python blackbox_bridge.py work   --goal-file <G> --r-url <URL>   # 委托给 run.cmd
    python blackbox_bridge.py report --run-id <ID> --message-file <F> # 委托给 run.cmd

四动词语义（§65）：
  SUBMIT TASK        -> work    （生产 runtime.py 既有，保留兼容）
  STATUS             -> status  （生产 runtime.py 既有，保留兼容）
  RESULT             -> result  （本桥新增：查最终结果 PASS/REWORK + 结论）
  RESPOND TO HUMAN GATE -> human-gate（本桥新增：列出等待人类介入的任务）

红线：
  1) 只读状态根；不写、不改任何 state / journal / reply 文件。
  2) 不碰 E:\\WB\\tools\\ai-production-control\\runtime\\ 生产文件结构。
  3) 输出为 inert 数据（non_authority）；任何 authority 词只作数据呈现，
     绝不代为执行。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

RESULT_SCHEMA = "v1.1-blackbox-result"
GATE_SCHEMA = "v1.1-blackbox-human-gate"
DELEGATE_SCHEMA = "v1.1-blackbox-delegate"

DEFAULT_STATE_ROOT = Path(r"E:\WB\state\ai-production-control\runtime-v1\runs")
CANONICAL_RUN_CMD = r"E:\WB\tools\ai-production-control\runtime\run.cmd"

# reply 文件中 R 审查方输出的机械标记（生产 runtime 强 AI 审查格式）
_VERDICT_RE = re.compile(r"^===REVIEW_VERDICT===\s*([A-Za-z_]+)\s*$", re.MULTILINE)
_MARKER_RE = re.compile(r"^===([A-Z0-9_]+)===\s*$", re.MULTILINE)

# HUMAN_GATE 判定：需要人类介入的状态（机械规则，不猜）
_GATE_STATUSES = ("HARD_BLOCKED", "PAUSED")
# 终态（用户已裁决，无需再介入；清单中单列，不计入 waiting）
_TERMINAL_STATUSES = ("STOPPED",)


def _safe_text(value: Any, limit: int = 4000) -> str:
    """任意值 -> 干净 str，限长，剔除不可打印控制符。"""
    if value is None:
        return ""
    text = str(value)
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return text[:limit]


def load_run_state(run_id: str, state_root: Optional[Path] = None) -> Dict[str, Any]:
    """读取 RUN 的 state.json（Runtime 的唯一恢复权威，只读）。"""
    root = Path(state_root) if state_root is not None else DEFAULT_STATE_ROOT
    state_file = root / run_id / "state.json"
    if not state_file.exists():
        raise FileNotFoundError(f"state.json not found: {state_file}")
    return json.loads(state_file.read_text(encoding="utf-8", errors="replace"))


def find_latest_reply(run_dir: Path) -> Optional[Path]:
    """在 RUN 目录中找最新一份 reply 文件（机械规则）。

    优先 `reply_epoch*_*.txt` / `requery_reply_*.txt`，按修改时间取最新。
    返回 None 表示该 RUN 还没有任何审查回复。
    """
    candidates: List[Path] = []
    for pattern in ("reply_epoch*_*.txt", "requery_reply_*.txt"):
        candidates.extend(run_dir.glob(pattern))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def parse_reply(text: str) -> Dict[str, Any]:
    """机械解析 R 审查 reply：verdict + 结论正文（尽力而为）。

    返回 {"verdict": str|None, "conclusion": str, "markers": [str]}。
    解析不到 verdict 时 verdict=None（不猜）。
    """
    m = _VERDICT_RE.search(text)
    verdict = m.group(1).strip().upper() if m else None
    # 结论正文 = NEXT_ACTION 段之后、下一个 ===XXX=== 标记之前
    body = ""
    markers = _MARKER_RE.findall(text)
    body_start = 0
    for marker_match in _MARKER_RE.finditer(text):
        if marker_match.group(1) in ("NEXT_ACTION", "REVIEW_VERDICT"):
            body_start = marker_match.end()
        else:
            break
    if body_start > 0:
        tail = text[body_start:]
        # 去掉结尾的 ===CHATGPT_DONE:...=== 及空行
        tail = re.sub(r"^===CHATGPT_DONE:.*$", "", tail, flags=re.MULTILINE)
        body = tail.strip()
    return {"verdict": verdict, "conclusion": body, "markers": markers}


def cmd_result(args: argparse.Namespace) -> int:
    """RESULT 动词：查询指定 run-id 的最终结果（§65）。

    从状态根读取 state.json + 最新 reply，输出结构化 PASS/REWORK + 结论。
    退出码：0=已读到审查结论；1=run 不存在；2=存在但尚无最终结论；3=状态损坏。
    """
    run_id = args.run_id
    root = Path(args.state_root) if args.state_root else DEFAULT_STATE_ROOT
    run_dir = root / run_id
    if not run_dir.exists():
        print(json.dumps({"schema": RESULT_SCHEMA, "command": "RESULT",
                          "ok": False, "error": "RUN_NOT_FOUND", "run_id": run_id,
                          "instruction": "RUN id 不存在；用 `status` 或问用户要正确的 RUN 号。"},
                         ensure_ascii=False, indent=2))
        return 1
    try:
        state = load_run_state(run_id, root)
    except FileNotFoundError as e:
        print(json.dumps({"schema": RESULT_SCHEMA, "command": "RESULT",
                          "ok": False, "error": "STATE_NOT_FOUND", "run_id": run_id,
                          "detail": str(e)}, ensure_ascii=False, indent=2))
        return 1
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        print(json.dumps({"schema": RESULT_SCHEMA, "command": "RESULT",
                          "ok": False, "error": "STATE_UNREADABLE", "run_id": run_id,
                          "detail": _safe_text(e, 400)}, ensure_ascii=False, indent=2))
        return 3

    status = _safe_text(state.get("status"), 64)
    verdict = state.get("last_r_verdict") or None
    reply_path: Optional[str] = state.get("last_reply_path")
    reply_text = ""
    if reply_path and Path(reply_path).exists():
        reply_text = Path(reply_path).read_text(encoding="utf-8", errors="replace")
    else:
        latest = find_latest_reply(run_dir)
        if latest is not None:
            reply_path = str(latest)
            reply_text = latest.read_text(encoding="utf-8", errors="replace")
    parsed = parse_reply(reply_text) if reply_text else {"verdict": None,
                                                         "conclusion": "",
                                                         "markers": []}
    # 权威 verdict 优先取 state（runtime 落盘为准）；reply 解析结果作为补充
    effective_verdict = verdict or parsed.get("verdict")
    if not effective_verdict:
        print(json.dumps({
            "schema": RESULT_SCHEMA, "command": "RESULT", "ok": True,
            "run_id": run_id, "status": status, "verdict": None,
            "final": False, "reply_path": reply_path,
            "conclusion": "",
            "instruction": "该 RUN 还没有审查结论（尚无 R 回复或仍在执行）。"
                           "先用 `report` 提交结果，再来查 RESULT。"},
            ensure_ascii=False, indent=2))
        return 2

    final = status in ("DONE", "STOPPED") or (
        effective_verdict == "PASS" and status == "DONE")
    if effective_verdict == "PASS" and status == "DONE":
        verdict_word = "PASS"
        user_line = "任务已通过。无需继续修改。"
    elif effective_verdict == "REWORK":
        verdict_word = "REWORK"
        user_line = "审查方要求返工：按结论中的要求修改后，重新 `report`。"
    elif effective_verdict == "BLOCKED":
        verdict_word = "BLOCKED"
        user_line = "审查方判定阻塞：需要人工介入，见 HUMAN_GATE 清单。"
    else:
        verdict_word = _safe_text(effective_verdict, 32)
        user_line = f"当前审查结论：{verdict_word}。"
    conclusion = parsed.get("conclusion") or _safe_text(state.get("last_r_next_action"), 4000)
    if args.max_conclusion and len(conclusion) > args.max_conclusion:
        conclusion = conclusion[: args.max_conclusion] + "…[截断]"

    print(json.dumps({
        "schema": RESULT_SCHEMA, "command": "RESULT", "ok": True,
        "run_id": run_id,
        "status": status,
        "verdict": verdict_word,
        "final": final,
        "reply_path": reply_path,
        "conclusion": conclusion,
        "goal": _safe_text(state.get("goal"), 300),
        "updated_at": _safe_text(state.get("updated_at"), 64),
        "user_line": user_line,
        "non_authority": True,
        "note": "RESULT 是状态根的机械投影；只有审查方 PASS 才算数，"
                "AI 不得自行宣布完成。"},
        ensure_ascii=False, indent=2))
    return 0


def _classify_run(run_dir: Path) -> Optional[Dict[str, Any]]:
    """机械判定单个 RUN 是否需要人类介入；返回清单项或 None。

    规则（只认 state.json 机械事实，不猜）：
      - HARD_BLOCKED / PAUSED            -> waiting（人类必须行动）
      - effect_human_gate_required=true  -> waiting
      - STOPPED                          -> terminal（用户已裁决，不计 waiting）
      - 其余（DONE/RUNNING）             -> 不需要介入
    """
    try:
        state = json.loads((run_dir / "state.json").read_text(
            encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return None
    run_id = _safe_text(state.get("run_id") or run_dir.name, 80)
    status = _safe_text(state.get("status"), 32)
    verdict = state.get("last_r_verdict") or None
    gate_flag = bool(state.get("effect_human_gate_required", False))
    if status in _TERMINAL_STATUSES:
        return {"run_id": run_id, "status": status, "verdict": verdict,
                "step": _safe_text(state.get("current_step"), 200),
                "need": "STOPPED（用户已裁决，终态，无需介入）",
                "updated_at": _safe_text(state.get("updated_at"), 64),
                "kind": "terminal"}
    if status in _GATE_STATUSES or gate_flag:
        reason = _safe_text(state.get("blocked_reason")) or \
            _safe_text(state.get("next_action"), 400)
        if status == "PAUSED":
            need = "PAUSED：等待人类 RESUME（`run.cmd directive --run-id %s RESUME`）。" % run_id
        elif gate_flag:
            need = "HUMAN_GATE 生效：该任务被效果安全闸门要求人工确认。"
        else:
            need = "HARD_BLOCKED：已停下，需要人类决策。原因：%s" % reason
        return {"run_id": run_id, "status": status, "verdict": verdict,
                "step": _safe_text(state.get("current_step"), 200),
                "need": need, "reason": reason,
                "updated_at": _safe_text(state.get("updated_at"), 64),
                "kind": "waiting"}
    return None


def cmd_human_gate(args: argparse.Namespace) -> int:
    """HUMAN_GATE 动词：列出当前需要人类介入的任务（§65 / §71）。"""
    root = Path(args.state_root) if args.state_root else DEFAULT_STATE_ROOT
    if not root.exists():
        print(json.dumps({"schema": GATE_SCHEMA, "command": "HUMAN_GATE",
                          "ok": False, "error": "STATE_ROOT_NOT_FOUND",
                          "state_root": str(root),
                          "instruction": "状态根不存在；请检查路径后重试。"},
                         ensure_ascii=False, indent=2))
        return 1

    if args.run_id:
        run_dir = root / args.run_id
        if not run_dir.exists():
            print(json.dumps({"schema": GATE_SCHEMA, "command": "HUMAN_GATE",
                              "ok": False, "error": "RUN_NOT_FOUND",
                              "run_id": args.run_id}, ensure_ascii=False, indent=2))
            return 1
        items = [x for x in (_classify_run(run_dir),) if x is not None]
    else:
        items = []
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            item = _classify_run(child)
            if item is not None:
                items.append(item)

    waiting = [x for x in items if x.get("kind") == "waiting"]
    terminal = [x for x in items if x.get("kind") == "terminal"]
    # 按 updated_at 倒序，最近的等待项在前
    waiting.sort(key=lambda x: str(x.get("updated_at", "")), reverse=True)

    if waiting:
        instruction = ("以下 RUN 需要人类介入：请把清单原样转发给用户；"
                       "用户决策后，用 `run.cmd directive --run-id <ID> "
                       "RESUME/STOP` 执行。")
    else:
        instruction = ("当前没有等待人类介入的任务。"
                       "（实测依据：已扫描 %d 个 RUN 状态根，无 HARD_BLOCKED/"
                       "PAUSED/effect_human_gate 等待项。）" % len(items))

    print(json.dumps({
        "schema": GATE_SCHEMA, "command": "HUMAN_GATE", "ok": True,
        "state_root": str(root),
        "total_scanned": (len(items) if args.run_id else
                          sum(1 for c in root.iterdir() if c.is_dir())),
        "waiting_count": len(waiting),
        "waiting": waiting,
        "terminal_count": len(terminal),
        "terminal": terminal if args.include_terminal else terminal[:0],
        "instruction": instruction,
        "non_authority": True,
        "note": "HUMAN_GATE 是状态根的机械投影；只读，不代行人类决策。"},
        ensure_ascii=False, indent=2))
    return 0


def _delegate(sub: str, args: argparse.Namespace) -> int:
    """work / report 兼容：不重实现，委托给生产 run.cmd（唯一正式入口）。

    纯只读 / 纯指引：本桥绝不执行 state-changing 命令。输出中的
    `executed: false` 明确表示"调用指引已生成，但命令尚未执行"，
    弱 AI 必须自行运行 invocation 字段中的命令（防误读为已执行，OBS-2）。
    work 的 --r-url 透传到 invocation；未提供时输出占位符并注明必须提供（D1）。
    """
    run_cmd = Path(args.run_cmd or CANONICAL_RUN_CMD)
    if run_cmd.exists():
        parts = [f'& "{run_cmd}"', sub]
        r_url = getattr(args, "r_url", "") or ""
        if getattr(args, "goal_file", None):
            parts.append(f"--goal-file {args.goal_file}")
        if sub == "work":
            if r_url:
                parts.append(f"--r-url {r_url}")
            else:
                parts.append("--r-url <R会话URL>")
        if getattr(args, "run_id", None):
            parts.append(f"--run-id {args.run_id}")
        if getattr(args, "message_file", None):
            parts.append(f"--message-file {args.message_file}")
        print(json.dumps({
            "schema": DELEGATE_SCHEMA, "command": sub.upper(), "ok": True,
            "executed": False,
            "r_url_provided": bool(r_url),
            "delegate": str(run_cmd),
            "invocation": " ".join(parts),
            "instruction": (f"{sub} 由生产 run.cmd 执行。本桥只生成调用指引、绝不代执行"
                            "（executed=false）；请先补齐全部必填参数，再自己运行 "
                            "invocation 字段中的命令。")},
            ensure_ascii=False, indent=2))
        return 0
    print(json.dumps({
        "schema": DELEGATE_SCHEMA, "command": sub.upper(), "ok": False,
        "executed": False,
        "error": "RUN_CMD_NOT_FOUND",
        "delegate": str(run_cmd),
        "instruction": f"{sub} 需通过生产 run.cmd 执行；当前环境未找到，"
                       "请报告用户，不要在本桥模拟执行。"},
        ensure_ascii=False, indent=2))
    return 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Blackbox Bridge: §65 四动词补齐（RESULT / HUMAN_GATE）+ work/report 委托")
    sub = ap.add_subparsers(dest="command", required=True)

    p_result = sub.add_parser("result", help="RESULT：查询 run 的最终结果")
    p_result.add_argument("--run-id", dest="run_id", required=True,
                          help="RUN id (e.g. RUN-20260818-173304-7350)")
    p_result.add_argument("--state-root", dest="state_root", default="",
                          help="optional state root override (read-only)")
    p_result.add_argument("--max-conclusion", dest="max_conclusion", type=int, default=4000,
                          help="truncate conclusion to N chars")

    p_gate = sub.add_parser("human-gate", help="HUMAN_GATE：列出等待人类介入的任务")
    p_gate.add_argument("--run-id", dest="run_id", default="",
                        help="optional: check a single RUN only")
    p_gate.add_argument("--state-root", dest="state_root", default="",
                        help="optional state root override (read-only)")
    p_gate.add_argument("--include-terminal", dest="include_terminal", action="store_true",
                        help="also include STOPPED terminal items in output")

    p_work = sub.add_parser("work", help="work：委托给生产 run.cmd（兼容保留）")
    p_work.add_argument("--goal-file", dest="goal_file", default="")
    p_work.add_argument("--r-url", dest="r_url", default="")
    p_work.add_argument("--run-cmd", dest="run_cmd", default="")

    p_report = sub.add_parser("report", help="report：委托给生产 run.cmd（兼容保留）")
    p_report.add_argument("--run-id", dest="run_id", default="")
    p_report.add_argument("--message-file", dest="message_file", default="")
    p_report.add_argument("--run-cmd", dest="run_cmd", default="")

    return ap


def main(argv: Optional[List[str]] = None) -> int:
    # 控制台统一 UTF-8 输出，避免 GBK console UnicodeEncodeError（审计 P0-2）
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.command == "result":
        return cmd_result(args)
    if args.command == "human-gate":
        return cmd_human_gate(args)
    if args.command == "work":
        return _delegate("work", args)
    if args.command == "report":
        return _delegate("report", args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
