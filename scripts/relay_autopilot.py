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
import hashlib
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

# --- 接线：调度准入三闸（§59/§55/§34）---
_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runtime")
if _RUNTIME_DIR not in sys.path:
    sys.path.insert(0, _RUNTIME_DIR)

try:
    import cost_router
    import context_sufficiency
    import controller_lease
    _WIRING_AVAILABLE = True
except Exception:
    _WIRING_AVAILABLE = False


def admission_checks(goal, require_gates=False):
    """调度准入三闸：§59 成本融断 / §55 Context / §34 Controller lease。
    返回 {admitted: bool, checks: {...}, reasons: [...]}。

    GATE-1#3/#4 (hardening 2026-08-31)：
    - 闸门正常判定为拒绝（SAFE_HALT/FROZEN/BLOCKED/HUMAN_AUTHORIZATION/租约失效）
      时，任何模式下都必须拒（判定本身即权威）。
    - require_gates=True（relay 真实投递）：模块不可用/配置损坏/闸内异常
      一律 fail-closed 拒绝 —— 真实投递不允许"门坏了就跳过门"。
    - require_gates=False（mock 沙箱）：闸内异常保守放行并记录（不误拦演练），
      但判定为拒的仍拒。
    """
    result = {"schema": "ADMISSION_V1", "admitted": True, "checks": {}, "reasons": []}
    if not _WIRING_AVAILABLE:
        if require_gates:
            result["admitted"] = False
            result["reasons"].append("gates-required: wiring modules unavailable (fail-closed)")
        else:
            result["reasons"].append("wiring modules unavailable; skip gates (mock only)")
        return result
    gh = goal.get("goal_id") or goal.get("title") or "unknown"
    goal_text = goal.get("objective") or goal.get("title") or ""
    adopts = goal.get("admission") if isinstance(goal.get("admission"), dict) else {}

    # §59 cost 门
    try:
        policy = cost_router.load_policy()
        reg = cost_router.load_registry_costs()
        state = cost_router.load_state()
        rk = str(adopts.get("rework_risk") or goal.get("rework_risk") or "low")
        cost = cost_router.do_route(goal_text, rk, tokens_est=None, max_cost=None,
                                    policy=policy, registry_costs=reg, state=state)
        result["checks"]["cost"] = {"verdict": cost.get("verdict"),
                                    "recommended_route": cost.get("recommended_route"),
                                    "expected_total_cost": cost.get("expected_total_cost")}
        # GATE-1#3: SAFE_HALT（新熔断）与 FROZEN（历史熔断后的冻结应答）均为
        # 拒绝性 verdict —— 只拦 SAFE_HALT 会让已冻结 goal 换个提交重新入队。
        if cost.get("verdict") in ("SAFE_HALT", "FROZEN"):
            result["admitted"] = False
            result["reasons"].append(
                f"cost-gate {cost.get('verdict')}: {cost.get('safe_halt', {}).get('record_id') or 'frozen'}")
        elif cost.get("verdict") == "UNDETERMINED":
            result["reasons"].append("cost-gate UNDETERMINED (全部待校准，不误拦)")
    except Exception as e:  # noqa: BLE001
        if require_gates:
            result["admitted"] = False
            result["reasons"].append(f"gates-required: cost-gate error (fail-closed): {e}")
        else:
            result["reasons"].append(f"cost-gate error (skip): {e}")

    # §55 context 门
    try:
        req = goal.get("required_info") or []
        ctx = {"goal": goal_text, "goal_id": gh}
        ctxres = context_sufficiency.route(ctx, req)
        result["checks"]["context"] = {"decision": ctxres.get("decision")}
        if ctxres.get("decision") in ("BLOCKED", "HUMAN_AUTHORIZATION"):
            result["admitted"] = False
            detail = ctxres.get("blocked_reason") or ctxres.get("reason") or ctxres.get("decision")
            result["reasons"].append(f"context-gate {ctxres.get('decision')}: {detail}")
    except Exception as e:  # noqa: BLE001
        if require_gates:
            result["admitted"] = False
            result["reasons"].append(f"gates-required: context-gate error (fail-closed): {e}")
        else:
            result["reasons"].append(f"context-gate error (skip): {e}")

    # §34 Controller lease 门（执行代用户控制器表示，还原实现代表）
    try:
        cur = controller_lease.load_lease()
        if cur is None:
            l = controller_lease.acquire("relay_autopilot")
            result["checks"]["lease"] = {"action": "acquired", "generation": l["generation"]}
        else:
            gen = int(cur.get("generation", 0))
            holder = str(cur.get("holder", ""))
            if holder != "relay_autopilot":
                # 老/foreign Controller 持有: 继续者接管 = acquire (generation+1)
                l = controller_lease.acquire("relay_autopilot")
                result["checks"]["lease"] = {"action": "took-over", "generation": l["generation"]}
                result["reasons"].append(f"lease-gate took over from {holder}（§34）")
            else:
                r = controller_lease.check_execute_right(holder, gen)
                # Land the check result FIRST (P3 fix: the check-OK path never
                # initialized checks["lease"] and blew up with KeyError later).
                result["checks"]["lease"] = {"ok": r.get("ok"), "reason": r.get("reason")}
                if not r["ok"] and r.get("reason") == "LEASE_EXPIRED":
                    # 自己持有的过期租约：同代续约即可（renew 在文件锁内校验
                    # generation——若期间已被他人接管则仍拒，fencing 不弱化）。
                    rn = controller_lease.renew(holder, gen)
                    if rn.get("ok"):
                        result["checks"]["lease"] = {"action": "renewed", "ok": True,
                                                     "reason": "OK",
                                                     "generation": (rn.get("lease") or {}).get("generation")}
                        r = {"ok": True, "reason": "OK"}
                    else:
                        result["checks"]["lease"] = {"action": "renew-denied", "ok": False,
                                                     "reason": rn.get("reason")}
                if not r["ok"]:
                    result["admitted"] = False
                    result["reasons"].append(f"lease-gate {r.get('reason')}: 老权失效或过期")
    except Exception as e:  # noqa: BLE001
        if require_gates:
            result["admitted"] = False
            result["reasons"].append(f"gates-required: lease-gate error (fail-closed): {e}")
        else:
            result["reasons"].append(f"lease-gate error (skip): {e}")

    return result


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
    """drive 单实例锁（GATE-2#9: lock.json 本身 O_EXCL 原子认领）。

    旧实现 mkdir 成功后再写 lock.json，两步之间的窗口让并发者把"刚建好
    还没写 json"的锁当陈旧锁 rmtree 掉 -> 覆盖写回 -> 双持有者。新实现
    直接对 lock.json 做 O_CREAT|O_EXCL 创建作为认领动作（原子，无窗口）：
    - 创建成功 = 认领成功，随后写 token；
    - 已存在 = 读内容判定：新鲜（0<=age<=300）-> SKIP_LOCKED；
      stale/损坏 -> 删除后重试一次独占创建（接管）。
    空目录（无 lock.json）无害：任何人可认领。release_lock 语义不变。
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    token = f"{stamp()}-{random.randint(1000, 9999)}{random.randint(1000, 9999)}"
    try:
        os.mkdir(LOCK_DIR)
    except FileExistsError:
        pass
    lock_json = os.path.join(LOCK_DIR, "lock.json")
    for _ in range(2):
        try:
            fd = os.open(lock_json, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            info = load_json(lock_json)
            if info is None:
                # 损坏/半写的认领文件（前主崩溃残留）：删除后重试一次。
                # Windows 上对仍被打开的文件 unlink 会 PermissionError
                # -> return None（绝不误删活跃持有者的锁）。
                try:
                    os.remove(lock_json)
                except OSError:
                    return None
                continue
            try:
                age = (now - datetime.datetime.fromisoformat(
                    str(info.get("at", "")).replace("Z", "+00:00"))).total_seconds()
            except Exception:
                age = -1
            # 新鲜锁（0<=age<=300）：另一实例持有 -> SKIP_LOCKED，绝不覆盖
            if 0 <= age <= 300:
                return None
            # stale（age>300）或解析失败/未来时间 -> 接管。
            # P2-1（内审）：不能直接 os.remove——并发接管者 A 读 stale、B
            # remove+认领+写新 json、A 再 remove 会删掉 B 的**新鲜**锁 ->
            # 双持有者。改为 rename-steal：把旧 lock.json 原子改名到唯一
            # 墓碑名，rename 唯一成功者才获得接管权（失败者 SKIP）。
            tombstone = os.path.join(LOCK_DIR, f"lock.stolen-{token}")
            try:
                os.rename(lock_json, tombstone)
            except OSError:
                return None  # 别的接管者已偷走（或 Windows 文件打开中）
            try:
                fd = os.open(lock_json, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    os.remove(tombstone)
                except OSError:
                    pass
                return None
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump({"token": token, "at": utcnow()}, fh, ensure_ascii=False)
                    fh.flush()
                    os.fsync(fh.fileno())
            finally:
                try:
                    os.remove(tombstone)
                except OSError:
                    pass
            return token
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"token": token, "at": utcnow()}, fh, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())
            return token
    return None


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
def _resolve_commit(goal, seq, candidate_commit, relay_mode):
    """GATE-1#2 (hardening 2026-08-31): resolve candidate_commit fail-closed.

    - explicit candidate_commit must be a real 40-hex value;
    - relay mode (real inbox, real reviewer) REQUIRES an explicit commit:
      a fabricated random hex would make R review a commit that does not
      exist — forbidden;
    - mock sandbox may omit it: a deterministic placeholder derived from the
      goal payload (reproducible, goal-bound, never impersonates a commit).
    """
    if candidate_commit:
        commit = str(candidate_commit).strip().lower()
        if not COMMIT_RE.match(commit):
            raise ValueError("candidate_commit must be 40 hex chars")
        return commit
    if relay_mode:
        raise ValueError(
            "relay mode requires --candidate-commit <40-hex real commit>; "
            "fabricating one is forbidden (GATE-1#2)")
    payload = json.dumps(goal, ensure_ascii=False, sort_keys=True) + "#" + str(seq)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:40]


def build_event(goal, seq, candidate_commit=None, relay_mode=False, repo_path=None,
                review_packet=None, evidence_paths=None):
    """构造与 review-relay.js validateEvent 期望一致的 BUILDER_READY 事件。"""
    cfg = load_relay_config()
    binding = load_builder_binding()
    ts = stamp()
    goal_id = ensure_id(goal.get("goal_id") or goal.get("title") or f"GOAL-{seq}", "GOAL")
    task_id = ensure_id(f"AUTOPILOT-{goal_id}", "AUTOPILOT")
    run_id = ensure_id(f"RUN-AUTO-{ts}-{seq:04d}", "RUN")
    event_id = ensure_id(f"EV-AUTO-{ts}-{seq:04d}", "EV")

    commit = _resolve_commit(goal, seq, candidate_commit, relay_mode)

    packet = review_packet or DEFAULT_REVIEW_PACKET
    if not os.path.exists(packet):
        packet = REVIEW_PACKET_ROOT  # 目录也可通过 existsSync
    verdict_path = os.path.join(REVIEW_PACKET_ROOT, f"autopilot-verdict-{run_id}.txt")
    evidence = list(evidence_paths or []) or [DEFAULT_EVIDENCE if os.path.exists(DEFAULT_EVIDENCE) else ALLOWED_EVIDENCE_ROOT]

    event = {
        "schema_version": 1,
        "event": "BUILDER_READY",
        "event_id": event_id,
        "project_id": cfg["project_id"],
        "run_id": run_id,
        "task_id": task_id,
        "repo_path": repo_path or ALLOWED_REPO_ROOT,  # GATE-5: caller may inject the real repo (hardcoded E:\WB\temp is legacy)
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
    admit = admission_checks(goal, require_gates=(args.mode == "relay"))
    if not admit["admitted"]:
        ledger("submit_rejected", "goal=" + (goal.get('goal_id') or goal.get('title'))
               + " reasons=" + str(admit['reasons']), ok=False)
        print(json.dumps({"ok": False, "admitted": False, "reasons": admit["reasons"],
                          "checks": admit["checks"]}, ensure_ascii=False, indent=2))
        return 2
    ledger("submit_admission", "goal=" + (goal.get('goal_id') or goal.get('title'))
           + " checks=" + json.dumps(admit['checks'], ensure_ascii=False), ok=True)
    seq = int(time.time() * 1000) % 100000
    event = build_event(goal, seq, args.candidate_commit, relay_mode=(args.mode == "relay"),
                        repo_path=getattr(args, "repo_path", None) or None,
                        review_packet=getattr(args, "review_packet", None) or None,
                        evidence_paths=getattr(args, "evidence_path", None) or None)

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
    # §34: drive 执行前验证 Controller 代（老权失效拒绝）
    if _WIRING_AVAILABLE:
        try:
            cur = controller_lease.load_lease()
            if cur is None:
                controller_lease.acquire("relay_autopilot")
                ledger("lease_acquired", "drive acquired controller lease gen=1", ok=True)
            else:
                chk = controller_lease.check_execute_right(str(cur.get("holder")), int(cur.get("generation", 0)))
                if not chk["ok"]:
                    ledger("drive", "lease-gate " + chk.get('reason') + ": old authority revoked, abort execute", ok=False)
                    print("LEASE_REJECTED: " + str(chk.get("error")), file=sys.stderr)
                    return 2
        except Exception as exc:  # noqa: BLE001
            # P1-4 (hardening batch A 补内审): drive 是真实执行器，与 submit 侧
            # require_gates 语义对齐 —— lease 门坏了不许"跳过门"继续执行
            # (fail-closed)。旧行为 catch-and-skip 会在状态文件损坏/权限故障时
            # 无授权推进状态机，与 GATE-1#4 纪律相悖。
            ledger("drive", "lease-gate error (fail-closed): " + str(exc), ok=False)
            print("LEASE_GATE_ERROR: " + str(exc), file=sys.stderr)
            return 2
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


def build_parser():
    """构建 CLI 解析器（抽出以便离线测试验证参数面，行为不变）。"""
    parser = argparse.ArgumentParser(description="A1 中继自动调度闭环接线")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_submit = sub.add_parser("submit", help="goal -> BUILDER_READY 事件 -> inbox")
    p_submit.add_argument("--goal-file", required=True)
    p_submit.add_argument("--mode", choices=["mock", "relay"], default="mock")
    p_submit.add_argument("--candidate-commit", default=None)
    p_submit.add_argument("--repo-path", default=None,
                          help="GATE-5: builder 实际工作的 git 仓库（默认遗留常量 E:\\WB\\temp）")
    p_submit.add_argument("--review-packet", default=None,
                          help="R 审查包路径（默认遗留 round18 常量会致会话串台，务必注入本任务包）")
    p_submit.add_argument("--evidence-path", action="append", default=None,
                          help="机器证据目录/文件（可多次；默认遗留 V0.6 证据会致 CANDIDATE 绑定不符）")
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
    return parser


def main():
    parser = build_parser()
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
