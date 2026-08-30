#!/usr/bin/env python3
"""BAM 报告对拍（冲刺 E · 域 6 收口）——宿主 BAM 产物 × native_bam 报告。

对拍口径（§9.6 豁免下的量化对拍）：

- **不变量对拍**（必须相等）：闭体数、水密（开放边=0）、多重边/面数、
  可 Build、体积区域名含 FluidRegion——这些是拓扑事实，与剖分密度无关；
- **密度相关量只记录不断言**：顶点/面数、Ridge 半边数——宿主 AF
  faceter 的细分密度是宿主内核行为（§9.6 豁免），本仓离线剖分不追平；
- **区域结构记录**：宿主 VMDL 导出的表面区域命名模式
  （``@PartSurface_Part`` / ``@VMDLSurf_MG0_*``）。

输入：P12-A BAM e2e 权威导出 ``p12a_bam_e2e_part.mdl``（VMDL.Save 产物）
+ 同一几何（``tests/box/box.x_t``）经 ``cad_import``（pskernel facet_2）
离线剖分后跑 ``native_bam.build_analysis_model``。

用法::

    python bam_reconcile.py [--host p12a_bam_e2e_part.mdl]
                            [--xt tests/box/box.x_t] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def host_mdl_facts(path) -> dict:
    """宿主 VMDL.Save 产物的报告级事实（拓扑不变量 + 密度记录）。"""
    import mdl

    m = mdl.parse_mdl(str(path))
    em = mdl.edge_face_map(m)
    n_open = sum(1 for refs in em.values() if len(refs) == 1)
    mf = mdl.detect_multifold_edges(m)
    b2 = m.csid[1]
    bodies = {int(v) for v in set(b2.tolist()) if int(v) > 0}
    ridge_state = m.edge_state
    n_ridge_half = 0
    if ridge_state is not None:
        import numpy as np
        n_ridge_half = int((np.asarray(ridge_state) > 0).sum())
    frid = m.frid
    n_frid = 0
    if frid is not None:
        import numpy as np
        n_frid = len(set(np.asarray(frid).tolist()))
    return {
        "source": str(path),
        "n_vertices": int(m.n_vertices),
        "n_faces": int(m.n_faces),
        "n_closed_volumes": int(m.n_closed_volumes),
        "n_open_edges": int(n_open),
        "n_multifold_edges": len(mf),
        "watertight": n_open == 0,
        "buildable": m.n_closed_volumes >= 1 and n_open == 0,
        "body_ids": sorted(bodies),
        "n_ridge_halfedges": n_ridge_half,
        "n_frid_groups": n_frid,
        "surface_regions": [r.name for r in m.surface_regions],
        "volume_regions": list(m.volume_regions),
    }


def native_facts(xt_path, params=None) -> dict:
    """同一 x_t 几何离线剖分 → native_bam 报告事实。"""
    import cad_import
    import native_bam

    bodies = cad_import.import_xt_file(str(xt_path))
    if not bodies:
        raise SystemExit(f"faceting produced no body: {xt_path}")
    tess = bodies[0].tess
    import numpy as np
    pts = np.asarray(tess.points, dtype=float).reshape(-1, 3)
    tris = np.asarray(tess.triangles, dtype=np.int64).reshape(-1, 3)
    res = native_bam.build_analysis_model(pts, tris, params)
    r = res.report
    return {
        "source": str(xt_path),
        "n_facet_points": len(pts),
        "n_facet_tris": len(tris),
        "n_vertices": len(res.points),
        "n_faces": len(res.faces),
        "n_closed_volumes": int(r.n_closed_volumes),
        "n_open_edges": int(r.n_open_edges),
        "n_multifold_edges": int(r.n_multifold_edges),
        "n_multifold_faces": int(r.n_multifold_faces),
        "n_matched_pairs": int(r.n_matched_pairs),
        "watertight": r.n_open_edges == 0,
        "buildable": bool(r.buildable),
        "n_ridge_edges": int(r.n_ridge_edges),
        "volume_regions": list(res.volume_regions),
    }


# 必须相等的拓扑不变量
INVARIANT_KEYS = ("n_closed_volumes", "n_open_edges", "watertight",
                  "buildable")
# 仅记录（宿主内核剖分密度，§9.6 豁免）
DENSITY_KEYS = ("n_vertices", "n_faces")


def reconcile(host: dict, native: dict) -> dict:
    """生成对拍表：不变量逐项 match/FAIL + 密度记录。"""
    rows = []
    ok = True
    for key in INVARIANT_KEYS:
        hv = host.get(key)
        nv = native.get(key)
        match = hv == nv
        ok = ok and match
        rows.append({"field": key, "host": hv, "native": nv,
                     "kind": "invariant", "match": match})
    # 宿主无 multifold 面概念字段，单边对拍
    rows.append({"field": "n_multifold_edges",
                 "host": host.get("n_multifold_edges"),
                 "native": native.get("n_multifold_edges"),
                 "kind": "invariant",
                 "match": host.get("n_multifold_edges") == 0
                 and native.get("n_multifold_edges") == 0})
    ok = ok and rows[-1]["match"]
    rows.append({"field": "FluidRegion volume region",
                 "host": "FluidRegion" in host.get("volume_regions", []),
                 "native": "FluidRegion" in native.get("volume_regions", []),
                 "kind": "invariant",
                 "match": "FluidRegion" in host.get("volume_regions", [])
                 and "FluidRegion" in native.get("volume_regions", [])})
    ok = ok and rows[-1]["match"]
    for key in DENSITY_KEYS:
        rows.append({"field": key, "host": host.get(key),
                     "native": native.get(key), "kind": "density",
                     "match": None})
    return {"ok": ok, "rows": rows}


def format_table(rep: dict) -> list[str]:
    lines = ["field | host | native | kind | match",
             "---|---|---|---|---"]
    for r in rep["rows"]:
        m = "—" if r["match"] is None else ("OK" if r["match"] else "FAIL")
        lines.append(f"{r['field']} | {r['host']} | {r['native']} | "
                     f"{r['kind']} | {m}")
    lines.append("VERDICT: " + ("PASS" if rep["ok"] else "FAIL"))
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="BAM report reconciliation")
    ap.add_argument("--host", default=str(ROOT / "p12a_bam_e2e_part.mdl"))
    ap.add_argument("--xt", default=str(ROOT / "tests" / "box" / "box.x_t"))
    ap.add_argument("--json", default=None)
    args = ap.parse_args(argv)

    host = host_mdl_facts(args.host)
    try:
        native = native_facts(args.xt)
    except SystemExit:
        raise
    except Exception as exc:  # pskernel 缺失等环境
        print(f"native facet path unavailable: {exc}")
        return 2
    rep = reconcile(host, native)
    out = {"host": host, "native": native, "reconcile": rep}
    for ln in format_table(rep):
        print(ln)
    if args.json:
        Path(args.json).write_text(
            json.dumps(out, ensure_ascii=False, indent=1),
            encoding="utf-8")
        print("json: " + args.json)
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
