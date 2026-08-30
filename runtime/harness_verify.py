#!/usr/bin/env python3
"""Runtime -> WorkBuddy CLI unattended Candidate verification adapter.

This is deliberately a thin adapter around the existing WorkBuddy Parallel
launcher. It does not implement another worker pool. The launcher still owns
WorkBuddy CLI process creation; this module only creates the two-task Run-mode
batch required by the frozen launcher, checks both workers' durable metadata,
and binds deterministic machine evidence to an explicit Candidate commit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
DEFAULT_LAUNCHER = Path(r"C:\Users\17838\.workbuddy\skills\workbuddy-parallel\scripts\Invoke-WorkBuddyParallel.ps1")
DEFAULT_CONFIG_DIR = Path(r"C:\Users\17838\.workbuddy")
DEFAULT_PYTHON = Path(r"C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe")
DEFAULT_STATE_ROOT = Path(r"E:\WB\state\ai-production-control\runtime-v1")
DEFAULT_MODEL = "hy3"
DEFAULT_TIMEOUT = 1200
EXPECTED_WORKERS = ("candidate_verifier", "candidate_witness")
LAUNCHER_ALLOWED_TOOLS = frozenset({"Read", "Glob", "Grep", "Bash", "Write", "Edit", "WebSearch", "WebFetch"})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{uuid.uuid4().hex[:8]}")
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def emit(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def _require_sha(name: str, value: str) -> str:
    if not SHA_RE.fullmatch(value or ""):
        raise ValueError(f"{name} must be an explicit full 40-hex commit SHA")
    return value.lower()


def _tail(text: str | None, limit: int = 4000) -> str:
    return (text or "")[-limit:]


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 300,
         env: dict | None = None) -> tuple[int, str, str, float]:
    started = time.monotonic()
    cp = subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", timeout=timeout,
        check=False,
    )
    return cp.returncode, cp.stdout, cp.stderr, time.monotonic() - started


def _git() -> str:
    override = os.environ.get("APC_HARNESS_GIT")
    if override:
        return override
    fixed = Path(r"C:\Program Files\Git\cmd\git.exe")
    if fixed.exists():
        return str(fixed)
    found = shutil.which("git")
    if found:
        return found
    raise FileNotFoundError("git executable not found")


def _record_check(checks: list[dict], name: str, cmd: list[str], *, cwd: Path,
                  timeout: int, env: dict | None = None) -> bool:
    try:
        rc, out, err, duration = _run(cmd, cwd=cwd, timeout=timeout, env=env)
        checks.append({
            "name": name,
            "status": "SUCCEEDED" if rc == 0 else "FAILED",
            "exit_code": rc,
            "duration_seconds": round(duration, 3),
            "stdout_tail": _tail(out),
            "stderr_tail": _tail(err),
        })
        return rc == 0
    except subprocess.TimeoutExpired as exc:
        checks.append({
            "name": name, "status": "TIMEOUT", "exit_code": None,
            "duration_seconds": timeout,
            "stdout_tail": _tail(exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else exc.stdout),
            "stderr_tail": _tail(exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else exc.stderr),
        })
        return False
    except Exception as exc:
        checks.append({
            "name": name, "status": "ERROR", "exit_code": None,
            "duration_seconds": 0,
            "stdout_tail": "", "stderr_tail": f"{type(exc).__name__}: {exc}",
        })
        return False


def _worker_verify(args: argparse.Namespace) -> int:
    started_at = utc_now()
    base = _require_sha("ACCEPTED_BASE", args.accepted_base)
    candidate = _require_sha("CANDIDATE_COMMIT", args.candidate_commit)
    evidence_path = Path(args.evidence_path).resolve()
    evidence: dict = {
        "schema_version": 1,
        "evidence_kind": "UNATTENDED_CANDIDATE_MACHINE_EVIDENCE",
        "status": "FAILED",
        "accepted_base": base,
        "candidate_commit": candidate,
        "canonical_remote": args.canonical_remote,
        "started_at": started_at,
        "finished_at": None,
        "candidate_parents": [],
        "changed_files": [],
        "isolated_worktree": None,
        "checks": [],
        "failure_reason": None,
    }
    checks: list[dict] = evidence["checks"]
    scratch = evidence_path.parent / "verification"
    repo = scratch / "repo"
    worktree = scratch / "worktree"
    try:
        if scratch.exists():
            shutil.rmtree(scratch)
        scratch.mkdir(parents=True, exist_ok=False)
        git = _git()

        if not _record_check(checks, "git_init", [git, "init", str(repo)], cwd=scratch, timeout=60):
            raise RuntimeError("git init failed")
        if not _record_check(checks, "git_remote_add", [git, "-C", str(repo), "remote", "add", "origin", args.canonical_remote], cwd=scratch, timeout=60):
            raise RuntimeError("git remote add failed")
        if not _record_check(checks, "fetch_accepted_base_exact_sha", [git, "-C", str(repo), "fetch", "--no-tags", "--force", "origin", base], cwd=scratch, timeout=180):
            raise RuntimeError("Accepted Base exact-SHA fetch failed")
        if not _record_check(checks, "fetch_candidate_exact_sha", [git, "-C", str(repo), "fetch", "--no-tags", "--force", "origin", candidate], cwd=scratch, timeout=180):
            raise RuntimeError("Candidate exact-SHA fetch failed")
        if not _record_check(checks, "candidate_is_commit", [git, "-C", str(repo), "cat-file", "-e", f"{candidate}^{{commit}}"], cwd=scratch, timeout=60):
            raise RuntimeError("Candidate SHA is not an unambiguous commit")
        if not _record_check(checks, "accepted_base_is_ancestor", [git, "-C", str(repo), "merge-base", "--is-ancestor", base, candidate], cwd=scratch, timeout=60):
            raise RuntimeError("Candidate is not based on Accepted Base")

        rc, out, err, _ = _run([git, "-C", str(repo), "show", "-s", "--format=%P", candidate], cwd=scratch, timeout=60)
        checks.append({"name": "candidate_parent_inventory", "status": "SUCCEEDED" if rc == 0 else "FAILED", "exit_code": rc, "stdout_tail": _tail(out), "stderr_tail": _tail(err)})
        if rc != 0:
            raise RuntimeError("Candidate parent inventory failed")
        evidence["candidate_parents"] = [p for p in out.strip().split() if SHA_RE.fullmatch(p)]

        rc, out, err, _ = _run([git, "-C", str(repo), "diff", "--name-only", base, candidate], cwd=scratch, timeout=60)
        checks.append({"name": "scope_inventory", "status": "SUCCEEDED" if rc == 0 else "FAILED", "exit_code": rc, "stdout_tail": _tail(out), "stderr_tail": _tail(err)})
        if rc != 0:
            raise RuntimeError("scope inventory failed")
        evidence["changed_files"] = [line.strip() for line in out.splitlines() if line.strip()]

        if not _record_check(checks, "isolated_worktree_add", [git, "-C", str(repo), "worktree", "add", "--detach", str(worktree), candidate], cwd=scratch, timeout=120):
            raise RuntimeError("isolated worktree creation failed")
        evidence["isolated_worktree"] = str(worktree)

        rc, out, err, _ = _run([git, "-C", str(worktree), "rev-parse", "HEAD"], cwd=worktree, timeout=60)
        exact_ok = rc == 0 and out.strip().lower() == candidate
        checks.append({"name": "isolated_head_exact_candidate", "status": "SUCCEEDED" if exact_ok else "FAILED", "exit_code": rc, "stdout_tail": _tail(out), "stderr_tail": _tail(err)})
        if not exact_ok:
            raise RuntimeError("isolated worktree HEAD does not equal Candidate SHA")

        python = os.environ.get("APC_HARNESS_PYTHON") or sys.executable
        machine_check = worktree / "runtime" / "entry_consistency_check.py"
        if not machine_check.is_file():
            checks.append({"name": "machine_check", "status": "MISSING", "exit_code": None, "stdout_tail": "", "stderr_tail": str(machine_check)})
            raise RuntimeError("Machine Check missing")
        if not _record_check(checks, "machine_check", [python, str(machine_check)], cwd=worktree, timeout=180):
            raise RuntimeError("Machine Check failed")

        for name in ("test_runtime_offline.py", "test_router_offline.py"):
            path = worktree / "runtime" / name
            if not path.is_file():
                checks.append({"name": name, "status": "MISSING", "exit_code": None, "stdout_tail": "", "stderr_tail": str(path)})
                raise RuntimeError(f"required test missing: {name}")
            if not _record_check(checks, name, [python, str(path)], cwd=worktree, timeout=600):
                raise RuntimeError(f"required test failed: {name}")

        run_cmd = worktree / "runtime" / "run.cmd"
        if not run_cmd.is_file():
            checks.append({"name": "runtime_check", "status": "MISSING", "exit_code": None, "stdout_tail": "", "stderr_tail": str(run_cmd)})
            raise RuntimeError("Runtime entry missing")
        if os.environ.get("APC_HARNESS_TEST_RUNTIME_CHECK") == "PYTHON_HELP":
            runtime_check_cmd = [python, str(worktree / "runtime" / "runtime.py"), "--help"]
        else:
            runtime_check_cmd = [python, str(worktree / "runtime" / "runtime.py"), "health"]
        if not _record_check(checks, "runtime_check", runtime_check_cmd, cwd=worktree, timeout=180):
            raise RuntimeError("Runtime Check failed")

        evidence["status"] = "SUCCEEDED"
        evidence["failure_reason"] = None
        return_code = 0
    except Exception as exc:
        evidence["status"] = "FAILED"
        evidence["failure_reason"] = f"{type(exc).__name__}: {exc}"
        return_code = 20
    finally:
        evidence["finished_at"] = utc_now()
        evidence["harness_exit_code"] = return_code if "return_code" in locals() else 20
        atomic_json(evidence_path, evidence)
    emit({"HARNESS_WORKER_STATUS": evidence["status"], "CANDIDATE_COMMIT": candidate,
          "EVIDENCE_PATH": str(evidence_path), "HARNESS_WORKER_EXIT_CODE": return_code})
    return return_code


def _to_bash_path(value: str) -> str:
    p = str(value).replace("\\", "/")
    m = re.match(r"^([A-Za-z]):/(.*)$", p)
    if m:
        return f"/{m.group(1).lower()}/{m.group(2)}"
    return p


def _paths_overlap(first: Path | str, second: Path | str) -> bool:
    """Mirror the frozen launcher's same-or-ancestor overlap rule."""
    a = os.path.normcase(os.path.abspath(os.path.normpath(str(first))))
    b = os.path.normcase(os.path.abspath(os.path.normpath(str(second))))
    try:
        common = os.path.commonpath([a, b])
    except ValueError:
        return False
    return common == a or common == b


