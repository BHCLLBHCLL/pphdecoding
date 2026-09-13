#!/usr/bin/env python3
"""R1-1：x_t 的「本仓离线剖分」与「宿主 OpenCadFile」量化对拍。

同一份 .x_t 走两条路：
  * 离线：本仓 pskernel 直调（PK_PART_receive + PK_TOPOL_facet_2 / B-rep 遍历）
  * 宿主：scFLOWpre OpenCadFile → SaveProject → 解析宿主产出的 *_part.mdl
逐项比较 体数 / B-rep 面·边·顶点 / 剖分三角数 / 包围盒 / 表面积。

两者用的是**同一个 Parasolid 内核**，因此面积与包围盒应达到数值级一致；
剖分三角数会因容差/自适应策略不同而有差异（记录并给出比值）。

用法：
    python tools/cad_compare.py tests/box/box.x_t
    python tools/cad_compare.py model.x_t --json evidence.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mdl  # noqa: E402
import ps_facet2_nodes as ps  # noqa: E402
import automation.host_boot as host_boot  # noqa: E402

WORK = ROOT / "_p12u_cmp"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _area(points, triangles) -> float:
    V = np.asarray(points, dtype=float)
    T = np.asarray(triangles)
    if len(T) == 0:
        return 0.0
    a, b, c = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    return float(np.sum(np.linalg.norm(np.cross(b - a, c - a), axis=1)) / 2.0)


def offline_metrics(path: Path) -> dict:
    raw = path.read_bytes()
    sess = ps._get_session()
    tags = sess.receive_xt(raw)
    bodies = sess.bodies_of(tags)
    out = {"bytes": len(raw), "receive_tags": len(tags),
           "bodies": len(bodies)}
    try:
        br = ps.decode_brep(raw)
        out["brep_faces"] = len(br.get("faces", []))
        out["brep_edges"] = len(br.get("edges", []))
        out["brep_vertices"] = len(br.get("vertices", []))
    except Exception as exc:  # noqa: BLE001
        out["brep_error"] = f"{type(exc).__name__}: {exc}"
    parts = ps.tessellate_xt(raw, adaptive=False)
    out["tess_parts"] = len(parts)
    out["tess_triangles"] = int(sum(len(p.triangles) for p in parts))
    out["tess_area"] = round(sum(_area(p.points, p.triangles) for p in parts), 6)
    if parts:
        P = np.vstack([np.asarray(p.points, dtype=float) for p in parts])
        out["bbox_min"] = [round(float(v), 6) for v in P.min(0)]
        out["bbox_max"] = [round(float(v), 6) for v in P.max(0)]
    return out


def _host_snapshot_metrics(pph: Path) -> dict:
    """宿主存储体（main.sctsnapshot 的 CADthru/PKBody3）→ XT 实体计数。"""
    try:
        import sctsnapshot
        import parasolid
        with zipfile.ZipFile(pph) as z:
            if "main.sctsnapshot" not in z.namelist():
                return {}
            data = z.read("main.sctsnapshot")
        snap = sctsnapshot.SctSnapshot.from_bytes(data)
        counts: dict = {}
        n_bodies = 0
        for item in snap.decompress_bodies():
            pk = item.get("pkbody3")
            if pk is None:
                continue
            n_bodies += 1
            try:
                model = parasolid.parse_xt(pk.decrypt())
            except Exception as exc:  # noqa: BLE001
                key = f"xt_parse_error:{type(exc).__name__}"
                counts[key] = counts.get(key, 0) + 1
                continue
            for nd in (getattr(model, "order", []) or []):
                nm = getattr(nd, "name", None) or type(nd).__name__
                counts[nm] = counts.get(nm, 0) + 1
        return {"snapshot_bodies": n_bodies, "xt_node_types": counts}
    except Exception as exc:  # noqa: BLE001
        return {"snapshot_error": f"{type(exc).__name__}: {exc}"}


def host_metrics(xt: Path) -> dict:
    """宿主 OpenCadFile → SaveProject → 解析产出的 *_part.mdl。"""
    p12e = _load("p12e_run", ROOT / "tools" / "_p12e_e2e_run.py")
    WORK.mkdir(parents=True, exist_ok=True)
    out_pph = WORK / "host_out.pph"
    vbs = WORK / "r1_host.vbs"
    log = WORK / "r1_host.log"
    if log.is_file():
        log.unlink()
    actions = [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        "RetWW0_ = Doc_.WaitForWorker",
        f'Set SN_ = Doc_.OpenCadFile("{xt.as_posix()}")',
        "RetWW1_ = Doc_.WaitForWorker",
        "Doc_.SetModePart",
        "RetWW2_ = Doc_.WaitForWorker",
        "Param1_ = False",
        "Doc_.GetAllPartsBoundingBox BBox_, False",
        'If IsArray(BBox_) Then out_.WriteLine "hbbox=" & CStr(BBox_(0)) '
        '& "," & CStr(BBox_(1)) & "," & CStr(BBox_(2)) & "," '
        '& CStr(BBox_(3)) & "," & CStr(BBox_(4)) & "," & CStr(BBox_(5)) '
        'Else out_.WriteLine "hbbox=NA"',
        "Err.Clear",
        f'Doc_.SaveProject "{out_pph.as_posix()}"',
    ]
    p12e._write_ansi_vbs(p12e.logged_script([("host", actions)], log, "R1-1"),
                         vbs, "R1-1")
    t0 = time.time()
    try:
        p12e.run_e2e("r1_host", vbs, log, timeout=900.0, retry_with_boot=True)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}
    out = {"seconds": round(time.time() - t0, 1)}
    if log.is_file():
        text = log.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^hbbox=([-0-9eE.,]+)$", text, re.MULTILINE)
        if m:
            try:
                vals = [float(v) for v in m.group(1).split(",")]
                out["host_bbox_min"] = [round(v, 6) for v in vals[0:3]]
                out["host_bbox_max"] = [round(v, 6) for v in vals[3:6]]
            except Exception:  # noqa: BLE001
                out["host_bbox_raw"] = m.group(1)
    if not out_pph.is_file():
        out["error"] = "host produced no project"
        return out
    # 宿主把导入的 Parasolid 体存进 main.sctsnapshot 的 CADthru/PKBody3；
    # OpenCadFile 本身不产出 *_part.mdl（那需要 BAM/CreateMDL 步骤），
    # 因此这里优先比对**宿主存储体**与离线接收体的实体计数。
    snap = _host_snapshot_metrics(out_pph)
    if snap:
        out.update(snap)
    with zipfile.ZipFile(out_pph) as z:
        names = [n for n in z.namelist() if n.endswith("_part.mdl")]
        if not names:
            out.setdefault("note", "host project has no *_part.mdl "
                                   "(OpenCadFile 不产 facet MDL)")
            out["members"] = z.namelist()
            return out
        data = z.read(sorted(names)[0])
        out["member"] = sorted(names)[0]
        out["mdl_bytes"] = len(data)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "host_part.mdl"
        p.write_bytes(data)
        m = mdl.parse_mdl(p)
        faces = [m.face_nodes(i) for i in range(m.n_faces)]
        verts = np.asarray(m.xyz, dtype=float)
        out["mdl_vertices"] = int(len(verts))
        out["mdl_faces"] = int(m.n_faces)
        tris = mdl.triangulate_faces(m) if hasattr(mdl, "triangulate_faces") else None
        pts, tri = (tris if tris is not None else (verts, None))
        if tri is not None and len(tri):
            out["mdl_triangles"] = int(len(tri))
            out["mdl_area"] = round(_area(pts, tri), 6)
        if len(verts):
            out["bbox_min"] = [round(float(v), 6) for v in verts.min(0)]
            out["bbox_max"] = [round(float(v), 6) for v in verts.max(0)]
    return out


def _tri_areas_normals(points, triangles):
    """三角形面积 + 单位法向（R2-2 面元级对拍基础量）。"""
    V = np.asarray(points, dtype=float)
    T = np.asarray(triangles)
    if len(T) == 0:
        return np.zeros(0), np.zeros((0, 3))
    a, b, c = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    cr = np.cross(b - a, c - a)
    ar = np.linalg.norm(cr, axis=1) / 2.0
    with np.errstate(invalid="ignore", divide="ignore"):
        n = cr / (2.0 * ar)[:, None]
    n[~np.isfinite(n)] = 0.0
    return ar, n


#: 六轴向（+X -X +Y -Y +Z -Z）单位矢量
_AXES = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0],
                  [0, -1, 0], [0, 0, 1], [0, 0, -1]], dtype=float)


def facet_profile(points, triangles) -> dict:
    """面元级画像：三角数 / 总面积 / 面积累积分布 / 轴向面积分解。

    面积累积分布（按面积降序的累积占比）与轴向面积分解都是对**分面策略
    不敏感**的形态量：不同容差产出不同三角数，但同一几何的这两条曲线
    应彼此靠近。
    """
    ar, n = _tri_areas_normals(points, triangles)
    tot = float(ar.sum())
    out: dict = {"triangles": int(len(ar)), "area_total": round(tot, 9)}
    if tot <= 0.0 or len(ar) == 0:
        return out
    s = np.sort(ar)[::-1]
    cum = np.cumsum(s) / tot
    dist = {}
    for q in (10, 25, 50, 75, 90, 99):
        i = min(len(cum) - 1, max(0, int(round(q / 100.0 * len(cum))) - 1))
        dist[str(q)] = round(float(cum[i]), 4)
    out["area_cum_pct"] = dist
    dots = n @ _AXES.T
    idx = np.argmax(dots, axis=1)
    proj = np.abs(dots[np.arange(len(n)), idx])
    axial = np.zeros(6)
    np.add.at(axial, idx, ar * proj)
    out["axial_area"] = [round(float(v), 9) for v in axial]
    out["area_min"] = round(float(ar.min()), 9)
    out["area_max"] = round(float(ar.max()), 9)
    return out


def facet_profile_mesh(points, tri_index) -> dict:
    """已索引三角网格 → :func:`facet_profile`（``mdl.triangulate_faces`` 形态）。

    ``mdl.triangulate_faces`` 返回 ``(tri_verts (m,3), face_of_tri (m,))``，
    即**顶点下标**而非坐标；这里先取出三角坐标再交给统一的面积/法向分解。
    """
    V = np.asarray(points, dtype=float)
    T = np.asarray(tri_index, dtype=np.int64)
    if len(T) == 0:
        return {"triangles": 0, "area_total": 0.0}
    P = V[T].reshape(-1, 3)
    TT = np.arange(len(P), dtype=np.int64).reshape(-1, 3)
    return facet_profile(P, TT)


def _rel(a, b) -> float | None:
    if a is None or b is None:
        return None
    d = max(abs(float(a)), abs(float(b)))
    if d == 0.0:
        return 0.0
    return round(abs(float(a) - float(b)) / d, 9)


def facet_compare(off: dict, host: dict) -> dict:
    """离线剖分 vs 宿主分面的面元级差异（相对量，分面策略无关者优先）。"""
    res: dict = {"triangles_off": off.get("triangles"),
                 "triangles_host": host.get("triangles"),
                 "area_total_off": off.get("area_total"),
                 "area_total_host": host.get("area_total"),
                 "area_total_relerr": _rel(off.get("area_total"),
                                           host.get("area_total"))}
    if off.get("triangles") and host.get("triangles"):
        res["triangles_ratio"] = round(
            host["triangles"] / float(off["triangles"]), 4)
    oa, ha = off.get("axial_area"), host.get("axial_area")
    if oa and ha:
        so, sh = sum(oa), sum(ha)
        res["axial_off"] = oa
        res["axial_host"] = ha
        if so > 0 and sh > 0:
            res["axial_relerr"] = round(
                float(np.abs(np.asarray(oa) / so - np.asarray(ha) / sh).max()),
                6)
    oc, hc = off.get("area_cum_pct"), host.get("area_cum_pct")
    if oc and hc:
        res["area_cum_pct_off"] = oc
        res["area_cum_pct_host"] = hc
        res["area_cum_maxdiff"] = round(
            max(abs(oc[k] - hc[k]) for k in oc if k in hc), 4)
    return res


def host_facet_metrics(pph: Path) -> dict:
    """宿主工程里 *_part.mdl 的分面画像（BAM/网格产物的宿主侧真值）。"""
    out: dict = {"pph": str(pph)}
    if not pph.is_file():
        out["error"] = "pph missing"
        return out
    with zipfile.ZipFile(pph) as z:
        out["all_members"] = z.namelist()
        names = sorted(n for n in z.namelist() if n.endswith("_part.mdl"))
        out["mdl_members"] = names
        if not names:
            out["error"] = "no *_part.mdl member"
            return out
        data = z.read(names[0])
    out["member"] = names[0]
    out["mdl_bytes"] = len(data)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "host_part.mdl"
        p.write_bytes(data)
        m = mdl.parse_mdl(p)
        out["mdl_vertices"] = int(len(m.xyz))
        out["mdl_faces"] = int(m.n_faces)
        if not hasattr(mdl, "triangulate_faces"):
            out["error"] = "triangulate_faces unavailable"
            return out
        tri_idx, _face_of = mdl.triangulate_faces(m)
        if not len(tri_idx):
            out["error"] = "no triangles in host MDL"
            return out
        out["host_triangles_from_faces"] = int(len(tri_idx))
        out.update(facet_profile_mesh(m.xyz, tri_idx))
        V = np.asarray(m.xyz, dtype=float)
        if len(V):
            out["bbox_min"] = [round(float(v), 9) for v in V.min(0)]
            out["bbox_max"] = [round(float(v), 9) for v in V.max(0)]
    return out


def offline_facet_metrics(xt: Path) -> dict:
    """离线 pskernel 剖分的分面画像（多体合并为一份点/三角）。"""
    raw = xt.read_bytes()
    parts = ps.tessellate_xt(raw, adaptive=False)
    pts = [np.asarray(p.points, dtype=float) for p in parts if len(p.triangles)]
    tris = []
    off = 0
    for p in parts:
        t = np.asarray(p.triangles)
        if not len(t):
            continue
        tris.append(t + off)
        off += len(p.points)
    if not pts:
        return {"error": "tessellation produced no triangles"}
    P = np.vstack(pts)
    T = np.vstack(tris)
    out = {"parts": len(parts)}
    out.update(facet_profile(P, T))
    out["bbox_min"] = [round(float(v), 9) for v in P.min(0)]
    out["bbox_max"] = [round(float(v), 9) for v in P.max(0)]
    return out


def compare(off: dict, host: dict) -> list[tuple]:
    rows = []
    for key, label, tol in (("bodies", "体数", 0),
                            ("brep_faces", "B-rep 面", 0),
                            ("brep_edges", "B-rep 边", 0),
                            ("brep_vertices", "B-rep 顶点", 0),
                            ("tess_triangles", "剖分三角数", None),
                            ("tess_area", "表面积", 1e-6),
                            ("bbox_min", "bbox min", 1e-6),
                            ("bbox_max", "bbox max", 1e-6)):
        o = off.get(key)
        h = host.get("mdl_faces" if key == "brep_faces" else key)
        rows.append((label, o, h, tol))
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R1-1 x_t 离线↔宿主量化对拍")
    ap.add_argument("xt", type=Path)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--facets", action="store_true",
                    help="R2-2：额外做面元级对拍（用 --host-pph 的宿主产物）")
    ap.add_argument("--host-pph", type=Path,
                    default=ROOT / "_p2_accept" / "control_out.pph",
                    help="宿主已产出 /*_part.mdl 的工程（默认 P2 宿主原生控制件）")
    args = ap.parse_args(argv)
    xt = args.xt.resolve()
    if not xt.is_file():
        print(json.dumps({"error": f"x_t missing: {xt}"}))
        return 1
    off = offline_metrics(xt)
    result = {"xt": str(xt), "offline": off}
    if args.facets:
        off_f = offline_facet_metrics(xt)
        host_f = host_facet_metrics(args.host_pph.resolve())
        result["facets"] = {
            "offline": off_f, "host": host_f,
            "compare": facet_compare(off_f, host_f),
        }
    if not args.offline_only:
        host_boot.cold_boot()
        result["host"] = host_metrics(xt)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
