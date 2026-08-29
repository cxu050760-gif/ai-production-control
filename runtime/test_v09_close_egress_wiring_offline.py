#!/usr/bin/env python3
"""T11b egress wiring acceptance: the outbound gate really decides.

V09 CLOSE final batch (BUILDER_RULING_FINALBATCH §3.2). Spec clauses:
V14-FROZEN §31 check 9 "Data Egress permits it"; DATA_EGRESS_POLICY.md
(permission is destination/provider/purpose/contract/authorization specific).

The point of this file is the opposite of a green checkmark: it proves the gate
wired in T11b is a live decision and not a formality. Every positive case is
paired with the negative that would fire if the permission were widened, and the
two later gates (TCB, bound authority) are shown to still refuse on their own.

Scenario construction only (AD-8): contract policy, ``effect_tcb_verified`` and an
authority issued through the product's own ``grant_authorization`` API with an
Authority issuer distinct from the holder. No product default and no gate logic
is altered here, and nothing in this file asserts a relaxed expectation.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

DESTINATION = "https://chatgpt.com/c/11111111-2222-3333-4444-555555555555"
PROVIDER = "chatgpt-web"
IDENTITY = "runtime-v1"
PURPOSE = "review transport"


def _load_rt():
    spec = importlib.util.spec_from_file_location("apc_runtime_core", HERE / "runtime.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


import effect_safety_lite as es  # noqa: E402


class _World:
    """A single run with its gate inputs assembled independently."""

    def __init__(self, *, policy=None, tcb=False, authority=False,
                 classification="INTERNAL", purpose=PURPOSE, destination=DESTINATION):
        self.tmp = tempfile.TemporaryDirectory(prefix="v09-close-egress-")
        root = Path(self.tmp.name)
        self.state_root = root / "state"
        os.environ["APC_RUNTIME_STATE_ROOT"] = str(self.state_root)
        self.rt = _load_rt()
        state = self.rt._new_run("T11b egress wiring scenario", destination, "worker-egress")
        self.run_id = state["run_id"]
        if policy is not None:
            import goal_contract_lite as gc
            gc.persist_contract(self.rt, state, self.gc_build(policy),
                                event="GOAL_CONTRACT_CREATED")
        # No policy => no contract => no projection at all, which is the real
        # fail-closed condition rather than a simulated one.
        es.install(self.rt, {})
        if tcb:
            state["effect_tcb_verified"] = True
        state["effect_data_classification"] = classification
        if authority:
            self.grant(state, purpose=purpose, destination=destination)
        self.rt.save_state(state)
        self.state = self.rt.load_state(self.run_id)

    def gc_build(self, policy):
        import goal_contract_lite as gc
        return gc.build_contract("T11b scenario", ["A"], data_egress_policy=policy)

    def grant(self, state, *, purpose, destination, issuer_role="HUMAN_AUTHORITY",
              issuer_identity="scenario-authority", holder=IDENTITY):
        return es.grant_authorization(
            self.rt, state, issuer_role=issuer_role, issuer_identity=issuer_identity,
            holder=holder, scope={"provider": PROVIDER, "resource": destination,
                                  "purpose": purpose, "identity": holder,
                                  "destination": destination,
                                  "data_classes": ["PUBLIC", "INTERNAL"]},
            max_effect_count=3)

    def send(self, message="review packet"):
        """Run the real gated send path; return (allowed, observation)."""
        state = self.rt.load_state(self.run_id)
        payload_hash = es.sha256_text(message)
        try:
            record = es._prepare_runtime_send(
                self.rt, state, operation="send", destination=DESTINATION,
                payload_hash=payload_hash, slot=f"send:{state.get('review_epoch', 1)}",
                purpose=PURPOSE)
            es._begin_runtime_send(self.rt, state, record)
            return True, record
        except es.EffectDenied as exc:
            return False, str(exc)

    def close(self) -> None:
        self.tmp.cleanup()


PERMITTED = {"default": ["PUBLIC", "INTERNAL"]}


class EgressWiringTests(unittest.TestCase):
    def world(self, **kwargs) -> _World:
        built = _World(**kwargs)
        self.addCleanup(built.close)
        return built

    # --- gate 1: egress -----------------------------------------------------
    def test_policy_absent_denies(self):
        world = self.world(policy=None, tcb=True, authority=True)
        allowed, detail = world.send()
        self.assertFalse(allowed)
        self.assertIn("egress", detail.lower())

    def test_empty_policy_denies(self):
        world = self.world(policy={}, tcb=True, authority=True)
        allowed, detail = world.send()
        self.assertFalse(allowed, "an empty contract policy must not open the gate")

    def test_other_destination_policy_denies(self):
        world = self.world(policy={"https://chatgpt.com/c/elsewhere": ["PUBLIC", "INTERNAL"]},
                       tcb=True, authority=True)
        allowed, detail = world.send()
        self.assertFalse(allowed, "permission is destination-specific (DATA_EGRESS_POLICY)")

    def test_secret_class_denies_even_when_everything_else_permits(self):
        world = self.world(policy={"default": ["PUBLIC", "INTERNAL", "PRIVATE_LOCAL",
                                           "SENSITIVE", "SECRET"]},
                       tcb=True, authority=True, classification="SECRET")
        allowed, detail = world.send()
        self.assertFalse(allowed, "SECRET must stay denied regardless of the policy entry")

    def test_permitted_policy_allows_and_records(self):
        world = self.world(policy=PERMITTED, tcb=True, authority=True)
        allowed, record = world.send()
        self.assertTrue(allowed, f"expected the gate to open, got {record}")
        self.assertEqual(record["destination"], DESTINATION)
        state = world.rt.load_state(world.run_id)
        self.assertTrue(state.get("effect_safety_log"), "the permitted effect must be recorded")

    # --- gate 2: TCB still live --------------------------------------------
    def test_tcb_not_declared_denies_despite_full_egress_permission(self):
        world = self.world(policy=PERMITTED, tcb=False, authority=True)
        allowed, detail = world.send()
        self.assertFalse(allowed)
        self.assertIn("TCB", detail)

    # --- gate 3: bound authority still live --------------------------------
    def test_missing_authority_denies_despite_permission_and_tcb(self):
        world = self.world(policy=PERMITTED, tcb=True, authority=False)
        allowed, detail = world.send()
        self.assertFalse(allowed)
        self.assertIn("authorization", detail.lower())

    def test_self_grant_is_refused_by_the_api(self):
        world = self.world(policy=PERMITTED, tcb=True, authority=False)
        state = world.rt.load_state(world.run_id)
        with self.assertRaises(es.EffectDenied):
            world.grant(state, purpose=PURPOSE, destination=DESTINATION,
                        issuer_identity=IDENTITY, holder=IDENTITY)

    def test_worker_issuer_role_is_refused_by_the_api(self):
        world = self.world(policy=PERMITTED, tcb=True, authority=False)
        state = world.rt.load_state(world.run_id)
        with self.assertRaises(es.EffectDenied):
            world.grant(state, purpose=PURPOSE, destination=DESTINATION, issuer_role="WORKER")

    # --- projection integrity ------------------------------------------------
    def test_projection_bound_to_contract_hash_and_fail_closed_when_stale(self):
        world = self.world(policy=PERMITTED, tcb=True, authority=True)
        state = world.rt.load_state(world.run_id)
        self.assertEqual(state["egress_policy_projection"]["source_contract_hash"],
                         state["goal_contract_hash"])
        # a tampered contract hash must close the gate again, not crash
        state["goal_contract_hash"] = "f" * 64
        world.rt.save_state(state)
        allowed, detail = world.send()
        self.assertFalse(allowed, "hash mismatch must deny")

    def test_legacy_state_without_projection_loads_and_denies(self):
        world = self.world(policy=PERMITTED, tcb=True, authority=True)
        state = world.rt.load_state(world.run_id)
        state.pop("egress_policy_projection", None)
        world.rt.save_state(state)
        allowed, detail = world.send()   # must deny, not raise
        self.assertFalse(allowed)
        self.assertIn("egress", detail.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
