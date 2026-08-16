#!/usr/bin/env python3
"""原生 BAM（Build Analysis Model）管线 —— 无宿主时对齐 Analysis Model Wizard。

步骤严格对照录制锁定的 scFLOWpre MDLWizard 序列（``box_scflow_mdl.vbs``，
2026-08-14；``automation/pipeline_plan.BAM_WIZARD_ACTIONS``）：

| # | 向导步骤（VBS） | 原生实现 |
|---|------------------|----------|
| 1 | BeginMDLWizard / Proj 设置（Project solids/sheets、Use AF facetter、精度类型） | :class:`BamParams` 参数面（session/xenv） |
| 2 | ``CreateBoundary`` | :func:`create_boundary`：一致定向 + 连通分量 + 水密闭体识别 → csid |
| 3 | ``CreateMultiEntityInfo`` ×6 | :func:`detect_multifold`：多重边/多重面识别 |
| 4 | Facet 精度设置（AF 角度/边长比/最大边、绝对值） | 参数记录（原生面片已存在，不重剖分） |
| 5 | ``Set/ReconfigureSpatialSeparationSettings``（Influence of adjacent part） | 记录 influence targets（几何效应在宿主内核） |
| 6 | ``SetAutoRemoveTinyFaceConfigured`` | 自动微小面去除配置（tiny_pct / tol） |
| 7 | ``CreateMDL`` | 面片装配（本模块输入即剖分结果） |
| 8 | ``FindAFFaceMatching`` + ``SetFaceMatched`` | :func:`match_faces`：容差匹配 + frid 合并 |
| 9 | ``FindTinyFace`` + ``SetTinyFacesRemoved`` | :func:`remove_tiny_faces`：顶点坍缩删除 |
| 10 | ``RepairMDL`` | :func:`repair_surface`：焊接/去重/重定向/去孤立点 |
| 11 | ``CheckMDLErrors`` | :func:`check_errors`：非法形状报告 + buildable |
| 12 | Ridge 标记（CreateBoundary 副产品） | 尖边二面角 → edge_state / node_state |

产物经 :func:`write_bam_mdl` 写出 ``*_part.mdl``（LS_CsidOfFaces /
LS_FridOfFaces / LS_EdgeStateOfFaces / LS_MdlClosedVolumes /
LS_MdlVolumeRegions / LS_MdlSurfaceRegions，布局与宿主一致，
见 ``mdl.write_mdl``）。
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np


# ────────────────────────────────────────────────────────────────────────────
# 参数与报告
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class BamParams:
    """原生 BAM 参数（键位对齐 Analysis Model Wizard session["build_am"]）。"""

    # 1. Interference 页
    project_solids: bool = True
    project_sheets: bool = True
    use_facetter: bool = True            # solid-based (AF) faceter
    acc_type: str = "0"                  # 0=Specify value 1=Specify octree
    # 2. Multi-fold 容差（1/N 的分母，越大越严格）
    tol_multifold_edge: float = 1e6
    tol_multifold_face: float = 1e6
    # 3. Facet accuracy（原生面片已存在 → 仅记录，用于报告与 xenv 透传）
    sb_ang: float = 10.0                 # deg
    sb_len: float = 0.05                 # edge length reduction ratio
    max_edge: float = 5.0
    absolute: bool = False
    dist_abs: float = 0.0
    edge_abs: float = 0.0
    # 5. Influence of adjacent part
    influence_enable: bool = False
    influence_targets: list[str] = field(default_factory=list)
    # 8. Face matching
    apply_face_matching: bool = True
    match_tol: float = 1e-3
    # 9. Tiny faces
    remove_tiny: bool = True
    remove_tiny_tol: float = 1e-3
    tiny_pct: float = 5.0                # 自动去除参考（面宽 %，0-100）
    # 10. Repair
    repair: bool = True
    weld_tol_ratio: float = 1e-8         # 焊接容差 = ratio × 包围盒对角线
    # 11. Ridge（尖边二面角阈值）
    ridge_angle_deg: float = 30.0
    # 区域/体命名
    surface_regions: list = field(default_factory=list)  # [(name, frid)]
    volume_regions: list[str] = field(
        default_factory=lambda: ["FluidRegion"])

    @classmethod
    def from_session(cls, sess: Optional[dict] = None,
                     xenv=None) -> "BamParams":
        """从向导 session["build_am"]（缺省回落 xenv FACET 键）构造参数。"""
        sess = sess or {}

        def _xb(key: str, default: bool) -> bool:
            if xenv is None:
                return default
            raw = xenv.get("FACET", key, "true" if default else "false")
            return (raw or ("true" if default else "false")).lower() == "true"

        def _xf(key: str, default: float) -> float:
            if xenv is None:
                return float(default)
            try:
                return float(xenv.get("FACET", key, default) or default)
            except (TypeError, ValueError):
                return float(default)

        def _den(key: str, default: float) -> float:
            """向导的 1/N 容差文本（'1e+06'）→ 分母浮点。"""
            raw = str(sess.get(key, "") or "").strip()
            if not raw:
                return float(default)
            try:
                return float(raw)
            except ValueError:
                return float(default)

        tiny = float(sess.get(
            "tiny_pct", _xf("SOLID_BASE_TINY_FACE_WIDTH_RATIO", 0.05)))
        if tiny <= 1.0:  # xenv 存 0-1 比例，session 存百分数
            tiny *= 100.0
        return cls(
            project_solids=bool(sess.get(
                "project_solids", _xb("PROJECT_SOLIDS", True))),
            project_sheets=bool(sess.get(
                "project_sheets", _xb("PROJECT_SHEETS", True))),
            use_facetter=bool(sess.get(
                "use_facetter", _xb("USE_FACETTER", True))),
            acc_type=str(sess.get(
                "acc_type",
                (xenv.get("FACET", "FACET_ACCURACY_SPECIFY_TYPE", "0")
                 if xenv is not None else "0") or "0")),
            tol_multifold_edge=_den("tol_multifold_edge", 1e6),
            tol_multifold_face=_den("tol_multifold_face", 1e6),
            sb_ang=float(sess.get(
                "sb_ang", _xf("SOLID_BASE_MINIMUM_ANGLE", 10.0))),
            sb_len=float(sess.get(
                "sb_len", _xf("SOLID_BASE_LENGTH_FACTOR", 0.05))),
            max_edge=float(sess.get("max_edge", _xf("SIMPLE_MAX_WIDTH", 5.0))),
            absolute=bool(sess.get(
                "absolute", _xb("USE_ABSOLUTE_VALUE", False))),
            dist_abs=float(sess.get(
                "dist_abs", _xf("SIMPLE_CHORD_TOLERANCE_ABS", 0.0))),
            edge_abs=float(sess.get(
                "edge_abs", _xf("SIMPLE_MAX_WIDTH_ABS", 0.0))),
            influence_enable=bool(sess.get("influence_enable", False)),
            influence_targets=list(sess.get("influence_targets") or []),
            apply_face_matching=bool(sess.get("apply_face_matching", True)),
            match_tol=float(sess.get("match_tol", 1e-3)),
            remove_tiny=bool(sess.get("remove_tiny", True)),
            remove_tiny_tol=float(sess.get("remove_tiny_tol", 1e-3)),
            tiny_pct=tiny,
            repair=bool(sess.get("repair", True)),
        )


@dataclass
class BamReport:
    """CheckMDLErrors 报告 + 各步骤计数（供向导 Repair 页 / 日志）。"""

    rows: list[dict] = field(default_factory=list)  # level/count/type/cause
    n_closed_volumes: int = 0
    n_sheet_components: int = 0
    n_multifold_edges: int = 0
    n_multifold_faces: int = 0
    n_matched_pairs: int = 0
    n_tiny_found: int = 0
    n_tiny_removed: int = 0
    n_open_edges: int = 0
    n_ridge_edges: int = 0
    repair_stats: dict = field(default_factory=dict)
    buildable: bool = False

    def summary_lines(self) -> list[str]:
        lines = [
            f"闭体识别: {self.n_closed_volumes}"
            + (f"（开放面片组件 {self.n_sheet_components}）"
               if self.n_sheet_components else ""),
            f"多重边: {self.n_multifold_edges} / 多重面: {self.n_multifold_faces}",
            f"匹配面对: {self.n_matched_pairs}",
            f"微小面: 发现 {self.n_tiny_found} / 移除 {self.n_tiny_removed}",
            f"开放边: {self.n_open_edges}",
            f"Ridge 边: {self.n_ridge_edges}",
        ]
        if self.repair_stats:
            lines.append("修复: " + ", ".join(
                f"{k}={v}" for k, v in self.repair_stats.items()))
        lines.append(f"可 Build: {'是' if self.buildable else '否'}")
        return lines


@dataclass
class BamResult:
    """原生 BAM 产物（可直接写 ``*_part.mdl``）。"""

    points: np.ndarray                       # (n,3)
    faces: list                              # list[list[int]] 多边形面
    csid: tuple                              # (b1, b2) 两侧闭体 id
    frid: np.ndarray
    edge_state: np.ndarray                   # U1[sum(npe)] ridge 半边
    node_state: np.ndarray
    surface_regions: list                    # [(name, frid)]
    closed_volumes: list[str]                # 含记录 0 = 外部
    volume_regions: list[str]
    report: BamReport

    def tris(self) -> tuple:
        """三角化 (points, tris) 供 octree/mesher 使用。"""
        out: list = []
        for f in self.faces:
            ids = [int(v) for v in f]
            for k in range(1, len(ids) - 1):
                out.append([ids[0], ids[k], ids[k + 1]])
        return self.points, np.asarray(out, dtype=np.int64).reshape(-1, 3)


# ────────────────────────────────────────────────────────────────────────────
# 几何基元
# ────────────────────────────────────────────────────────────────────────────

def _face_list(faces: Sequence) -> list:
    return [[int(v) for v in f] for f in faces]


def _edge_key(a: int, b: int) -> tuple:
    return (a, b) if a < b else (b, a)


def _edge_faces(faces: list) -> dict:
    """无向边 → 引用它的 (face_id, 遍历方向) 列表。

    方向 +1 表示面按 (min→max) 遍历该边，-1 反之。
    """
    em: dict = defaultdict(list)
    for fid, face in enumerate(faces):
        n = len(face)
        for k in range(n):
            a, b = face[k], face[(k + 1) % n]
            d = 1 if a < b else -1
            em[_edge_key(a, b)].append((fid, d))
    return em


def _face_normal(points: np.ndarray, face: list) -> np.ndarray:
    """Newell 法向（未归一化时长度为 2×面积量级）。"""
    pts = points[np.asarray(face, dtype=np.int64)]
    n = np.zeros(3)
    for i in range(len(pts)):
        a = pts[i]
        b = pts[(i + 1) % len(pts)]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    norm = float(np.linalg.norm(n))
    return n / norm if norm > 1e-30 else n


def _face_size(points: np.ndarray, face: list) -> float:
    """面宽度指标 = 最大边长（对齐 detect_tiny_faces）。"""
    pts = points[np.asarray(face, dtype=np.int64)]
    d = np.linalg.norm(np.roll(pts, -1, axis=0) - pts, axis=1)
    return float(d.max()) if d.size else 0.0


def _signed_volume(points: np.ndarray, faces: list,
                   comp: Optional[set] = None) -> float:
    """散度定理体积（一致定向且外向时为正）。"""
    vol = 0.0
    ids = comp if comp is not None else range(len(faces))
    for fid in ids:
        f = faces[fid]
        if len(f) < 3:
            continue
        p0 = points[f[0]]
        for k in range(1, len(f) - 1):
            vol += float(np.dot(p0, np.cross(points[f[k]],
                                             points[f[k + 1]])))
    return vol / 6.0


def _weld_vertices(points: np.ndarray, faces: list,
                   tol: float) -> tuple:
    """合并间距 < tol 的顶点（量化桶哈希）。返回 (points, faces, n_welded)。"""
    if tol <= 0 or len(points) == 0:
        return points, faces, 0
    key_of = {}
    remap = np.arange(len(points))
    kept: list = []
    for i, p in enumerate(points):
        key = (round(float(p[0]) / tol), round(float(p[1]) / tol),
               round(float(p[2]) / tol))
        j = key_of.get(key)
        if j is None:
            key_of[key] = len(kept)
            kept.append(p)
            remap[i] = len(kept) - 1
        else:
            remap[i] = j
    n_welded = len(points) - len(kept)
    if n_welded == 0:
        return points, faces, 0
    new_faces = []
    for f in faces:
        nf = []
        for v in f:
            nv = int(remap[v])
            if not nf or nf[-1] != nv:
                nf.append(nv)
        if len(nf) > 2 and nf[0] == nf[-1]:
            nf.pop()
        new_faces.append(nf)
    return np.asarray(kept, dtype=float).reshape(-1, 3), new_faces, n_welded


def _drop_degenerate(faces: list) -> tuple:
    """丢弃去重后顶点数 < 3 的面。返回 (faces, n_dropped)。"""
    out = []
    dropped = 0
    for f in faces:
        uniq = list(dict.fromkeys(f))
        if len(uniq) >= 3:
            out.append(uniq)
        else:
            dropped += 1
    return out, dropped


def _drop_duplicate_faces(faces: list) -> tuple:
    """丢弃顶点集完全相同的面（保留首个）。返回 (faces, keep_mask, n_dup)。"""
    seen: dict = {}
    out = []
    keep = []
    n_dup = 0
    for f in faces:
        key = frozenset(f)
        if key in seen:
            n_dup += 1
            keep.append(False)
            continue
        seen[key] = True
        out.append(f)
        keep.append(True)
    return out, keep, n_dup


def _components(faces: list, em: Optional[dict] = None) -> list:
    """按共享边连通的 face 分量（union-find）。"""
    em = em if em is not None else _edge_faces(faces)
    parent = list(range(len(faces)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for refs in em.values():
        if len(refs) >= 2:
            f0 = refs[0][0]
            for fid, _d in refs[1:]:
                union(f0, fid)
    comps: dict = defaultdict(list)
    for fid in range(len(faces)):
        comps[find(fid)].append(fid)
    return list(comps.values())


def _orient_consistent(faces: list) -> list:
    """BFS 重定向：相邻面的共享边遍历方向相反（分量内法向一致）。"""
    em = _edge_faces(faces)
    adj: dict = defaultdict(list)
    for refs in em.values():
        if len(refs) == 2:
            (f0, d0), (f1, d1) = refs
            adj[f0].append((f1, d0 * d1))
            adj[f1].append((f0, d0 * d1))
    sign = [0] * len(faces)
    for seed in range(len(faces)):
        if sign[seed] != 0:
            continue
        sign[seed] = 1
        stack = [seed]
        while stack:
            f = stack.pop()
            for g, dd in adj[f]:
                want = -sign[f] * dd
                if sign[g] == 0:
                    sign[g] = want
                    stack.append(g)
    return [f if sign[i] > 0 else list(reversed(f))
            for i, f in enumerate(faces)]


def _flip_inward_components(points: np.ndarray, faces: list) -> list:
    """水密闭分量符号体积 < 0 → 整体翻转（法向朝外）。"""
    em = _edge_faces(faces)
    comps = _components(faces, em)
    comp_of = {}
    flip_comps = set()
    for ci, comp in enumerate(comps):
        comp_set = set(comp)
        for fid in comp:
            comp_of[fid] = ci
        watertight = all(len(refs) == 2
                         for refs in em.values()
                         if refs[0][0] in comp_set)
        if watertight and _signed_volume(points, faces, comp_set) < 0:
            flip_comps.add(ci)
    if not flip_comps:
        return faces
    return [list(reversed(f)) if comp_of[i] in flip_comps else f
            for i, f in enumerate(faces)]


def _compact_vertices(points: np.ndarray, faces: list) -> tuple:
    """删除未被引用的孤立顶点并压实索引。"""
    used = sorted({v for f in faces for v in f})
    remap = {old: new for new, old in enumerate(used)}
    new_pts = points[np.asarray(used, dtype=np.int64)]
    new_faces = [[remap[v] for v in f] for f in faces]
    return new_pts, new_faces, len(points) - len(used)


# ────────────────────────────────────────────────────────────────────────────
# 向导步骤实现
# ────────────────────────────────────────────────────────────────────────────

def create_boundary(points: np.ndarray, faces: list) -> tuple:
    """``CreateBoundary``：一致定向 + 闭体识别 → csid。

    返回 ``(faces, csid=(b1,b2), n_closed, n_sheets, n_open_edges)``：

    - 一致定向（共享边反向遍历）+ 水密闭分量符号体积朝外；
    - 水密分量（每条边恰被 2 面共享）→ 闭体 k（1 起）：csid = (0, k)；
    - 非水密分量（sheet）→ csid = (0, 0)，并统计其开放边；
    - 与 part MDL 语义一致（b1=0 外部 / b2=所属体；体间界面属 ridge MDL，
      原生 part 不内嵌）。
    """
    faces = _orient_consistent(faces)
    faces = _flip_inward_components(points, faces)
    em = _edge_faces(faces)
    b1 = np.zeros(len(faces), dtype=np.int64)
    b2 = np.zeros(len(faces), dtype=np.int64)
    n_open = 0
    n_closed = 0
    n_sheets = 0
    for comp in _components(faces, em):
        comp_set = set(comp)
        watertight = True
        open_edges = 0
        for key, refs in em.items():
            if refs[0][0] not in comp_set:
                continue
            if len(refs) == 1:
                open_edges += 1
                watertight = False
            elif len(refs) > 2:
                watertight = False
        if watertight:
            n_closed += 1
            for fid in comp:
                b2[fid] = n_closed
        else:
            n_sheets += 1
            n_open += open_edges
    return faces, (b1, b2), n_closed, n_sheets, n_open


def _proximity_remap(points: np.ndarray, tol: float) -> np.ndarray:
    """距离 < tol 的顶点并为一组（cKDTree + union-find）→ 代表 id 映射。

    仅返回映射，不修改几何；代表 = 组内最小顶点 id（保证确定性）。
    """
    n = len(points)
    if tol <= 0 or n < 2:
        return np.arange(n, dtype=np.int64)
    from scipy.spatial import cKDTree
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in cKDTree(points).query_pairs(float(tol)):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)
    roots = [find(v) for v in range(n)]
    return np.asarray(roots, dtype=np.int64)


def detect_multifold(points: np.ndarray, faces: list,
                     tol_edge: float = 0.0,
                     tol_face: float = 0.0) -> tuple:
    """``CreateMultiEntityInfo``：多重边（>2 面共享）与多重面（顶点集重复）。

    容差合并（P3-1）：``tol_edge`` / ``tol_face`` > 0 时先把间距小于容差
    的顶点并为同一代表（只影响分组键，不改几何），缝隙面片间微偏的
    重合边/重复面也能识别——对齐向导 1/N 容差语义
    （``tol = 包围盒对角线 / N``，N 即 ``tol_multifold_*`` 分母）。
    返回 ``(mf_edges: dict[key, list[face_id]], n_mf_faces)``。
    """
    em = _edge_faces(faces)
    mf_edges: dict = {k: [f for f, _d in v] for k, v in em.items()
                      if len(v) > 2}

    # 容差模式：代表键分组，补上精确拓扑抓不到的"几何重合"实例
    if tol_edge > 0 or tol_face > 0:
        remap_e = _proximity_remap(points, tol_edge)
        remap_f = _proximity_remap(points, tol_face)
        if tol_edge > 0:
            groups: dict = defaultdict(set)
            for fid, face in enumerate(faces):
                ids = [int(remap_e[v]) for v in face]
                for a, b in zip(ids, ids[1:] + ids[:1]):
                    if a != b:
                        groups[(min(a, b), max(a, b))].add(fid)
            for key, fids in groups.items():
                if len(fids) > 2 and key not in mf_edges:
                    mf_edges[key] = sorted(fids)
        if tol_face > 0:
            # 多重面 = 总面数 − 代表键（容差内顶点集）去重后的组数；
            # tol_face→0 时退化为精确口径（每对重复面计 1）
            keys = {frozenset(int(remap_f[v]) for v in face)
                    for face in faces}
            return mf_edges, len(faces) - len(keys)

    seen: dict = {}
    mf_faces = 0
    for f in faces:
        key = frozenset(f)
        if key in seen:
            mf_faces += 1
        else:
            seen[key] = True
    return mf_edges, mf_faces


def match_faces(points: np.ndarray, faces: list, frid: np.ndarray,
                tol: float) -> tuple:
    """``FindAFFaceMatching`` + ``SetFaceMatched``。

    匹配判据（容差 ``tol``）：质心距 ≤ tol、法向相反（dot ≤ -0.99）、
    面积差 ≤ 1%；匹配对 frid 合并为较小值。返回 (frid, pairs)。
    """
    if len(faces) == 0 or tol <= 0:
        return frid, []
    cents = np.empty((len(faces), 3))
    norms = np.empty((len(faces), 3))
    areas = np.empty(len(faces))
    for i, f in enumerate(faces):
        pts = points[np.asarray(f, dtype=np.int64)]
        cents[i] = pts.mean(axis=0)
        n = _face_normal(points, f)
        norms[i] = n
        areas[i] = 0.0
        for k in range(1, len(f) - 1):
            areas[i] += 0.5 * float(np.linalg.norm(
                np.cross(pts[k] - pts[0], pts[k + 1] - pts[0])))
    from scipy.spatial import cKDTree
    pairs = cKDTree(cents).query_pairs(float(tol))
    matched = []
    for i, j in sorted(pairs):
        if float(np.dot(norms[i], norms[j])) > -0.99:
            continue
        a0, a1 = areas[i], areas[j]
        if max(a0, a1) <= 0 or abs(a0 - a1) / max(a0, a1) > 0.01:
            continue
        matched.append((i, j))
    if matched:
        frid = frid.copy()
        for i, j in matched:
            lo = min(frid[i], frid[j])
            frid[i] = lo
            frid[j] = lo
    return frid, matched


def remove_tiny_faces(points: np.ndarray, faces: list, frid: np.ndarray,
                      tol: float, max_passes: int = 8) -> tuple:
    """``FindTinyFace`` + ``SetTinyFacesRemoved``：微小面顶点坍缩删除。

    每趟把面宽 < tol 的面的全部顶点并到质心（union-find），重建面表时
    丢弃退化面；重复直到无微小面或达到 ``max_passes``。
    返回 (points, faces, frid, n_found, n_removed)。
    """
    if tol <= 0 or len(faces) == 0:
        return points, faces, frid, 0, 0
    n_found = 0
    n_removed = 0
    frid = np.asarray(frid, dtype=np.int64)
    for _ in range(max_passes):
        tiny = [fid for fid, f in enumerate(faces)
                if _face_size(points, f) < tol]
        if not tiny:
            break
        n_found += len(tiny)
        parent = list(range(len(points)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for fid in tiny:
            f = faces[fid]
            for v in f[1:]:
                union(f[0], v)
        # 代表点 → 成员质心
        members: dict = defaultdict(list)
        for v in range(len(points)):
            members[find(v)].append(v)
        new_pos = {r: points[ids].mean(axis=0) for r, ids in members.items()}
        remap = {}
        new_pts = []
        for r, ids in members.items():
            remap[r] = len(new_pts)
            new_pts.append(new_pos[r])
        new_faces = []
        new_frid = []
        for fid, f in enumerate(faces):
            nf = []
            for v in f:
                nv = remap[find(v)]
                if not nf or nf[-1] != nv:
                    nf.append(nv)
            if len(nf) > 2 and nf[0] == nf[-1]:
                nf.pop()
            if len(set(nf)) >= 3:
                new_faces.append(nf)
                new_frid.append(int(frid[fid]))
            else:
                n_removed += 1
        points = np.asarray(new_pts, dtype=float).reshape(-1, 3)
        faces = new_faces
        frid = np.asarray(new_frid, dtype=np.int64)
    return points, faces, frid, n_found, n_removed


def repair_surface(points: np.ndarray, faces: list, frid: np.ndarray,
                   weld_tol: float) -> tuple:
    """``RepairMDL``：焊接重复顶点 → 去退化/重复面 → 一致定向 → 去孤立点。

    所有删面操作均带掩码以保持 ``frid`` 对齐。
    """
    stats: dict = {}
    if weld_tol > 0:
        points, faces, n_weld = _weld_vertices(points, faces, weld_tol)
        if n_weld:
            stats["welded_vertices"] = n_weld
    # 去退化面（焊接/坍缩后可能出现），保持 frid 对齐
    keep = np.asarray([len(set(f)) >= 3 for f in faces], dtype=bool)
    n_deg = int((~keep).sum())
    if n_deg:
        stats["degenerate_faces"] = n_deg
        faces = [f for f, k in zip(faces, keep) if k]
        frid = frid[keep]
    faces, keep2, n_dup = _drop_duplicate_faces(faces)
    if n_dup:
        stats["duplicate_faces"] = n_dup
        frid = frid[np.asarray(keep2, dtype=bool)]
    faces = _orient_consistent(faces)
    faces = _flip_inward_components(points, faces)
    points, faces, n_iso = _compact_vertices(points, faces)
    if n_iso:
        stats["isolated_vertices"] = n_iso
    return points, faces, frid, stats


def detect_ridges(points: np.ndarray, faces: list,
                  angle_deg: float) -> tuple:
    """尖边（二面角 > 阈值）→ LS_EdgeStateOfFaces / LS_StateOfNodes。"""
    em = _edge_faces(faces)
    cos_lim = math.cos(math.radians(angle_deg))
    n_ridge = 0
    edge_state = np.zeros(sum(len(f) for f in faces), dtype=np.uint8)
    node_flag = np.zeros(len(points), dtype=np.int64)
    node_cnt: dict = defaultdict(int)
    normals: dict = {}
    off = 0
    face_off = np.zeros(len(faces) + 1, dtype=np.int64)
    for i, f in enumerate(faces):
        off += len(f)
        face_off[i + 1] = off
    for (a, b), refs in em.items():
        if len(refs) != 2:
            continue
        f0, f1 = refs[0][0], refs[1][0]
        n0 = normals.get(f0)
        if n0 is None:
            n0 = _face_normal(points, faces[f0])
            normals[f0] = n0
        n1 = normals.get(f1)
        if n1 is None:
            n1 = _face_normal(points, faces[f1])
            normals[f1] = n1
        if float(np.dot(n0, n1)) >= cos_lim:
            continue
        n_ridge += 1
        for fid, _d in refs:
            face = faces[fid]
            for k in range(len(face)):
                if _edge_key(face[k], face[(k + 1) % len(face)]) == (a, b):
                    edge_state[face_off[fid] + k] = 1
                    break
        node_cnt[a] += 1
        node_cnt[b] += 1
    for v, c in node_cnt.items():
        if c >= 2:  # 两条以上尖边交汇 → 特征点
            node_flag[v] = 1
    return edge_state, node_flag, n_ridge


def check_errors(points: np.ndarray, faces: list,
                 tiny_tol: float, tol_edge: float = 0.0,
                 tol_face: float = 0.0) -> tuple:
    """``CheckMDLErrors``：非法形状报告（level/count/type/cause）。"""
    em = _edge_faces(faces)
    n_open = sum(1 for v in em.values() if len(v) == 1)
    mf_edges, mf_faces = detect_multifold(points, faces,
                                          tol_edge=tol_edge,
                                          tol_face=tol_face)
    n_tiny = 0
    if tiny_tol > 0:
        n_tiny = sum(1 for f in faces if _face_size(points, f) < tiny_tol)
    rows: list[dict] = []
    if n_tiny:
        rows.append({"level": 1, "count": n_tiny, "type": "Tiny face",
                     "cause": "Face max edge < tolerance"})
    if mf_faces:
        rows.append({"level": 2, "count": mf_faces,
                     "type": "Multi-fold face",
                     "cause": "Faces share the same vertex set"})
    if mf_edges:
        rows.append({"level": 2, "count": len(mf_edges),
                     "type": "Multi-fold edge",
                     "cause": "Edge shared by >2 faces"})
    if n_open:
        rows.append({"level": 3, "count": n_open, "type": "Open edge",
                     "cause": "Edge shared by only one face "
                              "(gap or sheet)"})
    n_closed = 0
    for comp in _components(faces, em):
        comp_set = set(comp)
        if all(len(refs) == 2 for key, refs in em.items()
               if refs[0][0] in comp_set):
            n_closed += 1
    return rows, n_open, n_closed


# ────────────────────────────────────────────────────────────────────────────
# 主管线
# ────────────────────────────────────────────────────────────────────────────

def build_analysis_model(points, faces,
                         params: Optional[BamParams] = None) -> BamResult:
    """原生 BAM 主管线（步骤序对齐 MDLWizard 录制）。

    输入：三角/多边形面片（CAD 剖分或既有 MDL 表面）。
    输出：:class:`BamResult`（含 csid/frid/区域/闭体/报告）。
    """
    params = params or BamParams()
    report = BamReport()
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    faces = _face_list(faces)

    diag = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0))) \
        if len(points) else 1.0
    weld_tol = max(params.weld_tol_ratio * diag, 1e-15)

    # 前置：焊接 + 退化清理（CreateBoundary 需要一致拓扑；保持 frid 对齐）
    points, faces, _ = _weld_vertices(points, faces, weld_tol)
    keep = np.asarray([len(set(f)) >= 3 for f in faces], dtype=bool)
    if not bool(keep.all()):
        faces = [f for f, k in zip(faces, keep) if k]
    frid = np.zeros(len(faces), dtype=np.int64)

    # 1-2. CreateBoundary：定向 + 闭体识别
    faces, (b1, b2), n_closed, n_sheets, n_open = create_boundary(
        points, faces)
    report.n_closed_volumes = n_closed
    report.n_sheet_components = n_sheets
    report.n_open_edges = n_open

    # 3. CreateMultiEntityInfo：多重边/面识别（容差合并；重复面在 Repair 去除）
    tol_edge = diag / max(params.tol_multifold_edge, 1e-12)
    tol_face = diag / max(params.tol_multifold_face, 1e-12)
    mf_edges, mf_faces = detect_multifold(points, faces,
                                          tol_edge=tol_edge,
                                          tol_face=tol_face)
    report.n_multifold_edges = len(mf_edges)
    report.n_multifold_faces = mf_faces

    # 4-5. Facet 精度 / Influence：原生面片不再重剖分，参数随报告透传
    #    （influence targets 的几何效应在宿主内核；原生仅记录）

    # 6. FindAFFaceMatching + SetFaceMatched（仅 AF faceter 路径）
    if params.use_facetter and params.apply_face_matching:
        frid, matched = match_faces(points, faces, frid, params.match_tol)
        report.n_matched_pairs = len(matched)

    # 7. FindTinyFace + SetTinyFacesRemoved
    if params.remove_tiny:
        points, faces, frid, n_found, n_removed = remove_tiny_faces(
            points, faces, frid, params.remove_tiny_tol)
        report.n_tiny_found = n_found
        report.n_tiny_removed = n_removed

    # 8. RepairMDL
    if params.repair:
        points, faces, frid, stats = repair_surface(
            points, faces, frid, weld_tol)
        report.repair_stats = stats

    # 拓扑变更后重跑 CreateBoundary 得最终 csid（CreateMDL 语义）
    faces, (b1, b2), n_closed, n_sheets, n_open = create_boundary(
        points, faces)
    report.n_closed_volumes = n_closed
    report.n_sheet_components = n_sheets
    report.n_open_edges = n_open

    # 9. CheckMDLErrors（容差口径与步骤 3 一致）
    rows, _n_open2, _n_closed2 = check_errors(
        points, faces, params.remove_tiny_tol,
        tol_edge=tol_edge, tol_face=tol_face)
    report.rows = rows
    report.buildable = n_closed >= 1 and not any(
        r["level"] >= 4 for r in rows)

    # 10. Ridge 标记（CreateBoundary 副产品）
    edge_state, node_state, n_ridge = detect_ridges(
        points, faces, params.ridge_angle_deg)
    report.n_ridge_edges = n_ridge

    surface_regions = list(params.surface_regions) or [("@PartSurface_Part", 0)]
    closed_volumes = [""] * (report.n_closed_volumes + 1)  # 记录 0 = 外部
    return BamResult(
        points=points, faces=faces, csid=(b1, b2), frid=frid,
        edge_state=edge_state, node_state=node_state,
        surface_regions=surface_regions,
        closed_volumes=closed_volumes,
        volume_regions=list(params.volume_regions),
        report=report)


def write_bam_mdl(result: BamResult, filepath, **kwargs) -> Path:
    """把 :class:`BamResult` 写出为 ``*_part.mdl``（原生布局）。"""
    import mdl
    kwargs.setdefault("app", "pphdecoding")
    return mdl.write_mdl(
        filepath, result.points, result.faces,
        csid=result.csid, frid=result.frid,
        edge_state=result.edge_state, node_state=result.node_state,
        surface_regions=result.surface_regions,
        closed_volumes=result.closed_volumes,
        volume_regions=result.volume_regions, **kwargs)
