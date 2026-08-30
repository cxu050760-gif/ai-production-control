# AI Production Control Plane

A Windows-local, single-host Controller for durable goals, scoped authorization, monotonic authority recovery, logical-effect deduplication, worker/brain source binding, browser automation, evidence, acceptance, and digest-bound release candidates.

## V0.1 Official Runtime Entry

The only OFFICIAL Runtime Entry for V0.1 is:

```powershell
E:\WB\tools\ai-production-control\runtime\run.cmd
```

For Worker operation and recovery, start from `runtime/WEAK_WORKER_START_HERE.md`. The Runtime owns Bridge/daemon/session/marker details; normal Workers do not invoke those internals directly.

`ai-control.cmd` and `scripts/ai_control.py` are COMPATIBILITY / LEGACY Controller surfaces retained for historical diagnostics and compatibility. They are not a second OFFICIAL Runtime Entry.

Legacy Controller commands include `run`, `status`, `resume`, `doctor`, `selftest`, `brain`, `worker`, `browser`, `review`, `acceptance`, `tcb`, and `release`. These remain legacy/diagnostic surfaces and do not replace `runtime/run.cmd` as the V0.1 production entry.

Legacy Controller boundary: `ai-control.cmd run` is wired to a brokered local capability-probe Worker, not a general Goal executor. The legacy Controller therefore returns `PRODUCT_NOT_READY` and preserves the probe as evidence instead of promoting it to a release artifact. A `GENERAL_GOAL_EXECUTION` Worker/Workflow adapter and unified test/review/rework path would be required before that legacy surface could claim Goal completion.

Release is fail-closed: acceptance and independent review manifests must be registered as Controller-owned canonical Evidence and source-bound to the same task, Goal Contract, Canonical State revision, Context Fence, artifact digest, canonical test executions, verified Reviewer result, and committed Effect. Empty, forged, stale, cross-task, cross-digest, or incomplete inputs are rejected.

The tracked `runtime` tree is the canonical V0.1 Runtime surface. Its only OFFICIAL Runtime Entry is `runtime/run.cmd`; it must not be bypassed by introducing another launcher or authority store.

Persistent state is stored in `E:\WB\state\ai-production-control`; evidence and release outputs are stored in `E:\WB\outputs\ai-production-control`. Browser profiles remain browser-runtime-only credential containers.
