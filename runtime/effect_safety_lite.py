#!/usr/bin/env python3
"""Slice I Minimum Effect Safety Lite integration for the single OFFICIAL Runtime entry.

Minimum real side-effect safety: every real side effect performed by the official
runtime (the outbound review transport) gets a durable, deduplicated, hash-bound
logical-effect record in the canonical runtime-v1 state.json + journal.jsonl, and
is fail-closed when a precondition is denied or the record cannot be made durable.

Reuse (not rebuild): identity primitives come from src/aicontrol/util
(canonical_json + sha256_text), the same serialization/hash the Legacy Effect
Safety system uses; durability reuses the official runtime's atomic_write /
save_state / journal. The full TCB-gated ControlStore.reserve_effect chain is
deliberately NOT wired here (it requires a sealed/VERIFIED TCB, which the current
runtime has not achieved); that remains a deferred hardening item (record, not fix).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aicontrol.util import canonical_json, sha256_text  # noqa: E402

EFFECT_SCHEMA_VERSION = 1


class EffectSafetyError(RuntimeError):
    pass


class EffectDenied(EffectSafetyError):
    pass


def _load_runtime():
    spec = importlib.util.spec_from_file_location("apc_runtime_core_i", HERE / "runtime.py")
    if spec is None or spec.loader is None:
        raise EffectSafetyError("runtime.py loader unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def effect_identity(run_id: str, slot: str, payload_hash: str) -> str:
    core = {"task_id": run_id, "logical_effect_slot": slot, "payload_hash": payload_hash}
    return sha256_text(canonical_json(core))


def record_effect(rt, state: dict, *, operation: str, destination: str, payload_hash: str,
                  slot: str, purpose: str,
                  capability_permitted: bool = True, egress_permitted: bool = True,
                  resource_fresh: bool = True) -> dict[str, Any]:
    """Durable, deduplicated logical-effect record; fail-closed on denial."""
    if not (capability_permitted and egress_permitted and resource_fresh):
        raise EffectDenied("capability, egress, or resource precondition denied")
    if not payload_hash or len(payload_hash) != 64:
        raise EffectDenied("payload_hash missing or invalid")
    logical_effect_id = effect_identity(state["run_id"], slot, payload_hash)
    prior = state.get("effect_safety_log") or []
    deduplicated = any(rec.get("logical_effect_id") == logical_effect_id for rec in prior)
    record = {
        "schema_version": EFFECT_SCHEMA_VERSION,
        "logical_effect_id": logical_effect_id,
        "logical_effect_slot": slot,
        "operation": operation,
        "destination": destination,
        "payload_hash": payload_hash,
        "purpose": purpose,
        "deduplicated": bool(deduplicated),
        "status": "RESERVED",
    }
    if not deduplicated:
        prior.append(record)
    state["effect_safety_log"] = prior
    state["effect_safety"] = record
    rt.save_state(state)
    rt.journal(state["run_id"], "EFFECT_RESERVED",
               logical_effect_id=logical_effect_id, slot=slot,
               deduplicated=bool(deduplicated), operation=operation)
    return record


def install(rt, options: dict) -> None:
    original_cmd_send = rt.cmd_send

    def gated_cmd_send(args):
        state = rt.load_state(args.run_id)
        payload = (args.message or "") + json.dumps(sorted(getattr(args, "file", None) or []))
        payload_hash = sha256_text(payload)
        try:
            record_effect(rt, state, operation="send",
                          destination=str(state.get("r_url") or ""),
                          payload_hash=payload_hash,
                          slot=f"send:{state.get('review_epoch', 1)}",
                          purpose="review transport")
        except EffectDenied as exc:
            rt.hard_block(state, f"EFFECT_SAFETY_DENIED: {exc}")
            rt.emit({"status": "HARD_BLOCKED", "reason": f"EFFECT_SAFETY_DENIED: {exc}"})
            return rt.EXIT_HARD_BLOCKED
        except Exception as exc:  # noqa: BLE001
            rt.hard_block(state, f"EFFECT_SAFETY_ERROR: {type(exc).__name__}: {exc}")
            rt.emit({"status": "HARD_BLOCKED", "reason": f"EFFECT_SAFETY_ERROR: {exc}"})
            return rt.EXIT_HARD_BLOCKED
        return original_cmd_send(args)

    rt.cmd_send = gated_cmd_send


def main(argv: list | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    rt = _load_runtime()
    install(rt, {})
    sys.argv = [str(HERE / "runtime.py"), *argv]
    return rt.main()


if __name__ == "__main__":
    sys.exit(main())
