#!/usr/bin/env python3
"""自研 Voxel / Hex-dominant mesher（MVP，cfMesh cartesianMesh / snappy 风格）。

参照：

- DEV_PLAN.md §0.6：scFLOWpre Voxel fitting mesher 的自研旁路（算法不等价
  Cradle，产物兼容 CRDL-FLD OCT/GPH）；
- scFLOW 手册 ``Condition - Mesh Parameter - Voxel Fitting Mesher``：
  BlockMesh（octant 归属判定）→ fitting（贴体/平滑/迭代）→ 面区域映射；
- cfMesh ``cartesianMesh``：背景 octree → hex-dominant；
- OpenFOAM ``snappyHexMesh``：castellation → snap → layers；
- Hexotic / HybridOctree_Hex：平衡与对偶全 hex（后续质量路线）。

流水线（MVP）：MDL/STL 面片 → 根立方盒 + 初始 octree 深度 → 按表面相交
自适应细化（2:1 平衡为后续项）→ 体素分类 outside/cut/inside →
内部 hex + 切割带 polyhedra（或 rough hex）→ 写 ``.oct`` + ``.gph``。
"""

from __future__ import annotations

import argparse
import math
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import numpy as np


@dataclass
class VoxelMeshParams:
    """拟体素化参数（对齐 scFLOW Voxel 控制面）。"""

    initial_depth: int = 2            # 根盒均匀初分（2^depth/轴）
    max_depth: int = 4                # 表面相交自适应细化上限
    max_cells: int = 500_000          # 单元数上限（NUMBER_OF_INITIAL_DIVISION 语义）
    rough_poly: bool = True           # USE_ROUGH_POLY_WHEN_VOXEL_MESHING
    fit_to_surface: bool = False      # 简单 snap：近表面内角点投影到面片
    max_fit_distance_ratio: float = 0.5  # Maximum fitting distance ratio
    margin_ratio: float = 0.02        # 根盒外扩比例


@dataclass
class VoxelMeshResult:
    root_min: np.ndarray
    root_max: np.ndarray
    refinement: np.ndarray            # 前序位图：0=leaf, 1=internal
    leaf_boxes: np.ndarray            # (n_leaves, 2, 3) min/max
    leaf_depths: np.ndarray           # (n_leaves,)
    inside_mask: np.ndarray           # (n_leaves,)
    cut_mask: np.ndarray              # (n_leaves,)
    cells: list[np.ndarray]           # 每个单元顶点索引（convex 有序）
    cell_kind: np.ndarray             # 0=hex, 1=poly(cut)
    hull_faces: list[list[np.ndarray]] = field(default_factory=list)
    vertices: np.ndarray = field(default_factory=lambda: np.empty((0, 3)))

    def stats(self) -> dict:
        n_hex = int(np.count_nonzero(self.cell_kind == 0))
        n_poly = int(np.count_nonzero(self.cell_kind == 1))
        return {
            "n_octants": int(len(self.refinement)),
            "n_leaves": int(len(self.leaf_boxes)),
            "n_inside": int(np.count_nonzero(self.inside_mask)),
            "n_cut": int(np.count_nonzero(self.cut_mask)),
            "n_outside": int(np.count_nonzero(
                ~self.inside_mask & ~self.cut_mask)),
            "n_cells": len(self.cells),
            "n_hex": n_hex,
            "n_poly": n_poly,
            "n_vertices": int(len(self.vertices)),
            "max_depth": int(self.leaf_depths.max())
            if len(self.leaf_depths) else 0,
        }


