#!/usr/bin/env python3
"""fldstats：官方 scPOST FLD 样例（Samples_POST/FLD）回归。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import fldstats  # noqa: E402

BASE = Path("C:/Program Files/Cradle/CradleCFD2025.2/"
            "Programs_x64/Samples_POST/FLD")


def _sum(name: str) -> dict:
    return fldstats.summarize_fld_file(str(BASE / name))


class TestOfficialSamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not BASE.exists():
            raise unittest.SkipTest("Samples_POST/FLD not installed")

    def test_minimum_hexa_f32(self):
        s = _sum("minimumHexa.fld")
        self.assertEqual(s["n_vertices"], 8)
        self.assertIn("LS_Elements", s["sections"])
        self.assertIn("LS_SurfaceGeometryArray", s["sections"])
        # f32 方言：Pressure 块 8 值
        self.assertIn(("Pressure", "f32", [8]), s["field_sections"])

    def test_example1_100_full(self):
        s = _sum("scSTREAM_example1_100.fld")
        self.assertEqual(s["n_vertices"], 21145)
        self.assertEqual(s["n_cells"], 18240)
        self.assertEqual(s["element_type_histogram"], {"hexahedron(8)": 18240})
        self.assertEqual(s["n_conn_entries"], 18240 * 8)
        self.assertEqual(s["material_bincount"], {1: 17162, 2: 1078})
        # BC 区域名
        self.assertIn("FLUX(velocity)", s["region_names"])
        self.assertIn("AMOM(noslip)", s["region_names"])
        # 场量（f64 方言，按顶点数）
        for name, dt, counts in s["field_sections"]:
            self.assertEqual(dt, "f64")
            for c in counts:
                self.assertEqual(c, 21145)

    def test_mixed_mesh_2cars(self):
        s = _sum("2cars.fld")
        self.assertEqual(s["n_cells"], 1671037)
        # 混合单元类型：34/35/36 = 4/5/6 节点；conn 总长 = Σ(type-30)
        self.assertEqual(s["element_type_histogram"],
                         {"tetrahedron(4)": 1548396, "pyramid(5)": 1619,
                          "prism(6)": 121022})
        self.assertEqual(s["n_conn_entries"], 6927811)

    def test_scteta_mixed(self):
        s = _sum("SCTeta_tutorial.fld")
        self.assertEqual(s["n_cells"], 361868)
        self.assertEqual(s["n_conn_entries"],
                         230090 * 4 + 198 * 5 + 131580 * 6)

    def test_result_only_file(self):
        # 无网格的结果文件（共享基准步网格）：应无网格计数但全节可扫
        s = _sum("scSTREAM_example1_300.fld")
        self.assertIsNone(s["n_vertices"])
        self.assertIsNone(s["n_cells"])
        self.assertIn("Pressure", s["sections"])


if __name__ == "__main__":
    unittest.main()
