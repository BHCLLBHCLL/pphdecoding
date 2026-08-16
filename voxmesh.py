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
自适应细化 → 面邻 2:1 平衡（可选）→ 体素分类 outside/cut/inside →
内部 hex + 切割带 polyhedra（或 rough hex）→ pairing 面装配
（邻叶贴合面，悬挂面自动 1:4 分裂，hex 全共形）→ 写 ``.oct`` + ``.gph``。
"""

from __future__ import annotations

import argparse
import math
import tempfile
from collections import deque
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
    balance_2to1: bool = True         # 面邻 2:1 平衡（相邻叶子深度差 ≤ 1）


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
    # pairing 装配结果（build_mesh 内经邻叶贴合面法填充；hex 全共形）
    cell_leaf: np.ndarray = field(
        default_factory=lambda: np.empty(0, dtype=np.int64))  # cell → leaf
    faces: Optional[list[list[int]]] = None    # 顶点索引环（外向 owner）
    face_owner: Optional[np.ndarray] = None    # (n_faces,) int32
    face_neigh: Optional[np.ndarray] = None    # (n_faces,) int32, -1=边界
    # 面区域映射（P2-2）：face_region[i] = 边界面 i 的输入表面区域 id
    # （-1 = 未分配/内部面/计算域边界）；region_names[id] = 区域名
    face_region: np.ndarray = field(
        default_factory=lambda: np.empty(0, dtype=np.int64))
    region_names: list[str] = field(default_factory=list)

    def stats(self) -> dict:
        n_hex = int(np.count_nonzero(self.cell_kind == 0))
        n_poly = int(np.count_nonzero(self.cell_kind == 1))
        out = {
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
            "n_faces": (len(self.faces)
                        if self.faces is not None else None),
        }
        if self.faces is not None and self.face_owner is not None:
            boundary = int(np.count_nonzero(
                np.asarray(self.face_neigh) < 0))
            out["n_boundary_faces"] = boundary
            if self.face_region.size:
                out["surface_regions"] = {
                    self.region_names[ri] if ri < len(self.region_names)
                    else f"surface_{ri}": int(np.count_nonzero(
                        self.face_region == ri))
                    for ri in np.unique(self.face_region) if ri >= 0
                }
        return out


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
# HEX_FACES[i] ↔ (axis, sign)：面的外法向（局部盒坐标系）
_FACE_DIRS = [
    (2, -1), (2, 1), (1, -1), (1, 1), (0, 1), (0, -1),
]


# ────────────────────────────────────────────────────────────────────────────
# 表面输入
# ────────────────────────────────────────────────────────────────────────────

def surface_from_mdl(mdl_path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """读取 ``*_part.mdl`` → (points, triangles)。四边形拆成两个三角形。"""
    pts, tris, _frid, _names = _surface_from_mdl_ex(mdl_path)
    return pts, tris


def _surface_from_mdl_ex(mdl_path: str | Path) -> tuple[
        np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """MDL → (points, triangles, tri_region, region_names)。

    ``tri_region``：拆分后每个三角形的面区域 id（frid，四边形拆分
    两个三角形继承同一 frid）；``region_names``：frid → 区域名
    （来自 LS_MdlSurfaceRegions，未匹配的 id 回退 ``surface_{i}``）。
    """
    import mdl
    model = mdl.parse_mdl(str(mdl_path))
    pts = np.asarray(model.xyz, dtype=float).reshape(-1, 3)
    off = np.empty(model.n_faces + 1, dtype=np.int64)
    off[0] = 0
    np.cumsum(model.npe, out=off[1:])
    tris: list[np.ndarray] = []
    tri_region: list[int] = []
    frid = (np.asarray(model.frid, dtype=np.int64).reshape(-1)
            if model.frid is not None and len(model.frid)
            else np.zeros(model.n_faces, dtype=np.int64))
    for f in range(model.n_faces):
        ids = model.conn[off[f]:off[f + 1]].astype(np.int64)
        n = len(ids)
        r = int(frid[f])
        if n == 3:
            tris.append(ids)
            tri_region.append(r)
        elif n == 4:
            tris.append(ids[[0, 1, 2]])
            tris.append(ids[[0, 2, 3]])
            tri_region.extend((r, r))
    if not tris:
        raise ValueError(f"{mdl_path}: no triangle faces")
    names_by_id = {int(r.index): r.name for r in model.surface_regions}
    n_regions = max(tri_region) + 1 if tri_region else 0
    region_names = [names_by_id.get(i, f"surface_{i}")
                    for i in range(n_regions)]
    return (pts, np.asarray(tris, dtype=np.int64),
            np.asarray(tri_region, dtype=np.int64), region_names)


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
        """射线法（跨桶收集候选），三方向投票提升稳健性。

        命中按 t 去重后数奇偶：命中点落在共享边/对角线上时会被
        两侧三角形各记一次（如盒面四边形对角线），不去重会把
        内部点误判为外部（网格出现悬浮洞）。
        """
        votes = 0
        for axis in range(3):
            lo = p.copy()
            hi = p.copy()
            hi[axis] = self.bmax[axis] + 1e-9
            direc = np.zeros(3)
            direc[axis] = 1.0
            ts: list[float] = []
            for t in self.candidate_ids(lo, hi):
                h = _ray_tri(p, direc, self.tri_pts[t])
                if h is not None:
                    ts.append(h)
            if not ts:
                continue
            ts.sort()
            tol_t = 1e-9 * (self.bmax[axis] - self.bmin[axis] + 1.0)
            uniq = 1
            for a, b in zip(ts, ts[1:]):
                if b - a > tol_t:
                    uniq += 1
            if uniq % 2 == 1:
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
                              k: int = 12) -> tuple[np.ndarray, float, int]:
        """最近面点（质心粗筛 + 精确三角形投影）→ (q, dist, tri_id)。"""
        centroids = self.tri_pts.mean(axis=1)
        idx = np.argsort(np.sum((centroids - p) ** 2, axis=1))[:k]
        best_q = p.copy()
        best_d = float("inf")
        best_t = -1
        for t in idx:
            q, d2 = _nearest_on_tri(p, self.tri_pts[t])
            if d2 < best_d:
                best_d = d2
                best_q = q
                best_t = int(t)
        return best_q, math.sqrt(best_d), best_t


# ────────────────────────────────────────────────────────────────────────────
# 八叉树
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class _OctNode:
    box_min: np.ndarray
    size: float
    depth: int
    children: Optional[list["_OctNode"]] = None
    leaf_id: int = -1                  # 前序叶子序号（_walk_nodes 填充）

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


# ────────────────────────────────────────────────────────────────────────────
# 面邻 2:1 平衡（相邻叶子深度差 ≤ 1）
# ────────────────────────────────────────────────────────────────────────────

def _collect_leaves(node: _OctNode, out: deque) -> None:
    if node.children is None:
        out.append(node)
        return
    for c in node.children:
        _collect_leaves(c, out)


def _collect_overlapping(node: _OctNode, qmin: np.ndarray, qmax: np.ndarray,
                         eps: float, out: list[_OctNode]) -> None:
    """收集与查询盒真正重叠（非仅相接）的叶子。"""
    lo = node.box_min
    hi = node.box_max
    if (np.any(qmax <= lo + eps) or np.any(qmin >= hi - eps)):
        return
    if node.children is None:
        out.append(node)
        return
    for c in node.children:
        _collect_overlapping(c, qmin, qmax, eps, out)


def _face_neighbor_leaves(root: _OctNode, leaf: _OctNode,
                          axis: int, sign: int, eps: float
                          ) -> list[_OctNode]:
    """leaf 沿 (axis, sign) 方向的整面邻居叶子（查询盒 = leaf 盒平移）。"""
    size = leaf.size
    qmin = leaf.box_min.copy()
    qmax = leaf.box_max.copy()
    if sign > 0:
        qmin[axis] += size
        qmax[axis] += size
    else:
        qmin[axis] -= size
        qmax[axis] -= size
    out: list[_OctNode] = []
    _collect_overlapping(root, qmin, qmax, eps, out)
    return out


def _balance_tree(root: _OctNode, max_depth: int, cap: int,
                  counter: list[int]) -> None:
    """面邻 2:1 平衡：任意叶子的面邻居深度差 ≤ 1（BFS 传播）。

    由细侧驱动：叶子 L 的面邻居深度 < L.depth - 1 时分裂该邻居，L 重新
    入队直到所有面邻居满足约束；新叶子也入队（可能触发新的违反）。
    受 max_depth / cap 截断处允许局部违反——pairing 装配对任意深度差
    都共形（粗面按邻叶贴合面分裂），平衡仅是过渡质量优化。
    """
    eps = 1e-9 * float(root.size)
    queue: deque = deque()
    _collect_leaves(root, queue)
    while queue:
        leaf = queue.popleft()
        if leaf.children is not None:
            continue
        violated = False
        for axis in range(3):
            for sign in (-1, 1):
                for nb in _face_neighbor_leaves(root, leaf, axis, sign, eps):
                    if (nb.children is None
                            and nb.depth < leaf.depth - 1
                            and nb.depth < max_depth
                            and counter[0] < cap):
                        nb.split()
                        counter[0] += 7
                        queue.extend(nb.children)
                        violated = True
        if violated:
            queue.append(leaf)


def _walk_nodes(node: _OctNode, refinement: list[int],
                leaves: list[tuple[np.ndarray, np.ndarray, int]],
                nodes: list[_OctNode]) -> None:
    if node.children is None:
        node.leaf_id = len(leaves)
        refinement.append(0)
        leaves.append((node.box_min.copy(), node.box_max.copy(), node.depth))
        nodes.append(node)
        return
    refinement.append(1)
    for c in node.children:
        _walk_nodes(c, refinement, leaves, nodes)


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
    if params.balance_2to1:
        _balance_tree(root, params.max_depth, params.max_cells, counter)
    return root_min, root_max, index, root


def build_octree(points: np.ndarray, tris: np.ndarray,
                 params: Optional[VoxelMeshParams] = None
                 ) -> tuple[np.ndarray, np.ndarray, np.ndarray,
                            list[tuple[np.ndarray, np.ndarray, int]]]:
    """仅构建八叉树（不生成体单元），返回 (root_min, root_max, refinement,
    叶子列表 [(min, max, depth)]），可直接交给 ``oct.write_oct``。"""
    params = params or VoxelMeshParams()
    root_min, root_max, _index, root = _build_octree(points, tris, params)
    refinement: list[int] = []
    leaves: list[tuple[np.ndarray, np.ndarray, int]] = []
    nodes: list[_OctNode] = []
    _walk_nodes(root, refinement, leaves, nodes)
    return (root_min, root_max,
            np.asarray(refinement, dtype=np.uint8), leaves)


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
            q, d, _t = index.nearest_surface_point(p)
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
               params: Optional[VoxelMeshParams] = None, *,
               tri_region: Optional[np.ndarray] = None,
               region_names: Optional[list[str]] = None
               ) -> VoxelMeshResult:
    """从三角面片构建 voxel/hex-dominant 网格（含 pairing 面装配）。

    ``tri_region``：(n_tris,) 输入三角形 → 表面区域 id（MDL frid 语义）；
    传入时边界面按「面质心最近输入三角形」映射区域（result.face_region），
    写 GPH 时输出 LS_SurfaceRegions。``region_names``：区域 id → 名。
    """
    params = params or VoxelMeshParams()
    root_min, root_max, index, root = _build_octree(points, tris, params)
    refinement: list[int] = []
    leaves: list[tuple[np.ndarray, np.ndarray, int]] = []
    leaf_nodes: list[_OctNode] = []
    _walk_nodes(root, refinement, leaves, leaf_nodes)
    leaf_boxes = np.asarray([np.stack([lo, hi]) for lo, hi, _ in leaves])
    leaf_depths = np.asarray([d for _, _, d in leaves], dtype=np.int64)

    inside_mask = np.zeros(len(leaves), dtype=bool)
    cut_mask = np.zeros(len(leaves), dtype=bool)
    cells: list[np.ndarray] = []
    cell_kind: list[int] = []
    hull_faces: list[list[np.ndarray]] = []
    cell_leaf: list[int] = []             # cell → leaf 序号
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
        cell_leaf.append(li)
        if kind == 1:
            hull_faces.append(hull)
        else:
            hull_faces.append([])

    # pairing：邻叶贴合面装配（hex 全共形；poly 三角面不与 hex 配对）
    leaf_cell = np.full(len(leaf_nodes), -1, dtype=np.int64)
    for ci, li in enumerate(cell_leaf):
        leaf_cell[li] = ci
    faces, f_owner, f_neigh = _assemble_paired_faces(
        root, leaf_nodes, np.asarray(cell_leaf, dtype=np.int64),
        leaf_cell, cells,
        np.asarray(cell_kind, dtype=np.int64), hull_faces,
        global_verts, _register)

    vertices = np.asarray(global_verts, dtype=float).reshape(-1, 3)
    face_region = _map_surface_regions(
        faces, f_owner, f_neigh, vertices, index,
        np.asarray(cell_leaf, dtype=np.int64), leaf_nodes,
        tri_region)
    names: list[str] = []
    if tri_region is not None:
        tri_region = np.asarray(tri_region, dtype=np.int64).reshape(-1)
        n_reg = int(tri_region.max()) + 1 if tri_region.size else 0
        given = list(region_names or [])
        names = [given[i] if i < len(given) else f"surface_{i}"
                 for i in range(n_reg)]
    result = VoxelMeshResult(
        root_min=root_min, root_max=root_max,
        refinement=np.asarray(refinement, dtype=np.uint8),
        leaf_boxes=leaf_boxes, leaf_depths=leaf_depths,
        inside_mask=inside_mask, cut_mask=cut_mask,
        cells=cells,
        cell_kind=np.asarray(cell_kind, dtype=np.int64),
        hull_faces=hull_faces,
        vertices=vertices,
        cell_leaf=np.asarray(cell_leaf, dtype=np.int64),
        faces=faces, face_owner=f_owner, face_neigh=f_neigh,
        face_region=face_region, region_names=names)
    return result


# ────────────────────────────────────────────────────────────────────────────
# 面装配 + 写 GPH / OCT
# ────────────────────────────────────────────────────────────────────────────

def _map_surface_regions(faces: list[list[int]], f_owner: np.ndarray,
                         f_neigh: np.ndarray, vertices: np.ndarray,
                         index: _TriIndex, cell_leaf: np.ndarray,
                         leaf_nodes: list[_OctNode],
                         tri_region: Optional[np.ndarray]) -> np.ndarray:
    """边界面 → 输入表面区域 id（face_region，-1 = 未分配）。

    映射规则（frid 传参 → LS_SurfaceRegions）：内部面（neigh ≥ 0）
    → -1；边界面取「面质心最近输入三角形」的区域，距离阈值
    2√3·owner 叶尺寸——粗糙阶梯面质心距表面 ≤ ~对角叶尺寸（含
    rough hex 切割单元延伸到根盒的近似面），远离表面（异常残留）
    不归属任何区域。内部单元不可能触及根盒（根盒 = bbox 外扩
    margin），故全部边界近似贴体。
    """
    if tri_region is None or not faces:
        return np.empty(0, dtype=np.int64)
    tri_region = np.asarray(tri_region, dtype=np.int64).reshape(-1)
    if tri_region.size != len(index.tris):
        raise ValueError(
            f"tri_region size {tri_region.size} != n_tris {len(index.tris)}")
    out = np.full(len(faces), -1, dtype=np.int64)
    for fi, fids in enumerate(faces):
        if f_neigh[fi] >= 0:
            continue
        centroid = vertices[np.asarray(fids, dtype=np.int64)].mean(axis=0)
        _q, dist, t = index.nearest_surface_point(centroid)
        if t < 0:
            continue
        li = int(cell_leaf[int(f_owner[fi])])
        if dist <= 2.0 * math.sqrt(3.0) * float(leaf_nodes[li].size):
            out[fi] = int(tri_region[t])
    return out

def _assemble_paired_faces(root: _OctNode, leaf_nodes: list[_OctNode],
                           cell_leaf: np.ndarray, leaf_cell: np.ndarray,
                           cells: list[np.ndarray],
                           cell_kind: np.ndarray,
                           hull_faces: list[list[np.ndarray]],
                           global_verts: list[np.ndarray], register
                           ) -> tuple[list[list[int]], np.ndarray,
                                      np.ndarray]:
    """邻叶贴合面装配（pairing，hex 全共形）。

    规则：对每个 hex 单元的叶 L 的 6 个面方向，查询盒 q（= L 盒沿
    (axis, sign) 平移）内的重叠叶子，只取**交集盒真正接触 L 面**的
    贴面层叶（q 是 3D 盒，覆盖它的叶在过渡带会分层，第二层叶不与
    L 共享面，须跳过）：

    - 无贴面叶（计算域边界）→ 生成 L 自己的整面（neigh = -1）；
    - 贴面叶 n → 生成「q ∩ n 交集盒」朝 L 的贴合面。两侧（粗/细）
      视角算出的交集盒相同 → 顶点集相同 → frozenset 去重后天然配对：
      粗侧把整面分裂为子面（2:1 时 1:4），细侧生成自己的整面，对
      任意深度差都恰好覆盖一次（平衡仅为质量优化）；
    - 贴面叶是 outside 叶（无单元）或 cut polyhedron → 该贴合面为
      边界面（neigh = -1；poly 的 hull 三角面另行生成，不与 hex
      配对，MVP 接受局部非共形——rough_poly=True 时不存在 poly）。
    """
    face_map: dict[frozenset, list] = {}
    centers: list[np.ndarray] = []
    for ids in cells:
        pts = np.asarray([global_verts[int(i)] for i in ids], dtype=float)
        centers.append(pts.mean(axis=0))
    eps = 1e-9 * float(root.size)

    def _emit(fids: list[int], owner: int, neigh: int) -> None:
        key = frozenset(fids)
        rec = face_map.get(key)
        if rec is None:
            face_map[key] = [owner, neigh, list(fids)]
        elif rec[1] == -1 and rec[0] != owner:
            rec[1] = owner

    for ci, ids in enumerate(cells):
        if cell_kind[ci] != 0:
            continue
        leaf = leaf_nodes[int(cell_leaf[ci])]
        for d, (axis, sign) in enumerate(_FACE_DIRS):
            size = leaf.size
            qmin = leaf.box_min.copy()
            qmax = leaf.box_max.copy()
            if sign > 0:
                qmin[axis] += size
                qmax[axis] += size
            else:
                qmin[axis] -= size
                qmax[axis] -= size
            overlap: list[_OctNode] = []
            _collect_overlapping(root, qmin, qmax, eps, overlap)
            nbs: list[_OctNode] = []
            for nb in overlap:
                # 贴面层过滤：交集盒必须在 L 的面上（跳过悬浮叶）
                if sign > 0:
                    if max(qmin[axis], nb.box_min[axis]) > qmin[axis] + eps:
                        continue
                else:
                    if min(qmax[axis], nb.box_max[axis]) < qmax[axis] - eps:
                        continue
                nbs.append(nb)
            if not nbs:
                # 计算域边界：整面（顶点已注册为 cell 角点）
                _emit([int(v) for v in ids[HEX_FACES[d]]], ci, -1)
                continue
            nd = _FACE_DIRS.index((axis, -sign))
            for nb in nbs:
                isect_min = np.maximum(qmin, nb.box_min)
                isect_max = np.minimum(qmax, nb.box_max)
                corner_pts = (isect_min
                              + HEX_CORNERS[HEX_FACES[nd]]
                              * (isect_max - isect_min))
                gids = [int(g) for g in register(corner_pts)]
                nc = int(leaf_cell[nb.leaf_id])
                neigh = nc if (nc >= 0 and cell_kind[nc] == 0) else -1
                _emit(gids, ci, neigh)
    # cut polyhedron：hull 三角面（poly-poly 顶点集相同才配对）
    for ci, ids in enumerate(cells):
        if cell_kind[ci] != 1:
            continue
        for f in hull_faces[ci]:
            _emit([int(v) for v in ids[f]], ci, -1)

    faces_out: list[list[int]] = []
    owner_out: list[int] = []
    neigh_out: list[int] = []
    vertices = np.asarray(global_verts, dtype=float).reshape(-1, 3)
    for rec in face_map.values():
        owner, neigh, fids = rec
        arr = np.asarray(fids, dtype=np.int64)
        arr = _orient_face_outward(arr, centers[owner], vertices)
        faces_out.append([int(v) for v in arr])
        owner_out.append(owner)
        neigh_out.append(neigh)
    return (faces_out,
            np.asarray(owner_out, dtype=np.int32),
            np.asarray(neigh_out, dtype=np.int32))


def assemble_faces(result: VoxelMeshResult
                   ) -> tuple[list[list[int]], np.ndarray, np.ndarray]:
    """返回 (faces, owner, neigh)；优先使用 build_mesh 内的 pairing
    装配缓存（邻叶贴合面，hex 全共形），否则退回整面枚举去重。"""
    if result.faces is not None:
        return (result.faces,
                np.asarray(result.face_owner, dtype=np.int32),
                np.asarray(result.face_neigh, dtype=np.int32))
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
    """写 ``.oct`` + ``.gph``（含 LS_SurfaceRegions），返回路径对。"""
    import gphstats
    import oct

    out_prefix = Path(out_prefix)
    oct_path = out_prefix.with_suffix(".oct")
    gph_path = out_prefix.with_suffix(".gph")
    oct.write_oct(oct_path, result.root_min, result.root_max,
                  refinement=result.refinement, date=date)
    faces, owner, neigh = assemble_faces(result)
    regions: list[tuple[str, np.ndarray]] = []
    if result.face_region.size == len(faces):
        for ri in np.unique(result.face_region):
            ri = int(ri)
            if ri < 0:
                continue
            ids = np.flatnonzero(result.face_region == ri)
            if not ids.size:
                continue
            name = (result.region_names[ri]
                    if ri < len(result.region_names) else f"surface_{ri}")
            regions.append((name, ids.astype(np.int64)))
    gphstats.write_gph_volume(
        gph_path, result.vertices, faces, owner, neigh,
        app="pphdecoding", date=date,
        surface_regions=regions or None)
    return oct_path, gph_path


def build_from_surface(points: np.ndarray, tris: np.ndarray,
                       out_prefix: str | Path,
                       params: Optional[VoxelMeshParams] = None, *,
                       tri_region: Optional[np.ndarray] = None,
                       region_names: Optional[list[str]] = None
                       ) -> tuple[VoxelMeshResult, Path, Path]:
    """便捷入口：三角面 → (result, oct_path, gph_path)。"""
    result = build_mesh(points, tris, params,
                        tri_region=tri_region, region_names=region_names)
    oct_path, gph_path = write_outputs(result, out_prefix)
    return result, oct_path, gph_path


def build_from_mdl(mdl_path: str | Path, out_prefix: str | Path,
                   params: Optional[VoxelMeshParams] = None
                   ) -> tuple[VoxelMeshResult, Path, Path]:
    points, tris, tri_region, region_names = _surface_from_mdl_ex(mdl_path)
    return build_from_surface(points, tris, out_prefix, params,
                              tri_region=tri_region,
                              region_names=region_names)


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
    ap.add_argument("--no-balance", action="store_true",
                    help="关闭面邻 2:1 平衡")
    args = ap.parse_args(argv)
    params = VoxelMeshParams(
        initial_depth=args.initial_depth, max_depth=args.max_depth,
        max_cells=args.max_cells, rough_poly=args.rough,
        fit_to_surface=args.fit, balance_2to1=not args.no_balance)
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
    # P5-4：质量度量统计接入 quality.py（from_voxel 装配缓存优先）
    try:
        import quality
        rep = quality.from_voxel(result)
        print()
        print(rep.format_report("Mesh quality"))
    except Exception as e:  # noqa: BLE001 —— 质量报告失败不阻断网格输出
        print(f"[quality report unavailable: {e}]")
    print(f"oct -> {oct_p}")
    print(f"gph -> {gph_p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
