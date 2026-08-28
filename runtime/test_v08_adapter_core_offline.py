from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import v08_adapter as adapter  # noqa: E402
from v08_adapter_contract import (  # noqa: E402
    CONTRACT_VERSION,
    ERROR_ARTIFACT_INTEGRITY,
    ERROR_ARTIFACT_OUTSIDE_WORKSPACE,
    ERROR_FORBIDDEN_INTERNAL_TERM,
    ERROR_INVALID_CAPSULE,
    ERROR_MALFORMED_RESULT,
    ERROR_REGISTRY_INVALID,
    ERROR_REGISTRY_MISSING,
    ERROR_SOURCE_BINDING_MISMATCH,
    ERROR_UNKNOWN_WORKER,
    ERROR_WORKER_UNAVAILABLE,
    PROVIDER_KIND_API_MODEL,
    PROVIDER_KIND_WEB_SESSION,
    AdapterContractError,
    build_task_capsule,
    validate_registry,
    validate_source_binding,
    validate_task_capsule,
    validate_worker_artifacts,
    validate_worker_result_envelope,
)

FIXTURE = RUNTIME / "fixtures" / "v08_fixture_worker.py"
REAL_REGISTRY = RUNTIME / "v08_adapter_registry.json"
REAL_BOOTSTRAP = RUNTIME / "bootstrap.json"

class CanonicalRegistryFixture(dict):
    """Canonical B2-shaped registry with a non-JSON test-only execution overlay."""

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def execution_binding_for(worker_id: str) -> dict:
    return {
        "binding_type": adapter.TEST_ONLY_EXECUTION_BINDING,
        "worker_id": worker_id,
        "command": [sys.executable, str(FIXTURE)],
        "allowed_effects": ["LOCAL_REVERSIBLE_WRITE"],
        "network_scope": "NONE",
        "timeout_seconds": 20,
    }

def registry_for(*worker_ids: str) -> dict:
    """Isolated unit fixture using the ONE canonical B2 registry shape."""
    registry = CanonicalRegistryFixture({
        "schema": "V08_ADAPTER_REGISTRY",
        "schema_version": 1,
        "registry_generation": 1,
        "worker_selection_mode": "SINGLE_ACTIVE_REPLACEMENT",
        "providers": [
            {
                "provider_id": "provider-api",
                "kind": PROVIDER_KIND_API_MODEL,
                "adapter_class": "APIModelProvider",
                "contract": "V08_PROVIDER_CONTRACT",
                "availability": "UNVERIFIED_CURRENT",
                "transport_identity_owner": "RUNTIME_CONTROLLER",
            },
            {
                "provider_id": "provider-web",
                "kind": PROVIDER_KIND_WEB_SESSION,
                "adapter_class": "WebSessionProvider",
                "contract": "V08_PROVIDER_CONTRACT",
                "availability": "UNVERIFIED_CURRENT",
                "transport_identity_owner": "RUNTIME_CONTROLLER",
            },
        ],
        "reviewers": [
            {
                "reviewer_id": "reviewer-prod",
                "role": "R_PROD",
                "provider_id": "provider-web",
                "contract": "V08_REVIEWER_IDENTITY_CONTRACT",
                "availability": "UNVERIFIED_CURRENT",
                "health": "UNVERIFIED_CURRENT",
            },
            {
                "reviewer_id": "reviewer-lab",
                "role": "E_LAB",
                "provider_id": "provider-api",
                "contract": "V08_REVIEWER_IDENTITY_CONTRACT",
                "availability": "UNVERIFIED_CURRENT",
                "health": "UNVERIFIED_CURRENT",
            },
        ],
        "workers": [
            {
                "worker_id": worker_id,
                "type": "AI_CLI",
                "provider_id": "provider-api",
                "contract": "V08_WORKER_ADAPTER_CONTRACT",
                "capabilities": ["analysis", "proposal"],
                "availability": "UNVERIFIED_CURRENT",
            }
            for worker_id in worker_ids
        ],
    })
    registry.test_only_execution_bindings = {
        worker_id: execution_binding_for(worker_id) for worker_id in worker_ids
    }
    return registry

