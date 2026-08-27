"""Independent rerunnable Evidence driver for V07-INTEGRATE-2 verification.

Usage:
  python runtime/v07_integration_evidence.py --candidate <40-char-HEAD> --preflight
  python runtime/v07_integration_evidence.py --candidate <40-char-HEAD>

Full mode fails if B1's test-only adapter is unbound. Success is machine asserted
by command exits plus the explicit final marker; no Builder prose counts.
"""
from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
from pathlib import Path

from v07_integration_verify_support import BASE_COMMIT, SUCCESS_MARKER

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

# Existing production/control surfaces B2 is not allowed to alter. Keeping these
# byte-identical to the frozen base plus running the complete runtime offline suite
# prevents a verification-only branch from silently changing V0.1-V0.6 behavior.
LEGACY_NO_DIFF_PATHS = (
    "src",
    "tests",
    "runtime/runtime.py",
    "runtime/strategic_brain_contract.py",
    "runtime/strategic_correction.py",
    "runtime/strategic_reuse_contract.py",
)


def run(cmd, env=None):
    """Run one fail-fast evidence command with deterministic UTF-8 child stdio."""
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


def require_legacy_surfaces_unchanged():
    # The frozen repository's top-level legacy suite contains machine-bound paths
    # (local Python/browser profile). Do not weaken those tests or pretend they are
    # portable: prove the legacy code/tests are byte-identical to the accepted base,
    # then run every portable runtime offline test plus the core store/path smoke.
    run(["git", "diff", "--exit-code", BASE_COMMIT, "--", *LEGACY_NO_DIFF_PATHS])
    print("REGRESSION_LEGACY_SURFACES=UNCHANGED_FROM_FROZEN_BASE")


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
    require_legacy_surfaces_unchanged()

    for test in (
        "runtime/test_strategic_brain_contract_offline.py",
        "runtime/test_strategic_correction_offline.py",
        "runtime/test_strategic_reuse_contract_offline.py",
        "runtime/test_strategic_integration_offline.py",
        "runtime/test_v07_integration_contract_matrix_offline.py",
    ):
        run([PYTHON, test])

    # Complete runtime offline regression, including B1 smoke and B2 candidate
    # attack tests when the adapter is bound.
    run([PYTHON, "-m", "unittest", "discover", "-s", "runtime", "-p", "test_*_offline.py"])
    run([PYTHON, "tests/test_core.py"])

    if args.preflight:
        print("V07_INTEGRATE2_PREFLIGHT_SUCCESS=" + args.candidate)
        print("WAITING_FOR_B1=" + ("false" if adapter_bound() else "true"))
        return 0

    if not adapter_bound():
        raise SystemExit("EVIDENCE_FAIL=B1_INTERFACE_NOT_BOUND")

    # Run the candidate attack file explicitly again as the final integration gate.
    run([PYTHON, "runtime/test_v07_integration_candidate_offline.py"])
    print(f"{SUCCESS_MARKER} candidate={args.candidate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
