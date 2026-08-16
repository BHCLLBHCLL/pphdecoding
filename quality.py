#!/usr/bin/env python3
"""网格质量统计（非正交度 / 偏斜度 / 单元几何）—— scFLOWpre
``Element Quality Check`` 的本地实现（P2-3）。

指标定义（对齐 OpenFOAM checkMesh / Jasaak 论文口径，全部基于
面拓扑 owner/neigh + 散度定理，适用于任意凸多面体网格）：

* **非正交度 non-orthogonality**（内面）：单元中心连线 ``d = C_N - C_P``
  与面面积向量 ``S``（owner 外向，Newell）的夹角，
  ``θ = acos(|d·S| / (|d||S|))``，取 ``[0°, 90°]``。规则六面体/voxel
  网格恒为 0°。
* **边界面正交度**：``C_f - C_P`` 与面法向的夹角（切割单元贴面处
  容易偏斜，单独统计）。
* **偏斜度 skewness**（内面）：中心连线与面平面交点 ``P`` 偏离面
  重心的程度，``skew = |P - C_f| / |d|``，0 = 完美居中。
* **单元长宽比 aspect ratio**：中心到各面重心距离的 max/min。

体积 / 质心用散度定理精确计算（有向四面体分解，对闭合多面体精确），
非正交度 > 70° 与偏斜度 > 0.6 的面单独计数（checkMesh 风格阈值）。

入口：

- ``compute_quality(vertices, faces, owner, neigh)``：通用（faces 为
  顶点索引列表，neigh==-1 = 边界）；
- ``from_voxel(result)`` / ``from_poly(result)``：直接吃
  ``VoxelMeshResult`` / ``PolyMeshResult``；
- ``from_gph(path)``：读 GPH 文件（经 gphstats.parse_mesh）。

CLI：``python quality.py mesh.gph``
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

# checkMesh 风格报告阈值
NONORTHO_WARN = 70.0     # 非正交度警戒（deg）
NONORTHO_MAX = 90.0      # 上限
SKEW_WARN = 0.6          # 偏斜度警戒


# ────────────────────────────────────────────────────────────────────────────
# 面几何（Newell 面积向量 + 面积加权重心）与单元几何（散度定理）
# ────────────────────────────────────────────────────────────────────────────

def _faces_to_csr(faces) -> tuple[np.ndarray, np.ndarray]:
    """faces（顶点索引列表）→ CSR (conn, offsets)。"""
    npe = np.asarray([len(f) for f in faces], dtype=np.int64)
    offsets = np.empty(npe.size + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(npe, out=offsets[1:])
    conn = np.concatenate(
        [np.asarray(f, dtype=np.int64) for f in faces]) if faces \
        else np.empty(0, dtype=np.int64)
    return conn, offsets


def _fan_triangles(conn: np.ndarray, offsets: np.ndarray
                   ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """多边形扇形三角化（每面 (v0, vi, vi+1)）→ 三元组全局顶点索引。

    返回 (a, b, c, face_id)；face_id 与三角形一一对应（供
    ``np.add.reduceat`` 按面聚合）。
    """
    n_faces = offsets.size - 1
    npe = np.diff(offsets)
    n_tris_per_face = np.maximum(npe - 2, 0)
    face_id = np.repeat(np.arange(n_faces, dtype=np.int64), n_tris_per_face)
    if face_id.size == 0:
        e = np.empty(0, dtype=np.int64)
        return e, e, e, face_id
    # 每个三角形在面内的位置（0..n_tris-1）
    tri_total = int(n_tris_per_face.sum())
    idx = np.arange(tri_total, dtype=np.int64)
    # face 内第 k 个三角形：k = idx - (face 首三角形序号)
    first_tri = np.empty(n_faces + 1, dtype=np.int64)
    first_tri[0] = 0
    np.cumsum(n_tris_per_face, out=first_tri[1:])
    k = idx - first_tri[face_id]
    base = offsets[face_id]
    a = conn[base]
    b = conn[base + 1 + k]
    c = conn[base + 2 + k]
    return a, b, c, face_id


def face_geometry(vertices: np.ndarray, faces
                  ) -> tuple[np.ndarray, np.ndarray]:
    """全部面的 (面积向量 S（面序外向待定）, 面积加权重心 C_f)。

    ``faces`` 可为顶点索引列表或 CSR ``(conn, offsets)`` 元组。
    """
    if isinstance(faces, tuple):
        conn, offsets = faces
    else:
        conn, offsets = _faces_to_csr(faces)
    a, b, c, fid = _fan_triangles(conn, offsets)
    n_faces = offsets.size - 1
    va, vb, vc = vertices[a], vertices[b], vertices[c]
    # 三角形有向面积向量 = 0.5 (b-a)×(c-a)
    cross = np.cross(vb - va, vc - va)
    area = 0.5 * np.linalg.norm(cross, axis=1)
    tri_centroid = (va + vb + vc) / 3.0
    # 面聚合：S = Σ cross/2（Newell），C_f = Σ A·c / Σ A
    seg_start = np.flatnonzero(np.diff(fid, prepend=-1))
    with np.errstate(invalid="ignore", divide="ignore"):
        area_sum = np.add.reduceat(area, seg_start)
        S = 0.5 * np.add.reduceat(cross, seg_start)
        w_centroid = np.add.reduceat(area[:, None] * tri_centroid, seg_start)
        centroids = w_centroid / area_sum[:, None]
    degenerate = ~np.isfinite(centroids).all(axis=1) | (area_sum <= 0)
    if degenerate.any():
        # 退化面（零面积/坏连接）：重心退化为首顶点，指标侧按 NaN 过滤
        centroids[degenerate] = vertices[conn[offsets[:-1][degenerate]]]
    return S, centroids


def cell_geometry(vertices: np.ndarray, faces, owner: np.ndarray,
                  neigh: np.ndarray
                  ) -> tuple[np.ndarray, np.ndarray]:
    """散度定理计算每个单元的 (体积, 质心)。

    有向四面体 (0, a, b, c)：``V_i = det/6``，``∫x dV_i = det·(a+b+c)/24``；
    对 owner 面取 +，neigh 面取 −（GPH/内存约定：面外向 owner，
    ``neigh == -1`` 或 ``0xFFFFFFFF`` 为边界）。对闭合多面体精确。
    """
    if isinstance(faces, tuple):
        conn, offsets = faces
    else:
        conn, offsets = _faces_to_csr(faces)
    a, b, c, fid = _fan_triangles(conn, offsets)
    va, vb, vc = vertices[a], vertices[b], vertices[c]
    det = np.einsum("ij,ij->i", va, np.cross(vb, vc))   # a·(b×c)
    owner = np.asarray(owner, dtype=np.int64)
    neigh = np.asarray(neigh, dtype=np.int64)
    neigh = np.where(neigh > np.iinfo(np.int32).max, -1, neigh)
    n_cells = int(max(owner.max(), neigh.max() if neigh.size else -1)) + 1
    moment = det[:, None] * (va + vb + vc)               # ∝ ∫x dV

    tri_owner = owner[fid] if fid.size else np.empty(0, dtype=np.int64)
    tri_neigh = neigh[fid] if fid.size else np.empty(0, dtype=np.int64)
    nmask = tri_neigh >= 0

    def _acc(w):   # owner(+)/neigh(−) 有符号聚合
        return (np.bincount(tri_owner, weights=w, minlength=n_cells)
                - np.bincount(tri_neigh[nmask], weights=w[nmask],
                              minlength=n_cells))

    vol = _acc(det) / 6.0
    mom = _acc(moment[:, 0])
    mom2 = _acc(moment[:, 1])
    mom3 = _acc(moment[:, 2])
    centroid = np.column_stack([mom, mom2, mom3]) / (24.0 * vol)[:, None]
    bad = ~np.isfinite(centroid).all(axis=1) | (np.abs(vol) < 1e-300)
    centroid[bad] = 0.0
    return vol, centroid


# ────────────────────────────────────────────────────────────────────────────
# 质量指标
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class QualityReport:
    """面级 + 单元级质量指标与汇总。"""

    n_faces: int = 0
    n_internal: int = 0
    n_boundary: int = 0
    n_cells: int = 0
    # 每面指标（NaN = 不适用，如边界的 skewness）
    non_orthogonality: np.ndarray = field(
        default_factory=lambda: np.empty(0))       # deg，内面
    skewness: np.ndarray = field(
        default_factory=lambda: np.empty(0))       # 内面
    boundary_non_ortho: np.ndarray = field(
        default_factory=lambda: np.empty(0))       # deg，边界面
    # 每单元
    cell_volumes: np.ndarray = field(
        default_factory=lambda: np.empty(0))
    cell_aspect: np.ndarray = field(
        default_factory=lambda: np.empty(0))       # 中心-面重心距离 max/min
    n_negative_volume: int = 0

    # ── 汇总 ──
    def summary(self) -> dict:
        def _st(x):
            x = x[np.isfinite(x)]
            if not x.size:
                return {"min": 0.0, "mean": 0.0, "max": 0.0, "n": 0}
            return {"min": float(x.min()), "mean": float(x.mean()),
                    "max": float(x.max()), "n": int(x.size)}

        no = self.non_orthogonality
        sk = self.skewness
        bno = self.boundary_non_ortho
        return {
            "n_faces": self.n_faces,
            "n_internal_faces": self.n_internal,
            "n_boundary_faces": self.n_boundary,
            "n_cells": self.n_cells,
            "non_orthogonality": _st(no),
            "non_orthogonality_over_70": int(
                np.count_nonzero(np.isfinite(no) & (no > NONORTHO_WARN))),
            "boundary_non_ortho": _st(bno),
            "skewness": _st(sk),
            "skewness_over_0_6": int(
                np.count_nonzero(np.isfinite(sk) & (sk > SKEW_WARN))),
            "cell_volume": _st(self.cell_volumes),
            "negative_volume_cells": self.n_negative_volume,
            "cell_aspect": _st(self.cell_aspect),
        }

    def histogram(self, metric: str = "non_orthogonality",
                  edges: Optional[list[float]] = None
                  ) -> list[tuple[str, int]]:
        """按区间分箱 → [(标签, 数量)]。"""
        x = {"non_orthogonality": self.non_orthogonality,
             "skewness": self.skewness,
             "boundary_non_ortho": self.boundary_non_ortho,
             "cell_aspect": self.cell_aspect}.get(metric)
        if x is None or not x.size:
            return []
        x = x[np.isfinite(x)]
        if edges is None:
            edges = ([0, 10, 20, 30, 40, 50, 60, 70, 80, 90]
                     if "ortho" in metric else
                     [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
        counts, _ = np.histogram(x, bins=edges)
        out: list[tuple[str, int]] = []
        for i, cnt in enumerate(counts):
            lo, hi = edges[i], edges[i + 1]
            fmt = (f"{lo:.0f}–{hi:.0f}" if "ortho" in metric
                   else f"{lo:.1f}–{hi:.1f}")
            out.append((fmt + ("°" if "ortho" in metric else ""),
                        int(cnt)))
        over = int(np.count_nonzero(x >= edges[-1]))
        if over:
            out.append((f">={edges[-1]}" + ("°" if "ortho" in metric else ""),
                        over))
        return out

    def format_report(self, title: str = "Mesh quality") -> str:
        """checkMesh 风格文本报告。"""
        s = self.summary()

        def _line(name, st, unit, warn=None):
            txt = (f"  {name:<22} min {st['min']:10.4g}  "
                   f"mean {st['mean']:10.4g}  max {st['max']:10.4g} {unit}")
            return txt

        lines = [
            f"{title}",
            f"  cells: {s['n_cells']:,}  "
            f"faces: {s['n_faces']:,} "
            f"(internal {s['n_internal_faces']:,} / "
            f"boundary {s['n_boundary_faces']:,})",
            "",
            "Face non-orthogonality (internal):",
            _line("angle", s["non_orthogonality"], "deg"),
            (f"  faces > {NONORTHO_WARN:.0f}°: "
             f"{s['non_orthogonality_over_70']:,}"),
            "Face orthogonality (boundary):",
            _line("angle", s["boundary_non_ortho"], "deg"),
            "Face skewness (internal):",
            _line("skew", s["skewness"], ""),
            (f"  faces > {SKEW_WARN}: {s['skewness_over_0_6']:,}"),
            "Cells:",
            _line("volume", s["cell_volume"], "m³"),
            f"  negative-volume cells: {s['negative_volume_cells']:,}",
            _line("aspect ratio", s["cell_aspect"], ""),
        ]
        return "\n".join(lines)


def compute_quality(vertices: np.ndarray, faces, owner: np.ndarray,
                    neigh: np.ndarray, *,
                    cell_centers: Optional[np.ndarray] = None
                    ) -> QualityReport:
    """通用入口：vertices + faces（列表或 CSR）+ owner/neigh。

    ``neigh == -1`` 或 ``0xFFFFFFFF`` = 边界面；``cell_centers`` 可传入
    已有质心（如 PolyMeshResult.cell_centers），否则散度定理现算。
    """
    vertices = np.asarray(vertices, dtype=float)
    owner = np.asarray(owner, dtype=np.int64)
    neigh = np.asarray(neigh, dtype=np.int64).copy()
    neigh[neigh > np.iinfo(np.int32).max] = -1        # 0xFFFFFFFF → -1
    if isinstance(faces, tuple):
        conn, offsets = faces
    else:
        conn, offsets = _faces_to_csr(faces)

    S, face_c = face_geometry(vertices, (conn, offsets))
    volumes, centroids = cell_geometry(vertices, (conn, offsets),
                                       owner, neigh)
    if cell_centers is not None and len(cell_centers) == len(centroids):
        centroids = np.asarray(cell_centers, dtype=float)

    n_cells = len(centroids)
    internal = neigh >= 0
    boundary = ~internal

    rep = QualityReport(
        n_faces=len(owner), n_internal=int(internal.sum()),
        n_boundary=int(boundary.sum()), n_cells=n_cells,
        cell_volumes=volumes,
        n_negative_volume=int(np.count_nonzero(volumes < 0.0)))

    # ── 非正交度（内面）：d 与 S 夹角 ──
    non_ortho = np.full(len(owner), np.nan)
    if internal.any():
        c_own = centroids[owner[internal]]
        c_nei = centroids[neigh[internal]]
        d = c_nei - c_own
        s = S[internal]
        dn = np.linalg.norm(d, axis=1)
        sn = np.linalg.norm(s, axis=1)
        cos_t = np.zeros(dn.shape)
        good = (dn > 1e-300) & (sn > 1e-300)
        cos_t[good] = np.abs(np.einsum("ij,ij->i", d[good], s[good])) / (
            dn[good] * sn[good])
        non_ortho[internal] = np.degrees(
            np.arccos(np.clip(cos_t, 0.0, 1.0)))
    rep.non_orthogonality = non_ortho

    # ── 偏斜度（内面）：中心连线交点偏离面重心 ──
    skew = np.full(len(owner), np.nan)
    if internal.any():
        c_own = centroids[owner[internal]]
        c_nei = centroids[neigh[internal]]
        cf = face_c[internal]
        d = c_nei - c_own
        dd = np.einsum("ij,ij->i", d, d)
        t = np.zeros(dd.shape)
        good = dd > 1e-300
        t[good] = np.einsum("ij,ij->i", cf[good] - c_own[good],
                            d[good]) / dd[good]
        p = c_own + t[:, None] * d
        dist = np.linalg.norm(p - cf, axis=1)
        dn = np.sqrt(dd)
        sk = np.zeros(dist.shape)
        sk[good] = dist[good] / dn[good]
        skew[internal] = sk
    rep.skewness = skew

    # ── 边界面正交度：C_f - C_P 与法向夹角 ──
    bno = np.empty(0)
    if boundary.any():
        cp = centroids[owner[boundary]]
        cf = face_c[boundary]
        s = S[boundary]
        v = cf - cp
        vn = np.linalg.norm(v, axis=1)
        sn = np.linalg.norm(s, axis=1)
        cos_t = np.zeros(vn.shape)
        good = (vn > 1e-300) & (sn > 1e-300)
        cos_t[good] = np.abs(np.einsum("ij,ij->i", v[good], s[good])) / (
            vn[good] * sn[good])
        bno = np.degrees(np.arccos(np.clip(cos_t, 0.0, 1.0)))
    rep.boundary_non_ortho = bno

    # ── 单元长宽比：包围盒最长边 / 最短边（对薄切片单元数值稳定）──
    if conn.size and len(owner):
        npe = np.diff(offsets)
        face_of_conn = np.repeat(np.arange(len(owner), dtype=np.int64), npe)
        cell_of_conn = owner[face_of_conn]
        coords = vertices[conn]
        cmin = np.full((n_cells, 3), np.inf)
        cmax = np.full((n_cells, 3), -np.inf)
        np.minimum.at(cmin, cell_of_conn, coords)
        np.maximum.at(cmax, cell_of_conn, coords)
        extent = cmax - cmin
        emax = extent.max(axis=1)
        emin = extent.min(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            aspect = np.where(emin > 0, emax / emin, np.nan)
        rep.cell_aspect = aspect
    return rep


# ────────────────────────────────────────────────────────────────────────────
# 适配器
# ────────────────────────────────────────────────────────────────────────────

def from_voxel(result) -> QualityReport:
    """VoxelMeshResult → QualityReport（pairing 装配缓存优先）。"""
    import voxmesh
    faces, owner, neigh = voxmesh.assemble_faces(result)
    return compute_quality(result.vertices, faces, owner, neigh)


def from_poly(result) -> QualityReport:
    """PolyMeshResult → QualityReport（复用已知质心）。"""
    import polymesh
    faces, owner, neigh = polymesh.assemble_faces(result)
    return compute_quality(result.vertices, faces, owner, neigh,
                           cell_centers=result.cell_centers)


def from_gph(path: str | Path) -> QualityReport:
    """GPH 文件 → QualityReport。"""
    import gphstats
    with gphstats.open_buffer(str(path)) as data:
        mesh = gphstats.parse_mesh(data)
    if not mesh or not mesh.get("n_faces"):
        raise ValueError(f"{path}: no mesh (LS_Links) found")
    neigh = np.asarray(mesh["neigh"], dtype=np.int64)
    return compute_quality(
        mesh["vertices"],
        (mesh["conn"], mesh["face_offsets"]),
        mesh["owner"], neigh)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="mesh quality metrics (non-orthogonality / skewness)")
    ap.add_argument("mesh", help="*.gph 体网格")
    ap.add_argument("--histogram", action="store_true",
                    help="打印非正交度直方图")
    args = ap.parse_args(argv)
    rep = from_gph(args.mesh)
    print(rep.format_report(f"Quality: {args.mesh}"))
    if args.histogram:
        print("\nNon-orthogonality histogram (internal faces):")
        total = max(1, rep.n_internal)
        for label, cnt in rep.histogram("non_orthogonality"):
            print(f"  {label:>8} {cnt:8,}  ({cnt / total:5.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
