#!/usr/bin/env python3
"""V0.9 speculative RED-first authority/effect attack matrix.

All scenarios are deterministic and offline. External reality is represented by a
counted in-memory fake executor; production authority/effect code is exercised as
a black box wherever an implementation surface already exists.
"""
from __future__ import annotations

import argparse
import copy
import inspect
import json
import os
import sys
import tempfile
import unittest
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from aicontrol.controller import Controller  # noqa: E402
from aicontrol.security import egress_allowed, scan_evidence_privacy  # noqa: E402
from aicontrol.store import GateDenied, Reservation  # noqa: E402
from aicontrol.util import read_json, sha256_text, write_json  # noqa: E402
import effect_safety_lite as effect_lite  # noqa: E402

MATRIX_PATH = HERE / "fixtures" / "v09_authority_effect_attack_cases.json"
SPECULATIVE_BASE = "b65a51267969824c05a8794376eac766edc08eb9"


@dataclass
class AttackObservation:
    test_id: str
    expected_outcome: str
    observed_outcome: str
    external_effect_count: int = 0
    final_effect_status: str = "NOT_STARTED"
    authorization_identity: str = "NONE"
    generation_fence: str = "NOT_APPLICABLE"
    reconciliation_result: str = "NOT_RUN"
    detail: str = ""

    @property
    def matched(self) -> bool:
        return self.observed_outcome == self.expected_outcome


class CountedExternalReality:
    """Deterministic fake reality. No network or external resource is touched."""

    def __init__(self) -> None:
        self.real_effect_count = 0
        self.external_state = "NOT_OCCURRED"

    def succeed_then_lose_response(self, _reservation: Reservation) -> dict[str, Any]:
        self.real_effect_count += 1
        self.external_state = "SUCCEEDED"
        raise ConnectionError("deterministic response lost after external success")

    def succeed(self, _reservation: Reservation) -> dict[str, Any]:
        self.real_effect_count += 1
        self.external_state = "SUCCEEDED"
        return {"envelope": {"status": "DONE", "data": {}}}

    def probe(self, _reservation: Reservation | None = None) -> str:
        return self.external_state


