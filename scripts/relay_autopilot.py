#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
relay_autopilot.py — A1 自动调度闭环接线 (执衡 v1.1-blackbox)

无人值守中继流转接线：goal 文件 -> BUILDER_READY 事件 -> inbox ->
认领建 RUN -> mock 执行(work) -> report -> R 审查(PASS/REWORK) -> 收尾。
全程事件触发（文件出现/状态变化驱动），无需人工逐命令。

命令:
  submit --goal-file F [--mode mock|relay] [--candidate-commit HEX]
      把 goal 转为 BUILDER_READY 事件。
        --mode mock (默认): 写入 autopilot 沙箱 inbox（真 watcher 不可见，
             供 L2 状态机驱动）
        --mode relay: 写入真实 construction-relay/inbox/（生产/L3 路径，
             运行中的 watcher 会认领并走真实 R 审查）
  drive  [--watch|--once] [--mock-review PASS|REWORK] [--max-reworks N]
        [--interval SEC] [--max-wait SEC]
      驱动状态机：
        --watch: 轮询直至队列收敛（inbox 空且无进行中 run），事件触发
        --once : 只推进一轮
      默认 mock 审查；--mock-review REWORK 用于验证 REWORK 与重排队。
  status
      打印 run 队列/状态机视图。
  validate-event --event-file F
      用 Trae-Ralph 真实 protocol.validateEvent + 真实 config/builder
      绑定校验事件格式（证明与 review-relay.js 期望一致）。
  reset-sandbox
      清空 autopilot 沙箱（inbox/runs/queue）——只动 autopilot 目录，
      绝不触碰真实 relay 状态。

状态机（run 级）:
  CLAIMED -> WORKING -> REPORTED -> WAITING_REVIEW -> REVIEWING
         -> (PASS) WRAPPED
         -> (REWORK) WORKING (rework_count+1, 重排队; 超限 -> ABORTED)
  R 并发度 = 1: 同时仅 1 个 run 处于 WAITING_REVIEW/REVIEWING。
  WAITING_REVIEW 不阻塞队列: 其余 run 仍可 CLAIMED->WORKING->REPORTED。

账本: E:\\WB\\state\\ai-production-control\\construction-relay\\
      autopilot-actions.ndjson (timestamp/action/detail/ok, 追加)
