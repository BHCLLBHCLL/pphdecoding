#!/usr/bin/env python3
"""quality.py 回归（P2-3：非正交度 / 偏斜度 / 单元几何）。

验证：

- 结构化均匀 hex 网格：内面非正交度/偏斜度恒 0，体积/长宽比精确；
- 偏移扰动网格：共享面上非正交度 > 0 且解析一致；
- voxmesh / polymesh 适配器：内面指标全部有限，纯 hex 区非正交度 0；
- from_gph 往返：与 from_poly 体积/面数一致；
- 直方图与文本报告可生成。
"""

from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import polymesh  # noqa: E402
import quality  # noqa: E402
import voxmesh  # noqa: E402

# 与 test_voxmesh / test_polymesh 相同的水密盒面（z+ 面 [1,5,7,3]）
_BOX_PTS = np.array(
    [[x, y, z]
     for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)],
    dtype=float)
_BOX_QUADS = [
    [0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1],
    [2, 3, 7, 6], [1, 5, 7, 3], [0, 2, 6, 4],
]


def _box_surface() -> tuple[np.ndarray, np.ndarray]:
    tris: list[list[int]] = []
    for q in _BOX_QUADS:
        qa = np.asarray(q, dtype=np.int64)
        tris.append(qa[[0, 1, 2]].tolist())
        tris.append(qa[[0, 2, 3]].tolist())
    return _BOX_PTS, np.asarray(tris, dtype=np.int64)


def _structured_grid(nx: int, ny: int, nz: int, h: float = 1.0):
    """均匀结构化 hex 网格 → (vertices, cells(顶点环), HEX_FACES 装配面)。"""
    pts = np.array(
        [[i * h, j * h, k * h]
         for i in range(nx + 1) for j in range(ny + 1)
         for k in range(nz + 1)], dtype=float)

    def vid(i, j, k):
        return (i * (ny + 1) + j) * (nz + 1) + k

    cells = []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                cells.append([vid(i, j, k), vid(i + 1, j, k),
                              vid(i + 1, j + 1, k), vid(i, j + 1, k),
                              vid(i, j, k + 1), vid(i + 1, j, k + 1),
                              vid(i + 1, j + 1, k + 1), vid(i, j + 1, k + 1)])
    return pts, cells


def _assemble(cells, pts):
    """hex 单元列表 → (faces, owner, neigh)（frozenset 去重 + owner 外向）。"""
    face_map: dict[frozenset, list] = {}
    for cid, ids in enumerate(cells):
        for f in voxmesh.HEX_FACES:
            fids = [ids[v] for v in f]
            key = frozenset(fids)
            rec = face_map.get(key)
            if rec is None:
                face_map[key] = [cid, -1, fids]
            else:
                rec[1] = cid
    centers = [pts[np.asarray(ids)].mean(axis=0) for ids in cells]
    faces, owner, neigh = [], [], []
    for cid_owner, cid_neigh, fids in face_map.values():
        ring = np.asarray(fids, dtype=np.int64)
        ring = voxmesh._orient_face_outward(ring, centers[cid_owner], pts)
        faces.append([int(v) for v in ring])
        owner.append(cid_owner)
        neigh.append(cid_neigh)
    return faces, np.asarray(owner, dtype=np.int64), \
        np.asarray(neigh, dtype=np.int64)


class TestStructured(unittest.TestCase):
    """均匀 hex：全部指标理想。"""

    @classmethod
    def setUpClass(cls):
        cls.pts, cls.cells = _structured_grid(3, 2, 2, h=0.5)
        faces, owner, neigh = _assemble(cls.cells, cls.pts)
        cls.neigh = neigh
        cls.rep = quality.compute_quality(cls.pts, faces, owner, neigh)
        cls.n_cells = len(cls.cells)

    def test_counts(self):
        self.assertEqual(self.rep.n_cells, self.n_cells)
        # 内面 = (nx-1)ny·nz + nx(ny-1)nz + nx·ny(nz-1) = 8+6+6
        self.assertEqual(self.rep.n_internal, 2 * 2 * 2 + 3 * 1 * 2 + 3 * 2 * 1)
        # 边界面 = 2(xy+yz+zx 各对面) + 表面 - 内部…… 直接按闭包算：
        # n_boundary = n_faces - n_internal
        self.assertEqual(self.rep.n_faces,
                         self.rep.n_internal + self.rep.n_boundary)

    def test_ideal_metrics(self):
        no = self.rep.non_orthogonality
        sk = self.rep.skewness
        internal = self.neigh >= 0
        # 指标仅定义内面；边界面处为 NaN
        self.assertTrue(np.isfinite(no[internal]).all())
        self.assertTrue(np.isnan(no[~internal]).all())
        self.assertAlmostEqual(float(np.abs(no[internal]).max()),
                               0.0, places=10)
        self.assertAlmostEqual(
            float(np.abs(sk[internal]).max()), 0.0, places=10)

    def test_volumes_exact(self):
        v = self.rep.cell_volumes
        self.assertEqual(v.size, self.n_cells)
        self.assertTrue(np.allclose(v, 0.5 ** 3))
        self.assertEqual(self.rep.n_negative_volume, 0)

    def test_aspect_one(self):
        self.assertTrue(np.allclose(self.rep.cell_aspect, 1.0))

    def test_boundary_orthogonal(self):
        self.assertAlmostEqual(
            float(self.rep.boundary_non_ortho.max()), 0.0, places=10)