HEX_CORNERS = np.array([
    [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
    [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
], dtype=np.int64)
HEX_FACES = [
    [0, 1, 2, 3], [4, 7, 6, 5], [0, 4, 5, 1],
    [2, 3, 7, 6], [1, 5, 6, 2], [0, 3, 7, 4],
]
HEX_EDGES = [
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7),
]


# ────────────────────────────────────────────────────────────────────────────
# 表面输入
# ────────────────────────────────────────────────────────────────────────────

def surface_from_mdl(mdl_path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """读取 ``*_part.mdl`` → (points, triangles)。四边形拆成两个三角形。"""
    import mdl
    model = mdl.parse_mdl(str(mdl_path))
    pts = np.asarray(model.xyz, dtype=float).reshape(-1, 3)
    off = np.empty(model.n_faces + 1, dtype=np.int64)
    off[0] = 0
    np.cumsum(model.npe, out=off[1:])
    tris: list[np.ndarray] = []
    for f in range(model.n_faces):
        ids = model.conn[off[f]:off[f + 1]].astype(np.int64)
        n = len(ids)
        if n == 3:
            tris.append(ids)
        elif n == 4:
            tris.append(ids[[0, 1, 2]])
            tris.append(ids[[0, 2, 3]])
    if not tris:
        raise ValueError(f"{mdl_path}: no triangle faces")
    return pts, np.asarray(tris, dtype=np.int64)


def surface_from_stl(stl_path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """读取 STL（meshio）→ (points, triangles)。"""
    import meshio
    m = meshio.read(str(stl_path))
    pts = np.asarray(m.points, dtype=float).reshape(-1, 3)
    cells = [c for c in m.cells if c.type in ("triangle", "quad")]
    if not cells:
        raise ValueError(f"{stl_path}: no triangle/quad cells")
    tris: list[np.ndarray] = []
    for c in cells:
        data = np.asarray(c.data, dtype=np.int64)
        if c.type == "quad":
            tris.append(data[:, [0, 1, 2]])
            tris.append(data[:, [0, 2, 3]])
        else:
            tris.append(data)
    return pts, np.concatenate(tris, axis=0)


def surface_from_mesh(points: np.ndarray,
                      faces: Iterable[np.ndarray] | np.ndarray
                      ) -> tuple[np.ndarray, np.ndarray]:
    """任意多边形面 → 三角化 (points, tris)。"""
    pts = np.asarray(points, dtype=float).reshape(-1, 3)
    tris: list[np.ndarray] = []
    for f in faces:
        ids = np.asarray(f, dtype=np.int64).reshape(-1)
        if ids.size == 3:
            tris.append(ids)
        elif ids.size == 4:
            tris.append(ids[[0, 1, 2]])
            tris.append(ids[[0, 2, 3]])
        elif ids.size > 4:
            for k in range(1, ids.size - 1):
                tris.append(np.array([ids[0], ids[k], ids[k + 1]]))
    if not tris:
        raise ValueError("no faces")
    return pts, np.asarray(tris, dtype=np.int64)


# ────────────────────────────────────────────────────────────────────────────
# 几何基元（AABB/三角形相交、光线、线段求交、最近点）
# ────────────────────────────────────────────────────────────────────────────

def _tri_bbox(tris: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return tris.min(axis=1), tris.max(axis=1)


def _tri_box_overlap(bmin: np.ndarray, bmax: np.ndarray,
                     tri: np.ndarray) -> bool:
    """Akenine-Möller Triangle-Box Overlap（平移盒到原点后 SAT）。"""
    c = (bmin + bmax) * 0.5
    h = (bmax - bmin) * 0.5
    v0 = tri[0] - c
    v1 = tri[1] - c
    v2 = tri[2] - c

    def _axis_test(a: np.ndarray, b: np.ndarray, va: np.ndarray,
                   vb: np.ndarray, vc: np.ndarray) -> bool:
        e = np.cross(a, b)
        p0 = float(np.dot(e, va))
        p1 = float(np.dot(e, vb))
        p2 = float(np.dot(e, vc))
        r = float(h[0] * abs(e[0]) + h[1] * abs(e[1]) + h[2] * abs(e[2]))
        if max(-max(p0, p1, p2), min(p0, p1, p2)) > r:
            return True
        return False

    # 9 条分离轴：边的叉积
    edges = ((v1 - v0), (v2 - v1), (v0 - v2))
    box_axes = (np.array([1, 0, 0]), np.array([0, 1, 0]),
                np.array([0, 0, 1]))
    for a in edges:
        for b in box_axes:
            if _axis_test(a, b, v0, v1, v2):
                return False
    # 3 条盒面轴
    if abs(v0[0]) > h[0] + max(abs(v1[0]), abs(v2[0])) or \
            abs(v0[1]) > h[1] + max(abs(v1[1]), abs(v2[1])) or \
            abs(v0[2]) > h[2] + max(abs(v1[2]), abs(v2[2])):
        return False
    # 平面相交
    normal = np.cross(v1 - v0, v2 - v0)
    d = -float(np.dot(normal, v0))
    r = h[0] * abs(normal[0]) + h[1] * abs(normal[1]) + h[2] * abs(normal[2])
    s = d
    if abs(s) > r:
        return False
    return True


def _ray_tri(orig: np.ndarray, direc: np.ndarray,
             tri: np.ndarray, eps: float = 1e-12) -> Optional[float]:
    """Möller–Trumbore：返回 t>0 或 None。"""
    e1 = tri[1] - tri[0]
    e2 = tri[2] - tri[0]
    pv = np.cross(direc, e2)
    det = float(np.dot(e1, pv))
    if abs(det) < eps:
        return None
    inv = 1.0 / det
    tv = orig - tri[0]
    u = float(np.dot(tv, pv)) * inv
    if u < -eps or u > 1.0 + eps:
        return None
    qv = np.cross(tv, e1)
    v = float(np.dot(direc, qv)) * inv
    if v < -eps or u + v > 1.0 + eps:
        return None
    t = float(np.dot(e2, qv)) * inv
    return t if t > eps else None


def _segment_tri(a: np.ndarray, b: np.ndarray,
                 tri: np.ndarray) -> Optional[np.ndarray]:
    t = _ray_tri(a, b - a, tri)
    if t is None or t > 1.0:
        return None
    return a + t * (b - a)


def _nearest_on_tri(p: np.ndarray, tri: np.ndarray) -> tuple[np.ndarray, float]:
    a, b, c = tri
    ab = b - a
    ac = c - a
    ap = p - a
    d1 = float(np.dot(ab, ap))
    d2 = float(np.dot(ac, ap))
    if d1 <= 0 and d2 <= 0:
        return a.copy(), float(np.dot(ap, ap))
    bp = p - b
    d3 = float(np.dot(ab, bp))
    d4 = float(np.dot(ac, bp))
    if d3 >= 0 and d4 <= d3:
        return b.copy(), float(np.dot(bp, bp))
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3 + 1e-30)
        q = a + v * ab
        return q, float(np.dot(q - p, q - p))
    cp = p - c
    d5 = float(np.dot(ab, cp))
    d6 = float(np.dot(ac, cp))
    if d6 >= 0 and d5 <= d6:
        return c.copy(), float(np.dot(cp, cp))
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6 + 1e-30)
        q = a + w * ac
        return q, float(np.dot(q - p, q - p))
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6) + 1e-30)
        q = b + w * (c - b)
        return q, float(np.dot(q - p, q - p))
    denom = 1.0 / (va + vb + vc + 1e-30)
    v = vb * denom
    w = vc * denom
    q = a + ab * v + ac * w
    return q, float(np.dot(q - p, q - p))


