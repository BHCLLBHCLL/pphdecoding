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


def _closed_box_surface() -> tuple[np.ndarray, np.ndarray]:
    """严格水密的单位立方体（z+ 面修正为 [1,5,7,3]）。"""
    pts = np.array(
        [[x, y, z]
         for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)],
        dtype=float)
    faces = [
        [0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1],
        [2, 3, 7, 6], [1, 5, 7, 3], [0, 2, 6, 4],
    ]
    return voxmesh.surface_from_mesh(pts, faces)


class TestPolyMeshSynthetic(unittest.TestCase):
    def test_clipped_voronoi_cube(self):
        points, tris = _closed_box_surface()
        params = polymesh.PolyMeshParams(
            divisions=6, surface_stride=1, max_cells=50_000)
        res = polymesh.build_mesh(points, tris, params)
        st = res.stats()
        self.assertGreater(st["n_cells"], 80)      # 表面 + 内部种子
        # 8 角点表面种子中 ≥7 个被表面裁剪（恰在角点上的种子退化，
        # point_inside 命中去重后可能投内部票——不保证 8/8）
        self.assertGreaterEqual(st["n_clipped"], 7)
        # 真多边形面（三角/五边/六边，非纯 quad；扭面修复后 npe≤6 为
        # 正常晶格 Voronoi + 裁剪分布）
        self.assertGreaterEqual(st["max_npe"], 5)
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


class TestPolyMeshFeatures(unittest.TestCase):
    """Lloyd 平滑 / 近壁层 / VoroCrust 式特征保形。"""

    def test_sharp_edge_detection(self):
        points, tris = _closed_box_surface()
        sharp = polymesh.detect_sharp_edges(points, tris, 30.0)
        self.assertEqual(len(sharp), 12)  # 立方体 12 棱

    def test_feature_preserve_mirrored_seeds(self):
        points, tris = _closed_box_surface()
        base = polymesh.build_mesh(
            points, tris,
            polymesh.PolyMeshParams(divisions=6, surface_stride=1,
                                    max_cells=50_000))
        feat = polymesh.build_mesh(
            points, tris,
            polymesh.PolyMeshParams(divisions=6, surface_stride=1,
                                    max_cells=50_000, feature_preserve=True))
        s0, s1 = base.stats(), feat.stats()
        # 8 表面顶点 × 1 ghost + 12 尖边 × 2 ghost = 32
        self.assertEqual(s1["n_ghost_seeds"], 8 + 24)
        self.assertEqual(s1["n_sharp_edges"], 12)
        self.assertGreater(s1["n_cells"], 50)
        # 保形后总体积更接近真值 1.0
        v0 = s0["mean_volume"] * s0["n_cells"]
        v1 = s1["mean_volume"] * s1["n_cells"]
        self.assertLess(abs(v1 - 1.0), abs(v0 - 1.0) + 0.05)

    def test_wall_layers_add_cells(self):
        points, tris = _closed_box_surface()
        base = polymesh.build_mesh(
            points, tris,
            polymesh.PolyMeshParams(divisions=6, surface_stride=1,
                                    max_cells=50_000))
        lay = polymesh.build_mesh(
            points, tris,
            polymesh.PolyMeshParams(divisions=6, surface_stride=1,
                                    max_cells=50_000, n_wall_layers=2,
                                    first_layer_ratio=0.3))
        s0, s1 = base.stats(), lay.stats()
        self.assertGreater(s1["n_layer_seeds"], 0)
        self.assertGreater(s1["n_cells"], s0["n_cells"])
        v1 = s1["mean_volume"] * s1["n_cells"]
        self.assertAlmostEqual(v1, 1.0, delta=0.25)

    def test_lloyd_improves_regularity(self):
        points, tris = _closed_box_surface()
        common = dict(divisions=6, surface_stride=1, max_cells=50_000,
                      interior_jitter=0.4)
        r0 = polymesh.build_mesh(
            points, tris, polymesh.PolyMeshParams(lloyd_iterations=0,
                                                  **common))
        r5 = polymesh.build_mesh(
            points, tris, polymesh.PolyMeshParams(lloyd_iterations=5,
                                                  lloyd_damping=0.5,
                                                  **common))
        cv0 = float(np.std(r0.cell_volumes) / np.mean(r0.cell_volumes))
        cv5 = float(np.std(r5.cell_volumes) / np.mean(r5.cell_volumes))
        self.assertLess(cv5, cv0)
        self.assertEqual(r5.lloyd_iterations, 5)

    def test_poly_volume_centroid_box(self):
        # 非对称盒 [0,2]×[0,1]×[0,1]：体积质心 = (1, 0.5, 0.5)
        poly = polymesh._box_poly(np.array([0.0, 0.0, 0.0]),
                                  np.array([2.0, 1.0, 1.0]))
        c = polymesh._poly_volume_centroid(poly)
        self.assertIsNotNone(c)
        self.assertTrue(np.allclose(c, [1.0, 0.5, 0.5], atol=1e-12))

    def test_poly_volume_centroid_shifted_vertices(self):
        # 非均匀顶点分布（一面加密）：体积质心 ≠ 顶点平均，且更靠近加密面
        poly = polymesh._box_poly(np.array([0.0, 0.0, 0.0]),
                                  np.array([1.0, 1.0, 1.0]))
        verts = [np.asarray(v) for v in poly.verts]
        extra = [np.array([1.0, 0.5, 0.5])]
        poly2 = polymesh._Poly(verts + extra, [list(f) for f in poly.faces])
        c = polymesh._poly_volume_centroid(poly2)
        self.assertIsNotNone(c)
        vavg = np.asarray(poly2.verts).mean(axis=0)
        self.assertLess(c[0], vavg[0])   # x=1 面被顶点加密拉偏，体积质心不动

    def test_lloyd_volume_centroid_reduces_nonortho(self):
        # P2-4：体积质心 Lloyd 应降低内面非正交度均值（P2-3 quality 对拍）
        import quality
        points, tris = _closed_box_surface()
        common = dict(divisions=6, surface_stride=1, max_cells=50_000,
                      interior_jitter=0.4)
        r0 = polymesh.build_mesh(
            points, tris, polymesh.PolyMeshParams(lloyd_iterations=0,
                                                  **common))
        r5 = polymesh.build_mesh(
            points, tris, polymesh.PolyMeshParams(lloyd_iterations=6,
                                                  lloyd_damping=0.7,
                                                  **common))
        m0 = float(np.nanmean(quality.from_poly(r0).non_orthogonality))
        m5 = float(np.nanmean(quality.from_poly(r5).non_orthogonality))
        self.assertLess(m5, m0)
        # 总体积守恒（Lloyd 只挪 seed）
        for r in (r0, r5):
            self.assertAlmostEqual(
                float(r.cell_volumes.sum()), 1.0, delta=0.25)

    def test_feature_preserve_deterministic(self):
        points, tris = _closed_box_surface()
        p = polymesh.PolyMeshParams(divisions=5, surface_stride=1,
                                    feature_preserve=True, n_wall_layers=1,
                                    lloyd_iterations=2)
        r1 = polymesh.build_mesh(points, tris, p)
        r2 = polymesh.build_mesh(points, tris, p)
        self.assertEqual(r1.stats()["n_cells"], r2.stats()["n_cells"])
        self.assertEqual(r1.stats()["n_vertices"], r2.stats()["n_vertices"])


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
        self.assertIn("--lloyd", src)
        self.assertIn("--layers", src)
        self.assertIn("--preserve-features", src)


if __name__ == "__main__":
    unittest.main()
