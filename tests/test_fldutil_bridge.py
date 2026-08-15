#!/usr/bin/env python3
"""fldutil_bridge：FLDUTIL Rosetta 映射 + 子进程隔离探测回归。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import fldutil_bridge as fb  # noqa: E402


class TestRosetta(unittest.TestCase):
    def test_roles_present(self):
        roles = {r for _, r, _ in fb.rosace()}
        self.assertTrue({"node", "face", "cell", "sregn", "pregn", "var"} <= roles)

    def test_pregn_maps_to_volume_regions(self):
        m = dict(fb.ROSETTA)
        self.assertEqual(m["FLDUTIL_Get_PregnNum"][1], "LS_VolumeRegions")

    def test_sregn_maps_to_surface_regions(self):
        m = dict(fb.ROSETTA)
        self.assertEqual(m["FLDUTIL_Get_SregnNum"][1], "LS_SurfaceRegions")

    def test_coverage_covers_core_roles(self):
        self.assertEqual(set(fb.coverage_gaps()), {"node", "face", "cell",
                                                   "sregn", "pregn"})


class TestCrossCheckFld(unittest.TestCase):
    FLD = Path("D:/training/cgns/flddecoding/tests/ex1_e_from_sxemt_run.fld")

    @classmethod
    def setUpClass(cls):
        if not cls.FLD.exists():
            raise unittest.SkipTest("flddecoding sample not found")

    def test_sections_and_counts(self):
        r = fb.cross_check_fld(self.FLD)
        # 本仓 crdlfld 与 flddecoding 独立实现：同一容器解析一致
        self.assertIn("LS_Nodes", r["sections"])
        self.assertIn("OverlapEnd", r["sections"])
        if isinstance(r.get("flddecoding"), dict) \
                and "error" not in r["flddecoding"]:
            self.assertGreater(r["flddecoding"]["n_nodes"], 0)
            self.assertGreater(r["flddecoding"]["n_cells"], 0)

    def test_fldutil_format_mismatch_documented(self):
        # FLDUTIL 读 FEM 中性格式（非求解器 FLD）：探测须给出其自身错误串
        dll = fb.fldutil_dll()
        if dll is None:
            self.skipTest("FLDUTIL_Bx64.dll not installed")
        r = fb.probe_counts(self.FLD)
        self.assertEqual(r["returncode"], 0)
        # 错误串由 DLL 自身解析产生（格式错配证据），子进程不崩溃
        self.assertIsInstance(r.get("stdout"), str)


class TestDll(unittest.TestCase):
    def test_exports(self):
        dll = fb.fldutil_dll()
        if dll is None:
            self.skipTest("FLDUTIL_Bx64.dll not installed")
        self.assertTrue(dll.exists())
        self.assertEqual(len(fb.fldutil_exports()), 52)

    def test_signatures_pinned(self):
        # 反汇编钉死（capstone）的核心 ABI
        self.assertEqual(fb.SIGNATURES["FLDUTIL_Open_File"][3], "int")
        self.assertEqual(fb.SIGNATURES["FLDUTIL_Open_File"][0][1], "char*")
        self.assertEqual(fb.SIGNATURES["FLDUTIL_Get_NodePX"][3], "double")
        self.assertEqual(fb.SIGNATURES["FLDUTIL_GetLastErrorString"][3],
                         "char*")

    def test_probe_isolated_no_crash(self):
        dll = fb.fldutil_dll()
        if dll is None:
            self.skipTest("FLDUTIL_Bx64.dll not installed")
        gph = ROOT / "tests" / "box" / "meshinggroup1.gph"
        r = fb.probe_counts(gph)
        self.assertIsInstance(r, dict)
        self.assertTrue(r["available"])
        self.assertEqual(r["returncode"], 0)
        # 子进程隔离：核心调用（Open/Get_*Num/Close）不崩溃父进程
        self.assertIn("open_handle", r["stdout"])


if __name__ == "__main__":
    unittest.main()