class _TriIndex:
    """按均匀桶索引三角形 AABB，供单元相交与射线候选查询。"""

    def __init__(self, points: np.ndarray, tris: np.ndarray,
                 bmin: np.ndarray, bmax: np.ndarray,
                 n_buckets: int = 48):
        self.points = points
        self.tris = tris
        self.tri_pts = points[tris]                      # (n,3,3)
        self.bmin = np.asarray(bmin, dtype=float)
        self.bmax = np.asarray(bmax, dtype=float)
        self.n = int(n_buckets)
        size = np.maximum(self.bmax - self.bmin, 1e-30) / self.n
        self.size = size
        tb0, tb1 = _tri_bbox(self.tri_pts)
        self.tb0 = tb0
        self.tb1 = tb1
        i0 = np.floor((tb0 - self.bmin) / size).astype(np.int64)
        i1 = np.floor((tb1 - self.bmin) / size).astype(np.int64)
        i0 = np.clip(i0, 0, self.n - 1)
        i1 = np.clip(i1, 0, self.n - 1)
        self.buckets: dict[tuple[int, int, int], list[int]] = {}
        for t in range(len(tris)):
            for i in range(i0[t, 0], i1[t, 0] + 1):
                for j in range(i0[t, 1], i1[t, 1] + 1):
                    for k in range(i0[t, 2], i1[t, 2] + 1):
                        self.buckets.setdefault((i, j, k), []).append(t)

    def _bucket_range(self, lo: np.ndarray, hi: np.ndarray):
        i0 = np.clip(np.floor((lo - self.bmin) / self.size).astype(np.int64),
                     0, self.n - 1)
        i1 = np.clip(np.floor((hi - self.bmin) / self.size).astype(np.int64),
                     0, self.n - 1)
        return i0, i1

    def candidate_ids(self, lo: np.ndarray, hi: np.ndarray) -> set[int]:
        i0, i1 = self._bucket_range(lo, hi)
        out: set[int] = set()
        for i in range(i0[0], i1[0] + 1):
            for j in range(i0[1], i1[1] + 1):
                for k in range(i0[2], i1[2] + 1):
                    out.update(self.buckets.get((i, j, k), ()))
        return out

    def intersects_box(self, lo: np.ndarray, hi: np.ndarray) -> bool:
        for t in self.candidate_ids(lo, hi):
            if _tri_box_overlap(lo, hi, self.tri_pts[t]):
                return True
        return False

    def point_inside(self, p: np.ndarray) -> bool:
        """射线法（+x，跨越桶收集候选），三方向投票提升稳健性。"""
        votes = 0
        for axis in range(3):
            lo = p.copy()
            hi = p.copy()
            if axis == 0:
                hi[0] = self.bmax[0] + 1e-9
            elif axis == 1:
                hi[1] = self.bmax[1] + 1e-9
            else:
                hi[2] = self.bmax[2] + 1e-9
            direc = np.zeros(3)
            direc[axis] = 1.0
            hits = 0
            for t in self.candidate_ids(lo, hi):
                if _ray_tri(p, direc, self.tri_pts[t]) is not None:
                    hits += 1
            if hits % 2 == 1:
                votes += 1
        return votes >= 2

    def intersect_edge(self, a: np.ndarray, b: np.ndarray,
                       lo: np.ndarray, hi: np.ndarray) -> list[np.ndarray]:
        pts: list[np.ndarray] = []
        for t in self.candidate_ids(lo, hi):
            q = _segment_tri(a, b, self.tri_pts[t])
            if q is not None:
                pts.append(q)
        return pts

    def nearest_surface_point(self, p: np.ndarray,
                              k: int = 12) -> tuple[np.ndarray, float]:
        """最近面点（质心树粗筛 + 精确三角形投影）。"""
        centroids = self.tri_pts.mean(axis=1)
        idx = np.argsort(np.sum((centroids - p) ** 2, axis=1))[:k]
        best_q = p.copy()
        best_d = float("inf")
        for t in idx:
            q, d2 = _nearest_on_tri(p, self.tri_pts[t])
            if d2 < best_d:
                best_d = d2
                best_q = q
        return best_q, math.sqrt(best_d)


