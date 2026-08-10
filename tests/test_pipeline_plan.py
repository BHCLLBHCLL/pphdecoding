#!/usr/bin/env python3
"""PipelinePlan / VBS 验收脚本测试（含 box_vbs*.vbs 锁定回归）。"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation.history_vbs import (decode_vbs,  # noqa: E402
                                    parse_history_file)
from automation.pipeline_plan import (LOCKED_COMMANDS,  # noqa: E402
                                      UNLOCKED_COMMANDS,
                                      PipelinePlan,
                                      build_execute_vbs,
                                      oct_param_actions,
                                      octree_settings_actions,
                                      steps_from_execute_plan)
from automation.vbs_bridge import read_vbs_lines  # noqa: E402

BOX_PPH = ROOT / "box.pph"
BOX_VBS = ROOT / "tests" / "box_vbs.vbs"
BOX_VBS_V3 = ROOT / "tests" / "box_vbs_v3.vbs"
BOX_VBS_V4 = ROOT / "tests" / "box_vbs_v4.vbs"


class TestLockedCommands(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actions = parse_history_file(str(BOX_VBS))
        cls.commands = {a["command"] for a in cls.actions}
        cls.commands_v3 = {
            a["command"] for a in parse_history_file(str(BOX_VBS_V3))}
        cls.commands_v4 = {
            a["command"] for a in parse_history_file(str(BOX_VBS_V4))}

    def test_recording_present(self):
        self.assertGreater(len(self.actions), 1000)

    def test_locked_commands_are_recorded(self):
        expected = {
            "open_cad_file": ("Doc_.OpenCadFile", self.commands),
            "parts_control": ("Conditions_.SetPartsControl", self.commands),
            "open_project": ("Doc_.OpenProject", self.commands_v4),
            "begin_solid_edit": ("MeshingGroup_.BeginSolidEdit",
                                 self.commands_v4),
            "build_analysis_model": ("MeshingGroup_.BuildAnalysisModel",
                                     self.commands_v3),
            "generate_octree": ("MeshingGroup_.CreateOctree", self.commands),
            "set_mode_octree": ("Doc_.SetModeOctree", self.commands),
            "generate_mesh": ("MeshingGroup_.CreateMeshMonitor",
                              self.commands),
            "set_mode_mesh": ("Doc_.SetModeMesh", self.commands),
            "save_project": ("Doc_.SaveProject", self.commands),
        }
        for key, (command, cmds) in expected.items():
            self.assertIn(command, cmds,
                          f"locked command {key} missing in box_vbs*.vbs")
        self.assertIn("Doc_.WaitForWorker", self.commands)

    def test_locked_command_line_numbers(self):
        # 行号证据锁定：与 automation/pipeline_plan.py 中的注释一一对应，
        # 录制文件或命令映射变更时此处必须同步更新。
        lines = {
            BOX_VBS: decode_vbs(BOX_VBS.read_bytes()).splitlines(),
            BOX_VBS_V3: decode_vbs(BOX_VBS_V3.read_bytes()).splitlines(),
            BOX_VBS_V4: decode_vbs(BOX_VBS_V4.read_bytes()).splitlines(),
        }
        expected = [
            (BOX_VBS, 14, "Doc_.OpenCadFile"),
            (BOX_VBS, 18, "Conditions_.SetPartsControl"),
            (BOX_VBS_V4, 14, "MeshingGroup_.BeginSolidEdit"),
            (BOX_VBS_V4, 4352, "Doc_.OpenProject"),
            (BOX_VBS_V3, 210, "MeshingGroup_.BuildAnalysisModel"),
            (BOX_VBS, 3110, "MeshingGroup_.CreateOctree"),
            (BOX_VBS, 3112, "Doc_.SetModeOctree"),
            (BOX_VBS, 5276, "MeshingGroup_.CreateMeshMonitor"),
            (BOX_VBS, 5283, "Doc_.WaitForWorker"),
            (BOX_VBS, 5285, "Doc_.SetModeMesh"),
            (BOX_VBS, 7209, "Doc_.SaveProject"),
        ]
        for path, lineno, command in expected:
            with self.subTest(path=path.name, lineno=lineno,
                              command=command):
                self.assertIn(command, lines[path][lineno - 1],
                              f"line {lineno} does not contain {command}")

    def test_wrapping_commands_removed_from_vbs_defaults(self):
        # Begin/Execute Wrapping 在 v1-v4 录制中均未出现，
        # 已从 VBS 默认命令中移除，改走 NativeBridge。
        for key in ("begin_wrapping", "execute_wrapping"):
            self.assertNotIn(key, LOCKED_COMMANDS)
            self.assertNotIn(key, UNLOCKED_COMMANDS)
        self.assertNotIn("quit", LOCKED_COMMANDS)


class TestPipelinePlan(unittest.TestCase):
    def test_open_command_by_extension(self):
        plan = PipelinePlan(project_path=r"C:\case\case.x_t",
                            steps=["generate_octree"])
        self.assertEqual(plan.open_command(),
                         'Doc_.OpenCadFile "C:\\case\\case.x_t"')
        plan2 = PipelinePlan(project_path=r"C:\case\case.pph",
                             steps=["generate_octree"])
        self.assertEqual(plan2.open_command(),
                         'Doc_.OpenProject "C:\\case\\case.pph", False')

    def test_to_vbs_actions_multiline_mesh(self):
        plan = PipelinePlan(project_path=r"C:\case\case.x_t",
                            steps=["generate_mesh"])
        actions = plan.to_vbs_actions()
        self.assertEqual(actions[0], "Set App_ = GetApplication()")
        self.assertIn('Doc_.OpenCadFile "C:\\case\\case.x_t"', actions)
        self.assertIn("Set MeshingGroup_ = Doc_.QueryMeshingGroupByIndex(0)",
                      actions)
        self.assertIn("MeshingGroup_.CreateMeshMonitor", actions)
        self.assertIn("Doc_.WaitForWorker", actions)
        i = actions.index("MeshingGroup_.CreateMeshMonitor")
        self.assertEqual(
            actions[i - 1],
            "Set MeshingGroup_ = Doc_.QueryMeshingGroupByIndex(0)")

    def test_steps_from_execute_plan(self):
        self.assertEqual(
            steps_from_execute_plan(
                {"bam": True, "oct": True, "mesh": True}),
            ["build_analysis_model",
             "generate_octree", "set_mode_octree",
             "generate_mesh", "set_mode_mesh"])
        self.assertEqual(
            steps_from_execute_plan({"oct": True}),
            ["generate_octree", "set_mode_octree"])
        self.assertEqual(steps_from_execute_plan({}), [])

    def test_build_execute_vbs_pph_with_marker(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            out = td / "execute.vbs"
            marker = td / "execute.done"
            build_execute_vbs(
                r"D:\case\box.pph",
                {"bam": True, "oct": True, "mesh": True},
                out, marker=marker,
                xenv={"FACET": {
                    "SOLID_BASE_LENGTH_FACTOR_FOR_OCTREE": "0.5"}})
            text = decode_vbs(out.read_bytes())
            self.assertIn('Doc_.OpenProject "D:\\case\\box.pph", False', text)
            self.assertIn("MeshingGroup_.BuildAnalysisModel", text)
            self.assertIn(
                "MeshingGroupSetting_.SetAFFaceterLengthFactorForOctree 0.5",
                text)
            self.assertIn("MeshingGroup_.CreateOctree", text)
            self.assertLess(
                text.index(
                    "MeshingGroupSetting_.SetAFFaceterLengthFactorForOctree 0.5"),
                text.index("MeshingGroup_.CreateOctree"))
            self.assertIn("MeshingGroup_.CreateMeshMonitor", text)
            self.assertIn('Doc_.SaveProject "D:\\case\\box.pph"', text)
            self.assertIn(f'Set tf_ = fso_.CreateTextFile("{marker}", True)',
                          text)

    def test_build_execute_vbs_cad_no_save(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            out = td / "execute.vbs"
            build_execute_vbs(r"D:\case\box.x_t",
                              {"bam": True, "oct": True, "mesh": True},
                              out)
            text = decode_vbs(out.read_bytes())
            self.assertIn('Doc_.OpenCadFile "D:\\case\\box.x_t"', text)
            self.assertNotIn("Doc_.SaveProject", text)

    def test_octree_settings_actions(self):
        actions = octree_settings_actions({
            "OCT_MESH": {"FACET_LENGTH_FACTOR": "1",
                         "FACET_ANGLE": "5",
                         "FACET_MAX_WIDTH_FACTOR": "5",
                         "FACET_SPECIFY_EACH_REGION": "false",
                         "COMPLETE_PARALLEL": "false",
                         "VOXEL_OCT_REFINE_TYPE": "3"},
            "FACET": {"OCT_LENGTH_PARAM_FLAG": "true",
                      "OCT_LENGTH_PARAM_TYPE": "5",
                      "OCT_LENGTH_PARAM_ITR": "5",
                      "SOLID_BASE_LENGTH_FACTOR_FOR_OCTREE": "0.5"},
        })
        self.assertIn("Set MeshingGroupSetting_ = "
                      "MeshingGroup_.GetMeshingGroupSetting", actions)
        self.assertIn(
            "MeshingGroupSetting_.SetSolidFacetLengthFactor 1",
            actions)
        self.assertIn(
            "MeshingGroupSetting_.SetSolidFacetAngle 5",
            actions)
        self.assertIn(
            "MeshingGroupSetting_.SetVoxelOctRefineType octree",
            actions)
        self.assertIn(
            "MeshingGroupSetting_.SetAFFaceterLengthFactorForOctree 0.5",
            actions)
        self.assertIn("MeshingGroupSetting_.SetUseOctLengthParam True",
                      actions)
        self.assertEqual(octree_settings_actions(None), [])

    def test_default_steps_use_locked_commands(self):
        plan = PipelinePlan(project_path="box.x_t")
        actions = plan.to_vbs_actions()
        self.assertIn("MeshingGroup_.BeginSolidEdit", actions)
        self.assertTrue(any(a.startswith("Conditions_.SetPartsControl")
                            for a in actions))
        self.assertIn("MeshingGroup_.BuildAnalysisModel", actions)
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

    def test_oct_param_actions_set_minsize_and_type(self):
        """录制要求 SetOctType/SetMinSize；仅 SetParams 不会改边长。"""
        acts = oct_param_actions({
            "mode": "octant",
            "target": 100000,
            "detail": {
                "min_oct_size": 0.001,
                "max_oct_size": 0.001,
                "restrict_max": True,
                "region_size": {
                    "Part surface (@Part)": {"size": 0.001, "range": 0},
                },
            },
        })
        joined = "\n".join(acts)
        self.assertIn("MeshingGroup_.DeleteOctree", joined)
        self.assertIn("OctParam_.SetOctType 3", joined)
        self.assertIn("OctParam_.SetMinSize 0.001", joined)
        self.assertIn("OctParam_.SetParams ArrayParam1_", joined)
        self.assertIn(
            "MeshingGroup_.SetOctCreateTypeWithSolidBaseOct Param1_", joined)
        self.assertIn('ArrayParam1_', joined)
        # 数值按录制写成字符串
        self.assertRegex(joined, r'ArrayParam1_\(\d+\) = "0\.001"')

    def test_verify_outputs(self):
        plan = PipelinePlan(project_path=str(BOX_PPH))
        result = plan.verify_outputs()
        self.assertGreaterEqual(result["role_counts"]["mdl"], 1)
        self.assertGreaterEqual(result["role_counts"]["oct"], 1)
        self.assertGreaterEqual(result["role_counts"]["gph"], 1)


class TestWrappingAndCreateVbs(unittest.TestCase):
    def test_wrapping_sets_parts_control(self):
        from automation.pipeline_plan import wrapping_actions
        acts = wrapping_actions("exec_wrap", "proj.pph")
        joined = "\n".join(acts)
        self.assertIn('SetPartsControl "Wrapping", True', joined)
        self.assertIn("TODO", joined)

    def test_create_parts_begin_solid_edit(self):
        from automation.pipeline_plan import create_parts_actions
        acts = create_parts_actions(
            {"shape": "Cuboid", "name": "Box1"}, "proj.pph")
        self.assertIn("MeshingGroup_.BeginSolidEdit", "\n".join(acts))

    def test_write_nav_vbs_file(self):
        from automation.pipeline_plan import write_nav_vbs
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "w.vbs"
            write_nav_vbs("specify_disc", "p.pph", out)
            text = out.read_text(encoding="utf-16")
            self.assertIn("Discontinuous", text)


class TestConditionsSchema(unittest.TestCase):
    def test_load_bc_filters(self):
        from conditions_schema import load_bc_filters
        f = load_bc_filters()
        self.assertIn("CondBoundaryFlowIO", f.get("bc_flow", frozenset()))


if __name__ == "__main__":
    unittest.main()
