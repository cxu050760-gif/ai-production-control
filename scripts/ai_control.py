from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


CODE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = CODE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from aicontrol.acceptance import AcceptanceRunner  # noqa: E402
from aicontrol.controller import Controller, validate_reviewer_envelope  # noqa: E402
from aicontrol.security import seal_tcb, verify_tcb  # noqa: E402
from aicontrol.store import GateDenied  # noqa: E402
from aicontrol.util import (  # noqa: E402
    atomic_write,
    read_json,
    sha256_file,
    sha256_text,
    tree_manifest,
    utc_now,
    write_json,
)


DEFAULT_CONFIG = CODE_ROOT / "config" / "production.json"


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def ensure_runtime_directories(controller: Controller) -> None:
    for key in ("release_root", "evidence_root"):
        Path(controller.config[key]).mkdir(parents=True, exist_ok=True)


def latest_task_id(controller: Controller) -> str | None:
    row = controller.store.connection.execute(
        "SELECT task_id FROM goal_contracts ORDER BY created_at DESC, version DESC LIMIT 1"
    ).fetchone()
    return str(row["task_id"]) if row else None


def current_or_fresh_context(controller: Controller, task_id: str, checkpoint: str) -> str:
    try:
        return controller.store.current_context_fence(task_id)
    except GateDenied:
        capsule = controller.store.create_context_capsule(
            task_id,
            checkpoint,
            {
                "current_objective": "Resume from durable Canonical State",
                "last_verified_state": controller.store.state_head(),
                "next_required_steps": ["continue controller-owned execution"],
            },
        )
        return str(capsule["context_fence"])


def bootstrap_acceptance(controller: Controller) -> dict[str, Any]:
    return controller.bootstrap_task(
        goal="Build and authentically verify the V14-FROZEN AI Production Control Plane and Universal Browser Runtime.",
        expected_final_artifact="digest-bound release candidate plus A01-A65 evidence",
        acceptance_criteria=[f"A{i:02d}" for i in range(1, 66)],
        data_classification="INTERNAL",
    )


def command_run(args: argparse.Namespace, controller: Controller) -> dict[str, Any]:
    return controller.run_goal(args.goal, data_classification=args.data_classification)


def command_status(args: argparse.Namespace, controller: Controller) -> dict[str, Any]:
    return controller.status(args.task_id)


def command_resume(args: argparse.Namespace, controller: Controller) -> dict[str, Any]:
    recovery = controller.store.recover_state()
    controller.store.verify_effect_wal()
    controller.store.verify_authority_chain()
    task_id = args.task_id or latest_task_id(controller)
    if task_id:
        current_or_fresh_context(controller, task_id, "CLI_RESUME")
    return {"status": "RECOVERED", "recovery": recovery, "task": controller.status(task_id) if task_id else None}


def command_doctor(args: argparse.Namespace, controller: Controller) -> dict[str, Any]:
    controller.runtime.register_defaults()
    return controller.doctor(live_browser=args.live_browser)


def command_selftest(controller: Controller) -> dict[str, Any]:
    result = subprocess.run(
        [
            controller.config["workers"]["local_python"],
            "-m",
            "unittest",
            "discover",
            "-s",
            str(CODE_ROOT / "tests"),
            "-p",
            "test_*.py",
            "-v",
        ],
        cwd=str(CODE_ROOT),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=180,
    )
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def command_worker(args: argparse.Namespace, controller: Controller) -> dict[str, Any]:
    controller.runtime.register_defaults()
    task = controller.bootstrap_task(
        goal=args.goal,
        expected_final_artifact="worker diagnostic artifact",
        acceptance_criteria=["result envelope source-bound", "artifact hash verified"],
        data_classification="PRIVATE_LOCAL",
    )
    return controller.runtime.invoke_local_worker(
        task_id=task["task_id"],
        goal_text=args.goal,
        context_fence=task["context_fence"],
        cold_start=args.cold_start,
    )


def command_browser(args: argparse.Namespace, controller: Controller) -> dict[str, Any]:
    controller.runtime.register_defaults()
    task = controller.bootstrap_task(
        goal=f"Controller-owned browser {args.browser_command} diagnostic",
        expected_final_artifact="browser evidence",
        acceptance_criteria=["browser result envelope source-bound"],
        data_classification="PUBLIC",
    )
    options: dict[str, Any] = {
        "profile_path": str(Path(controller.config["state_root"]) / f"browser-cli-{args.browser_command}"),
        "controller_timeout_seconds": args.timeout,
    }
    if args.browser_command in ("lab", "benchmark"):
        options["video_path"] = str(CODE_ROOT / "lab" / "tiny-video.mp4")
    if args.browser_command == "lab":
        fixture = Path(controller.config["state_root"]) / "browser-cli-public-upload.txt"
        atomic_write(fixture, "PUBLIC SYNTHETIC BROWSER FIXTURE\n")
        options.update(
            synthetic_upload_path=str(fixture),
            download_dir=str(Path(controller.config["evidence_root"]) / task["task_id"] / "downloads"),
            screenshot_dir=str(Path(controller.config["evidence_root"]) / task["task_id"] / "screenshots"),
        )
    return controller.runtime.invoke_browser(
        task_id=task["task_id"],
        context_fence=task["context_fence"],
        command=args.browser_command,
        options=options,
    )


