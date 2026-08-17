# Rollback Record

## Baseline

- `E:\WB\tools\ai-production-control`, `E:\WB\state\ai-production-control`, and `E:\WB\outputs\ai-production-control` did not exist before this mission.
- `E:\WB\tools\bsk-file-bridge` and `E:\AI_Projects\ChatGPT_Codex_Bridge` are reuse assets and are not modified by this project.

## Recovery

- Code recovery: local Git history plus a digest-bound release candidate.
- State recovery: latest known-good immutable Canonical State snapshot, then Effect WAL scan, Authority Commit Journal replay, authority-generation verification, unresolved-effect reconciliation, and a new recovered revision.
- If Authority Journal integrity/latest generation cannot be proven: `AUTHORITY_STATE_UNCERTAIN`, fail closed, no new external effect.
- Controller change: mark `UNVERIFIED_AFTER_CONTROLLER_CHANGE`, rerun required regression, then seal a new TCB generation.

## Removal (not executed)

Stopping runtime processes and removing the three newly created roots would return to the pre-mission filesystem layout. Removal is intentionally not automated because it is destructive and would discard evidence/state.

