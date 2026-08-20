from __future__ import annotations

"""Fresh Weak Worker conformance fixture (M1).

This worker intentionally has ZERO project history and ZERO knowledge of the
Bridge / browser / runtime internals. It receives only the stable high-level
task capsule from `request.json` and must:

1. discover its granted capabilities from the capsule,
2. perform a deterministic local transform inside its workspace,
3. return a source-bound, per-artifact digest-backed result envelope.

It never needs to understand `bsk`, `daemon`, `marker`, `yz_lib`, session
internals, click/DOM hacks, or any recovery mechanism. A `variant` field lets
two different registrations share this same code path to prove interchangeability.
"""

import hashlib
import json
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    capsule = request["capsule"]
    workspace = Path(request["workspace"]).resolve(strict=True)
    artifact = Path(request["artifact_path"]).resolve()
    if not artifact.is_relative_to(workspace):
        print(json.dumps({"status": "FAILED", "error": "artifact outside workspace"}))
        return 2
    variant = request.get("variant") or "alpha"
    capabilities = ", ".join(sorted(capsule.get("capabilities", [])))
    content = (
        "# Worker Artifact\n\n"
        f"variant: {variant}\n"
        f"task_id: {request['task_id']}\n"
        f"objective: {capsule.get('objective', '')}\n"
        f"granted capabilities: {capabilities}\n"
        "Fresh Weak Worker conformance fixture produced through the stable high-level contract only.\n"
    )
    artifact.write_text(content, encoding="utf-8")
    artifact_path = str(artifact)
    digest = sha256_file(artifact)
    envelope = {
        "schema_version": 1,
        "invocation_id": request["invocation_id"],
        "request_nonce": request["request_nonce"],
        "task_id": request["task_id"],
        "goal_contract_hash": request["goal_contract_hash"],
        "request_state_revision": request["request_state_revision"],
        "request_context_fence": request["request_context_fence"],
        "status": "DONE",
        "execution_class": "WORKER_CONFORMANCE_FIXTURE",
        "goal_satisfied": False,
        "artifact_paths": [artifact_path],
        "artifact_hashes": {artifact_path: digest},
        "evidence": [{"kind": "worker-output", "sha256": digest}],
        # A proposal the weak worker is allowed to submit; it never mutates
        # canonical facts itself.
        "action_proposals": [{"operation": "REQUEST_REVIEW", "reason": "fixture complete"}],
        "escalation_needed": False,
        "human_readable_notes": f"FRESH_WEAK_WORKER_CONFORMANCE_{variant.upper()}",
    }
    print(json.dumps(envelope, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())