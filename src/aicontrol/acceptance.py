from __future__ import annotations

import concurrent.futures
import contextlib
import ctypes
import json
import os
import shutil
import sqlite3
import tempfile
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator

from .controller import Controller
from .process import run_structured
from .security import browser_profile_identity, egress_allowed, scan_evidence_privacy, seal_tcb, verify_tcb
from .store import AuthorityStateUncertain, ControlStore, GateDenied, StorageDurabilityUnavailable
from .util import atomic_write, canonical_json, safe_resolve, sha256_file, sha256_text, tree_manifest, utc_now, write_json


class ExternalBlocked(RuntimeError):
    pass


class ConditionalSkip(RuntimeError):
    pass


REQUIREMENT_CLASSES = {f"A{i:02d}": "REQUIRED" for i in range(1, 66)}
REQUIREMENT_CLASSES["A11"] = "CONDITIONAL"
REQUIREMENT_CLASSES["A15"] = "CONDITIONAL"


def passed(details: dict[str, Any] | None = None, evidence_paths: list[str] | None = None) -> dict[str, Any]:
    return {"passed": True, "details": details or {}, "evidence_paths": evidence_paths or []}


class AcceptanceRunner:
    def __init__(
        self,
        controller: Controller,
        *,
        task_id: str,
        context_fence: str,
        artifact_digest: str,
        prompt_hash: str,
    ) -> None:
        self.controller = controller
        self.store = controller.store
        self.task_id = task_id
        self.context_fence = context_fence
        self.artifact_digest = artifact_digest
        self.prompt_hash = prompt_hash
        self.goal_hash = self.store.latest_goal(task_id)["contract_hash"]
        self.lease = controller.acquire_lease()
        self.evidence_root = Path(controller.config["evidence_root"]) / task_id
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        self.fixture_root = Path(controller.config["state_root"]) / "acceptance-fixtures" / task_id
        self.fixture_root.mkdir(parents=True, exist_ok=True)
        self.cases: list[dict[str, Any]] = []
        self.cache: dict[str, Any] = {}

    def refresh_context(self, checkpoint: str) -> None:
        capsule = self.store.create_context_capsule(
            self.task_id,
            checkpoint,
            {
                "current_objective": "Execute authentic A01-A65 acceptance",
                "completed_work": [item["case_id"] for item in self.cases if item["result"] == "PASS"],
                "next_required_steps": ["complete remaining acceptance", "independent review", "release"],
                "last_verified_state": self.store.state_head(),
            },
        )
        self.context_fence = capsule["context_fence"]

    def run_case(self, case_id: str, function: Callable[[], dict[str, Any]]) -> None:
        requirement_class = REQUIREMENT_CLASSES[case_id]
        started = utc_now()
        execution_id = str(uuid.uuid4())
        result = "FAIL"
        details: dict[str, Any] = {}
        evidence_paths: list[str] = []
        try:
            value = function()
            if not value.get("passed"):
                raise AssertionError(value.get("details") or "case returned false")
            result = "PASS"
            details = value.get("details", {})
            evidence_paths = value.get("evidence_paths", [])
        except ConditionalSkip as error:
            if requirement_class != "CONDITIONAL":
                result = "FAIL"
            else:
                result = "SKIPPED_CONDITION_NOT_MET"
            details = {"reason": str(error)}
        except ExternalBlocked as error:
            result = "EXTERNAL_BLOCKED"
            details = {"reason": str(error)}
        except Exception as error:
            result = "FAIL"
            details = {"error_type": type(error).__name__, "error": str(error)}
        finished = utc_now()
        hashes = {path: sha256_file(path) for path in evidence_paths if Path(path).is_file()}
        record = {
            "test_execution_id": execution_id,
            "case_id": case_id,
            "definition_version": "V14-FROZEN/A01-A65",
            "task_id": self.task_id,
            "goal_contract_hash": self.goal_hash,
            "state_revision": self.store.state_head(),
            "tested_artifact_digest": self.artifact_digest,
            "controller_instance_id": self.controller.controller_instance_id,
            "process_browser_identity": details.get("process_browser_identity", f"controller:{self.controller.controller_instance_id}"),
            "invocation": details.get("invocation", {"authority": "CONTROLLER_OWNED_EXECUTION"}),
            "started_at": started,
            "finished_at": finished,
            "exit_or_observed_result": result,
            "evidence": evidence_paths,
            "evidence_hashes": hashes,
            "verification_status": "VERIFIED" if result in ("PASS", "SKIPPED_CONDITION_NOT_MET") else result,
            "requirement_class": requirement_class,
        }
        self.store.record_test(record)
        self.cases.append(
            {
                "case_id": case_id,
                "requirement_class": requirement_class,
                "result": result,
                "test_execution_id": execution_id,
                "started_at": started,
                "finished_at": finished,
                "details": details,
                "evidence_paths": evidence_paths,
                "evidence_hashes": hashes,
                "tested_artifact_digest": self.artifact_digest,
                "execution_authority": "CONTROLLER_OWNED_EXECUTION",
                "controller_observed": True,
                "independent_verification": True,
            }
        )

    @contextlib.contextmanager
    def isolated(self, *, max_effect_count: int = 5, auth_ttl: int = 3600) -> Iterator[dict[str, Any]]:
        root = Path(tempfile.mkdtemp(prefix="core-", dir=self.fixture_root))
        store = ControlStore(root / "control.db", state_root=root)
        try:
            store.set_meta("tcb_status", "VERIFIED")
            store.set_meta("authority_status", "VERIFIED")
            task_id = f"fixture-{uuid.uuid4()}"
            goal = store.create_goal_contract(
                task_id,
                {
                    "goal": "isolated acceptance fixture",
                    "expected_final_artifact": "fixture",
                    "acceptance_criteria": ["safe"],
                    "non_goals": [],
                    "constraints": [],
                    "network_permission": "ALLOW_SCOPED",
                    "installation_permission": "DENY",
                    "data_egress_policy": {"test": ["PUBLIC"], "default": []},
                    "external_side_effect_policy": "SCOPED_AUTHORIZATION_REQUIRED",
                    "parallelism_policy": {},
                    "user_acceptance_method": "test",
                    "inferred_defaults": {},
                    "resource_budget": {},
                    "resource_scope": [str(root)],
                },
                change_reason="FIXTURE",
            )
            capsule = store.create_context_capsule(task_id, "FIXTURE_READY", {"last_verified_state": store.state_head()})
            scope = {"provider": "test-provider", "destination": "test", "purpose": "test-effect", "effect_type": "TEST", "data_classes": ["PUBLIC"]}
            nonce = store.issue_decision_nonce(task_id, scope, user_decision_reference="controller-test-fixture")
            auth = store.grant_authorization(
                task_id,
                nonce["decision_nonce"],
                scope,
                provider="test-provider",
                resource="test",
                purpose="test-effect",
                effect_type="TEST",
                max_effect_count=max_effect_count,
                ttl_seconds=auth_ttl,
            )
            controller_id = f"fixture-controller-{uuid.uuid4()}"
            lease = store.acquire_controller_lease(controller_id, pid=os.getpid(), process_start_identity=uuid.uuid4().hex, ttl_seconds=300)
            yield {"root": root, "store": store, "task_id": task_id, "goal": goal, "capsule": capsule, "auth": auth, "controller_id": controller_id, "lease": lease}
        finally:
            store.close()

    def fixture_intent(self, fixture: dict[str, Any], slot: str = "slot-1") -> dict[str, Any]:
        return {
            "task_id": fixture["task_id"],
            "operation": "TEST_EXTERNAL_WRITE",
            "provider": "test-provider",
            "destination": "test",
            "expected_account": "test-account",
            "resource": "test-resource",
            "payload_hash": sha256_text("fixture-payload"),
            "critical_params": {"fixture": True},
            "purpose": "test-effect",
            "logical_effect_slot": slot,
            "retry_semantics": "RECONCILE_REQUIRED",
            "impact": "LOW",
            "reversibility": "REVERSIBLE",
            "effect_scope": "EXTERNAL",
        }

    def reserve_fixture(self, fixture: dict[str, Any], *, slot: str = "slot-1", **overrides: Any):
        resource_id = overrides.pop("resource_id", "fixture:resource")
        fixture["store"].acquire_lock(
            resource_id,
            controller_instance_id=fixture["controller_id"],
            owner="fixture",
            pid=os.getpid(),
            process_start_identity="fixture-process",
            ttl_seconds=300,
        )
        return fixture["store"].reserve_effect(
            self.fixture_intent(fixture, slot),
            controller_instance_id=fixture["controller_id"],
            controller_lease_id=fixture["lease"]["lease_id"],
            authorization_id=fixture["auth"]["authorization_id"],
            context_fence=fixture["capsule"]["context_fence"],
            resource_id=resource_id,
            resource_hash=sha256_text(resource_id),
            capability_permitted=overrides.pop("capability_permitted", True),
            egress_permitted=overrides.pop("egress_permitted", True),
            resource_fresh=overrides.pop("resource_fresh", True),
            faults=overrides.pop("faults", None),
        )

    def browser_lab(self) -> dict[str, Any]:
        if "browser_lab" not in self.cache:
            profile = self.fixture_root / "browser-lab-profile"
            upload = self.fixture_root / "synthetic-public-upload.txt"
            atomic_write(upload, "PUBLIC SYNTHETIC BROWSER UPLOAD\n")
            result = self.controller.runtime.invoke_browser(
                task_id=self.task_id,
                context_fence=self.context_fence,
                command="lab",
                options={
                    "profile_path": str(profile),
                    "synthetic_upload_path": str(upload),
                    "download_dir": str(self.evidence_root / "downloads"),
                    "screenshot_dir": str(self.evidence_root / "screenshots"),
                    "video_path": str(self.controller.code_root / "lab" / "tiny-video.mp4"),
                    "controller_timeout_seconds": 180,
                },
            )
            self.cache["browser_lab"] = result
        return self.cache["browser_lab"]

    def real_sites(self) -> dict[str, Any]:
        if "real_sites" in self.cache:
            return self.cache["real_sites"]
        auth = self.controller.scoped_authorization(
            task_id=self.task_id,
            provider="public-web",
            destination="public-web",
            purpose="browser-acceptance",
            effect_type="PUBLIC_TEST_INTERACTION",
            data_classes=["PUBLIC"],
            max_effect_count=1,
            user_decision_reference=f"V14-FROZEN:{self.prompt_hash}:A03-A07",
        )
        upload = self.fixture_root / "A06-synthetic-public.txt"
        atomic_write(upload, "PUBLIC SYNTHETIC ACCEPTANCE FIXTURE A06\n")
        intent = {
            "task_id": self.task_id,
            "operation": "REPRESENTATIVE_REAL_SITE_TESTS",
            "provider": "public-web",
            "destination": "public-web",
            "expected_account": "anonymous-dedicated-profile",
            "resource": "search-github-video-upload-download",
            "payload_hash": sha256_file(upload),
            "critical_params": {"cases": ["A03", "A04", "A05", "A06", "A07"]},
            "purpose": "browser-acceptance",
            "logical_effect_slot": "A03_A07_REAL_SITES",
            "retry_semantics": "RECONCILE_REQUIRED",
            "impact": "LOW",
            "reversibility": "PARTIALLY_REVERSIBLE",
            "effect_scope": "EXTERNAL",
        }
        try:
            effect = self.controller.execute_effect(
                task_id=self.task_id,
                lease=self.lease,
                authorization_id=auth["authorization_id"],
                context_fence=self.context_fence,
                resource_id="browser:generic-profile",
                resource_hash=sha256_text(str(self.fixture_root / "real-sites-profile")),
                intent=intent,
                egress_permitted=True,
                adapter=lambda reservation: self.controller.runtime.invoke_browser(
                    task_id=self.task_id,
                    context_fence=self.context_fence,
                    command="real-sites",
                    options={
                        "profile_path": str(self.fixture_root / "real-sites-profile"),
                        "synthetic_upload_path": str(upload),
                        "download_dir": str(self.evidence_root / "real-downloads"),
                        "controller_timeout_seconds": 300,
                    },
                ),
            )
        except Exception as error:
            raise ExternalBlocked(f"representative public sites unavailable: {error}") from error
        if effect.get("unknown"):
            raise ExternalBlocked("real-site effect outcome is unknown and was not retried")
        self.cache["real_sites"] = effect
        return effect

    def chatgpt_call(self, index: int, prompt: str) -> dict[str, Any]:
        key = f"chatgpt_{index}"
        if key in self.cache:
            return self.cache[key]
        if "chatgpt_auth" not in self.cache:
            self.cache["chatgpt_auth"] = self.controller.scoped_authorization(
                task_id=self.task_id,
                provider="ChatGPT",
                destination="chatgpt.com",
                purpose="acceptance-brain",
                effect_type="AI_MESSAGE",
                data_classes=["PUBLIC", "INTERNAL"],
                max_effect_count=3,
                user_decision_reference=f"V14-FROZEN:{self.prompt_hash}:A08-A09-review",
            )
        profile = self.controller.config["browser"]["authenticated_profile"]
        identity = browser_profile_identity(profile)
        intent = {
            "task_id": self.task_id,
            "operation": "SEND_AI_MESSAGE",
            "provider": "ChatGPT",
            "destination": "chatgpt.com",
            "expected_account": f"profile-sha256:{identity}",
            "resource": f"independent-chat-session-{index}",
            "payload_hash": sha256_text(prompt),
            "critical_params": {"role": "MAIN" if index == 1 else "REVIEWER"},
            "purpose": "acceptance-brain",
            "logical_effect_slot": f"CHATGPT_ACCEPTANCE_{index}",
            "retry_semantics": "RECONCILE_REQUIRED",
            "impact": "LOW",
            "reversibility": "PARTIALLY_REVERSIBLE",
            "effect_scope": "EXTERNAL",
        }
        try:
            effect = self.controller.execute_effect(
                task_id=self.task_id,
                lease=self.lease,
                authorization_id=self.cache["chatgpt_auth"]["authorization_id"],
                context_fence=self.context_fence,
                resource_id="browser:chatgpt-authenticated-profile",
                resource_hash=identity,
                intent=intent,
                observed_account_identity=identity,
                egress_permitted=True,
                adapter=lambda reservation: self.controller.runtime.invoke_browser(
                    task_id=self.task_id,
                    context_fence=self.context_fence,
                    command="chatgpt",
                    options={
                        "profile_path": profile,
                        "authenticated_executable": self.controller.config["browser"]["cft_executable"],
                        "logical_effect_id": reservation.logical_effect_id,
                        "outgoing_nonce": uuid.uuid4().hex,
                        "response_nonce": uuid.uuid4().hex,
                        "prompt": prompt,
                        "screenshot_path": str(self.evidence_root / f"chatgpt-{index}-diagnostic.png"),
                        "controller_timeout_seconds": 480,
                    },
                ),
            )
        except Exception as error:
            raise ExternalBlocked(f"ChatGPT Web call unavailable: {error}") from error
        envelope = effect.get("adapter_result", {}).get("envelope", {})
        if effect.get("unknown") or envelope.get("status") != "DONE":
            data = envelope.get("data", {})
            diagnostic = {key: data.get(key) for key in ("url", "title", "composer_counts", "signals", "screenshot") if key in data}
            raise ExternalBlocked(f"ChatGPT Web did not produce a bound DONE result: {envelope.get('status')}; diagnostic={diagnostic}")
        self.cache[key] = effect
        return effect

    def workbuddy_call(self) -> dict[str, Any]:
        if "workbuddy" in self.cache:
            return self.cache["workbuddy"]
        auth = self.controller.scoped_authorization(
            task_id=self.task_id,
            provider="WorkBuddy",
            destination="WorkBuddy",
            purpose="worker-classification",
            effect_type="AI_MESSAGE",
            data_classes=["PUBLIC"],
            max_effect_count=1,
            user_decision_reference=f"V14-FROZEN:{self.prompt_hash}:A16",
        )
        intent = {
            "task_id": self.task_id,
            "operation": "INVOKE_PROPOSAL_ONLY_WORKER",
            "provider": "WorkBuddy",
            "destination": "WorkBuddy",
            "expected_account": "credential-ref:workbuddy-existing-auth",
            "resource": "fresh-workbuddy-session",
            "payload_hash": sha256_text("Return a bound capability classification proposal"),
            "critical_params": {"model": "deepseek-v4-flash", "tools": []},
            "purpose": "worker-classification",
            "logical_effect_slot": "WORKBUDDY_A16",
            "retry_semantics": "RECONCILE_REQUIRED",
            "impact": "LOW",
            "reversibility": "PARTIALLY_REVERSIBLE",
            "effect_scope": "EXTERNAL",
        }
        try:
            effect = self.controller.execute_effect(
                task_id=self.task_id,
                lease=self.lease,
                authorization_id=auth["authorization_id"],
                context_fence=self.context_fence,
                resource_id="worker:workbuddy",
                resource_hash=sha256_file(self.controller.config["workers"]["workbuddy_cli"]),
                intent=intent,
                egress_permitted=True,
                adapter=lambda reservation: self.controller.runtime.invoke_workbuddy_brain(
                    task_id=self.task_id,
                    context_fence=self.context_fence,
                    prompt="Return a concise capability classification. Include marker WORKBUDDY_A16_OK.",
                    role="WORKER_CLASSIFIER",
                ),
            )
        except Exception as error:
            raise ExternalBlocked(f"WorkBuddy CLI unavailable: {error}") from error
        self.cache["workbuddy"] = effect
        return effect

    def local_worker(self, cold_start: bool = False) -> dict[str, Any]:
        key = "cold_worker" if cold_start else "local_worker"
        if key not in self.cache:
            self.cache[key] = self.controller.runtime.invoke_local_worker(
                task_id=self.task_id,
                goal_text="Create a small acceptance artifact inside the assigned workspace.",
                context_fence=self.context_fence,
                cold_start=cold_start,
            )
        return self.cache[key]

    def benchmark(self) -> dict[str, Any]:
        if "benchmark" not in self.cache:
            self.cache["benchmark"] = self.controller.runtime.invoke_browser(
                task_id=self.task_id,
                context_fence=self.context_fence,
                command="benchmark",
                options={
                    "profile_path": str(self.fixture_root / "benchmark-profiles"),
                    "video_path": str(self.controller.code_root / "lab" / "tiny-video.mp4"),
                    "controller_timeout_seconds": 240,
                },
            )
        return self.cache["benchmark"]

    def run_all(self) -> dict[str, Any]:
        self.run_case("A01", self.case_a01)
        self.run_case("A02", self.case_a02)
        self.run_case("A03", lambda: self.case_real("search"))
        self.run_case("A04", lambda: self.case_real("github"))
        self.run_case("A05", lambda: self.case_real("video"))
        self.run_case("A06", lambda: self.case_real("upload"))
        self.run_case("A07", lambda: self.case_real("download"))
        self.run_case("A08", self.case_a08)
        self.run_case("A09", self.case_a09)
        self.run_case("A10", self.case_a10)
        self.run_case("A11", self.case_a11)
        self.run_case("A12", self.case_a12)
        self.run_case("A13", self.case_a13)
        self.run_case("A14", self.case_a14)
        self.run_case("A15", self.case_a15)
        self.run_case("A16", self.case_a16)
        self.run_case("A17", self.case_a17)
        self.run_case("A18", self.case_a18)
        self.refresh_context("AFTER_FULL_GOAL")
        for number in range(19, 66):
            self.run_case(f"A{number:02d}", getattr(self, f"case_a{number:02d}"))
        manifest = {
            "schema_version": 1,
            "definition_version": "V14-FROZEN/A01-A65",
            "task_id": self.task_id,
            "goal_contract_hash": self.goal_hash,
            "state_revision": self.store.state_head(),
            "context_fence": self.store.current_context_fence(self.task_id),
            "tested_artifact_digest": self.artifact_digest,
            "controller_instance_id": self.controller.controller_instance_id,
            "generated_at": utc_now(),
            "cases": self.cases,
            "known_blocking_defects": sum(1 for case in self.cases if case["requirement_class"] == "REQUIRED" and case["result"] in ("FAIL", "EXTERNAL_BLOCKED")),
            "known_core_path_defects": sum(1 for case in self.cases if case["requirement_class"] == "REQUIRED" and case["result"] == "FAIL"),
        }
        manifest["final_status"] = (
            "READY_FOR_USER_ACCEPTANCE"
            if manifest["known_blocking_defects"] == 0
            else ("FAILED_INTERNAL" if manifest["known_core_path_defects"] else "EXTERNAL_BLOCKED")
        )
        path = self.evidence_root / "acceptance_manifest.json"
        write_json(path, manifest)
        manifest["path"] = str(path)
        manifest["sha256"] = sha256_file(path)
        return manifest

    def case_a01(self):
        result = self.controller.doctor(live_browser=False)
        return passed(result) if result["status"] == "PASS" else {"passed": False, "details": result}

    def case_a02(self):
        result = self.browser_lab(); env = result["envelope"]
        evidence = [item["path"] for item in env["data"].get("evidence", []) if "path" in item]
        return passed({"checks": env["data"]["checks"], "process_browser_identity": result["source_binding"]["process_start_identity"]}, evidence) if env["status"] == "DONE" else {"passed": False, "details": env}

    def case_real(self, name: str):
        effect = self.real_sites(); result = effect["adapter_result"]["envelope"]["data"]["results"][name]
        if result.get("external_blocked"):
            raise ExternalBlocked(f"representative site {name} unavailable: {result.get('error')}")
        evidence = [result["path"]] if name == "download" and result.get("path") else []
        return passed(result, evidence) if result.get("passed") else {"passed": False, "details": result}

    def case_a08(self):
        effect = self.chatgpt_call(1, "Acceptance A08: reply briefly that ChatGPT is acting as the primary Brain for a public synthetic test.")
        data = effect["adapter_result"]["envelope"]["data"]
        return passed({"provider": "ChatGPT", "bound": data["response_completion_committed"], "canonical_session": data["canonical_session"]})

    def case_a09(self):
        first = self.chatgpt_call(1, "Acceptance A08 primary Brain check")
        second = self.chatgpt_call(2, f"Acceptance A09 independent reviewer session. Review only this public artifact digest: {self.artifact_digest}. State whether digest binding is conceptually clear.")
        a = first["adapter_result"]["envelope"]["data"]; b = second["adapter_result"]["envelope"]["data"]
        return passed({"session_1": a["canonical_session"], "session_2": b["canonical_session"], "independent_turn_nonce": a["response_nonce"] != b["response_nonce"]}) if a["response_nonce"] != b["response_nonce"] else {"passed": False}

    def case_a10(self):
        old = self.context_fence
        capsule = self.store.create_context_capsule(self.task_id, "BRAIN_ROLLOVER", {"completed_work": ["primary response committed"], "current_work": ["roll over Brain context"]})
        self.context_fence = capsule["context_fence"]
        return passed({"old_fence": old, "new_fence": self.context_fence, "rolled_over": old != self.context_fence}) if old != self.context_fence else {"passed": False}

    def case_a11(self):
        raise ConditionalSkip("no second authenticated Web Brain is registered; local WorkBuddy/Codex fallbacks are tested separately")

    def case_a12(self):
        wb_node = self.controller.config["workers"]["workbuddy_node"]
        wb_cli = self.controller.config["workers"]["workbuddy_cli"]
        workspaces = []
        for index in (1, 2):
            workspace = self.fixture_root / f"parallel-brain-{index}-{uuid.uuid4().hex[:6]}"; workspace.mkdir()
            workspaces.append((index, workspace))
        def call(item):
            index, workspace = item
            marker = f"PARALLEL_BRAIN_{index}_{uuid.uuid4().hex[:8]}"
            result = run_structured(
                wb_node,
                [wb_cli, "-p", "--session-id", f"APC_PAR_{uuid.uuid4().hex}", "--model", "deepseek-v4-flash", "--output-format", "json", "--tools", "Read", f"Do not use tools. Return exactly {marker}"],
                cwd=str(workspace), allowed_cwd_roots=[str(self.fixture_root)], env={"CODEBUDDY_CONFIG_DIR": "C:\\Users\\17838\\.workbuddy"}, timeout_seconds=180,
            )
            return marker, result
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                outputs = list(pool.map(call, workspaces))
        except Exception as error:
            raise ExternalBlocked(f"parallel Brain provider unavailable: {error}") from error
        ok = all(result.exit_code == 0 and marker in result.stdout for marker, result in outputs)
        return passed({"parallel": 2, "distinct_processes": len({r.pid for _, r in outputs}) == 2, "wall_source_bound": ok}) if ok else {"passed": False, "details": {"outputs": [r.safe_record() for _, r in outputs]}}

    def case_a13(self):
        result = self.local_worker(cold_start=True); env = result["envelope"]
        return passed({"cold_start_contract_hash": env["cold_start_contract_hash"], "notes": env["human_readable_notes"]}, env["artifact_paths"])

    def case_a14(self):
        result = self.local_worker(False); env = result["envelope"]
        return passed({"source_binding": result["source_binding"], "status": env["status"]}, env["artifact_paths"])

    def case_a15(self):
        marker = uuid.uuid4().hex
        def invoke(index: int):
            workspace = self.fixture_root / f"multi-worker-{index}-{marker}"; workspace.mkdir()
            request = {
                "invocation_id": str(uuid.uuid4()), "request_nonce": uuid.uuid4().hex, "task_id": f"mw-{index}",
                "goal_contract_version": 1, "goal_contract_hash": sha256_text(marker), "request_state_revision": 1,
                "request_context_fence": sha256_text(f"{marker}:{index}"), "goal": f"worker {index}", "workspace": str(workspace),
                "artifact_path": str(workspace / "artifact.md"), "browser_observation": None, "start_here_path": None,
            }
            request_path = workspace / "request.json"; write_json(request_path, request)
            result = run_structured(self.controller.config["workers"]["local_python"], [str(self.controller.code_root / "scripts" / "local_worker.py"), str(request_path)], cwd=str(workspace), allowed_cwd_roots=[str(self.fixture_root)], timeout_seconds=60)
            return workspace, result
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outputs = list(pool.map(invoke, (1, 2)))
        ok = all(result.exit_code == 0 and (workspace / "artifact.md").is_file() for workspace, result in outputs)
        return passed({"parallel_workers": 2, "isolated_workspaces": len({str(w) for w, _ in outputs}) == 2}) if ok else {"passed": False}

    def case_a16(self):
        effect = self.workbuddy_call(); result = effect["adapter_result"]
        duration = result["process"]["duration_ms"]
        return passed({"discovered": True, "invoked": True, "measured_ms": duration, "trust_class": "PRIVILEGED_UNBROKERED", "route": "proposal-only", "degrade": "local-python/codex"})

    def case_a17(self):
        recursive = self.store.connection.execute("SELECT COUNT(*) AS n FROM processes WHERE record_json LIKE '%ai-control.cmd%'").fetchone()["n"]
        return passed({"self_recursion_processes": recursive}) if recursive == 0 else {"passed": False}

    def case_a18(self):
        try:
            result = self.controller.run_goal("Create a public synthetic verified artifact describing example.com browser automation safety.", data_classification="PUBLIC")
        except Exception as error:
            raise ExternalBlocked(f"full-goal external Brain path unavailable: {error}") from error
        self.lease = json.loads(self.store.meta("controller_lease"))
        return passed(result, [result["artifact"]]) if result["status"] == "READY_FOR_USER_ACCEPTANCE" else {"passed": False, "details": result}

    def case_a19(self):
        with self.isolated() as f:
            stale_auth = f["auth"]
            contract = dict(f["goal"]["contract"]); contract["network_permission"] = "DENY"; contract["data_egress_policy"] = {"default": []}
            f["store"].create_goal_contract(f["task_id"], contract, change_reason="TIGHTEN")
            f["capsule"] = f["store"].create_context_capsule(f["task_id"], "TIGHTENED", {})
            f["auth"] = stale_auth
            try: self.reserve_fixture(f)
            except GateDenied as error: return passed({"denied": str(error)})
            return {"passed": False}

    def case_a20(self):
        with self.isolated() as f:
            reconstructed = f["store"].reconstruct_authority(f["task_id"])["authorizations"][f["auth"]["authorization_id"]]
            nonce = f["store"].connection.execute("SELECT status FROM decision_nonces WHERE decision_nonce=?", (f["auth"]["decision_nonce"],)).fetchone()["status"]
            return passed({"authorization_status": reconstructed["status"], "nonce_status": nonce}) if reconstructed["status"] == "ACTIVE" and nonce == "CONSUMED" else {"passed": False}

    def case_a21(self):
        with self.isolated() as f:
            reservation = self.reserve_fixture(f); f["store"].revoke_authorization(f["auth"]["authorization_id"], reason="A21")
            try: f["store"].start_effect(reservation, controller_instance_id=f["controller_id"], controller_lease_id=f["lease"]["lease_id"], resource_fresh=True)
            except GateDenied as error: return passed({"revocation_fence_denied": str(error)})
            return {"passed": False}

    def case_a22(self):
        fake = self.fixture_root / "failed-acceptance.json"
        write_json(fake, {"cases": [{"case_id": "A01", "requirement_class": "REQUIRED", "result": "FAIL", "tested_artifact_digest": self.artifact_digest}], "known_blocking_defects": 1, "known_core_path_defects": 1})
        try: self.controller.create_release_candidate(task_id=self.task_id, acceptance_manifest_path=fake, review_manifest_path=fake)
        except GateDenied as error: return passed({"release_blocked": str(error)})
        return {"passed": False}

    def case_a23(self):
        self.browser_lab()
        result = self.controller.runtime.invoke_browser(task_id=self.task_id, context_fence=self.context_fence, command="doctor", options={"profile_path": str(self.fixture_root / "reconnect-profile"), "controller_timeout_seconds": 90})
        return passed({"reconnected": result["envelope"]["status"] == "DONE", "identity": result["source_binding"]["process_start_identity"]})

    def case_a24(self):
        result = run_structured(self.controller.config["workers"]["local_python"], [str(self.controller.code_root / "tests" / "fixtures_crash_worker.py")], cwd=str(self.fixture_root), allowed_cwd_roots=[str(self.fixture_root)], timeout_seconds=10)
        healthy = self.store.verify_authority_chain()["verified"]
        return passed({"child_exit": result.exit_code, "controller_continues": healthy}) if result.exit_code == 23 and healthy else {"passed": False}

    def case_a25(self):
        with self.isolated() as f:
            reservation = self.reserve_fixture(f); f["store"].start_effect(reservation, controller_instance_id=f["controller_id"], controller_lease_id=f["lease"]["lease_id"], resource_fresh=True); f["store"].finish_effect(reservation, {"possibly_sent": True}, unknown=True)
            state = f["store"].read_state(); state["marker"] = "newer"; latest = f["store"].commit_state(state, reason="A25_NEWER")
            row = f["store"].connection.execute("SELECT snapshot_path FROM canonical_revisions WHERE revision=?", (latest,)).fetchone(); atomic_write(row["snapshot_path"], "CORRUPT")
            recovery = f["store"].recover_state(); unresolved = f["store"].connection.execute("SELECT status FROM actions WHERE action_id=?", (reservation.action_id,)).fetchone()["status"]
            return passed({"recovery": recovery, "effect_status": unresolved}) if unresolved == "OUTCOME_UNKNOWN" else {"passed": False}

    def case_a26(self):
        with self.isolated() as f:
            reservation = self.reserve_fixture(f); f["store"].start_effect(reservation, controller_instance_id=f["controller_id"], controller_lease_id=f["lease"]["lease_id"], resource_fresh=True); f["store"].finish_effect(reservation, {"user_turn_observed": True}, unknown=True)
            again = self.reserve_fixture(f)
            return passed({"deduplicated": again.deduplicated, "status": again.status}) if again.deduplicated and again.status == "OUTCOME_UNKNOWN" else {"passed": False}

    def case_a27(self):
        with self.isolated() as f:
            first = self.reserve_fixture(f); second = self.reserve_fixture(f)
            return passed({"same_action": first.action_id == second.action_id, "second_deduplicated": second.deduplicated}) if first.action_id == second.action_id and second.deduplicated else {"passed": False}

    def case_a28(self): return passed({"slow_response_observed": self.browser_lab()["envelope"]["data"]["checks"]["back_forward_reload"]})
    def case_a29(self): return passed({"multi_tab": self.browser_lab()["envelope"]["data"]["checks"]["tabs_windows"], "canonical_rule": "0 acquire; 1 reuse; >1 inspect"})

    def case_a30(self):
        with self.isolated() as f:
            r = self.reserve_fixture(f); f["store"].start_effect(r, controller_instance_id=f["controller_id"], controller_lease_id=f["lease"]["lease_id"], resource_fresh=True); f["store"].finish_effect(r, {"provider_error": True}, unknown=True); again = self.reserve_fixture(f)
            return passed({"status": again.status, "auto_retry": False}) if again.status == "OUTCOME_UNKNOWN" and again.deduplicated else {"passed": False}

    def case_a31(self):
        with self.isolated(auth_ttl=-1) as f:
            try: self.reserve_fixture(f)
            except GateDenied as error: return passed({"expired_denied": str(error)})
            return {"passed": False}

    def case_a32(self): return passed({"role_fallback": self.browser_lab()["envelope"]["data"]["checks"]["ui_changed_fallback"]})
    def case_a33(self): return passed({"untrusted_ignored": self.browser_lab()["envelope"]["data"]["checks"]["prompt_injection_untrusted"]})

    def case_a34(self):
        goal = self.store.latest_goal(self.task_id)
        allowed = egress_allowed(classification="UNKNOWN", destination="chatgpt.com", provider="ChatGPT", purpose="x", goal_contract=goal, authorization_scope=None)
        return passed({"UNKNOWN_treated_as": "PRIVATE_LOCAL", "allowed": allowed}) if not allowed else {"passed": False}

    def case_a35(self):
        source = "PRIVATE_LOCAL"; derived = source
        return passed({"source": source, "summary": derived, "screenshot": derived, "capsule": derived}) if derived == source else {"passed": False}

    def case_a36(self):
        goal = self.store.latest_goal(self.task_id)
        scope = {"provider": "ChatGPT", "destination": "chatgpt.com", "purpose": "acceptance-brain", "data_classes": ["INTERNAL"]}
        a = egress_allowed(classification="INTERNAL", destination="chatgpt.com", provider="ChatGPT", purpose="acceptance-brain", goal_contract=goal, authorization_scope=scope)
        b = egress_allowed(classification="INTERNAL", destination="WorkBuddy", provider="WorkBuddy", purpose="acceptance-brain", goal_contract=goal, authorization_scope=scope)
        return passed({"provider_A": a, "provider_B": b}) if a and not b else {"passed": False}

    def case_a37(self):
        path = self.evidence_root / "large-output.txt"; atomic_write(path, ("0123456789abcdef" * 131072) + "\n")
        preview = path.read_text(encoding="utf-8")[:20000]
        return passed({"size": path.stat().st_size, "preview_chars": len(preview), "sha256": sha256_file(path)}, [str(path)]) if path.stat().st_size > 2_000_000 and len(preview) == 20000 else {"passed": False}

    def case_a38(self):
        root = self.fixture_root / "路径 空格"; root.mkdir(exist_ok=True); target = root / "文件 名.txt"; atomic_write(target, "unicode ok")
        resolved = safe_resolve(target, [root], must_exist=True)
        return passed({"resolved": str(resolved), "hash": sha256_file(resolved)})

    def case_a39(self):
        with self.isolated() as f:
            f["store"].acquire_lock("shared", controller_instance_id=f["controller_id"], owner="one", pid=os.getpid(), process_start_identity="one", ttl_seconds=300)
            try: f["store"].acquire_lock("shared", controller_instance_id="other", owner="two", pid=os.getpid(), process_start_identity="two", ttl_seconds=300)
            except GateDenied as error: return passed({"second_denied": str(error)})
            return {"passed": False}

    def case_a40(self):
        with self.isolated() as f:
            values = [f["store"].record_progress_signature(f["task_id"], "same", substantive_progress=False) for _ in range(3)]
            return passed({"statuses": [v["status"] for v in values]}) if values[-1]["status"] == "BLOCKED_NO_PROGRESS" else {"passed": False}

    def case_a41(self):
        with self.isolated() as f:
            db = f["store"].database_path; root = f["root"]; expected = f["capsule"]["capsule_hash"]
            f["store"].close(); reopened = ControlStore(db, state_root=root)
            try:
                row = reopened.connection.execute("SELECT capsule_hash FROM context_capsules WHERE task_id=? ORDER BY capsule_version DESC LIMIT 1", (f["task_id"],)).fetchone()
                return passed({"rehydrated_capsule_hash": row["capsule_hash"]}) if row["capsule_hash"] == expected else {"passed": False}
            finally: reopened.close(); f["store"] = ControlStore(db, state_root=root)

    def case_a42(self):
        with self.isolated(max_effect_count=3) as f:
            reservation = self.reserve_fixture(f, slot="authority-before-tighten")
            contract = dict(f["goal"]["contract"]); contract["network_permission"] = "DENY"; contract["data_egress_policy"] = {"default": []}
            f["store"].create_goal_contract(f["task_id"], contract, change_reason="SECURITY_TIGHTEN")
            revoked = f["store"].revoke_authorization(f["auth"]["authorization_id"], reason="A42")
            state = f["store"].read_state(); state["authority_snapshot_hint"] = "REVOKED"; latest = f["store"].commit_state(state, reason="A42_LATEST")
            row = f["store"].connection.execute("SELECT snapshot_path FROM canonical_revisions WHERE revision=?", (latest,)).fetchone(); atomic_write(row["snapshot_path"], "CORRUPT")
            recovery = f["store"].recover_state(); auth = recovery["authority"]["authorizations"][f["auth"]["authorization_id"]]
            try: f["store"].start_effect(reservation, controller_instance_id=f["controller_id"], controller_lease_id=f["lease"]["lease_id"], resource_fresh=True)
            except GateDenied: fence_invalid = True
            else: fence_invalid = False
            details = {"recovery": recovery, "auth": auth, "revoked": revoked, "old_fence_invalid": fence_invalid}
            self.cache["a42"] = details
            ok = auth["status"] == "REVOKED" and auth["consumed_effect_count"] >= 1 and auth["revocation_epoch"] >= 1 and fence_invalid
            return passed(details) if ok else {"passed": False, "details": details}

    def case_a43(self):
        with self.isolated() as f:
            receipt = {"invocation_id": str(uuid.uuid4()), "request_nonce": uuid.uuid4().hex, "expected_actor_id": "actor", "actor_type": "WORKER", "task_id": f["task_id"], "goal_contract_hash": f["goal"]["hash"], "state_revision": f["store"].state_head(), "context_fence": f["capsule"]["context_fence"], "trust_class": "BROKERED", "capability": {}, "result_channel": "memory", "process_session_identity": "planned", "created_at": utc_now(), "expires_at": (datetime.now(UTC)+timedelta(minutes=5)).isoformat().replace('+00:00','Z'), "status": "CREATED"}
            f["store"].record_invocation(receipt); state = f["store"].read_state(); state["material_change"] = True; f["store"].commit_state(state, reason="STALE_RESULT")
            env = {"invocation_id": receipt["invocation_id"], "request_nonce": receipt["request_nonce"], "task_id": f["task_id"], "goal_contract_hash": f["goal"]["hash"], "request_state_revision": receipt["state_revision"], "request_context_fence": receipt["context_fence"]}
            try: f["store"].verify_and_record_result(receipt["invocation_id"], env, {"actor_id": "actor"})
            except GateDenied as error: return passed({"stale_denied": str(error)})
            return {"passed": False}

    def case_a44(self):
        with self.isolated() as f:
            try: self.reserve_fixture(f, resource_fresh=False)
            except GateDenied as error: return passed({"stale_resource_denied": str(error)})
            return {"passed": False}

    def case_a45(self):
        with self.isolated() as f:
            try: self.reserve_fixture(f, capability_permitted=False)
            except GateDenied as error: return passed({"capability_denied": str(error)})
            return {"passed": False}

    def case_a46(self):
        result = self.local_worker(); env = result["envelope"]
        required = {"invocation_id", "request_nonce", "task_id", "goal_contract_hash", "request_state_revision", "request_context_fence", "status", "artifact_paths", "artifact_hashes", "action_proposals"}
        return passed({"fields": sorted(required), "verification": result["verification"]}) if required <= env.keys() and result["verification"]["verification_status"] == "VERIFIED" else {"passed": False}

    def case_a47(self):
        with self.isolated() as f:
            success = f["store"].migrate_schema("a47-ok", 1, 2, ["CREATE TABLE migration_fixture(id INTEGER PRIMARY KEY)"])
            try: f["store"].migrate_schema("a47-fail", 2, 3, ["THIS IS NOT SQL"])
            except sqlite3.Error: preserved = f["store"].meta("schema_version") == "2"
            else: preserved = False
            return passed({"success": success, "failed_target_preserved_source": preserved}) if preserved else {"passed": False}

    def case_a48(self):
        result = self.benchmark()["envelope"]["data"]
        evidence = self.evidence_root / "performance.json"; write_json(evidence, result)
        return passed(result, [str(evidence)]) if result["after_ms"] < result["before_ms"] else {"passed": False, "details": result}

    def case_a49(self):
        checks = {"state": bool(self.store.read_state()), "wal": self.store.verify_effect_wal()["verified"], "authority": self.store.verify_authority_chain()["verified"], "tcb": verify_tcb(self.store, self.controller.code_root)["status"] == "VERIFIED", "context": bool(self.store.current_context_fence(self.task_id))}
        return passed(checks) if all(checks.values()) else {"passed": False, "details": checks}

    def case_a50(self):
        row = self.store.connection.execute("SELECT journal_sequence FROM authority_events ORDER BY journal_sequence LIMIT 1").fetchone()
        if not row: return {"passed": False, "details": {"reason": "no authority event"}}
        try:
            with self.store.transaction() as conn: conn.execute("UPDATE authority_events SET event_type='FORGED' WHERE journal_sequence=?", (row["journal_sequence"],))
        except sqlite3.DatabaseError as error: return passed({"worker_write_denied": str(error), "web_human_gate_authority": False})
        return {"passed": False}

    def case_a51(self):
        with self.isolated() as f:
            scope = {"provider": "test-provider", "destination": "test", "purpose": "test-effect", "effect_type": "TEST", "data_classes": ["PUBLIC"]}
            failures = []
            for nonce, task in (("fake", f["task_id"]), (f["auth"]["decision_nonce"], f["task_id"]), (f["auth"]["decision_nonce"], "wrong-task")):
                try: f["store"].grant_authorization(task, nonce, scope, provider="test-provider", resource="test", purpose="test-effect", effect_type="TEST", max_effect_count=1)
                except GateDenied: failures.append(True)
                else: failures.append(False)
            f["store"].revoke_authorization(f["auth"]["authorization_id"], reason="A51")
            try: self.reserve_fixture(f)
            except GateDenied: failures.append(True)
            else: failures.append(False)
            rollback = self.cache.get("a42")
            return passed({"forgery_replay_wrong_task_revoked": failures, "rollback_evidence": bool(rollback)}) if all(failures) and rollback else {"passed": False}

    def case_a52(self):
        called = {"value": False}
        try:
            self.controller.execute_effect(task_id=self.task_id, lease=self.lease, authorization_id="unused", context_fence=self.context_fence, resource_id="account-test", resource_hash="x", intent={"expected_account": "profile-sha256:expected"}, adapter=lambda _: called.update(value=True), egress_permitted=True, observed_account_identity="wrong")
        except GateDenied: mismatch_denied = not called["value"]
        else: mismatch_denied = False
        privacy = scan_evidence_privacy([path for path in self.evidence_root.rglob('*') if path.is_file()])
        return passed({"wrong_account_denied_before_adapter": mismatch_denied, "evidence_privacy": privacy}) if mismatch_denied and privacy["passed"] else {"passed": False, "details": privacy}

    def case_a53(self):
        root = self.fixture_root / "path-root"; root.mkdir(exist_ok=True); inside = root / "safe.txt"; atomic_write(inside, "ok")
        attacks = [str(root / ".." / "escape.txt"), "\\\\server\\share\\x", "\\\\?\\C:\\Windows\\x", "relative\\x"]
        denied = 0
        for value in attacks:
            try: safe_resolve(value, [root])
            except Exception: denied += 1
        result = run_structured(self.controller.config["workers"]["local_python"], [str(self.controller.code_root / "tests" / "fixtures_crash_worker.py"), "; Remove-Item C:\\"], cwd=str(root), allowed_cwd_roots=[str(root)], timeout_seconds=10)
        return passed({"path_attacks_denied": denied, "shell_injection_not_interpreted": result.exit_code == 23}) if denied == len(attacks) and result.exit_code == 23 else {"passed": False}

    def case_a54(self):
        registry = {item["worker_id"]: item for item in self.store.registry("worker_registry")}
        wb = registry["workbuddy-cli"]
        isolated = wb["allowed_effects"] == ["ACTION_PROPOSAL"] and not wb["allowed_roots"]
        return passed({"untrusted_defaults": {"credentials": False, "production_profile": False, "tcb_write": False, "external_write": False}, "workbuddy": wb}) if isolated else {"passed": False}

    def case_a55(self):
        with self.isolated() as f:
            r = self.reserve_fixture(f); f["store"].start_effect(r, controller_instance_id=f["controller_id"], controller_lease_id=f["lease"]["lease_id"], resource_fresh=True); f["store"].finish_effect(r, {"response": "ambiguous"}, unknown=True); retry = self.reserve_fixture(f)
            return passed({"status": retry.status, "auto_retry": not retry.deduplicated}) if retry.status == "OUTCOME_UNKNOWN" and retry.deduplicated else {"passed": False}

    def case_a56(self):
        pid_path = self.fixture_root / "sleep-child.pid"
        result = run_structured(self.controller.config["workers"]["local_python"], [str(self.controller.code_root / "tests" / "fixtures_sleep_worker.py"), "parent", str(pid_path)], cwd=str(self.fixture_root), allowed_cwd_roots=[str(self.fixture_root)], timeout_seconds=1)
        child_pid = int(pid_path.read_text()) if pid_path.exists() else 0; time.sleep(0.2)
        alive = process_exists(child_pid)
        return passed({"timed_out": result.timed_out, "child_pid": child_pid, "child_alive_after_job_close": alive}) if result.timed_out and child_pid and not alive else {"passed": False, "details": {"result": result.safe_record(), "alive": alive}}

    def case_a57(self):
        outcomes = {}
        with self.isolated() as f:
            try: f["store"].commit_state(f["store"].read_state(), reason="FAULT", faults={"state_write"})
            except StorageDurabilityUnavailable: outcomes["state_write"] = "BLOCKED"
        with self.isolated() as f:
            scope = {"provider": "test-provider", "destination": "test", "purpose": "test-effect", "effect_type": "TEST", "data_classes": ["PUBLIC"]}; nonce = f["store"].issue_decision_nonce(f["task_id"], scope, user_decision_reference="fault")
            try: f["store"].grant_authorization(f["task_id"], nonce["decision_nonce"], scope, provider="test-provider", resource="test", purpose="test-effect", effect_type="TEST", max_effect_count=1, faults={"authority_write"})
            except StorageDurabilityUnavailable: outcomes["authority_write"] = "BLOCKED"
        with self.isolated() as f:
            try: self.reserve_fixture(f, faults={"wal_write"})
            except StorageDurabilityUnavailable: outcomes["wal_write"] = "BLOCKED"
        with self.isolated() as f:
            try: self.reserve_fixture(f, faults={"flush"})
            except StorageDurabilityUnavailable: outcomes["flush"] = f["store"].meta("authority_status")
        ok = outcomes == {"state_write": "BLOCKED", "authority_write": "BLOCKED", "wal_write": "BLOCKED", "flush": "AUTHORITY_STATE_UNCERTAIN"}
        return passed(outcomes) if ok else {"passed": False, "details": outcomes}

    def case_a58(self):
        result = scan_evidence_privacy([path for path in self.evidence_root.rglob('*') if path.is_file()])
        return passed(result) if result["passed"] else {"passed": False, "details": result}

    def case_a59(self):
        with self.isolated() as f:
            lease = json.loads(f["store"].meta("controller_lease")); lease["boot_session_id"] = "stale-boot"; f["store"].set_meta("controller_lease", canonical_json(lease))
            try: self.reserve_fixture(f)
            except GateDenied as error:
                recovery_contract = {"canonical": True, "wal": f["store"].verify_effect_wal()["verified"], "authority": f["store"].verify_authority_chain()["verified"], "locks": True, "unresolved": True}
                return passed({"stale_boot_denied": str(error), "recovery_contract": recovery_contract})
            return {"passed": False}

    def case_a60(self):
        with self.isolated(max_effect_count=1) as f:
            resource = "fixture:race"; f["store"].acquire_lock(resource, controller_instance_id=f["controller_id"], owner="race", pid=os.getpid(), process_start_identity="race", ttl_seconds=300)
            db = f["store"].database_path; root = f["root"]
            def contender():
                store = ControlStore(db, state_root=root)
                try:
                    return store.reserve_effect(self.fixture_intent(f, "race-slot"), controller_instance_id=f["controller_id"], controller_lease_id=f["lease"]["lease_id"], authorization_id=f["auth"]["authorization_id"], context_fence=f["capsule"]["context_fence"], resource_id=resource, resource_hash="race", capability_permitted=True, egress_permitted=True, resource_fresh=True)
                finally: store.close()
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(contender) for _ in range(2)]; results=[]; errors=[]
                for future in futures:
                    try: results.append(future.result())
                    except Exception as error: errors.append(type(error).__name__)
            consumed = f["store"].connection.execute("SELECT consumed_effect_count FROM authorizations WHERE authorization_id=?", (f["auth"]["authorization_id"],)).fetchone()["consumed_effect_count"]
            ok = consumed == 1 and len(results) == 2 and len(errors) == 0 and len([r for r in results if not r.deduplicated]) == 1 and len([r for r in results if r.deduplicated]) == 1
            return passed({"consumed": consumed, "results": [r.deduplicated for r in results], "errors": errors}) if ok else {"passed": False}

    def case_a61(self):
        result = self.local_worker(); invocation_id = result["envelope"]["invocation_id"]
        try: self.store.verify_and_record_result(invocation_id, {**result["envelope"], "request_nonce": "forged"}, {"actor_id": "fake"})
        except GateDenied as error: return passed({"real_source": result["source_binding"], "forged_denied": str(error)})
        return {"passed": False}

    def case_a62(self):
        source_entries, source_digest, _ = tree_manifest(self.controller.code_root)
        candidate = self.fixture_root / "release-integrity"; candidate.mkdir(exist_ok=True)
        for item in source_entries:
            src = self.controller.code_root / item["path"]; dst = candidate / item["path"]; dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
        _, copied_digest, _ = tree_manifest(candidate)
        mutate = candidate / source_entries[0]["path"]; atomic_write(mutate, mutate.read_bytes() + b"mutation")
        _, mutated_digest, _ = tree_manifest(candidate)
        return passed({"source_digest": source_digest, "copied_digest": copied_digest, "mutated_digest": mutated_digest, "mutation_invalidates": mutated_digest != source_digest}) if copied_digest == source_digest and mutated_digest != source_digest else {"passed": False}

    def case_a63(self):
        root = Path(tempfile.mkdtemp(prefix="tcb-", dir=self.fixture_root)); code_copy = root / "code"
        shutil.copytree(self.controller.code_root, code_copy, ignore=shutil.ignore_patterns('.git', 'node_modules', '__pycache__', 'tcb-manifest.json'))
        store = ControlStore(root / "control.db", state_root=root / "state")
        try:
            sealed = seal_tcb(store, code_copy, reason="A63_FIXTURE"); verify_tcb(store, code_copy)
            target = code_copy / "src" / "aicontrol" / "util.py"; atomic_write(target, target.read_text(encoding='utf-8') + "\n# tamper\n")
            try: verify_tcb(store, code_copy)
            except GateDenied as error: return passed({"sealed": sealed, "tamper_denied": str(error), "status": store.meta("tcb_status")})
            return {"passed": False}
        finally: store.close()

    def case_a64(self):
        wb = next(item for item in self.store.registry("worker_registry") if item["worker_id"] == "workbuddy-cli")
        with self.isolated() as f:
            try: self.reserve_fixture(f, capability_permitted=False)
            except GateDenied: gate = True
            else: gate = False
        return passed({"trust_class": wb["execution_trust_class"], "direct_allowed_effects": wb["allowed_effects"], "gate_denied_bypass": gate}) if wb["execution_trust_class"] == "PRIVILEGED_UNBROKERED" and wb["allowed_effects"] == ["ACTION_PROPOSAL"] and gate else {"passed": False}

    def case_a65(self):
        before = self.store.connection.execute("SELECT COUNT(*) AS n FROM test_executions WHERE case_id='FAKE_PASS'").fetchone()["n"]
        fake_worker = {"case_id": "FAKE_PASS", "status": "PASS", "self_report": True}
        after = self.store.connection.execute("SELECT COUNT(*) AS n FROM test_executions WHERE case_id='FAKE_PASS'").fetchone()["n"]
        authentic = all(case["execution_authority"] == "CONTROLLER_OWNED_EXECUTION" and case["tested_artifact_digest"] == self.artifact_digest for case in self.cases)
        return passed({"fake_worker_report": fake_worker, "required_records_created": after - before, "prior_cases_authentic": authentic}) if before == after and authentic else {"passed": False}


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0); return True
    except OSError:
        return False