def command_brain(args: argparse.Namespace, controller: Controller) -> dict[str, Any]:
    controller.runtime.register_defaults()
    task = controller.bootstrap_task(
        goal="Proposal-only Brain diagnostic",
        expected_final_artifact="source-bound Brain result envelope",
        acceptance_criteria=["no direct action", "binding fields verified"],
        data_classification="PUBLIC",
    )
    lease = controller.acquire_lease()
    provider = "WorkBuddy" if args.provider == "workbuddy" else "Codex CLI"
    authorization = controller.scoped_authorization(
        task_id=task["task_id"],
        provider=provider,
        destination=provider,
        purpose="brain-diagnostic",
        effect_type="AI_MESSAGE",
        data_classes=["PUBLIC"],
        max_effect_count=1,
        user_decision_reference=f"operator-brain-command:{sha256_text(args.prompt)}",
    )
    intent = {
        "task_id": task["task_id"],
        "operation": "INVOKE_PROPOSAL_ONLY_BRAIN",
        "provider": provider,
        "destination": provider,
        "expected_account": f"credential-ref:{args.provider}-existing-auth",
        "resource": f"fresh-{args.provider}-session",
        "payload_hash": sha256_text(args.prompt),
        "critical_params": {"role": "DIAGNOSTIC"},
        "purpose": "brain-diagnostic",
        "logical_effect_slot": f"CLI_BRAIN_{args.provider.upper()}",
        "retry_semantics": "RECONCILE_REQUIRED",
        "impact": "LOW",
        "reversibility": "PARTIALLY_REVERSIBLE",
        "effect_scope": "EXTERNAL",
    }
    if args.provider == "workbuddy":
        adapter = lambda _: controller.runtime.invoke_workbuddy_brain(
            task_id=task["task_id"], context_fence=task["context_fence"], prompt=args.prompt
        )
    else:
        adapter = lambda _: controller.runtime.invoke_codex_brain(
            task_id=task["task_id"], context_fence=task["context_fence"], prompt=args.prompt
        )
    return controller.execute_effect(
        task_id=task["task_id"],
        lease=lease,
        authorization_id=authorization["authorization_id"],
        context_fence=task["context_fence"],
        resource_id=f"brain:{args.provider}",
        resource_hash=sha256_text(provider),
        intent=intent,
        adapter=adapter,
        egress_permitted=True,
    )


def command_acceptance(args: argparse.Namespace, controller: Controller) -> dict[str, Any]:
    ensure_runtime_directories(controller)
    controller.runtime.register_defaults()
    if args.seal:
        controller.seal_tcb("V14_FROZEN_ACCEPTANCE_CANDIDATE")
    verify_tcb(controller.store, controller.code_root)
    task = bootstrap_acceptance(controller)
    entries, artifact_digest, artifact_size = tree_manifest(controller.code_root)
    artifact_manifest = Path(controller.config["evidence_root"]) / task["task_id"] / "tested-artifact-manifest.json"
    write_json(
        artifact_manifest,
        {
            "schema_version": 1,
            "task_id": task["task_id"],
            "artifact_digest": artifact_digest,
            "artifact_size": artifact_size,
            "entries": entries,
            "generated_at": utc_now(),
        },
    )
    runner = AcceptanceRunner(
        controller,
        task_id=task["task_id"],
        context_fence=task["context_fence"],
        artifact_digest=artifact_digest,
        prompt_hash=args.prompt_hash,
    )
    result = runner.run_all()
    acceptance_evidence_id = controller.store.record_evidence(
        task_id=task["task_id"],
        classification="INTERNAL",
        kind="ACCEPTANCE_MANIFEST",
        path=result["path"],
        sha256=result["sha256"],
        metadata={
            "schema_version": result["schema_version"],
            "goal_contract_hash": result["goal_contract_hash"],
            "state_revision": result["state_revision"],
            "context_fence": result["context_fence"],
            "tested_artifact_digest": result["tested_artifact_digest"],
        },
    )
    result["evidence_id"] = acceptance_evidence_id
    result["artifact_manifest_path"] = str(artifact_manifest)
    result["artifact_manifest_sha256"] = sha256_file(artifact_manifest)
    return result


