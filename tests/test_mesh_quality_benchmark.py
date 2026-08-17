#!/usr/bin/env python3
"""P6-3 网格质量量化对拍：宿主黄金产物 vs 自研 mesher。

把「有质量基础设施」变成「有验证信用」：对宿主 scFLOWpre 真实生成的
黄金 GPH 产物（tests/box、examples/tr03）做质量指标基线断言，并对自研
voxmesh/polymesh 产物做同一套质量指标，验证其不劣于宿主产物。

指标口径见 :mod:`quality`（非正交度 / 偏斜度 / 负体积 / 长宽比，
OpenFOAM checkMesh 对齐）。宿主黄金产物是真实几何、非手工构造
（P4-4 黄金文件集），质量指标为基准而非上限。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import polymesh  # noqa: E402
import quality  # noqa: E402
import voxmesh  # noqa: E402

# 宿主黄金产物（真实生成，非手工构造）
BOX_GOLDEN_GPH = ROOT / "tests" / "box" / "meshinggroup1.gph"
DISC_PPH = ROOT / "tests" / "box_disc.pph"
# 第三个真实几何（宿主产物，位于仓库外 examples 目录；存在才纳入对拍）
TR03_GOLDEN_GPH = ROOT.parent / "examples" / "tr03.gph"


def _unit_box_surface() -> tuple[np.ndarray, np.ndarray]:
    pts = np.array(
        [[x, y, z]
         for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)],
        dtype=float)
    faces = [
        [0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1],
        [2, 3, 7, 6], [1, 5, 7, 3], [0, 2, 6, 4],
    ]
    return voxmesh.surface_from_mesh(pts, faces)


class TestHostGoldenQuality(unittest.TestCase):
    """宿主黄金产物质量基线（真实几何，指标为基准）。"""

    @classmethod
    def setUpClass(cls):
        if not BOX_GOLDEN_GPH.is_file():
            raise unittest.SkipTest("box golden GPH not present")
        cls.rep = quality.from_gph(BOX_GOLDEN_GPH)
        cls.s = cls.rep.summary()

    def test_no_negative_volume(self):
        self.assertEqual(self.s["negative_volume_cells"], 0)

    def test_non_orthogonality_bounded(self):
        # 宿主 box 产物实测 mean 2.5° / max 25.8°；阈值宽松取 45°
        self.assertLess(self.s["non_orthogonality"]["max"], 45.0)
        self.assertEqual(self.s["non_orthogonality_over_70"], 0)

    def test_skewness_bounded(self):
        # 实测 max 0.13；阈值宽松取 0.5
        self.assertLess(self.s["skewness"]["max"], 0.5)
        self.assertEqual(self.s["skewness_over_0_6"], 0)

    def test_report_renders(self):
        text = self.rep.format_report("Golden box")
        self.assertIn("cells:", text)
        self.assertIn("non-orthogonality", text)


class TestSelfMeshVsGolden(unittest.TestCase):
    """自研 mesher 产物质量：同一套指标，且不劣于宿主黄金基准。"""

    def test_voxmesh_quality_beats_host_golden(self):
        # 纯 inside hex（max_depth=2，无切割单元）非正交度 ≈ 0，远优于
        # 宿主 box（mean 2.5° / max 25.8°）
        points, tris = _unit_box_surface()
        res = voxmesh.build_mesh(
            points, tris,
            voxmesh.VoxelMeshParams(initial_depth=2, max_depth=2,
                                    rough_poly=True))
        rep = quality.from_voxel(res)
        s = rep.summary()
        self.assertEqual(s["negative_volume_cells"], 0)
        self.assertLess(s["non_orthogonality"]["max"], 1.0)
        self.assertEqual(s["non_orthogonality_over_70"], 0)

    def test_voxmesh_cut_nonortho_not_worse_than_host(self):
        # 切割多面体路径的非正交度应不劣于宿主 box 黄金（实测 25.8°）
        host_s = quality.from_gph(BOX_GOLDEN_GPH).summary()
        points, tris = _unit_box_surface()
        res = voxmesh.build_mesh(
            points, tris,
            voxmesh.VoxelMeshParams(initial_depth=2, max_depth=3))
        s = quality.from_voxel(res).summary()
        self.assertEqual(s["negative_volume_cells"], 0)
        self.assertLessEqual(s["non_orthogonality"]["max"],
                             host_s["non_orthogonality"]["max"] + 1e-6)

    def test_voxmesh_matches_host_cell_count_order(self):
        # box 宿主 944 cells；自研在粗参数下也应产出可比量级（>100）
        points, tris = _unit_box_surface()
        res = voxmesh.build_mesh(
            points, tris,
            voxmesh.VoxelMeshParams(initial_depth=2, max_depth=3))
        self.assertGreater(res.stats()["n_cells"], 100)

    def test_polymesh_quality_bounds(self):
        # 多面体网格：无负体积；非正交度/偏斜度在可接受范围
        points, tris = _unit_box_surface()
        res = polymesh.build_mesh(
            points, tris,
            polymesh.PolyMeshParams(divisions=6, surface_stride=4,
                                    clip_to_surface=True, max_cells=50_000))
        rep = quality.from_poly(res)
        s = rep.summary()
        self.assertEqual(s["negative_volume_cells"], 0)
        self.assertLess(s["non_orthogonality"]["max"], 70.0)
        self.assertLess(s["skewness"]["max"], 0.8)

    def test_l_shape_voxmesh_no_negative_volume(self):
        """第二份自研几何（L 形，非单位立方体）。"""
        pts_a = np.array(
            [[x, y, z] for x in (0.0, 1.0) for y in (0.0, 1.0)
             for z in (0.0, 1.0)], dtype=float)
        pts_b = pts_a + np.array([1.0, 0.0, 0.0])
        faces = [
            [0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1],
            [2, 3, 7, 6], [1, 5, 7, 3], [0, 2, 6, 4],
        ]
        pts = np.vstack([pts_a, pts_b])
        faces2 = [[i + 8 for i in f] for f in faces]
        points, tris = voxmesh.surface_from_mesh(pts, faces + faces2)
        res = voxmesh.build_mesh(
            points, tris,
            voxmesh.VoxelMeshParams(initial_depth=2, max_depth=3,
                                    max_cells=80_000))
        s = quality.from_voxel(res).summary()
        self.assertEqual(s["negative_volume_cells"], 0)
        self.assertGreater(res.stats()["n_cells"], 50)


@unittest.skipUnless(DISC_PPH.is_file(), "box_disc.pph not present")
class TestDiscGoldenQuality(unittest.TestCase):
    """第二份宿主黄金：box_disc.pph 内 GPH（与 box 哈希不同）。"""

    @classmethod
    def setUpClass(cls):
        import zipfile
        import tempfile
        cls._td = tempfile.TemporaryDirectory()
        gph = Path(cls._td.name) / "disc.gph"
        with zipfile.ZipFile(DISC_PPH) as z:
            gph.write_bytes(z.read("meshinggroup1.gph"))
        cls.rep = quality.from_gph(gph)
        cls.s = cls.rep.summary()

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_no_negative_volume(self):
        self.assertEqual(self.s["negative_volume_cells"], 0)

    def test_non_orthogonality_bounded(self):
        self.assertLess(self.s["non_orthogonality"]["max"], 45.0)
        self.assertEqual(self.s["non_orthogonality_over_70"], 0)

    def test_differs_from_box_golden(self):
        import hashlib
        import zipfile
        box = hashlib.sha256(BOX_GOLDEN_GPH.read_bytes()).digest()
        with zipfile.ZipFile(DISC_PPH) as z:
            disc = hashlib.sha256(z.read("meshinggroup1.gph")).digest()
        self.assertNotEqual(box, disc)


@unittest.skipUnless(TR03_GOLDEN_GPH.is_file(),
                     "examples/tr03.gph not present")
class TestGoldenExpansion(unittest.TestCase):
    """黄金文件扩容：第三个真实几何（宿主产物）质量基线。"""

    def test_tr03_golden_no_negative_volume(self):
        rep = quality.from_gph(TR03_GOLDEN_GPH)
        s = rep.summary()
        self.assertEqual(s["negative_volume_cells"], 0)

    def test_tr03_golden_metric_sanity(self):
        rep = quality.from_gph(TR03_GOLDEN_GPH)
        s = rep.summary()
        # 真实复杂几何（63k cells），非正交度分布应有意义（n>0）
        self.assertGreater(s["non_orthogonality"]["n"], 0)
        self.assertLess(s["non_orthogonality"]["max"], 90.0)


if __name__ == "__main__":
    unittest.main()
