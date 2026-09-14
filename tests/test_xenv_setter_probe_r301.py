#!/usr/bin/env python3
"""R30-1 回归：单变量逐档增量探针（tools/xenv_setter_probe.py）。

口径（审计 §43 ★）：键映射必须**一次只改一个 setter**、**逐档 SaveProject**、
**逐档增量 diff**；多 setter 同改只能粗筛，不得据以否证 —— R26/R28 的假否证
就是这么来的。本文件钉住该工具的离线可验证部分（档位解析、VBS 取值引号、
每档单 setter、读回/返回值记录）；实机部分见 _p12u_gate/r30/summary*.json。
"""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROBE = ROOT / "tools" / "xenv_setter_probe.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestCaseParsing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = _load("probe_r301", PROBE)

    def test_setter_value_getter(self):
        c = self.p.parse_case("SetVoxelOctRefineType=speed:GetVoxelOctRefineType")
        self.assertEqual((c["setter"], c["value"], c["getter"]),
                         ("SetVoxelOctRefineType", "speed",
                          "GetVoxelOctRefineType"))
        self.assertEqual(c["value_literal"], '"speed"')

    def test_pure_read_case(self):
        c = self.p.parse_case("=:GetVoxelOctRefineType")
        self.assertEqual(c["setter"], "")
        self.assertIsNone(c["value_literal"])
        self.assertEqual(c["getter"], "GetVoxelOctRefineType")

    def test_float_and_bool_values(self):
        self.assertEqual(self.p.parse_case("SetX=0.7")["value_literal"], "0.7")
        self.assertEqual(self.p.parse_case("SetX=true")["value_literal"], "True")
        self.assertEqual(self.p.parse_case("SetX=3")["value_literal"], "3")

    def test_rejects_empty_case(self):
        with self.assertRaises(ValueError):
            self.p.parse_case("=:")
        with self.assertRaises(ValueError):
            self.p.parse_case("garbage-without-equals")

    def test_string_value_must_be_quoted_in_vbs(self):
        """裸标识符会被 VBScript 当变量名 → 错误被 On Error 吞掉 → 假否证。"""
        self.assertEqual(self.p.vbs_literal("octree"), '"octree"')
        self.assertNotEqual(self.p.vbs_literal("octree"), "octree")


class TestActions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = _load("probe_r301b", PROBE)

    def _cases(self, *specs):
        return [self.p.parse_case(s) for s in specs]

    def test_one_setter_per_step_with_save_each_step(self):
        cases = self._cases(
            "=:GetVoxelOctRefineType",
            "SetVoxelOctRefineType=speed:GetVoxelOctRefineType",
            "SetVoxelOctRefineType=shape:GetVoxelOctRefineType")
        acts = self.p.build_actions(ROOT / "box.pph", cases,
                                    ROOT / "_p12u_gate" / "unit_r301")
        text = "\n".join(acts)
        self.assertEqual(text.count("SetVoxelOctRefineType"), 2)
        self.assertEqual(text.count("Doc_.SaveProject"), 3)
        self.assertEqual(text.count("GetVoxelOctRefineType"), 3)
        self.assertIn('V1_ = "speed"', acts)
        self.assertIn("RetS1_ = MGS1_.SetVoxelOctRefineType(V1_)", acts)

    def test_each_step_refetches_meshing_group_setting(self):
        cases = self._cases("SetA=x", "SetB=y")
        acts = self.p.build_actions(ROOT / "box.pph", cases,
                                    ROOT / "_p12u_gate" / "unit_r301")
        for i in (0, 1):
            self.assertIn("Set MG%d_ = Doc_.QueryMeshingGroupByIndex(0)" % i,
                          acts)
            self.assertIn("Set MGS%d_ = MG%d_.GetMeshingGroupSetting" % (i, i),
                          acts)


class TestLogParse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = _load("probe_r301c", PROBE)

    def test_readbacks(self):
        text = ("start\nset0_ret=True err=0\nget0_val=speed err=0\n"
                "set1_ret=False err=0\nget1_val=shape err=0\nend\n")
        got = self.p.read_log_values(text)
        self.assertEqual(got["set0_ret"]["value"], "True")
        self.assertEqual(got["get1_val"]["value"], "shape")
        self.assertEqual(got["set1_ret"]["err"], 0)


class TestDiff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = _load("probe_r301d", PROBE)

    def test_incremental_diff_attributes_single_key(self):
        before = {"OCT_MESH.VOXEL_OCT_REFINE_TYPE": "3", "A.B": "1"}
        after = {"OCT_MESH.VOXEL_OCT_REFINE_TYPE": "1", "A.B": "1"}
        self.assertEqual(
            self.p.diff_keys(before, after),
            {"OCT_MESH.VOXEL_OCT_REFINE_TYPE": {"before": "3", "after": "1"}})

    def test_dry_run_writes_plan(self):
        rc = self.p.main(["--no-host", "--tag", "unit_r301",
                          "--case", "SetVoxelOctRefineType=speed:"
                                    "GetVoxelOctRefineType"])
        self.assertEqual(rc, 0)
        vbs = (ROOT / "_p12u_gate" / "unit_r301" / "unit_r301.vbs")
        self.assertTrue(vbs.is_file())
        self.assertIn('"speed"', vbs.read_text(encoding="mbcs"))


if __name__ == "__main__":
    unittest.main()
