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

    def sha256_text(self, b):
        import hashlib
        return hashlib.sha256(b).hexdigest()

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


def base_state():
    return {"run_id": "RUN-20260824-150000-iiii", "revision": 0, "goal": "G",
            "status": "RUNNING", "r_url": "https://chatgpt.com/c/x", "review_epoch": 1}


H = "a" * 64


class EffectSafetyLiteTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.rt = FakeRuntime(self.root)

    def tearDown(self):
        self.td.cleanup()

    def test_i1_reservation_binds_authorization_identity(self):
        st = base_state()
        auth = es.grant_authorization(self.rt, st, holder="runtime-v1")
        r1 = es.record_effect(self.rt, st, operation="send", destination="d", payload_hash=H,
                              slot="send:1", purpose="review transport")
        self.assertEqual(r1["authorization_id"], auth["authorization_id"])
        self.assertEqual(r1["authorization_status"], "GRANTED")
        self.assertEqual(r1["authorization_holder"], "runtime-v1")
        self.assertFalse(r1["deduplicated"])
        r2 = es.record_effect(self.rt, st, operation="send", destination="d", payload_hash=H,
                              slot="send:1", purpose="review transport")
        self.assertTrue(r2["deduplicated"])
        self.assertEqual(len(st["effect_safety_log"]), 1)

    def test_i2_reload_durability_auth_and_effect(self):
        st = base_state()
        es.grant_authorization(self.rt, st)
        es.record_effect(self.rt, st, operation="send", destination="d", payload_hash=H,
                         slot="send:1", purpose="x")
        reloaded = self.rt.load_state(st["run_id"])
        self.assertEqual(reloaded["effect_safety"]["authorization_id"],
                         st["effect_safety"]["authorization_id"])
        self.assertTrue(reloaded["effect_authorizations"])

    def test_i3_fail_closed_missing_revoked_expired(self):
        st = base_state()
        # missing authorization
        with self.assertRaises(es.EffectDenied):
            es.record_effect(self.rt, st, operation="send", destination="d", payload_hash=H,
                             slot="send:1", purpose="x")
        # revoked authorization
        auth = es.grant_authorization(self.rt, st)
        es.revoke_authorization(self.rt, st, auth["authorization_id"])
        with self.assertRaises(es.EffectDenied):
            es.record_effect(self.rt, st, operation="send", destination="d", payload_hash=H,
                             slot="send:1", purpose="x", authorization_id=auth["authorization_id"])
        # expired authorization
        st2 = base_state(); st2["run_id"] = "RUN-20260824-150001-jjjj"
        auth2 = es.grant_authorization(self.rt, st2, ttl_seconds=-1)
        with self.assertRaises(es.EffectDenied):
            es.record_effect(self.rt, st2, operation="send", destination="d", payload_hash=H,
                             slot="send:1", purpose="x", authorization_id=auth2["authorization_id"])

    def test_i5_expired_default_authorization_auto_rotates(self):
        st = base_state()
        es.grant_authorization(self.rt, st, ttl_seconds=-1)  # expired default
        # default selection skips expired; ensure_valid_authorization re-grants live one
        es.ensure_valid_authorization(self.rt, st)
        rec = es.record_effect(self.rt, st, operation="send", destination="d", payload_hash=H,
                               slot="send:1", purpose="x")
        self.assertEqual(rec["authorization_status"], "GRANTED")
        live = [a for a in st["effect_authorizations"].values() if a["status"] == "GRANTED"
                and a["expires_at"] >= es._now_iso()]
        self.assertTrue(live)

    def test_i4_send_wrapper_grants_and_binds(self):
        rt = self.rt
        sent = {"called": False}
        rt.cmd_send = lambda args: (sent.__setitem__("called", True), 0)[1]
        es.install(rt, {})
        st = base_state()
        rt.save_state(st)

        class A:
            run_id = st["run_id"]; message = "m"; file = None
        code = rt.cmd_send(A())
        self.assertEqual(code, 0)
        self.assertTrue(sent["called"])
        after = rt.load_state(st["run_id"])
        self.assertEqual(after["effect_safety"]["status"], "RESERVED")
        self.assertTrue(after["effect_safety"]["authorization_id"])
        self.assertEqual(after["effect_safety"]["authorization_status"], "GRANTED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
