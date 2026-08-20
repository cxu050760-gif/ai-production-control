# AI Production Control Plane

A Windows-local, single-host Controller for durable goals, scoped authorization, monotonic authority recovery, logical-effect deduplication, worker/brain source binding, browser automation, evidence, acceptance, and digest-bound release candidates.

The target official user entry is:

```powershell
E:\WB\tools\ai-production-control\ai-control.cmd run "<goal>"
```

Operational commands include `status`, `resume`, `doctor`, `selftest`, `brain`, `worker`, `browser`, `review`, `acceptance`, `tcb`, and `release`. These are operator/diagnostic surfaces; normal use remains `run`.

Current product boundary: `run` is wired to a brokered local capability-probe Worker, not a general Goal executor. The Controller therefore returns `PRODUCT_NOT_READY` and preserves the probe as evidence instead of promoting it to a release artifact. A `GENERAL_GOAL_EXECUTION` Worker/Workflow adapter and unified test/review/rework path are required before this entry can claim Goal completion.

Release is fail-closed: acceptance and independent review manifests must be registered as Controller-owned canonical Evidence and source-bound to the same task, Goal Contract, Canonical State revision, Context Fence, artifact digest, canonical test executions, verified Reviewer result, and committed Effect. Empty, forged, stale, cross-task, cross-digest, or incomplete inputs are rejected.

The untracked `runtime` tree is an existing ChatGPT review/REWORK transport candidate. It is not the canonical product entry and must not become a second authority store.

Persistent state is stored in `E:\WB\state\ai-production-control`; evidence and release outputs are stored in `E:\WB\outputs\ai-production-control`. Browser profiles remain browser-runtime-only credential containers.