# ────────────────────────────────────────────────────────────────────────────
# 八叉树
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class _OctNode:
    box_min: np.ndarray
    size: float
    depth: int
    children: Optional[list["_OctNode"]] = None

    @property
    def box_max(self) -> np.ndarray:
        return self.box_min + self.size

    def split(self) -> None:
        h = self.size * 0.5
        kids: list[_OctNode] = []
        for i in range(2):
            for j in range(2):
                for k in range(2):
                    mn = self.box_min + np.array([i * h, j * h, k * h])
                    kids.append(_OctNode(mn, h, self.depth + 1))
        self.children = kids


def _expand_uniform(node: _OctNode, depth: int) -> None:
    if node.depth >= depth:
        return
    node.split()
    for c in node.children:
        _expand_uniform(c, depth)


def _count_leaves(node: _OctNode) -> int:
    if node.children is None:
        return 1
    return sum(_count_leaves(c) for c in node.children)


def _refine_intersecting(node: _OctNode, index: _TriIndex,
                         max_depth: int, cap: int,
                         counter: list[int]) -> None:
    if node.children is None:
        if node.depth >= max_depth or counter[0] >= cap:
            return
        lo = node.box_min
        hi = node.box_max
        if index.intersects_box(lo, hi):
            node.split()
            counter[0] += 7  # 1 个内部节点替换 1 个叶子 → 净增 7 叶子
            for c in node.children:
                _refine_intersecting(c, index, max_depth, cap, counter)
        return
    for c in node.children:
        _refine_intersecting(c, index, max_depth, cap, counter)


def _walk(node: _OctNode, refinement: list[int],
          leaves: list[tuple[np.ndarray, np.ndarray, int]]) -> None:
    if node.children is None:
        refinement.append(0)
        leaves.append((node.box_min.copy(), node.box_max.copy(), node.depth))
        return
    refinement.append(1)
    for c in node.children:
        _walk(c, refinement, leaves)


