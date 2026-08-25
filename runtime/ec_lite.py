#!/usr/bin/env python3
"""V0.6 Slice A: EC-lite — Execution Correction by rules/counters/state machine only.

Product definition #11 (EC): keep the Worker from degrading at the execution
site — repeated failure, infinite retry, busy-but-no-progress. EC-lite follows
the definition's core principle: anything that can be judged by rules, state
machines, counters and programs must NOT burn strong AI. Therefore EC-lite is
pure deterministic code:

  * durable counters live in the canonical RUN state (state["ec"]), so they
    survive process restarts and AI swaps (counters belong to the Runtime,
    not to any Worker's conversation memory — definition #24);
  * a frozen, env-overridable threshold rule table;
  * every event and every correction is journaled (durable, auditable).

Verdicts (priority order):
  HALT        — RUN lifecycle is not RUNNING (PAUSE/STOP freezes Worker
                action; definitions #23/#41);
  STOP_RETRY  — consecutive failures reached EC_MAX_RETRY (suggest
                CHANGE_TOOL / REQUEUE instead of retrying the same way);
  NO_PROGRESS — actions executed since the last artifact reached
                EC_NO_PROGRESS_ACTIONS (busy but nothing delivered;
                definition #19; escalate to C when it exists, V0.7+);
  PROCEED     — none of the above.

Subcommands (enter only via the single official entry run.cmd):
  ec-record --run-id X --event failure|artifact|action [--detail TEXT]
  ec-check  --run-id X
  ec-gate   --run-id X --action send|step|router   (V0.6-B enforcement query)

V0.6 Slice B additionally installs a fail-closed EC gate on the official send
path (see install()): HALT freezes transport, STOP_RETRY blocks identical
retry loops at the transport boundary, NO_PROGRESS keeps transport open so
escalation can travel.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

EC_SCHEMA_VERSION = 1
DEFAULT_MAX_RETRY = 3
DEFAULT_NO_PROGRESS_ACTIONS = 50


def _load_runtime():
    spec = importlib.util.spec_from_file_location("apc_runtime_core_ec", HERE / "runtime.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("runtime.py loader unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _thresholds() -> dict:
    try:
        max_retry = int(os.environ.get("APC_EC_MAX_RETRY", DEFAULT_MAX_RETRY))
    except ValueError:
        max_retry = DEFAULT_MAX_RETRY
    try:
        no_progress = int(os.environ.get("APC_EC_NO_PROGRESS_ACTIONS",
                                         DEFAULT_NO_PROGRESS_ACTIONS))
    except ValueError:
        no_progress = DEFAULT_NO_PROGRESS_ACTIONS
    return {"max_retry": max_retry, "no_progress_actions": no_progress}


def _ec_block(state: dict) -> dict:
    ec = state.get("ec")
    if not isinstance(ec, dict):
        ec = {"schema_version": EC_SCHEMA_VERSION,
              "consecutive_failures": 0,
              "actions_since_artifact": 0,
              "total_actions": 0,
              "artifact_count": 0,
              "corrections": 0,
              "last_event": None,
              "last_event_at": None}
        state["ec"] = ec
    return ec


def cmd_ec_record(rt, args) -> int:
    state, code = rt._load_or_fail(args.run_id)
    if state is None:
        return code
    if args.event not in ("failure", "artifact", "action"):
        rt.emit({"status": "DENIED", "reason": "ec-record event must be failure|artifact|action",
                 "event": args.event})
        return rt.EXIT_DENIED
    with rt.RunLock(args.run_id):
        state = rt.load_state(args.run_id)
        ec = _ec_block(state)
        ec["last_event"] = args.event
        ec["last_event_at"] = _now_iso()
        if args.event == "failure":
            ec["consecutive_failures"] = int(ec.get("consecutive_failures", 0)) + 1
            ec["actions_since_artifact"] = int(ec.get("actions_since_artifact", 0)) + 1
        elif args.event == "action":
            ec["actions_since_artifact"] = int(ec.get("actions_since_artifact", 0)) + 1
            ec["total_actions"] = int(ec.get("total_actions", 0)) + 1
        else:  # artifact
            ec["consecutive_failures"] = 0
            ec["actions_since_artifact"] = 0
            ec["artifact_count"] = int(ec.get("artifact_count", 0)) + 1
        rt.save_state(state)
        rt.journal(args.run_id, "EC_EVENT", ec_event=args.event, detail=(args.detail or "")[:500],
                   consecutive_failures=ec["consecutive_failures"],
                   actions_since_artifact=ec["actions_since_artifact"])
    rt.emit({"status": "OK", "event": args.event,
             "consecutive_failures": ec["consecutive_failures"],
             "actions_since_artifact": ec["actions_since_artifact"],
             "artifact_count": ec["artifact_count"]})
    return rt.EXIT_OK


def evaluate(state: dict, thresholds: dict) -> tuple[str, list, list]:
    """Pure rule table: (verdict, actions, reasons). No AI, no I/O."""
    if state.get("status") != "RUNNING":
        return ("HALT", ["OBEY_LIFECYCLE"],
                [f"run status is {state.get('status')}; PAUSE/STOP freezes worker action"])
    ec = state.get("ec") or {}
    failures = int(ec.get("consecutive_failures", 0))
    since = int(ec.get("actions_since_artifact", 0))
    if failures >= thresholds["max_retry"]:
        return ("STOP_RETRY", ["CHANGE_TOOL", "REQUEUE"],
                [f"consecutive_failures={failures} >= max_retry={thresholds['max_retry']}"])
    if since >= thresholds["no_progress_actions"]:
        return ("NO_PROGRESS", ["ESCALATE_C"],
                [f"actions_since_artifact={since} >= no_progress_actions="
                 f"{thresholds['no_progress_actions']}"])
    return ("PROCEED", [], [])


def cmd_ec_check(rt, args) -> int:
    state, code = rt._load_or_fail(args.run_id)
    if state is None:
        return code
    thresholds = _thresholds()
    with rt.RunLock(args.run_id):
        state = rt.load_state(args.run_id)
        verdict, actions, reasons = evaluate(state, thresholds)
        ec = _ec_block(state)
        if verdict != "PROCEED":
            ec["corrections"] = int(ec.get("corrections", 0)) + 1
            rt.save_state(state)
        rt.journal(args.run_id, "EC_CHECK", verdict=verdict, actions=actions,
                   reasons=reasons, thresholds=thresholds)
    rt.emit({"status": "OK", "verdict": verdict, "actions": actions, "reasons": reasons,
             "thresholds": thresholds,
             "counters": {"consecutive_failures": ec.get("consecutive_failures", 0),
                          "actions_since_artifact": ec.get("actions_since_artifact", 0),
                          "total_actions": ec.get("total_actions", 0),
                          "artifact_count": ec.get("artifact_count", 0),
                          "corrections": ec.get("corrections", 0)}})
    return rt.EXIT_OK


def ec_gate_policy(verdict: str, action: str) -> tuple[bool, str]:
    """Frozen V0.6-B policy table (rules only): may the given action proceed
    under the given EC verdict? Transport is the enforced degradation point:
    HALT freezes everything (definitions #23/#41), STOP_RETRY stops identical
    retry loops at the transport boundary, NO_PROGRESS still allows transport
    because escalation itself travels through send (definition #19)."""
    if verdict == "HALT":
        return False, "lifecycle frozen: PAUSE/STOP freezes worker action"
    if verdict == "STOP_RETRY" and action in ("send", "router"):
        return False, "transport blocked after repeated failures; CHANGE_TOOL or REQUEUE first"
    if verdict == "NO_PROGRESS":
        return True, "escalation pending (ESCALATE_C); transport allowed so escalation can travel"
    return True, ""


def cmd_ec_gate(rt, args) -> int:
    state, code = rt._load_or_fail(args.run_id)
    if state is None:
        return code
    thresholds = _thresholds()
    verdict, actions, reasons = evaluate(state, thresholds)
    allowed, policy_reason = ec_gate_policy(verdict, args.action)
    rt.journal(args.run_id, "EC_GATE", action=args.action, verdict=verdict,
               allowed=allowed, policy_reason=policy_reason)
    if not allowed:
        rt.emit({"status": "DENIED", "verdict": verdict, "action": args.action,
                 "reason": policy_reason, "ec_actions": actions, "ec_reasons": reasons})
        return rt.EXIT_DENIED
    rt.emit({"status": "OK", "allowed": True, "verdict": verdict, "action": args.action,
             "note": policy_reason or None})
    return rt.EXIT_OK


def install(rt) -> None:
    """Compose the EC gate onto the official send path (fail-closed). Mirrors the
    effect-safety install pattern: wrap, never modify the underlying command."""
    original_cmd_send = rt.cmd_send

    def gated_cmd_send(args):
        state = rt.load_state(args.run_id)
        verdict, actions, reasons = evaluate(state, _thresholds())
        allowed, policy_reason = ec_gate_policy(verdict, "send")
        if not allowed:
            rt.journal(args.run_id, "EC_GATE_DENIAL", action="send", verdict=verdict,
                       policy_reason=policy_reason, ec_actions=actions)
            rt.emit({"status": "DENIED", "reason": f"EC_GATE: {policy_reason}",
                     "verdict": verdict, "ec_actions": actions, "ec_reasons": reasons})
            return rt.EXIT_DENIED
        return original_cmd_send(args)

    rt.cmd_send = gated_cmd_send

    original_router_send = getattr(rt, "_router_send_to_role", None)
    if original_router_send is not None:
        def gated_router_send(state, role, message, timeout):
            verdict, actions, reasons = evaluate(state, _thresholds())
            allowed, policy_reason = ec_gate_policy(verdict, "router")
            if not allowed:
                rt.journal(state["run_id"], "EC_GATE_DENIAL", action="router",
                           verdict=verdict, policy_reason=policy_reason, ec_actions=actions)
                raise RuntimeError(f"EC_GATE: {policy_reason}")
            return original_router_send(state, role, message, timeout)
        rt._router_send_to_role = gated_router_send


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ec_lite",
                                description="EC-lite execution correction (rules only)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("ec-record")
    s.add_argument("--run-id", dest="run_id", required=True)
    s.add_argument("--event", required=True)
    s.add_argument("--detail", default=None)
    s = sub.add_parser("ec-check")
    s.add_argument("--run-id", dest="run_id", required=True)
    s = sub.add_parser("ec-gate")
    s.add_argument("--run-id", dest="run_id", required=True)
    s.add_argument("--action", required=True)
    return p


def main(argv: list | None = None) -> int:
    rt = _load_runtime()
    args = build_parser().parse_args(argv)
    if args.cmd == "ec-record":
        return cmd_ec_record(rt, args)
    if args.cmd == "ec-check":
        return cmd_ec_check(rt, args)
    if args.cmd == "ec-gate":
        return cmd_ec_gate(rt, args)
    return rt.EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
