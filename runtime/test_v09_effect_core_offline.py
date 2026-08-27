#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import effect_safety_lite as es


class FakeRuntime:
    EXIT_OK = 0
    EXIT_HARD_BLOCKED = 6

    def __init__(self, root: Path):
        self.root = root
        self.journal_events = []
        self.saved = []

    def run_dir(self, rid):
        path = self.root / "runs" / rid
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_state(self, state):
        state["revision"] = int(state.get("revision", 0)) + 1
        self.saved.append(json.loads(json.dumps(state)))
        (self.run_dir(state["run_id"]) / "state.json").write_text(json.dumps(state), encoding="utf-8")

    def journal(self, rid, event, **kw):
        self.journal_events.append((event, kw))

    def load_state(self, rid):
        return json.loads((self.run_dir(rid) / "state.json").read_text(encoding="utf-8"))

    def hard_block(self, state, reason):
        state["status"] = "HARD_BLOCKED"
        state["blocked_reason"] = reason
        self.save_state(state)

    def emit(self, obj):
        self.last_emit = obj


def base_state(run_id="RUN-20260827-230000-a001"):
    return {
        "run_id": run_id,
        "revision": 0,
        "goal": "G",
        "status": "RUNNING",
        "r_url": "https://chatgpt.com/c/example-v09",
        "review_epoch": 1,
        "effect_authorization_generation": 0,
        "effect_revocation_epoch": 0,
    }


H = "a" * 64


def auth_scope(**overrides):
    scope = {
        "provider": "chatgpt-web",
        "resource": "review-thread",
        "purpose": "review transport",
        "identity": "runtime-v1",
        "destination": "https://chatgpt.com/c/example-v09",
        "data_classes": ["INTERNAL"],
    }
    scope.update(overrides)
    return scope


