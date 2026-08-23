from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = "runtime/run.cmd"
ACTIVE_ENTRY_DOCS = [
    ROOT / "README.md",
    ROOT / "STATUS.md",
    ROOT / "runtime" / "WEAK_WORKER_START_HERE.md",
    ROOT / "runtime" / "WEAK_WORKER_BOOTSTRAP.md",
]
LEGACY_FILES = [ROOT / "ai-control.cmd", ROOT / "scripts" / "ai_control.py"]
HISTORICAL_DOCS = [
    ROOT / "docs" / "AI_PRODUCTION_CONTROL_HANDOFF.md",
    ROOT / "docs" / "NEW_SESSION_KICKOFF.md",
    ROOT / "docs" / "SUCCESSOR_HANDOFF_REPORT.md",
]
TEXT_SUFFIXES = {".md", ".json", ".cmd", ".py", ".toml"}
POSITIVE_ENTRY_RE = re.compile(
    r"target\s+(?:official\s+user|production)\s+entry|"
    r"official\s+runtime\s+entry|single\s+production\s+entry|"
    r"正式[^\n]{0,20}入口|唯一[^\n]{0,20}入口",
    re.I,
)
NEGATION_TOKENS = ("legacy", "compatibility", "not", "不是", "非正式", "deprecated", "historical")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


def norm(text: str) -> str:
    return text.replace("\\", "/").lower()


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def is_historical(text: str) -> bool:
    head = text[:800].upper()
    return "DEPRECATED" in head and "HISTORICAL" in head


def main() -> int:
    errors: list[str] = []

    run_cmd = read(ROOT / OFFICIAL)
    if "single production entry" not in run_cmd.lower():
        fail(errors, "runtime/run.cmd does not declare single production entry")
    if run_cmd.lower().count("runtime\\runtime.py") != 1:
        fail(errors, "runtime/run.cmd must transfer exactly once to runtime/runtime.py")

    # Current authority/Worker entry docs must all resolve to runtime/run.cmd.
    for path in ACTIVE_ENTRY_DOCS:
        text = read(path)
        if OFFICIAL not in norm(text):
            fail(errors, f"active entry document does not resolve to {OFFICIAL}: {path.relative_to(ROOT)}")

    bootstrap = json.loads(read(ROOT / "runtime" / "bootstrap.json"))
    if not norm(str(bootstrap.get("runtime_entry", ""))).endswith(OFFICIAL):
        fail(errors, "runtime/bootstrap.json runtime_entry does not resolve to runtime/run.cmd")

    # Full-repository declaration scan: an active document may mention a legacy
    # .cmd, but it may not positively present that file as an official/target entry.
    checker_path = Path(__file__).resolve()
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        # The checker source necessarily contains the declaration patterns as
        # rule literals; it is executable policy, not an entry declaration.
        if path.resolve() == checker_path:
            continue
        text = read(path)
        historical = is_historical(text)
        for line_no, line in enumerate(text.splitlines(), 1):
            line_n = norm(line)
            if not POSITIVE_ENTRY_RE.search(line):
                continue
            if "target production entry" in line_n or "target official user entry" in line_n:
                if OFFICIAL not in line_n and not historical:
                    fail(errors, f"active target-entry declaration does not resolve to {OFFICIAL}: {path.relative_to(ROOT)}:{line_no}")
            if ".cmd" in line_n and OFFICIAL not in line_n and not historical:
                if not any(token in line_n for token in NEGATION_TOKENS):
                    fail(errors, f"active official-entry declaration points to another .cmd: {path.relative_to(ROOT)}:{line_no}: {line.strip()}")

    for path in LEGACY_FILES:
        text = read(path)
        upper = text[:500].upper()
        if "LEGACY" not in upper or "COMPATIBILITY" not in upper:
            fail(errors, f"legacy Controller surface lacks COMPATIBILITY / LEGACY marker: {path.relative_to(ROOT)}")
        if "OFFICIAL RUNTIME ENTRY" not in upper or "NOT" not in upper:
            fail(errors, f"legacy Controller surface lacks explicit not-official marker: {path.relative_to(ROOT)}")

    for path in HISTORICAL_DOCS:
        text = read(path)
        if not is_historical(text):
            fail(errors, f"historical handoff/kickoff is not explicitly deprecated: {path.relative_to(ROOT)}")
        if OFFICIAL not in norm(text[:1200]):
            fail(errors, f"deprecated handoff/kickoff does not redirect to {OFFICIAL}: {path.relative_to(ROOT)}")

    # Active Worker contracts may name internals only as prohibitions; they may
    # not contain direct invocation forms for Bridge/daemon/session/click tooling.
    worker_docs = [ROOT / "runtime" / "WEAK_WORKER_START_HERE.md", ROOT / "runtime" / "WEAK_WORKER_BOOTSTRAP.md"]
    dangerous_direct_invocations = [
        r"\bbsk\.exe\s+(?:daemon|browsers|eval|click)",
        r"\bdaemon\s+start\b",
        r"\byz_(?:acquire|send|grab|wait)_",
        r"\bclick\s+#[a-zA-Z0-9_-]+",
    ]
    for path in worker_docs:
        text = read(path)
        for pattern in dangerous_direct_invocations:
            if re.search(pattern, text, re.I):
                fail(errors, f"Worker document contains direct Bridge/internal operation: {path.relative_to(ROOT)} pattern={pattern}")

    # No second .cmd is allowed to forward into the Runtime implementation.
    runtime_py_forwarders = []
    for path in ROOT.rglob("*.cmd"):
        if "runtime\\runtime.py" in read(path).lower():
            runtime_py_forwarders.append(path.relative_to(ROOT).as_posix())
    if runtime_py_forwarders != [OFFICIAL]:
        fail(errors, f"runtime/runtime.py forwarders must be exactly [{OFFICIAL}], got {runtime_py_forwarders}")

    if errors:
        print("ENTRY_CONSISTENCY_CHECK=FAIL")
        for error in errors:
            print(f"ERROR={error}")
        return 1

    print("ENTRY_CONSISTENCY_CHECK=PASS")
    print(f"OFFICIAL_RUNTIME_ENTRY={OFFICIAL}")
    print("LEGACY_CONTROLLER=COMPATIBILITY")
    print("WORKER_BRIDGE_INTERNALS=DIRECT_USE_FORBIDDEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