"""

import argparse
import datetime
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time

# --------------------------------------------------------------------------
# 常量（与 R1 guard 同源；只读引用真实中继状态，绝不修改）
# --------------------------------------------------------------------------
STATE_ROOT = r"E:\WB\state\ai-production-control\construction-relay"
RELAY_CONFIG = os.path.join(STATE_ROOT, "relay.config.json")
BUILDER_BINDING = os.path.join(STATE_ROOT, "bindings", "builder.json")
REAL_INBOX = os.path.join(STATE_ROOT, "inbox")
LEDGER = os.path.join(STATE_ROOT, "autopilot-actions.ndjson")

AUTO_DIR = os.path.join(STATE_ROOT, "autopilot")
SANDBOX_INBOX = os.path.join(AUTO_DIR, "inbox")
RUNS_DIR = os.path.join(AUTO_DIR, "runs")
QUEUE_FILE = os.path.join(AUTO_DIR, "queue.json")
LOCK_DIR = os.path.join(AUTO_DIR, "lock")

REVIEW_PACKET_ROOT = r"E:\WB\temp\orchestration_20260824"
ALLOWED_REPO_ROOT = r"E:\WB\temp"
ALLOWED_EVIDENCE_ROOT = r"E:\WB\state\ai-production-control\runtime-v1\harness"
DEFAULT_REVIEW_PACKET = os.path.join(REVIEW_PACKET_ROOT, "review_packet_R_round18.txt")
DEFAULT_EVIDENCE = os.path.join(ALLOWED_EVIDENCE_ROOT, "HE-0105b00e527d4bd1")

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

STATE_TERMINAL = ("WRAPPED", "ABORTED", "FAILED")
STATE_ACTIVE = ("CLAIMED", "WORKING", "REPORTED", "WAITING_REVIEW", "REVIEWING")


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def stamp():
    return datetime.datetime.now().strftime("%Y%m%d%H%M%S")


def ledger(action, detail, ok=True):
    """追加一行账本（与 guard-actions.ndjson 同格式）。"""
    row = {"timestamp": utcnow(), "action": action, "detail": str(detail), "ok": bool(ok)}
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a", encoding="ascii") as fh:
        fh.write(json.dumps(row, ensure_ascii=True) + "\n")
    return row


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def save_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def ensure_id(value, fallback_prefix, default=None):
    """把任意字符串规范成符合中继 ID_RE 的 id。"""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", str(value or ""))
    cleaned = re.sub(r"-+", "-", cleaned).strip(".-_")
    if not cleaned:
        cleaned = fallback_prefix
    if not re.match(r"^[A-Za-z0-9]", cleaned):
        cleaned = "A" + cleaned
    if len(cleaned) < 3:
        cleaned = cleaned + "-X"
    if len(cleaned) > 119:
        cleaned = cleaned[:119]
    return cleaned


def load_queue():
    q = load_json(QUEUE_FILE, {"schema_version": 1, "runs": []})
    if not isinstance(q, dict) or "runs" not in q:
        q = {"schema_version": 1, "runs": []}
    return q


def save_queue(q):
    save_json(QUEUE_FILE, q)


def acquire_lock():
    """drive 单实例锁（mkdir 原子 + token），避免两个 driver 并行。"""
    token = f"{stamp()}-{random.randint(1000, 9999)}{random.randint(1000, 9999)}"
    try:
        os.mkdir(LOCK_DIR)
    except FileExistsError:
        info = load_json(os.path.join(LOCK_DIR, "lock.json"))
        if info:
            try:
                age = (datetime.datetime.now(datetime.timezone.utc) -
                       datetime.datetime.fromisoformat(info["at"].replace("Z", "+00:00"))).total_seconds()
            except Exception:
                age = -1
            # 新鲜锁（0<=age<=300）：另一实例持有 -> SKIP_LOCKED，绝不覆盖他人锁
            if age is not None and 0 <= age <= 300:
                return None
            # stale（age>300）或异常（解析失败 age=-1 / 未来时间 age<0）-> 回收重建
            shutil.rmtree(LOCK_DIR, ignore_errors=True)
            try:
                os.mkdir(LOCK_DIR)
            except FileExistsError:
                return None
        else:
            shutil.rmtree(LOCK_DIR, ignore_errors=True)
            try:
                os.mkdir(LOCK_DIR)
            except FileExistsError:
                return None
    save_json(os.path.join(LOCK_DIR, "lock.json"), {"token": token, "at": utcnow()})
    return token


def release_lock(token):
    info = load_json(os.path.join(LOCK_DIR, "lock.json"))
    if info and info.get("token") == token:
        try:
            os.remove(os.path.join(LOCK_DIR, "lock.json"))
        except OSError:
            pass
        try:
            os.rmdir(LOCK_DIR)
        except OSError:
            pass


def load_relay_config():
    cfg = load_json(RELAY_CONFIG)
    if not cfg:
        raise RuntimeError(f"relay config missing: {RELAY_CONFIG}")
    return cfg


def load_builder_binding():
    b = load_json(BUILDER_BINDING)
    if not b:
        raise RuntimeError(f"builder binding missing: {BUILDER_BINDING}")
    return b


# --------------------------------------------------------------------------
# submit：goal -> BUILDER_READY 事件
# --------------------------------------------------------------------------
def build_event(goal, seq, candidate_commit=None, relay_mode=False):
    """构造与 review-relay.js validateEvent 期望一致的 BUILDER_READY 事件。"""
    cfg = load_relay_config()
    binding = load_builder_binding()
    ts = stamp()
    goal_id = ensure_id(goal.get("goal_id") or goal.get("title") or f"GOAL-{seq}", "GOAL")
    task_id = ensure_id(f"AUTOPILOT-{goal_id}", "AUTOPILOT")
    run_id = ensure_id(f"RUN-AUTO-{ts}-{seq:04d}", "RUN")
    event_id = ensure_id(f"EV-AUTO-{ts}-{seq:04d}", "EV")

    commit = candidate_commit or "".join(random.choice("0123456789abcdef") for _ in range(40))
    if not COMMIT_RE.match(commit):
        raise ValueError("candidate_commit must be 40 hex chars")

    packet = DEFAULT_REVIEW_PACKET
    if not os.path.exists(packet):
        packet = REVIEW_PACKET_ROOT  # 目录也可通过 existsSync
    verdict_path = os.path.join(REVIEW_PACKET_ROOT, f"autopilot-verdict-{run_id}.txt")
    evidence = [DEFAULT_EVIDENCE if os.path.exists(DEFAULT_EVIDENCE) else ALLOWED_EVIDENCE_ROOT]

    event = {
        "schema_version": 1,
        "event": "BUILDER_READY",
        "event_id": event_id,
        "project_id": cfg["project_id"],
        "run_id": run_id,
        "task_id": task_id,
        "repo_path": ALLOWED_REPO_ROOT,
        "candidate_commit": commit,
        "candidate_branch": "autopilot-mock" if not relay_mode else "autopilot-relay",
        "review_packet": packet,
        "verdict_path": verdict_path,
        "evidence_paths": evidence,
        "builder": {
            "provider": binding["provider"],
            "model": binding["model"],
            "conversation_id": binding["conversation_id"],
            "generation": binding["generation"],
        },
        "created_at": utcnow(),
    }
    event["_goal"] = {
        "goal_id": goal_id,
        "title": str(goal.get("title") or goal.get("objective") or goal_id),
        "objective": str(goal.get("objective") or ""),
        "scope": goal.get("scope") or [],
        "acceptance": goal.get("acceptance") or [],
        "milestone": str(goal.get("milestone") or cfg.get("automation", {}).get("current_milestone", "V0.7")),
        "priority": int(goal.get("priority") or 1),
    }
    return event


def cmd_submit(args):
    goal = load_json(args.goal_file)
    if not goal:
        ledger("submit", f"goal file unreadable or invalid JSON: {args.goal_file}", ok=False)
        return 2
    if not (goal.get("objective") or goal.get("title")):
        ledger("submit", "goal must have objective or title", ok=False)
        return 2
    seq = int(time.time() * 1000) % 100000
    event = build_event(goal, seq, args.candidate_commit, relay_mode=(args.mode == "relay"))

    if args.mode == "relay":
        target_dir = REAL_INBOX
        os.makedirs(target_dir, exist_ok=True)
        target = os.path.join(target_dir, f"{event['event_id']}.json")
        payload = {k: v for k, v in event.items() if not k.startswith("_")}
    else:
        target_dir = SANDBOX_INBOX
        os.makedirs(target_dir, exist_ok=True)
        target = os.path.join(target_dir, f"{event['event_id']}.json")
        payload = event

    save_json(target, payload)
    ledger("submit", f"mode={args.mode} event={event['event_id']} run={event['run_id']} "
                     f"task={event['task_id']} inbox={target}", ok=True)
    print(json.dumps({"ok": True, "mode": args.mode, "event_id": event["event_id"],
                      "run_id": event["run_id"], "task_id": event["task_id"],
                      "inbox_file": target}, ensure_ascii=False, indent=2))
    return 0


# --------------------------------------------------------------------------
# drive：状态机引擎
# --------------------------------------------------------------------------
def claim_inbox():
    """扫描沙箱 inbox，把新 BUILDER_READY 事件认领为 run。"""
    q = load_queue()
    claimed = 0
    if not os.path.isdir(SANDBOX_INBOX):
        return 0
    names = sorted(n for n in os.listdir(SANDBOX_INBOX) if n.lower().endswith(".json"))
    for name in names:
        src = os.path.join(SANDBOX_INBOX, name)
        ev = load_json(src)
        if not ev or ev.get("event") != "BUILDER_READY":
            ledger("claim_skip", f"{name}: not BUILDER_READY", ok=False)
            continue
        run_id = ev.get("run_id")
        if not run_id or not ID_RE.match(str(run_id)):
            ledger("claim_skip", f"{name}: run_id escapes sandbox or invalid: {run_id!r}", ok=False)
            continue
        if any(r["run_id"] == run_id for r in q["runs"]):
            ledger("claim_skip", f"{run_id}: duplicate", ok=False)
            continue
        run_dir = os.path.join(RUNS_DIR, run_id)
        os.makedirs(run_dir, exist_ok=True)
        shutil.move(src, os.path.join(run_dir, "builder-ready.json"))
        goal = ev.get("_goal") or {}
        run = {
            "run_id": run_id,
            "event_id": ev["event_id"],
            "task_id": ev["task_id"],
            "title": goal.get("title") or ev["task_id"],
            "milestone": goal.get("milestone") or "",
            "priority": goal.get("priority") or 1,
            "candidate_commit": ev["candidate_commit"],
            "state": "CLAIMED",
            "rework_count": 0,
            "created_at": utcnow(),
            "claimed_at": utcnow(),
            "verdict": None,
        }
        q["runs"].append(run)
        ledger("claim", f"claimed run={run_id} task={ev['task_id']} event={ev['event_id']}", ok=True)
        claimed += 1
    save_queue(q)
    return claimed


def mock_work(run, run_dir):
    """mock 执行：生成证据与 report（L2 不触发真实弱模型）。"""
    work_dir = os.path.join(run_dir, "mock-work")
    os.makedirs(work_dir, exist_ok=True)
    evidence = {
        "schema_version": 1,
        "run_id": run["run_id"],
        "task_id": run["task_id"],
        "mock": True,
        "produced_at": utcnow(),
        "checks": ["mock_offline_suite: PASS"],
    }
    save_json(os.path.join(work_dir, "evidence.json"), evidence)
    report = {
        "schema_version": 1,
        "run_id": run["run_id"],
        "task_id": run["task_id"],
        "status": "COMPLETE",
        "summary": f"mock work complete for {run['title']}",
        "mock": True,
        "rework_count": run["rework_count"],
        "reported_at": utcnow(),
    }
    save_json(os.path.join(run_dir, "report.json"), report)
    return report


def mock_review(run, run_dir, verdict):
    """mock 审查：产出与 validateReviewResult 形状一致的结果。"""
    review = {
        "schema_version": 1,
        "verdict": verdict,
        "next_action": None if verdict == "PASS" else "REWORK_NEXT",
        "event_id": run["event_id"],
        "run_id": run["run_id"],
        "task_id": run["task_id"],
        "candidate_commit": run["candidate_commit"],
        "summary": f"mock review -> {verdict} for {run['title']}",
        "machine_checks": ["mock: identity binding PASS"],
        "confidence": "HIGH",
        "risk_tags": [],
        "provider": "autopilot-mock",
    }
    save_json(os.path.join(run_dir, "review-result.json"), review)
    return review


def wrap(run, run_dir):
    summary = {
        "schema_version": 1,
        "run_id": run["run_id"],
        "task_id": run["task_id"],
        "status": "WRAPPED",
        "rework_count": run["rework_count"],
        "wrapped_at": utcnow(),
    }
    save_json(os.path.join(run_dir, "wrap-summary.json"), summary)
    return summary


def advance_once(mock_review_verdict, max_reworks):
    """推进一轮状态机。返回状态变化次数。"""
    q = load_queue()
    changed = 0
    review_busy = any(r["state"] in ("WAITING_REVIEW", "REVIEWING") for r in q["runs"])

    # 1) 非门控推进：CLAIMED->WORKING->REPORTED
    for run in q["runs"]:
        run_id = run["run_id"]
        run_dir = os.path.join(RUNS_DIR, run_id)
        st = run["state"]
        if st == "CLAIMED":
            run["state"] = "WORKING"
            run["working_at"] = utcnow()
            ledger("work_start", f"run={run_id} mock execution start", ok=True)
            changed += 1
        elif st == "WORKING":
            mock_work(run, run_dir)
            run["state"] = "REPORTED"
            run["reported_at"] = utcnow()
            ledger("work_done", f"run={run_id} report produced", ok=True)
            changed += 1
        elif st == "REVIEWING":
            verdict = mock_review_verdict
            review = mock_review(run, run_dir, verdict)
            run["verdict"] = verdict
            if verdict == "PASS":
                wrap(run, run_dir)
                run["state"] = "WRAPPED"
                run["wrapped_at"] = utcnow()
                ledger("review_pass", f"run={run_id} verdict=PASS -> WRAPPED", ok=True)
            else:
                run["rework_count"] += 1
                if run["rework_count"] >= max_reworks:
                    run["state"] = "ABORTED"
                    run["aborted_at"] = utcnow()
                    ledger("abort", f"run={run_id} rework limit exceeded ({max_reworks})", ok=False)
                else:
                    run["state"] = "WORKING"
                    run["working_at"] = utcnow()
                    ledger("review_rework", f"run={run_id} verdict=REWORK rework={run['rework_count']} -> requeued", ok=True)
            changed += 1

    # OBS-A1: step1 后重算门状态——REWORK 在本轮释放 R 门时，同轮即可准入新 run（即时，不延迟一轮）
    review_busy = any(r["state"] in ("WAITING_REVIEW", "REVIEWING") for r in q["runs"])

    # 2) R 门控：REPORTED -> WAITING_REVIEW（并发度 1，公平：rework 少者优先）
    reported = [r for r in q["runs"] if r["state"] == "REPORTED"]
    reported.sort(key=lambda r: (r["rework_count"], r["created_at"]))
    if not review_busy and reported:
        run = reported[0]
        run["state"] = "WAITING_REVIEW"
        run["waiting_review_at"] = utcnow()
        ledger("review_enter", f"run={run['run_id']} entered WAITING_REVIEW (R gate, concurrency=1)", ok=True)
        review_busy = True
        changed += 1

    # 3) WAITING_REVIEW -> REVIEWING（门已被占用者推进）
    for run in q["runs"]:
        if run["state"] == "WAITING_REVIEW":
            run["state"] = "REVIEWING"
            run["reviewing_at"] = utcnow()
            ledger("review_start", f"run={run['run_id']} mock review start", ok=True)
            changed += 1
            break

    save_queue(q)
    return changed


def queue_converged(q):
    if any(r["state"] in STATE_ACTIVE for r in q["runs"]):
        return False
    if os.path.isdir(SANDBOX_INBOX) and any(n.endswith(".json") for n in os.listdir(SANDBOX_INBOX)):
        return False
    return True


def cmd_drive(args):
    token = acquire_lock()
    if token is None:
        ledger("drive", "SKIP_LOCKED another autopilot drive holds the lock", ok=False)
        print("SKIP_LOCKED: another drive instance is running")
        return 0
    try:
        if args.mode_review not in ("PASS", "REWORK"):
            print(f"invalid --mock-review {args.mode_review}; use PASS|REWORK", file=sys.stderr)
            return 2
        deadline = time.time() + args.max_wait
        rounds = 0
        while True:
            changed = 0
            changed += claim_inbox()
            changed += advance_once(args.mode_review, args.max_reworks)
            rounds += 1
            q = load_queue()
            if args.watch:
                if queue_converged(q) or time.time() > deadline:
                    break
                time.sleep(args.interval)
            else:
                break
        q = load_queue()
        summary = {
            "rounds": rounds,
            "total_runs": len(q["runs"]),
            "states": {},
        }
        for r in q["runs"]:
            summary["states"][r["state"]] = summary["states"].get(r["state"], 0) + 1
        ledger("drive_end", f"watch={args.watch} rounds={rounds} runs={len(q['runs'])} "
                            f"states={json.dumps(summary['states'], ensure_ascii=False)}", ok=True)
        print(json.dumps({"ok": True, **summary}, ensure_ascii=False, indent=2))
        return 0
    finally:
        release_lock(token)


def cmd_status(args):
    q = load_queue()
    print("=== autopilot run queue ===")
    if not q["runs"]:
        print("(empty)")
    for r in sorted(q["runs"], key=lambda x: x["created_at"]):
        print(f"  {r['run_id']:<32} {r['state']:<15} task={r['task_id']:<30} "
              f"rework={r['rework_count']} at={r['created_at']}")
    pending = 0
    if os.path.isdir(SANDBOX_INBOX):
        pending = len([n for n in os.listdir(SANDBOX_INBOX) if n.endswith(".json")])
    print(f"inbox_pending={pending} runs={len(q['runs'])}")
    return 0


def cmd_validate_event(args):
    """用 Trae-Ralph 真实 protocol.validateEvent 校验事件格式。"""
    node = os.environ.get("NODE_BIN") or "node"
    script = (
        "const fs=require('fs');const path=require('path');"
        "const proto=require('E:/WB/tools/Trae-Ralph/src/relay/protocol');"
        f"const cfg=proto.validateConfig(JSON.parse(fs.readFileSync({json.dumps(RELAY_CONFIG)},'utf8')));"
        f"const binding=proto.validateBinding(JSON.parse(fs.readFileSync({json.dumps(BUILDER_BINDING)},'utf8')),cfg);"
        f"const ev=JSON.parse(fs.readFileSync({json.dumps(os.path.abspath(args.event_file))},'utf8'));"
        "const n=proto.validateEvent(ev,cfg,binding);"
        "console.log(JSON.stringify({ok:true,event_id:n.event_id,run_id:n.run_id,task_id:n.task_id}));"
    )
    proc = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    if proc.returncode == 0:
        ledger("validate_event", f"{args.event_file} PASS against real protocol", ok=True)
        print(proc.stdout.strip())
        return 0
    ledger("validate_event", f"{args.event_file} FAIL: {proc.stderr.strip()[:300]}", ok=False)
    print(proc.stderr.strip(), file=sys.stderr)
    return 1


def cmd_reset_sandbox(args):
    """只清 autopilot 沙箱（inbox/runs/queue/lock），绝不碰真实中继状态。"""
    for sub in ("inbox", "runs", "lock"):
        shutil.rmtree(os.path.join(AUTO_DIR, sub), ignore_errors=True)
    for f in ("queue.json",):
        try:
            os.remove(os.path.join(AUTO_DIR, f))
        except OSError:
            pass
    ledger("reset_sandbox", f"autopilot sandbox reset ({AUTO_DIR})", ok=True)
    print("sandbox reset")
    return 0


def main():
    parser = argparse.ArgumentParser(description="A1 中继自动调度闭环接线")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_submit = sub.add_parser("submit", help="goal -> BUILDER_READY 事件 -> inbox")
    p_submit.add_argument("--goal-file", required=True)
    p_submit.add_argument("--mode", choices=["mock", "relay"], default="mock")
    p_submit.add_argument("--candidate-commit", default=None)
    p_submit.set_defaults(func=cmd_submit)

    p_drive = sub.add_parser("drive", help="驱动状态机")
    p_drive.add_argument("--watch", action="store_true")
    p_drive.add_argument("--once", dest="watch", action="store_false")
    p_drive.set_defaults(watch=True)
    p_drive.add_argument("--mock-review", dest="mode_review", choices=["PASS", "REWORK"], default="PASS")
    p_drive.add_argument("--max-reworks", type=int, default=8)
    p_drive.add_argument("--interval", type=float, default=1.0)
    p_drive.add_argument("--max-wait", type=float, default=120.0)
    p_drive.set_defaults(func=cmd_drive)

    p_status = sub.add_parser("status", help="队列/状态机视图")
    p_status.set_defaults(func=cmd_status)

    p_val = sub.add_parser("validate-event", help="用真实 protocol 校验事件格式")
    p_val.add_argument("--event-file", required=True)
    p_val.set_defaults(func=cmd_validate_event)

    p_reset = sub.add_parser("reset-sandbox", help="清空 autopilot 沙箱")
    p_reset.set_defaults(func=cmd_reset_sandbox)

    args = parser.parse_args()
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        ledger("error", f"{args.cmd}: {exc}", ok=False)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
