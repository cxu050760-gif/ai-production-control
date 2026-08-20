from __future__ import annotations

"""M2 mechanical Context Capsule tests.

Proves the capsule is projected from canonical durable state, not from AI memory:
- completed facts are mechanical DB-derived strings,
- OUTCOME_UNKNOWN / unresolved effects are preserved (never silently dropped as done),
- the capsule is revision-bound and fence-verifiable,
- a fabricated/stale capsule fails verification.
"""

import copy
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aicontrol.context import build_mechanical_capsule, verify_capsule  # noqa: E402
from aicontrol.controller import Controller  # noqa: E402
from aicontrol.store import GateDenied  # noqa: E402
from aicontrol.util import read_json, sha256_text, write_json  # noqa: E402


class ContextFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="aicontrol-ctx-")
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
            goal="context capsule fixture", expected_final_artifact="fixture",
            acceptance_criteria=["A01"], data_classification="PUBLIC",
        )
        self.task_id = self.task["task_id"]

    def tearDown(self) -> None:
        self.controller.close()
        self.temporary.cleanup()

    def create_unknown_effect(self) -> None:
        # Create and start an external effect whose outcome is unknown, so the
        # capsule must surface it as UNKNOWN rather than pretending completion.
        lease = self.controller.acquire_lease()
        scope = {"provider": "test", "destination": "test", "purpose": "ctx",
                 "effect_type": "AI_MESSAGE", "data_classes": ["PUBLIC"]}
        nonce = self.controller.store.issue_decision_nonce(self.task_id, scope, user_decision_reference="ctx")
        auth = self.controller.store.grant_authorization(
            self.task_id, nonce["decision_nonce"], scope, provider="test", resource="test",
            purpose="ctx", effect_type="AI_MESSAGE", max_effect_count=1,
        )
        intent = {
            "task_id": self.task_id,
            "operation": "TEST_EXTERNAL_EFFECT",
            "provider": "test", "destination": "test", "expected_account": "credential-ref:test",
            "resource": "test", "payload_hash": sha256_text("p"), "critical_params": {},
            "purpose": "ctx", "logical_effect_slot": "CTX_UNKNOWN", "retry_semantics": "RECONCILE_REQUIRED",
            "impact": "LOW", "reversibility": "REVERSIBLE", "effect_scope": "EXTERNAL",
        }
        try:
            self.controller.execute_effect(
                task_id=self.task_id, lease=lease, authorization_id=auth["authorization_id"],
                context_fence=self.task["context_fence"], resource_id="ctx:resource",
                resource_hash=sha256_text("r"), intent=intent,
                adapter=lambda _: None, egress_permitted=True,
            )
        except Exception:
            pass  # malformed adapter -> OUTCOME_UNKNOWN by design


class MechanicalCapsuleTests(ContextFixture):
    def test_capsule_is_mechanical_and_revision_bound(self) -> None:
        capsule = build_mechanical_capsule(self.controller.store, self.task_id)
        self.assertEqual(capsule["source"], "CANONICAL_STATE_PROJECTION")
        self.assertEqual(capsule["task_id"], self.task_id)
        self.assertEqual(capsule["state_revision"], self.controller.store.state_head())
        # completed facts are DB-derived facts, deterministic
        self.assertTrue(any(f.startswith("goal_contract:version=") for f in capsule["completed_facts"]))
        self.assertTrue(verify_capsule(capsule))

    def test_unknown_effect_is_preserved_not_dropped(self) -> None:
        self.create_unknown_effect()
        capsule = build_mechanical_capsule(self.controller.store, self.task_id)
        self.assertTrue(
            capsule["unknown_effects"],
            "an OUTCOME_UNKNOWN effect must appear in the capsule, never silently dropped",
        )
        self.assertTrue(
            any(e["status"] in ("EFFECT_START_COMMITTED", "OUTCOME_UNKNOWN") for e in capsule["unknown_effects"])
        )

    def test_unknown_not_rewritten_as_completed(self) -> None:
        self.create_unknown_effect()
        capsule = build_mechanical_capsule(self.controller.store, self.task_id)
        # A fact that ends with unresolved_effects=0 must NOT be claimed when there is an unknown effect.
        self.assertFalse(any(f == "unresolved_effects=0" for f in capsule["completed_facts"]))
        n = len(capsule["unknown_effects"])
        self.assertIn(f"unresolved_effects={n}", capsule["completed_facts"])

    def test_fabricated_fence_fails_verification(self) -> None:
        capsule = build_mechanical_capsule(self.controller.store, self.task_id)
        forged = dict(capsule)
        forged["provable_fence"] = "0" * 64
        self.assertFalse(verify_capsule(forged))
        # stale revision: change the fact then verify fails
        stale = dict(capsule)
        stale["state_revision"] = 0
        stale["completed_facts"] = [f.replace("state_revision=", "state_revision=0") for f in stale["completed_facts"]]
        self.assertFalse(verify_capsule(stale))

    def test_capsule_not_built_from_caller_memory(self) -> None:
        # No caller-supplied "completed work" prose exists in the mechanical function;
        # returned fields are either canonical identifiers or DB-derived counters.
        capsule = build_mechanical_capsule(self.controller.store, self.task_id)
        for key in ("current_objective", "next_required_steps", "critical_decisions", "worker_state"):
            self.assertNotIn(key, capsule)


if __name__ == "__main__":
    unittest.main()