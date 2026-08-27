"""Independent rerunnable Evidence driver for V07-INTEGRATE-2 verification.

Usage:
  python runtime/v07_integration_evidence.py --candidate <40-char-HEAD> --preflight
  python runtime/v07_integration_evidence.py --candidate <40-char-HEAD>

Full mode fails if B1's test-only adapter is still unbound. Success is machine
asserted by command exits plus the explicit final marker; no Builder prose counts.
"""
from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
from pathlib import Path

from v07_integration_verify_support import BASE_COMMIT, SUCCESS_MARKER

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run(cmd, env=None):
    print("EVIDENCE_RUN=" + " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env, text=True)
    if proc.returncode != 0:
        print("EVIDENCE_FAIL=" + " ".join(cmd), flush=True)
        raise SystemExit(proc.returncode or 1)


def capture(*args):
    return subprocess.check_output(args, cwd=str(ROOT), text=True).strip()


def require_git_binding(candidate):
    if len(candidate) != 40 or any(c not in "0123456789abcdef" for c in candidate.lower()):
        raise SystemExit("EVIDENCE_FAIL=candidate must be an exact 40-char commit SHA")
    head = capture("git", "rev-parse", "HEAD")
    if head != candidate:
        raise SystemExit(f"EVIDENCE_FAIL=HEAD_MISMATCH expected={candidate} actual={head}")
    run(["git", "merge-base", "--is-ancestor", BASE_COMMIT, candidate])
    dirty = capture("git", "status", "--porcelain")
    if dirty:
        raise SystemExit("EVIDENCE_FAIL=WORKTREE_DIRTY")
    print(f"EVIDENCE_CANDIDATE={candidate}")
    print(f"EVIDENCE_BASE={BASE_COMMIT}")


def adapter_bound():
    mod = importlib.import_module("v07_integration_candidate_adapter")
    return bool(mod.is_bound())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--preflight", action="store_true",
                        help="run base-contract + regression evidence without claiming B1 integration success")
    args = parser.parse_args()

    require_git_binding(args.candidate)

    for test in (
        "runtime/test_strategic_brain_contract_offline.py",
        "runtime/test_strategic_correction_offline.py",
        "runtime/test_strategic_reuse_contract_offline.py",
        "runtime/test_v07_integration_contract_matrix_offline.py",
    ):
        run([PYTHON, test])

    run([PYTHON, "-m", "unittest", "discover", "-s", "runtime", "-p", "test_*_offline.py"])
    run([PYTHON, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"])

    if args.preflight:
        print("V07_INTEGRATE2_PREFLIGHT_SUCCESS=" + args.candidate)
        print("WAITING_FOR_B1=" + ("false" if adapter_bound() else "true"))
        return 0

    if not adapter_bound():
        raise SystemExit("EVIDENCE_FAIL=B1_INTERFACE_NOT_BOUND")

    run([PYTHON, "runtime/test_v07_integration_candidate_offline.py"])
    print(f"{SUCCESS_MARKER} candidate={args.candidate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