def _build_octree(points: np.ndarray, tris: np.ndarray,
                  params: VoxelMeshParams) -> tuple[
                      np.ndarray, np.ndarray, _TriIndex, _OctNode]:
    bmin = points.min(axis=0)
    bmax = points.max(axis=0)
    span = (bmax - bmin).max()
    center = (bmin + bmax) * 0.5
    half = span * 0.5 * (1.0 + params.margin_ratio)
    root_min = center - half
    root_max = center + half
    size = root_max[0] - root_min[0]
    index = _TriIndex(points, tris, root_min, root_max)
    root = _OctNode(root_min.astype(float), float(size), 0)
    _expand_uniform(root, params.initial_depth)
    counter = [_count_leaves(root)]
    _refine_intersecting(root, index, params.max_depth,
                         params.max_cells, counter)
    refinement: list[int] = []
    leaves: list[tuple[np.ndarray, np.ndarray, int]] = []
    _walk(root, refinement, leaves)
    return root_min, root_max, index, root


# ────────────────────────────────────────────────────────────────────────────
# 单元构建（hex + 切割 polyhedra）
# ────────────────────────────────────────────────────────────────────────────

def _unique_verts(points: list[np.ndarray],
                  tol: float) -> tuple[np.ndarray, np.ndarray]:
    if not points:
        return np.empty((0, 3)), np.empty((0,), dtype=np.int64)
    arr = np.asarray(points, dtype=float).reshape(-1, 3)
    if len(arr) == 1:
        return arr, np.array([0], dtype=np.int64)
    # 简单贪心去重（单元内顶点数很小）
    out: list[np.ndarray] = []
    ids = np.empty(len(arr), dtype=np.int64)
    for i, p in enumerate(arr):
        found = -1
        for j, q in enumerate(out):
            if np.max(np.abs(p - q)) <= tol:
                found = j
                break
        if found < 0:
            found = len(out)
            out.append(p)
        ids[i] = found
    return np.asarray(out, dtype=float), ids


def _build_cell_geometry(leaf_min: np.ndarray, leaf_max: np.ndarray,
                         index: _TriIndex, params: VoxelMeshParams
                         ) -> tuple[Optional[np.ndarray], Optional[list],
                                    int]:
    """返回 (cell_verts, hull_face_vertex_indices, kind)；None 表示失败。"""
    corners = leaf_min + HEX_CORNERS * (leaf_max - leaf_min)
    if not index.intersects_box(leaf_min, leaf_max):
        return corners, None, 0  # 纯 hex（inside 由调用方判定）
    if params.rough_poly:
        return corners, None, 0
    # 切割单元：内部角点 + 棱-面交点 → 凸包多面体
    inside_flags = np.array(
        [index.point_inside(c) for c in corners], dtype=bool)
    pts: list[np.ndarray] = []
    for c, ok in zip(corners, inside_flags):
        if ok:
            pts.append(c)
    for a, b in HEX_EDGES:
        if inside_flags[a] == inside_flags[b]:
            continue
        hits = index.intersect_edge(corners[a], corners[b],
                                    leaf_min, leaf_max)
        if hits:
            # 取离内部端最近的交点（单元小，通常唯一）
            ref = corners[a] if inside_flags[a] else corners[b]
            hits.sort(key=lambda q: float(np.dot(q - ref, q - ref)))
            pts.append(hits[0])
    if params.fit_to_surface and pts:
        cell_size = float(np.linalg.norm(leaf_max - leaf_min))
        max_dist = params.max_fit_distance_ratio * cell_size
        fitted: list[np.ndarray] = []
        for p in pts:
            q, d = index.nearest_surface_point(p)
            if d <= max_dist:
                fitted.append(q)
            else:
                fitted.append(p)
        pts = fitted
    if len(pts) < 4:
        return corners, None, 0
    uniq, ids = _unique_verts(pts, tol=1e-9 * float(
        np.linalg.norm(leaf_max - leaf_min)))
    if len(uniq) < 4:
        return corners, None, 0
    from scipy.spatial import ConvexHull
    try:
        hull = ConvexHull(uniq, qhull_options="QJ")
    except Exception:  # noqa: BLE001
        return corners, None, 0
    if hull.volume <= 0:
        return corners, None, 0
    # hull.vertices 是按 hull 内索引的有序顶点集
    verts = uniq[hull.vertices]
    remap = np.empty(len(uniq), dtype=np.int64)
    remap[hull.vertices] = np.arange(len(verts))
    faces = [remap[s] for s in hull.simplices]
    return verts, faces, 1