class Fixture:
    """One isolated Controller and temporary state root per attack."""

    def __init__(self, *, task_id: str = "v09-task-fixed") -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="v09-authority-effect-")
        self.root = Path(self.tmp.name)
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
            goal="V0.9 offline authority/effect attack",
            expected_final_artifact="none",
            acceptance_criteria=["offline attack observation"],
            data_classification="PUBLIC",
            task_id=task_id,
        )
        self.task_id = task_id
        self.context_fence = self.task["context_fence"]
        self.lease = self.controller.acquire_lease()

    def close(self) -> None:
        self.controller.close()
        self.tmp.cleanup()

    def authorization(
        self,
        *,
        provider: str = "provider-a",
        destination: str = "destination-a",
        purpose: str = "v09-test",
        effect_type: str = "AI_MESSAGE",
        max_effect_count: int = 3,
    ) -> dict[str, Any]:
        return self.controller.scoped_authorization(
            task_id=self.task_id,
            provider=provider,
            destination=destination,
            purpose=purpose,
            effect_type=effect_type,
            data_classes=["PUBLIC"],
            max_effect_count=max_effect_count,
            user_decision_reference="fake-human-reference-v09",
        )

    def intent(
        self,
        *,
        provider: str = "provider-a",
        destination: str = "destination-a",
        resource: str = "resource-a",
        purpose: str = "v09-test",
        slot: str = "slot-a",
        payload: str = "payload-a",
        impact: str = "LOW",
        reversibility: str = "REVERSIBLE",
        effect_scope: str = "EXTERNAL",
        critical_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "operation": "FAKE_EXTERNAL_EFFECT",
            "provider": provider,
            "destination": destination,
            "expected_account": "credential-ref:fake-v09",
            "resource": resource,
            "payload_hash": sha256_text(payload),
            "critical_params": dict(critical_params or {}),
            "purpose": purpose,
            "logical_effect_slot": slot,
            "retry_semantics": "RECONCILE_REQUIRED",
            "impact": impact,
            "reversibility": reversibility,
            "effect_scope": effect_scope,
        }

    def execute(
        self,
        *,
        auth: dict[str, Any],
        intent: dict[str, Any],
        adapter: Callable[[Reservation], dict[str, Any]],
        resource_id: str = "resource-lock-a",
        resource_hash: str | None = None,
        egress_permitted: bool = True,
    ) -> dict[str, Any]:
        return self.controller.execute_effect(
            task_id=self.task_id,
            lease=self.lease,
            authorization_id=auth["authorization_id"],
            context_fence=self.context_fence,
            resource_id=resource_id,
            resource_hash=resource_hash or sha256_text(resource_id),
            intent=intent,
            adapter=adapter,
            egress_permitted=egress_permitted,
        )

    def reserve(self, auth: dict[str, Any], intent: dict[str, Any], *, resource_id: str = "resource-lock-a") -> Reservation:
        self.controller.store.acquire_lock(
            resource_id,
            controller_instance_id=self.controller.controller_instance_id,
            owner=f"task:{self.task_id}",
            pid=os.getpid(),
            process_start_identity=self.controller.process_start_identity,
            ttl_seconds=600,
        )
        try:
            return self.controller.store.reserve_effect(
                intent,
                controller_instance_id=self.controller.controller_instance_id,
                controller_lease_id=self.lease["lease_id"],
                authorization_id=auth["authorization_id"],
                context_fence=self.context_fence,
                resource_id=resource_id,
                resource_hash=sha256_text(resource_id),
                capability_permitted=True,
                egress_permitted=True,
                resource_fresh=True,
            )
        finally:
            self.controller.store.release_lock(resource_id, self.controller.controller_instance_id)

    def action_status(self, reservation: Reservation) -> str:
        row = self.controller.store.connection.execute(
            "SELECT status FROM actions WHERE action_id=?", (reservation.action_id,)
        ).fetchone()
        return str(row["status"]) if row else "MISSING"


def load_matrix() -> dict[str, Any]:
    matrix = read_json(MATRIX_PATH)
    if matrix.get("speculative_base_sha") != SPECULATIVE_BASE:
        raise RuntimeError("attack matrix speculative base mismatch")
    cases = matrix.get("cases")
    if not isinstance(cases, list) or len(cases) != 36:
        raise RuntimeError("attack matrix must contain exactly 36 cases")
    ids = [case.get("id") for case in cases]
    expected_ids = [f"V09-R{i:02d}" for i in range(1, 37)]
    if ids != expected_ids or len(set(ids)) != 36:
        raise RuntimeError("attack matrix IDs are not the frozen V09-R01..V09-R36 sequence")
    return matrix


def _obs(case: dict[str, Any], observed: str, **kwargs: Any) -> AttackObservation:
    return AttackObservation(case["id"], case["expected_outcome"], observed, **kwargs)


def _deny_call(case: dict[str, Any], call: Callable[[], Any], **kwargs: Any) -> AttackObservation:
    try:
        call()
    except (GateDenied, PermissionError) as exc:
        data = dict(kwargs)
        data["detail"] = f"{type(exc).__name__}: {exc}"
        return _obs(case, "DENY", **data)
    except Exception as exc:
        text = f"{type(exc).__name__}: {exc}"
        if any(token in text.upper() for token in ("DENY", "BLOCK", "AUTHORITY", "FENCE", "REVOK")):
            data = dict(kwargs)
            data["detail"] = text
            return _obs(case, "DENY", **data)
        data = dict(kwargs)
        data["detail"] = text
        return _obs(case, "ERROR", **data)
    return _obs(case, "ALLOW", **kwargs)


