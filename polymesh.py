#!/usr/bin/env python3
"""自研原生多面体（polyhedral）mesher MVP —— Delaunay/Voronoi 对偶 + 表面裁剪。

参照：

- DEV_PLAN.md §0.5：cfMesh ``pMesh`` 路线（tet 模板 → dual → 贴体投影）
  与 Voronoi 系（clipped / VoroCrust）并读；本实现取两者的共同数学内核：
  **点集 Voronoi 胞元 = Delaunay 四面体化的对偶**；
- cfMesh《An Inside-Out Method For Arbitrary Polyhedra》(2014)：八叉树模板 →
  tet → dual polyhedra；
- VoroCrust（ACM TOG）：conforming Voronoi、保尖角（本 MVP 未实现无裁剪保证）；
- NASA LAVA Voronoi mesher（AIAA 2024）：seed → Lloyd 平滑 → cell clipping
  的工业流程（本 MVP 实现 seed + 裁剪，未做 Lloyd/平滑）。

流水线：MDL/STL 面片 → 根盒 + 内部格点（射线法过滤 inside）→ 表面点 +
内部点联合 Delaunay/Voronoi → 内部点的有界 Voronoi 胞元 →
对与表面相交的胞元按三角形平面裁剪（convex clip）→ ConvexHull 面 →
owner/neigh 装配 → 写 ``.gph``（CRDL-FLD，可被 gphstats/查看器读回）。
"""

from __future__ import annotations

import argparse
import math
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from voxmesh import (
    _TriIndex,
    _orient_face_outward,
    surface_from_mdl,
    surface_from_stl,
)


@dataclass
class PolyMeshParams:
    """多面体 mesher 参数。"""

    divisions: int = 12            # 根盒内部格点每轴划分数（seed 密度）
    surface_stride: int = 8        # 表面点抽样步长（1=全部，越大越稀疏）
    clip_to_surface: bool = True   # 对表面相交胞元做三角形平面裁剪
    max_clip_planes: int = 64      # 每胞元最多裁剪平面数
    max_cells: int = 200_000       # 单元上限
    min_cell_volume: float = 1e-12 # 最小单元体积
    margin_ratio: float = 0.02     # 根盒外扩比例


@dataclass
class PolyMeshResult:
    cells: list[np.ndarray] = field(default_factory=list)
    """每个单元：全局顶点索引（凸包有序）。"""
    cell_faces: list[list[np.ndarray]] = field(default_factory=list)
    """每个单元的面（全局顶点索引列表；ConvexHull 三角面）。"""
    vertices: np.ndarray = field(default_factory=lambda: np.empty((0, 3)))
    cell_centers: np.ndarray = field(default_factory=lambda: np.empty((0, 3)))
    cell_volumes: np.ndarray = field(default_factory=lambda: np.empty(0))
    n_clipped: int = 0
    n_surface_seeds: int = 0
    n_interior_seeds: int = 0

    def stats(self) -> dict:
        npe = np.asarray([len(f) for fs in self.cell_faces for f in fs],
                         dtype=np.int64) if self.cell_faces else np.empty(0)
        vols = self.cell_volumes
        return {
            "n_cells": len(self.cells),
            "n_faces": int(npe.size),
            "n_vertices": int(len(self.vertices)),
            "n_surface_seeds": self.n_surface_seeds,
            "n_interior_seeds": self.n_interior_seeds,
            "n_clipped": self.n_clipped,
            "avg_faces_per_cell": float(npe.size / len(self.cells))
            if self.cells else 0.0,
            "min_npe": int(npe.min()) if npe.size else 0,
            "max_npe": int(npe.max()) if npe.size else 0,
            "min_volume": float(vols.min()) if vols.size else 0.0,
            "mean_volume": float(vols.mean()) if vols.size else 0.0,
            "max_volume": float(vols.max()) if vols.size else 0.0,
        }


