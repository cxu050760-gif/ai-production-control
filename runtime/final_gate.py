"""FINAL GATE — Canonical §74 twelve-condition completion gate.

Canonical requirement (docs/canonical/CANONICAL_PRODUCT_DEFINITION_V1.0.md:2255-2280):

    只有同时满足 12 条件才允许进入 FINAL DONE；
    Worker、Brain、C、R 中任何一个单独声称"已经完成"都不足以构成
    FINAL DONE。

This module mechanizes the 12 conditions into one fail-closed gate:

    C1  用户 Goal 已实现（声明必须引用盘上 evidence）
    C2  正式 Deliverables 已产生（磁盘真实存在）
    C3  Acceptance Criteria 已满足（runner 必须真实存在于盘上）
    C4  真实 Artifact 存在（磁盘真实存在 + §45 状态合法 + 完成层级索证
        + 状态与 Reviewer 裁定交叉一致）
    C5  机器可验证项目通过（每项须带 command 与盘上 evidence）
    C6  必要 Evidence 存在（磁盘真实存在）
    C7  独立 Reviewer PASS
    C8  Review 与当前 Artifact、State、Evidence 绑定（commit 为 hex SHA
        + evidence 文件非空且含 PASS + 逐个点名 artifact）
    C9  没有已知未解决的核心 Blocker
    C10 Effect 状态一致（声明必须引用盘上 evidence）
    C11 没有未经对账的 OUTCOME_UNKNOWN（声明必须引用盘上 evidence）
    C12 没有已经撤销却仍被使用的 Authority（声明必须引用盘上 evidence）

Honesty boundary (offline auditor): this gate runs offline against a
manifest.  It verifies three things machine-really: (a) on-disk
existence of every cited file (C2/C3/C4/C5/C6/C8/C1/C10/C11/C12
evidence), (b) content cross-binding — the review evidence file must be
non-empty, contain PASS, and name every artifact (C8), artifact states
at review level or above must agree with the reviewer verdict (C4), and
(c) every declarative boolean must cite an on-disk source a reviewer
can open.  It does not re-execute runners (that is run.cmd /
acceptance's job); a forger must therefore fake a whole on-disk trail,
not just flip JSON booleans.

Authority boundary (non_authority): the gate certifies machine
eligibility only.  Its verdict is FINAL_DONE_ELIGIBLE — never FINAL
DONE.  FINAL DONE itself is a Human Gate ruling (C-role/Human
Authority); no worker output can substitute it.  Every payload carries
non_authority=True and says so.

CLI:
    python final_gate.py check --file gate_manifest.json
    exit 0 = FINAL_DONE_ELIGIBLE, 2 = NOT_ELIGIBLE / invalid input
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import state_level as sl  # noqa: E402

SCHEMA = "v1.0-final-gate-74"

CONDITIONS: Tuple[Tuple[str, str], ...] = (
    ("C1", "goal_implemented"),
    ("C2", "deliverables_real"),
    ("C3", "acceptance_criteria_met"),
    ("C4", "artifacts_real"),
    ("C5", "machine_checks_passed"),
    ("C6", "evidence_present"),
    ("C7", "independent_reviewer_pass"),
    ("C8", "review_bound_to_artifacts"),
    ("C9", "no_unresolved_core_blockers"),
    ("C10", "effect_state_consistent"),
    ("C11", "no_unreconciled_unknown"),
    ("C12", "no_revoked_authority_in_use"),
)

_HEX_SHA = re.compile(r"^[0-9a-f]{7,40}$")


def _exists(path: Any) -> bool:
    if not path:
        return False
    try:
        return Path(str(path)).exists()
    except OSError:
        return False


def _read_text(path: Any) -> str:
    try:
        return Path(str(path)).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _check_c1(goal: Any) -> List[str]:
    if not isinstance(goal, dict):
        return ["C1_GOAL_MISSING"]
    if goal.get("implemented") is not True:
        return ["C1_GOAL_NOT_IMPLEMENTED"]
    if not goal.get("ref"):
        return ["C1_GOAL_REF_MISSING"]
    if not _exists(goal.get("evidence")):
        return ["C1_GOAL_EVIDENCE_NOT_FOUND"]
    return []


def _check_c2(deliverables: Any) -> List[str]:
    if not isinstance(deliverables, list) or not deliverables:
        return ["C2_NO_DELIVERABLES"]
    problems = []
    for i, d in enumerate(deliverables):
        if not isinstance(d, dict) or not d.get("name"):
            problems.append(f"C2_DELIVERABLE_MALFORMED:{i}")
        elif not _exists(d.get("path")):
            problems.append(f"C2_DELIVERABLE_NOT_FOUND:{d.get('name')}")
    return problems


def _check_c3(acceptance: Any) -> List[str]:
    if not isinstance(acceptance, dict):
        return ["C3_ACCEPTANCE_MISSING"]
    if acceptance.get("criteria_met") is not True:
        return ["C3_CRITERIA_NOT_MET"]
    if not acceptance.get("runner"):
        return ["C3_RUNNER_MISSING"]
    if not _exists(acceptance.get("runner")):
        return ["C3_RUNNER_NOT_FOUND"]
    return []


def _check_c4(artifacts: Any) -> List[str]:
    if not isinstance(artifacts, list) or not artifacts:
        return ["C4_NO_ARTIFACTS"]
    problems: List[str] = []
    for i, a in enumerate(artifacts):
        if not isinstance(a, dict) or not a.get("name"):
            problems.append(f"C4_ARTIFACT_MALFORMED:{i}")
            continue
        name = a.get("name")
        if not _exists(a.get("path")):
            problems.append(f"C4_ARTIFACT_NOT_FOUND:{name}")
            continue
        # §45 integration: state must be canonical; completion-level
        # states must present level-appropriate evidence.
        try:
            state = sl.validate_state(a.get("state"))
        except sl.StateLevelError as exc:
            problems.append(f"C4_ARTIFACT_STATE_INVALID:{name}:{exc}")
            continue
        claim_problems = sl.check_claim(state, a.get("evidence"))
        problems.extend(f"C4_ARTIFACT_CLAIM:{name}:{p}" for p in claim_problems)
    return problems


def _check_c4_review_mismatch(artifacts: Any, reviewer: Any) -> List[str]:
    """C4 交叉核验（R-E P2）：artifact 自报 review 级状态必须与
    Reviewer 实际裁定一致，脱钩即拒。"""
    verdict = reviewer.get("verdict") if isinstance(reviewer, dict) else None
    if verdict == "PASS" or not isinstance(artifacts, list):
        return []
    problems: List[str] = []
    for a in artifacts:
        if not isinstance(a, dict):
            continue
        try:
            state = sl.validate_state(a.get("state"))
        except sl.StateLevelError:
            continue
        if sl.LEVEL_RANK.get(state, -1) >= sl.LEVEL_RANK["R_REVIEW_PASS"]:
            problems.append(f"C4_STATE_REVIEW_MISMATCH:{a.get('name')}")
    return problems


def _check_c5(checks: Any) -> List[str]:
    if not isinstance(checks, list) or not checks:
        return ["C5_NO_MACHINE_CHECKS"]
    problems = []
    for i, c in enumerate(checks):
        if not isinstance(c, dict):
            problems.append(f"C5_CHECK_MALFORMED:{i}")
            continue
        if c.get("passed") is not True:
            problems.append(f"C5_CHECK_FAILED:{c.get('name', i)}")
            continue
        if not str(c.get("command") or "").strip():
            problems.append(f"C5_CHECK_NO_COMMAND:{c.get('name', i)}")
        if not _exists(c.get("evidence")):
            problems.append(f"C5_CHECK_EVIDENCE_NOT_FOUND:{c.get('name', i)}")
    return problems


def _check_c6(evidence: Any) -> List[str]:
    if not isinstance(evidence, list) or not evidence:
        return ["C6_NO_EVIDENCE"]
    return [f"C6_EVIDENCE_NOT_FOUND:{e}"
            for e in evidence if not _exists(e)]


def _check_c7_c8(reviewer: Any, artifacts: Any) -> List[str]:
    if not isinstance(reviewer, dict):
        return ["C7_REVIEWER_MISSING"]
    problems: List[str] = []
    if reviewer.get("independent") is not True:
        problems.append("C7_REVIEWER_NOT_INDEPENDENT")
    if reviewer.get("verdict") != "PASS":
        problems.append("C7_REVIEW_NOT_PASS")
    # C8: Review 与 Artifact/State/Evidence 绑定（R-E P1 升级）
    commit = str(reviewer.get("commit") or "").strip().lower()
    if not commit:
        problems.append("C8_REVIEW_COMMIT_MISSING")
    elif not _HEX_SHA.match(commit):
        problems.append("C8_REVIEW_COMMIT_MALFORMED")
    ev_path = reviewer.get("evidence")
    if not _exists(ev_path):
        problems.append("C8_REVIEW_EVIDENCE_NOT_FOUND")
    else:
        text = _read_text(ev_path)
        if not text.strip():
            problems.append("C8_REVIEW_EVIDENCE_EMPTY")
        elif "PASS" not in text.upper():
            problems.append("C8_REVIEW_EVIDENCE_NO_PASS")
        else:
            # 绑定的实质：review evidence 必须逐个点名 artifact。
            for a in (artifacts or []):
                if isinstance(a, dict) and a.get("name"):
                    if str(a["name"]) not in text:
                        problems.append(f"C8_REVIEW_NOT_BOUND:{a['name']}")
    return problems


def evaluate(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate all 12 conditions; return verdict + per-condition status."""
    if not isinstance(manifest, dict):
        raise ValueError("MANIFEST_MUST_BE_OBJECT")

    goal = manifest.get("goal")
    deliverables = manifest.get("deliverables")
    acceptance = manifest.get("acceptance")
    artifacts = manifest.get("artifacts")
    machine_checks = manifest.get("machine_checks")
    evidence = manifest.get("evidence")
    reviewer = manifest.get("reviewer")
    blockers = manifest.get("blockers") or []
    effect = manifest.get("effect_state") or {}
    authority = manifest.get("authority") or {}

    problems: List[str] = []
    problems += _check_c1(goal)
    problems += _check_c2(deliverables)
    problems += _check_c3(acceptance)
    problems += _check_c4(artifacts)
    problems += _check_c4_review_mismatch(artifacts, reviewer)
    problems += _check_c5(machine_checks)
    problems += _check_c6(evidence)
    problems += _check_c7_c8(reviewer, artifacts)
    if blockers:
        problems.extend(f"C9_BLOCKER_OPEN:{b}" for b in blockers)

    # C10/C11/C12：声明必须引用盘上证据源（R-E P1：不再纯自证布尔）。
    if not isinstance(effect, dict) or effect.get("consistent") is not True:
        problems.append("C10_EFFECT_STATE_INCONSISTENT")
    elif not _exists(effect.get("evidence")):
        problems.append("C10_EFFECT_EVIDENCE_NOT_FOUND")
    unknown = effect.get("unreconciled_unknown") if isinstance(effect, dict) else None
    if unknown != 0:
        problems.append(f"C11_UNRECONCILED_UNKNOWN:{unknown}")
    elif not _exists(effect.get("evidence")):
        problems.append("C11_EFFECT_EVIDENCE_NOT_FOUND")
    revoked = authority.get("revoked_still_used") if isinstance(authority, dict) else None
    if revoked != 0:
        problems.append(f"C12_REVOKED_AUTHORITY_IN_USE:{revoked}")
    elif not _exists(authority.get("evidence") if isinstance(authority, dict) else None):
        problems.append("C12_AUTHORITY_EVIDENCE_NOT_FOUND")

    per_condition = {}
    for code, key in CONDITIONS:
        hits = [p for p in problems if p.startswith(code + "_")]
        per_condition[code] = {"condition": key, "ok": not hits,
                              **({"problems": hits} if hits else {})}
    eligible = not problems
    return {
        "schema": SCHEMA,
        "verdict": "FINAL_DONE_ELIGIBLE" if eligible else "NOT_ELIGIBLE",
        "conditions": per_condition,
        "problems": problems,
        "ok": eligible,
        "human_gate": "FINAL DONE 本身是 Human Gate 裁定：本门禁只证明机器"
                      "资格（FINAL_DONE_ELIGIBLE），任何 Worker/Brain/C/R "
                      "单独声称'已完成'均不构成 FINAL DONE。",
        "non_authority": True,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Canonical §74 twelve-condition FINAL gate (non-authority)")
    ap.add_argument("cmd", choices=["check"])
    ap.add_argument("--file", required=True, help="gate manifest JSON")
    args = ap.parse_args(argv)

    mp = Path(args.file)
    if not mp.exists():
        print(json.dumps({"schema": SCHEMA, "ok": False,
                          "problem": "MANIFEST_NOT_FOUND",
                          "non_authority": True}, ensure_ascii=False))
        return 2
    try:
        manifest = json.loads(mp.read_text(encoding="utf-8"))
        result = evaluate(manifest)
    except Exception as exc:  # fail-closed: 畸形输入一律 exit 2
        print(json.dumps({"schema": SCHEMA, "ok": False,
                          "problem": f"MANIFEST_INVALID:{exc}",
                          "non_authority": True}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
