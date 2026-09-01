"""Browser Adapter 离线测试（D3/S3）：runtime/browser_adapter.py。

覆盖（全部离线，--mock 路径零真实网络）：
  - search --mock：结构化结果（title/url/snippet）+ mock:true
  - fetch --mock：title/body/final_url
  - download --mock：文件写入 temp + 输出路径/大小/sha256
  - PLAYWRIGHT_NOT_INSTALLED 分支：模拟 import 失败 -> 明确状态输出（patch sys.modules）
  - NODE_OPTIONS 清理逻辑（启动时清除环境变量）
"""

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from importlib import import_module
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
ba = import_module("browser_adapter")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _run_cmd(fn, ns, patches=None) -> tuple:
    """in-process 跑 cmd_*，可 patch 模块函数，捕获 stdout JSON。"""
    buf = io.StringIO()
    ctxs = [mock.patch.object(ba, k, v) for k, v in (patches or {}).items()]
    with ExitStack() as stack:
        for c in ctxs:
            stack.enter_context(c)
        with contextlib.redirect_stdout(buf):
            rc = fn(ns)
    try:
        return rc, json.loads(buf.getvalue())
    except json.JSONDecodeError:
        return rc, {"_raw": buf.getvalue()}


def _ns(argv) -> object:
    return ba.build_parser().parse_args(argv)


class _FakeElement:
    def __init__(self, text="", href=""):
        self._text = text
        self._href = href

    def inner_text(self):
        return self._text

    def get_attribute(self, name):
        return self._href


class _FakeLi:
    def __init__(self, a, cap=None):
        self._a = a
        self._cap = cap

    def query_selector(self, sel):
        if sel in ("h2 a", "a"):
            return self._a
        if sel in (".b_caption", "p"):
            return self._cap
        return None


class _FakePage:
    def __init__(self, items):
        self._items = items  # selector -> [elements]

    def query_selector_all(self, sel):
        return self._items.get(sel, [])


