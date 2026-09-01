"""State Level enforcement (Canonical §45 状态层级).

Canonical requirement (docs/canonical/CANONICAL_PRODUCT_DEFINITION_V1.0.md:1504-1524):

    至少区分 DISCUSSED / FOUND / LOCAL_EXISTS / IMPLEMENTED /
    LOCAL_TEST_PASS / R_REVIEW_PASS / E2E_PASS / PRODUCTION_VERIFIED /
    PARTIAL / NOT_VERIFIED / FAILED / BLOCKED。

    禁止：**代码写了 = 产品完成。**

This module turns that definition into machine-checked code:

1.  ``STATE_LEVELS`` is the closed enumeration of the 12 canonical states.
    Any other state value is rejected (fail-closed) by ``validate_state``.
2.  The 8 progressive states carry a strict monotonic rank
    (``LEVEL_RANK``); the 4 exception states (PARTIAL / NOT_VERIFIED /
    FAILED / BLOCKED) are deliberately rank-less: they never count as
    progress and never satisfy a completion claim.
3.  ``check_claim`` enforces the canonical prohibition directly: a claim
    at or above IMPLEMENTED must carry the evidence its level demands
    (tests for LOCAL_TEST_PASS, an R verdict for R_REVIEW_PASS, e2e
    evidence for E2E_PASS, production evidence for PRODUCTION_VERIFIED).
    Evidence matching is token-based (word-boundary regex, plural-aware)
    — substring matching is explicitly avoided so that garbage tokens
    like "untested" / "preview" / "preproduction" cannot satisfy the
    "test" / "review" / "production" requirements (R-D P1 fix).
    Code existing on disk (LOCAL_EXISTS / IMPLEMENTED) without evidence
    is explicitly *not* a completion claim — ``is_completion_claim``
    returns False for anything below LOCAL_TEST_PASS.
4.  ``check_progression`` flags LEVEL_REGRESSION: a state cannot move
    backwards along the rank (e.g. E2E_PASS -> IMPLEMENTED) without the
    regression being machine-visible.  Detection is the enforcement:
    regression is not silently swallowed.  Exception states have no rank,
    so a progressive state can legitimately fall into FAILED (that is a
    real event, not a disguised downgrade); but re-entering a completion
    level FROM an exception state is treated as a fresh claim and must
    re-present the evidence of that level (R-D P2 fix — no tunnel),
    otherwise REENTRY_EVIDENCE_REQUIRED is raised.

Non-authority: this module is a pure validator.  It never mutates state,
never grants authority, and its outputs are inert data
(non_authority=True in every JSON payload).

CLI:
    python state_level.py validate --state E2E_PASS
    python state_level.py check-claim --state LOCAL_TEST_PASS --evidence test_report
    python state_level.py check-file --file states.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = "v1.0-state-level-45"

# --- Canonical enumeration (§45) -------------------------------------------

STATE_LEVELS: Tuple[str, ...] = (
    "DISCUSSED",
    "FOUND",
    "LOCAL_EXISTS",
    "IMPLEMENTED",
    "LOCAL_TEST_PASS",
    "R_REVIEW_PASS",
    "E2E_PASS",
    "PRODUCTION_VERIFIED",
    "PARTIAL",
    "NOT_VERIFIED",
    "FAILED",
    "BLOCKED",
)

STATE_LEVEL_SET = frozenset(STATE_LEVELS)

# Strictly increasing verification rank over the progressive states.
LEVEL_RANK: Dict[str, int] = {
    "DISCUSSED": 0,
    "FOUND": 1,
    "LOCAL_EXISTS": 2,
    "IMPLEMENTED": 3,
    "LOCAL_TEST_PASS": 4,
    "R_REVIEW_PASS": 5,
    "E2E_PASS": 6,
    "PRODUCTION_VERIFIED": 7,
}

# Exception states: real, reportable, but never progress, never "done".
EXCEPTION_STATES = frozenset({"PARTIAL", "NOT_VERIFIED", "FAILED", "BLOCKED"})

# Evidence each progressive state demands (canonical prohibition #3):
# "代码写了 = 产品完成" is rejected here.  Evidence kinds are free-form
# strings but must *name* the artifact class, not be empty.
REQUIRED_EVIDENCE: Dict[str, Tuple[str, ...]] = {
    "LOCAL_TEST_PASS": ("test",),
    "R_REVIEW_PASS": ("test", "review"),
    "E2E_PASS": ("test", "review", "e2e"),
    "PRODUCTION_VERIFIED": ("test", "review", "e2e", "production"),
}

# States below this never constitute a completion claim (the canonical
# "code written != product complete" guard).
MIN_COMPLETION_STATE = "LOCAL_TEST_PASS"

# Token-based evidence matching (R-D P1 fix): word-boundary + plural-aware.
# "untested" never matches "test"; "preproduction" never matches
# "production"; "reviews/" still matches "review" via the plural form.
def _evidence_matched(kind: str, item: str) -> bool:
    # 字母级 lookaround（而非 \b）：snake_case 证据名（test_report.json、
    # prod_log.txt）中 kind 后跟 '_' 仍应命中；但与字母粘连的伪装词
    # （untested / preview / preproduction）必须被拒绝。
    return re.search(rf"(?<![A-Za-z]){re.escape(kind)}s?(?![A-Za-z])",
                     item) is not None


class StateLevelError(ValueError):
    """Raised on unknown/illegal state values (fail-closed)."""


def normalize_state(value: Any) -> Optional[str]:
    """Uppercase/strip a state value; returns None for empty input."""
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def validate_state(value: Any) -> str:
    """Fail-closed validation: only canonical §45 states pass."""
    state = normalize_state(value)
    if state is None:
        raise StateLevelError("STATE_EMPTY")
    if state not in STATE_LEVEL_SET:
        raise StateLevelError(f"STATE_UNKNOWN:{state}")
    return state


def rank_of(value: Any) -> Optional[int]:
    """Rank of a progressive state; None for exception states."""
    state = validate_state(value)
    return LEVEL_RANK.get(state)


def is_completion_claim(value: Any, evidence: Optional[List[str]] = None) -> bool:
    """True only when the claim constitutes a verified completion.

    Two layers (R-D P2: 单一口径，不再双轨):
    - Level eligibility: anything below LOCAL_TEST_PASS (including
      IMPLEMENTED — code exists, nothing verified) and every exception
      state returns False.
    - When ``evidence`` is provided (the audited path), the claim must
      ALSO pass ``check_claim`` — level eligibility alone is never a
      verified completion.  Passing evidence=None keeps the pure level
      predicate for callers that only rank states (documented escape
      hatch, still not a verified claim).
    """
    state = validate_state(value)
    if state in EXCEPTION_STATES:
        return False
    if LEVEL_RANK[state] < LEVEL_RANK[MIN_COMPLETION_STATE]:
        return False
    if evidence is None:
        return False  # 无证据时只给等级判定，不给完成判定（保守缺省）
    return not check_claim(state, evidence)


def check_claim(state: Any, evidence: Optional[List[str]]) -> List[str]:
    """Check a state claim against the evidence its level demands.

    Returns a list of problem codes; empty list = claim is sound.
    """
    problems: List[str] = []
    try:
        st = validate_state(state)
    except StateLevelError as exc:
        return [f"CLAIM_STATE_INVALID:{exc}"]

    ev = [str(e).strip().lower() for e in (evidence or []) if str(e).strip()]
    if not ev:
        # 只有"必须凭证据才算完成"的层级在零证据时报错；IMPLEMENTED 及
        # 以下是本地事实声明（代码在盘上即成立），本就不构成完成声明。
        if st in REQUIRED_EVIDENCE:
            problems.append(f"CLAIM_NO_EVIDENCE:{st}")
        return problems

    required = REQUIRED_EVIDENCE.get(st)
    if required:
        have = set()
        for item in ev:
            for kind in required:
                if _evidence_matched(kind, item):
                    have.add(kind)
        for kind in required:
            if kind not in have:
                problems.append(f"CLAIM_EVIDENCE_MISSING:{st}:{kind}")
    return problems


def check_progression(old: Any, new: Any,
                      evidence: Optional[List[str]] = None) -> List[str]:
    """Detect illegal state transitions (machine-visible regression).

    R-D P2 (异常态隧道封堵): falling into an exception state is a real
    event, not a downgrade — but re-entering a completion level FROM an
    exception state is a fresh claim and must re-present that level's
    evidence.  Without sufficient evidence the re-entry is flagged
    REENTRY_EVIDENCE_REQUIRED, so the tunnel
    PRODUCTION_VERIFIED -> FAILED -> PRODUCTION_VERIFIED can no longer
    bypass detection.  Pass the re-entry evidence via ``evidence``
    (same format as ``check_claim``).
    """
    problems: List[str] = []
    try:
        old_s = validate_state(old)
    except StateLevelError as exc:
        return [f"OLD_STATE_INVALID:{exc}"]
    try:
        new_s = validate_state(new)
    except StateLevelError as exc:
        return [f"NEW_STATE_INVALID:{exc}"]
    if old_s == new_s:
        return problems
    old_rank = LEVEL_RANK.get(old_s)
    new_rank = LEVEL_RANK.get(new_s)
    if old_rank is not None and new_rank is not None and new_rank < old_rank:
        problems.append(f"LEVEL_REGRESSION:{old_s}->{new_s}")
    if (old_rank is None and old_s != new_s
            and new_rank is not None
            and new_rank >= LEVEL_RANK[MIN_COMPLETION_STATE]):
        # 异常态 -> 完成层级：视为全新声明，索证不可豁免。
        if evidence is None:
            problems.append(f"REENTRY_EVIDENCE_REQUIRED:{new_s}")
        else:
            problems.extend(f"REENTRY_{p}" for p in check_claim(new_s, evidence))
    return problems


def check_file(path: str) -> Dict[str, Any]:
    """Batch check of a JSON file: [{"id", "state", "evidence": [...]}, ...].

    Also cross-checks progression when entries share an "id" and carry
    "prev_state".
    """
    entries = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise StateLevelError("BATCH_FORMAT_MUST_BE_LIST")
    problems: List[Dict[str, Any]] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            problems.append({"index": i, "problem": "BATCH_ENTRY_MUST_BE_OBJECT"})
            continue
        entry_id = str(entry.get("id") or f"entry-{i}")
        state = entry.get("state")
        try:
            validate_state(state)
        except StateLevelError as exc:
            problems.append({"id": entry_id, "problem": f"STATE_INVALID:{exc}"})
            continue
        for p in check_claim(state, entry.get("evidence")):
            problems.append({"id": entry_id, "problem": p})
        prev = entry.get("prev_state")
        if prev is not None:
            for p in check_progression(prev, state, entry.get("evidence")):
                problems.append({"id": entry_id, "problem": p})
    return {
        "schema": SCHEMA,
        "checked": len(entries),
        "problems": problems,
        "ok": not problems,
        "non_authority": True,
    }


# --- CLI -------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Canonical §45 state-level validator (fail-closed, non-authority)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_v = sub.add_parser("validate", help="validate a single state value")
    p_v.add_argument("--state", required=True)

    p_c = sub.add_parser("check-claim", help="check a state claim + evidence")
    p_c.add_argument("--state", required=True)
    p_c.add_argument("--evidence", default="",
                     help="comma-separated evidence kinds/paths")

    p_f = sub.add_parser("check-file", help="batch check a JSON file")
    p_f.add_argument("--file", required=True)

    args = ap.parse_args(argv)

    if args.cmd == "validate":
        try:
            state = validate_state(args.state)
        except StateLevelError as exc:
            print(json.dumps({"schema": SCHEMA, "ok": False,
                              "problem": str(exc), "non_authority": True},
                             ensure_ascii=False))
            return 2
        print(json.dumps({"schema": SCHEMA, "ok": True, "state": state,
                          "rank": LEVEL_RANK.get(state),
                          "completion_claim": is_completion_claim(state),
                          "non_authority": True}, ensure_ascii=False))
        return 0

    if args.cmd == "check-claim":
        evidence = [e for e in args.evidence.split(",") if e.strip()]
        problems = check_claim(args.state, evidence)
        print(json.dumps({"schema": SCHEMA, "state": normalize_state(args.state),
                          "problems": problems, "ok": not problems,
                          "non_authority": True}, ensure_ascii=False))
        return 0 if not problems else 2

    if args.cmd == "check-file":
        try:
            result = check_file(args.file)
        except (StateLevelError, OSError, json.JSONDecodeError) as exc:
            print(json.dumps({"schema": SCHEMA, "ok": False,
                              "problem": f"FILE_CHECK_FAILED:{exc}",
                              "non_authority": True}, ensure_ascii=False))
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 2

    return 2


if __name__ == "__main__":
    sys.exit(main())
