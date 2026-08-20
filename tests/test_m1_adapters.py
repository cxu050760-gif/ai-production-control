from __future__ import annotations

"""M1: Adapter contract, registry, and conformance tests.

Covers:
- the three M0.5 Reviewer non-blocking conformance items brought into M1
  (primary TIMEOUT/UNKNOWN no-fallback, Reviewer missing-verdict fail-closed,
  generic worker per-artifact-path digest proof),
- Fresh Weak Worker black-box conformance,
- two interchangeable Workers through one generic adapter path (no core branch),
- API-model vs Web-session provider separation in the registry.
"""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
import sys

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aicontrol.adapters import (  # noqa: E402
    PROVIDER_KIND_API_MODEL,
    PROVIDER_KIND_WEB_SESSION,
    REVIEWER_ROLE_E_LAB,
    REVIEWER_ROLE_R_PROD,
    AdapterContractError,
    assert_no_forbidden_terms,
    build_task_capsule,
    validate_capability_grant,
    validate_worker_artifacts,
)
from aicontrol.controller import Controller, validate_reviewer_envelope  # noqa: E402
from aicontrol.store import AuthorityStateUncertain, GateDenied  # noqa: E402
from aicontrol.util import read_json, sha256_file, sha256_text, write_json  # noqa: E402


