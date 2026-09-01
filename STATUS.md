# Status

- Mission: provider-independent AI production system controlled by durable canonical state and evidence.
- Current stage: `PRODUCT_NOT_READY` infrastructure/product construction.
- Official Runtime Entry: `E:\WB\tools\ai-production-control\runtime\run.cmd`.
- Legacy Controller surfaces: `ai-control.cmd` and `scripts/ai_control.py` are COMPATIBILITY / LEGACY only; they are not a second OFFICIAL Runtime Entry.
- Stable code root: `E:\WB\tools\ai-production-control`.
- Stable state root: `E:\WB\state\ai-production-control`.
- Stable output root: `E:\WB\outputs\ai-production-control`.
- Verified local foundation: canonical SQLite state, authority/effect journals, scoped side effects, source-bound actors, diagnostics, and digest-bound release primitives.
- Blocking product gap: no general Goal Worker/Workflow adapter and no unified execute/test/review/rework/resume workflow.
- The deterministic local Worker is a capability probe only; its artifact cannot pass the delivery contract.
- The 2026-08-17 A01-A65 manifest is historical evidence for that digest, not current product readiness.
- M0.5 hardening is implemented locally: Release now requires canonical task/Goal/state/context/digest-bound test and Reviewer records; fallback Providers use authorization/egress/Effect WAL; incomplete Reviewer envelopes and malformed adapter outcomes fail closed.
- M0.5 targeted regression is 20/20 PASS and Runtime V1 offline regression remains 55/55 PASS. The same independent ChatGPT Reviewer returned `VERDICT=PASS / M0_5_STATUS=VERIFIED / ALLOW_M1=YES` for code commit `63217a8`; M1 is unblocked but has not started.
- Any TCB change remains `UNVERIFIED_AFTER_CONTROLLER_CHANGE` until a new bounded regression and seal; do not infer release readiness from unit tests.

## 2026-09-01 capability delta (git verified)

- Master HEAD: `2f1188a` (2026-09-01 17:25:54 +0800). Full authority for trunk state is `PROJECT_STATE.json` / `PROJECT_STATE.md` (this file is a derived view).
- DeepSeek is now a first-class channel (`chat.deepseek.com/a/chat/s/<id>` alongside `chatgpt.com/c/<id>`): three modes (fast/expert/vision) auto-routed by the runtime and bound per conversation. Commits `9e1f99c`, `fffd0d3`, `63208d5`.
- Completion marker renamed to neutral `===WB_DONE===` across both channels (was `CHATGPT_DONE`). Commit `8525138`.
- Effect-safety triple wired at RUN start in `runtime/goal_contract_lite.py` (minimal egress policy defaulting to INTERNAL-only, per-run TCB declaration, review-transport authorization via `grant_authorization`). Commit `2f1188a`.
- Seed session reused preferentially in `runtime/lib/yz_ds_lib.sh` to preserve review context (opens another only when the seed is unreachable / mode-mismatched / busy).
- This entry is an additive refresh of expired master-head facts; historical sections above are retained unchanged.