def _orient_face_outward(face: np.ndarray, cell_center: np.ndarray,
                         points: np.ndarray) -> np.ndarray:
    """Newell 法向：使面法向背离 owner 单元中心。"""
    pts = points[face]
    n = np.zeros(3)
    for i in range(len(pts)):
        a = pts[i]
        b = pts[(i + 1) % len(pts)]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    fc = pts.mean(axis=0)
    if float(np.dot(n, fc - cell_center)) < 0:
        return face[::-1].copy()
    return face


def build_mesh(points: np.ndarray, tris: np.ndarray,
               params: Optional[VoxelMeshParams] = None
               ) -> VoxelMeshResult:
    """从三角面片构建 voxel/hex-dominant 网格。"""
    params = params or VoxelMeshParams()
    root_min, root_max, index, _root = _build_octree(
        points, tris, params)
    refinement: list[int] = []
    leaves: list[tuple[np.ndarray, np.ndarray, int]] = []
    _walk(_root, refinement, leaves)
    leaf_boxes = np.asarray([np.stack([lo, hi]) for lo, hi, _ in leaves])
    leaf_depths = np.asarray([d for _, _, d in leaves], dtype=np.int64)

    inside_mask = np.zeros(len(leaves), dtype=bool)
    cut_mask = np.zeros(len(leaves), dtype=bool)
    cells: list[np.ndarray] = []
    cell_kind: list[int] = []
    hull_faces: list[list[np.ndarray]] = []
    global_verts: list[np.ndarray] = []
    global_lookup: dict[tuple, int] = {}

    def _register(pts: np.ndarray) -> np.ndarray:
        ids = np.empty(len(pts), dtype=np.int64)
        for i, p in enumerate(pts):
            key = (round(float(p[0]), 10), round(float(p[1]), 10),
                   round(float(p[2]), 10))
            gid = global_lookup.get(key)
            if gid is None:
                gid = len(global_verts)
                global_lookup[key] = gid
                global_verts.append(p)
            ids[i] = gid
        return ids

    for li, (lo, hi, depth) in enumerate(leaves):
        center = (lo + hi) * 0.5
        is_cut = index.intersects_box(lo, hi)
        cut_mask[li] = bool(is_cut)
        if not is_cut:
            inside_mask[li] = bool(index.point_inside(center))
            if not inside_mask[li]:
                continue
        geo, hull, kind = _build_cell_geometry(lo, hi, index, params)
        if geo is None:
            continue
        ids = _register(geo)
        if len(ids) < 4:
            continue
        cells.append(ids)
        cell_kind.append(kind)
        if kind == 1:
            hull_faces.append(hull)
        else:
            hull_faces.append([])

    vertices = np.asarray(global_verts, dtype=float).reshape(-1, 3)
    result = VoxelMeshResult(
        root_min=root_min, root_max=root_max,
        refinement=np.asarray(refinement, dtype=np.uint8),
        leaf_boxes=leaf_boxes, leaf_depths=leaf_depths,
        inside_mask=inside_mask, cut_mask=cut_mask,
        cells=cells,
        cell_kind=np.asarray(cell_kind, dtype=np.int64),
        hull_faces=hull_faces,
        vertices=vertices)
    return result


# ────────────────────────────────────────────────────────────────────────────
# 面装配 + 写 GPH / OCT
# ────────────────────────────────────────────────────────────────────────────

def assemble_faces(result: VoxelMeshResult
                   ) -> tuple[list[list[int]], np.ndarray, np.ndarray]:
    """枚举全部单元面并去重，返回 (faces, owner, neigh)。"""
    face_map: dict[frozenset, list] = {}
    centers: list[np.ndarray] = []
    for cid, ids in enumerate(result.cells):
        pts = result.vertices[ids]
        centers.append(pts.mean(axis=0))
        if result.cell_kind[cid] == 0:
            face_id_lists = [ids[f] for f in HEX_FACES]
        else:
            face_id_lists = [ids[f] for f in result.hull_faces[cid]]
        for fids in face_id_lists:
            key = frozenset(int(v) for v in fids)
            rec = face_map.get(key)
            if rec is None:
                face_map[key] = [cid, -1, list(fids)]
            elif rec[1] == -1 and rec[0] != cid:
                rec[1] = cid
    faces_out: list[list[int]] = []
    owner_out: list[int] = []
    neigh_out: list[int] = []
    for rec in face_map.values():
        owner, neigh, fids = rec
        arr = np.asarray(fids, dtype=np.int64)
        arr = _orient_face_outward(arr, centers[owner], result.vertices)
        faces_out.append([int(v) for v in arr])
        owner_out.append(owner)
        neigh_out.append(neigh)
    return (faces_out,
            np.asarray(owner_out, dtype=np.int32),
            np.asarray(neigh_out, dtype=np.int32))