def _clip_poly_by_plane(pts: np.ndarray, normal: np.ndarray,
                        p0: np.ndarray, tol: float = 1e-12) -> np.ndarray:
    """Sutherland–Hodgman：保留 ``normal·(x-p0) <= tol`` 一侧。"""
    if len(pts) < 3:
        return pts
    out: list[np.ndarray] = []
    m = len(pts)
    for i in range(m):
        a = pts[i]
        b = pts[(i + 1) % m]
        da = float(np.dot(normal, a - p0))
        db = float(np.dot(normal, b - p0))
        if da <= tol:
            out.append(a)
        if (da > tol) != (db > tol):
            t = da / (da - db)
            out.append(a + t * (b - a))
    if not out:
        return np.empty((0, 3))
    scale = float(np.max(np.linalg.norm(pts, axis=1))) or 1.0
    eps = 1e-10 * scale
    cleaned: list[np.ndarray] = []
    for p in out:
        if not cleaned or float(np.linalg.norm(p - cleaned[-1])) > eps:
            cleaned.append(p)
    if len(cleaned) > 1 and \
            float(np.linalg.norm(cleaned[-1] - cleaned[0])) <= eps:
        cleaned.pop()
    return np.asarray(cleaned, dtype=float).reshape(-1, 3)


class _Poly:
    """凸多面体：顶点表 + 面表（顶点索引，按序闭合）。"""

    def __init__(self, verts: list[np.ndarray],
                 faces: list[list[int]]):
        self.verts = list(verts)
        self.faces = [list(f) for f in faces]

    def clip(self, normal: np.ndarray, p0: np.ndarray,
             tol: float = 1e-12) -> Optional["_Poly"]:
        """用半空间 ``normal·(x-p0) <= tol`` 裁剪（Sutherland–Hodgman 3D）。"""
        pos_to_id: dict[tuple, int] = {}
        for i, p in enumerate(self.verts):
            pos_to_id[(round(float(p[0]), 10), round(float(p[1]), 10),
                       round(float(p[2]), 10))] = i
        new_verts: list[np.ndarray] = list(self.verts)
        new_faces: list[list[int]] = []
        cap_ids: list[int] = []
        seen_faces: set[frozenset] = set()

        def _add_point(q: np.ndarray) -> int:
            key = (round(float(q[0]), 10), round(float(q[1]), 10),
                   round(float(q[2]), 10))
            gid = pos_to_id.get(key)
            if gid is None:
                gid = len(new_verts)
                pos_to_id[key] = gid
                new_verts.append(q)
            return gid

        for face in self.faces:
            m = len(face)
            out: list[int] = []
            for i in range(m):
                a_id = face[i]
                b_id = face[(i + 1) % m]
                a = self.verts[a_id]
                b = self.verts[b_id]
                da = float(np.dot(normal, a - p0))
                db = float(np.dot(normal, b - p0))
                if da <= tol:
                    out.append(a_id)
                if (da > tol) != (db > tol):
                    t = da / (da - db)
                    q = a + t * (b - a)
                    qid = _add_point(q)
                    out.append(qid)
                    cap_ids.append(qid)
            uniq = list(dict.fromkeys(out))
            if len(uniq) >= 3:
                fkey = frozenset(uniq)
                if fkey not in seen_faces:
                    seen_faces.add(fkey)
                    new_faces.append(uniq)
        if len(cap_ids) >= 3:
            cap_ids = list(dict.fromkeys(cap_ids))
            cap_pts = np.asarray([new_verts[i] for i in cap_ids])
            c = cap_pts.mean(axis=0)
            normal = normal / (np.linalg.norm(normal) + 1e-30)
            u = np.array([1.0, 0.0, 0.0])
            if abs(float(np.dot(u, normal))) > 0.9:
                u = np.array([0.0, 1.0, 0.0])
            v = np.cross(normal, u)
            u = np.cross(v, normal)
            u /= (np.linalg.norm(u) + 1e-30)
            v /= (np.linalg.norm(v) + 1e-30)
            ordered = sorted(
                cap_ids,
                key=lambda i: math.atan2(
                    float(np.dot(v, new_verts[i] - c)),
                    float(np.dot(u, new_verts[i] - c))))
            if len(ordered) >= 3:
                fkey = frozenset(ordered)
                if fkey not in seen_faces:
                    seen_faces.add(fkey)
                    new_faces.append(ordered)
        if len(new_faces) < 4 or len(new_verts) < 4:
            return None
        # 压实：丢弃不再被任何面引用的顶点，避免体积/几何误判
        used = sorted({v for f in new_faces for v in f})
        remap = {old: new for new, old in enumerate(used)}
        compact_verts = [new_verts[i] for i in used]
        compact_faces = [[remap[v] for v in f] for f in new_faces]
        return _Poly(compact_verts, compact_faces)


