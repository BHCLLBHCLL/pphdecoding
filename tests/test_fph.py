#!/usr/bin/env python3
"""fph：官方 scPOST FPH 样例（Samples_POST/FPH）回归。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import crdlfld  # noqa: E402
import fph  # noqa: E402

BASE = Path("C:/Program Files/Cradle/CradleCFD2025.2/"
            "Programs_x64/Samples_POST/FPH")


def _open(name: str):
    data, handles = crdlfld.open_buffer(str(BASE / name))
    if handles is not None:
        mm, f = handles
        mm.close()
        f.close()
    return data


class TestMinimumPolyhedral(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (BASE / "minimumPolyhedral.fph").exists():
            raise unittest.SkipTest("Samples_POST/FPH not installed")

    def setUp(self):
        self.data = _open("minimumPolyhedral.fph")

    def test_mesh_two_tets(self):
        v = fph.fph_vertices(self.data)
        self.assertEqual(v.shape, (5, 3))
        links = fph.fph_links(self.data)
        self.assertEqual(links["n_faces"], 7)
        self.assertEqual(int(links["boundary_mask"].sum()), 6)
        self.assertTrue((links["npe"] == 3).all())
        # 连接表 0 基节点号（21 个条目，节点 0..4）
        self.assertEqual(int(links["conn"].size), 21)
        self.assertEqual(int(links["conn"].max()), 4)
        self.assertEqual(int(links["conn"].min()), 0)

    def test_cells(self):
        m = fph.parse_fph(self.data)
        cells = m["cells"]
        self.assertEqual(cells["n_cells"], 2)
        self.assertEqual(cells["type_histogram"], {"tetrahedron": 2})

    def test_parts_materials(self):
        m = fph.parse_fph(self.data)
        self.assertEqual(m["parts"], ["Part1", "Part2"])
        self.assertEqual(m["materials"]["materials"], ["Fluid", "Solid"])
        self.assertEqual(m["materials"]["part_materials"],
                         {"Part1": "Fluid", "Part2": "Solid"})
        self.assertEqual(m["volume_regions"], ["vol1", "vol2"])

    def test_surface_regions(self):
        regs = fph.fph_surface_regions(self.data)
        names = [r["name"] for r in regs]
        self.assertEqual(names, ["surf1", "surf2"])
        self.assertEqual([int(r["face_ids"].size) for r in regs], [3, 3])
        # 面 id 1 基，覆盖 6 个边界面（内部共享面 1 不属于任何面区域）
        ids = sorted(int(x) for r in regs for x in r["face_ids"])
        self.assertEqual(ids, [1, 2, 3, 4, 5, 6])

    def test_pressure_field(self):
        fields = fph.fph_fields(self.data)
        f = fields["EC_Scalar:PRES"]
        self.assertEqual(f["target"].lower(), "pressure")
        arrs = f["arrays"]
        self.assertEqual(len(arrs), 1)
        # f32 [1.0, 2.0]
        self.assertEqual(len(arrs[0][1]), 2)
        vals = fph.as_f32(arrs[0][1])
        self.assertAlmostEqual(float(vals[0]), 1.0, places=6)
        self.assertAlmostEqual(float(vals[1]), 2.0, places=6)


class TestTutorial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (BASE / "scFLOW_tutorial.fph").exists():
            raise unittest.SkipTest("Samples_POST/FPH not installed")

    def setUp(self):
        self.data = _open("scFLOW_tutorial.fph")

    def test_mesh(self):
        m = fph.parse_fph(self.data)
        self.assertEqual(m["vertices"].shape, (240410, 3))
        links = m["links"]
        self.assertEqual(links["n_faces"], 362657)
        self.assertEqual(m["cells"]["n_cells"], 75062)
        self.assertEqual(int(links["boundary_mask"].sum()), 16487)
        # 多面体网格：npe 3..10
        self.assertEqual(int(links["npe"].min()), 3)
        self.assertEqual(int(links["npe"].max()), 10)
        hist = m["cells"]["type_histogram"]
        self.assertEqual(sum(hist.values()), 75062)
        self.assertIn("polyhedral", hist)

    def test_cvol_and_regions(self):
        m = fph.parse_fph(self.data)
        cvol = m["cvol_ids"]
        self.assertEqual(cvol.size, 75062)
        self.assertEqual(m["n_cvols"], 1)
        self.assertEqual(m["parts"], ["Domain"])
        self.assertEqual(m["volume_regions"], ["FluidRegion"])
        mats = m["materials"]
        self.assertEqual(mats["materials"], ["water(incompressible/20C)"])
        self.assertEqual(mats["part_materials"],
                         {"Domain": "water(incompressible/20C)"})

    def test_surface_regions(self):
        regs = fph.fph_surface_regions(self.data)
        names = [r["name"] for r in regs]
        self.assertEqual(len(names), 7)
        for wanted in ("inlet1", "inlet2", "outlet"):
            self.assertIn(wanted, names)
        counts = {r["name"]: (r["face_ids"].size if r["face_ids"]
                              is not None else 0) for r in regs}
        self.assertEqual(counts["inlet1"], 263)
        self.assertEqual(counts["inlet2"], 255)
        self.assertEqual(counts["outlet"], 242)
        # @UNDEFINED 区域为空（0 面）
        self.assertEqual(counts["@UNDEFINEDENTF"], 0)

    def test_fields(self):
        fields = fph.fph_fields(self.data)
        self.assertEqual(fields["EC_Vector:VEL"]["components"], 3)
        self.assertEqual(len(fields["EC_Vector:VEL"]["arrays"]), 3)
        for name in ("EC_Scalar:PRES", "EC_Scalar:DENS", "EC_Scalar:TEMP",
                     "EC_Scalar:TURK", "EC_Scalar:TEPS", "EC_Scalar:EVIS",
                     "EC_Scalar:ENTL"):
            self.assertIn(name, fields)
            self.assertEqual(len(fields[name]["arrays"]), 1)
            self.assertEqual(fields[name]["arrays"][0][1].size, 75062)
        for name in ("FC_Scalar:YPLS", "FC_Scalar:SURT"):
            kinds = [k for k, _ in fields[name]["arrays"]]
            self.assertEqual(kinds, ["ids", "flags", "values"])
            self.assertEqual(fields[name]["arrays"][0][1].size, 15727)

    def test_meta_targets(self):
        # 元数据节末尾携带目标数据节名字符串
        fields = fph.fph_fields(self.data)
        self.assertEqual(fields["EC_Scalar:PRES"]["target"], "pressure")
        self.assertEqual(fields["EC_Vector:VEL"]["target"], "velocity")
        self.assertEqual(fields["EC_Scalar:TURK"]["target"],
                         "turbulence energy")
        self.assertEqual(fields["FC_Scalar:YPLS"]["target"], "YPLS")

    def test_extra_sections(self):
        m = fph.parse_fph(self.data)
        self.assertEqual(m["element_center"].shape, (75062, 3))
        self.assertIsNotNone(m["assemblies"])
        self.assertIn("<assembly", m["assemblies"])
        self.assertIsNotNone(m["sphfile"])
        self.assertIn("SDAT", m["sphfile"])


if __name__ == "__main__":
    unittest.main()
