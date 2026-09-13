#!/usr/bin/env python3
"""pipeline_plan 结构不变量 + 工具函数直接覆盖（J6.1 回归强化）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation.pipeline_plan import (  # noqa: E402
    BAM_WIZARD_ACTIONS,
    EXECUTE_STEP_MAP,
    LOCKED_COMMANDS,
    OCTREE_ENUM_MAP,
    OCTREE_SETTING_MAP,
    UNLOCKED_COMMANDS,
    WRAP_OCT_PARAM_PAIRS,
    WRAP_PARAM_PAIRS,
    _fmt_oct_num,
    _oct_sect_name,
    _vbs_enum,
    _vbs_value,
    _xenv_get,
)


class TestWrapParamPairs(unittest.TestCase):
    def test_wrap_param_pairs_no_duplicate_keys(self):
        keys = [k for k, _ in WRAP_PARAM_PAIRS]
        self.assertEqual(len(keys), len(set(keys)),
                         f"duplicate keys: "
                         f"{[k for k in keys if keys.count(k) > 1]}")

    def test_wrap_oct_param_pairs_no_duplicate_keys(self):
        keys = [k for k, _ in WRAP_OCT_PARAM_PAIRS]
        self.assertEqual(len(keys), len(set(keys)),
                         f"duplicate keys: "
                         f"{[k for k in keys if keys.count(k) > 1]}")


class TestBAMWizardActions(unittest.TestCase):
    def test_bam_wizard_actions_bookend_sequence(self):
        self.assertEqual(BAM_WIZARD_ACTIONS[0],
                         "MeshingGroup_.BeginMDLWizard")
        end_count = sum(1 for a in BAM_WIZARD_ACTIONS
                        if "EndMDLWizard" in a)
        self.assertEqual(end_count, 1, "EndMDLWizard must appear exactly once")
        end_idx = next(i for i, a in enumerate(BAM_WIZARD_ACTIONS)
                       if "EndMDLWizard" in a)
        self.assertGreater(end_idx, len(BAM_WIZARD_ACTIONS) - 10,
                           "EndMDLWizard should be near the end")
        boundary_idx = next(i for i, a in enumerate(BAM_WIZARD_ACTIONS)
                            if "CreateBoundary" in a)
        mdl_idx = next(i for i, a in enumerate(BAM_WIZARD_ACTIONS)
                       if "CreateMDL" in a and "CreateMultiEntity" not in a)
        self.assertLess(boundary_idx, mdl_idx,
                        "CreateBoundary must precede CreateMDL")


class TestOctreeMaps(unittest.TestCase):
    def test_octree_setting_map_keys_match_enum_map(self):
        setting_keys = {(s, k) for (s, k), _ in OCTREE_SETTING_MAP}
        for enum_key in OCTREE_ENUM_MAP:
            self.assertIn(enum_key, setting_keys,
                          f"OCTREE_ENUM_MAP key {enum_key} not in "
                          f"OCTREE_SETTING_MAP")


class TestUtilityFunctions(unittest.TestCase):
    def test_vbs_value_bool_conversion(self):
        self.assertEqual(_vbs_value("true"), "True")
        self.assertEqual(_vbs_value("TRUE"), "True")
        self.assertEqual(_vbs_value("false"), "False")
        self.assertEqual(_vbs_value("FALSE"), "False")
        self.assertEqual(_vbs_value("3"), "3")
        self.assertEqual(_vbs_value("  true  "), "True")

    def test_vbs_enum_mapping(self):
        self.assertEqual(
            _vbs_enum("OCT_MESH", "VOXEL_OCT_REFINE_TYPE", "3"),
            "octree")
        self.assertEqual(
            _vbs_enum("OCT_MESH", "VOXEL_OCT_REFINE_TYPE", "99"),
            "99")
        self.assertEqual(
            _vbs_enum("NO_SUCH", "KEY", "val"),
            "val")

    def test_oct_sect_name_conversion(self):
        self.assertEqual(_oct_sect_name("Part surface (@Part)"),
                         "@PartSurface_Part")
        self.assertEqual(_oct_sect_name("Part surface (@case1)"),
                         "@PartSurface_case1")
        self.assertEqual(_oct_sect_name("Part surface ()"),
                         "@PartSurface_Part")
        self.assertEqual(_oct_sect_name("@PartSurface_Part"),
                         "@PartSurface_Part")
        self.assertEqual(_oct_sect_name(""), "")
        self.assertEqual(_oct_sect_name("OtherName"), "OtherName")

    def test_fmt_oct_num_precision(self):
        self.assertEqual(_fmt_oct_num(0.001), "0.001")
        self.assertEqual(_fmt_oct_num(1.4), "1.3999999999999999")
        self.assertEqual(_fmt_oct_num("bad"), "bad")
        self.assertEqual(_fmt_oct_num(100), "100")

    def test_xenv_get_dict_and_attr(self):
        xenv = {"FACET": {"KEY": "val"}}
        self.assertEqual(_xenv_get(xenv, "FACET", "KEY"), "val")
        self.assertIsNone(_xenv_get(xenv, "MISSING", "KEY"))
        self.assertIsNone(_xenv_get(None, "FACET", "KEY"))
        self.assertEqual(_xenv_get(xenv, "FACET", "MISSING", "def"), "def")


class TestExecuteStepMap(unittest.TestCase):
    def test_execute_step_map_all_known_steps(self):
        known = set(LOCKED_COMMANDS) | set(UNLOCKED_COMMANDS)
        for group, steps in EXECUTE_STEP_MAP.items():
            for step in steps:
                self.assertIn(step, known,
                              f"EXECUTE_STEP_MAP[{group!r}] references "
                              f"unknown step {step!r}")


if __name__ == "__main__":
    unittest.main()
