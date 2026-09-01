"""R-Adapter 离线测试（D1）：健康探测 / 仲裁 pick / fallback 链 / review mock。

全部离线：使用 tmp 目录 fixture；不触真实 API key（用注入 env 模拟 key 存在性）；
review mock 走 LiteLLM Router + mock_response（零网络、零额度）。
"""

import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
from importlib import import_module
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
r_adapter = import_module("r_adapter")


def _write_config(tmp: Path, providers) -> Path:
    cfg = {"schema": "R_ADAPTER_CONFIG", "schema_version": 1,
           "default_timeout_sec": 30, "providers": providers}
    p = tmp / "r_adapter.config.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return p


def _provider(pid, priority=1, key_env="", kind="api_model", model="deepseek/deepseek-chat",
              provider="deepseek", health=None, name=None):
    return {
        "id": pid, "name": name or pid, "kind": kind, "type": "API_MODEL",
        "model": model, "provider": provider, "api_key_env": key_env,
        "priority": priority, "health_timeout_sec": 5,
        "health_check": health,
    }


class TestConfigLoad(unittest.TestCase):
    def test_load_config_parses_providers(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_config(Path(d), [_provider("r-a", priority=1)])
            cfg = r_adapter.load_config(str(p))
            self.assertEqual(cfg["schema"], "R_ADAPTER_CONFIG")
            self.assertEqual(len(cfg["providers"]), 1)
            self.assertEqual(cfg["providers"][0]["id"], "r-a")

    def test_load_config_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            r_adapter.load_config("no-such-file.json")

    def test_load_config_bad_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.json"
            p.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ValueError):
                r_adapter.load_config(str(p))

    def test_load_config_empty_providers(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "empty.json"
            p.write_text(json.dumps({"providers": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                r_adapter.load_config(str(p))


class TestHealthProbe(unittest.TestCase):
    def _clean_env(self):
        saved = {}
        for name in ("DEEPSEEK_API_KEY", "FAKE_KEY", "OPENAI_API_KEY"):
            saved[name] = os.environ.get(name)
            os.environ.pop(name, None)
        return saved

    def _restore_env(self, saved):
        for name, val in saved.items():
            if val is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = val

    def test_unconfigured_when_no_key_env_declared(self):
        p = _provider("r-a", key_env="")
        rec = r_adapter.probe_provider(p, env={})
        self.assertEqual(rec["status"], "UNCONFIGURED")

    def test_unconfigured_when_env_var_missing(self):
        saved = self._clean_env()
        try:
            p = _provider("r-a", key_env="DEEPSEEK_API_KEY")
            rec = r_adapter.probe_provider(p, env={})
            self.assertEqual(rec["status"], "UNCONFIGURED")
            self.assertIn("DEEPSEEK_API_KEY", rec["reason"])
        finally:
            self._restore_env(saved)

    def test_unconfigured_when_web_session(self):
        p = _provider("r-a", kind="web_session", key_env="")
        rec = r_adapter.probe_provider(p, env={})
        self.assertEqual(rec["status"], "UNCONFIGURED")
        self.assertIn("会话 URL", rec["reason"])

    def test_up_when_key_set_and_file_health_ok(self):
        with tempfile.TemporaryDirectory() as d:
            probe_file = Path(d) / "probe.exe"
            probe_file.write_text("", encoding="utf-8")
            p = _provider("r-a", key_env="FAKE_KEY",
                          health={"kind": "file", "path": str(probe_file)})
            rec = r_adapter.probe_provider(p, env={"FAKE_KEY": "sk-test"})
            self.assertEqual(rec["status"], "UP")

    def test_down_when_key_set_and_file_health_missing(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "missing.exe"
            p = _provider("r-a", key_env="FAKE_KEY",
                          health={"kind": "file", "path": str(missing)})
            rec = r_adapter.probe_provider(p, env={"FAKE_KEY": "sk-test"})
            self.assertEqual(rec["status"], "DOWN")

    def test_up_when_key_set_and_port_health_ok(self):
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            port = srv.getsockname()[1]
            p = _provider("r-a", key_env="FAKE_KEY",
                          health={"kind": "port", "host": "127.0.0.1", "port": port,
                                  "timeout_sec": 2})
            rec = r_adapter.probe_provider(p, env={"FAKE_KEY": "sk-test"})
            self.assertEqual(rec["status"], "UP")

    def test_health_probe_all_summary(self):
        with tempfile.TemporaryDirectory() as d:
            providers = [
                _provider("r-a", priority=1, key_env=""),
                _provider("r-b", priority=2, key_env="MISSING_KEY"),
            ]
            p = _write_config(Path(d), providers)
            cfg = r_adapter.load_config(str(p))
            res = r_adapter.health_probe_all(cfg, env={})
            self.assertTrue(res["ok"])
            self.assertEqual(res["summary"].get("UNCONFIGURED", 0), 2)
            self.assertEqual(len(res["providers"]), 2)


class TestPick(unittest.TestCase):
    def test_pick_all_unconfigured_selects_highest_priority_degraded(self):
        with tempfile.TemporaryDirectory() as d:
            providers = [
                _provider("r-low", priority=5, key_env=""),
                _provider("r-high", priority=1, key_env=""),
                _provider("r-mid", priority=3, key_env=""),
            ]
            p = _write_config(Path(d), providers)
            cfg = r_adapter.load_config(str(p))
            res = r_adapter.pick_provider(cfg, env={})
            self.assertTrue(res["ok"])
            self.assertEqual(res["selected"]["id"], "r-high")
            self.assertTrue(res["degraded"])
            # fallback 链按 priority 升序
            chain = [x["id"] for x in res["fallback_chain"]]
            self.assertEqual(chain, ["r-high", "r-mid", "r-low"])

    def test_pick_prefers_up_over_higher_priority_unconfigured(self):
        with tempfile.TemporaryDirectory() as d:
            probe_file = Path(d) / "up.exe"
            probe_file.write_text("", encoding="utf-8")
            providers = [
                _provider("r-up", priority=9, key_env="FAKE_KEY",
                          health={"kind": "file", "path": str(probe_file)}),
                _provider("r-unconf", priority=1, key_env=""),
            ]
            p = _write_config(Path(d), providers)
            cfg = r_adapter.load_config(str(p))
            env = {"FAKE_KEY": "sk-test"}
            res = r_adapter.pick_provider(cfg, env=env)
            self.assertEqual(res["selected"]["id"], "r-up")
            self.assertEqual(res["selected"]["status"], "UP")
            self.assertFalse(res["degraded"])

    def test_pick_prefer_up_wins(self):
        with tempfile.TemporaryDirectory() as d:
            f1 = Path(d) / "a.exe"; f1.write_text("", encoding="utf-8")
            f2 = Path(d) / "b.exe"; f2.write_text("", encoding="utf-8")
            providers = [
                _provider("r-a", priority=1, key_env="K_A",
                          health={"kind": "file", "path": str(f1)}),
                _provider("r-b", priority=2, key_env="K_B",
                          health={"kind": "file", "path": str(f2)}),
            ]
            p = _write_config(Path(d), providers)
            cfg = r_adapter.load_config(str(p))
            env = {"K_A": "x", "K_B": "y"}
            res = r_adapter.pick_provider(cfg, prefer="r-b", env=env)
            self.assertEqual(res["selected"]["id"], "r-b")
            self.assertTrue(res["prefer_used"])

    def test_pick_prefer_not_up_falls_back(self):
        with tempfile.TemporaryDirectory() as d:
            f1 = Path(d) / "a.exe"; f1.write_text("", encoding="utf-8")
            providers = [
                _provider("r-a", priority=1, key_env="K_A",
                          health={"kind": "file", "path": str(f1)}),
                _provider("r-b", priority=2, key_env=""),
            ]
            p = _write_config(Path(d), providers)
            cfg = r_adapter.load_config(str(p))
            env = {"K_A": "x"}
            # prefer r-b（UNCONFIGURED）不采纳 -> 回退到 UP 的 r-a
            res = r_adapter.pick_provider(cfg, prefer="r-b", env=env)
            self.assertEqual(res["selected"]["id"], "r-a")
            self.assertFalse(res["prefer_used"])

    def test_fallback_chain_sorted_by_priority(self):
        with tempfile.TemporaryDirectory() as d:
            providers = [
                _provider("r-c", priority=30),
                _provider("r-a", priority=1),
                _provider("r-b", priority=10),
            ]
            p = _write_config(Path(d), providers)
            cfg = r_adapter.load_config(str(p))
            res = r_adapter.pick_provider(cfg, env={})
            chain = [x["id"] for x in res["fallback_chain"]]
            self.assertEqual(chain, ["r-a", "r-b", "r-c"])


class TestReviewMock(unittest.TestCase):
    def _cfg(self, tmp):
        providers = [
            _provider("r-a", priority=1, key_env=""),
            _provider("r-b", priority=2, key_env="DEEPSEEK_API_KEY"),
        ]
        p = _write_config(Path(tmp), providers)
        return r_adapter.load_config(str(p))

    def test_review_mock_pass(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(Path(d))
            res = r_adapter.do_review(cfg, mode="mock", mock_verdict="PASS",
                                     payload={"run_id": "RUN-1"})
            self.assertTrue(res["ok"])
            self.assertEqual(res["mode"], "mock")
            self.assertEqual(res["verdict"], "PASS")
            self.assertEqual(res["provider_used"], "mock-r")

    def test_review_mock_rework(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(Path(d))
            res = r_adapter.do_review(cfg, mode="mock", mock_verdict="REWORK",
                                     payload={"run_id": "RUN-2", "goal": "修复格式"})
            self.assertTrue(res["ok"])
            self.assertEqual(res["verdict"], "REWORK")
            self.assertIn("REWORK", res["raw_text"])

    def test_review_real_without_keys_returns_unconfigured(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(Path(d))
            res = r_adapter.do_review(cfg, mode="real", mock_verdict="PASS",
                                     payload={}, env={})
            self.assertFalse(res["ok"])
            self.assertEqual(res["error"], "UNCONFIGURED")

    def test_parse_verdict(self):
        self.assertEqual(r_adapter.parse_verdict("===REVIEW_VERDICT=== PASS\nbody"), "PASS")
        self.assertEqual(r_adapter.parse_verdict("===REVIEW_VERDICT=== REWORK\nbody"), "REWORK")
        self.assertEqual(r_adapter.parse_verdict("no marker, but REWORK inside"), "REWORK")
        self.assertEqual(r_adapter.parse_verdict("nothing here"), "UNKNOWN")


class TestNoLitellmOrdering(unittest.TestCase):
    """DEF-D1b 回归：litellm 不可用时的检查顺序。

    模拟 litellm 缺失（sys.modules['litellm']=None → import 抛 ImportError）：
      - health / pick 不依赖 litellm，应正常工作；
      - review --mode real 无 key → UNCONFIGURED（先查 keyed，不碰 litellm）；
      - review --mode real 有 key → LITELLM_NOT_INSTALLED；
      - review --mode mock → LITELLM_NOT_INSTALLED。
    """

    def _cfg(self, tmp):
        providers = [
            _provider("r-a", priority=1, key_env=""),
            _provider("r-b", priority=2, key_env="DEEPSEEK_API_KEY"),
        ]
        p = _write_config(Path(tmp), providers)
        return r_adapter.load_config(str(p))

    def test_health_works_without_litellm(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(Path(d))
            with mock.patch.dict(sys.modules, {"litellm": None}):
                res = r_adapter.health_probe_all(cfg, env={})
            self.assertTrue(res["ok"])
            self.assertEqual(res["summary"].get("UNCONFIGURED", 0), 2)

    def test_pick_works_without_litellm(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(Path(d))
            with mock.patch.dict(sys.modules, {"litellm": None}):
                res = r_adapter.pick_provider(cfg, env={})
            self.assertTrue(res["ok"])
            self.assertEqual(res["selected"]["id"], "r-a")

    def test_review_real_no_key_unconfigured_without_litellm(self):
        # DEF-D1b 核心：无 litellm + real 无 key -> UNCONFIGURED（不是 LITELLM_NOT_INSTALLED）
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(Path(d))
            with mock.patch.dict(sys.modules, {"litellm": None}):
                res = r_adapter.do_review(cfg, mode="real", mock_verdict="PASS",
                                          payload={}, env={})
            self.assertFalse(res["ok"])
            self.assertEqual(res["error"], "UNCONFIGURED")

    def test_review_real_with_key_requires_litellm(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(Path(d))
            env = {"DEEPSEEK_API_KEY": "sk-test"}
            with mock.patch.dict(sys.modules, {"litellm": None}):
                res = r_adapter.do_review(cfg, mode="real", mock_verdict="PASS",
                                          payload={}, env=env)
            self.assertFalse(res["ok"])
            self.assertEqual(res["error"], "LITELLM_NOT_INSTALLED")

    def test_review_mock_requires_litellm(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(Path(d))
            with mock.patch.dict(sys.modules, {"litellm": None}):
                res = r_adapter.do_review(cfg, mode="mock", mock_verdict="PASS",
                                          payload={})
            self.assertFalse(res["ok"])
            self.assertEqual(res["error"], "LITELLM_NOT_INSTALLED")


class TestDef1RealPickScope(unittest.TestCase):
    """DEF-1（架构会签）回归：real 模式 pick 仅对 keyed provider 仲裁。

    场景：web_session（priority=1，恒 UNCONFIGURED，无 key）+ api_model（priority=2，
    有 key）。修复前 pick 在全部 provider 上仲裁 → 选中 web_session → Router.completion
    BadRequestError → 误报 REAL_CALL_FAILED；修复后 pick 只在 keyed 内仲裁。
    """

    def _cfg(self, tmp):
        providers = [
            _provider("r-web", priority=1, kind="web_session", key_env="",
                      model="chatgpt-web", provider="chatgpt-web"),
            _provider("r-api", priority=2, key_env="DEEPSEEK_API_KEY"),
        ]
        p = _write_config(Path(tmp), providers)
        return r_adapter.load_config(str(p))

    def _fake_router(self):
        """记录 model 参数并返回 PASS 的假 Router（避免真实网络调用）。"""
        class _FakeRouter:
            def __init__(self):
                self.calls = []
            def completion(self, model, messages, max_tokens):
                self.calls.append(model)
                return SimpleNamespace(choices=[
                    SimpleNamespace(message=SimpleNamespace(
                        content="===REVIEW_VERDICT=== PASS\n\n===NEXT_ACTION===\nok"))])
        return _FakeRouter()

    def test_real_pick_scoped_to_keyed_not_web_session(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(Path(d))
            fake = self._fake_router()
            env = {"DEEPSEEK_API_KEY": "sk-test"}
            with mock.patch.object(r_adapter, "_build_router_real", return_value=fake):
                res = r_adapter.do_review(cfg, mode="real", mock_verdict="PASS",
                                          payload={}, env=env)
            # 选中 keyed 的 r-api（而不是 priority=1 但无 key 的 r-web）
            self.assertTrue(res["ok"])
            self.assertEqual(res["provider_used"], "r-api")
            self.assertEqual(fake.calls, ["r-api"])

    def test_real_partial_keyed_pick_prefer_within_keyed(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(Path(d))
            fake = self._fake_router()
            env = {"DEEPSEEK_API_KEY": "sk-test"}
            # prefer 指向无 key 的 r-web 不采纳（不在 keyed 内）→ 回退到 r-api
            with mock.patch.object(r_adapter, "_build_router_real", return_value=fake):
                res = r_adapter.do_review(cfg, mode="real", mock_verdict="PASS",
                                          payload={}, prefer="r-web", env=env)
            self.assertTrue(res["ok"])
            self.assertEqual(res["provider_used"], "r-api")

    def test_real_all_no_key_unconfigured(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(Path(d))
            res = r_adapter.do_review(cfg, mode="real", mock_verdict="PASS",
                                      payload={}, env={})
            self.assertFalse(res["ok"])
            self.assertEqual(res["error"], "UNCONFIGURED")


class TestCLIExitCodes(unittest.TestCase):
    def test_health_cli_exit_0(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_config(Path(d), [_provider("r-a", priority=1, key_env="")])
            code = r_adapter.main(["health", "--config", str(p)])
            self.assertEqual(code, 0)

    def test_review_mock_cli_exit_0(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_config(Path(d), [_provider("r-a", priority=1, key_env="")])
            code = r_adapter.main(["review", "--config", str(p), "--mode", "mock",
                                   "--mock-verdict", "PASS"])
            self.assertEqual(code, 0)

    def test_review_bad_mock_verdict_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_config(Path(d), [_provider("r-a", priority=1, key_env="")])
            code = r_adapter.main(["review", "--config", str(p), "--mode", "mock",
                                   "--mock-verdict", "MAYBE"])
            self.assertEqual(code, 2)

    def test_review_real_no_key_cli_exit_1(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_config(Path(d), [_provider("r-a", priority=1, key_env="NOPE_KEY")])
            code = r_adapter.main(["review", "--config", str(p), "--mode", "real"])
            self.assertEqual(code, 1)

    def test_config_error_exit_1(self):
        code = r_adapter.main(["health", "--config", "no-such-config.json"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