def capsule_for(*, worker_id: str = "fixture-alpha", objective: str = "offline probe") -> dict:
    return build_task_capsule(
        task_id="task-1",
        invocation_id="invocation-1",
        worker_id=worker_id,
        context_id="context-1",
        objective=objective,
        artifact_declarations=[{"path": "artifact.txt", "media_type": "text/plain"}],
        capabilities=["artifact-write"],
        allowed_effects=["LOCAL_REVERSIBLE_WRITE"],
        network_scope="NONE",
    )

def result_for(capsule: dict, artifact: Path, *, raw_path: str = "artifact.txt") -> dict:
    return {
        "contract_version": CONTRACT_VERSION,
        "result_type": "WORKER_RESULT",
        "status": "DONE",
        "source_binding": {
            "task_id": capsule["task_id"],
            "invocation_id": capsule["invocation_id"],
            "worker_id": capsule["worker_id"],
            "context_id": capsule["context_id"],
            "capsule_id": capsule["capsule_id"],
            "artifact_set_id": capsule["artifact_set_id"],
        },
        "artifact_paths": [raw_path],
        "artifact_hashes": {raw_path: digest(artifact)},
        "error": None,
        "notes": "ok",
    }

class V08AdapterCoreOfflineTests(unittest.TestCase):
    def test_01_valid_task_capsule(self) -> None:
        capsule = capsule_for()
        self.assertEqual(validate_task_capsule(capsule), capsule)
        self.assertIs(capsule["metadata"]["authority_grant"], False)
        self.assertIs(capsule["metadata"]["effect_authorization"], False)

    def test_02_invalid_capsule_fail_closed(self) -> None:
        capsule = capsule_for(); capsule["contract_version"] = "wrong"
        with self.assertRaises(AdapterContractError) as caught: validate_task_capsule(capsule)
        self.assertEqual(caught.exception.code, ERROR_INVALID_CAPSULE)

    def test_03_malformed_internal_capsule_fail_closed(self) -> None:
        capsule = capsule_for(); capsule["metadata"] = {"capabilities": "not-a-list"}
        with self.assertRaises(AdapterContractError) as caught: validate_task_capsule(capsule)
        self.assertEqual(caught.exception.code, ERROR_INVALID_CAPSULE)

    def test_04_forbidden_internal_term_rejected(self) -> None:
        with self.assertRaises(AdapterContractError) as caught: capsule_for(objective="inspect daemon state")
        self.assertEqual(caught.exception.code, ERROR_FORBIDDEN_INTERNAL_TERM)

    def test_05_valid_artifact_digest_recomputed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); artifact=root/"artifact.txt"; artifact.write_text("hello",encoding="utf-8")
            proof=validate_worker_artifacts(result_for(capsule_for(),artifact),capsule_for(),root)
            self.assertEqual(proof["artifacts"][0]["sha256"],digest(artifact))

    def test_06_missing_digest_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); artifact=root/"artifact.txt"; artifact.write_text("hello",encoding="utf-8")
            capsule=capsule_for(); result=result_for(capsule,artifact); result["artifact_hashes"]={}
            with self.assertRaises(AdapterContractError) as caught: validate_worker_artifacts(result,capsule,root)
            self.assertEqual(caught.exception.code,ERROR_ARTIFACT_INTEGRITY)

    def test_07_extra_digest_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); artifact=root/"artifact.txt"; artifact.write_text("hello",encoding="utf-8")
            capsule=capsule_for(); result=result_for(capsule,artifact); result["artifact_hashes"]["extra.txt"]="0"*64
            with self.assertRaises(AdapterContractError) as caught: validate_worker_artifacts(result,capsule,root)
            self.assertEqual(caught.exception.code,ERROR_ARTIFACT_INTEGRITY)

    def test_08_mismatched_digest_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); artifact=root/"artifact.txt"; artifact.write_text("hello",encoding="utf-8")
            capsule=capsule_for(); result=result_for(capsule,artifact); result["artifact_hashes"]["artifact.txt"]="0"*64
            with self.assertRaises(AdapterContractError) as caught: validate_worker_artifacts(result,capsule,root)
            self.assertEqual(caught.exception.code,ERROR_ARTIFACT_INTEGRITY)

    def test_09_artifact_outside_workspace_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent=Path(temporary); workspace=parent/"workspace"; workspace.mkdir()
            outside=parent/"outside.txt"; outside.write_text("outside",encoding="utf-8")
            capsule=capsule_for(); result=result_for(capsule,outside,raw_path="../outside.txt")
            with self.assertRaises(AdapterContractError) as caught: validate_worker_artifacts(result,capsule,workspace)
            self.assertEqual(caught.exception.code,ERROR_ARTIFACT_OUTSIDE_WORKSPACE)

    def test_10_unknown_worker_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(AdapterContractError) as caught:
                adapter.invoke_worker(worker_id="not-registered",task_id="task",context_id="context",objective="probe",
                    workspace=temporary,artifact_declarations=[{"path":"artifact.txt","media_type":"text/plain"}],
                    registry=registry_for("fixture-alpha"))
            self.assertEqual(caught.exception.code,ERROR_UNKNOWN_WORKER)

    def test_11_malformed_registry_rejected(self) -> None:
        value=registry_for("fixture-alpha"); del value["workers"][0]["contract"]
        with self.assertRaises(AdapterContractError) as caught: validate_registry(value)
        self.assertEqual(caught.exception.code,ERROR_REGISTRY_INVALID)

    def test_12_wrong_source_binding_rejected(self) -> None:
        capsule=capsule_for()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"artifact.txt"; p.write_text("x",encoding="utf-8"); base=result_for(capsule,p)
        for field in ("task_id","invocation_id","worker_id","context_id","capsule_id","artifact_set_id"):
            with self.subTest(field=field):
                result=copy.deepcopy(base); result["source_binding"][field]="cross-boundary-value"
                with self.assertRaises(AdapterContractError) as caught: validate_source_binding(result,capsule)
                self.assertEqual(caught.exception.code,ERROR_SOURCE_BINDING_MISMATCH)

    def test_13_malformed_worker_result_rejected(self) -> None:
        malformed={"contract_version":CONTRACT_VERSION,"result_type":"WORKER_RESULT","status":"DONE",
            "source_binding":{"task_id":"looks-valid-outside"},"artifact_paths":["artifact.txt"],
            "artifact_hashes":{"artifact.txt":"0"*64},"error":None,"notes":"outer envelope looks plausible"}
        with self.assertRaises(AdapterContractError) as caught: validate_worker_result_envelope(malformed)
        self.assertEqual(caught.exception.code,ERROR_MALFORMED_RESULT)

    def test_14_fresh_weak_worker_through_generic_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output=adapter.invoke_worker(worker_id="fixture-alpha",task_id="task-alpha",context_id="context-alpha",
                objective="produce offline artifact",workspace=temporary,
                artifact_declarations=[{"path":"artifact.txt","media_type":"text/plain"}],
                registry=registry_for("fixture-alpha"))
            self.assertEqual(output["status"],"DONE"); self.assertEqual(output["artifact_proof"]["artifact_count"],1)
            self.assertIn("worker_id=fixture-alpha",(Path(temporary)/"artifact.txt").read_text(encoding="utf-8"))
            self.assertEqual(output["execution_binding_source"],adapter.TEST_ONLY_EXECUTION_BINDING)

    def test_15_two_workers_same_core_path(self) -> None:
        registry=registry_for("fixture-alpha","fixture-beta"); outputs={}
        for worker_id in ("fixture-alpha","fixture-beta"):
            with tempfile.TemporaryDirectory() as temporary:
                result=adapter.invoke_worker(worker_id=worker_id,task_id="task-replacement",context_id="context-replacement",
                    objective="replacement probe",workspace=temporary,
                    artifact_declarations=[{"path":"artifact.txt","media_type":"text/plain"}],registry=registry)
                outputs[worker_id]=(Path(temporary)/"artifact.txt").read_text(encoding="utf-8")
                self.assertEqual(result["source_binding"]["worker_id"],worker_id)
        self.assertNotEqual(outputs["fixture-alpha"],outputs["fixture-beta"])

    def test_16_existing_run_cmd_behavior_preserved(self) -> None:
        text=(RUNTIME/"run.cmd").read_text(encoding="utf-8")
        for required in (
            'if /I "%~1"=="harness-verify" goto harness_verify',
            'if /I "%~1"=="start" goto goal_contract',
            'if /I "%~1"=="send" goto send_guard',
            'if /I "%~1"=="effect-gate" goto effect_safety',
            'if /I "%~1"=="ec-gate" goto ec_lite',
        ): self.assertIn(required,text)
        self.assertIn('if /I "%~1"=="adapter-check" goto v08_adapter',text)
        self.assertIn('if /I "%~1"=="adapter-invoke" goto v08_adapter',text)

    def test_17_missing_b2_registry_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bootstrap=Path(temporary)/"bootstrap.json"; bootstrap.write_text(json.dumps({"registry_version":1}),encoding="utf-8")
            with self.assertRaises(AdapterContractError) as caught: adapter.adapter_check(bootstrap_path=bootstrap)
            self.assertEqual(caught.exception.code,ERROR_REGISTRY_MISSING)

    def test_18_no_provider_worker_identity_core_special_case(self) -> None:
        source=(RUNTIME/"v08_adapter.py").read_text(encoding="utf-8").lower()
        for identity in ("fixture-alpha","fixture-beta","chatgpt-web","chatgpt","workbuddy","codex"):
            self.assertNotIn(identity,source)
        self.assertNotIn("if worker_id ==",source); self.assertNotIn("if provider_id ==",source)

    def test_19_no_authority_mutation(self) -> None:
        source=(RUNTIME/"v08_adapter.py").read_text(encoding="utf-8").lower()
        for token in ("grant_authority","revoke_authority","authority_status","set_meta(","crown","promote_milestone"):
            self.assertNotIn(token,source)
        self.assertIs(capsule_for()["metadata"]["authority_grant"],False)

    def test_20_no_effect_authorization(self) -> None:
        source=(RUNTIME/"v08_adapter.py").read_text(encoding="utf-8").lower()
        for token in ("effect_safety_lite","reserve_external_effect","commit_external_effect","effect-wal","effect_wal"):
            self.assertNotIn(token,source)
        self.assertIs(capsule_for()["metadata"]["effect_authorization"],False)

    def test_21_missing_artifact_file_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); capsule=capsule_for()
            result={"artifact_paths":["artifact.txt"],"artifact_hashes":{"artifact.txt":"0"*64}}
            with self.assertRaises(AdapterContractError) as caught: validate_worker_artifacts(result,capsule,root)
            self.assertEqual(caught.exception.code,ERROR_ARTIFACT_INTEGRITY)

    def test_22_extra_undeclared_artifact_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); one=root/"artifact.txt"; extra=root/"extra.txt"
            one.write_text("one",encoding="utf-8"); extra.write_text("extra",encoding="utf-8"); capsule=capsule_for()
            result={"artifact_paths":["artifact.txt","extra.txt"],"artifact_hashes":{"artifact.txt":digest(one),"extra.txt":digest(extra)}}
            with self.assertRaises(AdapterContractError) as caught: validate_worker_artifacts(result,capsule,root)
            self.assertEqual(caught.exception.code,ERROR_ARTIFACT_INTEGRITY)

    def test_23_artifact_forbidden_term_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); artifact=root/"artifact.txt"; artifact.write_text("daemon",encoding="utf-8")
            capsule=capsule_for(); result=result_for(capsule,artifact)
            with self.assertRaises(AdapterContractError) as caught: validate_worker_artifacts(result,capsule,root)
            self.assertEqual(caught.exception.code,ERROR_FORBIDDEN_INTERNAL_TERM)

    def test_24_core_path_rejects_malformed_internal_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            malformed={"contract_version":CONTRACT_VERSION,"result_type":"WORKER_RESULT","status":"DONE",
                "source_binding":{"task_id":"only-one-internal-field"},"artifact_paths":["artifact.txt"],
                "artifact_hashes":{"artifact.txt":"0"*64},"error":None,"notes":"looks valid at top level"}
            completed=SimpleNamespace(returncode=0,stdout=json.dumps(malformed),stderr="")
            with mock.patch.object(adapter.subprocess,"run",return_value=completed):
                with self.assertRaises(AdapterContractError) as caught:
                    adapter.invoke_worker(worker_id="fixture-alpha",task_id="task",context_id="context",objective="probe",
                        workspace=temporary,artifact_declarations=[{"path":"artifact.txt","media_type":"text/plain"}],
                        registry=registry_for("fixture-alpha"))
            self.assertEqual(caught.exception.code,ERROR_MALFORMED_RESULT)

    def test_25_duplicate_json_result_key_rejected(self) -> None:
        duplicate='{"contract_version":"%s","status":"DONE","status":"FAILED"}'%CONTRACT_VERSION
        with self.assertRaises(AdapterContractError) as caught: adapter.strict_json_loads(duplicate)
        self.assertEqual(caught.exception.code,ERROR_MALFORMED_RESULT)

    def test_26_fresh_worker_source_has_no_internal_vocabulary(self) -> None:
        source=FIXTURE.read_text(encoding="utf-8").lower()
        for token in ("bridge","bsk","daemon","marker","yz_lib","52900","chrome-extension","chrome extension","session internals","runtime recovery"):
            self.assertNotIn(token,source)

    def test_27_test_only_binding_timeout_metadata_is_strict(self) -> None:
        reg=registry_for("fixture-alpha"); reg.test_only_execution_bindings["fixture-alpha"]["timeout_seconds"]="twenty"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(AdapterContractError) as caught:
                adapter.invoke_worker(worker_id="fixture-alpha",task_id="t",context_id="c",objective="probe",
                    workspace=temporary,artifact_declarations=[{"path":"artifact.txt","media_type":"text/plain"}],registry=reg)
        self.assertEqual(caught.exception.code,ERROR_WORKER_UNAVAILABLE)

    def test_28_duplicate_registry_json_key_is_registry_invalid(self) -> None:
        duplicate='{"schema":"V08_ADAPTER_REGISTRY","schema":1}'
        with self.assertRaises(AdapterContractError) as caught:
            adapter.strict_json_loads(duplicate,error_code=ERROR_REGISTRY_INVALID,label="adapter registry")
        self.assertEqual(caught.exception.code,ERROR_REGISTRY_INVALID)

    def test_29_bootstrap_pointer_resolves_explicit_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); registry_path=root/"registry.json"
            registry_path.write_text(json.dumps(registry_for("fixture-alpha")),encoding="utf-8")
            bootstrap=root/"bootstrap.json"; bootstrap.write_text(json.dumps({adapter.BOOTSTRAP_REGISTRY_POINTER:"registry.json"}),encoding="utf-8")
            output=adapter.adapter_check(bootstrap_path=bootstrap)
            self.assertEqual(output["status"],"OK"); self.assertEqual(output["worker_count"],1)

    def test_30_malformed_envelopes_reject_unexpected_fields(self) -> None:
        capsule=capsule_for(); capsule["hidden_internal"]="smuggled"
        with self.assertRaises(AdapterContractError) as caught: validate_task_capsule(capsule)
        self.assertEqual(caught.exception.code,ERROR_INVALID_CAPSULE)

    def test_31_artifact_set_binding_is_explicit(self) -> None:
        capsule=capsule_for(); self.assertEqual(len(capsule["artifact_set_id"]),64)
        result={"contract_version":CONTRACT_VERSION,"result_type":"WORKER_RESULT","status":"DONE",
            "source_binding":{"task_id":capsule["task_id"],"invocation_id":capsule["invocation_id"],
                "worker_id":capsule["worker_id"],"context_id":capsule["context_id"],"capsule_id":capsule["capsule_id"],
                "artifact_set_id":"0"*64},
            "artifact_paths":["artifact.txt"],"artifact_hashes":{"artifact.txt":"0"*64},"error":None,"notes":"wrong artifact-set binding"}
        validate_worker_result_envelope(result)
        with self.assertRaises(AdapterContractError) as caught: validate_source_binding(result,capsule)
        self.assertEqual(caught.exception.code,ERROR_SOURCE_BINDING_MISMATCH)

    def test_32_provider_kind_and_test_overlay_network_scope_contract(self) -> None:
        from v08_adapter_contract import NETWORK_SCOPES, ProviderKind
        self.assertEqual(ProviderKind.API_MODEL.value,"API_MODEL"); self.assertIn("NONE",NETWORK_SCOPES)
        reg=registry_for("fixture-alpha"); reg.test_only_execution_bindings["fixture-alpha"]["network_scope"]="UNBOUNDED"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(AdapterContractError) as caught:
                adapter.invoke_worker(worker_id="fixture-alpha",task_id="t",context_id="c",objective="probe",
                    workspace=temporary,artifact_declarations=[{"path":"artifact.txt","media_type":"text/plain"}],registry=reg)
        self.assertEqual(caught.exception.code,ERROR_WORKER_UNAVAILABLE)

    def test_33_empty_registry_is_fail_closed(self) -> None:
        value={"schema":"V08_ADAPTER_REGISTRY","schema_version":1,"registry_generation":1,
            "worker_selection_mode":"SINGLE_ACTIVE_REPLACEMENT","providers":[],"reviewers":[],"workers":[]}
        with self.assertRaises(AdapterContractError) as caught: validate_registry(value)
        self.assertEqual(caught.exception.code,ERROR_REGISTRY_INVALID)

    def test_34_hidden_undeclared_workspace_artifact_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            def fake_run(command,**kwargs):
                capsule=json.loads(kwargs["input"]); artifact=root/"artifact.txt"; hidden=root/"hidden.txt"
                artifact.write_text("declared",encoding="utf-8"); hidden.write_text("undeclared",encoding="utf-8")
                result={"contract_version":CONTRACT_VERSION,"result_type":"WORKER_RESULT","status":"DONE",
                    "source_binding":{"task_id":capsule["task_id"],"invocation_id":capsule["invocation_id"],
                        "worker_id":capsule["worker_id"],"context_id":capsule["context_id"],
                        "capsule_id":capsule["capsule_id"],"artifact_set_id":capsule["artifact_set_id"]},
                    "artifact_paths":["artifact.txt"],"artifact_hashes":{"artifact.txt":digest(artifact)},"error":None,"notes":"attempted hidden output"}
                return SimpleNamespace(returncode=0,stdout=json.dumps(result),stderr="")
            with mock.patch.object(adapter.subprocess,"run",side_effect=fake_run):
                with self.assertRaises(AdapterContractError) as caught:
                    adapter.invoke_worker(worker_id="fixture-alpha",task_id="task",context_id="context",objective="probe",
                        workspace=root,artifact_declarations=[{"path":"artifact.txt","media_type":"text/plain"}],
                        registry=registry_for("fixture-alpha"))
            self.assertEqual(caught.exception.code,ERROR_ARTIFACT_INTEGRITY)

    # D01
    def test_35_d01_missing_digest_map_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); artifact=root/"artifact.txt"; artifact.write_text("hello",encoding="utf-8")
            capsule=capsule_for(); result={"artifact_paths":["artifact.txt"]}
            with self.assertRaises(AdapterContractError) as caught: validate_worker_artifacts(result,capsule,root)
            self.assertEqual(caught.exception.code,ERROR_ARTIFACT_INTEGRITY)

    # D09
    def test_36_d09_duplicate_artifact_path_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); artifact=root/"artifact.txt"; artifact.write_text("hello",encoding="utf-8")
            capsule=capsule_for(); result={"artifact_paths":["artifact.txt","artifact.txt"],"artifact_hashes":{"artifact.txt":digest(artifact)}}
            with self.assertRaises(AdapterContractError) as caught: validate_worker_artifacts(result,capsule,root)
            self.assertEqual(caught.exception.code,ERROR_ARTIFACT_INTEGRITY)

    # F01
    def test_37_f01_web_session_as_api_model_fail_closed(self) -> None:
        value=registry_for("fixture-alpha"); value["workers"][0]["provider_id"]="provider-web"
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(adapter.subprocess,"run",side_effect=AssertionError("worker execution entered")) as run:
                with self.assertRaises(AdapterContractError) as caught:
                    adapter.invoke_worker(worker_id="fixture-alpha",task_id="task-provider-kind",context_id="context-provider-kind",
                        objective="provider kind separation probe",workspace=temporary,
                        artifact_declarations=[{"path":"artifact.txt","media_type":"text/plain"}],registry=value)
            self.assertEqual(caught.exception.code,adapter.ERROR_WORKER_FAILED); self.assertEqual(run.call_count,0)

    # F02
    def test_38_f02_api_model_as_web_session_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(adapter.subprocess,"run",side_effect=AssertionError("worker execution entered")) as run:
                with self.assertRaises(AdapterContractError) as caught:
                    adapter.invoke_worker(worker_id="fixture-alpha",task_id="task-provider-kind",context_id="context-provider-kind",
                        objective="provider kind separation probe",workspace=temporary,
                        artifact_declarations=[{"path":"artifact.txt","media_type":"text/plain"}],
                        registry=registry_for("fixture-alpha"),provider_kind=PROVIDER_KIND_WEB_SESSION)
            self.assertEqual(caught.exception.code,adapter.ERROR_WORKER_FAILED); self.assertEqual(run.call_count,0)

    def test_39_canonical_schema_converges_private_registry_helper(self) -> None:
        reg=registry_for("fixture-alpha")
        self.assertEqual(set(reg),{"schema","schema_version","registry_generation","worker_selection_mode","providers","reviewers","workers"})
        self.assertNotIn("registry_version",reg); self.assertNotIn("adapter_contract_version",reg)
        self.assertNotIn("command",reg["workers"][0]); self.assertIs(validate_registry(reg),reg)

    def test_40_real_bootstrap_adapter_check(self) -> None:
        output=adapter.adapter_check(bootstrap_path=REAL_BOOTSTRAP)
        self.assertEqual(output["status"],"OK")
        self.assertGreater(output["provider_count"],0); self.assertGreater(output["worker_count"],0)
        self.assertEqual(Path(output["registry_path"]).resolve(),REAL_REGISTRY.resolve())

    def test_41_real_b2_registry_parse_and_worker_selection(self) -> None:
        reg=adapter.load_registry(REAL_REGISTRY)
        self.assertEqual(reg["schema"],"V08_ADAPTER_REGISTRY")
        worker=reg["workers"][0]; providers={p["provider_id"]:p for p in reg["providers"]}
        provider=providers[worker["provider_id"]]
        self.assertIn(provider["kind"],(PROVIDER_KIND_API_MODEL,PROVIDER_KIND_WEB_SESSION))
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(AdapterContractError) as caught:
                adapter.invoke_worker(worker_id=worker["worker_id"],task_id="real-select",context_id="real-select",
                    objective="selection only",workspace=temporary,
                    artifact_declarations=[{"path":"artifact.txt","media_type":"text/plain"}],
                    registry=reg,provider_kind=provider["kind"])
        self.assertEqual(caught.exception.code,ERROR_WORKER_UNAVAILABLE)

    def test_42_real_adapter_invoke_contract_uses_test_only_overlay(self) -> None:
        reg=adapter.load_registry(REAL_REGISTRY)
        providers={p["provider_id"]:p for p in reg["providers"]}
        worker=next(w for w in reg["workers"] if providers[w["provider_id"]]["kind"]==PROVIDER_KIND_API_MODEL)
        provider=providers[worker["provider_id"]]
        overlay=execution_binding_for(worker["worker_id"])
        with tempfile.TemporaryDirectory() as temporary:
            out=adapter.invoke_worker(worker_id=worker["worker_id"],task_id="real-invoke",context_id="real-invoke",
                objective="canonical registry integration probe",workspace=temporary,
                artifact_declarations=[{"path":"artifact.txt","media_type":"text/plain"}],
                registry=reg,provider_kind=provider["kind"],test_only_execution_binding=overlay)
            self.assertEqual(out["status"],"DONE")
            self.assertEqual(out["execution_binding_source"],adapter.TEST_ONLY_EXECUTION_BINDING)
            self.assertEqual(out["source_binding"]["worker_id"],worker["worker_id"])
            self.assertEqual(out["artifact_proof"]["artifact_count"],1)

    def test_43_c05_oversized_string_fail_closed(self) -> None:
        capsule=capsule_for(); capsule["objective"]="x"*65536
        with self.assertRaises(AdapterContractError): validate_task_capsule(capsule)

    def test_44_c06_oversized_list_fail_closed(self) -> None:
        capsule=capsule_for(); capsule["metadata"]["capabilities"]=[f"c{i}" for i in range(4096)]
        with self.assertRaises(AdapterContractError): validate_task_capsule(capsule)

if __name__ == "__main__":
    unittest.main(verbosity=2)
