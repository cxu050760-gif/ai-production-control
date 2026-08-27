#!/usr/bin/env python3
"""Machine-bound V0.9 speculative authority/effect Evidence generator."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MATRIX = HERE / "fixtures" / "v09_authority_effect_attack_cases.json"
ATTACK_RUNNER = HERE / "test_v09_attack_matrix_offline.py"
EXPECTED_BASE = "b65a51267969824c05a8794376eac766edc08eb9"


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def validate_sha(name: str, value: str) -> str:
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value.lower()):
        raise RuntimeError(f"{name} must be an exact 40-hex SHA")
    git("cat-file", "-e", f"{value}^{{commit}}")
    return value.lower()


def collect_observations() -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="v09-evidence-") as tmp:
        result_path = Path(tmp) / "attack-results.jsonl"
        proc = subprocess.run(
            [sys.executable, str(ATTACK_RUNNER), "--emit-jsonl", str(result_path)], cwd=ROOT, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"attack collector failed rc={proc.returncode}: stdout={proc.stdout[-2000:]} stderr={proc.stderr[-2000:]}"
            )
        records = [json.loads(line) for line in result_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-sha", default=EXPECTED_BASE)
    parser.add_argument("--candidate-sha")
    parser.add_argument("--output", default="-")
    args = parser.parse_args(argv)

    base_sha = validate_sha("base_sha", args.base_sha)
    if base_sha != EXPECTED_BASE:
        raise RuntimeError("speculative Evidence must remain bound to the frozen speculative base")
    candidate_sha = validate_sha("candidate_sha", args.candidate_sha or git("rev-parse", "HEAD"))
    head_sha = git("rev-parse", "HEAD").lower()
    if candidate_sha != head_sha:
        raise RuntimeError(f"candidate_sha must equal checked-out HEAD: candidate={candidate_sha} head={head_sha}")
    if subprocess.run(["git", "merge-base", "--is-ancestor", base_sha, candidate_sha], cwd=ROOT,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode != 0:
        raise RuntimeError("candidate is not a descendant of speculative base")

    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    if matrix.get("attack_case_count") != 36:
        raise RuntimeError("attack matrix count must remain 36")
    expected_ids = [f"V09-R{i:02d}" for i in range(1, 37)]
    cases = matrix.get("cases") or []
    if [case.get("id") for case in cases] != expected_ids:
        raise RuntimeError("attack matrix IDs/order changed")
    by_id = {case["id"]: case for case in cases}

    raw = collect_observations()
    if len(raw) != 36 or [item.get("test_id") for item in raw] != expected_ids:
        raise RuntimeError("attack runner did not produce the exact frozen 36-case sequence")
    if any(item.get("expected_outcome") != by_id[item["test_id"]]["expected_outcome"] for item in raw):
        raise RuntimeError("attack runner expected outcomes diverged from matrix")
    if any(key in item for item in raw for key in ("skip", "skipped", "xfail", "xfailed")):
        raise RuntimeError("skip/xfail markers are forbidden")

    evidence_records: list[dict[str, Any]] = []
    for item in raw:
        record = {
            "base_sha": base_sha,
            "candidate_sha": candidate_sha,
            "attack_matrix_version": matrix["attack_matrix_version"],
            "test_id": item["test_id"],
            "expected_outcome": item["expected_outcome"],
            "observed_outcome": item["observed_outcome"],
            "external_effect_count": int(item.get("external_effect_count", 0)),
            "final_effect_status": item.get("final_effect_status", "UNKNOWN"),
            "authorization_identity": item.get("authorization_identity", "NONE"),
            "generation_fence": item.get("generation_fence", "NOT_APPLICABLE"),
            "reconciliation_result": item.get("reconciliation_result", "NOT_RUN"),
            "detail": item.get("detail", ""),
            "overall_result": "MATCH" if item.get("matched") is True else "RED",
        }
        record["evidence_digest"] = digest(record)
        evidence_records.append(record)

    red = sum(record["overall_result"] == "RED" for record in evidence_records)
    crown = [record for record in evidence_records if record["test_id"] in {f"V09-R{i:02d}" for i in range(19, 23)}]
    crown_exactly_once = all(record["external_effect_count"] == 1 for record in crown)
    crown_match = all(record["overall_result"] == "MATCH" for record in crown)
    crown_status = "READY" if crown_match and crown_exactly_once else "RED"

    report: dict[str, Any] = {
        "schema": "v09-authority-effect-evidence-1",
        "speculative": True,
        "base_sha": base_sha,
        "candidate_sha": candidate_sha,
        "attack_matrix_version": matrix["attack_matrix_version"],
        "attack_matrix_count": 36,
        "red_baseline_count": red,
        "matched_count": 36 - red,
        "crown_test_status": crown_status,
        "crown_real_effect_count_invariant": crown_exactly_once,
        "overall_result": "RED_BASELINE" if red else "TEST_EVIDENCE_READY",
        "records": evidence_records,
    }
    report["evidence_digest"] = digest(report)

    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
        print(json.dumps({
            "output": str(target), "attack_matrix_count": 36, "red_baseline_count": red,
            "crown_test_status": crown_status, "overall_result": report["overall_result"],
            "evidence_digest": report["evidence_digest"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