def _box_poly(bmin: np.ndarray, bmax: np.ndarray) -> _Poly:
    c = np.array([
        [x, y, z]
        for x in (bmin[0], bmax[0])
        for y in (bmin[1], bmax[1])
        for z in (bmin[2], bmax[2])
    ], dtype=float)
    faces = [
        [0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1],
        [2, 3, 7, 6], [1, 5, 6, 2], [0, 2, 6, 4],
    ]
    return _Poly(list(c), faces)


def _cell_from_neighbors(seed_id: int, pts: np.ndarray,
                         neigh_indices: np.ndarray, neigh_ptrs: np.ndarray,
                         root_box: np.ndarray) -> Optional[_Poly]:
    """由 Delaunay 邻居的垂直平分半空间裁剪根盒，构造有界 Voronoi 胞元。"""
    poly = _box_poly(root_box[0], root_box[7])
    p = pts[seed_id]
    start = int(neigh_ptrs[seed_id])
    end = int(neigh_ptrs[seed_id + 1])
    for j in range(start, end):
        q = pts[int(neigh_indices[j])]
        mid = (p + q) * 0.5
        normal = q - p
        poly = poly.clip(normal, mid)
        if poly is None:
            return None
    return poly


def _clip_cell_by_surface(poly: _Poly, ref: np.ndarray,
                          index: _TriIndex, centroids: np.ndarray,
                          centroid_tree,
                          params: PolyMeshParams
                          ) -> tuple[Optional[_Poly], bool]:
    """按表面三角形平面裁剪，保留含 ``ref``（内部参考点）一侧。"""
    pts = np.asarray(poly.verts)
    centroid = ref.copy()
    clipped_any = False
    n_planes = 0
    lo = pts.min(axis=0)
    hi = pts.max(axis=0)
    candidates: set[int] = index.candidate_ids(lo, hi)
    if centroid_tree is not None:
        _, near = centroid_tree.query(centroid, k=24)
        near = np.atleast_1d(near)
        n_tri = len(index.tri_pts)
        candidates.update(int(t) for t in near if 0 <= int(t) < n_tri)
    for t in candidates:
        if n_planes >= params.max_clip_planes:
            break
        tri = index.tri_pts[t]
        normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        nlen = float(np.linalg.norm(normal))
        if nlen < 1e-14:
            continue
        normal = normal / nlen
        p0 = tri[0]
        if float(np.dot(normal, ref - p0)) > 0:
            normal = -normal
        sides = np.dot(pts - p0, normal)
        if not (sides.min() < -1e-12 and sides.max() > 1e-12):
            continue  # 平面不分离当前胞元顶点
        poly2 = poly.clip(normal, p0)
        if poly2 is None:
            return None, clipped_any
        clipped_any = True
        poly = poly2
        pts = np.asarray(poly.verts)
        n_planes += 1
    return poly, clipped_any


def _poly_volume(poly: _Poly, params: PolyMeshParams) -> Optional[float]:
    """凸多面体体积（ConvexHull；失败返回 None）。"""
    if len(poly.verts) < 4 or len(poly.faces) < 4:
        return None
    from scipy.spatial import ConvexHull
    try:
        hull = ConvexHull(np.asarray(poly.verts), qhull_options="QJ")
    except Exception:  # noqa: BLE001
        return None
    vol = float(hull.volume)
    if vol <= params.min_cell_volume:
        return None
    return vol


