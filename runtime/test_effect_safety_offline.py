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

    def test_i1_record_deduplicated_hash_bound(self):
        st = base_state()
        r1 = es.record_effect(self.rt, st, operation="send", destination="d", payload_hash=H,
                              slot="send:1", purpose="review transport")
        self.assertFalse(r1["deduplicated"])
        self.assertTrue(r1["logical_effect_id"])
        r2 = es.record_effect(self.rt, st, operation="send", destination="d", payload_hash=H,
                              slot="send:1", purpose="review transport")
        self.assertTrue(r2["deduplicated"])
        self.assertEqual(r2["logical_effect_id"], r1["logical_effect_id"])
        self.assertEqual(len(st["effect_safety_log"]), 1)  # dedup: only one stored record
        events = [e for e, _ in self.rt.journal_events if e == "EFFECT_RESERVED"]
        self.assertEqual(len(events), 2)

    def test_i2_reload_durability(self):
        st = base_state()
        es.record_effect(self.rt, st, operation="send", destination="d", payload_hash=H,
                         slot="send:1", purpose="x")
        reloaded = self.rt.load_state(st["run_id"])
        self.assertEqual(reloaded["effect_safety"]["logical_effect_id"],
                         st["effect_safety"]["logical_effect_id"])
        self.assertEqual(len(reloaded["effect_safety_log"]), 1)

    def test_i3_denied_precondition_fails_closed(self):
        st = base_state()
        with self.assertRaises(es.EffectDenied):
            es.record_effect(self.rt, st, operation="send", destination="d", payload_hash=H,
                             slot="send:1", purpose="x", capability_permitted=False)
        with self.assertRaises(es.EffectDenied):
            es.record_effect(self.rt, st, operation="send", destination="d", payload_hash="zz",
                             slot="send:1", purpose="x")

    def test_i4_send_wrapper_records_and_passes(self):
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
        self.assertEqual(after["effect_safety"]["operation"], "send")


if __name__ == "__main__":
    unittest.main(verbosity=2)
