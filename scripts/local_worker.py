from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".worker-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def inside(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((os.path.normcase(str(path)), os.path.normcase(str(root)))) == os.path.normcase(str(root))
    except ValueError:
        return False


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"status": "FAILED", "error": "request path required"}))
        return 2
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    workspace = Path(request["workspace"]).resolve(strict=True)
    output = Path(request["artifact_path"]).resolve(strict=False)
    if not inside(output, workspace):
        print(json.dumps({"status": "FAILED", "error": "artifact path outside worker workspace"}))
        return 3
    if request.get("start_here_path"):
        start_here = Path(request["start_here_path"]).resolve(strict=True)
        if start_here.name != "NEW_WORKER_START_HERE.md":
            print(json.dumps({"status": "FAILED", "error": "cold-start contract path rejected"}))
            return 4
        start_contract = start_here.read_text(encoding="utf-8")
    else:
        start_contract = ""
    goal = str(request["goal"])
    browser_observation = request.get("browser_observation") or "No browser observation was required."
    content = (
        "# Worker Artifact\n\n"
        f"Task: {request['task_id']}\n\n"
        f"Goal: {goal}\n\n"
        f"Browser observation: {browser_observation}\n\n"
        "Execution: capability probe created by the brokered local worker inside its isolated workspace.\n\n"
        "Goal satisfaction: NOT EVALUATED. This worker does not execute a general Goal.\n"
    )
    atomic_write(output, content)
    envelope = {
        "schema_version": 1,
        "invocation_id": request["invocation_id"],
        "request_nonce": request["request_nonce"],
        "task_id": request["task_id"],
        "goal_contract_version": request["goal_contract_version"],
        "goal_contract_hash": request["goal_contract_hash"],
        "request_state_revision": request["request_state_revision"],
        "request_context_fence": request["request_context_fence"],
        "status": "DONE",
        "execution_class": "CAPABILITY_PROBE",
        "goal_satisfied": False,
        "artifact_paths": [str(output)],
        "artifact_hashes": {str(output): digest(output)},
        "evidence": [{"kind": "worker-output", "sha256": digest(output)}],
        "unresolved_issues": ["GENERAL_GOAL_WORKER_NOT_CONFIGURED"],
        "action_proposals": [],
        "escalation_needed": False,
        "human_readable_notes": "BROKERED_LOCAL_WORKER_CAPABILITY_PROBE_ONLY",
        "cold_start_contract_hash": hashlib.sha256(start_contract.encode("utf-8")).hexdigest() if start_contract else None,
    }
    print(json.dumps(envelope, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
