#!/usr/bin/env python3
"""D5 offline tests: runtime/self_heal.py（宪法 §68 自举）。"""

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

import self_heal  # noqa: E402

REPO = HERE.parent


def clean_env() -> dict:
    """过滤超长环境变量 + 保证子进程 UTF-8 安全（见 test_task_graph_d5_offline.clean_env 说明）。"""
    env = {k: v for k, v in os.environ.items() if len(v) <= 30000}
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("SYSTEMROOT", r"C:\Windows")
    env.setdefault("SYSTEMDRIVE", "C:")
    return env


class DefectParseTests(unittest.TestCase):
    def test_t01_parse_drift(self):
        text = (
            "DRIFT: baseline mismatch | expected=ok | actual=bad\n"
            "DRIFT_COUNT=1\n"
        )
        r = self_heal.parse_defect(text)
        self.assertEqual(r.source_kind, "DRIFT")
        self.assertIn("baseline mismatch", r.defect_summary)
        self.assertEqual(r.expected, "ok")
        self.assertEqual(r.actual, "bad")
        self.assertTrue(r.evidence)

    def test_t02_parse_test_failed(self):
        text = (
            "FAILED runtime/test_x.py::test_foo\n"
            "AssertionError: expected 36 got 0\n"
        )
        r = self_heal.parse_defect(text)
        self.assertEqual(r.source_kind, "TEST_FAILED")
        self.assertIn("test_foo", r.defect_summary)
        self.assertEqual(r.expected, "AssertionError")

    def test_t03_parse_error_text(self):
        text = (
            "Traceback (most recent call last):\n"
            '  File "C:/repo/runtime/test_v09_attack_matrix_offline.py", line 432, in run_case\n'
            "aicontrol.store.GateDenied: pre-existing scoped authorization required; Controller self-grant is forbidden\n"
        )
        r = self_heal.parse_defect(text)
        self.assertEqual(r.source_kind, "ERROR_TEXT")
        self.assertIn("GateDenied", r.defect_summary)
        self.assertIn("test_v09_attack_matrix_offline.py", r.affected_file or "")
        self.assertEqual(r.expected, "GateDenied")

    def test_t04_parse_unknown(self):
        r = self_heal.parse_defect("随便一段没有结构的话")
        self.assertEqual(r.source_kind, "UNKNOWN")
        self.assertTrue(r.defect_summary)


class ConvertTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_t05_convert_writes_goal_file(self):
        out = self.root / "goal.goal.txt"
        result = self_heal.convert(
            "DRIFT: baseline | expected=ok | actual=bad",
            goal_out=str(out), evidence_dir=str(self.root / "ev"))
        self.assertTrue(result["valid"])
        self.assertEqual(result["defect"]["source_kind"], "DRIFT")
        text = out.read_text(encoding="utf-8")
        self.assertIn("要什么成果", text)
        self.assertIn("怎么算做完", text)
        self.assertIn("约束", text)
        # 证据 JSONL 落盘
        ev = self.root / "ev" / "self_heal_events.jsonl"
        self.assertTrue(ev.exists())
        line = json.loads(ev.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(line["schema"], self_heal.SCHEMA)
        self.assertIn("trace", line)
        self.assertIn("tool", line["trace"])

    def test_t06_convert_multiple_defects(self):
        # 同一文本含 DRIFT + FAILED + ERROR，优先级 DRIFT 最高
        result = self_heal.convert(
            "DRIFT: drift-a | expected=1 | actual=2\n"
            "FAILED test_zz\n"
            "ValueError: boom",
            goal_out=str(self.root / "g.goal.txt"))
        self.assertEqual(result["defect"]["source_kind"], "DRIFT")

    def test_t07_goal_acceptance_criteria(self):
        result = self_heal.convert(
            "GateDenied: pre-existing scoped authorization required",
            goal_out=str(self.root / "g2.goal.txt"))
        criteria = result["goal"]["acceptance_criteria"]
        self.assertTrue(any("返回 0" in c for c in criteria))
        self.assertTrue(any("零回归" in c for c in criteria))


class FixletTests(unittest.TestCase):
    def test_t08_sh001_applies_to_pre_fix_file(self):
        pre = (REPO / "docs" / "evidence" / "d5" / "test_v09_attack_matrix_offline_PRE_FIX.py")
        if not pre.exists():
            # GATE-3：前置缺失不是跳过的理由——静默 skip 是假绿，必须显式 FAIL
            self.fail("前置缺失不是跳过的理由：docs/evidence/d5/"
                      "test_v09_attack_matrix_offline_PRE_FIX.py 不存在")
        text = pre.read_text(encoding="utf-8")
        fixlet = self_heal.FIXLETS["SH-001"]
        self.assertFalse(fixlet.already_fixed(text))
        missing = fixlet.can_apply(text)
        self.assertEqual(missing, [])
        patched = fixlet.apply(text)
        compile(patched, str(pre), "exec")
        self.assertTrue(fixlet.already_fixed(patched))

    def test_t09_sh001_idempotent(self):
        pre = (REPO / "docs" / "evidence" / "d5" / "test_v09_attack_matrix_offline_PRE_FIX.py")
        if not pre.exists():
            # GATE-3：前置缺失不是跳过的理由——静默 skip 是假绿，必须显式 FAIL
            self.fail("前置缺失不是跳过的理由：docs/evidence/d5/"
                      "test_v09_attack_matrix_offline_PRE_FIX.py 不存在")
        text = pre.read_text(encoding="utf-8")
        fixlet = self_heal.FIXLETS["SH-001"]
        patched = fixlet.apply(text)
        # 对已修复文本再 apply 会因 anchor 缺失而报错（非幂等破坏）
        with self.assertRaises(ValueError):
            fixlet.apply(patched)

    def test_t10_apply_fixlet_dry_run(self):
        pre = (REPO / "docs" / "evidence" / "d5" / "test_v09_attack_matrix_offline_PRE_FIX.py")
        if not pre.exists():
            # GATE-3：前置缺失不是跳过的理由——静默 skip 是假绿，必须显式 FAIL
            self.fail("前置缺失不是跳过的理由：docs/evidence/d5/"
                      "test_v09_attack_matrix_offline_PRE_FIX.py 不存在")
        td = tempfile.TemporaryDirectory()
        src = Path(td.name) / "probe.py"
        src.write_text(pre.read_text(encoding="utf-8"), encoding="utf-8")
        r = self_heal.apply_fixlet("SH-001", str(src), dry_run=True)
        self.assertTrue(r["applied"])
        self.assertEqual(r["replacements"], 5)
        self.assertEqual(r["py_compile"], "ok")
        # dry-run 不写盘
        self.assertNotIn("written", r)
        td.cleanup()

    def test_t11_apply_fixlet_unknown(self):
        with self.assertRaises(ValueError):
            self_heal.apply_fixlet("NOPE", "x.py", dry_run=True)


class PipelineTests(unittest.TestCase):
    def test_t12_pipeline_with_verify(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        src = root / "log.txt"
        src.write_text(
            "FAILED test_boom\n"
            "GateDenied: pre-existing scoped authorization required; Controller self-grant is forbidden\n",
            encoding="utf-8")
        target = root / "probe.py"
        target.write_text("print('ok')\n", encoding="utf-8")
        result = self_heal.run_pipeline(
            src.read_text(encoding="utf-8"),
            auto_fix=False,
            verify_cmds=[[sys.executable, "-m", "py_compile", str(target)]],
            evidence_dir=str(root / "ev"),
            goal_out=str(root / "g.goal.txt"))
        self.assertTrue(result["valid"])
        self.assertEqual(result["steps"][0]["step"], "convert")
        self.assertTrue(result["verify"][0]["ok"])
        td.cleanup()

    def test_t13_pipeline_verify_failure(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        src = root / "log.txt"
        src.write_text("ValueError: boom\n", encoding="utf-8")
        result = self_heal.run_pipeline(
            src.read_text(encoding="utf-8"),
            verify_cmds=[[sys.executable, "-c", "raise SystemExit(1)"]],
            evidence_dir=str(root / "ev"))
        self.assertFalse(result["valid"])
        td.cleanup()


class CliTests(unittest.TestCase):
    def test_t14_cli_convert(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        src = root / "log.txt"
        src.write_text("DRIFT: x | expected=a | actual=b\n", encoding="utf-8")
        goal = root / "g.goal.txt"
        r = subprocess.run(
            [sys.executable, str(HERE / "self_heal.py"), "convert",
             "--source", str(src), "--goal-out", str(goal)],
            capture_output=True, text=True, encoding="utf-8", env=clean_env())
        self.assertEqual(r.returncode, 0, (r.stdout or "") + (r.stderr or ""))
        self.assertTrue(goal.exists())

    def test_t15_cli_list(self):
        r = subprocess.run(
            [sys.executable, str(HERE / "self_heal.py"), "list"],
            capture_output=True, text=True, encoding="utf-8", env=clean_env())
        self.assertEqual(r.returncode, 0, (r.stdout or "") + (r.stderr or ""))
        data = json.loads(r.stdout)
        self.assertIn("SH-001", {f["name"] for f in data["fixlets"]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