def command_review(args: argparse.Namespace, controller: Controller) -> dict[str, Any]:
    controller.runtime.register_defaults()
    acceptance_path = Path(args.acceptance_manifest).resolve(strict=True)
    claimed_acceptance = read_json(acceptance_path)
    task_id = args.task_id or claimed_acceptance["task_id"]
    _, artifact_digest, _ = tree_manifest(controller.code_root)
    acceptance, acceptance_evidence = controller.validate_acceptance_manifest(
        task_id=task_id,
        acceptance_manifest_path=acceptance_path,
        artifact_digest=artifact_digest,
    )
    context_fence = controller.store.current_context_fence(task_id)
    lease = controller.acquire_lease()
    authorization = controller.scoped_authorization(
        task_id=task_id,
        provider="Codex CLI",
        destination="Codex CLI",
        purpose="release-review",
        effect_type="AI_MESSAGE",
        data_classes=["INTERNAL"],
        max_effect_count=1,
        user_decision_reference=f"V14-FROZEN:release-review:{artifact_digest}",
    )
    prompt = (
        "Independently review the AI Production Control Plane release candidate at "
        f"{controller.code_root}. It is immutable for this review and has SHA-256 tree digest {artifact_digest}. "
        f"The controller-owned acceptance manifest is {acceptance_path}. Inspect source and evidence read-only. "
        "Report only genuine release-blocking correctness, security, durability, or source-binding findings; "
        "if none, return an empty findings list."
    )
    intent = {
        "task_id": task_id,
        "operation": "INDEPENDENT_RELEASE_REVIEW",
        "provider": "Codex CLI",
        "destination": "Codex CLI",
        "expected_account": "credential-ref:codex-existing-login",
        "resource": "fresh-read-only-review-session",
        "payload_hash": sha256_text(prompt),
        "critical_params": {"artifact_digest": artifact_digest, "acceptance_evidence_id": acceptance_evidence["evidence_id"], "role": "REVIEWER"},
        "purpose": "release-review",
        "logical_effect_slot": "INDEPENDENT_CODEX_RELEASE_REVIEW",
        "retry_semantics": "RECONCILE_REQUIRED",
        "impact": "LOW",
        "reversibility": "PARTIALLY_REVERSIBLE",
        "effect_scope": "EXTERNAL",
    }
    effect = controller.execute_effect(
        task_id=task_id,
        lease=lease,
        authorization_id=authorization["authorization_id"],
        context_fence=context_fence,
        resource_id="brain:codex-release-review",
        resource_hash=artifact_digest,
        intent=intent,
        egress_permitted=True,
        adapter=lambda _: controller.runtime.invoke_codex_brain(
            task_id=task_id,
            context_fence=context_fence,
            prompt=prompt,
            role="REVIEWER",
            artifact_digest=artifact_digest,
            acceptance_evidence_id=acceptance_evidence["evidence_id"],
        ),
    )
    if effect.get("unknown") or effect.get("deduplicated"):
        raise GateDenied("review refused: Reviewer Effect is unknown or not a fresh committed execution")
    envelope = effect["adapter_result"]["envelope"]
    validate_reviewer_envelope(
        envelope,
        task_id=task_id,
        goal_contract_hash=acceptance["goal_contract_hash"],
        state_revision=acceptance["state_revision"],
        context_fence=context_fence,
        artifact_digest=artifact_digest,
        acceptance_evidence_id=acceptance_evidence["evidence_id"],
    )
    reservation = effect["reservation"]
    reviews = [
        {
            "schema_version": 1,
            "reviewer": effect["adapter_result"]["source_binding"]["actor_id"],
            "provider": "Codex CLI",
            "task_id": task_id,
            "goal_contract_hash": acceptance["goal_contract_hash"],
            "state_revision": acceptance["state_revision"],
            "context_fence": context_fence,
            "artifact_digest": artifact_digest,
            "verdict": envelope["verdict"],
            "findings": envelope["findings"],
            "recommended_actions": envelope["recommended_actions"],
            "result_id": effect["adapter_result"]["verification"]["result_id"],
            "invocation_id": envelope["invocation_id"],
            "action_id": reservation.action_id,
            "logical_effect_id": reservation.logical_effect_id,
            "source_binding": effect["adapter_result"]["source_binding"],
        },
    ]
    output = Path(controller.config["evidence_root"]) / task_id / "independent-reviews.json"
    document = {
        "schema_version": 1,
        "task_id": task_id,
        "goal_contract_hash": acceptance["goal_contract_hash"],
        "state_revision": acceptance["state_revision"],
        "context_fence": context_fence,
        "artifact_digest": artifact_digest,
        "acceptance_evidence_id": acceptance_evidence["evidence_id"],
        "reviews": reviews,
        "generated_at": utc_now(),
    }
    write_json(output, document)
    output_hash = sha256_file(output)
    review_evidence_id = controller.store.record_evidence(
        task_id=task_id,
        classification="INTERNAL",
        kind="INDEPENDENT_REVIEW_MANIFEST",
        path=str(output),
        sha256=output_hash,
        metadata={
            "schema_version": 1,
            "goal_contract_hash": acceptance["goal_contract_hash"],
            "state_revision": acceptance["state_revision"],
            "context_fence": context_fence,
            "artifact_digest": artifact_digest,
            "acceptance_evidence_id": acceptance_evidence["evidence_id"],
        },
    )
    return {
        "status": "PASS" if envelope["verdict"] == "PASS" and envelope["findings"] == [] else "FAIL",
        "reviews": reviews,
        "path": str(output),
        "sha256": output_hash,
        "evidence_id": review_evidence_id,
    }