def _make_worker_tasks(script: Path, args: argparse.Namespace, evidence_path: Path) -> dict:
    python = os.environ.get("APC_HARNESS_PYTHON", str(DEFAULT_PYTHON))
    command = " ".join([
        shlex.quote(_to_bash_path(python)),
        shlex.quote(_to_bash_path(str(script))),
        "worker-verify",
        "--accepted-base", shlex.quote(args.accepted_base),
        "--candidate-commit", shlex.quote(args.candidate_commit),
        "--canonical-remote", shlex.quote(args.canonical_remote),
        "--evidence-path", shlex.quote(_to_bash_path(str(evidence_path))),
    ])
    repo_root = script.parent.parent
    verifier_cwd = script.parent
    witness_cwd = repo_root / "docs"
    witness_target = script.parent / "run.cmd"
    if _paths_overlap(verifier_cwd, witness_cwd):
        raise ValueError("candidate verifier/witness working directories overlap")
    tasks = [
        {
            "id": "candidate_verifier",
            "working_directory": str(verifier_cwd),
            "task": (
                "Use the Bash tool exactly once to execute the command below. "
                "Do not substitute a branch, tag, or latest ref for the explicit commit SHA. "
                "Do not edit production files.\n" + command
            ),
            "inputs": [args.accepted_base, args.candidate_commit, args.canonical_remote],
            "acceptance": (
                "The exact command exits 0 and machine_evidence.json reports SUCCEEDED "
                "for the exact Candidate SHA."
            ),
            "tools": ["Bash", "Read"],
        },
        {
            "id": "candidate_witness",
            "working_directory": str(witness_cwd),
            "task": (
                "Independent read-only witness task. Read the Candidate runtime entry at "
                f"{witness_target} and report WITNESS_OK together with the exact Candidate SHA "
                f"{args.candidate_commit}. Do not execute or edit anything."
            ),
            "inputs": [args.accepted_base, args.candidate_commit, args.canonical_remote],
            "acceptance": "Read succeeds and final response contains WITNESS_OK plus the exact Candidate SHA.",
            "tools": ["Read"],
        },
    ]
    for task in tasks:
        unknown = set(task["tools"]) - LAUNCHER_ALLOWED_TOOLS
        if unknown:
            raise ValueError(f"task {task['id']} requests launcher-disallowed tools: {sorted(unknown)}")
    return {
        "common_context": (
            "V0.1 unattended Candidate verification. These are two independent launcher "
            "Run-mode tasks. Neither task may edit production files."
        ),
        "tasks": tasks,
    }


