#!/usr/bin/env python3
"""registry-validate.py — Capability Registry schema self-check (宪法 §63).

Purpose:
    Machine-verifiable validation of config/capability-registry.json.
    Ensures the registry is parseable, complete (all 15 §63 sections),
    and internally consistent (unique ids, resolvable references,
    well-formed health_check / cost / quota / reliability / permissions).

Usage:
    python docs/ops/registry-validate.py [--registry PATH] [--verbose]

Exit codes:
    0  = PASS (registry is machine-readable and schema-consistent)
    1  = FAIL (one or more schema/consistency errors)
    2  = USAGE error (registry file missing / not parseable)

Discipline:
    Read-only. Does not modify the registry, production.json, or any TCB file.
    Does not probe live systems (use registry-launch.py for health probes).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Constitution §63 enumerates exactly these 15 capability classes.
REQUIRED_SECTIONS: List[str] = [
    "brains",
    "workers",
    "correctors",
    "reviewers",
    "browsers",
    "tools",
    "providers",
    "login_state",
    "costs",
    "quotas",
    "reliabilities",
    "capabilities",
    "lifecycle_status",
    "permissions",
    "adapters",
]

STATUS_ENUM = {"official", "experimental", "deprecated"}
HEALTH_KINDS = {"port", "file", "command", "note"}

# Sections whose entries are full capabilities: id/name/type/status all required.
CAPABILITY_SECTIONS = {
    "brains", "workers", "correctors", "reviewers", "browsers",
    "tools", "providers", "login_state",
}
# Sections whose entries are metadata with section-specific shapes.
METADATA_SECTIONS = {
    "costs", "quotas", "reliabilities", "capabilities",
    "lifecycle_status", "permissions", "adapters",
}


class RegistryValidator:
    """Validates capability-registry.json against the §63 schema."""

    def __init__(self, registry_path: Path, verbose: bool = False) -> None:
        self.registry_path = registry_path
        self.verbose = verbose
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.registry: Dict[str, Any] = {}

    def log(self, message: str) -> None:
        if self.verbose:
            print(f"[validate] {message}")

    def error(self, message: str) -> None:
        self.errors.append(message)
        self.log(f"ERROR: {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        self.log(f"WARN: {message}")

    def load(self) -> bool:
        if not self.registry_path.exists():
            self.error(f"registry file not found: {self.registry_path}")
            return False
        try:
            with self.registry_path.open(encoding="utf-8") as fh:
                self.registry = json.load(fh)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.error(f"registry is not valid JSON: {exc}")
            return False
        if not isinstance(self.registry, dict):
            self.error("registry root must be a JSON object")
            return False
        self.log(f"loaded {self.registry_path} ({len(json.dumps(self.registry))} bytes)")
        return True

    # ------------------------------------------------------------------
    # Section helpers
    # ------------------------------------------------------------------
    def section_entries(self, name: str) -> List[Dict[str, Any]]:
        section = self.registry.get("sections", {}).get(name, [])
        if not isinstance(section, list):
            return []
        return [e for e in section if isinstance(e, dict)]

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------
    def check_schema_version(self) -> None:
        if self.registry.get("schema") != "CAPABILITY_REGISTRY":
            self.error("registry.schema must be 'CAPABILITY_REGISTRY'")
        if self.registry.get("schema_version") != 1:
            self.error("registry.schema_version must be 1")

    def check_required_sections(self) -> None:
        sections = self.registry.get("sections", {})
        for section in REQUIRED_SECTIONS:
            if section not in sections:
                self.error(f"missing §63 section: sections.{section}")

    def check_entry_required_fields(self, section: str, entry: Dict[str, Any]) -> None:
        # Full capability entries require id/name/type/status.
        if section in CAPABILITY_SECTIONS:
            for field in ("id", "name", "type", "status"):
                if field not in entry or entry[field] in (None, ""):
                    self.error(f"{section} entry missing field '{field}': {json.dumps(entry, ensure_ascii=False)[:120]}")
            status = entry.get("status")
            if status not in STATUS_ENUM:
                self.error(f"{section}/{entry.get('id', '?')} invalid status '{status}' (must be one of {sorted(STATUS_ENUM)})")
            return
        # Metadata entries require id; the rest is section-specific.
        if "id" not in entry or entry["id"] in (None, ""):
            self.error(f"{section} metadata entry missing field 'id': {json.dumps(entry, ensure_ascii=False)[:120]}")
        if section in ("costs", "quotas", "reliabilities", "capabilities", "adapters", "permissions"):
            if "name" not in entry and section != "costs" and section != "quotas" and section != "reliabilities":
                self.error(f"{section}/{entry.get('id', '?')} metadata entry missing field 'name'")
        status = entry.get("status")
        if status is not None and status not in STATUS_ENUM:
            self.error(f"{section}/{entry.get('id', '?')} invalid status '{status}' (must be one of {sorted(STATUS_ENUM)})")

    def check_id_uniqueness(self) -> None:
        seen: Dict[str, str] = {}
        for section in REQUIRED_SECTIONS:
            for entry in self.section_entries(section):
                entry_id = entry.get("id")
                if not entry_id:
                    continue
                if entry_id in seen:
                    self.error(f"duplicate id '{entry_id}' in sections.{section} (also in sections.{seen[entry_id]})")
                else:
                    seen[entry_id] = section

    def check_health_check(self, section: str, entry: Dict[str, Any]) -> None:
        hc = entry.get("health_check")
        if hc is None:
            self.warn(f"{section}/{entry.get('id', '?')} has no health_check (acceptable for pure metadata)")
            return
        if not isinstance(hc, dict):
            self.error(f"{section}/{entry.get('id', '?')} health_check must be an object")
            return
        kind = hc.get("kind")
        if kind not in HEALTH_KINDS:
            self.error(f"{section}/{entry.get('id', '?')} health_check.kind '{kind}' invalid (must be one of {sorted(HEALTH_KINDS)})")
            return
        if kind == "port":
            port = hc.get("port")
            if not isinstance(port, int) or not (0 < port < 65536):
                self.error(f"{section}/{entry.get('id', '?')} health_check.port invalid: {port!r}")
        elif kind == "file":
            path = hc.get("path")
            if not isinstance(path, str) or not path.strip():
                self.error(f"{section}/{entry.get('id', '?')} health_check.path missing")
        elif kind == "command":
            cmd = hc.get("command")
            if not isinstance(cmd, list) or not cmd or not all(isinstance(c, str) for c in cmd):
                self.error(f"{section}/{entry.get('id', '?')} health_check.command must be a non-empty list of strings")
            timeout = hc.get("timeout_sec")
            if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
                self.error(f"{section}/{entry.get('id', '?')} health_check.timeout_sec invalid: {timeout!r}")

    def check_cost_quota_reliability(self, section: str, entry: Dict[str, Any]) -> None:
        for field in ("cost", "quota", "reliability"):
            value = entry.get(field)
            if value is None:
                continue
            if not isinstance(value, dict):
                self.error(f"{section}/{entry.get('id', '?')} {field} must be an object or null")
                continue
            if field == "cost":
                note = value.get("note", "")
                if value.get("cost_per_call") is None and value.get("cost_model") is None and "待 D2 校准" not in note:
                    self.warn(f"{section}/{entry.get('id', '?')} cost is null but note does not say '待 D2 校准'")
            if field == "reliability":
                level = value.get("level")
                if level is None or level == "":
                    self.warn(f"{section}/{entry.get('id', '?')} reliability.level empty (should be 待实测 when unmeasured)")

    def check_permissions(self, section: str, entry: Dict[str, Any]) -> None:
        perm = entry.get("permissions")
        if perm is None:
            self.warn(f"{section}/{entry.get('id', '?')} has no permissions (defaults to policy perm-default: deny external)")
            return
        if not isinstance(perm, dict):
            self.error(f"{section}/{entry.get('id', '?')} permissions must be an object or null")
        else:
            effect = perm.get("external_effect")
            if effect is not None and effect != "DENY":
                self.warn(f"{section}/{entry.get('id', '?')} external_effect='{effect}' (default policy is DENY)")

    def check_adapter_refs(self) -> None:
        adapter_ids = {e.get("id") for e in self.section_entries("adapters") if e.get("id")}
        for section in ("brains", "workers", "correctors", "reviewers", "browsers", "tools", "providers"):
            for entry in self.section_entries(section):
                adapter = entry.get("adapter")
                if adapter and adapter not in adapter_ids:
                    self.error(f"{section}/{entry.get('id', '?')} references unknown adapter '{adapter}'")

    def check_capability_refs(self) -> None:
        capability_ids = {e.get("id") for e in self.section_entries("capabilities") if e.get("id")}
        entry_ids = set()
        for section in REQUIRED_SECTIONS:
            for entry in self.section_entries(section):
                if entry.get("id"):
                    entry_ids.add(entry["id"])
        # workers/etc reference capabilities
        for section in ("workers", "correctors", "reviewers", "browsers", "tools", "providers", "brains"):
            for entry in self.section_entries(section):
                for cap in entry.get("capabilities", []) or []:
                    if cap not in capability_ids:
                        self.error(f"{section}/{entry.get('id', '?')} references unknown capability '{cap}'")
        # capabilities provided_by must resolve to real ids
        for entry in self.section_entries("capabilities"):
            for pid in entry.get("provided_by", []) or []:
                if pid not in entry_ids:
                    self.warn(f"capabilities/{entry.get('id', '?')} provided_by '{pid}' does not match any entry id (may be abstract)")

    def check_role_bindings(self) -> None:
        bindings = self.registry.get("role_bindings", {})
        if not isinstance(bindings, dict):
            self.error("role_bindings must be an object")
            return
        entry_ids = set()
        for section in REQUIRED_SECTIONS:
            for entry in self.section_entries(section):
                if entry.get("id"):
                    entry_ids.add(entry["id"])
        for role, ids in bindings.items():
            if not isinstance(ids, list):
                self.error(f"role_bindings.{role} must be a list")
                continue
            for entry_id in ids:
                if entry_id not in entry_ids:
                    self.error(f"role_bindings.{role} references unknown id '{entry_id}'")

    def check_cost_quota_section_links(self) -> None:
        entry_ids = set()
        for section in REQUIRED_SECTIONS:
            for entry in self.section_entries(section):
                if entry.get("id"):
                    entry_ids.add(entry["id"])
        for section in ("costs", "quotas", "reliabilities"):
            for entry in self.section_entries(section):
                cap_id = entry.get("capability_id")
                if cap_id and cap_id not in entry_ids:
                    self.error(f"{section}/{entry.get('id', '?')} capability_id '{cap_id}' does not match any entry id")

    def check_lifecycle_entries(self) -> None:
        entry_ids = set()
        for section in REQUIRED_SECTIONS:
            for entry in self.section_entries(section):
                if entry.get("id"):
                    entry_ids.add(entry["id"])
        for lc in self.section_entries("lifecycle_status"):
            entries = lc.get("entries", [])
            for ref in entries:
                if isinstance(ref, dict):
                    ref_id = ref.get("id")
                else:
                    ref_id = ref
                if ref_id and ref_id not in entry_ids:
                    self.warn(f"lifecycle_status/{lc.get('id', '?')} references '{ref_id}' which is not a section entry (may be a historical capability)")

    def check_metadata_shapes(self, section: str, entry: Dict[str, Any]) -> None:
        """Section-specific structural checks for metadata sections."""
        entry_id = entry.get("id", "?")
        if section in ("costs", "quotas", "reliabilities"):
            if "capability_id" not in entry:
                self.error(f"{section}/{entry_id} metadata entry missing field 'capability_id'")
            if section == "quotas":
                limit = entry.get("limit")
                if limit is not None and not isinstance(limit, (int, float)):
                    self.error(f"{section}/{entry_id} quota.limit must be number or null")
        elif section == "capabilities":
            if "name" not in entry:
                self.error(f"{section}/{entry_id} metadata entry missing field 'name'")
            provided_by = entry.get("provided_by", [])
            if not isinstance(provided_by, list):
                self.error(f"{section}/{entry_id} provided_by must be a list")
        elif section == "lifecycle_status":
            if "name" not in entry:
                self.error(f"{section}/{entry_id} metadata entry missing field 'name'")
            if "entries" not in entry or not isinstance(entry.get("entries"), list):
                self.error(f"{section}/{entry_id} lifecycle entry missing list field 'entries'")
        elif section == "permissions":
            if "rules" not in entry or not isinstance(entry.get("rules"), dict):
                self.error(f"{section}/{entry_id} permissions entry missing dict field 'rules'")
        elif section == "adapters":
            if "name" not in entry:
                self.error(f"{section}/{entry_id} metadata entry missing field 'name'")
            if "type" not in entry:
                self.error(f"{section}/{entry_id} metadata entry missing field 'type'")

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def run(self) -> bool:
        if not self.load():
            return False
        self.check_schema_version()
        self.check_required_sections()
        for section in REQUIRED_SECTIONS:
            for entry in self.section_entries(section):
                self.check_entry_required_fields(section, entry)
                if section in CAPABILITY_SECTIONS:
                    self.check_health_check(section, entry)
                    self.check_cost_quota_reliability(section, entry)
                    self.check_permissions(section, entry)
                elif section in METADATA_SECTIONS:
                    self.check_metadata_shapes(section, entry)
        self.check_id_uniqueness()
        self.check_adapter_refs()
        self.check_capability_refs()
        self.check_role_bindings()
        self.check_cost_quota_section_links()
        self.check_lifecycle_entries()
        return len(self.errors) == 0

    def report(self) -> str:
        lines: List[str] = []
        lines.append(f"registry: {self.registry_path}")
        total_entries = sum(len(self.section_entries(s)) for s in REQUIRED_SECTIONS)
        lines.append(f"sections: {len(REQUIRED_SECTIONS)}/15 required present | entries: {total_entries}")
        if self.warnings:
            lines.append(f"warnings ({len(self.warnings)}):")
            for w in self.warnings[:30]:
                lines.append(f"  - {w}")
            if len(self.warnings) > 30:
                lines.append(f"  ... and {len(self.warnings) - 30} more")
        if self.errors:
            lines.append(f"FAIL ({len(self.errors)} error(s)):")
            for e in self.errors[:40]:
                lines.append(f"  - {e}")
        else:
            lines.append("PASS")
        return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Capability Registry schema self-check (§63)")
    parser.add_argument("--registry", default=None, help="path to capability-registry.json (default: repo config/capability-registry.json)")
    parser.add_argument("--verbose", action="store_true", help="print per-check detail")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    registry_path = Path(args.registry) if args.registry else repo_root / "config" / "capability-registry.json"

    validator = RegistryValidator(registry_path, verbose=args.verbose)
    ok = validator.run()
    print(validator.report())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