class M1Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="aicontrol-m1-")
        self.root = Path(self.temporary.name)
        config = copy.deepcopy(read_json(ROOT / "config" / "production.json"))
        config["code_root"] = str(ROOT)
        config["state_root"] = str(self.root / "state")
        config["output_root"] = str(self.root / "output")
        config["release_root"] = str(self.root / "release")
        config["evidence_root"] = str(self.root / "evidence")
        config["database_path"] = str(self.root / "state" / "control.db")
        self.config_path = self.root / "config.json"
        write_json(self.config_path, config)
        self.controller = Controller(self.config_path)
        self.controller.store.set_meta("tcb_status", "VERIFIED")
        self.controller.store.set_meta("authority_status", "VERIFIED")
        self.task = self.controller.bootstrap_task(
            goal="M1 adapter fixture",
            expected_final_artifact="fixture",
            acceptance_criteria=["A01"],
            data_classification="PUBLIC",
        )
        self.task_id = self.task["task_id"]
        self.context_fence = self.task["context_fence"]

    def tearDown(self) -> None:
        self.controller.close()
        self.temporary.cleanup()

    def register_fixture_worker(self, worker_id: str, variant: str) -> None:
        self.controller.store.upsert_registry(
            "worker_registry",
            "worker_id",
            worker_id,
            {
                "worker_id": worker_id,
                "type": "LOCAL_PROCESS_FIXTURE",
                "invocation": str(ROOT / "scripts" / "fixture_worker.py"),
                "variant": variant,
                "capabilities": ["artifact-write", "local-transform"],
                "allowed_effects": ["LOCAL_REVERSIBLE_WRITE"],
                "network_scope": "NONE",
                "execution_trust_class": "BROKERED",
                "availability": "AVAILABLE",
            },
        )

    # ----- M0.5 Reviewer non-blocking conformance (brought into M1) -----

    def test_primary_timeout_unknown_status_never_falls_back(self) -> None:
        # ORIGIN: M0.5 Reviewer conformance item #1. The primary Brain is invoked
        # through the real run_goal path; each run creates a fresh task. A primary
        # that EXPLICITLY returns TIMEOUT/UNKNOWN (not an exception) must end as
        # OUTCOME_UNKNOWN and never trigger the WorkBuddy fallback.
        for status in ("TIMEOUT", "UNKNOWN"):
            with self.subTest(status=status):
                with (
                    mock.patch("aicontrol.controller.verify_tcb", return_value={"status": "VERIFIED"}),
                    mock.patch("aicontrol.controller.browser_profile_identity", return_value="cft-profile-hash"),
                    mock.patch.object(
                        self.controller.runtime,
                        "invoke_browser",
                        return_value={"envelope": {"status": status, "data": {"profile_identity_hash": "cft-profile-hash"}}},
                    ),
                    mock.patch.object(self.controller.runtime, "invoke_workbuddy_brain") as fallback,
                ):
                    with self.assertRaises(AuthorityStateUncertain):
                        self.controller.run_goal("M1 no-fallback probe", data_classification="PUBLIC")
                fallback.assert_not_called()
                row = self.controller.store.connection.execute(
                    "SELECT status FROM actions WHERE provider='ChatGPT' ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
                self.assertEqual(row["status"], "OUTCOME_UNKNOWN")

    def test_reviewer_missing_verdict_is_fail_closed(self) -> None:
        # ORIGIN: M0.5 Reviewer conformance item #2.
        envelope = {
            "schema_version": 1,
            "invocation_id": "i",
            "request_nonce": "n",
            "task_id": "t",
            "goal_contract_hash": "g",
            "request_state_revision": 1,
            "request_context_fence": "c",
            "artifact_digest": "a",
            "acceptance_evidence_id": "e",
            "status": "DONE",
            "role": "REVIEWER",
            "findings": [],
            "recommended_actions": [],
            "human_readable_content": "no verdict",
            # "verdict" deliberately omitted
        }
        with self.assertRaises(GateDenied):
            validate_reviewer_envelope(
                envelope, task_id="t", goal_contract_hash="g", state_revision=1,
                context_fence="c", artifact_digest="a", acceptance_evidence_id="e",
            )

    def test_worker_artifact_proof_is_per_path_not_dict_type(self) -> None:
        # ORIGIN: M0.5 Reviewer conformance item #3. The generic worker contract
        # must prove EVERY artifact_path has its own correct digest, not merely
        # that `artifact_hashes` is a dict.
        with tempfile.TemporaryDirectory(prefix="aicontrol-m1-artifact-") as temporary:
            root = Path(temporary)
            artifact = root / "out.txt"
            artifact.write_text("hello", encoding="utf-8")
            resolve = lambda p, roots, must_exist=True: Path(p)  # noqa: E731
            good = {"artifact_paths": [str(artifact)], "artifact_hashes": {str(artifact): sha256_file(artifact)}}
            result = validate_worker_artifacts(good, str(root), resolve=resolve)
            self.assertEqual(result["artifact_count"], 1)
            empty_hash = {"artifact_paths": [str(artifact)], "artifact_hashes": {}}
            with self.assertRaises(AdapterContractError):
                validate_worker_artifacts(empty_hash, str(root), resolve=resolve)
            wrong_hash = {"artifact_paths": [str(artifact)], "artifact_hashes": {str(artifact): sha256_text("other")}}
            with self.assertRaises(AdapterContractError):
                validate_worker_artifacts(wrong_hash, str(root), resolve=resolve)

    # ----- Fresh Weak Worker black-box conformance -----

    def test_fresh_weak_worker_runs_black_box_via_generic_adapter(self) -> None:
        self.register_fixture_worker("fixture-alpha", "alpha")
        result = self.controller.runtime.invoke_worker_adapter(
            task_id=self.task_id, context_fence=self.context_fence,
            worker_id="fixture-alpha", objective="produce a conformance fixture",
        )
        self.assertEqual(result["verification"]["verification_status"], "VERIFIED")
        self.assertEqual(result["source_binding"]["worker_id"], "fixture-alpha")
        self.assertEqual(len(result["envelope"]["artifact_paths"]), 1)
        assert_no_forbidden_terms(json.dumps(result["capsule"], ensure_ascii=False))
        assert_no_forbidden_terms(json.dumps(result["envelope"], ensure_ascii=False))
        request_path = Path(result["source_binding"]["result_channel"]).parent / "request.json"
        assert_no_forbidden_terms(request_path.read_text(encoding="utf-8"))
        artifact_path = Path(result["envelope"]["artifact_paths"][0])
        assert_no_forbidden_terms(artifact_path.read_text(encoding="utf-8"))
        self.assertIn("variant: alpha", artifact_path.read_text(encoding="utf-8"))

    def test_two_workers_are_interchangeable_through_one_generic_path(self) -> None:
        self.register_fixture_worker("fixture-alpha", "alpha")
        self.register_fixture_worker("fixture-beta", "beta")
        results = {}
        for worker_id in ("fixture-alpha", "fixture-beta"):
            results[worker_id] = self.controller.runtime.invoke_worker_adapter(
                task_id=self.task_id, context_fence=self.context_fence,
                worker_id=worker_id, objective="interchangeability probe",
            )
        for worker_id, result in results.items():
            self.assertEqual(result["verification"]["verification_status"], "VERIFIED")
            self.assertEqual(result["source_binding"]["worker_id"], worker_id)
        alpha_content = Path(results["fixture-alpha"]["envelope"]["artifact_paths"][0]).read_text(encoding="utf-8")
        beta_content = Path(results["fixture-beta"]["envelope"]["artifact_paths"][0]).read_text(encoding="utf-8")
        self.assertIn("variant: alpha", alpha_content)
        self.assertIn("variant: beta", beta_content)
        self.assertNotEqual(alpha_content, beta_content)

    # ----- Registry / provider separation -----

    def test_provider_registry_separates_api_model_from_websession(self) -> None:
        self.controller.runtime.register_defaults()
        providers = {p["provider_id"]: p for p in self.controller.store.registry("provider_registry")}
        self.assertEqual(providers["chatgpt-web"]["kind"], PROVIDER_KIND_WEB_SESSION)
        self.assertEqual(providers["workbuddy-cli"]["kind"], PROVIDER_KIND_API_MODEL)
        self.assertEqual(providers["codex-cli"]["kind"], PROVIDER_KIND_API_MODEL)
        for provider in providers.values():
            self.assertEqual(provider["transport_identity_owner"], "CONTROLLER")
        reviewers = {r["reviewer_id"]: r for r in self.controller.store.registry("reviewer_registry")}
        self.assertEqual(reviewers["chatgpt-web"]["role"], REVIEWER_ROLE_R_PROD)
        self.assertEqual(reviewers["codex-local"]["role"], REVIEWER_ROLE_E_LAB)

    def test_tool_registry_and_generation_increment(self) -> None:
        self.controller.runtime.register_defaults()
        self.assertEqual(self.controller.store.registry("tool_registry"), [])
        self.controller.store.upsert_registry("tool_registry", "tool_id", "browser", {"tool": "browser"})
        self.assertEqual(len(self.controller.store.registry("tool_registry")), 1)
        self.controller.store.upsert_registry("tool_registry", "tool_id", "browser", {"tool": "browser"})
        self.assertEqual(self.controller.store.registry("tool_registry")[0]["generation"], 2)

    def test_capability_grant_validation(self) -> None:
        validate_capability_grant({"capabilities": ["read"], "allowed_effects": ["LOCAL_REVERSIBLE_WRITE"], "network_scope": "NONE"})
        with self.assertRaises(AdapterContractError):
            validate_capability_grant({"capabilities": ["read"], "network_scope": "NONE"})
        capsule = build_task_capsule(
            task_id="t", objective="ok", goal_contract_hash="g", state_revision=1,
            context_fence="c", capability_grant={"capabilities": ["read"], "allowed_effects": [], "network_scope": "NONE"},
            allowed_roots=["C:\\x"],
        )
        assert_no_forbidden_terms(json.dumps(capsule, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()