#!/usr/bin/env python3
"""state_doctor.py — read-only drift detector for PROJECT_STATE authority.

Usage: run at repository root:  python scripts/state_doctor.py
Reads PROJECT_STATE.json / PROJECT_STATE.md / state/branch_registry.json and
verifies them against the actual git repository. It NEVER writes anything.

Output contract:
  - one line per finding:  DRIFT: <what> | expected=<...> | actual=<...>
  - warning lines:         WARN:  <what> | <detail>
  - final line:            DRIFT_FREE   or   DRIFT_COUNT=<n>
Exit code: 0 when DRIFT_FREE (warnings allowed), 1 when any DRIFT found.

Design rules (from DESIGN-状态权威化机制 §3.3):
  R1  PROJECT_STATE.json must exist and parse; required fields present.
  R2  every commit-anchor must resolve to a real commit object.
  R3  CANDIDATE_RED head must not be registered as TRUNK (promotion guard).
  R4  release_status must be PRODUCT_NOT_READY while head verdict is RED.
  R5  every local/remote branch must be registered (unregistered = SPECULATIVE drift).
  R6  registered branch heads must match actual heads when the branch exists locally.
  R7  BUILD_MISSION_JOURNAL freshness (staleness threshold, warning only).
  R8  spec_registry must not be empty for a version line under adjudication (warning
      with guidance; becomes DRIFT once PHASE_0 is declared complete).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PS_JSON = ROOT / "PROJECT_STATE.json"
PS_MD = ROOT / "PROJECT_STATE.md"
REGISTRY = ROOT / "state" / "branch_registry.json"
JOURNAL = ROOT / "docs" / "BUILD_MISSION_JOURNAL.md"
STALENESS_DAYS = 7

drifts: list[str] = []
warns: list[str] = []


def drift(what: str, expected: str, actual: str) -> None:
    drifts.append(f"DRIFT: {what} | expected={expected} | actual={actual}")


def warn(what: str, detail: str) -> None:
    warns.append(f"WARN: {what} | {detail}")


def git(*args: str) -> str | None:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def load_json(path: Path, label: str) -> dict | None:
    if not path.exists():
        drift(f"{label} missing", f"file at {path}", "absent")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        drift(f"{label} unparseable", "valid JSON", str(exc))
        return None


def check_project_state() -> dict | None:
    ps = load_json(PS_JSON, "PROJECT_STATE.json")
    if ps is None:
        return None
    for field in ("schema", "release_status", "current_stage", "baselines",
                  "current_blockers", "spec_registry", "roadmap"):
        if field not in ps:
            drift("PROJECT_STATE required field", field, "missing")
    if not PS_MD.exists():
        drift("PROJECT_STATE.md missing", "human-readable twin present", "absent")
    # R2: commit anchors resolve
    def walk(obj):
        if isinstance(obj, dict):
            anchor = obj.get("anchor")
            if isinstance(anchor, dict) and anchor.get("type") == "commit":
                sha = anchor.get("value", "")
                if git("rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}") is None:
                    drift("commit anchor unresolvable", f"commit {sha} exists",
                          "not found in this clone (fetch all branches first)")
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
    walk(ps)
    return ps


def check_baselines(ps: dict) -> None:
    baselines = ps.get("baselines") or {}
    head = (baselines.get("current_development_head") or {})
    verdict = head.get("verdict", "")
    if verdict == "CANDIDATE_RED" and ps.get("release_status") != "PRODUCT_NOT_READY":
        drift("release_status inconsistent with RED head", "PRODUCT_NOT_READY",
              str(ps.get("release_status")))
    accepted = (baselines.get("current_accepted_base") or {})
    green = (baselines.get("last_green_base") or {})
    if accepted and green:
        acc_head = accepted.get("head", "")
        if acc_head and acc_head not in str(green.get("ref", "")):
            warn("accepted base differs from last green base",
                 f"accepted={acc_head} green_ref={green.get('ref')} "
                 "(allowed only with an explicit DECISION_LEDGER entry)")


def _ref_to_branch(ref: str) -> str | None:
    """Map a git refname to a registry-style branch name, or None for a ref
    that is not a branch.

    Branches are:
      - local branches:        refs/heads/<path>
      - remote-tracking:       refs/remotes/<remote>/<path>
    Non-branch refs (must not be reported as an unregistered branch):
      - symbolic HEAD (refs/heads/HEAD, refs/remotes/<remote>/HEAD)
      - a bare '<remote>' leaf such as refs/remotes/origin (a repo-ref-layout
        artifact with no branch path; the origin remote itself has no branch)
      - any other namespace (refs/tags/..., refs/notes/..., ...)
    """
    if ref.endswith("/HEAD"):
        return None
    if ref.startswith("refs/heads/"):
        return ref[len("refs/heads/"):]
    if ref.startswith("refs/remotes/"):
        rest = ref[len("refs/remotes/"):]
        if "/" not in rest:
            # <remote> leaf ref with no branch path; not a branch.
            return None
        return rest.split("/", 1)[1]
    return None


def check_registry(ps: dict) -> None:
    reg = load_json(REGISTRY, "state/branch_registry.json")
    if reg is None:
        return
    entries = {b["name"]: b for b in reg.get("branches", []) if "name" in b}
    # R3: promotion guard
    for name, b in entries.items():
        if b.get("role") == "TRUNK" and b.get("name") != "master":
            drift("non-master branch registered as TRUNK", "only master or adjudicated promotion", name)
        head_info = (ps.get("baselines", {}).get("current_development_head") or {})
        if b.get("role") == "TRUNK" and name == head_info.get("branch") \
                and head_info.get("verdict") == "CANDIDATE_RED":
            drift("CANDIDATE_RED registered as TRUNK", "red candidate not promotable", name)
    # R5/R6: actual branches vs registry
    actual: dict[str, str] = {}
    for line in (git("for-each-ref", "--format=%(refname) %(objectname:short)",
                     "refs/heads/", "refs/remotes/") or "").splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        ref, sha = parts
        name = _ref_to_branch(ref)
        if name is None:
            # symbolic HEAD, bare '<remote>' leaf, or non-branch ref: ignore.
            continue
        actual[name] = sha
    for name in sorted(set(actual) - set(entries)):
        drift("unregistered branch (fail-closed: SPECULATIVE)", "registered in branch_registry", name)
    for name, b in entries.items():
        if name in actual:
            want = str(b.get("head", ""))
            got = actual[name]
            if want and not got.startswith(want) and not want.startswith(got):
                drift("registered head mismatch", f"{name}@{want}", f"{name}@{got}")
    for name in sorted(set(entries) - set(actual)):
        warn("registered branch not present in this clone", f"{name} (fetch it before trusting registry)")


def check_journal() -> None:
    if not JOURNAL.exists():
        warn("BUILD_MISSION_JOURNAL missing", "expected at docs/BUILD_MISSION_JOURNAL.md")
        return
    text = JOURNAL.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"updated_at:\s*`?(\d{4}-\d{2}-\d{2})", text)
    if not m:
        warn("journal updated_at unparsable", "cannot evaluate staleness")
        return
    updated = dt.date.fromisoformat(m.group(1))
    last_commit = git("log", "-1", "--format=%cs")
    if last_commit:
        committed = dt.date.fromisoformat(last_commit)
        if (committed - updated).days > STALENESS_DAYS:
            warn("journal staleness",
                 f"updated_at={updated} but latest commit={committed} "
                 f"(>{STALENESS_DAYS} days): docs lagging code")


def check_spec_registry(ps: dict) -> None:
    if ps.get("current_stage") == "PHASE_0" and not ps.get("spec_registry"):
        warn("SPEC_NOT_ANCHORED",
             "spec_registry is empty; V0.9 spec must be committed to docs/specs/ and "
             "registered (with sha256) before RED-case adjudication can start")
    elif not ps.get("spec_registry"):
        drift("spec_registry empty outside PHASE_0", "anchored specs present", "empty")


def main() -> int:
    if not (ROOT / ".git").exists():
        print("DRIFT: not a git repository root | expected=.git present | actual=absent")
        print("DRIFT_COUNT=1")
        return 1
    ps = check_project_state()
    if ps is not None:
        check_baselines(ps)
        check_registry(ps)
        check_spec_registry(ps)
    check_journal()
    for line in warns:
        print(line)
    for line in drifts:
        print(line)
    if drifts:
        print(f"DRIFT_COUNT={len(drifts)}")
        return 1
    print("DRIFT_FREE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
