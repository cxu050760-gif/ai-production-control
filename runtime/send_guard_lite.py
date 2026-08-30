#!/usr/bin/env python3
"""Slice J2 Send Guard Lite: compose Goal Contract binding + Effect Safety
authorization + EC-lite gate on the official runtime's send path, WITHOUT
modifying any of those modules.

Previously run.cmd routed `send` to goal_contract_lite only, so the
effect-safety gate was bypassed (and vice-versa). This adapter installs THREE
thin guards (each wraps rt.cmd_send) so a single real outbound side effect
enforces, outermost-first: (V0.6-B) the EC degradation/lifecycle gate, then
the frozen Goal Contract identity, then a deduplicated, authorized
logical-effect reservation. All fail-closed.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import goal_contract_lite as gc  # noqa: E402
import effect_safety_lite as es  # noqa: E402
import ec_lite as ec             # noqa: E402


def main(argv: list | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    rt = gc._load_runtime()
    cleaned, options = gc._extract_contract_options(argv)
    gc.install(rt, options)   # Goal Contract binding on send/recv/router/...
    es.install(rt, {})        # Effect Safety authorization on send
    ec.install(rt)            # V0.6-B EC gate outermost: HALT/STOP_RETRY block first
    sys.argv = [str(HERE / "runtime.py"), *cleaned]
    return rt.main()


if __name__ == "__main__":
    sys.exit(main())
