#!/usr/bin/env python3
"""R34-2 回归：VBS 生成通道的取值校验（typed 桥之外的第二条写路）。

R33-2 只守住了 typed 桥；`tools/_p12*.py` 那一大批流程走的是 VBS 直写，
落盘前没有任何取值检查。`build_vbs` 是唯一生成口 → 在那里校验。

两个要点：

* 只校验「字面量**紧跟**方法名」的形态（那必然是第一个实参），路径/说明等
  行内字符串一律跳过；
* setter 自己没有词表时按 `note_ref` 回退到 getter（R30 实测
  `SetVoxelOctRefineType` 即此）—— 不跟进引用就会**静默放过**整个 setter
  （这是本项第一版的漏洞，测试钉住它）。
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import vbs_bridge as vb  # noqa: E402


class TestValidateActions(unittest.TestCase):
    def setUp(self):
        vb.clear_value_warnings()

    def test_documented_value_passes(self):
        self.assertEqual(vb.validate_actions(['MGS_.ChangeMesher "poly"']), [])

    def test_bogus_value_warns(self):
        got = vb.validate_actions(['MGS_.ChangeMesher "polyhedral"'])
        self.assertEqual(len(got), 1)
        self.assertIn("polyhedral", got[0])

    def test_note_ref_setter_is_checked(self):
        """setter 无词表 → 按 note_ref 取 getter 的词表（否则静默放过）。"""
        self.assertEqual(sorted(vb._method_value_set(
            "SetVoxelOctRefineType")), ["shape", "speed"])
        self.assertEqual(
            vb.validate_actions(['MGS_.SetVoxelOctRefineType "speed"']), [])
        self.assertEqual(
            len(vb.validate_actions(['MGS_.SetVoxelOctRefineType "voxel"'])), 1)

    def test_paths_and_prose_are_skipped(self):
        acts = ['Doc_.OpenProject "D:/x/y.pph", False',
                'out_.WriteLine "read_a=True err=0"',
                'Doc_.SaveProject "C:/tmp/a b.pph"']
        self.assertEqual(vb.validate_actions(acts), [])

    def test_non_catalog_methods_are_skipped(self):
        self.assertEqual(vb.validate_actions(['Foo_.BarBaz "whatever"']), [])

    def test_second_argument_literals_are_not_misread(self):
        self.assertEqual(
            vb.validate_actions(['MGS_.Something 1, "polyhedral"']), [])


class TestBuildVbs(unittest.TestCase):
    def setUp(self):
        vb.clear_value_warnings()

    def test_default_mode_collects_warnings_only(self):
        text = vb.build_vbs(['MGS_.ChangeMesher "polyhedral"'])
        self.assertIn("ChangeMesher", text)
        self.assertEqual(len(vb.value_warnings), 1)

    def test_strict_mode_blocks_before_writing(self):
        from automation.scflowpre_api import ApiValueError
        with self.assertRaises(ApiValueError):
            vb.build_vbs(['MGS_.ChangeMesher "polyhedral"'],
                         strict_values=True)

    def test_clean_actions_produce_no_warnings(self):
        vb.build_vbs(['MGS_.ChangeMesher "oct"',
                      'MGS_.SetVoxelOctRefineType "shape"'])
        self.assertEqual(vb.value_warnings, [])


class TestBothChannelsAgree(unittest.TestCase):
    """两条写路（typed 桥 / VBS）必须给出同样的判断。"""

    def test_same_verdict_for_same_call(self):
        from automation import scflowpre_api as api
        vb.clear_value_warnings()
        api.clear_value_warnings()
        # 注意：validate_actions 只**返回**告警；累积到模块级的是 build_vbs
        self.assertEqual(
            len(vb.validate_actions(['MGS_.SetVoxelOctRefineType "voxel"'])), 1)
        vb.build_vbs(['MGS_.SetVoxelOctRefineType "voxel"'])
        self.assertTrue(vb.value_warnings)
        self.assertIs(api.check_api_value("MeshingGroupSetting",
                                          "SetVoxelOctRefineType", "voxel",
                                          "mode"), False)


if __name__ == "__main__":
    unittest.main()
