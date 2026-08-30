"""Reuse Gate 离线测试（D3/S3）：scripts/reuse_gate.py check/record/list 门禁行为。

覆盖（全部离线，mock 掉 gh/网络）：
  - check 普通模式：本地命中 -> GATE_OK/verdict=reuse；无命中 -> GUIDANCE_ONLY 搜索指引
  - record：追加 ndjson（临时文件验证，绝不触碰正式 docs/evidence/reuse-decisions.ndjson）
  - --require-decision：有记录 -> GATE_OK exit 0；无记录 -> BUILD_BLOCKED exit 1（门禁核心）
  - FAILED_APPROACH_LEDGER 衔接：任务命中已失败路线 -> 警告输出
  - 纯函数：关键词提取 / registry 搜索 / ledger 解析 / gh 解析 / Decision 匹配
"""

import argparse
import contextlib
import io
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import reuse_gate  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _default_gh() -> dict:
    """gh 不可用时的默认返回（测试可控，不依赖真实环境）。"""
    return {"ok": False, "detail": "gh CLI not found (test)", "results": []}


def _gh_ok(results=None) -> dict:
    return {"ok": True, "detail": "gh search repos returned N hits",
            "results": results or []}


def _write_registry(tmp: Path, watchdog: bool = True) -> Path:
    tools = []
    if watchdog:
        tools.append({
            "id": "tool-watchdog", "name": "守护看门狗", "type": "CLI_WRAPPER",
            "status": "official", "note": "看门狗探活 keepalive",
            "source": "config/production.json",
        })
    tools.append({
        "id": "tool-unrelated", "name": "财务计算器", "type": "CLI",
        "status": "official", "note": "与看门狗无关",
    })
    data = {"sections": {"tools": tools, "capabilities": [],
                         "browsers": [], "adapters": []}}
    p = tmp / "capability-registry.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def _write_empty_registry(tmp: Path) -> Path:
    data = {"sections": {"tools": [], "capabilities": [], "browsers": [],
                         "adapters": []}}
    p = tmp / "capability-registry.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def _write_ledger(tmp: Path) -> Path:
    p = tmp / "FAILED_APPROACH_LEDGER.md"
    p.write_text(
        "# Failed Approach Ledger\n\n"
        "## F099 — 看门狗方案失败（watchdog keepalive）\n"
        "- why_failed: 测试失败原因\n"
        "- do_not_retry_unless: 满足条件才可重试\n"
        "- status: REJECTED\n\n"
        "## F100 — 量子编译器失败\n"
        "- why_failed: 另一原因\n"
        "- status: REJECTED\n",
        encoding="utf-8")
    return p


def _run_main(argv, gh=None, patches=None) -> tuple:
    """in-process 跑 reuse_gate.main，mock 掉 gh，捕获 stdout JSON。"""
    buf = io.StringIO()
    ctxs = [mock.patch("reuse_gate.try_gh_search",
                       return_value=_default_gh() if gh is None else gh)]
    ctxs += [mock.patch.object(reuse_gate, k, v)
             for k, v in (patches or {}).items()]
    with ExitStack() as stack:
        for c in ctxs:
            stack.enter_context(c)
        with contextlib.redirect_stdout(buf):
            rc = reuse_gate.main(argv)
    return _parse(rc, buf.getvalue())


def _run_fn(fn, ns, patches=None) -> tuple:
    buf = io.StringIO()
    ctxs = [mock.patch.object(reuse_gate, k, v)
            for k, v in (patches or {}).items()]
    with ExitStack() as stack:
        for c in ctxs:
            stack.enter_context(c)
        with contextlib.redirect_stdout(buf):
            rc = fn(ns)
    return _parse(rc, buf.getvalue())


def _parse(rc: int, text: str) -> tuple:
    try:
        return rc, json.loads(text)
    except json.JSONDecodeError:
        return rc, {"_raw": text}


def _record_ns(**kw) -> argparse.Namespace:
    ns = dict(command="record", task="", decision="", evidence="", note="",
              failed_ledger="", decisions="")
    ns.update(kw)
    return argparse.Namespace(**ns)


