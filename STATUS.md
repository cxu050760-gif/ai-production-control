# Status

- Mission: provider-independent AI production system controlled by durable canonical state and evidence.
- Current stage: `PRODUCT_NOT_READY` infrastructure/product construction.
- Target production entry: `ai-control.cmd run "<goal>"`.
- Stable code root: `E:\WB\tools\ai-production-control`.
- Stable state root: `E:\WB\state\ai-production-control`.
- Stable output root: `E:\WB\outputs\ai-production-control`.
- Verified local foundation: canonical SQLite state, authority/effect journals, scoped side effects, source-bound actors, diagnostics, and digest-bound release primitives.
- Blocking product gap: no general Goal Worker/Workflow adapter and no unified execute/test/review/rework/resume workflow.
- The deterministic local Worker is a capability probe only; its artifact cannot pass the delivery contract.
- The 2026-08-17 A01-A65 manifest is historical evidence for that digest, not current product readiness.
- M0.5 hardening is implemented locally: Release now requires canonical task/Goal/state/context/digest-bound test and Reviewer records; fallback Providers use authorization/egress/Effect WAL; incomplete Reviewer envelopes and malformed adapter outcomes fail closed.
- M0.5 targeted regression is 20/20 PASS and Runtime V1 offline regression remains 55/55 PASS. Independent Reviewer re-review is still required before M1.
- Any TCB change remains `UNVERIFIED_AFTER_CONTROLLER_CHANGE` until a new bounded regression and seal; do not infer release readiness from unit tests.
