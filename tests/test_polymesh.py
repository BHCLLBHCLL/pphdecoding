#!/usr/bin/env python3
"""自研原生多面体（clipped Voronoi）mesher 回归。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import gphstats  # noqa: E402
import polymesh  # noqa: E402
import voxmesh  # noqa: E402

BOX_PPH = ROOT / "box.pph"


def _unit_box_surface() -> tuple[np.ndarray, np.ndarray]:
    pts = np.array(
        [[x, y, z]
         for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)],
        dtype=float)
    faces = [
        [0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1],
        [2, 3, 7, 6], [1, 5, 6, 2], [0, 2, 6, 4],
    ]
    return voxmesh.surface_from_mesh(pts, faces)


class TestPolyMeshSynthetic(unittest.TestCase):
    def test_clipped_voronoi_cube(self):
        points, tris = _unit_box_surface()
        params = polymesh.PolyMeshParams(
            divisions=6, surface_stride=1, max_cells=50_000)
        res = polymesh.build_mesh(points, tris, params)
        st = res.stats()
        self.assertGreater(st["n_cells"], 80)      # 8 表面 + 82 内部种子
        self.assertEqual(st["n_clipped"], 8)       # 全部表面种子被裁剪
        self.assertGreater(st["max_npe"], 6)       # 真多面体（非纯 hex）
        self.assertGreater(st["min_npe"], 2)
        self.assertAlmostEqual(
            float(st["mean_volume"]) * st["n_cells"], 1.0, delta=0.25)

    def test_gph_roundtrip(self):
        points, tris = _unit_box_surface()
        with tempfile.TemporaryDirectory() as td:
            pre = Path(td) / "cube"
            res = polymesh.build_mesh(
                points, tris,
                polymesh.PolyMeshParams(
                    divisions=6, surface_stride=1, max_cells=50_000))
            gph = polymesh.write_gph(res, pre.with_suffix(".gph"))
            mesh = gphstats.parse_mesh(gph.read_bytes())
            st = res.stats()
            self.assertEqual(int(mesh["owner"].max()) + 1,
                             st["n_cells"])
            self.assertGreater(int(mesh["boundary_mask"].sum()), 0)
            self.assertGreater(len(mesh["vertices"]), 100)

    def test_deterministic(self):
        points, tris = _unit_box_surface()
        params = polymesh.PolyMeshParams(divisions=5, surface_stride=1)
        r1 = polymesh.build_mesh(points, tris, params)
        r2 = polymesh.build_mesh(points, tris, params)
        self.assertEqual(r1.stats()["n_cells"], r2.stats()["n_cells"])
        self.assertEqual(r1.stats()["n_vertices"],
                         r2.stats()["n_vertices"])


class TestPolyMeshReal(unittest.TestCase):
    @unittest.skipUnless(BOX_PPH.is_file(), "box.pph not present")
    def test_build_from_box_mdl(self):
        import pph_parser
        arch = pph_parser.PphArchive.open(str(BOX_PPH))
        members = arch.by_role(pph_parser.ROLE_MDL_PART)
        self.assertTrue(members)
        with tempfile.TemporaryDirectory() as td:
            mdl_path = Path(td) / "part.mdl"
            mdl_path.write_bytes(arch.read_member(members[0].name))
            pre = Path(td) / "poly_vox"
            res, gph_p = polymesh.build_from_mdl(
                mdl_path, pre,
                polymesh.PolyMeshParams(
                    divisions=6, surface_stride=24, max_cells=100_000))
            st = res.stats()
            self.assertGreater(st["n_cells"], 100)
            self.assertGreater(st["n_clipped"], 0)
            mesh = gphstats.parse_mesh(gph_p.read_bytes())
            self.assertEqual(int(mesh["owner"].max()) + 1,
                             st["n_cells"])

    @unittest.skipUnless(BOX_PPH.is_file(), "box.pph not present")
    def test_cli_smoke(self):
        with tempfile.TemporaryDirectory() as td:
            pre = Path(td) / "cli_poly"
            code = polymesh.main([
                str(BOX_PPH), "-o", str(pre),
                "--divisions", "5", "--surface-stride", "32"])
            self.assertEqual(code, 0)
            self.assertTrue(Path(str(pre) + ".gph").is_file())


class TestGuiWiring(unittest.TestCase):
    def test_execute_menu_and_dialog_wired(self):
        src = (ROOT / "pph_gui.py").read_text(encoding="utf-8")
        self.assertIn("Polyhedral Mesh (Self Build)", src)
        self.assertIn("def _build_poly_mesh", src)
        self.assertIn("def _poly_params_dialog", src)
        self.assertIn("polymesh.build_from_mdl", src)

    def test_native_execute_pipeline_wired(self):
        src = (ROOT / "pph_gui.py").read_text(encoding="utf-8")
        self.assertIn("def _run_native_pipeline", src)
        self.assertIn("voxmesh.build_octree", src)
        self.assertIn("polymesh.build_from_mdl", src)
        self.assertIn("未启用 scFLOWpre API", src)

    def test_module_cli_args(self):
        src = (ROOT / "polymesh.py").read_text(encoding="utf-8")
        self.assertIn("--divisions", src)
        self.assertIn("--surface-stride", src)
        self.assertIn("--no-clip", src)


if __name__ == "__main__":
    unittest.main()
