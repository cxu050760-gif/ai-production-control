from __future__ import annotations

"""V0.8 Adapter Registry offline conformance gate.

This file is intentionally self-contained and standard-library-only.  It validates
Registry identity/relationship data without importing the B1 Adapter core, running
Reviewers, granting Authority, executing Effects, or scheduling multiple Workers.
"""

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "runtime" / "v08_adapter_registry.json"
ATTACK_CASES_PATH = ROOT / "runtime" / "fixtures" / "v08_adapter_registry_attack_cases.json"
BOOTSTRAP_PATH = ROOT / "runtime" / "bootstrap.json"

REGISTRY_SCHEMA = "V08_ADAPTER_REGISTRY"
REGISTRY_SCHEMA_VERSION = 1
PROVIDER_KINDS = frozenset({"API_MODEL", "WEB_SESSION"})
REVIEWER_ROLES = frozenset({"R_PROD", "E_LAB"})
CONSERVATIVE_STATUS = frozenset({"UNVERIFIED_CURRENT", "UNKNOWN", "DISABLED"})
TRANSPORT_IDENTITY_OWNER = "RUNTIME_CONTROLLER"
WORKER_SELECTION_MODE = "SINGLE_ACTIVE_REPLACEMENT"
MAX_COLLECTION_ITEMS = 64
MAX_STRING_LENGTH = 512
MAX_CAPABILITIES = 32
MAX_OBJECT_FIELDS = 32
MAX_ID_LENGTH = 128
MAX_DEPTH = 8
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

ROOT_FIELDS = frozenset(
    {"schema", "schema_version", "registry_generation", "worker_selection_mode", "providers", "reviewers", "workers"}
)
PROVIDER_FIELDS = frozenset(
    {"provider_id", "kind", "adapter_class", "contract", "availability", "transport_identity_owner"}
)
REVIEWER_FIELDS = frozenset(
    {"reviewer_id", "role", "provider_id", "contract", "availability", "health"}
)
WORKER_FIELDS = frozenset(
    {"worker_id", "type", "provider_id", "contract", "capabilities", "availability"}
)

# Historical M1 semantics retained without importing the old SQLite registry.
ADAPTER_CLASS_BY_KIND = {
    "API_MODEL": "APIModelProvider",
    "WEB_SESSION": "WebSessionProvider",
}
PINNED_PROVIDER_KINDS = {
    "chatgpt-web": "WEB_SESSION",
    "workbuddy-cli": "API_MODEL",
    "codex-cli": "API_MODEL",
}

SECRET_KEY_TERMS = frozenset(
    {"token", "api_key", "apikey", "secret", "password", "passwd", "cookie", "authorization", "credential"}
)
TRANSPORT_INTERNAL_KEY_TERMS = frozenset(
    {
        "bsk",
        "daemon",
        "marker",
        "yz_lib",
        "bridge",
        "chrome_extension",
        "chromeextension",
        "cft_executable",
        "session_id",
        "session_url",
        "session_secret",
        "bsk_session",
    }
)
TRANSPORT_INTERNAL_VALUE_TERMS = frozenset(
    {"bsk", "daemon", "marker", "yz_lib", "chrome-extension://", "chrome extension internals", "cft_executable"}
)
FORBIDDEN_CONTROL_KEYS = frozenset(
    {
        "authority",
        "authorities",
        "authorization",
        "authorizations",
        "effect",
        "effects",
        "effect_execution",
        "verdict",
        "review_verdict",
        "milestone_pass",
        "promotion",
        "release",
        "crown",
        "scheduler",
        "scheduling",
        "routing_policy",
        "fallback_policy",
        "account",
        "accounts",
    }
)


class RegistryConformanceError(ValueError):
    pass


def _fail(code: str) -> None:
    raise RegistryConformanceError(code)


def _normalized_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")