def _fake_runtime_send_observation(case: dict[str, Any]) -> AttackObservation:
    state = {"run_id": "run-fixed", "r_url": "fake://review", "review_epoch": 1}
    sent = {"count": 0}
    journals: list[dict[str, Any]] = []

    class FakeRuntime:
        EXIT_HARD_BLOCKED = 86

        def cmd_send(self, _args: Any) -> int:
            sent["count"] += 1
            return 0

        def load_state(self, _run_id: str) -> dict[str, Any]:
            return state

        def save_state(self, _state: dict[str, Any]) -> None:
            return None

        def journal(self, _run_id: str, event: str, **data: Any) -> None:
            journals.append({"event": event, **data})

        def hard_block(self, _state: dict[str, Any], _reason: str) -> None:
            return None

        def emit(self, _data: dict[str, Any]) -> None:
            return None

    rt = FakeRuntime()
    effect_lite.install(rt, {})
    args = SimpleNamespace(run_id="run-fixed", message="offline", file=[])
    rc = rt.cmd_send(args)
    auths = state.get("effect_authorizations") or {}
    if rc == rt.EXIT_HARD_BLOCKED and sent["count"] == 0:
        observed = "DENY"
    else:
        observed = "ALLOW"
    return _obs(
        case,
        observed,
        external_effect_count=sent["count"],
        final_effect_status=str((state.get("effect_safety") or {}).get("status") or "NOT_STARTED"),
        authorization_identity=next(iter(auths), "NONE"),
        detail=f"runtime_rc={rc}; authorization_count={len(auths)}",
    )


def _find_reconciler(controller: Controller) -> tuple[Any | None, str]:
    candidates = (
        (controller, "reconcile_effect"),
        (controller, "reconcile_unknown_effect"),
        (controller, "reconcile_outcome"),
        (controller.store, "reconcile_effect"),
        (controller.store, "reconcile_unknown_effect"),
        (controller.store, "reconcile_outcome"),
    )
    for obj, name in candidates:
        method = getattr(obj, name, None)
        if callable(method):
            return method, f"{type(obj).__name__}.{name}"
    return None, "NONE"


def _invoke_reconciler(method: Callable[..., Any], reservation: Reservation, reality: CountedExternalReality) -> Any:
    sig = inspect.signature(method)
    kwargs: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if name in ("reservation", "effect_reservation"):
            kwargs[name] = reservation
        elif name == "action_id":
            kwargs[name] = reservation.action_id
        elif name == "logical_effect_id":
            kwargs[name] = reservation.logical_effect_id
        elif name in ("probe", "reconciliation_probe", "reality_probe"):
            kwargs[name] = reality.probe
        elif name in ("external_state", "observed_state"):
            kwargs[name] = reality.external_state
        elif param.default is inspect.Parameter.empty:
            raise TypeError(f"unsupported reconciliation parameter: {name}")
    return method(**kwargs)


def _reservation_for_slot(fx: Fixture, slot: str) -> Reservation:
    row = fx.controller.store.connection.execute(
        "SELECT * FROM actions WHERE task_id=? AND logical_effect_slot=? ORDER BY created_at DESC LIMIT 1",
        (fx.task_id, slot),
    ).fetchone()
    if not row:
        raise AssertionError("attack setup did not create an action")
    return Reservation(
        action_id=row["action_id"], logical_effect_id=row["logical_effect_id"],
        effect_intent_hash=row["effect_intent_hash"], logical_effect_slot=row["logical_effect_slot"],
        attempt_id=row["attempt_id"], execution_fence_token=row["execution_fence_token"],
        deduplicated=False, status=row["status"],
    )


def _crown_unknown(fx: Fixture, *, slot: str) -> tuple[dict[str, Any], Reservation, CountedExternalReality]:
    auth = fx.authorization(max_effect_count=3)
    reality = CountedExternalReality()
    try:
        fx.execute(auth=auth, intent=fx.intent(slot=slot), adapter=reality.succeed_then_lose_response)
    except ConnectionError:
        pass
    return auth, _reservation_for_slot(fx, slot), reality


def _unknown_before_effect(fx: Fixture, *, slot: str, external_state: str) -> tuple[dict[str, Any], Reservation, CountedExternalReality]:
    auth = fx.authorization(max_effect_count=3)
    reality = CountedExternalReality()
    reality.external_state = external_state

    def lost_before_reality(_reservation: Reservation) -> dict[str, Any]:
        raise ConnectionError("deterministic response lost before any confirmed external effect")

    try:
        fx.execute(auth=auth, intent=fx.intent(slot=slot), adapter=lost_before_reality)
    except ConnectionError:
        pass
    return auth, _reservation_for_slot(fx, slot), reality


