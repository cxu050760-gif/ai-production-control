"""Independent full-candidate Evidence driver for V07-INTEGRATE-2.

Usage:
  python runtime/v07_integration_evidence.py \
      --candidate <FINAL_40_CHAR_SHA> \
      --core-commit <B1_REWORK_40_CHAR_SHA>

There is intentionally no preflight/partial-success mode. Structural Git binding
is verified before formal tests. The success marker is printed only after every
machine assertion and regression command succeeds.
"""
from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Set, Tuple

from v07_integration_verify_support import (
    BASE_COMMIT,
    CHANGED_PATH_ALLOWLIST,
    CORE_OWNED_PATHS,
    FAILED_CANDIDATE,
    SUCCESS_MARKER,
)

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def hard_fail(code: str) -> None:
    raise SystemExit("EVIDENCE_HARD_FAIL=" + code)


def run(cmd: List[str], env=None) -> None:
    proc_env = os.environ.copy()
    proc_env["PYTHONUTF8"] = "1"
    proc_env["PYTHONIOENCODING"] = "utf-8"
    if env:
        proc_env.update(env)
    print("EVIDENCE_RUN=" + " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT), env=proc_env, text=True)
    if proc.returncode != 0:
        print("EVIDENCE_FAIL=" + " ".join(cmd), flush=True)
        raise SystemExit(proc.returncode or 1)


def capture(*args: str) -> str:
    return subprocess.check_output(args, cwd=str(ROOT), text=True).strip()


def require_exact_sha(label: str, value: str) -> str:
    if not isinstance(value, str) or len(value) != 40:
        hard_fail(f"{label}_NOT_EXACT_40_CHAR_SHA")
    lowered = value.lower()
    if value != lowered or any(c not in "0123456789abcdef" for c in value):
        hard_fail(f"{label}_NOT_LOWER_HEX_SHA")
    return value


def parse_name_status(text: str, allowed_statuses: Set[str]) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    if not text:
        return rows
    for raw in text.splitlines():
        parts = raw.split("\t")
        if len(parts) != 2:
            hard_fail("DIFF_NAME_STATUS_RENAME_COPY_OR_MALFORMED")
        status, path = parts
        if status not in allowed_statuses:
            hard_fail(f"DIFF_STATUS_NOT_ALLOWED:{status}:{path}")
        rows.append((status, path))
    return rows


def require_exact_changed_path_allowlist(candidate: str) -> None:
    text = capture("git", "diff", "--name-status", f"{BASE_COMMIT}..{candidate}", "--")
    # All nine paths are absent at the Accepted Base, so the final base-bound
    # diff must show exactly nine additions. Delete/rename/copy/type-change fails.
    rows = parse_name_status(text, {"A"})
    paths = [path for _, path in rows]
    expected = set(CHANGED_PATH_ALLOWLIST)
    actual = set(paths)
    if len(paths) != len(CHANGED_PATH_ALLOWLIST) or len(actual) != len(paths):
        hard_fail(f"CHANGED_PATH_COUNT_NOT_EXACT_9:{len(paths)}")
    unexpected = sorted(actual - expected)
    missing = sorted(expected - actual)
    if unexpected:
        hard_fail("UNEXPECTED_CHANGED_PATHS:" + ",".join(unexpected))
    if missing:
        hard_fail("MISSING_CHANGED_PATHS:" + ",".join(missing))
    print("EVIDENCE_CHANGED_PATHS=EXACT_9_ALLOWLIST")


def require_core_binding(candidate: str, core_commit: str) -> None:
    # All ancestry/scope/core-immutability failures occur before formal tests.
    run(["git", "cat-file", "-e", f"{core_commit}^{{commit}}"])
    if core_commit == FAILED_CANDIDATE:
        hard_fail("CORE_COMMIT_IS_FROZEN_FAILED_CANDIDATE")
    run(["git", "merge-base", "--is-ancestor", BASE_COMMIT, candidate])
    run(["git", "merge-base", "--is-ancestor", FAILED_CANDIDATE, candidate])
    run(["git", "merge-base", "--is-ancestor", FAILED_CANDIDATE, core_commit])
    run(["git", "merge-base", "--is-ancestor", core_commit, candidate])

    # B1 rework itself must be a targeted successor: from the frozen failed
    # candidate to CORE_COMMIT, only the two already-existing B1-owned files may
    # be modified, and strategic_integration.py must actually change.
    core_delta = capture("git", "diff", "--name-status", f"{FAILED_CANDIDATE}..{core_commit}", "--")
    rows = parse_name_status(core_delta, {"M"})
    changed = {path for _, path in rows}
    if not changed:
        hard_fail("CORE_COMMIT_HAS_NO_CORE_REWORK_DELTA")
    illegal = sorted(changed - set(CORE_OWNED_PATHS))
    if illegal:
        hard_fail("CORE_COMMIT_OUT_OF_SCOPE_PATHS:" + ",".join(illegal))
    if "runtime/strategic_integration.py" not in changed:
        hard_fail("CORE_COMMIT_DID_NOT_CHANGE_STRATEGIC_INTEGRATION")

    # Once exact B1 CORE_COMMIT is merged, B2 may not touch either B1-owned file.
    run(["git", "diff", "--exit-code", f"{core_commit}..{candidate}", "--", *CORE_OWNED_PATHS])
    print(f"EVIDENCE_CORE_COMMIT={core_commit}")
    print("EVIDENCE_CORE_FILES_AFTER_CORE=IMMUTABLE")


def require_git_binding(candidate: str, core_commit: str) -> None:
    require_exact_sha("CANDIDATE", candidate)
    require_exact_sha("CORE_COMMIT", core_commit)

    head = capture("git", "rev-parse", "HEAD")
    if head != candidate:
        hard_fail(f"HEAD_MISMATCH:expected={candidate}:actual={head}")
    dirty = capture("git", "status", "--porcelain")
    if dirty:
        hard_fail("WORKTREE_DIRTY")

    require_core_binding(candidate, core_commit)
    require_exact_changed_path_allowlist(candidate)

    print(f"EVIDENCE_BASE={BASE_COMMIT}")
    print(f"EVIDENCE_FAILED_CANDIDATE={FAILED_CANDIDATE}")
    print(f"EVIDENCE_CANDIDATE={candidate}")


def adapter_bound() -> bool:
    mod = importlib.import_module("v07_integration_candidate_adapter")
    return bool(mod.is_bound())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--core-commit", required=True)
    args = parser.parse_args()

    require_git_binding(args.candidate, args.core_commit)
    if not adapter_bound():
        hard_fail("B1_INTERFACE_NOT_BOUND")

    run(["git", "diff", "--check", f"{BASE_COMMIT}..{args.candidate}"])
    run([PYTHON, "-m", "compileall", "runtime", "src", "tests"])

    for test in (
        "runtime/test_strategic_brain_contract_offline.py",
        "runtime/test_strategic_correction_offline.py",
        "runtime/test_strategic_reuse_contract_offline.py",
        "runtime/test_strategic_integration_offline.py",
        "runtime/test_v07_integration_contract_matrix_offline.py",
        "runtime/test_v07_integration_candidate_offline.py",
    ):
        run([PYTHON, test])

    run([PYTHON, "-m", "unittest", "discover", "-s", "runtime", "-p", "test_*_offline.py"])
    run([PYTHON, "tests/test_core.py"])

    # MUST remain the final Evidence output line.
    print(f"{SUCCESS_MARKER} candidate={args.candidate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