# ---------------------------------------------------------------------------
# NODE_OPTIONS 清理
# ---------------------------------------------------------------------------
class TestSanitizeNodeOptions(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("NODE_OPTIONS", None)

    def test_sanitize_removes_node_options(self):
        os.environ["NODE_OPTIONS"] = "--use-system-ca"
        ba._sanitize_node_options()
        self.assertNotIn("NODE_OPTIONS", os.environ)

    def test_sanitize_noop_when_unset(self):
        os.environ.pop("NODE_OPTIONS", None)
        ba._sanitize_node_options()  # 不应抛异常
        self.assertNotIn("NODE_OPTIONS", os.environ)

    def test_cmd_search_clears_node_options(self):
        os.environ["NODE_OPTIONS"] = "--use-system-ca"
        ns = _ns(["search", "--query", "playwright download", "--mock"])
        rc, doc = _run_cmd(ba.cmd_search, ns,
                           {"playwright_available": lambda: False})
        self.assertEqual(rc, 0)
        self.assertNotIn("NODE_OPTIONS", os.environ)
        self.assertTrue(doc["mock"])


# ---------------------------------------------------------------------------
# Playwright 可用性探测
# ---------------------------------------------------------------------------
class TestPlaywrightAvailability(unittest.TestCase):
    def test_available_reflects_environment(self):
        import importlib.util
        expected = importlib.util.find_spec("playwright") is not None
        self.assertEqual(ba.playwright_available(), expected)

    def test_unavailable_when_import_blocked(self):
        with mock.patch.dict(sys.modules, {"playwright": None}):
            self.assertFalse(ba.playwright_available())

    def test_get_playwright_raises_when_sync_api_blocked(self):
        with mock.patch.dict(sys.modules, {"playwright.sync_api": None}):
            with self.assertRaises(ImportError):
                ba._get_playwright()


class TestChromiumInstalled(unittest.TestCase):
    def _with_localappdata(self, d: str):
        """手动设置 LOCALAPPDATA（mock.patch.dict 在 Windows os.environ 上有恢复缺陷）。"""
        old = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = d
        self.addCleanup(self._restore_localappdata, old)

    @staticmethod
    def _restore_localappdata(old):
        if old is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = old

    def test_true_when_browser_dir_present(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "ms-playwright" / "chromium-123").mkdir(parents=True)
            self._with_localappdata(d)
            self.assertTrue(ba.chromium_installed())

    def test_false_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self._with_localappdata(d)
            self.assertFalse(ba.chromium_installed())


# ---------------------------------------------------------------------------
# search --mock
# ---------------------------------------------------------------------------
class TestMockSearch(unittest.TestCase):
    def test_mock_search_structured_results(self):
        ns = _ns(["search", "--query", "playwright 下载文件", "--max", "3", "--mock"])
        rc, doc = _run_cmd(ba.cmd_search, ns,
                           {"playwright_available": lambda: False})
        self.assertEqual(rc, 0)
        self.assertTrue(doc["ok"])
        self.assertTrue(doc["mock"])
        self.assertEqual(doc["engine"], "mock")
        self.assertEqual(doc["result_count"], 3)
        self.assertEqual(doc["final_url"], "mock://local")
        for r in doc["results"]:
            self.assertTrue(r["title"])
            self.assertTrue(r["url"].startswith("https://mock.example.com/"))
            self.assertIn("title", r)
            self.assertIn("url", r)
            self.assertIn("snippet", r)

    def test_mock_search_playwright_fallback(self):
        """playwright_available True 但 _get_playwright 失败 -> 回退手工解析。"""
        def _boom():
            raise RuntimeError("no playwright for test")

        ns = _ns(["search", "--query", "watchdog", "--max", "2", "--mock"])
        rc, doc = _run_cmd(ba.cmd_search, ns,
                           {"playwright_available": lambda: True,
                            "_get_playwright": _boom})
        self.assertEqual(rc, 0)
        self.assertTrue(doc["mock"])
        self.assertEqual(doc["result_count"], 2)

    def test_build_mock_search_page(self):
        html = ba._build_mock_search_page("watchdog", 2)
        self.assertIn("https://mock.example.com/result1", html)
        self.assertIn("Mock Result 1 for watchdog", html)
        self.assertIn("Mock Result 2 for watchdog", html)


# ---------------------------------------------------------------------------
# fetch --mock
# ---------------------------------------------------------------------------
class TestMockFetch(unittest.TestCase):
    def test_fetch_mock_fields(self):
        ns = _ns(["fetch", "--url", "https://example.com/", "--mock"])
        rc, doc = _run_cmd(ba.cmd_fetch, ns)
        self.assertEqual(rc, 0)
        self.assertTrue(doc["ok"])
        self.assertTrue(doc["mock"])
        self.assertEqual(doc["url"], "https://example.com/")
        self.assertEqual(doc["final_url"], "mock://local")
        self.assertEqual(doc["title"], "Mock Page Title")
        self.assertTrue(doc["body_text"])
        self.assertGreater(doc["body_chars"], 0)


# ---------------------------------------------------------------------------
# download --mock
# ---------------------------------------------------------------------------
class TestMockDownload(unittest.TestCase):
    def test_download_mock_writes_file(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d)
            ns = _ns(["download", "--url", "https://example.com/file.bin",
                      "--dest", str(dest), "--mock"])
            rc, doc = _run_cmd(ba.cmd_download, ns)
            self.assertEqual(rc, 0)
            self.assertTrue(doc["ok"])
            self.assertTrue(doc["mock"])
            target = Path(doc["file"])
            self.assertTrue(target.exists())
            self.assertEqual(target.parent, dest)
            self.assertGreater(doc["size"], 0)
            self.assertEqual(doc["size"], target.stat().st_size)
            self.assertEqual(len(doc["sha256"]), 64)
            self.assertTrue(
                target.read_text(encoding="utf-8").startswith("mock download from"))

    def test_download_dest_unwritable(self):
        with tempfile.TemporaryDirectory() as d:
            blocker = Path(d) / "blocker"
            blocker.write_text("x", encoding="utf-8")
            ns = _ns(["download", "--url", "https://example.com/f",
                      "--dest", str(blocker), "--mock"])
            rc, doc = _run_cmd(ba.cmd_download, ns)
            self.assertEqual(rc, 1)
            self.assertEqual(doc["error"], "DEST_UNWRITABLE")


# ---------------------------------------------------------------------------
# PLAYWRIGHT_NOT_INSTALLED 分支
# ---------------------------------------------------------------------------
class TestNotInstalledBranch(unittest.TestCase):
    def test_search_playwright_not_installed(self):
        ns = _ns(["search", "--query", "playwright"])
        rc, doc = _run_cmd(ba.cmd_search, ns,
                           {"playwright_available": lambda: False})
        self.assertEqual(rc, 1)
        self.assertFalse(doc["ok"])
        self.assertEqual(doc["error"], "PLAYWRIGHT_NOT_INSTALLED")

    def test_fetch_playwright_not_installed(self):
        ns = _ns(["fetch", "--url", "https://example.com/"])
        rc, doc = _run_cmd(ba.cmd_fetch, ns,
                           {"playwright_available": lambda: False})
        self.assertEqual(rc, 1)
        self.assertEqual(doc["error"], "PLAYWRIGHT_NOT_INSTALLED")

    def test_download_playwright_strategy_not_installed(self):
        with tempfile.TemporaryDirectory() as d:
            ns = _ns(["download", "--url", "https://example.com/f.bin",
                      "--dest", str(Path(d)), "--strategy", "playwright"])
            rc, doc = _run_cmd(ba.cmd_download, ns,
                               {"playwright_available": lambda: False})
            self.assertEqual(rc, 1)
            self.assertEqual(doc["error"], "DOWNLOAD_FAILED")
            self.assertIn("playwright 未安装", doc["detail"])

    def test_status_not_installed(self):
        ns = _ns(["status"])
        rc, doc = _run_cmd(ba.cmd_status, ns,
                           {"playwright_available": lambda: False,
                            "chromium_installed": lambda: False})
        self.assertEqual(rc, 0)
        self.assertEqual(doc["status"], "PLAYWRIGHT_NOT_INSTALLED")
        self.assertFalse(doc["playwright_installed"])
        self.assertIn("未安装", doc["detail"])


# ---------------------------------------------------------------------------
# status 其余状态
# ---------------------------------------------------------------------------
class TestStatus(unittest.TestCase):
    def test_status_ready(self):
        ns = _ns(["status"])
        rc, doc = _run_cmd(ba.cmd_status, ns,
                           {"playwright_available": lambda: True,
                            "chromium_installed": lambda: True})
        self.assertEqual(rc, 0)
        self.assertEqual(doc["status"], "PLAYWRIGHT_READY")
        self.assertTrue(doc["playwright_installed"])
        self.assertTrue(doc["chromium_installed"])

    def test_status_installed_no_browser(self):
        ns = _ns(["status"])
        rc, doc = _run_cmd(ba.cmd_status, ns,
                           {"playwright_available": lambda: True,
                            "chromium_installed": lambda: False})
        self.assertEqual(rc, 0)
        self.assertEqual(doc["status"], "PLAYWRIGHT_INSTALLED_NO_BROWSER")


# ---------------------------------------------------------------------------
# 结果解析（fake page）
# ---------------------------------------------------------------------------
class TestParseResults(unittest.TestCase):
    def test_parse_bing_algo_items(self):
        page = _FakePage({
            "li.b_algo": [
                _FakeLi(_FakeElement("Title One", "https://a.example/1"),
                        _FakeElement("snippet one")),
                _FakeLi(_FakeElement("Title Two", "https://a.example/2"), None),
            ],
        })
        res = ba._parse_bing_results(page, 5)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0]["title"], "Title One")
        self.assertEqual(res[0]["url"], "https://a.example/1")
        self.assertEqual(res[0]["snippet"], "snippet one")
        self.assertEqual(res[1]["snippet"], "")

    def test_parse_respects_max_results(self):
        page = _FakePage({
            "li.b_algo": [
                _FakeLi(_FakeElement(f"T{i}", f"https://a.example/{i}"))
                for i in range(4)
            ],
        })
        res = ba._parse_bing_results(page, 2)
        self.assertEqual(len(res), 2)

    def test_parse_fallback_links(self):
        page = _FakePage({
            "li.b_algo": [],
            "a[href^='http']": [
                _FakeElement("Ext Link", "https://ext.example/1"),
                _FakeElement("bing junk", "https://www.bing.com/search?q=x"),
                _FakeElement("", "https://empty.example/2"),
            ],
        })
        res = ba._parse_bing_results(page, 5)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["url"], "https://ext.example/1")