def build_mesh(points: np.ndarray, tris: np.ndarray,
               params: Optional[PolyMeshParams] = None) -> PolyMeshResult:
    """从三角面片构建原生多面体网格（Voronoi 对偶 + 表面裁剪）。"""
    params = params or PolyMeshParams()
    bmin = points.min(axis=0)
    bmax = points.max(axis=0)
    span = float((bmax - bmin).max())
    center = (bmin + bmax) * 0.5
    half = span * 0.5 * (1.0 + params.margin_ratio)
    root_min = center - half
    root_max = center + half
    index = _TriIndex(points, tris, root_min, root_max)

    # 1) 表面点抽样
    surf_ids = np.arange(0, len(points), max(1, int(params.surface_stride)))
    surf_pts = points[surf_ids]

    # 2) 内部格点（射线法过滤）
    n_div = int(params.divisions)
    axes = np.linspace(root_min, root_max, n_div + 1)
    gx, gy, gz = np.meshgrid(axes[:, 0], axes[:, 1], axes[:, 2],
                             indexing="ij")
    grid = np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()])
    inside = np.array([index.point_inside(p) for p in grid], dtype=bool)
    interior = grid[inside]
    if len(interior) == 0:
        raise ValueError("no interior lattice points; "
                         "check surface orientation/watertightness")
    if len(interior) + len(surf_pts) > params.max_cells * 4:
        raise ValueError("point set too large; increase surface_stride "
                         "or reduce divisions")

    # 3) 联合 Delaunay（Voronoi 对偶的邻居图）
    from scipy.spatial import Delaunay, cKDTree
    all_pts = np.vstack([surf_pts, interior])
    n_surf = len(surf_pts)
    tri = Delaunay(all_pts, qhull_options="Qbb Qc Qz Qx")
    neigh_ptrs, neigh_indices = tri.vertex_neighbor_vertices
    interior_tree = cKDTree(interior)
    root_box = np.array([
        [x, y, z]
        for x in (root_min[0], root_max[0])
        for y in (root_min[1], root_max[1])
        for z in (root_min[2], root_max[2])
    ], dtype=float)
    tri_centroids = index.tri_pts.mean(axis=1)
    centroid_tree = cKDTree(tri_centroids)

    # 4) 内部点 → 有界 Voronoi 胞元 → 表面裁剪 → 凸包面
    lookup: dict[tuple, int] = {}
    global_verts: list[np.ndarray] = []
    cells: list[np.ndarray] = []
    cell_faces: list[list[np.ndarray]] = []
    cell_centers: list[np.ndarray] = []
    cell_vols: list[float] = []
    n_clipped = 0
    for k in range(len(all_pts)):
        if len(cells) >= params.max_cells:
            break
        poly = _cell_from_neighbors(k, all_pts, neigh_indices, neigh_ptrs,
                                    root_box)
        if poly is None:
            continue
        seed = all_pts[k]
        is_surface = k < n_surf
        clipped = False
        if params.clip_to_surface and is_surface:
            # 表面种子的未裁剪胞元大部分在域外；以最近内部种子为内部参考
            _, nb = interior_tree.query(seed, k=1)
            ref = interior[int(nb)]
            poly, any_clip = _clip_cell_by_surface(
                poly, ref, index, tri_centroids, centroid_tree, params)
            if poly is None:
                continue
            clipped = any_clip
        volume = _poly_volume(poly, params)
        if volume is None:
            continue
        verts_local = np.asarray(poly.verts)
        ids = np.empty(len(verts_local), dtype=np.int64)
        for i, p in enumerate(verts_local):
            key = (round(float(p[0]), 10), round(float(p[1]), 10),
                   round(float(p[2]), 10))
            gid = lookup.get(key)
            if gid is None:
                gid = len(global_verts)
                lookup[key] = gid
                global_verts.append(p)
            ids[i] = gid
        face_ids = [ids[f] for f in poly.faces]
        cells.append(ids)
        cell_faces.append(face_ids)
        cell_centers.append(verts_local.mean(axis=0))
        cell_vols.append(volume)
        if clipped:
            n_clipped += 1

    vertices = np.asarray(global_verts, dtype=float).reshape(-1, 3)
    return PolyMeshResult(
        cells=cells, cell_faces=cell_faces, vertices=vertices,
        cell_centers=np.asarray(cell_centers, dtype=float).reshape(-1, 3),
        cell_volumes=np.asarray(cell_vols, dtype=float),
        n_clipped=n_clipped,
        n_surface_seeds=n_surf,
        n_interior_seeds=len(interior))


