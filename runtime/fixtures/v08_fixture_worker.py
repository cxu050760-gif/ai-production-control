from __future__ import annotations

"""Fresh weak-worker fixture for the stable V0.8 Task Capsule only."""

import hashlib
import json
import sys
from pathlib import Path

CONTRACT_VERSION = "V0.8-ADAPTER-CORE-1"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _failed(capsule: dict, detail: str) -> int:
    binding = {
        "task_id": str(capsule.get("task_id", "invalid")),
        "invocation_id": str(capsule.get("invocation_id", "invalid")),
        "worker_id": str(capsule.get("worker_id", "invalid")),
        "context_id": str(capsule.get("context_id", "invalid")),
        "capsule_id": str(capsule.get("capsule_id", "invalid")),
        "artifact_set_id": str(capsule.get("artifact_set_id", "invalid")),
    }
    result = {
        "contract_version": CONTRACT_VERSION,
        "result_type": "WORKER_RESULT",
        "status": "FAILED",
        "source_binding": binding,
        "artifact_paths": [],
        "artifact_hashes": {},
        "error": {"code": "INVALID_TASK", "detail": detail},
        "notes": "fixture rejected task capsule",
    }
    print(json.dumps(result, ensure_ascii=False))
    return 2


def main() -> int:
    try:
        capsule = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        capsule = {}
        return _failed(capsule, "invalid task capsule")
    if not isinstance(capsule, dict):
        return _failed({}, "invalid task capsule")
    if capsule.get("contract_version") != CONTRACT_VERSION or capsule.get("capsule_type") != "TASK_CAPSULE":
        return _failed(capsule, "unsupported task capsule")
    declarations = capsule.get("artifact_declarations")
    if not isinstance(declarations, list) or not declarations:
        return _failed(capsule, "artifact declaration missing")

    artifact_paths: list[str] = []
    artifact_hashes: dict[str, str] = {}
    for item in declarations:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            return _failed(capsule, "artifact declaration invalid")
        relative = item["path"]
        target = Path.cwd() / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        content = (
            "V0.8 fresh worker artifact\n"
            f"worker_id={capsule['worker_id']}\n"
            f"task_id={capsule['task_id']}\n"
            f"context_id={capsule['context_id']}\n"
            f"objective={capsule['objective']}\n"
        )
        target.write_text(content, encoding="utf-8")
        artifact_paths.append(relative)
        artifact_hashes[relative] = _digest(target)

    binding = {
        "task_id": capsule["task_id"],
        "invocation_id": capsule["invocation_id"],
        "worker_id": capsule["worker_id"],
        "context_id": capsule["context_id"],
        "capsule_id": capsule["capsule_id"],
        "artifact_set_id": capsule["artifact_set_id"],
    }
    result = {
        "contract_version": CONTRACT_VERSION,
        "result_type": "WORKER_RESULT",
        "status": "DONE",
        "source_binding": binding,
        "artifact_paths": artifact_paths,
        "artifact_hashes": artifact_hashes,
        "error": None,
        "notes": "fresh weak-worker fixture complete",
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