def _find_worker_metadata(output_root: Path) -> list[Path]:
    return sorted(output_root.rglob("worker.json")) if output_root.exists() else []


def _worker_id(meta: dict, path: Path) -> str:
    return str(meta.get("worker_id") or meta.get("id") or path.parent.name)


def _persist_outer_failure(state_path: Path, state: dict, reason: str, exit_code: int) -> int:
    state["HARNESS_STATUS"] = "HARD_BLOCKED"
    state["HARNESS_EXIT_CODE"] = exit_code
    state["HARNESS_FINISHED_AT"] = utc_now()
    state["FAILURE_REASON"] = reason
    atomic_json(state_path, state)
    emit(state)
    return exit_code


def _invoke(args: argparse.Namespace) -> int:
    base = _require_sha("ACCEPTED_BASE", args.accepted_base)
    candidate = _require_sha("CANDIDATE_COMMIT", args.candidate_commit)
    if not args.canonical_remote:
        raise ValueError("CANONICAL_REMOTE is required")

    state_root = Path(os.environ.get("APC_RUNTIME_STATE_ROOT", str(DEFAULT_STATE_ROOT)))
    token = hashlib.sha256(f"{base}|{candidate}|{args.canonical_remote}|{utc_now()}|{uuid.uuid4()}".encode("utf-8")).hexdigest()[:16]
    evidence_id = f"HE-{token}"
    harness_dir = state_root / "harness" / evidence_id
    evidence_path = harness_dir / "machine_evidence.json"
    state_path = harness_dir / "harness_state.json"
    tasks_path = harness_dir / "tasks.json"
    output_root = harness_dir / "workbuddy"
    launcher = Path(os.environ.get("APC_HARNESS_LAUNCHER", str(DEFAULT_LAUNCHER)))
    model = os.environ.get("APC_HARNESS_MODEL", DEFAULT_MODEL)

    state = {
        "TASK_ID": "V0.1-UNATTENDED-HARNESS-BOOTSTRAP",
        "HARNESS_STATUS": "RUNNING",
        "ACCEPTED_BASE": base,
        "CANDIDATE_COMMIT": candidate,
        "CANONICAL_REMOTE": args.canonical_remote,
        "EVIDENCE_ID": evidence_id,
        "EVIDENCE_PATH": str(evidence_path),
        "HARNESS_EXIT_CODE": None,
        "HARNESS_STARTED_AT": utc_now(),
        "HARNESS_FINISHED_AT": None,
        "WORKER_METADATA_PATH": None,
        "WORKER_METADATA_PATHS": [],
        "FAILURE_REASON": None,
    }
    atomic_json(state_path, state)

    if not launcher.is_file():
        return _persist_outer_failure(state_path, state, "WorkBuddy launcher missing", 21)

    task_doc = _make_worker_tasks(Path(__file__).resolve(), args, evidence_path)
    atomic_json(tasks_path, task_doc)
    output_root.mkdir(parents=True, exist_ok=True)

    ps = os.environ.get("APC_HARNESS_POWERSHELL", "powershell.exe")
    cmd = [
        ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(launcher),
        "-Mode", "Run", "-TasksFile", str(tasks_path), "-OutputRoot", str(output_root),
        "-MaxWorkers", "2", "-TimeoutSeconds", str(args.timeout), "-Model", model,
    ]
    env = os.environ.copy()
    env["CODEBUDDY_CONFIG_DIR"] = os.environ.get("CODEBUDDY_CONFIG_DIR", str(DEFAULT_CONFIG_DIR))
    try:
        rc, out, err, _ = _run(cmd, cwd=Path(__file__).resolve().parent.parent,
                               timeout=args.timeout + 120, env=env)
    except subprocess.TimeoutExpired:
        return _persist_outer_failure(state_path, state, "WorkBuddy launcher timeout", 22)
    except Exception as exc:
        return _persist_outer_failure(state_path, state, f"WorkBuddy launcher start failed: {type(exc).__name__}: {exc}", 23)
    if rc != 0:
        return _persist_outer_failure(state_path, state, f"WorkBuddy launcher non-zero exit={rc}; stderr={_tail(err, 1000)}", 24)

    metas = _find_worker_metadata(output_root)
    if len(metas) != len(EXPECTED_WORKERS):
        return _persist_outer_failure(
            state_path, state,
            f"expected exactly {len(EXPECTED_WORKERS)} worker.json files, found {len(metas)}",
            25,
        )

    workers: dict[str, tuple[Path, dict]] = {}
    for meta_path in metas:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return _persist_outer_failure(state_path, state, f"invalid worker metadata: {type(exc).__name__}", 26)
        wid = _worker_id(meta, meta_path)
        if wid in workers:
            return _persist_outer_failure(state_path, state, f"duplicate worker metadata id: {wid}", 25)
        workers[wid] = (meta_path, meta)

    if set(workers) != set(EXPECTED_WORKERS):
        return _persist_outer_failure(
            state_path, state,
            f"worker metadata ids mismatch: expected={list(EXPECTED_WORKERS)!r} actual={sorted(workers)!r}",
            25,
        )

    state["WORKER_METADATA_PATHS"] = [str(workers[wid][0]) for wid in EXPECTED_WORKERS]
    state["WORKER_METADATA_PATH"] = str(workers["candidate_verifier"][0])
    atomic_json(state_path, state)

    for wid in EXPECTED_WORKERS:
        meta = workers[wid][1]
        if meta.get("timed_out") is True:
            return _persist_outer_failure(state_path, state, f"WorkBuddy worker timed out: {wid}", 27)
        if meta.get("exit_code") != 0 or meta.get("status") != "succeeded":
            return _persist_outer_failure(
                state_path, state,
                f"WorkBuddy worker not succeeded: id={wid} status={meta.get('status')!r} exit={meta.get('exit_code')!r}",
                28,
            )

    if not evidence_path.is_file():
        return _persist_outer_failure(state_path, state, "Machine Evidence missing", 29)
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _persist_outer_failure(state_path, state, f"Machine Evidence invalid JSON: {type(exc).__name__}", 30)
    if evidence.get("candidate_commit") != candidate or evidence.get("accepted_base") != base:
        return _persist_outer_failure(state_path, state, "Machine Evidence identity binding mismatch", 31)
    if evidence.get("status") != "SUCCEEDED" or evidence.get("harness_exit_code") != 0:
        return _persist_outer_failure(state_path, state, f"Machine Evidence is not successful: {evidence.get('status')!r}", 32)
    checks = evidence.get("checks")
    if not isinstance(checks, list) or not checks or any(c.get("status") != "SUCCEEDED" for c in checks):
        return _persist_outer_failure(state_path, state, "Machine Evidence contains failed/unknown/missing checks", 33)

    state["HARNESS_STATUS"] = "SUCCEEDED"
    state["HARNESS_EXIT_CODE"] = 0
    state["HARNESS_FINISHED_AT"] = utc_now()
    state["FAILURE_REASON"] = None
    atomic_json(state_path, state)
    emit(state)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="harness_verify")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("harness-verify")
    s.add_argument("--accepted-base", required=True)
    s.add_argument("--candidate-commit", required=True)
    s.add_argument("--canonical-remote", required=True)
    s.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    s = sub.add_parser("worker-verify")
    s.add_argument("--accepted-base", required=True)
    s.add_argument("--candidate-commit", required=True)
    s.add_argument("--canonical-remote", required=True)
    s.add_argument("--evidence-path", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "harness-verify":
            return _invoke(args)
        if args.command == "worker-verify":
            return _worker_verify(args)
        raise ValueError("UNKNOWN command")
    except ValueError as exc:
        emit({"HARNESS_STATUS": "HARD_BLOCKED", "ERROR": str(exc), "HARNESS_EXIT_CODE": 2})
        return 2
    except Exception as exc:
        emit({"HARNESS_STATUS": "HARD_BLOCKED", "ERROR": f"{type(exc).__name__}: {exc}", "HARNESS_EXIT_CODE": 1})
        return 1


if __name__ == "__main__":
    sys.exit(main())