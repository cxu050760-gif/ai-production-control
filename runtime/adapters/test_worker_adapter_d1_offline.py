"""Worker-Adapter 离线测试（D1）：run mock / run cli / 超时 / 退出码 / list / health。

全部离线：mock 模式零消耗；cli 模式只用本机 python 无害命令（不触真实 AI worker）。
"""

import json
import os
import sys
import tempfile
import unittest
from importlib import import_module
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
worker_adapter = import_module("worker_adapter")

PY = "C:/Users/17838/AppData/Local/Programs/Python/Python312/python.exe"


def _write_config(tmp: Path, workers) -> Path:
    cfg = {"schema": "WORKER_ADAPTER_CONFIG", "schema_version": 1,
           "default_timeout_sec": 300, "workers": workers}
    p = tmp / "worker_adapter.config.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return p


def _worker(wid, entry_cmd, health_path=None, timeout=None, cwd=None):
    return {
        "id": wid, "name": wid, "role": "worker", "type": "LOCAL_RUNTIME",
        "status": "official",
        "entry": {"kind": "command", "command": entry_cmd, "cwd": cwd},
        "health_check": {"kind": "file", "path": health_path} if health_path else None,
        "timeout_sec": timeout,
        "adapter": "adapter-local-command",
        "capabilities": ["cap-local-python"],
    }


def _goal_file(tmp: Path, text: str = "产出一份测试报告") -> Path:
    gf = tmp / "goal.txt"
    gf.write_text(text, encoding="utf-8")
    return gf


