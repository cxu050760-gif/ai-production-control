#!/usr/bin/env python3
"""registry-launch.py — Capability Registry consumer & launch advisor (§63).

Purpose:
    1. Read config/capability-registry.json (machine-readable, 宪法 §63).
    2. Probe each registered capability's health_check (port / file / command).
    3. For capabilities that are status=official and currently DOWN, print the
       ready-to-run launch command — WITHOUT executing it (no dangerous
       auto-start; the operator decides).
    4. Verify the "registry is consumed by the runtime" acceptance point by
       cross-checking that config/production.json's brains/workers/browser
       declarations all have matching registry entries.

Design note — why Python instead of .cmd:
    * The canonical runtime interpreter is Python 3.12 (config/production.json
      workers.local_python; runtime/run.cmd APC_PY).
    * JSON parsing, UTF-8 Chinese paths, and structured reporting are native.
    * A .cmd implementation would need fragile escaping for JSON quotes and
      CJK paths; Python keeps probes safe and auditable.

Discipline:
    * Read-only by default. Command health probes are ONLY executed with
      --probe-commands and ONLY for health_check entries whose
      read_only=true marker is set. Launch suggestions are printed, never run.
    * Does not modify config/production.json or any TCB file.

Usage:
    python docs/ops/registry-launch.py [--probe-commands] [--json] [--strict]
      --probe-commands  additionally execute read_only command health checks
      --json            emit a machine-readable JSON report
      --strict          exit non-zero if any official capability is DOWN
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REQUIRED_SECTIONS = [
    "brains", "workers", "correctors", "reviewers", "browsers", "tools",
    "providers", "login_state", "costs", "quotas", "reliabilities",
    "capabilities", "lifecycle_status", "permissions", "adapters",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_json(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def probe_port(host: str, port: int, timeout_sec: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except OSError:
        return False


def probe_file(path_str: str) -> bool:
    return Path(path_str).exists()


def probe_command(command: List[str], expect: Optional[str], timeout_sec: float) -> Tuple[bool, str]:
    """Run a read_only command health check and compare output to expect.

    On Windows, script-type executables (bash shebang scripts such as
    chatgpt_bridge, and .cmd wrappers) cannot be spawned directly by
    CreateProcess.  We retry via the shell when the direct spawn raises
    WinError 193 (not a valid Win32 application).
    """
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            shell=False,
        )
    except OSError as exc:
        if getattr(exc, "winerror", None) == 193:
            # Direct spawn failed because the file is a script, not an EXE.
            shell_cmd = " ".join(command)
            try:
                proc = subprocess.run(
                    shell_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec,
                    shell=True,
                )
            except (OSError, subprocess.TimeoutExpired) as shell_exc:
                return False, f"error={shell_exc}"
        else:
            return False, f"error={exc}"
    except subprocess.TimeoutExpired as exc:
        return False, f"timeout={exc}"
    output = (proc.stdout or "") + (proc.stderr or "")
    if expect:
        return expect in output, output.strip().replace("\n", " | ")[:200]
    return proc.returncode == 0, output.strip().replace("\n", " | ")[:200]


def probe_health_check(hc: Dict[str, Any], allow_commands: bool) -> Tuple[str, str]:
    """Return (UP|DOWN|SKIP, detail)."""
    if not isinstance(hc, dict):
        return "SKIP", "no health_check"
    kind = hc.get("kind")
    if kind == "port":
        ok = probe_port(str(hc.get("host", "127.0.0.1")), int(hc["port"]), float(hc.get("timeout_sec", 2)))
        return ("UP" if ok else "DOWN"), f"port {hc.get('host', '127.0.0.1')}:{hc['port']}"
    if kind == "file":
        ok = probe_file(str(hc["path"]))
        return ("UP" if ok else "DOWN"), f"file {hc['path']}"
    if kind == "command":
        if not allow_commands:
            return "SKIP", f"command probe disabled (use --probe-commands): {hc.get('command', [])}"
        if not hc.get("read_only"):
            return "SKIP", "command health_check not marked read_only; refusing to run"
        ok, detail = probe_command(list(hc.get("command", [])), hc.get("expect"), float(hc.get("timeout_sec", 30)))
        return ("UP" if ok else "DOWN"), detail
    if kind == "note":
        return "SKIP", f"note-only health: {hc.get('note', '')}"
    return "SKIP", f"unknown kind {kind}"


def format_command(cmd: Optional[List[str]], cwd: Optional[str]) -> str:
    if not cmd:
        return "(none)"
    joined = " ".join(cmd)
    if cwd:
        joined = f"cd {cwd} && {joined}"
    return joined


def resolve_short_id(value: str, entry_ids: set) -> bool:
    """production.json uses short ids (e.g. 'chatgpt-web'); registry ids are
    namespaced by role (e.g. 'brain-chatgpt-web').  Return True if the short id
    resolves to any registry entry id."""
    candidates = {
        value,
        f"brain-{value}",
        f"worker-{value}",
        f"provider-{value}",
        f"browser-{value}",
        f"tool-{value}",
        f"c-{value}",
        f"r-{value}",
    }
    if any(c in entry_ids for c in candidates):
        return True
    # fall back: the value appears as a suffix of some entry id
    return any(value in eid for eid in entry_ids)


def cross_check_production(registry: Dict[str, Any], production: Dict[str, Any]) -> List[str]:
    """Verify the registry is consumable by the runtime (acceptance point)."""
    issues: List[str] = []
    entry_ids = set()
    for section in REQUIRED_SECTIONS:
        for e in registry.get("sections", {}).get(section, []):
            if isinstance(e, dict) and e.get("id"):
                entry_ids.add(e["id"])

    brains = production.get("brains", {})
    primary = brains.get("default_primary")
    if primary and not resolve_short_id(primary, entry_ids):
        issues.append(f"production.json brains.default_primary '{primary}' has no registry entry")
    for fb in brains.get("fallbacks", []):
        if not resolve_short_id(fb, entry_ids):
            issues.append(f"production.json brains.fallbacks '{fb}' has no registry entry")

    for key, path in production.get("workers", {}).items():
        # registry ids use kebab style; verify presence of a worker whose source mentions the key
        match = any(
            key in str(e.get("source", "")) or key in str(e.get("entry", {}))
            for e in registry.get("sections", {}).get("workers", [])
            if isinstance(e, dict)
        )
        if not match:
            issues.append(f"production.json workers.{key} has no matching registry worker entry")

    browser = production.get("browser", {})
    browser_registry = {e.get("id"): e for e in registry.get("sections", {}).get("browsers", []) if isinstance(e, dict)}
    if browser.get("primary") != "playwright-cdp" or "browser-playwright-cdp" not in browser_registry:
        issues.append("production.json browser.primary not covered by registry (browser-playwright-cdp)")
    if browser.get("fallback") != "bsk" or "browser-bsk" not in browser_registry:
        issues.append("production.json browser.fallback not covered by registry (browser-bsk)")
    return issues


def build_report(registry: Dict[str, Any], allow_commands: bool, strict: bool) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "schema": "REGISTRY_LAUNCH_REPORT",
        "schema_version": 1,
        "registry_schema": registry.get("schema"),
        "registry_generation": registry.get("registry_generation"),
        "probe_commands": allow_commands,
        "results": [],
        "launch_suggestions": [],
        "summary": {"official": 0, "experimental": 0, "deprecated": 0, "up": 0, "down": 0, "skip": 0},
        "production_cross_check": {"issues": [], "ok": False},
    }

    for section in REQUIRED_SECTIONS:
        for e in registry.get("sections", {}).get(section, []):
            if not isinstance(e, dict) or not e.get("id"):
                continue
            status = e.get("status", "unknown")
            state, detail = probe_health_check(e.get("health_check"), allow_commands)
            report["summary"][status] = report["summary"].get(status, 0) + 1
            report["summary"][state.lower()] = report["summary"].get(state.lower(), 0) + 1
            report["results"].append({
                "id": e["id"],
                "section": section,
                "name": e.get("name"),
                "status": status,
                "state": state,
                "detail": detail,
            })
            if status == "official" and state == "DOWN":
                launch = e.get("launch")
                if launch and isinstance(launch, dict):
                    report["launch_suggestions"].append({
                        "id": e["id"],
                        "section": section,
                        "name": e.get("name"),
                        "reason": detail,
                        "command": format_command(launch.get("command"), launch.get("cwd")),
                        "note": launch.get("note", ""),
                    })
                else:
                    report["launch_suggestions"].append({
                        "id": e["id"],
                        "section": section,
                        "name": e.get("name"),
                        "reason": detail,
                        "command": "(no launch suggestion registered)",
                        "note": "",
                    })

    # Production cross-check (registry consumed by runtime)
    prod_path = repo_root() / "config" / "production.json"
    if prod_path.exists():
        try:
            production = load_json(prod_path)
            issues = cross_check_production(registry, production)
            report["production_cross_check"] = {"issues": issues, "ok": len(issues) == 0}
        except Exception as exc:  # noqa: BLE001 - report, don't crash
            report["production_cross_check"] = {"issues": [f"could not read production.json: {exc}"], "ok": False}
    else:
        report["production_cross_check"] = {"issues": ["config/production.json not found"], "ok": False}

    report["summary"]["official_down"] = sum(
        1 for r in report["results"] if r["status"] == "official" and r["state"] == "DOWN"
    )
    return report


def print_human(report: Dict[str, Any]) -> None:
    print("=" * 78)
    print("CAPABILITY REGISTRY — launch advisor / health survey (§63)")
    print(f"registry: {report['registry_schema']} gen={report['registry_generation']} | probe_commands={report['probe_commands']}")
    print("=" * 78)
    print(f"\nsummary: {report['summary']}")
    print("\n--- per-entry health ---")
    for r in report["results"]:
        print(f"  [{r['state']:<4}] {r['section']:<14} {r['id']:<32} ({r['status']}) {r['detail']}")
    print("\n--- launch suggestions (official & DOWN) — PRINTED ONLY, NOT EXECUTED ---")
    if not report["launch_suggestions"]:
        print("  (none)")
    for s in report["launch_suggestions"]:
        print(f"  {s['id']}: {s['name']}")
        print(f"    reason : {s['reason']}")
        print(f"    command: {s['command']}")
        if s["note"]:
            print(f"    note   : {s['note']}")
    print("\n--- production.json cross-check (registry consumed by runtime) ---")
    pc = report["production_cross_check"]
    print(f"  ok: {pc['ok']}")
    for issue in pc["issues"]:
        print(f"  ISSUE: {issue}")
    print("=" * 78)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Capability Registry consumer & launch advisor (§63)")
    parser.add_argument("--probe-commands", action="store_true", help="execute read_only command health probes")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON report")
    parser.add_argument("--strict", action="store_true", help="exit non-zero if any official capability is DOWN")
    args = parser.parse_args(argv)

    registry_path = repo_root() / "config" / "capability-registry.json"
    try:
        registry = load_json(registry_path)
    except (json.JSONDecodeError, UnicodeDecodeError, FileNotFoundError) as exc:
        print(f"FATAL: cannot read registry {registry_path}: {exc}", file=sys.stderr)
        return 2

    report = build_report(registry, allow_commands=args.probe_commands, strict=args.strict)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)

    if not report["production_cross_check"]["ok"]:
        # The acceptance point "registry is consumed by the runtime" failed.
        return 3
    if args.strict and report["summary"].get("official_down", 0) > 0:
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
