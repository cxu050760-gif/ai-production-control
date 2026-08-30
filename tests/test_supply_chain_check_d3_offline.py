"""Supply Chain Check 离线测试（D3/S3）：scripts/supply_chain_check.py。

覆盖（全部离线，mock 掉 pip-audit 子进程）：
  - pip-audit 可用：输出依赖清单 + 漏洞状态（VULNERABLE/OK 分支）
  - pip-audit 未装：全包 UNKNOWN + 登记待补（不伪造 OK）
  - 参数校验：--requirements 不存在文件 -> 明确错误（exit 2）
  - 纯函数：requirements/pyproject 解析、漏洞映射、pip-audit 可用性探测、run_pip_audit
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
import supply_chain_check as scc  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
def _write_requirements(tmp: Path, text: str = None) -> Path:
    if text is None:
        text = ("requests==2.32.5\n"
                "urllib3==1.26.4\n"
                "flask>=2.0\n"
                "rich\n"
                "./local-pkg\n"
                "# 注释行\n"
                "\n")
    p = tmp / "requirements.txt"
    p.write_text(text, encoding="utf-8")
    return p


def _audit_ok(vulns=None, exit_code=0) -> dict:
    return {"ok": True, "kind": "requirements", "error": None, "detail": None,
            "exit_code": exit_code, "vulnerabilities": vulns or []}


def _audit_not_installed() -> dict:
    return {"ok": False, "kind": None, "error": "PIP_AUDIT_NOT_INSTALLED",
            "detail": "pip-audit 未安装；依赖漏洞状态一律 UNKNOWN。登记待补：安装命令 ...",
            "vulnerabilities": []}


def _run_check(argv, patches=None, tmp=None) -> tuple:
    """in-process 跑 main，mock 掉 pip-audit 相关调用，捕获 stdout JSON。"""
    buf = io.StringIO()
    work = tmp or Path(tempfile.mkdtemp(prefix="scc_test_"))
    p = dict(patches or {})
    p.setdefault("DEFAULT_PYPROJECT", work / "no-such-pyproject.toml")
    ctxs = [mock.patch.object(scc, k, v) for k, v in p.items()]
    with ExitStack() as stack:
        for c in ctxs:
            stack.enter_context(c)
        with contextlib.redirect_stdout(buf):
            rc = scc.main(argv)
    try:
        return rc, json.loads(buf.getvalue())
    except json.JSONDecodeError:
        return rc, {"_raw": buf.getvalue()}


# ---------------------------------------------------------------------------
# 依赖解析
# ---------------------------------------------------------------------------
class TestParseRequirementLine(unittest.TestCase):
    def test_pinned_pypi(self):
        d = scc.parse_requirement_line("requests==2.32.5")
        self.assertEqual(d["name"], "requests")
        self.assertEqual(d["specifier"], "==")
        self.assertEqual(d["version"], "2.32.5")
        self.assertEqual(d["source"], "PyPI")

    def test_operator_version(self):
        d = scc.parse_requirement_line("flask>=2.0")
        self.assertEqual(d["name"], "flask")
        self.assertEqual(d["specifier"], ">=")
        self.assertEqual(d["version"], "2.0")

    def test_unpinned(self):
        d = scc.parse_requirement_line("rich")
        self.assertEqual(d["name"], "rich")
        self.assertEqual(d["specifier"], "")
        self.assertEqual(d["version"], "")

    def test_extras(self):
        d = scc.parse_requirement_line("requests[security]==2.32.5")
        self.assertEqual(d["name"], "requests")
        self.assertEqual(d["version"], "2.32.5")

    def test_local_path(self):
        d = scc.parse_requirement_line("./local-pkg")
        self.assertEqual(d["source"], "LOCAL")
        self.assertEqual(d["name"], "./local-pkg")

    def test_url_local(self):
        d = scc.parse_requirement_line("https://github.com/user/repo")
        self.assertEqual(d["source"], "LOCAL")

    def test_comment_blank_option_ignored(self):
        self.assertIsNone(scc.parse_requirement_line("# comment"))
        self.assertIsNone(scc.parse_requirement_line(""))
        self.assertIsNone(scc.parse_requirement_line("   "))
        self.assertIsNone(scc.parse_requirement_line("-e git+https://x/y.git"))

    def test_inline_comment_stripped(self):
        d = scc.parse_requirement_line("requests==2.32.5  # 主依赖")
        self.assertEqual(d["name"], "requests")
        self.assertEqual(d["version"], "2.32.5")


class TestParseFiles(unittest.TestCase):
    def test_parse_requirements_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_requirements(Path(d))
            deps = scc.parse_requirements_file(p)
            names = [x["name"] for x in deps]
            self.assertIn("requests", names)
            self.assertIn("urllib3", names)
            self.assertIn("./local-pkg", names)
            self.assertNotIn("# 注释行", names)

    def test_parse_requirements_missing_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                scc.parse_requirements_file(Path(d) / "missing.txt"), [])

    def test_parse_pyproject(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "pyproject.toml"
            p.write_text(
                '[project]\nname="demo"\ndependencies=["requests==2.32.5"]\n'
                '[project.optional-dependencies]\ntest=["pytest>=8.0"]\n',
                encoding="utf-8")
            deps = scc.parse_pyproject(p)
            by_name = {x["name"]: x for x in deps}
            self.assertEqual(by_name["requests"]["version"], "2.32.5")
            self.assertEqual(by_name["pytest"]["optional_group"], "test")

    def test_parse_pyproject_unreadable_reports_local(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "pyproject.toml"
            p.write_text("{bad toml", encoding="utf-8")
            deps = scc.parse_pyproject(p)
            self.assertEqual(len(deps), 1)
            self.assertEqual(deps[0]["source"], "LOCAL")
            self.assertIn("pyproject", deps[0]["name"])


class TestBuildManifest(unittest.TestCase):
    def test_manifest_from_requirements_and_packages(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            req = _write_requirements(tmp)
            with mock.patch.object(scc, "DEFAULT_PYPROJECT",
                                   tmp / "no-pyproject.toml"):
                m = scc.build_dependency_manifest(req, ["extra-pkg==1.0"])
            names = [x["name"] for x in m["dependencies"]]
            self.assertIn("requests", names)
            self.assertIn("extra-pkg", names)
            self.assertTrue(any("requirements" in s for s in m["sources"]))
            self.assertTrue(any("packages" in s for s in m["sources"]))

    def test_manifest_dedup(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            req = _write_requirements(tmp, text="requests==2.32.5\n")
            with mock.patch.object(scc, "DEFAULT_PYPROJECT",
                                   tmp / "no-pyproject.toml"):
                m = scc.build_dependency_manifest(
                    req, ["requests==2.32.5", "requests==1.0.0"])
            count = sum(1 for x in m["dependencies"] if x["name"] == "requests")
            self.assertEqual(count, 1)


class TestMapVulnerabilities(unittest.TestCase):
    def test_maps_by_lowercase_name(self):
        audit = {"vulnerabilities": [
            {"id": "PYSEC-2021-108", "package": "urllib3", "version": "1.26.4",
             "fix_versions": ["1.26.5"], "description": "d", "aliases": []},
        ]}
        m = scc.map_vulnerabilities([], audit)
        self.assertIn("urllib3", m)
        self.assertEqual(m["urllib3"][0]["id"], "PYSEC-2021-108")
        # 实现把 fix_versions 列表以 repr 字符串呈现（"['1.26.5']"），断言其包含修复版本号
        self.assertIn("1.26.5", m["urllib3"][0]["fixed_version"])

    def test_empty_audit(self):
        self.assertEqual(
            scc.map_vulnerabilities([], {"vulnerabilities": []}), {})


# ---------------------------------------------------------------------------
# pip-audit 可用性探测
# ---------------------------------------------------------------------------
class TestPipAuditAvailable(unittest.TestCase):
    def test_which_found(self):
        with mock.patch.object(scc.shutil, "which", return_value="pip-audit"):
            self.assertTrue(scc.pip_audit_available())

    def test_module_available(self):
        with mock.patch.object(scc.shutil, "which", return_value=None), \
                mock.patch.object(scc.subprocess, "run",
                                  return_value=mock.Mock(returncode=0)):
            self.assertTrue(scc.pip_audit_available())

    def test_module_missing(self):
        with mock.patch.object(scc.shutil, "which", return_value=None), \
                mock.patch.object(scc.subprocess, "run",
                                  return_value=mock.Mock(returncode=1)):
            self.assertFalse(scc.pip_audit_available())

    def test_module_oserror(self):
        with mock.patch.object(scc.shutil, "which", return_value=None), \
                mock.patch.object(scc.subprocess, "run",
                                  side_effect=OSError("no pip-audit")):
            self.assertFalse(scc.pip_audit_available())


# ---------------------------------------------------------------------------
# run_pip_audit（mock subprocess）
# ---------------------------------------------------------------------------
class TestRunPipAudit(unittest.TestCase):
    def _ns(self):
        return argparse.Namespace()

    def test_requirements_mode_flattens_vulns(self):
        with tempfile.TemporaryDirectory() as d:
            req = _write_requirements(Path(d), text="urllib3==1.26.4\n")
            payload = json.dumps({"dependencies": [
                {"name": "urllib3", "version": "1.26.4", "vulns": [
                    {"id": "PYSEC-2021-108", "fix_versions": ["1.26.5"],
                     "description": "desc", "aliases": []},
                ]},
            ]})
            with mock.patch.object(
                    scc.subprocess, "run",
                    return_value=mock.Mock(returncode=1, stdout=payload,
                                           stderr="")) as mr:
                r = scc.run_pip_audit(self._ns(), req, Path("."))
            self.assertTrue(r["ok"])
            self.assertEqual(r["kind"], "requirements")
            self.assertEqual(r["exit_code"], 1)
            self.assertEqual(len(r["vulnerabilities"]), 1)
            self.assertEqual(r["vulnerabilities"][0]["package"], "urllib3")
            self.assertEqual(r["vulnerabilities"][0]["fix_versions"], ["1.26.5"])
            # 命令行带 --no-deps -r <file>
            args = mr.call_args.args[0]
            self.assertIn("--no-deps", args)
            self.assertIn("-r", args)

    def test_clean_audit_no_vulns(self):
        with tempfile.TemporaryDirectory() as d:
            req = _write_requirements(Path(d), text="requests==2.32.5\n")
            payload = json.dumps({"dependencies": [
                {"name": "requests", "version": "2.32.5", "vulns": []},
            ]})
            with mock.patch.object(
                    scc.subprocess, "run",
                    return_value=mock.Mock(returncode=0, stdout=payload,
                                           stderr="")):
                r = scc.run_pip_audit(self._ns(), req, Path("."))
            self.assertTrue(r["ok"])
            self.assertEqual(r["vulnerabilities"], [])

    def test_unparseable_stdout_reports_error(self):
        with tempfile.TemporaryDirectory() as d:
            req = _write_requirements(Path(d), text="requests==2.32.5\n")
            with mock.patch.object(
                    scc.subprocess, "run",
                    return_value=mock.Mock(returncode=2, stdout="not json",
                                           stderr="bad")):
                r = scc.run_pip_audit(self._ns(), req, Path("."))
            self.assertFalse(r["ok"])
            self.assertEqual(r["error"], "PIP_AUDIT_EXIT_NONZERO")
            self.assertEqual(r["exit_code"], 2)

    def test_subprocess_exception_reports_error(self):
        with tempfile.TemporaryDirectory() as d:
            req = _write_requirements(Path(d), text="requests==2.32.5\n")
            with mock.patch.object(
                    scc.subprocess, "run", side_effect=OSError("boom")):
                r = scc.run_pip_audit(self._ns(), req, Path("."))
            self.assertFalse(r["ok"])
            self.assertEqual(r["error"], "PIP_AUDIT_RUN_FAILED")

    def test_packages_mode_creates_and_cleans_temp_req(self):
        payload = json.dumps({"dependencies": []})
        with mock.patch.object(
                scc.subprocess, "run",
                return_value=mock.Mock(returncode=0, stdout=payload,
                                       stderr="")) as mr:
            r = scc.run_pip_audit(self._ns(), None, Path("."),
                                  packages=["requests==2.32.5"])
        self.assertTrue(r["ok"])
        self.assertEqual(r["kind"], "packages")
        args = mr.call_args.args[0]
        self.assertIn("-r", args)
        temp_path = args[args.index("-r") + 1]
        # 临时 requirements 已清理
        self.assertFalse(Path(temp_path).exists())

    def test_no_source_uses_project_dir(self):
        with mock.patch.object(
                scc.subprocess, "run",
                return_value=mock.Mock(returncode=0,
                                       stdout=json.dumps({"dependencies": []}),
                                       stderr="")) as mr:
            r = scc.run_pip_audit(self._ns(), None, Path("C:/proj"))
        self.assertEqual(r["kind"], "project-dir")
        args = mr.call_args.args[0]
        self.assertIn("--path", args)


# ---------------------------------------------------------------------------
# check CLI 主流程
# ---------------------------------------------------------------------------
class TestCheckCLI(unittest.TestCase):
    def test_requirements_not_found_clear_error(self):
        rc, doc = _run_check(["check", "--requirements", "C:/nonexistent/req.txt"])
        self.assertEqual(rc, 2)
        self.assertFalse(doc["ok"])
        self.assertEqual(doc["error"], "REQUIREMENTS_NOT_FOUND")
        self.assertIn("不存在", doc["detail"])

    def test_pip_audit_available_vulnerable_and_ok_branches(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            req = _write_requirements(tmp, text="urllib3==1.26.4\nrequests==2.32.5\n")
            audit = _audit_ok([
                {"id": "PYSEC-2021-108", "package": "urllib3",
                 "version": "1.26.4", "fix_versions": ["1.26.5"],
                 "description": "d", "aliases": []},
            ])
            rc, doc = _run_check(
                ["check", "--requirements", str(req)],
                patches={"pip_audit_available": lambda: True,
                         "run_pip_audit": lambda *a, **k: audit},
                tmp=tmp)
            self.assertEqual(rc, 0)
            self.assertTrue(doc["ok"])
            rows = {r["name"]: r for r in doc["dependencies"]}
            self.assertEqual(rows["urllib3"]["vuln_status"], "VULNERABLE")
            self.assertEqual(rows["requests"]["vuln_status"], "OK")
            self.assertIn("PYSEC-2021-108",
                          rows["urllib3"]["vulnerabilities"][0]["id"])
            self.assertEqual(doc["summary"]["vulnerable"], 1)
            self.assertEqual(doc["summary"]["ok"], 1)
            self.assertEqual(doc["summary"]["unknown"], 0)
            self.assertEqual(doc["pip_audit"]["status"], "OK")

    def test_pip_audit_available_clean_all_ok(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            req = _write_requirements(tmp, text="requests==2.32.5\n")
            rc, doc = _run_check(
                ["check", "--requirements", str(req)],
                patches={"pip_audit_available": lambda: True,
                         "run_pip_audit": lambda *a, **k: _audit_ok()},
                tmp=tmp)
            self.assertEqual(rc, 0)
            rows = {r["name"]: r for r in doc["dependencies"]}
            self.assertEqual(rows["requests"]["vuln_status"], "OK")
            self.assertEqual(doc["summary"]["vulnerable"], 0)
            self.assertEqual(doc["summary"]["unknown"], 0)

    def test_pip_audit_not_installed_all_unknown_no_fake_ok(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            req = _write_requirements(tmp, text="requests==2.32.5\nurllib3==1.26.4\n")
            rc, doc = _run_check(
                ["check", "--requirements", str(req)],
                patches={"pip_audit_available": lambda: False},
                tmp=tmp)
            self.assertEqual(rc, 0)
            self.assertFalse(doc["pip_audit"]["available"])
            self.assertEqual(doc["pip_audit"]["status"], "PIP_AUDIT_NOT_INSTALLED")
            rows = {r["name"]: r for r in doc["dependencies"]}
            for name in ("requests", "urllib3"):
                self.assertEqual(rows[name]["vuln_status"], "UNKNOWN")
                self.assertIn("登记待补", rows[name]["action"])
            self.assertEqual(doc["summary"]["ok"], 0)
            self.assertEqual(doc["summary"]["unknown"], 2)
            self.assertTrue(any("登记待补" in r
                                for r in doc["recommendations"]))

    def test_packages_flag_passes_packages_to_audit(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            mr = mock.Mock(return_value=_audit_ok())
            rc, doc = _run_check(
                ["check", "--packages", "requests==2.32.5"],
                patches={"pip_audit_available": lambda: True,
                         "run_pip_audit": mr},
                tmp=tmp)
            self.assertEqual(rc, 0)
            self.assertTrue(any("packages" in s for s in doc["manifest_sources"]))
            self.assertEqual(doc["dependency_count"], 1)
            self.assertEqual(mr.call_args.args[3], ["requests==2.32.5"])

    def test_unpinned_uses_installed_version(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            req = _write_requirements(tmp, text="rich\n")
            rc, doc = _run_check(
                ["check", "--requirements", str(req)],
                patches={"pip_audit_available": lambda: True,
                         "run_pip_audit": lambda *a, **k: _audit_ok(),
                         "resolve_installed_version": lambda name: "13.7.1"},
                tmp=tmp)
            self.assertEqual(rc, 0)
            self.assertEqual(doc["dependencies"][0]["version"], "13.7.1")


if __name__ == "__main__":
    unittest.main()