class TestRunMock(unittest.TestCase):
    def test_run_mock_success(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg_p = _write_config(tmp, [_worker("w-python", [PY, "-"])])
            gf = _goal_file(tmp)
            cfg = worker_adapter.load_config(str(cfg_p))
            res = worker_adapter.run_worker(cfg, worker_id="w-python",
                                            goal=gf.read_text(encoding="utf-8"),
                                            mode="mock", timeout=None,
                                            mock_result={}, mock_exit_code=0)
            self.assertTrue(res["ok"])
            self.assertEqual(res["exit_code"], 0)
            self.assertEqual(res["mode"], "mock")
            self.assertEqual(res["result"]["result"], "mock worker completed")
            self.assertIn("产出一份测试报告", res["result"]["goal_excerpt"])

    def test_run_mock_preset_result(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg_p = _write_config(tmp, [_worker("w-python", [PY, "-"])])
            gf = _goal_file(tmp)
            cfg = worker_adapter.load_config(str(cfg_p))
            res = worker_adapter.run_worker(cfg, worker_id="w-python",
                                            goal=gf.read_text(encoding="utf-8"),
                                            mode="mock", timeout=None,
                                            mock_result={"result": "PRESET_OK"},
                                            mock_exit_code=0)
            self.assertEqual(res["result"]["result"], "PRESET_OK")

    def test_run_mock_exit_code_1(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg_p = _write_config(tmp, [_worker("w-python", [PY, "-"])])
            gf = _goal_file(tmp)
            cfg = worker_adapter.load_config(str(cfg_p))
            res = worker_adapter.run_worker(cfg, worker_id="w-python",
                                            goal=gf.read_text(encoding="utf-8"),
                                            mode="mock", timeout=None,
                                            mock_result={}, mock_exit_code=1)
            self.assertFalse(res["ok"])
            self.assertEqual(res["exit_code"], 1)

    def test_run_mock_unknown_worker_raises(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg_p = _write_config(tmp, [_worker("w-python", [PY, "-"])])
            cfg = worker_adapter.load_config(str(cfg_p))
            with self.assertRaises(ValueError):
                worker_adapter.run_worker(cfg, worker_id="no-such", goal="g",
                                          mode="mock", timeout=None,
                                          mock_result={}, mock_exit_code=0)


class TestRunCli(unittest.TestCase):
    def test_run_cli_python_echo(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            entry = [PY, "-c", "import sys; print('GOT:' + sys.stdin.read().strip()[:20])"]
            cfg_p = _write_config(tmp, [_worker("w-python", entry)])
            gf = _goal_file(tmp, "hello-goal")
            cfg = worker_adapter.load_config(str(cfg_p))
            res = worker_adapter.run_worker(cfg, worker_id="w-python",
                                            goal=gf.read_text(encoding="utf-8"),
                                            mode="cli", timeout=10,
                                            mock_result={}, mock_exit_code=0)
            self.assertTrue(res["ok"])
            self.assertEqual(res["exit_code"], 0)
            self.assertEqual(res["mode"], "cli")
            self.assertIn("GOT:hello-goal", res["stdout_tail"])

    def test_run_cli_exit_code_1(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            entry = [PY, "-c", "import sys; sys.exit(1)"]
            cfg_p = _write_config(tmp, [_worker("w-fail", entry)])
            gf = _goal_file(tmp)
            cfg = worker_adapter.load_config(str(cfg_p))
            res = worker_adapter.run_worker(cfg, worker_id="w-fail",
                                            goal=gf.read_text(encoding="utf-8"),
                                            mode="cli", timeout=10,
                                            mock_result={}, mock_exit_code=0)
            self.assertFalse(res["ok"])
            self.assertEqual(res["exit_code"], 1)

    def test_run_cli_timeout_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            entry = [PY, "-c", "import time; time.sleep(30)"]
            cfg_p = _write_config(tmp, [_worker("w-slow", entry, timeout=60)])
            gf = _goal_file(tmp)
            cfg = worker_adapter.load_config(str(cfg_p))
            res = worker_adapter.run_worker(cfg, worker_id="w-slow",
                                            goal=gf.read_text(encoding="utf-8"),
                                            mode="cli", timeout=1,
                                            mock_result={}, mock_exit_code=0)
            self.assertTrue(res["timed_out"])
            self.assertEqual(res["exit_code"], 2)
            self.assertFalse(res["ok"])

    def test_run_cli_json_stdout_parsed_as_result(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            entry = [PY, "-c",
                     "import json,sys; print(json.dumps({'ok': True, 'n': 42}))"]
            cfg_p = _write_config(tmp, [_worker("w-json", entry)])
            gf = _goal_file(tmp)
            cfg = worker_adapter.load_config(str(cfg_p))
            res = worker_adapter.run_worker(cfg, worker_id="w-json",
                                            goal=gf.read_text(encoding="utf-8"),
                                            mode="cli", timeout=10,
                                            mock_result={}, mock_exit_code=0)
            self.assertEqual(res["result"], {"ok": True, "n": 42})


class TestCLI(unittest.TestCase):
    def test_run_mock_cli_exit_0(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg_p = _write_config(tmp, [_worker("w-python", [PY, "-"])])
            gf = _goal_file(tmp)
            code = worker_adapter.main(["run", "--config", str(cfg_p),
                                        "--goal-file", str(gf),
                                        "--mode", "mock"])
            self.assertEqual(code, 0)

    def test_run_cli_missing_goal_exit_1(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg_p = _write_config(tmp, [_worker("w-python", [PY, "-"])])
            code = worker_adapter.main(["run", "--config", str(cfg_p),
                                        "--goal-file", str(tmp / "nope.txt"),
                                        "--mode", "mock"])
            self.assertEqual(code, 1)

    def test_run_cli_timeout_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            entry = [PY, "-c", "import time; time.sleep(30)"]
            cfg_p = _write_config(tmp, [_worker("w-slow", entry)])
            gf = _goal_file(tmp)
            code = worker_adapter.main(["run", "--config", str(cfg_p),
                                        "--goal-file", str(gf),
                                        "--mode", "cli", "--timeout", "1"])
            self.assertEqual(code, 2)

    def test_list_workers(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg_p = _write_config(tmp, [
                _worker("w-a", [PY, "-"], health_path=str(PY)),
                _worker("w-b", [PY, "-"], health_path=str(PY)),
            ])
            code = worker_adapter.main(["list", "--config", str(cfg_p)])
            self.assertEqual(code, 0)

    def test_health_workers(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg_p = _write_config(tmp, [
                _worker("w-ok", [PY, "-"], health_path=str(PY)),
                _worker("w-missing", [PY, "-"], health_path=str(tmp / "nope.exe")),
            ])
            cfg = worker_adapter.load_config(str(cfg_p))
            res = worker_adapter.health_workers(cfg)
            by_id = {x["id"]: x["status"] for x in res["workers"]}
            self.assertEqual(by_id["w-ok"], "UP")
            self.assertEqual(by_id["w-missing"], "MISSING")

    def test_config_error_exit_1(self):
        code = worker_adapter.main(["list", "--config", "no-such.json"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
