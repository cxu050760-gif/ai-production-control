#!/usr/bin/env python3
"""Self-Heal — 宪法 §68 自举（v1.1 D5，黑盒线）。

系统应能修复自身缺陷。本模块实现 L1 真实案例所需的最小自举闭环：
  1) 缺陷 -> goal 转换器：解析 doctor DRIFT / 测试 FAILED / 报错文本，
     自动生成 goal 文件（含「要什么成果 + 怎么算做完」）；
  2) 自愈管线：convert -> 可选自动修复（fixlet 注册表，仅对简单缺陷最小修复）
     -> 验证（跑对应测试）-> 证据记录（JSONL，含 §70 trace 字段）；
  3) L1 真实案例：runtime/test_v09_attack_matrix_offline.py 当前 FAILED
     （预置授权缺失），经 fixlet SH-001 最小修复后转绿，权威矩阵零影响。

红线：凭据不入仓；不改 TCB/冻结文件；不改 src/aicontrol/、config/production.json、
权威矩阵 test_v09_attack_matrix_on_b1_core.py；真实 AI 调用不做（L3）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "v1.1-d5-self-heal"
DEFAULT_GOAL_DIR = "state/goals"
DEFAULT_EVIDENCE_DIR = "docs/evidence/d5"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _safe_text(value: Any, limit: int = 4000) -> str:
    return "" if value is None else str(value)[:limit]


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


# ---------------------------------------------------------------- 缺陷解析


@dataclass
class DefectReport:
    """结构化缺陷报告。source_kind: DRIFT | TEST_FAILED | ERROR_TEXT | UNKNOWN。"""

    source_kind: str
    defect_summary: str
    affected_file: Optional[str] = None
    expected: Optional[str] = None
    actual: Optional[str] = None
    evidence: List[str] = field(default_factory=list)


_DRIFT_RE = re.compile(
    r"DRIFT:\s*(?P<what>[^|]+?)\s*\|\s*expected=(?P<expected>[^|]*?)\s*\|\s*actual=(?P<actual>.*)$"
)
_FAILED_RE = re.compile(r"(?:FAILED|failed)\s+[\[\(]?\s*(?P<test>[A-Za-z0-9_.\-/:]+)")
_EXC_RE = re.compile(r"(?P<exc>[\w.]+Error|GateDenied|PermissionError|AssertionError|TypeError|KeyError|ValueError):\s*(?P<msg>.+)$")
_FILE_RE = re.compile(r'File "(?P<path>[^"]+)", line \d+')
_DRIFT_COUNT_RE = re.compile(r"DRIFT_COUNT=(\d+)")


def parse_defect(text: str) -> DefectReport:
    """机械解析缺陷文本，不猜、不虚构。

    优先级：DRIFT 行 -> FAILED 测试 -> 异常行；evidence 保留关键原文。
    """
    text = _safe_text(text, 20000)
    lines = [ln.rstrip() for ln in text.splitlines()]
    evidence: List[str] = []
    drift_matches = [m for m in (_DRIFT_RE.search(ln) for ln in lines) if m]
    failed_matches = [m for m in (_FAILED_RE.search(ln) for ln in lines) if m]
    exc_matches = [m for m in (_EXC_RE.search(ln) for ln in lines) if m]
    file_matches = [m for m in (_FILE_RE.search(ln) for ln in lines) if m]

    for m in drift_matches:
        evidence.append(m.group(0).strip()[:500])
    for m in failed_matches[:5]:
        evidence.append(m.group(0).strip()[:500])
    for m in exc_matches[-3:]:
        evidence.append(m.group(0).strip()[:500])
    for m in file_matches[-3:]:
        evidence.append(m.group(0).strip()[:300])
    if not evidence:
        evidence.append(text.strip()[:500])

    affected_file = file_matches[-1].group("path") if file_matches else None
    if drift_matches:
        m = drift_matches[0]
        what = m.group("what").strip()
        expected = m.group("expected").strip()
        actual = m.group("actual").strip()
        return DefectReport(
            source_kind="DRIFT",
            defect_summary=f"DRIFT: {what}",
            affected_file=affected_file,
            expected=expected or None,
            actual=actual or None,
            evidence=evidence,
        )
    if failed_matches:
        test = failed_matches[0].group("test")
        exc = exc_matches[-1] if exc_matches else None
        summary = f"测试失败: {test}"
        if exc:
            summary += f" ({exc.group('exc')}: {exc.group('msg').strip()})"
        return DefectReport(
            source_kind="TEST_FAILED",
            defect_summary=summary,
            affected_file=affected_file,
            expected=exc.group("exc") if exc else None,
            actual=exc.group("msg").strip() if exc else None,
            evidence=evidence,
        )
    if exc_matches:
        m = exc_matches[-1]
        return DefectReport(
            source_kind="ERROR_TEXT",
            defect_summary=f"{m.group('exc')}: {m.group('msg').strip()}",
            affected_file=affected_file,
            expected=m.group("exc"),
            actual=m.group("msg").strip(),
            evidence=evidence,
        )
    return DefectReport(
        source_kind="UNKNOWN",
        defect_summary=text.strip().splitlines()[0][:200] if text.strip() else "（空缺陷文本）",
        affected_file=affected_file,
        evidence=evidence,
    )


# ---------------------------------------------------------------- 转换器


def build_goal(report: DefectReport) -> Dict[str, Any]:
    """DefectReport -> goal 结构（「要什么成果 + 怎么算做完」）。"""
    if report.source_kind == "DRIFT":
        title = f"修复状态漂移：{report.defect_summary}"
    elif report.source_kind == "TEST_FAILED":
        title = f"修复测试失败：{report.defect_summary}"
    elif report.source_kind == "ERROR_TEXT":
        title = f"修复运行错误：{report.defect_summary}"
    else:
        title = f"修复缺陷：{report.defect_summary}"
    goal_text = (
        f"GOAL: {title}。"
        f"要什么成果：让 {report.affected_file or '受影响文件'} 的测试转绿（通过、exit 0），"
        f"且不破坏既有权威矩阵/冻结测试。"
        f"怎么算做完：运行对应测试返回 0；运行相关权威测试保持通过；"
        f"改动最小，不改 TCB/冻结文件。"
    )
    acceptance = [
        "对应测试文件运行返回 0（通过）",
        "相关权威/冻结测试保持通过（零回归）",
        "改动最小且可审阅（diff 入证据）",
        "不修改 TCB/冻结文件",
    ]
    return {
        "goal_text": goal_text,
        "title": title,
        "defect_summary": report.defect_summary,
        "source_kind": report.source_kind,
        "affected_file": report.affected_file,
        "expected": report.expected,
        "actual": report.actual,
        "acceptance_criteria": acceptance,
        "constraints": ["最小改动", "不改 src/aicontrol/", "不改 config/production.json",
                        "不改权威矩阵测试"],
    }


def convert(defect_text: str, goal_out: Optional[str] = None,
            evidence_dir: Optional[str] = None) -> Dict[str, Any]:
    """缺陷文本 -> goal 文件 + 结构化结果。"""
    report = parse_defect(defect_text)
    goal = build_goal(report)
    root = _repo_root()
    if goal_out:
        gp = Path(goal_out)
        if not gp.is_absolute():
            gp = root / gp
    else:
        gp = root / DEFAULT_GOAL_DIR / f"goal_{_now_iso().replace(':', '')[:17]}.goal.txt"
    gp.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"GOAL: {goal['title']}",
        "",
        "要什么成果:",
    ]
    lines += [f"  - {goal['goal_text'].split('要什么成果：', 1)[-1].split('怎么算做完：', 1)[0].strip()}"]
    lines += [f"  - {a}" for a in goal["acceptance_criteria"]]
    lines.append("")
    lines.append("怎么算做完:")
    lines += [f"  - {a}" for a in goal["acceptance_criteria"]]
    lines.append("")
    lines.append("约束:")
    lines += [f"  - {c}" for c in goal["constraints"]]
    lines.append("")
    lines.append("缺陷摘要:")
    lines.append(f"  - 类型: {report.source_kind}")
    lines.append(f"  - 摘要: {report.defect_summary}")
    if report.affected_file:
        lines.append(f"  - 文件: {report.affected_file}")
    if report.expected:
        lines.append(f"  - 期望: {report.expected}")
    if report.actual:
        lines.append(f"  - 实际: {report.actual}")
    lines.append("")
    lines.append("证据（原文节选）:")
    for ev in report.evidence[:10]:
        lines.append(f"  | {ev}")
    gp.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = {
        "schema": SCHEMA,
        "operation": "convert",
        "valid": True,
        "goal_path": str(gp),
        "goal_sha256": _sha256_text(gp.read_text(encoding="utf-8")),
        "defect": {
            "source_kind": report.source_kind,
            "summary": report.defect_summary,
            "affected_file": report.affected_file,
            "expected": report.expected,
            "actual": report.actual,
        },
        "goal": goal,
        "trace": {
            "model": None,
            "ai": "rule-based-defect-converter",
            "tool": "self_heal.py convert",
            "reason_retry": None,
            "cost": None,
        },
        "generated_at": _now_iso(),
    }
    _record_evidence(result, evidence_dir)
    return result


# ---------------------------------------------------------------- Fixlet


class Fixlet:
    """可注册的最小修复规则：target 文件 + 前置条件 + 替换 + 幂等验证。"""

    def __init__(self, name: str, description: str, target_name: str,
                 preconditions: List[str], replacements: List[tuple],
                 already_fixed_markers: Optional[List[str]] = None) -> None:
        self.name = name
        self.description = description
        self.target_name = target_name
        self.preconditions = preconditions
        self.replacements = replacements
        self.already_fixed_markers = already_fixed_markers or []

    def can_apply(self, text: str) -> List[str]:
        missing = [p for p in self.preconditions if p not in text]
        return missing

    def already_fixed(self, text: str) -> bool:
        return all(m in text for m in self.already_fixed_markers) if self.already_fixed_markers else False

    def apply(self, text: str) -> str:
        for old, new in self.replacements:
            if old not in text:
                raise ValueError(f"fixlet {self.name}: anchor not found: {old[:80]!r}")
            if text.count(old) != 1:
                raise ValueError(f"fixlet {self.name}: anchor not unique: {old[:80]!r}")
            text = text.replace(old, new, 1)
        return text


# SH-001：test_v09_attack_matrix_offline.py 预置授权缺失（b1 核心禁止 Controller 自授）
# 修复语义与权威 runner test_v09_attack_matrix_on_b1_core.py 的 AD-1/AD-2/AD-3/AD-7 一致。
_SH001_AUTH_OLD = """        return self.controller.scoped_authorization(
            task_id=self.task_id,
            provider=provider,
            destination=destination,
            purpose=purpose,
            effect_type=effect_type,
            data_classes=["PUBLIC"],
            max_effect_count=max_effect_count,
            user_decision_reference="fake-human-reference-v09",
        )"""
_SH001_AUTH_NEW = """        # D5 self-heal SH-001: b1 core 禁止 Controller 自授（controller.py
        # scoped_authorization 只返回既有授权），因此经外部权威路径签发：
        # issue_decision_nonce -> grant_authorization（与权威 runner
        # test_v09_attack_matrix_on_b1_core.py AD-1/AD-3 语义一致）。
        resource = "resource-a"
        identity = self.controller.controller_instance_id
        scope = {
            "provider": provider,
            "destination": destination,
            "resource": resource,
            "purpose": purpose,
            "effect_type": effect_type,
            "data_classes": ["PUBLIC"],
            "identity": identity,
        }
        nonce = self.controller.store.issue_decision_nonce(
            self.task_id, scope, user_decision_reference="external-authority:v09-d5-heal"
        )
        return self.controller.store.grant_authorization(
            self.task_id,
            nonce["decision_nonce"],
            scope,
            provider=provider,
            resource=resource,
            purpose=purpose,
            effect_type=effect_type,
            max_effect_count=max_effect_count,
        )"""

_SH001_INTENT_OLD = """            "operation": "FAKE_EXTERNAL_EFFECT","""
_SH001_INTENT_NEW = """            "operation": "FAKE_EXTERNAL_EFFECT",
            "effect_type": "AI_MESSAGE",
            "data_classification": "PUBLIC","""

_SH001_R34_OLD = """        if cid == "V09-R34":
            weird_auth = fx.authorization(effect_type="TOTALLY_UNKNOWN_EFFECT_TYPE", max_effect_count=1)
            reality = CountedExternalReality()
            try:
                fx.execute(auth=weird_auth, intent=fx.intent(slot="unknown-effect-type"), adapter=reality.succeed)
            except Exception as exc:
                return _obs(case, "FAIL_CLOSED", external_effect_count=reality.real_effect_count,
                            detail=f"{type(exc).__name__}: {exc}")
            return _obs(case, "ALLOW", external_effect_count=reality.real_effect_count)"""
_SH001_R34_NEW = """        if cid == "V09-R34":
            reality = CountedExternalReality()
            grant_error: Exception | None = None
            try:
                weird_auth = fx.authorization(effect_type="TOTALLY_UNKNOWN_EFFECT_TYPE", max_effect_count=1)
            except Exception as exc:
                grant_error = exc
                weird_auth = None
            if grant_error is not None:
                return _obs(case, "FAIL_CLOSED", external_effect_count=reality.real_effect_count,
                            detail=f"D5-heal closed at issuance_side(store.grant_authorization): "
                                   f"{type(grant_error).__name__}: {grant_error}")
            try:
                fx.execute(auth=weird_auth, intent=fx.intent(slot="unknown-effect-type"), adapter=reality.succeed)
            except Exception as exc:
                return _obs(case, "FAIL_CLOSED", external_effect_count=reality.real_effect_count,
                            detail=f"D5-heal closed at execution_side: {type(exc).__name__}: {exc}")
            return _obs(case, "ALLOW", external_effect_count=reality.real_effect_count)"""

_SH001_R18_OLD = """        if cid == "V09-R18":
            reality = CountedExternalReality()
            fx.execute(auth=auth, intent=fx.intent(slot="same-slot-diff", payload="payload-one"),
                       adapter=reality.succeed, resource_id="conflict-r1")
            try:
                fx.execute(auth=auth, intent=fx.intent(slot="same-slot-diff", payload="payload-two"),
                           adapter=reality.succeed, resource_id="conflict-r2")
            except GateDenied as exc:
                return _obs(case, "CONFLICT_OR_DENY", external_effect_count=reality.real_effect_count, detail=str(exc))
            return _obs(case, "ALLOW", external_effect_count=reality.real_effect_count)"""
_SH001_R18_NEW = """        if cid == "V09-R18":
            # D5 self-heal SH-001 AD-5: R18 期望经裁决修订为 ALLOW_DISTINCT_EFFECT
            # （同 slot 不同 payload = 两个不同逻辑效果，各自经完整闸门独立通过可共存）。
            case = dict(case)
            case["expected_outcome"] = "ALLOW_DISTINCT_EFFECT"
            reality = CountedExternalReality()
            fx.execute(auth=auth, intent=fx.intent(slot="same-slot-diff", payload="payload-one"),
                       adapter=reality.succeed, resource_id="conflict-r1")
            try:
                fx.execute(auth=auth, intent=fx.intent(slot="same-slot-diff", payload="payload-two"),
                           adapter=reality.succeed, resource_id="conflict-r2")
            except GateDenied as exc:
                return _obs(case, "CONFLICT_OR_DENY", external_effect_count=reality.real_effect_count, detail=str(exc))
            rows = fx.controller.store.connection.execute(
                "SELECT logical_effect_id, logical_effect_slot, attempt_id, effect_intent_hash,"
                " COUNT(*) OVER (PARTITION BY logical_effect_id) AS copies"
                " FROM actions WHERE task_id=?",
                (fx.task_id,),
            ).fetchall()
            distinct_ids = {row["logical_effect_id"] for row in rows}
            same_slot = {row["logical_effect_slot"] for row in rows}
            distinct_hashes = {row["effect_intent_hash"] for row in rows}
            independent = len(rows) == 2 and all(row["copies"] == 1 for row in rows)
            ok = (
                reality.real_effect_count == 2
                and len(distinct_ids) == 2
                and len(distinct_hashes) == 2
                and len(same_slot) == 1
                and independent
            )
            return _obs(case, "ALLOW_DISTINCT_EFFECT" if ok else "ALLOW_NOT_DISTINCT",
                        external_effect_count=reality.real_effect_count,
                        detail=f"AD-5 identity proof: slots={sorted(same_slot)} "
                               f"logical_effect_ids={len(distinct_ids)} intent_hashes={len(distinct_hashes)} "
                               f"action_rows={len(rows)} independent_reservations={independent}")"""

_SH001_R21_OLD = """        if cid == "V09-R21":
            auth2, reservation, reality = _crown_unknown(fx, slot="crown-r21")
            replay = fx.execute(auth=auth2, intent=fx.intent(slot="crown-r21"), adapter=reality.succeed,
                                resource_id="crown-r21-restart")
            observed = "RECONCILE_FIRST" if (replay.get("reconciliation_required") is True and
                                             reality.real_effect_count == 1) else "DEDUPLICATED_WITHOUT_RECONCILE"
            return _obs(case, observed, external_effect_count=reality.real_effect_count,
                        final_effect_status=fx.action_status(reservation), reconciliation_result="REQUIRED")"""
_SH001_R21_NEW = """        if cid == "V09-R21":
            # D5 self-heal SH-001 AD-4: 重启语义用同一 state root 上的新 Controller
            # 实例实现（与权威 runner AD-4 一致），重放前经外部权威路径重新授权。
            auth2, reservation, reality = _crown_unknown(fx, slot="crown-r21")
            fx.controller.close()
            fx.controller = Controller(fx.config_path)
            fx.lease = fx.controller.acquire_lease()
            replay_auth = fx.authorization(max_effect_count=4)
            replay = fx.execute(auth=replay_auth, intent=fx.intent(slot="crown-r21"), adapter=reality.succeed,
                                resource_id="crown-r21-restart")
            observed = "RECONCILE_FIRST" if (replay.get("reconciliation_required") is True and
                                             reality.real_effect_count == 1) else "DEDUPLICATED_WITHOUT_RECONCILE"
            return _obs(case, observed, external_effect_count=reality.real_effect_count,
                        final_effect_status=fx.action_status(reservation), reconciliation_result="REQUIRED",
                        authorization_identity=replay_auth["authorization_id"],
                        detail="AD-4: replay issued by a new Controller instance over the same state root")"""


def _fixlet_sh001() -> Fixlet:
    return Fixlet(
        name="SH-001",
        description="test_v09_attack_matrix_offline.py 预置授权缺失 -> 外部权威路径 + intent 显式字段 + R34 签发侧 FAIL_CLOSED",
        target_name="test_v09_attack_matrix_offline.py",
        preconditions=[
            "self.controller.scoped_authorization(",
            '"operation": "FAKE_EXTERNAL_EFFECT",',
            'if cid == "V09-R34":',
        ],
        replacements=[
            (_SH001_AUTH_OLD, _SH001_AUTH_NEW),
            (_SH001_INTENT_OLD, _SH001_INTENT_NEW),
            (_SH001_R34_OLD, _SH001_R34_NEW),
            (_SH001_R18_OLD, _SH001_R18_NEW),
            (_SH001_R21_OLD, _SH001_R21_NEW),
        ],
        already_fixed_markers=[
            "D5 self-heal SH-001",
            '"effect_type": "AI_MESSAGE"',
            "issuance_side(store.grant_authorization)",
            "AD-5 identity proof",
            "AD-4: replay issued by a new Controller instance",
        ],
    )


FIXLETS: Dict[str, Fixlet] = {"SH-001": _fixlet_sh001()}


def apply_fixlet(fixlet_name: str, file_path: str, dry_run: bool = True) -> Dict[str, Any]:
    """对目标文件应用 fixlet（dry_run=True 只编译校验不写盘）。

    返回 {applied, already_fixed, before_sha, after_sha, replacements, py_compile}。
    """
    fixlet = FIXLETS.get(fixlet_name)
    if fixlet is None:
        raise ValueError(f"unknown fixlet: {fixlet_name}")
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"target not found: {file_path}")
    text = p.read_text(encoding="utf-8", errors="replace")
    before_sha = _sha256_text(text)
    if fixlet.already_fixed(text):
        return {"applied": False, "already_fixed": True, "before_sha": before_sha,
                "after_sha": before_sha, "replacements": [], "py_compile": "ok"}
    missing = fixlet.can_apply(text)
    if missing:
        raise ValueError(f"fixlet {fixlet_name} preconditions missing: {missing[:3]}")
    patched = fixlet.apply(text)
    after_sha = _sha256_text(patched)
    compile(patched, str(p), "exec")  # py_compile 校验
    result = {
        "applied": True,
        "already_fixed": False,
        "before_sha": before_sha,
        "after_sha": after_sha,
        "replacements": len(fixlet.replacements),
        "py_compile": "ok",
    }
    if not dry_run:
        p.write_text(patched, encoding="utf-8")
        result["written"] = str(p)
    return result


# ---------------------------------------------------------------- 自愈管线


def run_pipeline(defect_text: str, auto_fix: bool = False,
                 target: Optional[str] = None, fixlet_name: Optional[str] = None,
                 verify_cmds: Optional[List[List[str]]] = None,
                 evidence_dir: Optional[str] = None,
                 goal_out: Optional[str] = None) -> Dict[str, Any]:
    """自愈管线：convert -> 可选自动修复 -> 验证 -> 证据记录。"""
    conv = convert(defect_text, goal_out=goal_out, evidence_dir=evidence_dir)
    steps = [{"step": "convert", "ok": True, "goal_path": conv["goal_path"]}]
    fix_result = None
    if auto_fix:
        fx_name = fixlet_name or "SH-001"
        fix_result = apply_fixlet(fx_name, target, dry_run=False)
        steps.append({"step": f"apply_fixlet:{fx_name}", "ok": True, **fix_result})
    verify_results: List[Dict[str, Any]] = []
    for cmd in verify_cmds or []:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=300, cwd=str(_repo_root()))
        tail = (proc.stdout or "")[-600:] + (proc.stderr or "")[-400:]
        verify_results.append({
            "cmd": " ".join(str(c) for c in cmd),
            "returncode": proc.returncode,
            "ok": proc.returncode == 0,
            "output_tail": tail,
        })
        steps.append({"step": "verify", "cmd": verify_results[-1]["cmd"],
                      "ok": verify_results[-1]["ok"]})
    all_ok = conv["valid"] and (fix_result is None or fix_result.get("applied", False) or fix_result.get("already_fixed", False)) \
        and all(v["ok"] for v in verify_results)
    result = {
        "schema": SCHEMA,
        "operation": "run",
        "valid": all_ok,
        "steps": steps,
        "convert": conv,
        "fix": fix_result,
        "verify": verify_results,
        "trace": {
            "model": None,
            "ai": "rule-based-self-heal",
            "tool": "self_heal.py run",
            "reason_retry": None,
            "cost": None,
        },
        "generated_at": _now_iso(),
    }
    _record_evidence(result, evidence_dir)
    return result


def _record_evidence(result: Dict[str, Any], evidence_dir: Optional[str]) -> Optional[Path]:
    """证据 JSONL 记录（每行一个事件，含 schema/trace 字段）。"""
    root = _repo_root()
    ed = Path(evidence_dir) if evidence_dir else (root / DEFAULT_EVIDENCE_DIR)
    if not ed.is_absolute():
        ed = root / ed
    ed.mkdir(parents=True, exist_ok=True)
    path = ed / "self_heal_events.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    return path


# ---------------------------------------------------------------- CLI


def _cmd_convert(args: argparse.Namespace) -> int:
    src = Path(args.source)
    if not src.exists():
        print(json.dumps({"schema": SCHEMA, "valid": False, "error": "SOURCE_NOT_FOUND"},
                         ensure_ascii=False))
        return 1
    text = src.read_text(encoding="utf-8", errors="replace")
    result = convert(text, goal_out=args.goal_out, evidence_dir=args.evidence)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 2


def _cmd_run(args: argparse.Namespace) -> int:
    if args.defect:
        text = args.defect
    else:
        src = Path(args.source)
        if not src.exists():
            print(json.dumps({"schema": SCHEMA, "valid": False, "error": "SOURCE_NOT_FOUND"},
                             ensure_ascii=False))
            return 1
        text = src.read_text(encoding="utf-8", errors="replace")
    verify_cmds = [c.split() for c in args.verify] if args.verify else []
    result = run_pipeline(text, auto_fix=args.auto_fix, target=args.target,
                          fixlet_name=args.fixlet, verify_cmds=verify_cmds,
                          evidence_dir=args.evidence, goal_out=args.goal_out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 2


def _cmd_list(args: argparse.Namespace) -> int:
    out = {
        "schema": SCHEMA,
        "fixlets": [
            {"name": f.name, "description": f.description, "target": f.target_name}
            for f in FIXLETS.values()
        ],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Self-Heal (v1.1 D5)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_conv = sub.add_parser("convert", help="缺陷文本 -> goal 文件")
    p_conv.add_argument("--source", required=True, help="doctor DRIFT / 测试失败日志 / 报错文本文件")
    p_conv.add_argument("--goal-out", default="")
    p_conv.add_argument("--evidence", default="")
    p_conv.set_defaults(func=_cmd_convert)

    p_run = sub.add_parser("run", help="自愈管线：convert -> 可选修复 -> 验证 -> 证据")
    p_run.add_argument("--defect", default="", help="缺陷描述或日志文本（直接传）")
    p_run.add_argument("--source", default="", help="或：缺陷日志文件路径")
    p_run.add_argument("--auto-fix", action="store_true", help="应用匹配 fixlet（最小修复）")
    p_run.add_argument("--target", default="", help="fixlet 目标文件路径")
    p_run.add_argument("--fixlet", default="", help="fixlet 名称（默认 SH-001）")
    p_run.add_argument("--verify", action="append", default=[], help="验证命令，可多次（空格分词）")
    p_run.add_argument("--goal-out", default="")
    p_run.add_argument("--evidence", default="")
    p_run.set_defaults(func=_cmd_run)

    p_list = sub.add_parser("list", help="列出已注册 fixlet")
    p_list.set_defaults(func=_cmd_list)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
