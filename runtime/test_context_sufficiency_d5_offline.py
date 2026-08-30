#!/usr/bin/env python3
"""D5 offline tests: runtime/context_sufficiency.py（宪法 §55 五分支路由）。"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import context_sufficiency as cs  # noqa: E402


def clean_env() -> dict:
    """过滤超长环境变量 + 保证子进程 UTF-8 安全（见 test_task_graph_d5_offline.clean_env 说明）。"""
    env = {k: v for k, v in os.environ.items() if len(v) <= 30000}
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("SYSTEMROOT", r"C:\Windows")
    env.setdefault("SYSTEMDRIVE", "C:")
    return env


def _registry(brains: list, providers: list) -> dict:
    return {
        "sections": {
            "brains": [
                {"id": bid, "type": btype, "status": status}
                for bid, btype, status in brains
            ],
            "providers": [
                {"id": pid, "status": status}
                for pid, status in providers
            ],
        }
    }


# 默认策略：1 个 Brain + 1 个 Provider -> 分支 ①② 不可用；allow_human=True
_NO_FALLBACK_REGISTRY = _registry(
    brains=[("brain-solo", "API_MODEL", "official")],
    providers=[("provider-solo", "official")],
)
# 分支① 可用：>=2 官方 API_MODEL Brain
_FALLBACK_REGISTRY = _registry(
    brains=[("brain-weak", "API_MODEL", "official"),
            ("brain-strong", "API_MODEL", "official")],
    providers=[("provider-solo", "official")],
)
# 分支② 可用：>=2 官方 Provider，但 Brain 只有 1 个
_PROVIDER_REGISTRY = _registry(
    brains=[("brain-solo", "API_MODEL", "official")],
    providers=[("provider-a", "official"), ("provider-b", "official")],
)


class BranchTests(unittest.TestCase):
    def test_t01_switch_local_brain(self):
        out = cs.route(
            {"a": {"value": 1}},
            ["a", "b"],
            registry=_FALLBACK_REGISTRY)
        self.assertEqual(out["decision"], "SWITCH_LOCAL_BRAIN")
        self.assertEqual(out["completeness"]["missing"], 1)
        self.assertEqual(out["routing_action"]["branch"], "SWITCH_LOCAL_BRAIN")
        self.assertIn("brain-weak", out["routing_action"]["fallback_chain"])

    def test_t02_switch_allowed_provider(self):
        out = cs.route(
            {"a": {"value": 1}},
            ["a", "b"],
            registry=_PROVIDER_REGISTRY)
        self.assertEqual(out["decision"], "SWITCH_ALLOWED_PROVIDER")
        self.assertIn("provider-a", out["routing_action"]["allowed_providers"])
        self.assertEqual(out["branches_tried"][0]["branch"], "SWITCH_LOCAL_BRAIN")
        self.assertTrue(out["branches_tried"][0]["skipped"])

    def test_t03_desensitize_retry(self):
        out = cs.route(
            {"contact": {"value": "13812345678", "source": "ctx"}},
            ["contact", "secret"],
            registry=_NO_FALLBACK_REGISTRY)
        self.assertEqual(out["decision"], "DESENSITIZE_RETRY")
        masked = out["routing_action"]["masked_keys"]
        self.assertEqual(masked[0]["key"], "contact")
        self.assertIn("****", masked[0]["masked_value"])
        self.assertNotIn("13812345678", masked[0]["masked_value"])

    def test_t04_human_authorization(self):
        out = cs.route(
            {"a": {"value": 1}},
            ["a", "b", "c"],
            registry=_NO_FALLBACK_REGISTRY)
        self.assertEqual(out["decision"], "HUMAN_AUTHORIZATION")
        self.assertIsNotNone(out["authorization_request"])
        self.assertIn("b", out["authorization_request"]["requested_keys"])
        self.assertIn("request_id", out["authorization_request"])

    def test_t05_blocked_when_human_disallowed(self):
        policy = cs.default_policy()
        policy["allow_human_authorization"] = False
        out = cs.route(
            {"a": {"value": 1}},
            ["a", "b"],
            registry=_NO_FALLBACK_REGISTRY,
            policy=policy)
        self.assertEqual(out["decision"], "BLOCKED")
        self.assertIsNotNone(out["blocked_reason"])
        self.assertIsNone(out["authorization_request"])

    def test_t06_sufficient_default_policy(self):
        out = cs.route(
            {"a": {"value": 1}, "b": {"value": 2}},
            ["a", "b"],
            registry=_NO_FALLBACK_REGISTRY)
        self.assertEqual(out["decision"], "SUFFICIENT")
        self.assertEqual(out["completeness"]["ratio"], 1.0)

    def test_t07_trust_threshold_routes(self):
        # trust 0.1 < 0.5 -> 视为缺失 -> 触发路由
        out = cs.route(
            {"a": {"value": 1, "trust": 0.1}},
            ["a"],
            registry=_FALLBACK_REGISTRY)
        self.assertEqual(out["decision"], "SWITCH_LOCAL_BRAIN")
        self.assertEqual(out["completeness"]["missing"], 1)


class PolicyAndMaskTests(unittest.TestCase):
    def test_t08_default_policy_values(self):
        p = cs.default_policy()
        self.assertEqual(p["completeness_threshold"], 1.0)
        self.assertEqual(p["trust_threshold"], 0.5)
        self.assertTrue(p["allow_human_authorization"])

    def test_t09_policy_file_override(self):
        td = tempfile.TemporaryDirectory()
        p = Path(td.name) / "policy.json"
        p.write_text(json.dumps({
            "context_sufficiency": {"allow_human_authorization": False}
        }, ensure_ascii=False), encoding="utf-8")
        out = cs.route({"a": {"value": 1}}, ["a", "b"],
                       registry=_NO_FALLBACK_REGISTRY,
                       policy=cs._load_policy(str(p)))
        self.assertEqual(out["decision"], "BLOCKED")
        td.cleanup()

    def test_t10_mask_value(self):
        self.assertIn("****", cs.mask_value("13812345678"))
        self.assertIn("****", cs.mask_value("user@example.com"))
        self.assertIn("****", cs.mask_value("password=hunter2"))
        self.assertIn("****", cs.mask_value("Bearer abcdefghijklmnop123456"))
        # 掩码结果不含原文
        self.assertNotIn("hunter2", cs.mask_value("password=hunter2"))

    def test_t11_sensitive_detection(self):
        self.assertTrue(cs._is_sensitive_key("api_key"))
        self.assertTrue(cs._is_sensitive_key("password"))
        self.assertTrue(cs._is_sensitive_value("13812345678"))
        self.assertTrue(cs._is_sensitive_value("authorization: Bearer abc123def456"))
        self.assertFalse(cs._is_sensitive_value("hello world"))


class RegistryAndCliTests(unittest.TestCase):
    def test_t12_missing_registry_falls_back(self):
        out = cs.route({"a": {"value": 1}}, ["a", "b"],
                       registry_path="C:/definitely/missing/registry.json")
        # registry 缺失 -> 无可用 Brain/Provider -> 分支 ①② 不可用
        self.assertIn(out["decision"], ("DESENSITIZE_RETRY", "HUMAN_AUTHORIZATION", "BLOCKED"))

    def test_t13_no_required_info(self):
        out = cs.route({"a": 1}, [])
        self.assertEqual(out["decision"], "SUFFICIENT")

    def test_t14_cli_route(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        ctx = root / "ctx.json"
        ctx.write_text(json.dumps({"a": {"value": 1}}, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(HERE / "context_sufficiency.py"), "route",
             "--context", str(ctx), "--required", "a,b"],
            capture_output=True, text=True, encoding="utf-8", env=clean_env())
        self.assertEqual(r.returncode, 0, (r.stdout or "") + (r.stderr or ""))
        data = json.loads(r.stdout)
        self.assertIn(data["decision"], (
            "SWITCH_LOCAL_BRAIN", "SWITCH_ALLOWED_PROVIDER",
            "DESENSITIZE_RETRY", "HUMAN_AUTHORIZATION", "BLOCKED"))
        td.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
