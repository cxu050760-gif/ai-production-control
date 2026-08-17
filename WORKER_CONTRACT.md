# Worker Contract

Workers receive an invocation id, nonce, task id, Goal Contract hash/version, Canonical State revision, Context Fence, capability grant, isolated workspace, and result channel.

They return:

```json
{
  "schema_version": 1,
  "invocation_id": "...",
  "request_nonce": "...",
  "task_id": "...",
  "goal_contract_version": 1,
  "goal_contract_hash": "...",
  "request_state_revision": 1,
  "request_context_fence": "...",
  "status": "DONE",
  "artifact_paths": [],
  "artifact_hashes": {},
  "evidence": [],
  "unresolved_issues": [],
  "action_proposals": [],
  "escalation_needed": false,
  "human_readable_notes": ""
}
```

The Controller validates the invocation source, state/fence bindings, schema, paths, hashes, evidence, and proposals. Worker self-report cannot authorize effects or make a REQUIRED test pass.