def assemble_faces(result: PolyMeshResult
                   ) -> tuple[list[list[int]], np.ndarray, np.ndarray]:
    """全部单元面去重 + owner/neigh + 外向法向。"""
    face_map: dict[frozenset, list] = {}
    for cid, faces in enumerate(result.cell_faces):
        for fids in faces:
            key = frozenset(int(v) for v in fids)
            rec = face_map.get(key)
            if rec is None:
                face_map[key] = [cid, -1, list(fids)]
            elif rec[1] == -1 and rec[0] != cid:
                rec[1] = cid
    # 保证每个单元至少拥有一个面：仅作 neigh 的单元翻转一条共享面
    owners = {rec[0] for rec in face_map.values()}
    for cid in range(len(result.cells)):
        if cid in owners:
            continue
        for rec in face_map.values():
            if rec[1] == cid:
                rec[0], rec[1] = rec[1], rec[0]
                owners.add(cid)
                break
    faces_out: list[list[int]] = []
    owner_out: list[int] = []
    neigh_out: list[int] = []
    for rec in face_map.values():
        owner, neigh, fids = rec
        arr = np.asarray(fids, dtype=np.int64)
        arr = _orient_face_outward(arr, result.cell_centers[owner],
                                   result.vertices)
        faces_out.append([int(v) for v in arr])
        owner_out.append(owner)
        neigh_out.append(neigh)
    return (faces_out,
            np.asarray(owner_out, dtype=np.int32),
            np.asarray(neigh_out, dtype=np.int32))


def write_gph(result: PolyMeshResult, gph_path: str | Path,
              *, date: int = 20260813) -> Path:
    import gphstats
    faces, owner, neigh = assemble_faces(result)
    return gphstats.write_gph_volume(
        gph_path, result.vertices, faces, owner, neigh,
        app="pphdecoding", date=date)


def build_from_surface(points: np.ndarray, tris: np.ndarray,
                       out_prefix: str | Path,
                       params: Optional[PolyMeshParams] = None
                       ) -> tuple[PolyMeshResult, Path]:
    result = build_mesh(points, tris, params)
    gph = write_gph(result, Path(out_prefix).with_suffix(".gph"))
    return result, gph


def build_from_mdl(mdl_path: str | Path, out_prefix: str | Path,
                   params: Optional[PolyMeshParams] = None
                   ) -> tuple[PolyMeshResult, Path]:
    points, tris = surface_from_mdl(mdl_path)
    return build_from_surface(points, tris, out_prefix, params)


def build_from_stl(stl_path: str | Path, out_prefix: str | Path,
                   params: Optional[PolyMeshParams] = None
                   ) -> tuple[PolyMeshResult, Path]:
    points, tris = surface_from_stl(stl_path)
    return build_from_surface(points, tris, out_prefix, params)


def _extract_mdl_from_pph(pph_path: str | Path) -> Path:
    import pph_parser
    arch = pph_parser.PphArchive.open(str(pph_path))
    members = arch.by_role(pph_parser.ROLE_MDL_PART)
    if not members:
        raise ValueError(f"{pph_path}: no MDL part member")
    tmp = Path(tempfile.mkdtemp(prefix="polymesh_"))
    p = tmp / members[0].name.replace("\\", "_").replace("/", "_")
    p.write_bytes(arch.read_member(members[0].name))
    return p


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="native polyhedral mesher (Voronoi dual + surface clip)")
    ap.add_argument("input", help="*.mdl / *.stl / *.pph")
    ap.add_argument("-o", "--out", required=True, help="输出前缀（.gph）")
    ap.add_argument("--divisions", type=int, default=12)
    ap.add_argument("--surface-stride", type=int, default=8)
    ap.add_argument("--max-cells", type=int, default=200_000)
    ap.add_argument("--no-clip", action="store_true",
                    help="不对表面相交胞元做裁剪")
    args = ap.parse_args(argv)
    params = PolyMeshParams(
        divisions=args.divisions, surface_stride=args.surface_stride,
        max_cells=args.max_cells, clip_to_surface=not args.no_clip)
    inp = str(args.input)
    suffix = Path(inp).suffix.lower()
    if suffix == ".mdl":
        result, gph = build_from_mdl(inp, args.out, params)
    elif suffix == ".stl":
        result, gph = build_from_stl(inp, args.out, params)
    elif suffix == ".pph":
        mdl = _extract_mdl_from_pph(inp)
        result, gph = build_from_mdl(mdl, args.out, params)
    else:
        ap.error(f"unsupported input: {inp}")
        return 2
    print(result.stats())
    print(f"gph -> {gph}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
