"""Offline tests for the V0.7 Strategic Brain scaffold (V07-INTEGRATE-1).

Proves the inert-by-default contract: with the default (disabled) module-level
instance, plan/C-hook/reuse-registry make no changes and return None; enabling is
a pure opt-in flag with no external effects. Isolated; does not touch runtime.
"""
import unittest
from importlib import import_module

sb = import_module("strategic_brain")


class TestStrategicBrainInert(unittest.TestCase):
    def test_brain_default_disabled(self):
        self.assertFalse(sb.brain.enabled)
        self.assertIsNone(sb.brain.plan({"x": 1}))
        self.assertIsNone(sb.brain.route_correction_hook({"plan": []}))
        self.assertEqual(len(sb.brain.reuse_registry), 0)

    def test_registry_inert_when_disabled(self):
        reg = sb.StrategicReuseRegistry(enabled=False)
        self.assertFalse(reg.register("a", "src"))
        self.assertIsNone(reg.lookup("a"))
        self.assertEqual(len(reg), 0)

    def test_enable_is_opt_in_flag_only(self):
        b = sb.StrategicBrain(enabled=False)
        b.set_enabled(True)
        self.assertTrue(b.enabled)
        plan = b.plan({"g": "t"})
        self.assertIsNotNone(plan)
        self.assertEqual(plan["source"], "strategic-brain")
        self.assertTrue(b.reuse_registry.register("k", "s"))
        self.assertEqual(b.reuse_registry.lookup("k"), "s")
        # disable again -> inert, no leftover effects from earlier calls
        b.set_enabled(False)
        self.assertIsNone(b.plan({}))
        self.assertIsNone(b.route_correction_hook({}))
        self.assertIsNone(b.reuse_registry.lookup("k"))

    def test_module_level_instance_remains_inert(self):
        # importing the module must not have silently enabled anything
        self.assertFalse(sb.brain.enabled)
        self.assertEqual(len(sb.brain.reuse_registry), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)