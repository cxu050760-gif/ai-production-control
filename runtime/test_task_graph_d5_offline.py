#!/usr/bin/env python3
"""D5 offline tests: runtime/task_graph.py（宪法 §17 Task Graph）。"""

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

import task_graph  # noqa: E402


def clean_env() -> dict:
    """过滤超长环境变量 + 保证子进程 UTF-8 安全（Windows 32767 上限）。

    已知基线：test_harness_verify_offline 的 env patch tearDown 在 Windows 上
    失败会把 os.environ 清空/撑爆，导致其后所有 spawn 子进程的测试被污染
    （空环境 + 非 UTF-8 子进程输出 -> UnicodeDecodeError）。此处防御性构造
    最小安全环境，保证 CLI 测试独立可跑。
    """
    env = {k: v for k, v in os.environ.items() if len(v) <= 30000}
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("SYSTEMROOT", r"C:\Windows")
    env.setdefault("SYSTEMDRIVE", "C:")
    return env


class TaskGraphBuildTests(unittest.TestCase):
    def test_t01_linear_dependencies(self):
        g = task_graph.TaskGraph("线性目标")
        g.add_task("A", "实现A")
        g.add_task("B", "实现B", depends_on=["A"])
        g.add_task("C", "实现C", depends_on=["B"])
        v = g.validate()
        self.assertTrue(v["valid"], v["errors"])
        self.assertEqual(v["topological_order"], ["A", "B", "C"])

    def test_t02_cycle_detected(self):
        g = task_graph.TaskGraph("环目标")
        g.add_task("A", "A", depends_on=["B"])
        g.add_task("B", "B", depends_on=["C"])
        g.add_task("C", "C", depends_on=["A"])
        v = g.validate()
        self.assertFalse(v["valid"])
        self.assertEqual(sorted(v["cycles"]), ["A", "B", "C"])
        self.assertTrue(any("cycle" in e for e in v["errors"]))

    def test_t03_parallel_marking_and_symmetry(self):
        g = task_graph.TaskGraph("并行目标")
        g.add_task("A", "A")
        g.add_task("B", "B", parallel_with=["A"])
        g.add_task("C", "C", depends_on=["A", "B"])
        v = g.validate()
        self.assertTrue(v["valid"], v["errors"])
        # parallel_with 对称化
        self.assertIn("A", g.nodes["B"].parallel_with)
        self.assertIn("B", g.nodes["A"].parallel_with)
        j = g.to_json()
        self.assertTrue(any(set(grp) == {"A", "B"} for grp in j["parallel_groups"]))

    def test_t04_dynamic_add_subtask(self):
        g = task_graph.TaskGraph("动态加任务")
        g.add_task("T01", "主任务")
        g.add_subtask("T01", "T01a", "子任务a")
        g.add_subtask("T01", "T01b", "子任务b")
        v = g.validate()
        self.assertTrue(v["valid"], v["errors"])
        self.assertEqual(g.nodes["T01a"].depends_on, ["T01"])
        self.assertEqual(g.nodes["T01b"].depends_on, ["T01"])
        self.assertEqual(len(g.nodes["T01"].subtasks), 2)
        # 动态加任务后拓扑序：T01 必须在前
        self.assertLess(v["topological_order"].index("T01"),
                        v["topological_order"].index("T01a"))

    def test_t05_critical_path_weighted(self):
        g = task_graph.TaskGraph("关键路径")
        g.add_task("S", "起点", est_cost=1)
        g.add_task("M", "中段", depends_on=["S"], est_cost=5)
        g.add_task("O", "旁路", depends_on=["S"], est_cost=9)
        g.add_task("E", "终点", depends_on=["M", "O"], est_cost=1)
        cp = g.critical_path()
        # 最长路径 S -> O -> E（1+9+1=11）vs S -> M -> E（1+5+1=7）
        self.assertEqual(cp["path"], ["S", "O", "E"])
        self.assertEqual(cp["length"], 11.0)

    def test_t06_owner_and_json_structure(self):
        g = task_graph.TaskGraph("owner 目标")
        g.add_task("T01", "实现 owner:alice 的任务", owner="alice")
        j = g.to_json()
        self.assertEqual(j["schema"], task_graph.SCHEMA)
        self.assertTrue(j["non_authority"])
        self.assertIn("human_view", j)
        self.assertEqual(j["nodes"][0]["owner"], "alice")

    def test_t07_rule_based_goal_decomposition(self):
        g = task_graph.build_from_goal("实现模块A。随后验证模块A。修复模块B，与模块A并行。")
        j = g.to_json()
        self.assertTrue(j["valid"], j["validation"]["errors"])
        ids = {n["task_id"] for n in j["nodes"]}
        self.assertEqual(ids, {"T01", "T02", "T03"})
        # T02 是验证任务，依赖 T01（非验证前驱）
        self.assertEqual(g.nodes["T02"].depends_on, ["T01"])
        # T03 并行 T01
        self.assertEqual(g.nodes["T03"].parallel_with, ["T01"])

    def test_t08_duplicate_and_missing_dep_errors(self):
        g = task_graph.TaskGraph("错误目标")
        g.add_task("A", "A")
        with self.assertRaises(ValueError):
            g.add_task("A", "重复")
        g.add_task("B", "B", depends_on=["GHOST"])
        v = g.validate()
        self.assertFalse(v["valid"])
        self.assertTrue(any("GHOST" in e for e in v["errors"]))


