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

# State-only / governance-only paths. A leading commit that touches ONLY these
# is a governance meta-commit (e.g. a Phase 0 seal) and is allowed to sit ahead
# of CURRENT_DEVELOPMENT_HEAD. Any other path = a real code/development change.
GOVERNANCE_PATHS = frozenset({
    "PROJECT_STATE.json",
    "PROJECT_STATE.md",
    "state/branch_registry.json",
    "scripts/state_doctor.py",
    "scripts/test_state_doctor_classification.py",
    "docs/PHASE0_PACK_README.md",
})

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


def _unregistered_branches(actual_names, registered_names):
    """Branches present on disk but absent from the registry: SPECULATIVE.
    Empty means no unregistered branch (CASE 4 PASS)."""
    return sorted(set(actual_names) - set(registered_names))


def _all_in(given, allowed) -> bool:
    """True iff every element of `given` is in `allowed` and `given` is non-empty.
    An empty change set is NOT governance-only (fail closed)."""
    return bool(given) and all(p in allowed for p in given)


def _commit_is_governance_only(commit: str) -> bool:
    """A leading commit is governance-only iff every path it changes is in
    GOVERNANCE_PATHS. Driven by verifiable tree diff (path metadata), never by
    matching commit-message strings."""
    changed = (git("diff-tree", "--no-commit-id", "--name-only", "-r", commit) or "").splitlines()
    return _all_in(changed, GOVERNANCE_PATHS)


def _classify_dev_head(recorded, physical, is_ancestor, ahead_commits, is_governance_commit):
    """Decision core for CURRENT_DEVELOPMENT_HEAD.

    Returns (is_clean, detail). Governing rule (Phase 0 Seal ruling A / user
    2026-08-28):
      - development_head == physical_head                 -> clean (CASE 1)
      - physical ahead, all leading commits governance-   -> clean (CASE 2)
      - physical ahead, any leading commit is a real      -> DRIFT (CASE 3)
        code/development change
      - recorded development_head does not resolve         -> DRIFT (CASE 5)
      - physical diverged / not descendant                -> DRIFT
    """
    if recorded is None:
        return False, "development head recorded sha does not resolve to a commit"
    if recorded == physical:
        return True, "development head == physical head"
    if not is_ancestor(recorded, physical):
        return False, (f"development head is not an ancestor of physical head: "
                       f"recorded={recorded[:8]} physical={physical[:8]}")
    for commit in ahead_commits:
        if not is_governance_commit(commit):
            return False, f"non-governance commit ahead of development head: {commit}"
    return True, "ahead commits are state-only/governance"


def _check_dev_head(name: str, want_short: str, physical_full: str) -> None:
    recorded = git("rev-parse", "--verify", "--quiet", f"{want_short}^{{commit}}")

    def is_ancestor(a: str, b: str) -> bool:
        return git("merge-base", "--is-ancestor", a, b) is not None

    ahead = [] if recorded is None else (git("rev-list", f"{recorded}..{physical_full}") or "").splitlines()
    ok, detail = _classify_dev_head(recorded, physical_full, is_ancestor,
                                    ahead, _commit_is_governance_only)
    if not ok:
        drift("development head drift", f"{name}@governance-only-ahead", detail)


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
    for line in (git("for-each-ref", "--format=%(refname) %(objectname)",
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
    # R5: unregistered branches are SPECULATIVE (fail-closed) -> DRIFT.
    for name in _unregistered_branches(set(actual), set(entries)):
        drift("unregistered branch (fail-closed: SPECULATIVE)", "registered in branch_registry", name)
    dev_branch = (ps.get("baselines", {}).get("current_development_head") or {}).get("branch")
    for name, b in entries.items():
        if name not in actual:
            continue
        got_full = actual[name]
        want = str(b.get("head", ""))
        if not want:
            continue
        if name == dev_branch:
            # Phase 0 Seal ruling A: physical HEAD may be ahead of the recorded
            # development head by governance-only commits. Anything else drifts.
            _check_dev_head(name, want, got_full)
        elif not got_full.startswith(want) and not want.startswith(got_full):
            drift("registered head mismatch", f"{name}@{want}", f"{name}@{got_full[:8]}")
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