# ---------------------------------------------------------------------------
# 关键词提取
# ---------------------------------------------------------------------------
class TestKeywordExtraction(unittest.TestCase):
    def test_extract_cjk_and_ascii(self):
        kws = reuse_gate._extract_keywords("watchdog keepalive 看门狗守护")
        self.assertIn("watchdog", kws)
        self.assertIn("keepalive", kws)
        self.assertIn("看门狗守护", kws)

    def test_stopwords_removed(self):
        kws = reuse_gate._extract_keywords("the and for with watchdog")
        self.assertNotIn("the", kws)
        self.assertNotIn("and", kws)
        self.assertNotIn("for", kws)
        self.assertIn("watchdog", kws)

    def test_short_ascii_tokens_excluded(self):
        kws = reuse_gate._extract_keywords("ab cd watchdog")
        self.assertNotIn("ab", kws)
        self.assertNotIn("cd", kws)

    def test_dedupe_preserves_order(self):
        kws = reuse_gate._extract_keywords("watchdog watchdog keepalive")
        self.assertEqual(kws, ["watchdog", "keepalive"])

    def test_empty(self):
        self.assertEqual(reuse_gate._extract_keywords(""), [])


# ---------------------------------------------------------------------------
# 本地 registry 搜索
# ---------------------------------------------------------------------------
class TestLocalRegistry(unittest.TestCase):
    def test_hit_matches_keywords(self):
        reg = {"sections": {"tools": [
            {"id": "tool-watchdog", "name": "守护看门狗", "type": "CLI",
             "status": "official", "note": "看门狗探活 keepalive"},
        ]}}
        hits = reuse_gate.search_local_registry(reg, ["watchdog", "keepalive"])
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["id"], "tool-watchdog")
        self.assertIn("watchdog", hits[0]["matched_keywords"])

    def test_no_hit(self):
        reg = {"sections": {"tools": [
            {"id": "tool-unrelated", "name": "财务计算器", "type": "CLI",
             "status": "official", "note": "无关"},
        ]}}
        hits = reuse_gate.search_local_registry(reg, ["quantum", "compiler"])
        self.assertEqual(hits, [])

    def test_no_keywords_no_hit(self):
        reg = {"sections": {"tools": [
            {"id": "tool-watchdog", "name": "看门狗", "type": "CLI",
             "status": "official", "note": ""},
        ]}}
        self.assertEqual(reuse_gate.search_local_registry(reg, []), [])

    def test_missing_file_warns(self):
        with tempfile.TemporaryDirectory() as d:
            data = reuse_gate.load_registry(Path(d) / "missing.json")
            self.assertIn("_warning", data)

    def test_bad_json_warns(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "reg.json"
            p.write_text("{bad json", encoding="utf-8")
            data = reuse_gate.load_registry(p)
            self.assertIn("_warning", data)

    def test_non_dict_warns(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "reg.json"
            p.write_text("[1,2]", encoding="utf-8")
            data = reuse_gate.load_registry(p)
            self.assertIn("_warning", data)


# ---------------------------------------------------------------------------
# FAILED_APPROACH_LEDGER 解析/搜索
# ---------------------------------------------------------------------------
class TestFailedLedger(unittest.TestCase):
    def test_parse_entries_and_fields(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_ledger(Path(d))
            entries = reuse_gate.load_failed_approaches(p)
            self.assertEqual(len(entries), 2)
            f099 = next(e for e in entries if e["id"] == "F099")
            self.assertEqual(f099["status"], "REJECTED")
            self.assertIn("看门狗", f099["_text"])

    def test_search_hit(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_ledger(Path(d))
            entries = reuse_gate.load_failed_approaches(p)
            hits = reuse_gate.search_failed_approaches(entries, ["看门狗"])
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["id"], "F099")
            self.assertIn("do_not_retry_unless", hits[0])
            self.assertIn("看门狗", hits[0]["matched_keywords"])

    def test_search_no_hit(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_ledger(Path(d))
            entries = reuse_gate.load_failed_approaches(p)
            self.assertEqual(
                reuse_gate.search_failed_approaches(entries, ["不存在的关键词xyz"]), [])

    def test_missing_ledger_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                reuse_gate.load_failed_approaches(Path(d) / "missing.md"), [])


# ---------------------------------------------------------------------------
# GitHub 搜索（gh CLI mock）
# ---------------------------------------------------------------------------
def _gh_proc(returncode=0, stdout="[]", stderr=""):
    return mock.Mock(returncode=returncode, stdout=stdout, stderr=stderr)


class TestGitHubSearch(unittest.TestCase):
    def test_gh_not_installed_returns_not_ok(self):
        with mock.patch("reuse_gate.shutil.which", return_value=None):
            r = reuse_gate.try_gh_search(["watchdog"])
        self.assertFalse(r["ok"])
        self.assertIn("not found", r["detail"])
        self.assertEqual(r["results"], [])

    def test_gh_success_parses_results(self):
        payload = json.dumps([
            {"fullName": "user/repo", "description": "desc",
             "stargazersCount": 42, "htmlUrl": "https://github.com/user/repo"},
        ])
        with mock.patch("reuse_gate.shutil.which", return_value="gh"), \
                mock.patch("reuse_gate.subprocess.run",
                           return_value=_gh_proc(stdout=payload)):
            r = reuse_gate.try_gh_search(["watchdog"])
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["results"]), 1)
        self.assertEqual(r["results"][0]["repo"], "user/repo")
        self.assertEqual(r["results"][0]["stars"], 42)

    def test_gh_nonzero_exit_not_ok(self):
        with mock.patch("reuse_gate.shutil.which", return_value="gh"), \
                mock.patch("reuse_gate.subprocess.run",
                           return_value=_gh_proc(returncode=1, stderr="boom")):
            r = reuse_gate.try_gh_search(["watchdog"])
        self.assertFalse(r["ok"])
        self.assertIn("exit=1", r["detail"])

    def test_gh_unparseable_not_ok(self):
        with mock.patch("reuse_gate.shutil.which", return_value="gh"), \
                mock.patch("reuse_gate.subprocess.run",
                           return_value=_gh_proc(stdout="not json")):
            r = reuse_gate.try_gh_search(["watchdog"])
        self.assertFalse(r["ok"])
        self.assertIn("unparseable", r["detail"])

    def test_gh_exception_not_ok(self):
        with mock.patch("reuse_gate.shutil.which", return_value="gh"), \
                mock.patch("reuse_gate.subprocess.run",
                           side_effect=OSError("no gh")):
            r = reuse_gate.try_gh_search(["watchdog"])
        self.assertFalse(r["ok"])
        self.assertIn("failed", r["detail"])

    def test_build_search_guidance(self):
        g = reuse_gate.build_search_guidance(["watchdog", "keepalive"])
        self.assertEqual(g["engine"], "github + websearch")
        self.assertEqual(g["recommended_keywords"], ["watchdog", "keepalive"])
        self.assertIn("watchdog", g["github_search_url"])
        self.assertIn("watchdog", g["websearch_suggestion"])
        self.assertTrue(g["examples"])


# ---------------------------------------------------------------------------
# check 主流程
# ---------------------------------------------------------------------------
class TestCheck(unittest.TestCase):
    def _check(self, tmp: Path, task: str, extra=None, gh=None):
        argv = ["check", "--task", task,
                "--registry", str(_write_empty_registry(tmp)),
                "--failed-ledger", str(tmp / "FAILED_APPROACH_LEDGER.md"),
                "--decisions", str(tmp / "reuse-decisions.ndjson")]
        argv += extra or []
        return _run_main(argv, gh=gh)

    def test_local_hit_gate_ok_verdict_reuse(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            reg = _write_registry(tmp, watchdog=True)
            rc, doc = _run_main([
                "check", "--task", "watchdog keepalive 看门狗守护",
                "--registry", str(reg),
                "--failed-ledger", str(tmp / "FAILED_APPROACH_LEDGER.md"),
                "--decisions", str(tmp / "reuse-decisions.ndjson"),
            ])
            self.assertEqual(rc, 0)
            self.assertTrue(doc["ok"])
            self.assertEqual(doc["steps"]["local_registry_search"]["hit_count"], 1)
            self.assertEqual(doc["verdict"]["level"], "reuse")
            self.assertEqual(doc["verdict"]["priority"], 1)
            self.assertEqual(doc["gate"]["status"], "GATE_OK")

    def test_no_hit_outputs_guidance(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            rc, doc = self._check(tmp, "quantum compiler optimizer 量子编译器")
            self.assertEqual(rc, 0)
            self.assertEqual(doc["verdict"]["level"], "build")
            gh = doc["steps"]["github_search"]
            self.assertEqual(gh["status"], "GUIDANCE_ONLY")
            self.assertIsNotNone(gh["guidance"])
            self.assertIn("quantum", gh["guidance"]["recommended_keywords"])
            self.assertIn("github.com", gh["guidance"]["github_search_url"])

    def test_gh_hit_verdict_adapt(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            gh = _gh_ok([{"repo": "user/watchdog", "description": "d",
                          "stars": 123, "url": "https://github.com/user/watchdog"}])
            rc, doc = self._check(tmp, "watchdog 守护进程", gh=gh)
            self.assertEqual(rc, 0)
            self.assertEqual(doc["steps"]["github_search"]["status"], "SEARCHED")
            self.assertEqual(doc["steps"]["github_search"]["results"][0]["repo"],
                             "user/watchdog")
            self.assertEqual(doc["verdict"]["level"], "adapt")

    def test_require_decision_without_record_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            rc, doc = self._check(
                tmp, "量子编译器优化任务",
                extra=["--require-decision"])
            self.assertEqual(rc, 1)
            self.assertEqual(doc["gate"]["status"], "BUILD_BLOCKED")
            self.assertEqual(doc["gate"]["covering_count"], 0)

    def test_require_decision_with_record_passes(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            dec = tmp / "reuse-decisions.ndjson"
            r1, _ = _run_main(["record", "--task", "watchdog keepalive 看门狗守护",
                               "--decision", "reuse",
                               "--evidence", "https://example.com/evidence",
                               "--decisions", str(dec)])
            self.assertEqual(r1, 0)
            rc, doc = _run_main([
                "check", "--task", "watchdog keepalive 看门狗守护",
                "--registry", str(_write_empty_registry(tmp)),
                "--failed-ledger", str(tmp / "FAILED_APPROACH_LEDGER.md"),
                "--decisions", str(dec),
                "--require-decision",
            ])
            self.assertEqual(rc, 0)
            self.assertEqual(doc["gate"]["status"], "GATE_OK")
            self.assertEqual(doc["gate"]["covering_count"], 1)

    def test_require_decision_shared_keyword_passes(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            dec = tmp / "reuse-decisions.ndjson"
            _run_main(["record", "--task", "watchdog keepalive 实现方案",
                       "--decision", "compose",
                       "--evidence", "https://example.com/e",
                       "--decisions", str(dec)])
            rc, doc = _run_main([
                "check", "--task", "watchdog keepalive 守护层",
                "--registry", str(_write_empty_registry(tmp)),
                "--failed-ledger", str(tmp / "FAILED_APPROACH_LEDGER.md"),
                "--decisions", str(dec),
                "--require-decision",
            ])
            self.assertEqual(rc, 0)
            self.assertEqual(doc["gate"]["status"], "GATE_OK")
            self.assertTrue(doc["gate"]["covering_count"] >= 1)
            self.assertIn("watchdog", doc["gate"]["covering_decisions"][0]["_match"]["shared_keywords"])

    def test_normal_mode_no_decision_does_not_block(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            rc, doc = self._check(tmp, "watchdog 新任务", extra=[])
            self.assertEqual(rc, 0)
            self.assertEqual(doc["gate"]["status"], "GATE_OK")

    def test_failed_approach_warning_output(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            ledger = _write_ledger(tmp)
            rc, doc = _run_main([
                "check", "--task", "watchdog keepalive 看门狗守护",
                "--registry", str(_write_empty_registry(tmp)),
                "--failed-ledger", str(ledger),
                "--decisions", str(tmp / "reuse-decisions.ndjson"),
            ])
            self.assertEqual(rc, 0)
            step = doc["steps"]["failed_approach_ledger"]
            self.assertTrue(step["hit_count"] >= 1)
            self.assertIsNotNone(step["warning"])
            self.assertIn("do_not_retry_unless", step["warning"])

    def test_empty_task_error(self):
        rc, doc = _run_main(["check", "--task", ""])
        self.assertEqual(rc, 2)
        self.assertFalse(doc["ok"])
        self.assertEqual(doc["error"], "TASK_REQUIRED")


# ---------------------------------------------------------------------------
# record 命令
# ---------------------------------------------------------------------------
class TestRecord(unittest.TestCase):
    def test_record_appends_ndjson(self):
        with tempfile.TemporaryDirectory() as d:
            dec = Path(d) / "reuse-decisions.ndjson"
            for i in range(2):
                rc, doc = _run_main([
                    "record", "--task", f"任务{i}",
                    "--decision", "reuse",
                    "--evidence", f"https://example.com/e{i}",
                    "--note", f"note{i}",
                    "--decisions", str(dec),
                ])
                self.assertEqual(rc, 0)
                self.assertTrue(doc["ok"])
            lines = [ln for ln in dec.read_text(encoding="utf-8").splitlines()
                     if ln.strip()]
            self.assertEqual(len(lines), 2)
            for ln in lines:
                obj = json.loads(ln)
                self.assertEqual(obj["schema"], "v1.1-d3-reuse-decision")
                self.assertTrue(obj["decision_id"].startswith("D3-"))
                self.assertIn("recorded_at", obj)
                self.assertTrue(obj["non_authority"])
                self.assertIn("evidence", obj)

    def test_record_only_writes_target_file(self):
        with tempfile.TemporaryDirectory() as d:
            dec = Path(d) / "reuse-decisions.ndjson"
            rc, doc = _run_main([
                "record", "--task", "watchdog keepalive",
                "--decision", "adapt",
                "--evidence", "https://example.com/e",
                "--decisions", str(dec),
            ])
            self.assertEqual(rc, 0)
            self.assertEqual(Path(doc["decisions_file"]), dec)
            self.assertTrue(dec.exists())
            # 未向正式 docs/evidence/reuse-decisions.ndjson 写入（tmp 文件仅 1 行）
            self.assertEqual(len(dec.read_text(encoding="utf-8").splitlines()), 1)

    def test_record_bad_decision(self):
        rc, doc = _run_fn(
            reuse_gate.cmd_record,
            _record_ns(task="x", decision="reimplement", evidence="e"))
        self.assertEqual(rc, 2)
        self.assertEqual(doc["error"], "BAD_DECISION")

    def test_record_missing_evidence(self):
        rc, doc = _run_fn(
            reuse_gate.cmd_record,
            _record_ns(task="x", decision="reuse", evidence=""))
        self.assertEqual(rc, 2)
        self.assertEqual(doc["error"], "EVIDENCE_REQUIRED")

    def test_record_empty_task(self):
        rc, doc = _run_fn(
            reuse_gate.cmd_record,
            _record_ns(task="", decision="reuse", evidence="e"))
        self.assertEqual(rc, 2)
        self.assertEqual(doc["error"], "TASK_REQUIRED")

    def test_record_failed_approach_warning(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            ledger = _write_ledger(tmp)
            rc, doc = _run_fn(
                reuse_gate.cmd_record,
                _record_ns(task="watchdog keepalive 看门狗守护",
                           decision="reuse", evidence="https://example.com/e",
                           failed_ledger=str(ledger),
                           decisions=str(tmp / "reuse-decisions.ndjson")))
            self.assertEqual(rc, 0)
            self.assertIsNotNone(doc["decision"]["failed_approach_warning"])
            self.assertEqual(
                doc["decision"]["failed_approach_warning"][0]["id"], "F099")
            self.assertEqual(
                doc["decision"]["gate_check_summary"]["failed_approach_hits"], 1)

    def test_record_write_failure(self):
        with tempfile.TemporaryDirectory() as d:
            rc, doc = _run_fn(
                reuse_gate.cmd_record,
                _record_ns(task="x", decision="reuse", evidence="e",
                           decisions=str(Path(d) / "out.ndjson")),
                patches={"append_decision": mock.Mock(side_effect=OSError("denied"))})
            self.assertEqual(rc, 1)
            self.assertEqual(doc["error"], "WRITE_FAILED")


# ---------------------------------------------------------------------------
# Decision 匹配与留痕读写
# ---------------------------------------------------------------------------
class TestDecisionMatching(unittest.TestCase):
    def test_exact_task_covers(self):
        d = {"task": "watchdog keepalive 看门狗守护", "decision": "reuse"}
        self.assertTrue(reuse_gate.decision_covers(d, "watchdog keepalive 看门狗守护"))

    def test_shared_keyword_covers(self):
        d = {"task": "watchdog keepalive 实现方案", "decision": "compose"}
        self.assertTrue(reuse_gate.decision_covers(d, "watchdog keepalive 守护层"))

    def test_no_match_does_not_cover(self):
        d = {"task": "quantum compiler", "decision": "build"}
        self.assertFalse(reuse_gate.decision_covers(d, "watchdog keepalive"))

    def test_empty_task_does_not_cover(self):
        d = {"task": "watchdog", "decision": "reuse"}
        self.assertFalse(reuse_gate.decision_covers(d, ""))

    def test_find_covering_decisions_meta(self):
        decisions = [{"task": "watchdog keepalive 实现方案", "decision": "compose"}]
        hits = reuse_gate.find_covering_decisions(decisions, "watchdog keepalive 守护层")
        self.assertEqual(len(hits), 1)
        self.assertFalse(hits[0]["_match"]["exact"])
        self.assertIn("watchdog", hits[0]["_match"]["shared_keywords"])

    def test_gate_verdict(self):
        self.assertEqual(reuse_gate._gate_verdict([], require=True), "BUILD_BLOCKED")
        self.assertEqual(reuse_gate._gate_verdict([{"task": "x"}], require=True), "GATE_OK")
        self.assertEqual(reuse_gate._gate_verdict([], require=False), "GATE_OK")


class TestAppendLoadDecisions(unittest.TestCase):
    def test_append_creates_file_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "reuse-decisions.ndjson"
            reuse_gate.append_decision({"task": "a", "decision": "reuse"}, p)
            reuse_gate.append_decision({"task": "b", "decision": "adapt"}, p)
            loaded = reuse_gate.load_decisions(p)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0]["task"], "a")
            self.assertEqual(loaded[1]["task"], "b")

    def test_load_skips_bad_lines(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "reuse-decisions.ndjson"
            p.write_text('{"task": "a"}\nnot-json\n{"task": "b"}\n',
                         encoding="utf-8")
            loaded = reuse_gate.load_decisions(p)
            self.assertEqual(len(loaded), 2)

    def test_load_missing_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                reuse_gate.load_decisions(Path(d) / "missing.ndjson"), [])


# ---------------------------------------------------------------------------
# list 命令
# ---------------------------------------------------------------------------
class TestList(unittest.TestCase):
    def test_list_all_count(self):
        with tempfile.TemporaryDirectory() as d:
            dec = Path(d) / "reuse-decisions.ndjson"
            for i in range(3):
                reuse_gate.append_decision(
                    {"task": f"task{i}", "decision": "reuse"}, dec)
            rc, doc = _run_main(["list", "--decisions", str(dec)])
            self.assertEqual(rc, 0)
            self.assertTrue(doc["ok"])
            self.assertEqual(doc["decision_count"], 3)
            self.assertEqual(len(doc["decisions"]), 3)

    def test_list_task_covering(self):
        with tempfile.TemporaryDirectory() as d:
            dec = Path(d) / "reuse-decisions.ndjson"
            reuse_gate.append_decision(
                {"task": "watchdog keepalive 实现方案", "decision": "compose"}, dec)
            reuse_gate.append_decision(
                {"task": "quantum compiler", "decision": "build"}, dec)
            rc, doc = _run_main(["list", "--task", "watchdog keepalive 守护层",
                                 "--decisions", str(dec)])
            self.assertEqual(rc, 0)
            self.assertEqual(doc["covering_count"], 1)
            self.assertEqual(doc["covering"][0]["task"],
                             "watchdog keepalive 实现方案")


# ---------------------------------------------------------------------------
# CLI 路由
# ---------------------------------------------------------------------------
class TestCLIRouting(unittest.TestCase):
    def test_unknown_command_raises_usage_error(self):
        with self.assertRaises(SystemExit):
            reuse_gate.main(["bogus-command"])

    def test_no_command_raises_usage_error(self):
        with self.assertRaises(SystemExit):
            reuse_gate.main([])


if __name__ == "__main__":
    unittest.main()
