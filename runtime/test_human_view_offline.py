"""Offline tests for runtime/human_view.py (Canonical §71 简洁 UI 投影).

Covers:
- H1: 8 canonical §71 sections derivable; empty sections omitted
- H2: conciseness enforced — list caps, goal clipped, no trace leakage
- H3: derived-only semantics — non_authority=True + view_note, no mutation
- H4: accepts both brain_bridge (tasks) and task_graph (task_graph.nodes) shapes
- H5: CLI contract (json/text formats, exit codes)
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (str(HERE),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import human_view as hv  # noqa: E402

PY = sys.executable


def _graph(**extra):
    tasks = [
        {"step": "t1", "detail": "do first", "state": "DONE"},
        {"step": "t2", "detail": "do second", "state": "READY"},
        {"step": "t3", "detail": "do third", "state": "RUNNING"},
        {"step": "t4", "detail": "stuck on auth", "state": "BLOCKED",
         "blocker": "waiting for human authority key"},
        {"step": "t5", "detail": "final", "state": "DISCUSSED"},
    ]
    g = {"goal": "交付执衡 V1.0" + "，补充说明" * 30, "tasks": tasks}
    g.update(extra)
    return g


class H1SectionsTests(unittest.TestCase):
    """H1：八节可派生；空节整体省略。"""

    def test_h1_full_graph_all_applicable_sections(self):
        g = _graph(
            changes=[{"task": "t2", "change": "READY after deps met"}],
            human_gates=[{"title": "业主提供 DeepSeek key", "reason": "真实额度"}],
            final_result="七十五节达成矩阵",
            evidence=["docs/evidence/matrix.md", "delivery/MANIFEST.json"],
            final_acceptance={"verdict": "PASS", "commit": "a840433"})
        v = hv.build_view(g)
        self.assertEqual(v["current_state"], "有阻塞，等待解除")
        self.assertEqual(v["progress"], {"done": 1, "total": 5, "percent": 20.0})
        self.assertEqual(v["blockers"][0]["task"], "t4")
        self.assertIn("human authority", v["blockers"][0]["why"])
        self.assertEqual(v["key_changes"][0]["change"], "READY after deps met")
        self.assertEqual(v["human_gates"][0]["gate"], "业主提供 DeepSeek key")
        self.assertEqual(v["final_result"], "七十五节达成矩阵")
        self.assertEqual(len(v["evidence"]), 2)
        self.assertEqual(v["final_acceptance"]["verdict"], "PASS")
        self.assertEqual(v["next_steps"][0]["task"], "t2")

    def test_h1_empty_sections_omitted_not_null(self):
        g = _graph()
        g["tasks"][3]["state"] = "DISCUSSED"  # 移除唯一 BLOCKED 样本
        v = hv.build_view(g)
        for key in ("blockers", "key_changes", "human_gates",
                    "final_result", "evidence", "final_acceptance"):
            self.assertNotIn(key, v)
        self.assertIn("next_steps", v)  # 有活跃任务 → 有下一步

    def test_h1_failed_state_surfaces(self):
        g = _graph()
        g["tasks"][1]["state"] = "FAILED"
        v = hv.build_view(g)
        self.assertEqual(v["current_state"], "有任务失败，需处理")
        self.assertEqual({b["task"] for b in v["blockers"]}, {"t4", "t2"})

    def test_h1_all_done_and_empty_graph(self):
        g = _graph()
        for t in g["tasks"]:
            t["state"] = "DONE"
        self.assertEqual(hv.build_view(g)["current_state"], "全部完成")
        self.assertEqual(hv.build_view({"goal": "x", "tasks": []})["current_state"],
                         "待开始")


class H2ConcisenessTests(unittest.TestCase):
    """H2：简洁是结构约束——封顶、截断、不泄 Trace。"""

    def test_h2_lists_capped_at_max_list(self):
        g = _graph(
            changes=[{"task": f"c{i}", "change": f"change {i}"} for i in range(20)],
            human_gates=[{"title": f"gate {i}"} for i in range(20)],
            evidence=[f"evidence/{i}.md" for i in range(20)])
        v = hv.build_view(g)
        self.assertEqual(len(v["key_changes"]), hv.MAX_LIST)
        self.assertEqual(len(v["human_gates"]), hv.MAX_LIST)
        self.assertEqual(len(v["evidence"]), hv.MAX_LIST)

    def test_h2_goal_summary_clipped(self):
        v = hv.build_view(_graph())
        self.assertLessEqual(len(v["goal_summary"]), hv.GOAL_SUMMARY_CHARS)

    def test_h2_trace_never_leaks_into_view(self):
        g = _graph(trace={"model": "deepseek", "tokens": 123456,
                          "secret_plan": "do not show"},
                   instruction="authority lives in controller",
                   brain_selection={"brain_id": "x", "cost": 9.9})
        raw = json.dumps(hv.build_view(g), ensure_ascii=False)
        for leaked in ("secret_plan", "tokens", "brain_selection",
                       "instruction", "123456"):
            self.assertNotIn(leaked, raw)


class H3DerivedOnlyTests(unittest.TestCase):
    """H3：纯派生 non_authority，不改输入图。"""

    def test_h3_marks_and_does_not_mutate(self):
        g = _graph()
        snapshot = json.dumps(g, ensure_ascii=False, sort_keys=True)
        v = hv.build_view(g)
        self.assertTrue(v["non_authority"])
        self.assertIn("非独立状态源", v["view_note"])
        self.assertEqual(json.dumps(g, ensure_ascii=False, sort_keys=True),
                         snapshot)

    def test_h3_bad_graph_raises(self):
        with self.assertRaises(ValueError):
            hv.build_view({"goal": "x"})  # 无 tasks


class H4GraphShapeTests(unittest.TestCase):
    """H4：两种图形状均可投影。"""

    def test_h4_taskgraph_node_dict_shape(self):
        g = {"goal": "g", "task_graph": {"nodes": {
            "n1": {"description": "first", "state": "DONE"},
            "n2": {"description": "second", "state": "READY"}}}}
        v = hv.build_view(g)
        self.assertEqual(v["progress"]["total"], 2)
        self.assertEqual(v["next_steps"][0]["task"], "n2")


class H5CliTests(unittest.TestCase):
    """H5：CLI 契约。"""

    def _run(self, *argv):
        return subprocess.run([PY, str(HERE / "human_view.py"), *argv],
                              capture_output=True, text=True,
                              encoding="utf-8", timeout=30)

    def test_h5_json_and_text_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "graph.json"
            f.write_text(json.dumps(_graph(human_gates=[{"title": "G"}]),
                                    ensure_ascii=False), encoding="utf-8")
            r = self._run("--graph", str(f))
            self.assertEqual(r.returncode, 0)
            self.assertEqual(json.loads(r.stdout)["schema"], hv.SCHEMA)
            r2 = self._run("--graph", str(f), "--format", "text")
            self.assertEqual(r2.returncode, 0)
            self.assertIn("执衡 · Human View", r2.stdout)
            self.assertIn("Human Gate", r2.stdout)

    def test_h5_missing_and_invalid_graph_exit_2(self):
        r = self._run("--graph", "Z:/definitely/not/there.json")
        self.assertEqual(r.returncode, 2)
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "bad.json"
            f.write_text("{not json", encoding="utf-8")
            r2 = self._run("--graph", str(f))
        self.assertEqual(r2.returncode, 2)

    def test_h5_malformed_task_entries_fail_closed(self):
        """R-D P2：tasks 含非对象元素 → exit 2 无 traceback。"""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "malformed.json"
            f.write_text(json.dumps({"goal": "g", "tasks": [1, 2]}),
                         encoding="utf-8")
            r = self._run("--graph", str(f))
        self.assertEqual(r.returncode, 2)
        self.assertIn("GRAPH_TASKS_MUST_BE_OBJECTS",
                      json.loads(r.stdout)["problem"])
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_h5_out_writes_view_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "graph.json"
            out = Path(tmp) / "view.json"
            f.write_text(json.dumps(_graph()), encoding="utf-8")
            r = self._run("--graph", str(f), "--out", str(out))
            self.assertEqual(r.returncode, 0)
            view = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(view["current_state"], "有阻塞，等待解除")


if __name__ == "__main__":
    unittest.main()