def run_case(case: dict[str, Any]) -> AttackObservation:
    cid = case["id"]

    if cid == "V09-R01":
        return _fake_runtime_send_observation(case)
    if cid == "V09-R13":
        state = {"run_id": "run-fixed", "effect_authorizations": {}}
        rt = SimpleNamespace(save_state=lambda _s: None, journal=lambda *_a, **_k: None)
        try:
            auth = effect_lite.ensure_valid_authorization(rt, state, holder="executor", scope={"purpose": "self"})
        except Exception as exc:
            return _obs(case, "DENY", detail=f"{type(exc).__name__}: {exc}")
        return _obs(case, "ALLOW", authorization_identity=str(auth.get("authorization_id") or "NONE"),
                    detail="executor obtained authorization without an external grant")

    if cid in ("V09-R27", "V09-R28", "V09-R29"):
        goal = {"data_egress_policy": {"destination-a": ["PUBLIC", "INTERNAL", "PRIVATE_LOCAL"]}}
        if cid == "V09-R27":
            allowed = egress_allowed(classification="SECRET", destination="destination-a", provider="provider-a",
                                     purpose="v09-test", goal_contract=goal, authorization_scope=None)
        elif cid == "V09-R28":
            allowed = egress_allowed(classification="UNKNOWN", destination="destination-a", provider="provider-a",
                                     purpose="v09-test", goal_contract=goal, authorization_scope=None)
        else:
            scope = {"provider": "provider-a", "destination": "destination-a", "purpose": "v09-test",
                     "data_classes": ["PUBLIC"]}
            allowed = egress_allowed(classification="PUBLIC", destination="destination-b", provider="provider-b",
                                     purpose="other-purpose", goal_contract=goal, authorization_scope=scope)
        return _obs(case, "ALLOW" if allowed else "DENY", final_effect_status="EGRESS_ONLY")

    if cid == "V09-R30":
        with tempfile.TemporaryDirectory(prefix="v09-credential-") as tmp:
            p = Path(tmp) / "fake-evidence.log"
            p.write_text("authorization: Bearer fake_token_value_123456789\npassword=fake_password_value\n", encoding="utf-8")
            report = scan_evidence_privacy([p])
        observed = "DENY_OR_REDACT" if (not report["passed"] and report["findings"]) else "ALLOW"
        return _obs(case, observed, final_effect_status="PRIVACY_SCAN", detail=json.dumps(report, sort_keys=True))

    if cid == "V09-R35":
        run_cmd = (HERE / "run.cmd").read_text(encoding="utf-8", errors="replace").lower()
        send_guard = (HERE / "send_guard_lite.py").read_text(encoding="utf-8", errors="replace").lower()
        routes = [
            'if /i "%~1"=="send" goto send_guard',
            'if /i "%~1"=="router-start" goto send_guard',
            'if /i "%~1"=="router-step" goto send_guard',
            'if /i "%~1"=="router-run" goto send_guard',
            'if /i "%~1"=="router-continue" goto send_guard',
        ]
        composed = all(route in run_cmd for route in routes) and "es.install(rt" in send_guard
        return _obs(case, "NO_BYPASS" if composed else "BYPASS_PRESENT", final_effect_status="COMPOSITION_CHECK")

    fx = Fixture()
    try:
        auth = fx.authorization(max_effect_count=4)
        intent = fx.intent()

        if cid == "V09-R02":
            intent["provider"] = "provider-b"
            return _deny_call(case, lambda: fx.execute(auth=auth, intent=intent, adapter=CountedExternalReality().succeed))
        if cid == "V09-R03":
            intent["purpose"] = "different-purpose"
            return _deny_call(case, lambda: fx.execute(auth=auth, intent=intent, adapter=CountedExternalReality().succeed))
        if cid == "V09-R04":
            intent["destination"] = "destination-b"
            intent["resource"] = "resource-b"
            reality = CountedExternalReality()
            obs = _deny_call(case, lambda: fx.execute(auth=auth, intent=intent, adapter=reality.succeed))
            obs.external_effect_count = reality.real_effect_count
            return obs
        if cid == "V09-R05":
            other = Fixture(task_id="v09-task-other")
            try:
                other_auth = other.authorization()
                return _deny_call(case, lambda: fx.execute(auth=other_auth, intent=intent, adapter=CountedExternalReality().succeed))
            finally:
                other.close()
        if cid == "V09-R06":
            intent["critical_params"] = {"worker_id": "worker-b", "role": "UNAUTHORIZED_ROLE"}
            reality = CountedExternalReality()
            obs = _deny_call(case, lambda: fx.execute(auth=auth, intent=intent, adapter=reality.succeed))
            obs.external_effect_count = reality.real_effect_count
            return obs
        if cid == "V09-R07":
            reservation = fx.reserve(auth, intent)
            fx.controller.store.connection.execute(
                "UPDATE authorizations SET generation=generation+1 WHERE authorization_id=?",
                (auth["authorization_id"],),
            )
            return _deny_call(case, lambda: fx.controller.store.start_effect(
                reservation, controller_instance_id=fx.controller.controller_instance_id,
                controller_lease_id=fx.lease["lease_id"], resource_fresh=True),
                final_effect_status=fx.action_status(reservation), authorization_identity=auth["authorization_id"],
                generation_fence="AUTH_GENERATION_MUTATED")
        if cid == "V09-R08":
            reservation = fx.reserve(auth, intent)
            forged = Reservation(reservation.action_id, reservation.logical_effect_id, reservation.effect_intent_hash,
                                 reservation.logical_effect_slot, reservation.attempt_id, "0" * 64, False, reservation.status)
            return _deny_call(case, lambda: fx.controller.store.start_effect(
                forged, controller_instance_id=fx.controller.controller_instance_id,
                controller_lease_id=fx.lease["lease_id"], resource_fresh=True),
                final_effect_status=fx.action_status(reservation), authorization_identity=auth["authorization_id"],
                generation_fence="FORGED_EXECUTION_FENCE")
        if cid == "V09-R09":
            reservation = fx.reserve(auth, intent)
            state = fx.controller.store.read_state()
            state["v09_attack_revision"] = "changed"
            fx.controller.store.commit_state(state, reason="V09_R09_STALE_REVISION")
            obs = _deny_call(case, lambda: fx.controller.store.start_effect(
                reservation, controller_instance_id=fx.controller.controller_instance_id,
                controller_lease_id=fx.lease["lease_id"], resource_fresh=True),
                final_effect_status=fx.action_status(reservation), authorization_identity=auth["authorization_id"],
                generation_fence="STATE_REVISION_CHANGED")
            if obs.observed_outcome == "DENY":
                obs.observed_outcome = "DENY_OR_REVALIDATE"
            return obs
        if cid == "V09-R10":
            fx.controller.store.revoke_authorization(auth["authorization_id"], reason="V09-R10")
            return _deny_call(case, lambda: fx.execute(auth=auth, intent=intent, adapter=CountedExternalReality().succeed),
                              authorization_identity=auth["authorization_id"])
        if cid == "V09-R11":
            expired = (datetime.now(UTC) - timedelta(seconds=60)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            fx.controller.store.connection.execute("UPDATE authorizations SET expires_at=? WHERE authorization_id=?",
                                                   (expired, auth["authorization_id"]))
            return _deny_call(case, lambda: fx.execute(auth=auth, intent=intent, adapter=CountedExternalReality().succeed),
                              authorization_identity=auth["authorization_id"])
        if cid == "V09-R12":
            one = fx.authorization(max_effect_count=1)
            fx.execute(auth=one, intent=fx.intent(slot="quota-1", payload="quota-1"),
                       adapter=CountedExternalReality().succeed, resource_id="quota-r1")
            return _deny_call(case, lambda: fx.execute(auth=one, intent=fx.intent(slot="quota-2", payload="quota-2"),
                                                       adapter=CountedExternalReality().succeed, resource_id="quota-r2"),
                              authorization_identity=one["authorization_id"])
        if cid == "V09-R14":
            fake = Reservation("missing-action", "missing-effect", "0"*64, "missing-slot", "missing-attempt", "0"*64,
                               False, "RESERVATION_COMMITTED")
            result = _deny_call(case, lambda: fx.controller.store.start_effect(
                fake, controller_instance_id=fx.controller.controller_instance_id,
                controller_lease_id=fx.lease["lease_id"], resource_fresh=True))
            result.observed_outcome = "NO_EXECUTE" if result.observed_outcome == "DENY" else "EXECUTED"
            return result
        if cid == "V09-R15":
            reservation = fx.reserve(auth, fx.intent(slot="crash-before-execute"))
            replay = fx.reserve(auth, fx.intent(slot="crash-before-execute"))
            status = fx.action_status(reservation)
            observed = "NO_DUPLICATE" if replay.deduplicated and status == "RESERVATION_COMMITTED" else "DUPLICATE"
            return _obs(case, observed, external_effect_count=0, final_effect_status=status,
                        authorization_identity=auth["authorization_id"], generation_fence="RESERVATION_DURABLE")
        if cid in ("V09-R16", "V09-R17"):
            reality = CountedExternalReality()
            same = fx.intent(slot="same-slot", payload="same-payload")
            fx.execute(auth=auth, intent=same, adapter=reality.succeed, resource_id="dup-r1")
            replay = fx.execute(auth=auth, intent=same, adapter=reality.succeed, resource_id="dup-r2")
            observed = ("EXACTLY_ONCE" if cid == "V09-R16" else "DEDUPLICATE") if (
                reality.real_effect_count == 1 and replay.get("deduplicated")) else "DUPLICATE"
            return _obs(case, observed, external_effect_count=reality.real_effect_count,
                        final_effect_status=str(replay["reservation"].status), authorization_identity=auth["authorization_id"])
        if cid == "V09-R18":
            reality = CountedExternalReality()
            fx.execute(auth=auth, intent=fx.intent(slot="same-slot-diff", payload="payload-one"),
                       adapter=reality.succeed, resource_id="conflict-r1")
            try:
                fx.execute(auth=auth, intent=fx.intent(slot="same-slot-diff", payload="payload-two"),
                           adapter=reality.succeed, resource_id="conflict-r2")
            except GateDenied as exc:
                return _obs(case, "CONFLICT_OR_DENY", external_effect_count=reality.real_effect_count, detail=str(exc))
            return _obs(case, "ALLOW", external_effect_count=reality.real_effect_count)
        if cid == "V09-R19":
            auth2, reservation, reality = _crown_unknown(fx, slot="crown-r19")
            status = fx.action_status(reservation)
            observed = "OUTCOME_UNKNOWN" if status == "OUTCOME_UNKNOWN" and reality.real_effect_count == 1 else status
            return _obs(case, observed, external_effect_count=reality.real_effect_count, final_effect_status=status,
                        authorization_identity=auth2["authorization_id"], reconciliation_result="NOT_RUN")
        if cid == "V09-R20":
            auth2, reservation, reality = _crown_unknown(fx, slot="crown-r20")
            try:
                replay = fx.execute(auth=auth2, intent=fx.intent(slot="crown-r20"), adapter=reality.succeed,
                                    resource_id="crown-r20-retry")
            except Exception as exc:
                if isinstance(exc, GateDenied) or "reconcile" in str(exc).lower() or "unknown" in str(exc).lower():
                    return _obs(case, "DENY", external_effect_count=reality.real_effect_count,
                                final_effect_status=fx.action_status(reservation), detail=str(exc))
                raise
            return _obs(case, "ALLOW", external_effect_count=reality.real_effect_count,
                        final_effect_status=fx.action_status(reservation),
                        detail=f"ordinary retry returned deduplicated={replay.get('deduplicated')}")
        if cid == "V09-R21":
            auth2, reservation, reality = _crown_unknown(fx, slot="crown-r21")
            replay = fx.execute(auth=auth2, intent=fx.intent(slot="crown-r21"), adapter=reality.succeed,
                                resource_id="crown-r21-restart")
            observed = "RECONCILE_FIRST" if (replay.get("reconciliation_required") is True and
                                             reality.real_effect_count == 1) else "DEDUPLICATED_WITHOUT_RECONCILE"
            return _obs(case, observed, external_effect_count=reality.real_effect_count,
                        final_effect_status=fx.action_status(reservation), reconciliation_result="REQUIRED")
        if cid in ("V09-R22", "V09-R23", "V09-R24"):
            if cid == "V09-R22":
                auth2, reservation, reality = _crown_unknown(fx, slot="crown-r22")
            elif cid == "V09-R23":
                auth2, reservation, reality = _unknown_before_effect(fx, slot="crown-r23", external_state="NOT_OCCURRED")
            else:
                auth2, reservation, reality = _unknown_before_effect(fx, slot="crown-r24", external_state="INDETERMINATE")
            method, method_name = _find_reconciler(fx.controller)
            if method is None:
                return _obs(case, "UNSUPPORTED", external_effect_count=reality.real_effect_count,
                            final_effect_status=fx.action_status(reservation), authorization_identity=auth2["authorization_id"],
                            reconciliation_result="NO_RECONCILIATION_API")
            try:
                value = _invoke_reconciler(method, reservation, reality)
            except Exception as exc:
                return _obs(case, "RECONCILIATION_ERROR", external_effect_count=reality.real_effect_count,
                            final_effect_status=fx.action_status(reservation),
                            reconciliation_result=f"{method_name}:{type(exc).__name__}:{exc}")
            status = fx.action_status(reservation)
            text = json.dumps(value, default=str, sort_keys=True).upper()
            if cid == "V09-R22":
                observed = "COMMIT_SUCCESS_NO_EXECUTE" if status == "ACTION_COMMITTED" and reality.real_effect_count == 1 else "WRONG_RECONCILIATION"
            elif cid == "V09-R23":
                observed = "CONTROLLED_RETRY_ONLY" if ("RETRY" in text or "NOT_OCCURRED" in text) and reality.real_effect_count == 0 else "WRONG_RECONCILIATION"
            else:
                safe = status == "OUTCOME_UNKNOWN" and ("HUMAN" in text or "UNKNOWN" in text or "INDETERMINATE" in text)
                observed = "STAY_UNKNOWN_OR_HUMAN_GATE" if safe else "WRONG_RECONCILIATION"
            return _obs(case, observed, external_effect_count=reality.real_effect_count, final_effect_status=status,
                        authorization_identity=auth2["authorization_id"], reconciliation_result=f"{method_name}:{value!r}")
        if cid == "V09-R25":
            reservation = fx.reserve(auth, fx.intent(slot="revoke-between"))
            fx.controller.store.revoke_authorization(auth["authorization_id"], reason="V09-R25")
            return _deny_call(case, lambda: fx.controller.store.start_effect(
                reservation, controller_instance_id=fx.controller.controller_instance_id,
                controller_lease_id=fx.lease["lease_id"], resource_fresh=True),
                final_effect_status=fx.action_status(reservation), authorization_identity=auth["authorization_id"],
                generation_fence="REVOKED_AFTER_RESERVE")
        if cid == "V09-R26":
            reservation = fx.reserve(auth, fx.intent(slot="generation-between"))
            fx.authorization(provider="provider-b", destination="destination-b", purpose="other", max_effect_count=1)
            return _deny_call(case, lambda: fx.controller.store.start_effect(
                reservation, controller_instance_id=fx.controller.controller_instance_id,
                controller_lease_id=fx.lease["lease_id"], resource_fresh=True),
                final_effect_status=fx.action_status(reservation), authorization_identity=auth["authorization_id"],
                generation_fence="TASK_AUTH_GENERATION_ADVANCED")
        if cid == "V09-R31":
            fx.controller.store.set_meta("tcb_status", "UNVERIFIED_AFTER_CONTROLLER_CHANGE")
            return _deny_call(case, lambda: fx.execute(auth=auth, intent=intent, adapter=CountedExternalReality().succeed),
                              final_effect_status="TCB_UNVERIFIED")
        if cid == "V09-R32":
            high = fx.intent(impact="HIGH", reversibility="IRREVERSIBLE", slot="high-risk")
            reality = CountedExternalReality()
            obs = _deny_call(case, lambda: fx.execute(auth=auth, intent=high, adapter=reality.succeed),
                             detail="no explicit Human Gate token supplied")
            obs.external_effect_count = reality.real_effect_count
            return obs
        if cid == "V09-R33":
            missing = fx.intent(slot="missing-classification")
            missing.pop("effect_scope")
            try:
                fx.execute(auth=auth, intent=missing, adapter=CountedExternalReality().succeed)
            except Exception as exc:
                return _obs(case, "FAIL_CLOSED", detail=f"{type(exc).__name__}: {exc}")
            return _obs(case, "ALLOW")
        if cid == "V09-R34":
            weird_auth = fx.authorization(effect_type="TOTALLY_UNKNOWN_EFFECT_TYPE", max_effect_count=1)
            reality = CountedExternalReality()
            try:
                fx.execute(auth=weird_auth, intent=fx.intent(slot="unknown-effect-type"), adapter=reality.succeed)
            except Exception as exc:
                return _obs(case, "FAIL_CLOSED", external_effect_count=reality.real_effect_count,
                            detail=f"{type(exc).__name__}: {exc}")
            return _obs(case, "ALLOW", external_effect_count=reality.real_effect_count)
        if cid == "V09-R36":
            reservation = fx.reserve(auth, fx.intent(slot="stale-process"))
            fx.authorization(provider="provider-b", destination="destination-b", purpose="takeover", max_effect_count=1)
            return _deny_call(case, lambda: fx.controller.store.start_effect(
                reservation, controller_instance_id=fx.controller.controller_instance_id,
                controller_lease_id=fx.lease["lease_id"], resource_fresh=True),
                final_effect_status=fx.action_status(reservation), authorization_identity=auth["authorization_id"],
                generation_fence="STALE_PROCESS_AFTER_TAKEOVER")
        raise AssertionError(f"unimplemented attack case: {cid}")
    finally:
        fx.close()


def run_all() -> list[AttackObservation]:
    matrix = load_matrix()
    return [run_case(case) for case in matrix["cases"]]


class V09AttackMatrixOfflineTests(unittest.TestCase):
    maxDiff = None

    def test_matrix_contract_and_all_attacks(self) -> None:
        observations = run_all()
        failures = [asdict(obs) for obs in observations if not obs.matched]
        self.assertEqual(len(observations), 36)
        self.assertFalse(failures, json.dumps(failures, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--emit-jsonl", type=Path)
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args(argv)
    if args.emit_jsonl or args.summary_only:
        observations = run_all()
        if args.emit_jsonl:
            args.emit_jsonl.parent.mkdir(parents=True, exist_ok=True)
            args.emit_jsonl.write_text(
                "".join(json.dumps(asdict(obs) | {"matched": obs.matched}, sort_keys=True) + "\n" for obs in observations),
                encoding="utf-8",
            )
        red = sum(not obs.matched for obs in observations)
        print(json.dumps({
            "protocol": "V09_ATTACK_RESULT_JSONL_1",
            "attack_matrix_count": len(observations),
            "matched_count": len(observations) - red,
            "red_baseline_count": red,
            "crown": {
                obs.test_id: {
                    "observed_outcome": obs.observed_outcome,
                    "external_effect_count": obs.external_effect_count,
                    "final_effect_status": obs.final_effect_status,
                    "reconciliation_result": obs.reconciliation_result,
                }
                for obs in observations if obs.test_id in {f"V09-R{i:02d}" for i in range(19, 25)}
            },
        }, sort_keys=True))
        return 0
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(V09AttackMatrixOfflineTests)
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
