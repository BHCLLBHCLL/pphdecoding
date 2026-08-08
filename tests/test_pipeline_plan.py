#!/usr/bin/env python3
"""PipelinePlan / VBS 验收脚本测试（含 box_vbs.vbs 锁定回归）。"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation.history_vbs import (decode_vbs,  # noqa: E402
                                    parse_history_file)
from automation.pipeline_plan import (LOCKED_COMMANDS,  # noqa: E402
                                      PipelinePlan)
from automation.vbs_bridge import read_vbs_lines  # noqa: E402

BOX_PPH = ROOT / "box.pph"
BOX_VBS = ROOT / "tests" / "box_vbs.vbs"


class TestLockedCommands(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actions = parse_history_file(str(BOX_VBS))
        cls.commands = {a["command"] for a in cls.actions}

    def test_recording_present(self):
        self.assertGreater(len(self.actions), 1000)

    def test_locked_commands_are_recorded(self):
        expected = {
            "open_cad_file": "Doc_.OpenCadFile",
            "parts_control": "Conditions_.SetPartsControl",
            "generate_octree": "MeshingGroup_.CreateOctree",
            "set_mode_octree": "Doc_.SetModeOctree",
            "generate_mesh": "MeshingGroup_.CreateMeshMonitor",
            "set_mode_mesh": "Doc_.SetModeMesh",
            "save_project": "Doc_.SaveProject",
        }
        for key, command in expected.items():
            self.assertIn(command, self.commands,
                          f"locked command {key} missing in box_vbs.vbs")
        self.assertIn("Doc_.WaitForWorker", self.commands)

    def test_locked_command_line_numbers(self):
        # 行号证据锁定：与 automation/pipeline_plan.py 中的注释一一对应，
        # 录制文件或命令映射变更时此处必须同步更新。
        lines = decode_vbs(BOX_VBS.read_bytes()).splitlines()
        expected = {
            "open_cad_file": (14, "Doc_.OpenCadFile"),
            "parts_control": (18, "Conditions_.SetPartsControl"),
            "generate_octree": (3110, "MeshingGroup_.CreateOctree"),
            "set_mode_octree": (3112, "Doc_.SetModeOctree"),
            "generate_mesh": (5276, "MeshingGroup_.CreateMeshMonitor"),
            "generate_mesh_wait": (5283, "Doc_.WaitForWorker"),
            "set_mode_mesh": (5285, "Doc_.SetModeMesh"),
            "save_project": (7209, "Doc_.SaveProject"),
        }
        for key, (lineno, command) in expected.items():
            with self.subTest(key=key, lineno=lineno):
                self.assertIn(command, lines[lineno - 1],
                              f"line {lineno} does not contain {command}")

    def test_unlocked_commands_not_recorded(self):
        # 未录制命令保持“未验证”状态：它们不应出现在锁定表中
        for key in ("begin_wrapping", "execute_wrapping",
                    "build_analysis_model", "quit"):
            self.assertNotIn(key, LOCKED_COMMANDS)


class TestPipelinePlan(unittest.TestCase):
    def test_open_command_by_extension(self):
        plan = PipelinePlan(project_path=r"C:\case\case.x_t",
                            steps=["generate_octree"])
        self.assertEqual(plan.open_command(),
                         'Doc_.OpenCadFile "C:\\case\\case.x_t"')
        plan2 = PipelinePlan(project_path=r"C:\case\case.pph",
                             steps=["generate_octree"])
        self.assertEqual(plan2.open_command(),
                         'Doc_.OpenProject "C:\\case\\case.pph"')

    def test_to_vbs_actions_multiline_mesh(self):
        plan = PipelinePlan(project_path=r"C:\case\case.x_t",
                            steps=["generate_mesh"])
        actions = plan.to_vbs_actions()
        self.assertEqual(actions[0], 'Doc_.OpenCadFile "C:\\case\\case.x_t"')
        self.assertIn("MeshingGroup_.CreateMeshMonitor", actions)
        self.assertIn("Doc_.WaitForWorker", actions)

    def test_default_steps_use_locked_commands(self):
        plan = PipelinePlan(project_path="box.x_t")
        actions = plan.to_vbs_actions()
        self.assertTrue(any(a.startswith("Conditions_.SetPartsControl")
                            for a in actions))
        self.assertIn("MeshingGroup_.CreateOctree", actions)
        self.assertIn("Doc_.SetModeOctree", actions)
        self.assertIn("Doc_.SetModeMesh", actions)
        self.assertTrue(any(a.startswith("Doc_.SaveProject") for a in actions))

    def test_custom_commands(self):
        plan = PipelinePlan(
            project_path="case.x_t",
            steps=["generate_octree"],
            commands={"generate_octree": "MeshingGroup_.CreateOctree2"})
        self.assertIn("MeshingGroup_.CreateOctree2", plan.to_vbs_actions())

    def test_unknown_step(self):
        plan = PipelinePlan(project_path="case.x_t", steps=["nope"])
        with self.assertRaises(ValueError):
            plan.to_vbs_actions()

    def test_write_read(self):
        plan = PipelinePlan(project_path="case.x_t",
                            steps=["generate_mesh"], include_quit=True)
        with tempfile.TemporaryDirectory() as td:
            p = plan.write_vbs(Path(td) / "plan.vbs")
            lines = read_vbs_lines(p)
        self.assertIn('Doc_.OpenCadFile "case.x_t"', lines)
        self.assertIn("MeshingGroup_.CreateMeshMonitor", lines)
        self.assertIn("Doc_.WaitForWorker", lines)
        self.assertIn("App_.Quit", lines)

    def test_verify_outputs(self):
        plan = PipelinePlan(project_path=str(BOX_PPH))
        result = plan.verify_outputs()
        self.assertGreaterEqual(result["role_counts"]["mdl"], 1)
        self.assertGreaterEqual(result["role_counts"]["oct"], 1)
        self.assertGreaterEqual(result["role_counts"]["gph"], 1)


if __name__ == "__main__":
    unittest.main()
