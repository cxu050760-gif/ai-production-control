"""V0.8 B3 machine Evidence. No Adapter/Registry implementation lives here."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
BASE = "a184e2bd1f42d62bae6d195814fe4bf5ac30be4e"
VERSION = "V0.8"
SCHEMA = "v0.8-adapter-evidence/2"
MATRIX_SCHEMA = "v0.8-adapter-attack-matrix"
MATRIX_VERSION = "V08-ATTACK-MATRIX-2"
ATTACK_RESULT_PREFIX = "V08_ATTACK_RESULT="
SUCCESS = "V08_ADAPTER_EVIDENCE_OK"

PATHS = (
    "runtime/run.cmd",
    "runtime/v08_adapter_contract.py",
    "runtime/v08_adapter.py",
    "runtime/fixtures/v08_fixture_worker.py",
    "runtime/test_v08_adapter_core_offline.py",
    "runtime/bootstrap.json",
    "runtime/v08_adapter_registry.json",
    "runtime/test_v08_adapter_registry_offline.py",
    "runtime/fixtures/v08_adapter_registry_attack_cases.json",
    "runtime/v08_adapter_evidence.py",
    "runtime/test_v08_adapter_evidence_offline.py",
    "runtime/fixtures/v08_adapter_attack_cases.json",
)
OWN = {"b1": PATHS[:5], "b2": PATHS[5:9], "b3": PATHS[9:]}
CORE = ("runtime/v08_adapter_contract.py", "runtime/v08_adapter.py")
ISOLATION = CORE + ("runtime/fixtures/v08_fixture_worker.py",)
REGISTRY = "runtime/v08_adapter_registry.json"
REQUIRED_FIELDS = (
    "schema",
    "version",
    "accepted_base_sha",
    "candidate_sha",
    "b1_commit",
    "b2_commit",
    "b3_commit",
    "changed_files",
    "changed_file_hashes",
    "test_command",
    "exit_code",
    "test_result",
    "attack_case_id",
    "attack_result",
    "worker_replacement_proof",
    "provider_separation_proof",
    "artifact_integrity_proof",
    "source_binding_proof",
    "authority_isolation_proof",
    "effect_isolation_proof",
    "backward_regression_result",
    "generated_at",
)
DEFAULT_IDENTITIES = {
    "fixture-alpha",
    "fixture-beta",
    "chatgpt-web",
    "chatgpt",
    "workbuddy",
    "codex",
}
TRANSPORT = {
    "bsk",
    "daemon",
    "marker",
    "yz_lib",
    "52900",
    "chrome-extension",
    "cft_executable",
    "bsk_daemon_port",
    "dom hack",
    "click internals",
    "bridge",
}
AUTH = {
    "grant_authority",
    "revoke_authority",
    "set_authority",
    "mutate_authority",
    "mutate_authority_state",
    "promote",
    "promote_milestone",
    "crown",
    "crown_candidate",
    "assign_verdict",
    "set_verdict",
    "reviewer_pass",
}
EFFECT = {
    "reserve_effect",
    "effect_reservation",
    "commit_effect",
    "effect_wal",
    "effect_wal_commit",
    "authorize_effect",
    "authorize_external_effect",
    "execute_external_effect",
    "external_effect_permission",
}


class EvidenceError(RuntimeError):
    def __init__(self, code: str, status: str = "HARD_FAIL"):
        super().__init__(f"{status}:{code}")
        self.code = code
        self.status = status


def die(code: str, status: str = "HARD_FAIL") -> None:
    raise EvidenceError(code, status)


def sha(label: str, value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        die(f"{label}_BAD_SHA")
    return value


def run(root: Path, *cmd: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        cmd,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if check and proc.returncode:
        die(f"COMMAND_FAILED:{' '.join(cmd)}:{proc.returncode}")
    return proc


def gt(root: Path, *args: str) -> str:
    return run(root, "git", *args).stdout.strip()


def exists(root: Path, commit: str) -> bool:
    return run(root, "git", "cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode == 0


def need_commit(root: Path, label: str, commit: str, status: str = "HARD_FAIL") -> None:
    sha(label, commit)
    if not exists(root, commit):
        die(f"{label}_NOT_FOUND", status)


def ancestor(root: Path, older: str, newer: str) -> bool:
    return run(root, "git", "merge-base", "--is-ancestor", older, newer, check=False).returncode == 0


def need_ancestor(root: Path, older: str, newer: str, code: str) -> None:
    if not ancestor(root, older, newer):
        die(code)


def name_status(text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if not text.strip():
        return rows
    for raw in text.splitlines():
        parts = raw.split("\t")
        if len(parts) != 2:
            die("DIFF_RENAME_COPY_OR_MALFORMED")
        status, path = parts
        if status not in {"A", "M"}:
            die(f"DIFF_STATUS:{status}:{path}")
        if not path or path.startswith("/") or "\\" in path:
            die(f"DIFF_PATH:{path}")
        rows.append((status, path))
    return rows


def exact_path_rows(rows: list[tuple[str, str]], expected: tuple[str, ...] | list[str]) -> list[tuple[str, str]]:
    got = [path for _, path in rows]
    if len(got) != len(set(got)):
        die("DUPLICATE_CHANGED_PATH")
    if len(got) != len(expected):
        die(f"CHANGED_PATH_COUNT:{len(got)}")
    extra = sorted(set(got) - set(expected))
    missing = sorted(set(expected) - set(got))
    if extra:
        die("EXTRA_CHANGED_PATH:" + ",".join(extra))
    if missing:
        die("MISSING_CHANGED_PATH:" + ",".join(missing))
    return rows


def exact_paths(root: Path, base: str, candidate: str, expected: tuple[str, ...] | list[str] = PATHS) -> list[tuple[str, str]]:
    rows = name_status(gt(root, "diff", "--name-status", f"{base}..{candidate}", "--"))
    return exact_path_rows(rows, expected)


def blob_or_none(root: Path, commit: str, path: str) -> str | None:
    proc = run(root, "git", "rev-parse", f"{commit}:{path}", check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def blob(root: Path, commit: str, path: str) -> str:
    value = blob_or_none(root, commit, path)
    if value is None:
        die(f"PATH_MISSING:{commit}:{path}")
    return value


def bytes_at(root: Path, commit: str, path: str) -> bytes:
    proc = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode:
        die(f"PATH_READ_FAIL:{commit}:{path}")
    return proc.stdout


def text_at(root: Path, commit: str, path: str) -> str:
    try:
        return bytes_at(root, commit, path).decode("utf-8")
    except UnicodeDecodeError:
        die(f"NON_UTF8:{path}")


def commit_parents(root: Path, commit: str) -> list[str]:
    parts = gt(root, "rev-list", "--parents", "-n", "1", commit).split()
    return parts[1:]


def diff_paths(root: Path, older: str, newer: str) -> set[str]:
    text = gt(root, "diff", "--name-only", f"{older}..{newer}", "--")
    return {line for line in text.splitlines() if line}


def commit_touched_paths(root: Path, commit: str) -> set[str]:
    parents = commit_parents(root, commit)
    if not parents:
        text = gt(root, "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", commit)
        return {line for line in text.splitlines() if line}
    touched: set[str] = set()
    for parent in parents:
        touched |= diff_paths(root, parent, commit)
    return touched


def require_builder_history(root: Path, base: str, source: str, builder: str, owned: tuple[str, ...] | list[str]) -> list[dict[str, Any]]:
    commits = [x for x in gt(root, "rev-list", "--reverse", f"{base}..{source}").splitlines() if x]
    proof: list[dict[str, Any]] = []
    for commit in commits:
        if not ancestor(root, base, commit):
            die(f"{builder.upper()}_HISTORY_NOT_FROM_BASE:{commit}")
        touched = sorted(commit_touched_paths(root, commit))
        illegal = sorted(set(touched) - set(owned))
        if illegal:
            die(f"{builder.upper()}_HISTORY_OUT_OF_OWNERSHIP:{commit}:{','.join(illegal)}")
        proof.append({"commit": commit, "touched_paths": touched})
    return proof


def require_no_post_source_touch(root: Path, source: str, final: str, builder: str, owned: tuple[str, ...] | list[str]) -> list[str]:
    commits = [x for x in gt(root, "rev-list", f"{source}..{final}").splitlines() if x]
    inspected: list[str] = []
    owned_set = set(owned)
    for commit in commits:
        parents = commit_parents(root, commit)
        if len(parents) <= 1:
            touched = commit_touched_paths(root, commit) & owned_set
            if touched:
                die(f"{builder.upper()}_POST_SOURCE_HISTORY_TOUCH:{commit}:{','.join(sorted(touched))}")
            inspected.append(commit)
            continue
        for path in owned:
            current_blob = blob_or_none(root, commit, path)
            parent_blobs = {blob_or_none(root, parent, path) for parent in parents}
            if current_blob not in parent_blobs:
                if any(path in diff_paths(root, parent, commit) for parent in parents):
                    die(f"{builder.upper()}_POST_SOURCE_MERGE_RESOLUTION_TOUCH:{commit}:{path}")
        inspected.append(commit)
    return inspected


def provenance(
    root: Path,
    candidate: str,
    sources: dict[str, str],
    base: str = BASE,
    ownership: dict[str, tuple[str, ...]] = OWN,
) -> dict[str, Any]:
    proof: dict[str, Any] = {}
    for builder in ("b1", "b2", "b3"):
        source = sources.get(builder, "")
        need_commit(root, builder.upper() + "_COMMIT", source, "NOT_READY")
        if source == base:
            die(f"{builder.upper()}_EQUALS_BASE")
        need_ancestor(root, base, source, f"{builder.upper()}_NOT_FROM_BASE")
        need_ancestor(root, source, candidate, f"{builder.upper()}_NOT_ANCESTOR_CANDIDATE")
        history = require_builder_history(root, base, source, builder, ownership[builder])
        source_delta = name_status(gt(root, "diff", "--name-status", f"{base}..{source}", "--"))
        got = [path for _, path in source_delta]
        expected = set(ownership[builder])
        if set(got) - expected:
            die(f"{builder.upper()}_OUT_OF_OWNERSHIP")
        if expected - set(got):
            die(f"{builder.upper()}_MISSING_OWNED_PATH")
        later = require_no_post_source_touch(root, source, candidate, builder, ownership[builder])
        bindings: dict[str, str] = {}
        for path in ownership[builder]:
            if blob(root, source, path) != blob(root, candidate, path):
                die(f"{builder.upper()}_POST_SOURCE_TAMPER:{path}")
            bindings[path] = blob(root, candidate, path)
        proof[builder] = {
            "commit": source,
            "paths": got,
            "history": history,
            "post_source_commits_inspected": later,
            "candidate_blob_binding": bindings,
        }
    return proof


def matrix(root: Path = ROOT) -> dict[str, Any]:
    path = root / "runtime" / "fixtures" / "v08_adapter_attack_cases.json"
    if not path.exists():
        die("ATTACK_MATRIX_MISSING", "NOT_READY")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        die("ATTACK_MATRIX_MALFORMED")
    if (
        data.get("schema") != MATRIX_SCHEMA
        or data.get("version") != VERSION
        or data.get("attack_matrix_version") != MATRIX_VERSION
        or data.get("accepted_base_sha") != BASE
    ):
        die("ATTACK_MATRIX_BINDING")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        die("ATTACK_MATRIX_EMPTY")
    ids: list[str] = []
    for case in cases:
        if not isinstance(case, dict):
            die("ATTACK_MATRIX_CASE_NOT_OBJECT")
        if set(case) != {"id", "category", "owner", "owner_case", "expected_outcome"}:
            die("ATTACK_MATRIX_CASE_SCHEMA")
        if case["owner"] not in {"B1", "B2", "B3"}:
            die("ATTACK_MATRIX_OWNER")
        if not all(isinstance(case[k], str) and case[k] for k in case):
            die("ATTACK_MATRIX_CASE_VALUE")
        ids.append(case["id"])
    if len(ids) != len(set(ids)):
        die("ATTACK_MATRIX_IDS")
    categories = {case["category"] for case in cases}
    required = {
        "scope_git",
        "registry",
        "adapter_contract",
        "artifact",
        "worker_replacement",
        "provider_separation",
        "authority_isolation",
        "effect_isolation",
    }
    if categories != required:
        die("ATTACK_MATRIX_CATEGORIES")
    declared = data.get("attack_case_count")
    if isinstance(declared, bool) or not isinstance(declared, int) or declared != len(cases):
        die("ATTACK_MATRIX_COUNT_BINDING")
    return data


def parse_attack_records(stdout: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        if not line.startswith(ATTACK_RESULT_PREFIX):
            continue
        payload = line[len(ATTACK_RESULT_PREFIX) :]
        try:
            record = json.loads(payload)
        except json.JSONDecodeError:
            die("ATTACK_RESULT_MALFORMED_JSON")
        if not isinstance(record, dict):
            die("ATTACK_RESULT_NOT_OBJECT")
        records.append(record)
    return records


def validate_attack_records(matrix_data: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    expected_cases = matrix_data["cases"]
    expected_by_id = {case["id"]: case for case in expected_cases}
    observed_ids: list[str] = []
    normalized: dict[str, dict[str, Any]] = {}
    required_fields = {
        "attack_id",
        "owner",
        "owner_case",
        "expected_outcome",
        "observed_outcome",
        "executed",
        "result",
    }
    for record in records:
        if set(record) != required_fields:
            die("ATTACK_RESULT_SCHEMA")
        attack_id = record.get("attack_id")
        if not isinstance(attack_id, str):
            die("ATTACK_RESULT_ID_TYPE")
        observed_ids.append(attack_id)
        if attack_id in normalized:
            die(f"ATTACK_RESULT_DUPLICATE:{attack_id}")
        normalized[attack_id] = record
    expected_ids = set(expected_by_id)
    observed_set = set(observed_ids)
    missing = sorted(expected_ids - observed_set)
    extra = sorted(observed_set - expected_ids)
    if missing:
        die("ATTACK_RESULT_MISSING:" + ",".join(missing))
    if extra:
        die("ATTACK_RESULT_EXTRA:" + ",".join(extra))
    if len(observed_ids) != len(expected_cases):
        die(f"ATTACK_RESULT_COUNT:{len(observed_ids)}")
    for attack_id, case in expected_by_id.items():
        record = normalized[attack_id]
        for field, matrix_field in (
            ("owner", "owner"),
            ("owner_case", "owner_case"),
            ("expected_outcome", "expected_outcome"),
        ):
            if record[field] != case[matrix_field]:
                die(f"ATTACK_RESULT_MAPPING_MISMATCH:{attack_id}:{field}")
        if record["executed"] is not True:
            die(f"ATTACK_RESULT_NOT_EXECUTED:{attack_id}")
        if record["observed_outcome"] != record["expected_outcome"]:
            die(f"ATTACK_RESULT_OUTCOME_MISMATCH:{attack_id}")
        if record["result"] != "PASS":
            die(f"ATTACK_RESULT_NOT_PASS:{attack_id}")
    return normalized


def execute_attack_producer(root: Path, matrix_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    proc = run(root, PYTHON, "runtime/test_v08_adapter_evidence_offline.py", "--emit-attack-results", check=False)
    records = parse_attack_records(proc.stdout)
    if proc.returncode == 3:
        detail = proc.stderr.strip() or proc.stdout.strip() or "OWNER_ATTACK_EXECUTION_NOT_READY"
        die("ATTACK_EXECUTION_NOT_READY:" + detail[-500:], "NOT_READY")
    if proc.returncode != 0:
        die(f"ATTACK_PRODUCER_FAILED:{proc.returncode}:{proc.stderr[-500:]}")
    return validate_attack_records(matrix_data, records)


def _all_names(tree: ast.AST) -> set[str]:
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            values.add(node.id)
        elif isinstance(node, ast.arg):
            values.add(node.arg)
    return values


def _identity_aliases(tree: ast.AST) -> set[str]:
    aliases = {name for name in _all_names(tree) if name.endswith("provider_id") or name.endswith("worker_id")}
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                if not isinstance(value, ast.Name) or value.id not in aliases:
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name) and target.id not in aliases:
                        aliases.add(target.id)
                        changed = True
    return aliases


def _strings(node: ast.AST) -> list[str]:
    return [x.value for x in ast.walk(node) if isinstance(x, ast.Constant) and isinstance(x.value, str)]


def _is_identity_literal(value: str, identities: set[str]) -> bool:
    lowered = value.lower()
    return lowered in {x.lower() for x in identities} or any(token in lowered for token in DEFAULT_IDENTITIES)


def identity_findings(src: str, path: str = "<memory>", identities: set[str] | None = None) -> list[str]:
    identities = set(identities or ()) | DEFAULT_IDENTITIES
    try:
        tree = ast.parse(src, path)
    except SyntaxError:
        die(f"CORE_SYNTAX:{path}")
    aliases = _identity_aliases(tree)
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.IfExp, ast.While, ast.Match)):
            subject = node.test if hasattr(node, "test") else node.subject
            names = {x.id for x in ast.walk(subject) if isinstance(x, ast.Name)}
            strings = _strings(subject)
            if names & aliases and any(_is_identity_literal(value, identities) for value in strings):
                findings.append(f"{path}:{getattr(node, 'lineno', 0)}:identity-alias-branch")
            if any(_is_identity_literal(value, identities) for value in strings):
                findings.append(f"{path}:{getattr(node, 'lineno', 0)}:identity-literal-branch")
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str) and _is_identity_literal(key.value, identities):
                    findings.append(f"{path}:{getattr(node, 'lineno', 0)}:identity-literal-mapping")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"get", "pop", "setdefault"}:
            names = {x.id for x in ast.walk(node) if isinstance(x, ast.Name)}
            if names & aliases:
                base = node.func.value
                if isinstance(base, ast.Dict):
                    for key in base.keys:
                        if isinstance(key, ast.Constant) and isinstance(key.value, str) and _is_identity_literal(key.value, identities):
                            findings.append(f"{path}:{getattr(node, 'lineno', 0)}:identity-dict-dispatch")
    return sorted(set(findings))


def isolation_findings(src: str, path: str = "<memory>") -> tuple[list[str], list[str]]:
    try:
        tree = ast.parse(src, path)
    except SyntaxError:
        die(f"ISOLATION_SYNTAX:{path}")
    authority: list[str] = []
    effect: list[str] = []
    for node in ast.walk(tree):
        symbol: str | None = None
        if isinstance(node, ast.Name):
            symbol = node.id.lower()
        elif isinstance(node, ast.Attribute):
            symbol = node.attr.lower()
        elif isinstance(node, ast.alias):
            symbol = node.name.rsplit(".", 1)[-1].lower()
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            symbol = node.value.lower()
        if symbol in AUTH:
            authority.append(f"{path}:{getattr(node, 'lineno', 0)}:{symbol}")
        if symbol in EFFECT:
            effect.append(f"{path}:{getattr(node, 'lineno', 0)}:{symbol}")
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and str(key.value).lower() in {"verdict", "reviewer_verdict"}
                    and isinstance(value, ast.Constant)
                    and value.value == "PASS"
                ):
                    authority.append(f"{path}:{node.lineno}:reviewer-pass")
    return sorted(set(authority)), sorted(set(effect))


def registry_identities(root: Path, candidate: str) -> set[str]:
    try:
        data = json.loads(text_at(root, candidate, REGISTRY))
    except Exception:
        return set(DEFAULT_IDENTITIES)
    identities = set(DEFAULT_IDENTITIES)
    for section, key in (("providers", "provider_id"), ("workers", "worker_id"), ("reviewers", "reviewer_id")):
        values = data.get(section)
        if isinstance(values, list):
            for item in values:
                if isinstance(item, dict) and isinstance(item.get(key), str):
                    identities.add(item[key])
    return identities


def static_gates(root: Path, candidate: str) -> dict[str, Any]:
    identities = registry_identities(root, candidate)
    identity: list[str] = []
    for path in CORE:
        identity.extend(identity_findings(text_at(root, candidate, path), path, identities))
    if identity:
        die("IDENTITY_CORE_BRANCH:" + "|".join(identity[:8]))
    authority: list[str] = []
    effect: list[str] = []
    for path in ISOLATION:
        a, e = isolation_findings(text_at(root, candidate, path), path)
        authority.extend(a)
        effect.extend(e)
    if authority:
        die("AUTHORITY_ISOLATION:" + "|".join(authority[:8]))
    if effect:
        die("EFFECT_ISOLATION:" + "|".join(effect[:8]))
    leaks: list[str] = []
    transport_surface = (REGISTRY, "runtime/v08_adapter.py", "runtime/fixtures/v08_fixture_worker.py")
    for path in transport_surface:
        lowered = text_at(root, candidate, path).lower()
        leaks.extend(f"{path}:{token}" for token in TRANSPORT if token in lowered)
    if leaks:
        die("TRANSPORT_LEAK:" + "|".join(leaks[:8]))
    return {
        "identity": {"status": "PASS", "paths": list(CORE), "registry_identity_count": len(identities)},
        "authority": {"status": "PASS", "paths": list(ISOLATION)},
        "effect": {"status": "PASS", "paths": list(ISOLATION)},
        "transport": {"status": "PASS", "paths": list(transport_surface)},
    }


def checked(root: Path, *cmd: str) -> dict[str, Any]:
    proc = run(root, *cmd, check=False)
    result = {
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "stdout_tail": proc.stdout[-1000:],
        "stderr_tail": proc.stderr[-1000:],
    }
    if proc.returncode:
        die(f"TEST_FAILED:{result['command']}:{proc.returncode}")
    return result


def not_ready(args: argparse.Namespace, missing: list[str]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    result = {key: None for key in REQUIRED_FIELDS}
    result.update(
        schema=SCHEMA,
        version=VERSION,
        status="NOT_READY",
        accepted_base_sha=BASE,
        candidate_sha=args.candidate,
        b1_commit=args.b1_commit,
        b2_commit=args.b2_commit,
        b3_commit=args.b3_commit,
        changed_files=[],
        changed_file_hashes={},
        test_command=[],
        exit_code=3,
        test_result="NOT_READY",
        attack_case_id=[],
        attack_result={},
        worker_replacement_proof={"status": "NOT_READY"},
        provider_separation_proof={"status": "NOT_READY"},
        artifact_integrity_proof={"status": "NOT_READY"},
        source_binding_proof={"status": "NOT_READY"},
        authority_isolation_proof={"status": "NOT_READY"},
        effect_isolation_proof={"status": "NOT_READY"},
        backward_regression_result={"status": "NOT_READY"},
        generated_at=now,
        missing_required=missing,
    )
    return result


def build(root: Path, candidate: str, b1: str, b2: str, b3: str) -> dict[str, Any]:
    need_commit(root, "ACCEPTED_BASE", BASE)
    need_commit(root, "CANDIDATE", candidate)
    need_ancestor(root, BASE, candidate, "CANDIDATE_NOT_FROM_BASE")
    if gt(root, "rev-parse", "HEAD") != candidate:
        die("HEAD_MISMATCH")
    if gt(root, "status", "--porcelain"):
        die("WORKTREE_DIRTY")
    rows = exact_paths(root, BASE, candidate)
    source_proof = provenance(root, candidate, {"b1": b1, "b2": b2, "b3": b3})
    matrix_data = matrix(root)
    attack_records = execute_attack_producer(root, matrix_data)
    static = static_gates(root, candidate)

    commands = [
        (PYTHON, "runtime/test_v08_adapter_core_offline.py"),
        (PYTHON, "runtime/test_v08_adapter_registry_offline.py"),
        (PYTHON, "runtime/test_v08_adapter_evidence_offline.py"),
        ("git", "diff", "--check", f"{BASE}..{candidate}"),
        (PYTHON, "-m", "compileall", "runtime", "src", "tests"),
        (PYTHON, "-m", "unittest", "discover", "-s", "runtime", "-p", "test_*_offline.py"),
        (PYTHON, "tests/test_core.py"),
    ]
    results = [checked(root, *cmd) for cmd in commands]
    ids = [case["id"] for case in matrix_data["cases"]]
    hashes = {path: hashlib.sha256(bytes_at(root, candidate, path)).hexdigest() for path in PATHS}
    by_prefix = lambda prefix: [attack_id for attack_id in ids if attack_id.startswith(prefix)]
    attack_result = {attack_id: attack_records[attack_id]["result"] for attack_id in ids}
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "status": "PASS",
        "accepted_base_sha": BASE,
        "candidate_sha": candidate,
        "b1_commit": b1,
        "b2_commit": b2,
        "b3_commit": b3,
        "changed_files": [{"status": status, "path": path} for status, path in rows],
        "changed_file_hashes": hashes,
        "test_command": [item["command"] for item in results],
        "exit_code": 0,
        "test_result": "PASS",
        "attack_case_id": ids,
        "attack_result": attack_result,
        "attack_execution_records": [attack_records[attack_id] for attack_id in ids],
        "worker_replacement_proof": {"status": "PASS", "attack_case_ids": by_prefix("E")},
        "provider_separation_proof": {"status": "PASS", "attack_case_ids": by_prefix("F"), "static": static["identity"]},
        "artifact_integrity_proof": {"status": "PASS", "attack_case_ids": by_prefix("D")},
        "source_binding_proof": {"status": "PASS", "builders": source_proof},
        "authority_isolation_proof": {"status": "PASS", "attack_case_ids": by_prefix("G"), "static": static["authority"]},
        "effect_isolation_proof": {"status": "PASS", "attack_case_ids": by_prefix("H"), "static": static["effect"]},
        "backward_regression_result": {"status": "PASS", "commands": results[3:]},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--candidate")
    p.add_argument("--b1-commit")
    p.add_argument("--b2-commit")
    p.add_argument("--b3-commit")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    missing = [name for name in ("candidate", "b1_commit", "b2_commit", "b3_commit") if not getattr(args, name)]
    if missing:
        result = not_ready(args, missing)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        print("V08_EVIDENCE_STATUS=NOT_READY")
        return 3
    try:
        result = build(ROOT, args.candidate, args.b1_commit, args.b2_commit, args.b3_commit)
    except EvidenceError as exc:
        print(json.dumps({"schema": SCHEMA, "version": VERSION, "status": exc.status, "error": exc.code}, sort_keys=True))
        print(f"V08_EVIDENCE_STATUS={exc.status}")
        return 3 if exc.status == "NOT_READY" else 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    print(f"{SUCCESS} candidate={args.candidate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