def command_release(args: argparse.Namespace, controller: Controller) -> dict[str, Any]:
    return controller.create_release_candidate(
        task_id=args.task_id,
        acceptance_manifest_path=args.acceptance_manifest,
        review_manifest_path=args.review_evidence,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-control", description="Windows-local AI Production Control Plane")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Run one controlled goal")
    run.add_argument("goal")
    run.add_argument(
        "--data-classification",
        choices=["PUBLIC", "INTERNAL", "PRIVATE_LOCAL", "SENSITIVE", "SECRET"],
        default="PRIVATE_LOCAL",
    )

    status = commands.add_parser("status")
    status.add_argument("--task-id")
    resume = commands.add_parser("resume")
    resume.add_argument("--task-id")
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--live-browser", action="store_true")
    commands.add_parser("selftest")

    worker = commands.add_parser("worker")
    worker.add_argument("goal")
    worker.add_argument("--cold-start", action="store_true")

    browser = commands.add_parser("browser")
    browser.add_argument("browser_command", choices=["doctor", "lab", "benchmark"])
    browser.add_argument("--timeout", type=int, default=240)

    brain = commands.add_parser("brain")
    brain.add_argument("provider", choices=["workbuddy", "codex"])
    brain.add_argument("prompt")

    acceptance = commands.add_parser("acceptance")
    acceptance.add_argument("--seal", action="store_true", help="Seal the current controller candidate before testing")
    acceptance.add_argument(
        "--prompt-hash",
        default="6fe3bb7996a1f78a7d6584d08311c3ebc1aa2d9ffc56c27fc61e8d599e154df6",
    )

    review = commands.add_parser("review")
    review.add_argument("acceptance_manifest")
    review.add_argument("--task-id")

    tcb = commands.add_parser("tcb")
    tcb.add_argument("tcb_command", choices=["seal", "verify"])
    tcb.add_argument("--reason", default="OPERATOR_REQUESTED_SEAL")

    release = commands.add_parser("release")
    release.add_argument("task_id")
    release.add_argument("acceptance_manifest")
    release.add_argument("review_evidence")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        with Controller(args.config) as controller:
            ensure_runtime_directories(controller)
            if args.command == "run":
                value = command_run(args, controller)
            elif args.command == "status":
                value = command_status(args, controller)
            elif args.command == "resume":
                value = command_resume(args, controller)
            elif args.command == "doctor":
                value = command_doctor(args, controller)
            elif args.command == "selftest":
                value = command_selftest(controller)
            elif args.command == "worker":
                value = command_worker(args, controller)
            elif args.command == "browser":
                value = command_browser(args, controller)
            elif args.command == "brain":
                value = command_brain(args, controller)
            elif args.command == "acceptance":
                value = command_acceptance(args, controller)
            elif args.command == "review":
                value = command_review(args, controller)
            elif args.command == "release":
                value = command_release(args, controller)
            elif args.command == "tcb" and args.tcb_command == "seal":
                value = seal_tcb(controller.store, controller.code_root, reason=args.reason)
            elif args.command == "tcb" and args.tcb_command == "verify":
                value = verify_tcb(controller.store, controller.code_root)
            else:
                parser.error("unsupported command")
                return 2
        emit(value)
        if isinstance(value, dict) and value.get("status") in ("FAIL", "FAILED_INTERNAL", "EXTERNAL_BLOCKED", "PRODUCT_NOT_READY"):
            return 1
        return 0
    except Exception as error:
        emit({"status": "FAILED_INTERNAL", "error_type": type(error).__name__, "error": str(error)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