def write_outputs(result: VoxelMeshResult,
                  out_prefix: str | Path,
                  *,
                  date: int = 20260813) -> tuple[Path, Path]:
    """写 ``.oct`` + ``.gph``，返回 (oct_path, gph_path)。"""
    import gphstats
    import oct

    out_prefix = Path(out_prefix)
    oct_path = out_prefix.with_suffix(".oct")
    gph_path = out_prefix.with_suffix(".gph")
    oct.write_oct(oct_path, result.root_min, result.root_max,
                  refinement=result.refinement, date=date)
    faces, owner, neigh = assemble_faces(result)
    gphstats.write_gph_volume(
        gph_path, result.vertices, faces, owner, neigh,
        app="pphdecoding", date=date)
    return oct_path, gph_path


def build_from_surface(points: np.ndarray, tris: np.ndarray,
                       out_prefix: str | Path,
                       params: Optional[VoxelMeshParams] = None
                       ) -> tuple[VoxelMeshResult, Path, Path]:
    """便捷入口：三角面 → (result, oct_path, gph_path)。"""
    result = build_mesh(points, tris, params)
    oct_path, gph_path = write_outputs(result, out_prefix)
    return result, oct_path, gph_path


def build_from_mdl(mdl_path: str | Path, out_prefix: str | Path,
                   params: Optional[VoxelMeshParams] = None
                   ) -> tuple[VoxelMeshResult, Path, Path]:
    points, tris = surface_from_mdl(mdl_path)
    return build_from_surface(points, tris, out_prefix, params)


def build_from_stl(stl_path: str | Path, out_prefix: str | Path,
                   params: Optional[VoxelMeshParams] = None
                   ) -> tuple[VoxelMeshResult, Path, Path]:
    points, tris = surface_from_stl(stl_path)
    return build_from_surface(points, tris, out_prefix, params)


def _extract_mdl_from_pph(pph_path: str | Path) -> Path:
    import pph_parser
    arch = pph_parser.PphArchive.open(str(pph_path))
    members = arch.by_role(pph_parser.ROLE_MDL_PART)
    if not members:
        raise ValueError(f"{pph_path}: no MDL part member")
    tmp = Path(tempfile.mkdtemp(prefix="voxmesh_"))
    p = tmp / members[0].name.replace("\\", "_").replace("/", "_")
    p.write_bytes(arch.read_member(members[0].name))
    return p


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="voxel/hex-dominant mesher (self)")
    ap.add_argument("input", help="*.mdl / *.stl / *.pph")
    ap.add_argument("-o", "--out", required=True, help="输出前缀（.oct/.gph）")
    ap.add_argument("--initial-depth", type=int, default=2)
    ap.add_argument("--max-depth", type=int, default=4)
    ap.add_argument("--max-cells", type=int, default=500_000)
    ap.add_argument("--rough", action="store_true",
                    help="切割单元保留 hex（rough poly）")
    ap.add_argument("--fit", action="store_true", help="近表面角点贴体")
    args = ap.parse_args(argv)
    params = VoxelMeshParams(
        initial_depth=args.initial_depth, max_depth=args.max_depth,
        max_cells=args.max_cells, rough_poly=args.rough,
        fit_to_surface=args.fit)
    inp = str(args.input)
    suffix = Path(inp).suffix.lower()
    if suffix == ".mdl":
        result, oct_p, gph_p = build_from_mdl(inp, args.out, params)
    elif suffix == ".stl":
        result, oct_p, gph_p = build_from_stl(inp, args.out, params)
    elif suffix == ".pph":
        mdl = _extract_mdl_from_pph(inp)
        result, oct_p, gph_p = build_from_mdl(mdl, args.out, params)
    else:
        ap.error(f"unsupported input: {inp}")
        return 2
    print(result.stats())
    print(f"oct -> {oct_p}")
    print(f"gph -> {gph_p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
