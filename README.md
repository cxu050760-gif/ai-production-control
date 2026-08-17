# AI Production Control Plane

A Windows-local, single-host Controller for durable goals, scoped authorization, monotonic authority recovery, logical-effect deduplication, worker/brain source binding, browser automation, evidence, acceptance, and digest-bound release candidates.

The one official user entry is:

```powershell
E:\WB\tools\ai-production-control\ai-control.cmd run "<goal>"
```

Operational commands include `status`, `resume`, `doctor`, `selftest`, `brain`, `worker`, `browser`, `review`, `acceptance`, `tcb`, and `release`. These are operator/diagnostic surfaces; normal use remains `run`.

Persistent state is stored in `E:\WB\state\ai-production-control`; evidence and release outputs are stored in `E:\WB\outputs\ai-production-control`. Browser profiles remain browser-runtime-only credential containers.

