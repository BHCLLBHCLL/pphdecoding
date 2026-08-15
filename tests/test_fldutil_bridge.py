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
