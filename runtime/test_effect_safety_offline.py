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
        p = self.root / "runs" / rid
        p.mkdir(parents=True, exist_ok=True)
        return p

    def save_state(self, state):
        state["revision"] = int(state.get("revision", 0)) + 1
        self.saved.append(json.loads(json.dumps(state)))
        (self.run_dir(state["run_id"]) / "state.json").write_text(json.dumps(state), encoding="utf-8")

    def journal(self, rid, event, **kw):
        self.journal_events.append((event, kw))

    def load_state(self, rid):
        return json.loads((self.run_dir(rid) / "state.json").read_text())

    def hard_block(self, state, reason):
        state["status"] = "HARD_BLOCKED"
        state["blocked_reason"] = reason
        self.save_state(state)

    def emit(self, obj):
        self.last_emit = obj


def base_state(run_id="RUN-20260824-150000-iiii"):
    return {
        "run_id": run_id,
        "revision": 0,
        "goal": "G",
        "status": "RUNNING",
        "r_url": "https://chatgpt.com/c/x",
        "review_epoch": 1,
        "effect_authorization_generation": 0,
        "effect_revocation_epoch": 0,
        "effect_egress_permitted": True,
        "effect_tcb_verified": True,
        "effect_data_classification": "INTERNAL",
    }


H = "a" * 64


def scope_for(destination="d", purpose="x", resource=None):
    return {
        "provider": "chatgpt-web",
        "resource": resource or destination,
        "purpose": purpose,
        "identity": "runtime-v1",
        "destination": destination,
        "data_classes": ["INTERNAL"],
    }


def grant(rt, state, *, destination="d", purpose="x", resource=None, ttl_seconds=3600, max_effect_count=3):
    return es.grant_authorization(
        rt,
        state,
        issuer_role="AUTHORITY",
        issuer_identity="human-orchestrator",
        holder="runtime-v1",
        scope=scope_for(destination, purpose, resource),
        ttl_seconds=ttl_seconds,
        max_effect_count=max_effect_count,
    )


class EffectSafetyLiteTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.rt = FakeRuntime(self.root)

    def tearDown(self):
        self.td.cleanup()

    def test_i1_successful_effect_deduplicates_after_commit(self):
        st = base_state()
        auth = grant(self.rt, st, destination="d", purpose="review transport")
        r1 = es.prepare_effect(
            self.rt, st, operation="send", destination="d", provider="chatgpt-web",
            resource="d", identity="runtime-v1", payload_hash=H, slot="send:1",
            purpose="review transport", authorization_id=auth["authorization_id"],
            classification="INTERNAL", tcb_verified=True,
        )
        self.assertEqual(r1["status"], "INTENT_WRITTEN")
        es.begin_effect(self.rt, st, r1["logical_effect_id"],
                        execution_fence_token=r1["execution_fence_token"])
        es.commit_effect_success(self.rt, st, r1["logical_effect_id"], observation={"ok": True})
        r2 = es.prepare_effect(
            self.rt, st, operation="send", destination="d", provider="chatgpt-web",
            resource="d", identity="runtime-v1", payload_hash=H, slot="send:1",
            purpose="review transport", authorization_id=auth["authorization_id"],
            classification="INTERNAL", tcb_verified=True,
        )
        self.assertTrue(r2["deduplicated"])
        self.assertEqual(r2["status"], "SUCCESS")
        self.assertEqual(len(st["effect_safety_log"]), 1)

    def test_i2_reload_durability_auth_and_write_ahead_intent(self):
        st = base_state("RUN-20260824-150001-iiii")
        auth = grant(self.rt, st)
        es.prepare_effect(
            self.rt, st, operation="send", destination="d", provider="chatgpt-web",
            resource="d", identity="runtime-v1", payload_hash=H, slot="send:1",
            purpose="x", authorization_id=auth["authorization_id"],
            classification="INTERNAL", tcb_verified=True,
        )
        reloaded = self.rt.load_state(st["run_id"])
        self.assertEqual(reloaded["effect_safety"]["status"], "INTENT_WRITTEN")
        self.assertEqual(reloaded["effect_safety"]["authorization_id"], auth["authorization_id"])
        self.assertTrue(reloaded["effect_authorizations"])

    def test_i3_fail_closed_missing_revoked_expired(self):
        st = base_state("RUN-20260824-150002-iiii")
        with self.assertRaises(es.EffectDenied):
            es.prepare_effect(
                self.rt, st, operation="send", destination="d", provider="chatgpt-web",
                resource="d", identity="runtime-v1", payload_hash=H, slot="send:1",
                purpose="x", classification="INTERNAL", tcb_verified=True,
            )
        auth = grant(self.rt, st)
        es.revoke_authorization(self.rt, st, auth["authorization_id"])
        with self.assertRaises(es.EffectDenied):
            es.prepare_effect(
                self.rt, st, operation="send", destination="d", provider="chatgpt-web",
                resource="d", identity="runtime-v1", payload_hash=H, slot="send:1",
                purpose="x", authorization_id=auth["authorization_id"],
                classification="INTERNAL", tcb_verified=True,
            )
        st2 = base_state("RUN-20260824-150003-iiii")
        auth2 = grant(self.rt, st2, ttl_seconds=-1)
        with self.assertRaises(es.EffectDenied):
            es.prepare_effect(
                self.rt, st2, operation="send", destination="d", provider="chatgpt-web",
                resource="d", identity="runtime-v1", payload_hash=H, slot="send:1",
                purpose="x", authorization_id=auth2["authorization_id"],
                classification="INTERNAL", tcb_verified=True,
            )

    def test_i4_expired_default_authorization_does_not_auto_rotate(self):
        st = base_state("RUN-20260824-150004-iiii")
        grant(self.rt, st, ttl_seconds=-1)
        before = len(st["effect_authorizations"])
        with self.assertRaises(es.EffectDenied):
            es.ensure_valid_authorization(self.rt, st, holder="runtime-v1", scope=scope_for())
        self.assertEqual(len(st["effect_authorizations"]), before)

    def test_i5_send_wrapper_denies_missing_authority_without_execute(self):
        rt = self.rt
        sent = {"called": False}
        rt.cmd_send = lambda args: (sent.__setitem__("called", True), 0)[1]
        es.install(rt, {})
        st = base_state("RUN-20260824-150005-iiii")
        rt.save_state(st)

        class A:
            run_id = st["run_id"]
            message = "m"
            message_file = None
            file = None

        code = rt.cmd_send(A())
        self.assertEqual(code, rt.EXIT_HARD_BLOCKED)
        self.assertFalse(sent["called"])
        after = rt.load_state(st["run_id"])
        self.assertEqual(after["status"], "HARD_BLOCKED")
        self.assertIn("EFFECT_SAFETY_DENIED", after["blocked_reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
