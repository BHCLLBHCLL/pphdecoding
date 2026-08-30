#!/usr/bin/env python3
"""BAM 报告对拍回归（冲刺 E · 域 6）：宿主 VMDL 产物 × native_bam 拓扑不变量。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bam_reconcile  # noqa: E402
import cad_import  # noqa: E402
import native_bam  # noqa: E402

HOST_MDL = ROOT / "p12a_bam_e2e_part.mdl"
BOX_XT = ROOT / "tests" / "box" / "box.x_t"


def _unit_cube():
    import numpy as np
    pts = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                    [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]],
                   dtype=float)
    tris = np.array([
        [0, 2, 1], [0, 3, 2],          # z=0（朝外 = -z）
        [4, 5, 6], [4, 6, 7],          # z=1
        [0, 1, 5], [0, 5, 4],          # y=0
        [2, 3, 7], [2, 7, 6],          # y=1
        [1, 2, 6], [1, 6, 5],          # x=1
        [0, 4, 7], [0, 7, 3],          # x=0
    ], dtype=np.int64)
    return pts, tris


@unittest.skipUnless(HOST_MDL.is_file(), "P12-A BAM MDL evidence missing")
class TestHostMdlFacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.facts = bam_reconcile.host_mdl_facts(HOST_MDL)

    def test_closed_volume_invariant(self):
        self.assertEqual(self.facts["n_closed_volumes"], 1)
        self.assertTrue(self.facts["watertight"])
        self.assertTrue(self.facts["buildable"])
        self.assertEqual(self.facts["n_open_edges"], 0)
        self.assertEqual(self.facts["n_multifold_edges"], 0)

    def test_region_structure(self):
        self.assertIn("FluidRegion", self.facts["volume_regions"])
        names = self.facts["surface_regions"]
        self.assertIn("@PartSurface_Part", names)
        # box 六个 CAD 面 → 六个 @VMDLSurf_MG0_N 表面区域
        vmdl_surfs = [n for n in names if n.startswith("@VMDLSurf_MG0_")
                      and not n.endswith("Group_0")]
        self.assertEqual(len(vmdl_surfs), 6)

    def test_density_fields_recorded(self):
        self.assertGreater(self.facts["n_faces"], 10_000)
        self.assertGreater(self.facts["n_vertices"], 5_000)
        self.assertGreater(self.facts["n_ridge_halfedges"], 0)


class TestNativeFactsSynthetic(unittest.TestCase):
    """无 pskernel 依赖：合成单位立方体直喂 native_bam。"""

    def test_cube_invariants(self):
        pts, tris = _unit_cube()
        res = native_bam.build_analysis_model(pts, tris)
        r = res.report
        self.assertEqual(r.n_closed_volumes, 1)
        self.assertEqual(r.n_open_edges, 0)
        self.assertEqual(r.n_multifold_edges, 0)
        self.assertTrue(r.buildable)


@unittest.skipUnless(cad_import.available(),
                     "pskernel facet path unavailable")
@unittest.skipUnless(HOST_MDL.is_file() and BOX_XT.is_file(),
                     "BAM evidence/geometry missing")
class TestFullReconcile(unittest.TestCase):
    def test_reconcile_pass(self):
        host = bam_reconcile.host_mdl_facts(HOST_MDL)
        native = bam_reconcile.native_facts(BOX_XT)
        rep = bam_reconcile.reconcile(host, native)
        bad = [r for r in rep["rows"] if r["match"] is False]
        self.assertEqual(bad, [])
        self.assertTrue(rep["ok"])
        # 密度行必须存在但不断言（None）
        dens = [r for r in rep["rows"] if r["kind"] == "density"]
        self.assertTrue(all(r["match"] is None for r in dens))


class TestReconcileLogic(unittest.TestCase):
    def test_mismatch_detected(self):
        host = {"n_closed_volumes": 1, "n_open_edges": 0,
                "watertight": True, "buildable": True,
                "n_multifold_edges": 0, "n_vertices": 100, "n_faces": 200,
                "volume_regions": ["FluidRegion"]}
        native = dict(host, n_closed_volumes=2, n_vertices=8, n_faces=12)
        rep = bam_reconcile.reconcile(host, native)
        self.assertFalse(rep["ok"])
        fails = [r["field"] for r in rep["rows"] if r["match"] is False]
        self.assertIn("n_closed_volumes", fails)

    def test_format_table_has_verdict(self):
        host = {"n_closed_volumes": 1, "n_open_edges": 0,
                "watertight": True, "buildable": True,
                "n_multifold_edges": 0, "n_vertices": 100, "n_faces": 200,
                "volume_regions": ["FluidRegion"]}
        rep = bam_reconcile.reconcile(dict(host), dict(host))
        lines = bam_reconcile.format_table(rep)
        self.assertIn("VERDICT: PASS", lines)


if __name__ == "__main__":
    unittest.main()
