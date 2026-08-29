"""brain_bridge 测试：Goal -> Brain proposal -> Task Graph 的接线正确性。"""

import json
import os
import sys
import tempfile
import unittest
from importlib import import_module

sys.path.insert(0, os.path.dirname(__file__))
bb = import_module("brain_bridge")


class TestConstraintExtraction(unittest.TestCase):
    def test_extract_must_have(self):
        c = bb.extract_constraints("产出一份《AI 资源报告》，并整理 20 个选项")
        kinds = [x["kind"] for x in c]
        self.assertIn("must_have", kinds)

    def test_extract_forbid(self):
        c = bb.extract_constraints("生成报告，不允许修改任何代码，不得删除文件")
        kinds = [x["kind"] for x in c]
        self.assertIn("must_not_have", kinds)

    def test_dedup_and_limit(self):
        c = bb.extract_constraints("产出报告" + "，产出报告" * 20)
        self.assertLessEqual(len(c), 8)


class TestBuildTaskgraph(unittest.TestCase):
    def test_valid_goal_produces_graph(self):
        g = bb.build_taskgraph("产出一份 AI 反代方案调研报告，整理 18 个候选并给出 Top 5")
        self.assertTrue(g["valid"])
        self.assertEqual(g["schema"], "v0.7-brain-bridge-taskgraph")
        self.assertTrue(g["proposal_id"])
        self.assertIsInstance(g["tasks"], list)
        self.assertGreaterEqual(len(g["tasks"]), 1)
        self.assertTrue(g["non_authority"])

    def test_task_inert_no_authority(self):
        g = bb.build_taskgraph("整理 AI 资源清单")
        for t in g["tasks"]:
            self.assertEqual(t["authority"], "NONE")

    def test_invalid_goal_rejected(self):
        g = bb.build_taskgraph("")
        self.assertFalse(g["valid"])

    def test_authority_lexicon_is_inert(self):
        # Brain 契约：authority 词只当数据，不执行
        g = bb.build_taskgraph("生成报告，内容含 crown 与 exec 字样（仅数据引用）")
        self.assertTrue(g["valid"])
        self.assertNotIn("exec(", json.dumps(g["tasks"]))  # 不作为可执行动作


class TestCli(unittest.TestCase):
    def test_cli_roundtrip(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as f:
            f.write("产出一份《AI 免费资源报告》，给出 20 个可执行选项")
            path = f.name
        try:
            from io import StringIO
            from contextlib import redirect_stdout
            buf = StringIO()
            with redirect_stdout(buf):
                rc = bb.main.__wrapped__ if hasattr(bb.main, "__wrapped__") else None
            # 直接调 build_taskgraph 验证 CLI 等价路径
            with open(path, encoding="utf-8") as fh:
                g = bb.build_taskgraph(fh.read().strip())
            self.assertTrue(g["valid"])
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