def _strict_positive_int(value: Any, where: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{where}:TYPE")
    minimum = 0 if allow_zero else 1
    if value < minimum:
        _fail(f"{where}:RANGE")
    return value


def _walk_security(value: Any, path: tuple[str, ...] = (), depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        _fail("REGISTRY_TOO_DEEP")
    if isinstance(value, dict):
        if len(value) > MAX_OBJECT_FIELDS:
            _fail("OVERSIZED_OBJECT")
        for raw_key, child in value.items():
            if not isinstance(raw_key, str) or not raw_key:
                _fail("MALFORMED_KEY")
            if len(raw_key) > MAX_STRING_LENGTH:
                _fail("OVERSIZED_KEY")
            key = _normalized_key(raw_key)
            if any(term in key for term in SECRET_KEY_TERMS):
                _fail(f"SECRET_LIKE_FIELD:{'.'.join(path + (raw_key,))}")
            if any(term in key for term in TRANSPORT_INTERNAL_KEY_TERMS):
                _fail(f"TRANSPORT_INTERNAL_FIELD:{'.'.join(path + (raw_key,))}")
            if key in FORBIDDEN_CONTROL_KEYS:
                _fail(f"FORBIDDEN_CONTROL_FIELD:{'.'.join(path + (raw_key,))}")
            _walk_security(child, path + (raw_key,), depth + 1)
        return
    if isinstance(value, list):
        if len(value) > MAX_COLLECTION_ITEMS:
            _fail(f"OVERSIZED_LIST:{'.'.join(path)}")
        for index, child in enumerate(value):
            _walk_security(child, path + (str(index),), depth + 1)
        return
    if isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH:
            _fail(f"OVERSIZED_STRING:{'.'.join(path)}")
        lowered = value.lower()
        if "http://" in lowered or "https://" in lowered:
            _fail(f"DYNAMIC_OR_SESSION_URL:{'.'.join(path)}")
        if any(term in lowered for term in TRANSPORT_INTERNAL_VALUE_TERMS):
            _fail(f"TRANSPORT_INTERNAL_VALUE:{'.'.join(path)}")


def _require_exact_fields(obj: Any, allowed: frozenset[str], where: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        _fail(f"{where}:NOT_OBJECT")
    fields = set(obj)
    missing = sorted(allowed - fields)
    unexpected = sorted(fields - allowed)
    if missing:
        _fail(f"{where}:MISSING:{','.join(missing)}")
    if unexpected:
        _fail(f"{where}:UNEXPECTED:{','.join(unexpected)}")
    return obj


def _require_id(value: Any, where: str) -> str:
    if not isinstance(value, str):
        _fail(f"{where}:TYPE")
    if value != value.strip() or not value or len(value) > MAX_ID_LENGTH or not ID_RE.fullmatch(value):
        _fail(f"{where}:INVALID")
    return value


def _require_string(value: Any, expected: str, where: str) -> None:
    if not isinstance(value, str) or value != expected:
        _fail(f"{where}:EXPECTED:{expected}")


def _require_status(value: Any, where: str) -> None:
    if not isinstance(value, str) or value not in CONSERVATIVE_STATUS:
        _fail(f"{where}:NON_CONSERVATIVE")


def _unique_ids(records: list[dict[str, Any]], key: str, where: str) -> None:
    seen: set[str] = set()
    for record in records:
        identity = record[key]
        if identity in seen:
            _fail(f"DUPLICATE_{where.upper()}_ID:{identity}")
        seen.add(identity)


def validate_registry(registry: Any, *, minimum_generation: int = 1) -> dict[str, Any]:
    """Fail-closed validation for the static V0.8 Registry data model."""
    _walk_security(registry)
    root = _require_exact_fields(registry, ROOT_FIELDS, "ROOT")
    _require_string(root["schema"], REGISTRY_SCHEMA, "SCHEMA")
    schema_version = _strict_positive_int(root["schema_version"], "SCHEMA_VERSION")
    if schema_version != REGISTRY_SCHEMA_VERSION:
        _fail("UNSUPPORTED_SCHEMA_VERSION")
    minimum_generation = _strict_positive_int(minimum_generation, "MINIMUM_GENERATION")
    generation = _strict_positive_int(root["registry_generation"], "REGISTRY_GENERATION")
    if generation < minimum_generation:
        _fail("REGISTRY_GENERATION_ROLLBACK")
    _require_string(root["worker_selection_mode"], WORKER_SELECTION_MODE, "WORKER_SELECTION_MODE")

    providers = root["providers"]
    reviewers = root["reviewers"]
    workers = root["workers"]
    if not isinstance(providers, list) or not providers:
        _fail("PROVIDERS:NON_EMPTY_LIST_REQUIRED")
    if not isinstance(reviewers, list) or not reviewers:
        _fail("REVIEWERS:NON_EMPTY_LIST_REQUIRED")
    if not isinstance(workers, list) or not workers:
        _fail("WORKERS:NON_EMPTY_LIST_REQUIRED")

    normalized_providers: list[dict[str, Any]] = []
    for index, raw in enumerate(providers):
        item = _require_exact_fields(raw, PROVIDER_FIELDS, f"PROVIDERS[{index}]")
        provider_id = _require_id(item["provider_id"], f"PROVIDERS[{index}].provider_id")
        kind = item["kind"]
        if not isinstance(kind, str) or kind not in PROVIDER_KINDS:
            _fail(f"UNKNOWN_PROVIDER_KIND:{kind!r}")
        if provider_id in PINNED_PROVIDER_KINDS and PINNED_PROVIDER_KINDS[provider_id] != kind:
            _fail(f"PROVIDER_IDENTITY_KIND_SWAP:{provider_id}")
        expected_class = ADAPTER_CLASS_BY_KIND[kind]
        _require_string(item["adapter_class"], expected_class, f"PROVIDERS[{index}].adapter_class")
        _require_string(item["contract"], "V08_PROVIDER_CONTRACT", f"PROVIDERS[{index}].contract")
        _require_status(item["availability"], f"PROVIDERS[{index}].availability")
        _require_string(item["transport_identity_owner"], TRANSPORT_IDENTITY_OWNER, f"PROVIDERS[{index}].transport_identity_owner")
        normalized_providers.append(item)
    _unique_ids(normalized_providers, "provider_id", "provider")
    provider_by_id = {item["provider_id"]: item for item in normalized_providers}

    normalized_reviewers: list[dict[str, Any]] = []
    for index, raw in enumerate(reviewers):
        item = _require_exact_fields(raw, REVIEWER_FIELDS, f"REVIEWERS[{index}]")
        _require_id(item["reviewer_id"], f"REVIEWERS[{index}].reviewer_id")
        if not isinstance(item["role"], str) or item["role"] not in REVIEWER_ROLES:
            _fail(f"REVIEWERS[{index}].role:INVALID")
        provider_id = _require_id(item["provider_id"], f"REVIEWERS[{index}].provider_id")
        if provider_id not in provider_by_id:
            _fail(f"REVIEWER_PROVIDER_MISSING:{provider_id}")
        _require_string(item["contract"], "V08_REVIEWER_IDENTITY_CONTRACT", f"REVIEWERS[{index}].contract")
        _require_status(item["availability"], f"REVIEWERS[{index}].availability")
        _require_status(item["health"], f"REVIEWERS[{index}].health")
        normalized_reviewers.append(item)
    _unique_ids(normalized_reviewers, "reviewer_id", "reviewer")

    normalized_workers: list[dict[str, Any]] = []
    for index, raw in enumerate(workers):
        item = _require_exact_fields(raw, WORKER_FIELDS, f"WORKERS[{index}]")
        _require_id(item["worker_id"], f"WORKERS[{index}].worker_id")
        _require_string(item["type"], "AI_CLI", f"WORKERS[{index}].type")
        provider_id = _require_id(item["provider_id"], f"WORKERS[{index}].provider_id")
        if provider_id not in provider_by_id:
            _fail(f"WORKER_PROVIDER_MISSING:{provider_id}")
        _require_string(item["contract"], "V08_WORKER_ADAPTER_CONTRACT", f"WORKERS[{index}].contract")
        capabilities = item["capabilities"]
        if not isinstance(capabilities, list) or not capabilities or len(capabilities) > MAX_CAPABILITIES:
            _fail(f"WORKERS[{index}].capabilities:INVALID")
        if len(set(capabilities)) != len(capabilities):
            _fail(f"WORKERS[{index}].capabilities:DUPLICATE")
        for cap_index, capability in enumerate(capabilities):
            if not isinstance(capability, str) or not capability or len(capability) > MAX_ID_LENGTH:
                _fail(f"WORKERS[{index}].capabilities[{cap_index}]:INVALID")
        _require_status(item["availability"], f"WORKERS[{index}].availability")
        normalized_workers.append(item)
    _unique_ids(normalized_workers, "worker_id", "worker")

    kinds = {item["kind"] for item in normalized_providers}
    if kinds != PROVIDER_KINDS:
        _fail("PROVIDER_KIND_SEPARATION_NOT_EXPLICIT")

    return {
        "schema": REGISTRY_SCHEMA,
        "schema_version": schema_version,
        "registry_generation": generation,
        "provider_count": len(normalized_providers),
        "reviewer_count": len(normalized_reviewers),
        "worker_count": len(normalized_workers),
        "provider_kinds": sorted(kinds),
        "worker_selection_mode": root["worker_selection_mode"],
    }


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_parent(root: Any, path: list[Any]) -> tuple[Any, Any]:
    if not path:
        _fail("ATTACK_PATH_EMPTY")
    current = root
    for part in path[:-1]:
        current = current[part]
    return current, path[-1]


def apply_attack(valid_registry: dict[str, Any], case: dict[str, Any]) -> Any:
    mutated: Any = copy.deepcopy(valid_registry)
    operation = case["operation"]
    if operation == "replace_root":
        return copy.deepcopy(case["value"])
    if operation == "set":
        parent, key = _resolve_parent(mutated, case["path"])
        parent[key] = copy.deepcopy(case["value"])
        return mutated
    if operation == "delete":
        parent, key = _resolve_parent(mutated, case["path"])
        del parent[key]
        return mutated
    if operation == "duplicate_record":
        section = case["section"]
        mutated[section].append(copy.deepcopy(mutated[section][case["index"]]))
        return mutated
    if operation == "oversize_list":
        section = case["section"]
        sample = copy.deepcopy(mutated[section][0])
        mutated[section] = []
        for index in range(case["count"]):
            item = copy.deepcopy(sample)
            identity_key = {"providers": "provider_id", "reviewers": "reviewer_id", "workers": "worker_id"}[section]
            item[identity_key] = f"oversize-{index}"
            mutated[section].append(item)
        return mutated
    _fail(f"UNKNOWN_ATTACK_OPERATION:{operation}")


class V08AdapterRegistryConformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = _load_json(REGISTRY_PATH)
        cls.attacks = _load_json(ATTACK_CASES_PATH)

    def test_valid_registry_is_accepted(self) -> None:
        proof = validate_registry(copy.deepcopy(self.registry), minimum_generation=1)
        self.assertEqual(proof["schema"], REGISTRY_SCHEMA)
        self.assertEqual(proof["registry_generation"], 1)
        self.assertEqual(proof["provider_kinds"], ["API_MODEL", "WEB_SESSION"])
        self.assertEqual(proof["worker_selection_mode"], WORKER_SELECTION_MODE)

    def test_provider_kind_and_transport_separation_is_exact(self) -> None:
        providers = {item["provider_id"]: item for item in self.registry["providers"]}
        self.assertEqual(providers["chatgpt-web"]["kind"], "WEB_SESSION")
        self.assertEqual(providers["chatgpt-web"]["adapter_class"], "WebSessionProvider")
        self.assertEqual(providers["workbuddy-cli"]["kind"], "API_MODEL")
        self.assertEqual(providers["codex-cli"]["kind"], "API_MODEL")
        for item in providers.values():
            self.assertEqual(item["transport_identity_owner"], TRANSPORT_IDENTITY_OWNER)

    def test_registry_is_identity_only_not_authority_review_pass_or_scheduler(self) -> None:
        serialized = json.dumps(self.registry, ensure_ascii=False).lower()
        for forbidden in ("\"verdict\"", "\"authority\"", "\"effect_execution\"", "\"scheduler\"", "\"promotion\"", "\"release\""):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(self.registry["worker_selection_mode"], WORKER_SELECTION_MODE)
        self.assertNotIn("MULTI", self.registry["worker_selection_mode"])
        for reviewer in self.registry["reviewers"]:
            self.assertEqual(reviewer["availability"], "UNVERIFIED_CURRENT")
            self.assertEqual(reviewer["health"], "UNVERIFIED_CURRENT")

    def test_registry_conformance_has_no_b1_core_dependency(self) -> None:
        # This gate imports only the Python standard library and reads static JSON.
        # Absence of runtime/v08_adapter.py or runtime/v08_adapter_contract.py must
        # not change pure Registry validation behavior.
        proof = validate_registry(copy.deepcopy(self.registry), minimum_generation=1)
        self.assertEqual(proof["provider_count"], 3)
        self.assertEqual(proof["reviewer_count"], 2)
        self.assertEqual(proof["worker_count"], 2)

    def test_bootstrap_exposes_only_fixed_registry_pointer_from_v08_b2(self) -> None:
        bootstrap = _load_json(BOOTSTRAP_PATH)
        self.assertEqual(bootstrap.get("adapter_registry"), "runtime/v08_adapter_registry.json")
        self.assertIsInstance(bootstrap["adapter_registry"], str)
        self.assertNotRegex(bootstrap["adapter_registry"], r"(?i)https?://|token|secret|cookie|session[_-]?id|bsk")

    def test_all_declared_red_first_attack_cases_fail_closed(self) -> None:
        self.assertGreaterEqual(len(self.attacks.get("cases", [])), 20)
        ids = [case["id"] for case in self.attacks["cases"]]
        self.assertEqual(len(ids), len(set(ids)))
        for case in self.attacks["cases"]:
            with self.subTest(case=case["id"]):
                mutated = apply_attack(self.registry, case)
                minimum = case.get("minimum_generation", 1)
                with self.assertRaises(RegistryConformanceError):
                    validate_registry(mutated, minimum_generation=minimum)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(V08AdapterRegistryConformance)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print(f"V08_ADAPTER_REGISTRY_CONFORMANCE=PASS ATTACK_CASES={len(V08AdapterRegistryConformance.attacks['cases'])}")
    raise SystemExit(0 if result.wasSuccessful() else 1)
