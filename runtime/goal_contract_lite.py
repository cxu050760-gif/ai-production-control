#!/usr/bin/env python3
"""Slice C Goal Contract Lite integration for the single OFFICIAL Runtime entry.

This module is not a second Runtime entry. runtime/run.cmd remains the only
production entry and delegates contract-sensitive commands here so they can
install a thin contract binding around the frozen runtime.py implementation.
The canonical RUN state remains runtime-v1 state.json + journal.jsonl.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Reuse the Legacy Goal Contract canonical serialization/hash primitives.
from aicontrol.util import canonical_json, sha256_text  # noqa: E402

import ec_lite as ec  # noqa: E402  (V0.6-C auto-telemetry; rules-only, no cycle)

CONTRACT_SCHEMA_VERSION = 1
DEFAULT_ACCEPTANCE = ("Independent Reviewer must return PASS for the frozen GOAL under this Goal Contract identity.",)
CONTRACT_HASH_RE = re.compile(r"(?im)^\s*GOAL_CONTRACT_HASH\s*=\s*([0-9a-f]{64})\s*$")
CONTRACT_AWARE_COMMANDS = {
    "start", "work", "step", "directive", "send", "recv", "report", "done",
    "router-start", "router-step", "router-run",
}


class GoalContractError(RuntimeError):
    pass


def _load_runtime():
    spec = importlib.util.spec_from_file_location("apc_runtime_core", HERE / "runtime.py")
    if spec is None or spec.loader is None:
        raise GoalContractError("runtime.py loader unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalize_text(value: str) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _normalize_list(values: list[str] | tuple[str, ...] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        text = _normalize_text(value)
        if text:
            out.append(text)
    return out


def _contract_core(goal: str, acceptance: list[str], constraints: list[str]) -> dict[str, Any]:
    return {
        "goal": _normalize_text(goal),
        "acceptance_criteria": _normalize_list(acceptance),
        "constraints": _normalize_list(constraints),
    }


def build_contract(goal: str, acceptance: list[str] | None = None,
                   constraints: list[str] | None = None, *, revision: int = 1,
                   data_egress_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    acceptance_values = _normalize_list(acceptance)
    if not acceptance_values:
        acceptance_values = list(DEFAULT_ACCEPTANCE)
    core = _contract_core(goal, acceptance_values, constraints or [])
    if not core["goal"]:
        raise GoalContractError("Goal Contract GOAL is empty")
    digest = sha256_text(canonical_json(core))
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_revision": int(revision),
        **core,
        # T11b: the contract is the authority for outbound egress. An empty policy
        # means "nothing is permitted", so the default stays fail-closed. It is
        # deliberately NOT part of the hashed core: contract identity remains
        # sha256(goal, acceptance_criteria, constraints) and is unaffected.
        "data_egress_policy": dict(data_egress_policy or {}),
        "contract_hash": digest,
        "identity_semantics": "sha256(canonical_json(goal,acceptance_criteria,constraints))",
    }


def contract_hash(contract: dict[str, Any]) -> str:
    core = _contract_core(
        str(contract.get("goal") or ""),
        list(contract.get("acceptance_criteria") or []),
        list(contract.get("constraints") or []),
    )
    return sha256_text(canonical_json(core))


def _contract_path(rt, state: dict[str, Any], revision: int) -> Path:
    return rt.run_dir(state["run_id"]) / f"goal_contract_v{revision:04d}.json"


def persist_contract(rt, state: dict[str, Any], contract: dict[str, Any], *, event: str,
                     old_hash: str | None = None, note: str = "") -> dict[str, Any]:
    digest = contract_hash(contract)
    if digest != contract.get("contract_hash"):
        raise GoalContractError("Goal Contract hash does not match canonical content")
    revision = int(contract["contract_revision"])
    path = _contract_path(rt, state, revision)
    rt.atomic_write_text(path, json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    state["goal"] = contract["goal"]
    state["goal_contract"] = contract
    state["goal_contract_hash"] = digest
    state["goal_contract_revision"] = revision
    state["goal_contract_path"] = str(path)
    # T11b: minimal permission projection derived from the contract just persisted.
    # Only this runtime code path writes it (no worker or model output channel does).
    # Additive field: pre-existing state files simply have no projection, and the
    # consumer must deny when it is absent or when source_contract_hash no longer
    # matches goal_contract_hash.
    state["egress_policy_projection"] = {
        "data_egress_policy": dict(contract.get("data_egress_policy") or {}),
        "source_contract_hash": digest,
    }
    rt.save_state(state)
    rt.journal(
        state["run_id"], event,
        goal_contract_hash=digest,
        goal_contract_revision=revision,
        goal_contract_path=str(path),
        old_goal_contract_hash=old_hash,
        note=note,
    )
    return state


def require_contract(rt, state: dict[str, Any]) -> dict[str, Any]:
    contract = state.get("goal_contract")
    if not isinstance(contract, dict):
        raise GoalContractError("Goal Contract missing from RUN state")
    stored_hash = str(state.get("goal_contract_hash") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", stored_hash):
        raise GoalContractError("RUN goal_contract_hash missing or invalid")
    digest = contract_hash(contract)
    if digest != stored_hash or digest != contract.get("contract_hash"):
        raise GoalContractError("Goal Contract identity mismatch in RUN state")
    if _normalize_text(state.get("goal", "")) != contract["goal"]:
        raise GoalContractError("RUN GOAL differs from frozen Goal Contract")
    revision = int(state.get("goal_contract_revision") or 0)
    if revision < 1 or revision != int(contract.get("contract_revision") or 0):
        raise GoalContractError("Goal Contract revision mismatch")
    path_text = str(state.get("goal_contract_path") or "")
    if not path_text:
        raise GoalContractError("Goal Contract persistent path missing")
    path = Path(path_text)
    if not path.is_file():
        raise GoalContractError("Goal Contract persistent file missing")
    try:
        on_disk = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise GoalContractError(f"Goal Contract persistent file unreadable: {type(exc).__name__}") from exc
    if on_disk != contract or contract_hash(on_disk) != stored_hash:
        raise GoalContractError("Goal Contract persistent file identity mismatch")
    return contract


def _contract_block(rt, state: dict[str, Any], exc: Exception) -> None:
    rt.hard_block(state, f"GOAL_CONTRACT_BLOCKED: {type(exc).__name__}: {exc}")


def _binding_block(contract: dict[str, Any], *, include_body: bool = True) -> str:
    acceptance = "\n".join(f"- {item}" for item in contract["acceptance_criteria"]) or "- NONE"
    constraints = "\n".join(f"- {item}" for item in contract["constraints"]) or "- NONE"
    body = (
        "[Goal Contract Lite | frozen binding]\n"
        f"GOAL_CONTRACT_HASH={contract['contract_hash']}\n"
        f"GOAL_CONTRACT_REVISION={contract['contract_revision']}\n"
    )
    if include_body:
        body += (
            f"GOAL:\n{contract['goal']}\n"
            f"ACCEPTANCE_CRITERIA:\n{acceptance}\n"
            f"CONSTRAINTS:\n{constraints}\n"
        )
    return body


def _assert_reply_binding(reply: str, expected_hash: str, *, required: bool, actor: str) -> None:
    found = CONTRACT_HASH_RE.findall(reply or "")
    if required and not found:
        raise GoalContractError(f"{actor} reply missing GOAL_CONTRACT_HASH binding")
    if found and any(value != expected_hash for value in found):
        raise GoalContractError(f"{actor} reply Goal Contract identity mismatch")


def _parse_list_file(path: str | None) -> list[str] | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        raise GoalContractError(f"contract input file missing: {path}")
    text = p.read_text(encoding="utf-8", errors="strict")
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        value = json.loads(stripped)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise GoalContractError(f"contract list file must be JSON string array: {path}")
        return value
    return [line.strip() for line in text.splitlines() if line.strip()]


def _parse_policy_file(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        raise GoalContractError(f"contract input file missing: {path}")
    value = json.loads(p.read_text(encoding="utf-8", errors="strict") or "{}")
    if not isinstance(value, dict):
        raise GoalContractError(f"egress policy file must be a JSON object: {path}")
    return value


def _extract_contract_options(argv: list[str]) -> tuple[list[str], dict[str, Any]]:
    cleaned: list[str] = []
    acceptance: list[str] = []
    constraints: list[str] = []
    acceptance_file = None
    constraints_file = None
    egress_policy_file = None
    i = 0
    while i < len(argv):
        token = argv[i]
        if token in ("--acceptance", "--constraint", "--acceptance-file", "--constraints-file",
                     "--egress-policy-file"):
            if i + 1 >= len(argv):
                raise GoalContractError(f"{token} requires a value")
            value = argv[i + 1]
            if token == "--acceptance":
                acceptance.append(value)
            elif token == "--constraint":
                constraints.append(value)
            elif token == "--acceptance-file":
                acceptance_file = value
            elif token == "--constraints-file":
                constraints_file = value
            else:
                egress_policy_file = value
            i += 2
            continue
        cleaned.append(token)
        i += 1
    file_acceptance = _parse_list_file(acceptance_file)
    file_constraints = _parse_list_file(constraints_file)
    file_policy = _parse_policy_file(egress_policy_file)
    if file_acceptance is not None:
        acceptance.extend(file_acceptance)
    if file_constraints is not None:
        constraints.extend(file_constraints)
    return cleaned, {"acceptance": acceptance, "constraints": constraints,
                     "data_egress_policy": file_policy or {}}


def install(rt, contract_options: dict[str, Any]) -> None:
    """Install thin Goal Contract bindings around the frozen Runtime functions."""
    original_new_run = rt._new_run
    original_router_send = rt._router_send_to_role
    original_router_review = rt._router_review_envelope
    original_cmd_send = rt.cmd_send
    original_cmd_recv = rt.cmd_recv
    original_cmd_done = rt.cmd_done
    original_cmd_step = rt.cmd_step
    original_cmd_directive = rt.cmd_directive
    original_router_continue = getattr(rt, "cmd_router_continue", None)

    def contract_new_run(goal: str, r_url: str, worker_id: str) -> dict[str, Any]:
        state = original_new_run(goal, r_url, worker_id)
        contract = build_contract(
            goal,
            contract_options.get("acceptance") or None,
            contract_options.get("constraints") or None,
            revision=1,
            data_egress_policy=contract_options.get("data_egress_policy") or None,
        )
        persist_contract(rt, state, contract, event="GOAL_CONTRACT_CREATED")
        return state

    def contract_router_review(state: dict[str, Any], builder_reply: str, round_no: int) -> str:
        contract = require_contract(rt, state)
        return (
            _binding_block(contract)
            + "Review the Builder output ONLY against this exact Goal Contract identity.\n\n"
            + original_router_review(state, builder_reply, round_no)
        )

    def contract_router_send(state: dict[str, Any], role: str, message: str, timeout: int):
        contract = require_contract(rt, state)
        outbound = message
        if role == "builder":
            if state["router"]["phase"] == "SEND_GOAL_TO_BUILDER":
                outbound = (
                    _binding_block(contract)
                    + "Execute only this frozen contract. Your complete result MUST contain a line exactly:\n"
                    + f"GOAL_CONTRACT_HASH={contract['contract_hash']}\n"
                    + "Do not change GOAL, Acceptance Criteria, Constraints, or this hash.\n"
                )
            else:
                outbound = (
                    _binding_block(contract, include_body=False)
                    + "This is REWORK under the SAME frozen Goal Contract. Your updated result MUST retain:\n"
                    + f"GOAL_CONTRACT_HASH={contract['contract_hash']}\n\n"
                    + message
                )
        reply, reply_path = original_router_send(state, role, outbound, timeout)
        _assert_reply_binding(
            reply, contract["contract_hash"],
            required=(role == "builder"), actor=role,
        )
        return reply, reply_path

    def _require_run(args):
        state = rt.load_state(args.run_id)
        try:
            require_contract(rt, state)
        except GoalContractError as exc:
            _contract_block(rt, state, exc)
            raise
        return state

    def contract_cmd_send(args):
        try:
            state = _require_run(args)
        except GoalContractError:
            rt.emit({"status": "HARD_BLOCKED", "reason": "Goal Contract missing or invalid"})
            return rt.EXIT_HARD_BLOCKED
        contract = state["goal_contract"]
        if args.message_file:
            src = Path(args.message_file)
            if src.is_file():
                bound = rt.run_dir(args.run_id) / f"contract_bound_{src.name}"
                rt.atomic_write_text(bound, _binding_block(contract) + "\n" + src.read_text(encoding="utf-8", errors="replace"))
                args = argparse.Namespace(**vars(args))
                args.message_file = str(bound)
        elif args.message:
            bound = rt.run_dir(args.run_id) / f"contract_bound_msg_{os.getpid()}.txt"
            rt.atomic_write_text(bound, _binding_block(contract) + "\n" + args.message)
            args = argparse.Namespace(**vars(args))
            args.message = ""
            args.message_file = str(bound)
        code = original_cmd_send(args)
        state_after = rt.load_state(args.run_id)
        path = state_after.get("last_reply_path")
        if path and Path(path).is_file():
            try:
                _assert_reply_binding(
                    Path(path).read_text(encoding="utf-8", errors="replace"),
                    contract["contract_hash"], required=False, actor="reviewer",
                )
            except GoalContractError as exc:
                _contract_block(rt, state_after, exc)
                return rt.EXIT_HARD_BLOCKED
        return code

    def contract_cmd_recv(args):
        try:
            state = _require_run(args)
        except GoalContractError:
            rt.emit({"status": "HARD_BLOCKED", "reason": "Goal Contract missing or invalid"})
            return rt.EXIT_HARD_BLOCKED
        code = original_cmd_recv(args)
        state_after = rt.load_state(args.run_id)
        path = state_after.get("last_reply_path")
        if path and Path(path).is_file():
            try:
                _assert_reply_binding(Path(path).read_text(encoding="utf-8", errors="replace"),
                                      state["goal_contract_hash"], required=False, actor="reviewer")
            except GoalContractError as exc:
                _contract_block(rt, state_after, exc)
                return rt.EXIT_HARD_BLOCKED
        return code

    def contract_cmd_done(args):
        try:
            _require_run(args)
        except GoalContractError:
            rt.emit({"status": "HARD_BLOCKED", "reason": "Goal Contract missing or invalid"})
            return rt.EXIT_HARD_BLOCKED
        return original_cmd_done(args)

    def contract_cmd_step(args):
        try:
            _require_run(args)
        except GoalContractError:
            rt.emit({"status": "HARD_BLOCKED", "reason": "Goal Contract missing or invalid"})
            return rt.EXIT_HARD_BLOCKED
        return original_cmd_step(args)

    def contract_cmd_directive(args):
        try:
            _require_run(args)
        except GoalContractError:
            rt.emit({"status": "HARD_BLOCKED", "reason": "Goal Contract missing or invalid"})
            return rt.EXIT_HARD_BLOCKED
        if str(args.action or "").upper() == "CHANGE_SCOPE":
            rt.emit({
                "status": "DENIED",
                "reason": "CHANGE_SCOPE cannot mutate a frozen Goal Contract in place",
                "instruction": "Use contract-revise with explicit Goal/Acceptance/Constraints changes so a new Goal Contract revision is created.",
            })
            return rt.EXIT_DENIED
        return original_cmd_directive(args)

    def contract_cmd_router_continue(args):
        try:
            _require_run(args)
        except GoalContractError:
            rt.emit({"status": "HARD_BLOCKED", "reason": "Goal Contract missing or invalid"})
            return rt.EXIT_HARD_BLOCKED
        return original_router_continue(args)

    rt._new_run = contract_new_run
    rt._router_review_envelope = contract_router_review
    rt._router_send_to_role = contract_router_send
    rt.cmd_send = contract_cmd_send
    rt.cmd_recv = contract_cmd_recv
    rt.cmd_done = contract_cmd_done
    rt.cmd_step = contract_cmd_step
    rt.cmd_directive = contract_cmd_directive
    if original_router_continue is not None:
        rt.cmd_router_continue = contract_cmd_router_continue


def _read_goal_file(path: str | None, current: str) -> str:
    if not path:
        return current
    p = Path(path)
    if not p.is_file():
        raise GoalContractError(f"goal file missing: {path}")
    value = p.read_text(encoding="utf-8", errors="strict").strip()
    if not value:
        raise GoalContractError("revised GOAL is empty")
    return value


def cmd_contract_revise(rt, argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="contract-revise")
    p.add_argument("--run-id", required=True)
    p.add_argument("--goal-file")
    p.add_argument("--acceptance", action="append", default=[])
    p.add_argument("--acceptance-file")
    p.add_argument("--constraint", action="append", default=[])
    p.add_argument("--constraints-file")
    p.add_argument("--note", required=True)
    args = p.parse_args(argv)
    try:
        state = rt.load_state(args.run_id)
        current = require_contract(rt, state)
        if state.get("status") not in ("RUNNING", "PAUSED"):
            rt.emit({"status": "DENIED", "reason": "contract-revise requires RUNNING or PAUSED"})
            return rt.EXIT_DENIED
        goal = _read_goal_file(args.goal_file, current["goal"])
        acceptance = list(current["acceptance_criteria"])
        constraints = list(current["constraints"])
        if args.acceptance_file:
            acceptance = _parse_list_file(args.acceptance_file) or []
        if args.acceptance:
            acceptance = args.acceptance
        if args.constraints_file:
            constraints = _parse_list_file(args.constraints_file) or []
        if args.constraint:
            constraints = args.constraint
        proposed = build_contract(goal, acceptance, constraints,
                                  revision=int(current["contract_revision"]) + 1)
        if proposed["contract_hash"] == current["contract_hash"]:
            rt.emit({"status": "NO_CONTRACT_CHANGE", "run_id": args.run_id,
                     "goal_contract_hash": current["contract_hash"],
                     "goal_contract_revision": current["contract_revision"]})
            return rt.EXIT_OK
        old_hash = current["contract_hash"]
        state["last_r_verdict"] = None
        state["last_r_next_action"] = ""
        state["last_reply_path"] = None
        state["last_reply_bytes"] = 0
        state["last_action_fingerprint"] = None
        if state.get("mode") == getattr(rt, "ROUTER_MODE", None) and isinstance(state.get("router"), dict):
            state["router"].update({
                "phase": "SEND_GOAL_TO_BUILDER",
                "round": 0,
                "last_builder_reply_path": None,
                "last_builder_reply_bytes": 0,
                "last_review_reply_path": None,
                "pending_rework": "",
            })
            state["current_step"] = "router: Goal Contract revised by explicit user command"
            state["next_action"] = "router-step: dispatch revised Goal Contract to builder"
        persist_contract(rt, state, proposed, event="GOAL_CONTRACT_REVISED",
                         old_hash=old_hash, note=args.note)
        rt.emit({"status": "OK", "run_id": args.run_id,
                 "goal_contract_hash": proposed["contract_hash"],
                 "goal_contract_revision": proposed["contract_revision"],
                 "old_goal_contract_hash": old_hash})
        return rt.EXIT_OK
    except GoalContractError as exc:
        try:
            state = rt.load_state(args.run_id)
            _contract_block(rt, state, exc)
        except Exception:
            pass
        rt.emit({"status": "HARD_BLOCKED", "reason": str(exc)})
        return rt.EXIT_HARD_BLOCKED


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    rt = _load_runtime()
    if argv and argv[0] == "contract-revise":
        return cmd_contract_revise(rt, argv[1:])
    try:
        cleaned, options = _extract_contract_options(argv)
    except (GoalContractError, json.JSONDecodeError) as exc:
        rt.emit({"status": "HARD_BLOCKED", "reason": f"Goal Contract input invalid: {exc}"})
        return rt.EXIT_HARD_BLOCKED
    install(rt, options)
    ec.install_telemetry(rt)  # V0.6-C: auto EC telemetry on step/recv paths
    sys.argv = [str(HERE / "runtime.py"), *cleaned]
    return rt.main()


if __name__ == "__main__":
    sys.exit(main())
