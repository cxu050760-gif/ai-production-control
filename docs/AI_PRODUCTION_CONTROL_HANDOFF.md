# DEPRECATED / HISTORICAL — AI Production Control Handoff

This handoff predates V0.1 Official Runtime Entry canonicalization and must not be used to choose or start the current Runtime.

Current Worker handoff:

1. Read `runtime/WEAK_WORKER_START_HERE.md`.
2. Use `E:\WB\tools\ai-production-control\runtime\run.cmd` as the only OFFICIAL Runtime Entry.
3. Treat `ai-control.cmd` / `scripts/ai_control.py` as COMPATIBILITY / LEGACY Controller surfaces only.
4. Do not require a normal Worker to operate Bridge, daemon, session, marker, click, or browser-runtime internals directly.

The former Controller-oriented handoff is historical context only and is intentionally superseded for current entry selection.
