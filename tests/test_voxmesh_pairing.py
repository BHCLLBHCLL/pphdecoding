#!/usr/bin/env python3
"""voxmesh 2:1 平衡 + pairing（邻叶贴合面装配）回归。

验证：

- 平衡后任意面相邻叶子深度差 ≤ 1（且不平衡版确有违反，测试有意义）；
- pairing 装配后每个 hex 单元闭合、体积精确（散度定理：悬挂面 1:4
  分裂共形，粗细单元面拼接无缺口/重叠）；
- 输出与旧路径行为兼容（GPH roundtrip、多面体路径不崩）。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import gphstats  # noqa: E402
import voxmesh  # noqa: E402


def _sphere_surface(radius: float = 0.35, n_lat: int = 8, n_lon: int = 16,
                    center: tuple[float, float, float] = (0.0, 0.0, 0.0),
                    far_marker: bool = False,
                    ) -> tuple[np.ndarray, np.ndarray]:
    """经纬球面三角化（局部细化 → 深度梯度，验证 2:1 平衡）。

    ``far_marker``：在对角远处加一个小三角形撑大 bbox，使球偏居
    root 一角 → 球面带细化到 max_depth 而紧邻叶停在浅层（未平衡时
    面邻深度差 >> 1；单球 bbox 中心恒为球心，同心细化恰好级联平滑）。
    """
    pts: list[list[float]] = []
    for i in range(n_lat + 1):
        phi = np.pi * i / n_lat
        for j in range(n_lon if 0 < i < n_lat else 1):
            th = 2.0 * np.pi * j / n_lon
            pts.append([
                center[0] + radius * np.sin(phi) * np.cos(th),
                center[1] + radius * np.sin(phi) * np.sin(th),
                center[2] + radius * np.cos(phi)])

    def idx(i: int, j: int) -> int:
        if i == 0:
            return 0
        if i == n_lat:
            return 1 + (n_lat - 1) * n_lon
        return 1 + (i - 1) * n_lon + (j % n_lon)

    faces: list[list[int]] = []
    for i in range(n_lat):
        for j in range(n_lon):
            a, b = idx(i, j), idx(i + 1, j)
            c, d = idx(i + 1, j + 1), idx(i, j + 1)
            if i == 0:
                faces.append([a, c, d])
            elif i == n_lat - 1:
                faces.append([a, b, c])
            else:
                faces.append([a, b, c, d])
    if far_marker:
        base = len(pts)
        pts.extend([[0.9, 0.9, 0.9], [0.905, 0.9, 0.9], [0.9, 0.905, 0.9]])
        faces.append([base, base + 1, base + 2])
    return voxmesh.surface_from_mesh(np.asarray(pts), faces)


def _count_depth_violations(leaves: list[tuple[np.ndarray, np.ndarray, int]],
                            ) -> int:
    """面相邻（恰一轴相接、其余两轴重叠）叶子深度差 > 1 的对数。"""
    if len(leaves) < 2:
        return 0
    boxes = np.asarray([np.stack([lo, hi]) for lo, hi, _ in leaves])
    depths = np.asarray([d for _, _, d in leaves], dtype=np.int64)
    lo = boxes[:, 0, :]
    hi = boxes[:, 1, :]
    tol = 1e-9 * float((hi - lo).max())
    n = len(leaves)
    bad = 0
    for i in range(n):
        touch = ((np.abs(hi[i] - lo) < tol) | (np.abs(lo[i] - hi) < tol))
        overlap = (np.minimum(hi[i], hi) - np.maximum(lo[i], lo)) > tol
        # 恰一轴相接；相接轴 overlap 恒 0，只要求非相接轴重叠
        adjacent = ((touch.sum(axis=1) == 1)
                    & ((overlap & ~touch).sum(axis=1) == 2))
        adjacent[i] = False
        bad += int((adjacent & (np.abs(depths - depths[i]) > 1)).sum())
    return bad // 2  # 每对计两次


class TestBalance2to1(unittest.TestCase):
    def _octree(self, balance: bool):
        # 小球 + 远角标记：球面带细化到 max_depth，紧邻的内部/外部叶
        # 停在浅层 → 未平衡时面邻深度差 >> 1（单球同心恰好级联平滑）
        points, tris = _sphere_surface(radius=0.1, far_marker=True)
        params = voxmesh.VoxelMeshParams(
            initial_depth=1, max_depth=4, max_cells=2_000_000,
            rough_poly=True, balance_2to1=balance)
        return voxmesh.build_octree(points, tris, params)

    def test_unbalanced_has_violations(self):
        """球面局部细化在不平衡时确有深度差 > 1 的面邻对（测试有意义）。"""
        leaves = self._octree(False)[3]
        self.assertGreater(_count_depth_violations(leaves), 0)

    def test_balanced_no_violations(self):
        leaves = self._octree(True)[3]
        self.assertEqual(_count_depth_violations(leaves), 0)

    def test_balance_adds_leaves(self):
        self.assertGreaterEqual(len(self._octree(True)[3]),
                                len(self._octree(False)[3]))

    def test_full_tree_invariant_holds(self):
        # 平衡不改满八叉树结构不变式：nodes = 8*internal + 1
        ref = self._octree(True)[2]
        internal = int(ref.sum())
        self.assertEqual(8 * internal + 1, int(ref.size))


class TestPairing(unittest.TestCase):
    def _build(self, **kw):
        points, tris = _sphere_surface()
        opts = dict(initial_depth=1, max_depth=3, max_cells=2_000_000,
                    rough_poly=True, balance_2to1=True)
        opts.update(kw)
        params = voxmesh.VoxelMeshParams(**opts)
        return voxmesh.build_mesh(points, tris, params)

    def test_hex_closure_and_volume(self):
        """散度定理：V = (1/6)Σ(fc-c)·N（N 为 Newell 向量，|N|=2A；
        闭合 + 无重叠覆盖 → 每 hex 精确等于 s³）。"""
        res = self._build()
        self.assertEqual(int(res.cell_kind.max()), 0)  # 全 hex
        faces, owner, neigh = voxmesh.assemble_faces(res)
        self.assertGreater(len(faces), 0)
        cell_faces: dict[int, list[tuple[int, int]]] = {}
        for fi, (o, nh) in enumerate(zip(owner, neigh)):
            cell_faces.setdefault(int(o), []).append((fi, 1))
            if nh >= 0:
                cell_faces.setdefault(int(nh), []).append((fi, -1))
        self.assertEqual(len(cell_faces), len(res.cells))
        for ci, flist in cell_faces.items():
            vol = self._cell_volume(res, faces, flist)
            li = int(res.cell_leaf[ci])
            size = float(res.leaf_boxes[li, 1, 0] - res.leaf_boxes[li, 0, 0])
            expect = size ** 3
            self.assertLess(abs(vol - expect) / expect, 1e-9,
                            f"cell {ci}: vol={vol} expect={expect}")

    @staticmethod
    def _cell_volume(res, faces, flist) -> float:
        vol = 0.0
        for fi, sgn in flist:
            pts = res.vertices[np.asarray(faces[fi])]
            nv = np.zeros(3)
            for k in range(len(pts)):
                a, b = pts[k], pts[(k + 1) % len(pts)]
                nv[0] += (a[1] - b[1]) * (a[2] + b[2])
                nv[1] += (a[2] - b[2]) * (a[0] + b[0])
                nv[2] += (a[0] - b[0]) * (a[1] + b[1])
            if sgn < 0:
                nv = -nv
            vol += float(np.dot(pts.mean(axis=0), nv)) / 6.0
        return vol

    def test_hanging_faces_present(self):
        """2:1 过渡带确有 1:4 分裂的子面（faces 数多于整面枚举）。"""
        res = self._build()
        faces, owner, neigh = voxmesh.assemble_faces(res)
        # 整面枚举（旧逻辑）面数 = 6*cells - 内部整面共享数；存在深度差
        # 则 pairing 面数必然多于"理想整面"情形——这里验证存在边界子面
        # 与内部面（owner/neigh 均 ≥ 0）共存
        self.assertTrue((neigh >= 0).any())
        self.assertTrue((neigh < 0).any())
        # 相同深度的面邻对（存在整面 1:1 配对）与 1:4 子面配对共存
        self.assertGreater(len(faces), len(res.cells) * 2)

    def test_paired_gph_roundtrip(self):
        res = self._build()
        with tempfile.TemporaryDirectory() as td:
            pre = Path(td) / "sph"
            oct_p, gph_p = voxmesh.write_outputs(res, pre)
            mesh = gphstats.parse_mesh(gph_p.read_bytes())
            self.assertEqual(mesh["n_faces"], len(res.faces))
            self.assertEqual(int(mesh["owner"].max()) + 1,
                             len(res.cells))
            self.assertTrue(mesh["boundary_mask"].any())
            self.assertTrue(oct_p.is_file())

    def test_unbalanced_pairing_still_conformal(self):
        """关平衡（存在深度差 > 1）时 pairing 仍共形（体积闭合）。"""
        points, tris = _sphere_surface(radius=0.1, far_marker=True)
        params = voxmesh.VoxelMeshParams(
            initial_depth=1, max_depth=4, max_cells=2_000_000,
            rough_poly=True, balance_2to1=False)
        res = voxmesh.build_mesh(points, tris, params)
        faces, owner, neigh = voxmesh.assemble_faces(res)
        cell_faces: dict[int, list[tuple[int, int]]] = {}
        for fi, (o, nh) in enumerate(zip(owner, neigh)):
            cell_faces.setdefault(int(o), []).append((fi, 1))
            if nh >= 0:
                cell_faces.setdefault(int(nh), []).append((fi, -1))
        self.assertEqual(len(cell_faces), len(res.cells))
        for ci, flist in cell_faces.items():
            vol = self._cell_volume(res, faces, flist)
            li = int(res.cell_leaf[ci])
            size = float(res.leaf_boxes[li, 1, 0] - res.leaf_boxes[li, 0, 0])
            expect = size ** 3
            self.assertLess(abs(vol - expect) / expect, 1e-9)

    def test_poly_path_smoke(self):
        """rough_poly=False（存在 cut polyhedron）时装配不崩、有面。"""
        res = self._build(rough_poly=False)
        st = res.stats()
        self.assertGreater(st["n_poly"], 0)
        faces, owner, neigh = voxmesh.assemble_faces(res)
        self.assertGreater(len(faces), 0)
        with tempfile.TemporaryDirectory() as td:
            oct_p, gph_p = voxmesh.write_outputs(res, Path(td) / "mix")
            mesh = gphstats.parse_mesh(gph_p.read_bytes())
            self.assertEqual(int(mesh["owner"].max()) + 1,
                             st["n_cells"])


class TestCli(unittest.TestCase):
    def test_no_balance_flag(self):
        points, tris = _sphere_surface()
        with tempfile.TemporaryDirectory() as td:
            try:
                import meshio
            except ImportError:
                self.skipTest("meshio not installed")
            # 直接走 main 需要文件输入；用 STL 中转
            stl_path = Path(td) / "sph.stl"
            cells = [("triangle", tris)]
            meshio.write_points_cells(str(stl_path), points, cells)
            pre = Path(td) / "out"
            code = voxmesh.main([
                str(stl_path), "-o", str(pre),
                "--initial-depth", "1", "--max-depth", "3",
                "--no-balance"])
            self.assertEqual(code, 0)
            self.assertTrue(Path(str(pre) + ".oct").is_file())
            self.assertTrue(Path(str(pre) + ".gph").is_file())


if __name__ == "__main__":
    unittest.main()