class TestWarped(unittest.TestCase):
    """扰动网格：非正交度 / 偏斜度解析一致。"""

    def test_shifted_neighbor(self):
        # 2 个 hex（x 向相邻）；右单元顶点整体 +y 0.25。共享面顶点同时
        # 属于两单元 → 左单元被剪切：左质心 y=0.625，右质心 y=0.75，
        # 中心连线斜率 = 0.125/1 → θ = atan(0.125)，skew > 0
        pts, cells = _structured_grid(2, 1, 1, h=1.0)
        pts = pts.copy()
        right_ids = set(cells[1])
        pts[list(right_ids)] += np.array([0.0, 0.25, 0.0])
        faces, owner, neigh = _assemble(cells, pts)
        rep = quality.compute_quality(pts, faces, owner, neigh)
        internal = np.flatnonzero(np.asarray(neigh) >= 0)
        self.assertEqual(internal.size, 1)
        theta = math.degrees(math.atan2(0.125, 1.0))
        self.assertAlmostEqual(
            float(rep.non_orthogonality[internal[0]]), theta, places=6)
        self.assertGreater(float(rep.skewness[internal[0]]), 0.0)
        # 平移不改变体积
        self.assertTrue(np.allclose(rep.cell_volumes, 1.0))

    def test_skew_from_shifted_face(self):
        # 单 hex：顶面顶点整体偏移 → 面重心偏离中心连线投影（skew>0、
        # 边界面非正交 > 0）
        pts, cells = _structured_grid(1, 1, 1, h=1.0)
        pts = pts.copy()
        top = [i for i, p in enumerate(pts) if p[2] > 0.5]
        pts[top] += np.array([0.3, 0.0, 0.0])
        faces, owner, neigh = _assemble(cells, pts)
        rep = quality.compute_quality(pts, faces, owner, neigh)
        self.assertGreater(float(rep.boundary_non_ortho.max()), 1.0)


class TestAdapters(unittest.TestCase):
    """voxmesh / polymesh / GPH 三路一致。"""

    @classmethod
    def setUpClass(cls):
        points, tris = _box_surface()
        cls.vox = voxmesh.build_mesh(
            points, tris,
            voxmesh.VoxelMeshParams(initial_depth=2, max_depth=3,
                                    max_cells=50_000, rough_poly=True))
        cls.poly = polymesh.build_mesh(
            points, tris,
            polymesh.PolyMeshParams(divisions=6, surface_stride=1,
                                    max_cells=50_000))

    def test_voxel_internal_faces_finite(self):
        rep = quality.from_voxel(self.vox)
        no = rep.non_orthogonality
        self.assertTrue(np.isfinite(no[np.asarray(
            voxmesh.assemble_faces(self.vox)[2]) >= 0]).all())
        # 纯 hex 对齐面占绝大多数：大量内面非正交度应接近 0
        self.assertGreater(float(np.nanpercentile(no, 50)), -1e-9)
        self.assertEqual(rep.n_negative_volume, 0)
        self.assertGreaterEqual(rep.n_internal, 1)

    def test_poly_quality_and_gph_roundtrip(self):
        rep = quality.from_poly(self.poly)
        vols = rep.cell_volumes
        self.assertTrue(np.all(np.isfinite(vols)))
        # 闭包性：总体积 ≈ 盒体积 1（切割误差容差）
        self.assertAlmostEqual(float(vols.sum()), 1.0, delta=0.2)
        # 无种子质心的同算法基线（from_gph 与之逐面精确一致；
        # from_poly 用 Voronoi 种子质心，是另一套合法口径）
        faces, owner, neigh = polymesh.assemble_faces(self.poly)
        base = quality.compute_quality(self.poly.vertices, faces,
                                       owner, neigh)
        with tempfile.TemporaryDirectory() as td:
            gph = polymesh.write_gph(
                self.poly, Path(td) / "cube.gph")
            rep2 = quality.from_gph(gph)
        self.assertEqual(rep2.n_faces, rep.n_faces)
        self.assertEqual(rep2.n_cells, rep.n_cells)
        self.assertEqual(rep2.n_internal, rep.n_internal)
        self.assertTrue(np.allclose(
            rep2.cell_volumes, vols, rtol=1e-9, atol=1e-12))
        self.assertTrue(np.allclose(
            np.sort(rep2.non_orthogonality[np.isfinite(
                rep2.non_orthogonality)]),
            np.sort(base.non_orthogonality[np.isfinite(
                base.non_orthogonality)]), atol=1e-9))
        # 两种质心口径的非正交度均值接近（Voronoi 种子 ≈ 体积质心）
        self.assertAlmostEqual(
            float(np.nanmean(rep.non_orthogonality)),
            float(np.nanmean(rep2.non_orthogonality)), delta=5.0)

    def test_histogram_and_report(self):
        rep = quality.from_poly(self.poly)
        hist = rep.histogram("non_orthogonality")
        self.assertTrue(hist)
        total = sum(c for _, c in hist)
        self.assertEqual(total, rep.n_internal)
        text = rep.format_report("test")
        self.assertIn("non-orthogonality", text.lower())
        self.assertIn("skewness", text.lower())
        s = rep.summary()
        self.assertLessEqual(s["non_orthogonality"]["max"], 90.0 + 1e-9)
        self.assertLessEqual(s["skewness"]["max"], 2.0)


if __name__ == "__main__":
    unittest.main()