# ---------------------------------------------------------------------------
# 辅助纯函数
# ---------------------------------------------------------------------------
class TestHelpers(unittest.TestCase):
    def test_sha256_matches_hashlib(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.bin"
            data = b"hello world" * 100
            p.write_bytes(data)
            self.assertEqual(ba._sha256(p), hashlib.sha256(data).hexdigest())

    def test_launch_kwargs_proxy_and_headed(self):
        kw = ba._launch_kwargs("http://127.0.0.1:7897", headed=True, timeout_ms=30000)
        self.assertEqual(kw["headless"], False)
        self.assertEqual(kw["proxy"], {"server": "http://127.0.0.1:7897"})
        self.assertEqual(kw["timeout"], 30000)

    def test_launch_kwargs_no_proxy(self):
        kw = ba._launch_kwargs("", headed=False, timeout_ms=10000)
        self.assertNotIn("proxy", kw)
        self.assertTrue(kw["headless"])


# ---------------------------------------------------------------------------
# 参数校验
# ---------------------------------------------------------------------------
class TestValidation(unittest.TestCase):
    def test_search_empty_query(self):
        ns = _ns(["search", "--query", ""])
        rc, doc = _run_cmd(ba.cmd_search, ns)
        self.assertEqual(rc, 2)
        self.assertEqual(doc["error"], "QUERY_REQUIRED")

    def test_fetch_empty_url(self):
        ns = _ns(["fetch", "--url", ""])
        rc, doc = _run_cmd(ba.cmd_fetch, ns)
        self.assertEqual(rc, 2)
        self.assertEqual(doc["error"], "URL_REQUIRED")

    def test_download_empty_url(self):
        with tempfile.TemporaryDirectory() as d:
            ns = _ns(["download", "--url", "", "--dest", str(Path(d))])
            rc, doc = _run_cmd(ba.cmd_download, ns)
            self.assertEqual(rc, 2)
            self.assertEqual(doc["error"], "URL_REQUIRED")


if __name__ == "__main__":
    unittest.main()