class V09EffectCoreOfflineTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.rt = FakeRuntime(self.root)

    def tearDown(self):
        self.td.cleanup()

    def grant(self, state, *, max_effect_count=2, scope=None):
        return es.grant_authorization(
            self.rt,
            state,
            issuer_role="AUTHORITY",
            issuer_identity="human-orchestrator",
            holder="runtime-v1",
            scope=scope or auth_scope(),
            max_effect_count=max_effect_count,
        )

    def prepare(self, state, *, authorization_id=None, slot="send:1", **overrides):
        params = {
            "operation": "send",
            "destination": "https://chatgpt.com/c/example-v09",
            "provider": "chatgpt-web",
            "resource": "review-thread",
            "identity": "runtime-v1",
            "payload_hash": H,
            "slot": slot,
            "purpose": "review transport",
            "authorization_id": authorization_id,
            "classification": "INTERNAL",
            "capability_permitted": True,
            "egress_permitted": True,
            "resource_fresh": True,
            "tcb_verified": True,
        }
        params.update(overrides)
        return es.prepare_effect(self.rt, state, **params)

    def test_v09_01_no_authorization_denied(self):
        state = base_state()
        with self.assertRaises(es.EffectDenied):
            self.prepare(state)

    def test_v09_02_executor_self_grant_denied(self):
        state = base_state("RUN-20260827-230001-a002")
        with self.assertRaises(es.EffectDenied):
            es.grant_authorization(
                self.rt,
                state,
                issuer_role="EXECUTOR",
                issuer_identity="runtime-v1",
                holder="runtime-v1",
                scope=auth_scope(),
            )

    def test_v09_03_stale_generation_denied_before_execute(self):
        state = base_state("RUN-20260827-230002-a003")
        auth = self.grant(state)
        intent = self.prepare(state, authorization_id=auth["authorization_id"])
        self.grant(state, scope=auth_scope(resource="other-resource"))
        with self.assertRaises(es.EffectDenied):
            es.begin_effect(
                self.rt,
                state,
                intent["logical_effect_id"],
                execution_fence_token=intent["execution_fence_token"],
            )

    def test_v09_04_stale_fence_denied(self):
        state = base_state("RUN-20260827-230003-a004")
        auth = self.grant(state)
        intent = self.prepare(state, authorization_id=auth["authorization_id"])
        with self.assertRaises(es.EffectDenied):
            es.begin_effect(self.rt, state, intent["logical_effect_id"], execution_fence_token="0" * 64)

    def test_v09_05_revoke_between_prepare_execute_denied(self):
        state = base_state("RUN-20260827-230004-a005")
        auth = self.grant(state)
        intent = self.prepare(state, authorization_id=auth["authorization_id"])
        es.revoke_authorization(self.rt, state, auth["authorization_id"])
        with self.assertRaises(es.EffectDenied):
            es.begin_effect(
                self.rt,
                state,
                intent["logical_effect_id"],
                execution_fence_token=intent["execution_fence_token"],
            )

    def test_v09_06_execute_happened_response_lost_becomes_unknown(self):
        state = base_state("RUN-20260827-230005-a006")
        auth = self.grant(state)
        intent = self.prepare(state, authorization_id=auth["authorization_id"])
        es.begin_effect(
            self.rt,
            state,
            intent["logical_effect_id"],
            execution_fence_token=intent["execution_fence_token"],
        )
        result = es.mark_outcome_unknown(
            self.rt,
            state,
            intent["logical_effect_id"],
            observation={"transport": "response_lost_after_execute"},
        )
        self.assertEqual(result["status"], "OUTCOME_UNKNOWN")
        self.assertFalse(result["ordinary_retry_permitted"])

    def test_v09_07_unknown_ordinary_retry_denied(self):
        state = base_state("RUN-20260827-230006-a007")
        auth = self.grant(state)
        intent = self.prepare(state, authorization_id=auth["authorization_id"])
        es.begin_effect(
            self.rt,
            state,
            intent["logical_effect_id"],
            execution_fence_token=intent["execution_fence_token"],
        )
        es.mark_outcome_unknown(self.rt, state, intent["logical_effect_id"], observation={"lost": True})
        with self.assertRaises(es.EffectDenied):
            self.prepare(state, authorization_id=auth["authorization_id"])

    def test_v09_08_reconcile_success_prevents_second_execute(self):
        state = base_state("RUN-20260827-230007-a008")
        auth = self.grant(state)
        intent = self.prepare(state, authorization_id=auth["authorization_id"])
        es.begin_effect(
            self.rt,
            state,
            intent["logical_effect_id"],
            execution_fence_token=intent["execution_fence_token"],
        )
        es.mark_outcome_unknown(self.rt, state, intent["logical_effect_id"], observation={"lost": True})
        reconciled = es.reconcile_effect(
            self.rt,
            state,
            intent["logical_effect_id"],
            observed_succeeded=True,
            evidence={"inspection": "remote-message-present"},
        )
        self.assertEqual(reconciled["status"], "SUCCESS")
        duplicate = self.prepare(state, authorization_id=auth["authorization_id"])
        self.assertTrue(duplicate["deduplicated"])
        self.assertEqual(duplicate["status"], "SUCCESS")
        with self.assertRaises(es.EffectDenied):
            es.begin_effect(
                self.rt,
                state,
                duplicate["logical_effect_id"],
                execution_fence_token=duplicate["execution_fence_token"],
            )

    def test_v09_09_secret_egress_denied(self):
        state = base_state("RUN-20260827-230008-a009")
        auth = self.grant(state)
        with self.assertRaises(es.EffectDenied):
            self.prepare(state, authorization_id=auth["authorization_id"], classification="SECRET")

    def test_v09_10_invalid_tcb_denied(self):
        state = base_state("RUN-20260827-230009-a010")
        auth = self.grant(state)
        with self.assertRaises(es.EffectDenied):
            self.prepare(state, authorization_id=auth["authorization_id"], tcb_verified=False)

    def test_v09_11_missing_human_gate_denied_for_high_risk_effect(self):
        state = base_state("RUN-20260827-230010-a011")
        auth = self.grant(state)
        with self.assertRaises(es.EffectDenied):
            self.prepare(
                state,
                authorization_id=auth["authorization_id"],
                human_gate_required=True,
                human_gate_reference=None,
            )

    def test_v09_12_wrong_resource_or_identity_denied(self):
        state = base_state("RUN-20260827-230011-a012")
        auth = self.grant(state)
        with self.assertRaises(es.EffectDenied):
            self.prepare(state, authorization_id=auth["authorization_id"], resource="other-resource")
        with self.assertRaises(es.EffectDenied):
            self.prepare(state, authorization_id=auth["authorization_id"], identity="other-executor")

    def test_v09_13_effect_count_exhausted_denied(self):
        state = base_state("RUN-20260827-230012-a013")
        auth = self.grant(state, max_effect_count=1)
        self.prepare(state, authorization_id=auth["authorization_id"], slot="send:1")
        with self.assertRaises(es.EffectDenied):
            self.prepare(state, authorization_id=auth["authorization_id"], slot="send:2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