class BrainPickTests(unittest.TestCase):
    def test_t09_brain_pick_complexity(self):
        low = task_graph.brain_pick("机械复制单文件格式转换")
        self.assertEqual(low["complexity"], "low")
        self.assertIn(low["brain_id"], ("brain-workbuddy-deepseek-v4-flash", "brain-codex-local"))
        high = task_graph.brain_pick("多文件集成重构安全审计")
        self.assertEqual(high["complexity"], "high")
        self.assertIn(high["brain_id"], ("brain-chatgpt-web", "brain-codex-local"))
        self.assertTrue(high["non_authority"])
        self.assertIn("trace", high)

    def test_t10_brain_pick_missing_registry(self):
        out = task_graph.brain_pick("简单任务", registry_path="C:/definitely/missing/registry.json")
        # registry 缺失时回退默认映射，不崩溃
        self.assertIn(out["brain_id"], (
            "brain-workbuddy-deepseek-v4-flash", "brain-codex-local", "brain-chatgpt-web"))
        self.assertEqual(out["complexity"], "low")


class TaskGraphCliTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_t11_cli_build_add_status(self):
        gf = self.root / "goal.txt"
        gf.write_text("实现模块A。随后验证模块A。", encoding="utf-8")
        out1 = self.root / "tg.json"
        import subprocess
        r = subprocess.run(
            [sys.executable, str(HERE / "task_graph.py"), "build",
             "--goal-file", str(gf), "--out", str(out1)],
            capture_output=True, text=True, encoding="utf-8", env=clean_env())
        self.assertEqual(r.returncode, 0, (r.stdout or "") + (r.stderr or ""))
        data = json.loads(out1.read_text(encoding="utf-8"))
        self.assertTrue(data["valid"])
        # add 动态加任务
        r2 = subprocess.run(
            [sys.executable, str(HERE / "task_graph.py"), "add",
             "--parent", "T01", "--task-id", "T01a", "--desc", "子任务",
             "--state", str(out1), "--out", str(out1)],
            capture_output=True, text=True, encoding="utf-8", env=clean_env())
        self.assertEqual(r2.returncode, 0, (r2.stdout or "") + (r2.stderr or ""))
        data2 = json.loads(out1.read_text(encoding="utf-8"))
        self.assertIn("T01a", {n["task_id"] for n in data2["nodes"]})
        # status
        r3 = subprocess.run(
            [sys.executable, str(HERE / "task_graph.py"), "status", "--state", str(out1)],
            capture_output=True, text=True, encoding="utf-8", env=clean_env())
        self.assertEqual(r3.returncode, 0, (r3.stdout or "") + (r3.stderr or ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
