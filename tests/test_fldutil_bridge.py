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

    def test_probe_isolated(self):
        dll = fb.fldutil_dll()
        if dll is None:
            self.skipTest("FLDUTIL_Bx64.dll not installed")
        gph = ROOT / "tests" / "box" / "meshinggroup1.gph"
        r = fb.probe_counts(gph)
        self.assertIsInstance(r, dict)
        self.assertIn("available", r)
        self.assertTrue(r["available"])
        # 子进程隔离：即使 ABI 未钉死（返回垃圾句柄），也不应崩溃父进程
        self.assertIsInstance(r.get("returncode"), int)


if __name__ == "__main__":
    unittest.main()
