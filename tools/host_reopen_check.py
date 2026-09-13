#!/usr/bin/env python3
"""R1-7：写端宿主回读验收 harness（MDL / OCT / GPH / PPH 四类）。

把 R0 期一次性脚本（_p2_accept）产品化：给定一个宿主工程，按类别把成员
用**本仓写端**重写后回注，再交给宿主 OpenProject 探针（SNode / MeshingGroup /
GetMDL / DoesMeshExist / bbox），输出 JSON 证据。

用法：
    python tools/host_reopen_check.py                         # 四类全跑
    python tools/host_reopen_check.py --cases pph,gph         # 指定类别
    python tools/host_reopen_check.py --base <base.pph> --json out.json

前置：Cradle 已安装且宿主可经 Kicker 冷启动（无宿主时本工具不可用，属设计使然）。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import gphstats  # noqa: E402
import mdl  # noqa: E402
import oct as octmod  # noqa: E402
import pphwriter  # noqa: E402
import automation.host_boot as host_boot  # noqa: E402

DEFAULT_BASE = ROOT / "_p12a_e2e" / "box.pph"
MEMBERS = ("meshinggroup1_part.mdl", "meshinggroup1.oct", "meshinggroup1.gph")
CASES = {
    "pph": (),                       # 纯容器往返（不改成员）
    "mdl": ("meshinggroup1_part.mdl",),
    "oct": ("meshinggroup1.oct",),
    "gph": ("meshinggroup1.gph",),
    "all": MEMBERS,
}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _date_of(data: bytes) -> int:
    """从 CRDL-FLD 的 Date 节读 I4（回填后往返零差异）。"""
    name = b"Date" + b" " * 28
    i = data.find(name)
    if i < 4:
        return 20260812
    import struct
    return struct.unpack_from(">i", data, i + 36 + 16 + 8)[0]


def _rewrite_mdl(src: Path, dst: Path) -> None:
    raw = src.read_bytes()
    m = mdl.parse_mdl(src)
    faces = [m.face_nodes(i) for i in range(m.n_faces)]
    b1, b2 = m.csid_sides
    mdl.write_mdl(dst, m.xyz, faces, csid=(b1, b2), frid=m.frid,
                  edge_state=m.edge_state, node_state=m.node_state,
                  date=_date_of(raw),
                  surface_regions=[(r.name, r.index)
                                   for r in (m.surface_regions or [])] or None,
                  closed_volumes=getattr(m, "closed_volumes", None),
                  volume_regions=getattr(m, "volume_regions", None))


def _rewrite_oct(src: Path, dst: Path) -> None:
    raw = src.read_bytes()
    m = octmod.parse_oct(src)
    octmod.write_oct(dst, m.root_min, m.root_max, refinement=m.refinement,
                     block_id=m.block_id, unit=m.unit or "m",
                     date=_date_of(raw))


def _rewrite_gph(src: Path, dst: Path) -> None:
    raw = src.read_bytes()
    mesh = gphstats.parse_mesh(raw)
    fo = np.asarray(mesh["face_offsets"])
    faces = [np.asarray(mesh["conn"][fo[i]:fo[i + 1]])
             for i in range(len(fo) - 1)]
    cvol = gphstats.cvol_ids(raw)
    info = gphstats.element_info(raw)
    gphstats.write_gph_volume(
        dst, mesh["vertices"], faces, mesh["owner"], mesh["neigh"],
        app="SCTpre", date=_date_of(raw), cvol=cvol,
        surface_regions=[(n, ids) for n, ids
                         in gphstats.surface_region_face_ids(raw).items()] or None,
        volume_regions=gphstats.volume_region_names(raw) or None,
        parts=gphstats.parts_summary(raw, cvol) or None,
        assemblies=gphstats.assemblies_xml(raw),
        element_info=(info[1] if info else None))


REWRITERS = {"meshinggroup1_part.mdl": _rewrite_mdl,
             "meshinggroup1.oct": _rewrite_oct,
             "meshinggroup1.gph": _rewrite_gph}


def build_case(base: Path, case: str, work: Path) -> Path:
    """按 case 生成变体工程（members 用本仓写端重写后回注）。"""
    override_names = CASES[case]
    if not override_names:
        out = work / f"{case}.pph"
        pphwriter.clone_pph(str(base), str(out), None)
        return out
    overrides = {}
    with zipfile.ZipFile(base) as z:
        for name in override_names:
            tmp = work / f"src_{name}"
            tmp.write_bytes(z.read(name))
            dst = work / f"ours_{name}"
            REWRITERS[name](tmp, dst)
            overrides[name] = dst.read_bytes()
    out = work / f"{case}.pph"
    pphwriter.clone_pph(str(base), str(out), overrides)
    return out


def probe_actions(pph: Path, out_pph: Path) -> list[str]:
    p12m = _load("p12m_run", ROOT / "tools" / "_p12m_j1_run.py")
    return [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        "RetWW0_ = Doc_.WaitForWorker",
        f'Doc_.OpenProject "{pph.as_posix()}", False',
        "RetWW1_ = Doc_.WaitForWorker",
        'Set SN_ = Doc_.QuerySNodeByName("Part")',
        "Set MG_ = Doc_.QueryMeshingGroupByIndex(0)",
        "Set MDL_ = MG_.GetMDL",
        "Set OCT_ = MG_.GetOctree",
        p12m._w("mesh_exists", "MG_.DoesMeshExist"),
        "Param1_ = False",
        "Doc_.GetAllPartsBoundingBox BBox_, False",
        'If IsArray(BBox_) Then out_.WriteLine "bbox_ub=" & CStr(UBound(BBox_)) '
        '& " b0=" & CStr(BBox_(0)) & " bL=" & CStr(BBox_(UBound(BBox_))) '
        '& " err=" & CStr(Err.Number) Else out_.WriteLine "bbox=NA" ',
        "Err.Clear",
        "Parts_ = Doc_.GetSParts(False, False, False)",
    ] + p12m._ubound_guard("Parts_") + [
        f'Doc_.SaveProject "{out_pph.as_posix()}"',
    ]


def run_case(p12e, name: str, pph: Path, work: Path, log_dir: Path) -> dict:
    out_pph = work / f"{name}_out.pph"
    vbs = log_dir / f"r1_{name}.vbs"
    log = log_dir / f"r1_{name}.log"
    if log.is_file():
        log.unlink()
    groups = [(name, probe_actions(pph, out_pph))]
    p12e._write_ansi_vbs(p12e.logged_script(groups, log, f"R1-7 {name}"),
                         vbs, f"R1-7 {name}")
    t0 = time.time()
    try:
        p12e.run_e2e(name, vbs, log, timeout=900.0, retry_with_boot=True)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    ver = p12e.verify_log(text)
    alive = ver.get("alive", {})
    bbox = re.search(r"^bbox.*$", text, re.MULTILINE)
    checks = {
        "has_end": ver.get("has_end"),
        "err0": ver.get("err0"),
        "total": ver.get("total"),
        "sn_alive": alive.get("sn_"),
        "mg_alive": alive.get("mg_"),
        "mdl_alive": alive.get("mdl_"),
        "oct_alive": alive.get("oct_"),
    }
    m = re.search(r"mesh_exists=(\w+)", text)
    checks["mesh_exists"] = m.group(1) if m else None
    checks["bbox"] = bbox.group(0) if bbox else None
    ok = (
        checks["has_end"]
        and checks["err0"] == checks["total"]
        and checks["mg_alive"] == "True"
    )
    if name in ("mdl", "all"):
        ok = ok and checks["mdl_alive"] == "True"
    if name in ("oct", "all"):
        ok = ok and checks["oct_alive"] == "True"
    if name in ("gph", "all"):
        ok = ok and checks["mesh_exists"] == "True"
    return {"ok": bool(ok), "seconds": round(time.time() - t0, 1),
            "checks": checks}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R1-7 宿主编译回读验收")
    ap.add_argument("--base", type=Path, default=DEFAULT_BASE)
    ap.add_argument("--cases", default="pph,mdl,oct,gph,all")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--work", type=Path, default=ROOT / "_p12u_reopen")
    args = ap.parse_args(argv)
    if not args.base.is_file():
        print(json.dumps({"error": f"base pph missing: {args.base}"}))
        return 1
    cases = [c.strip() for c in args.cases.split(",") if c.strip()]
    for c in cases:
        if c not in CASES:
            print(json.dumps({"error": f"unknown case {c}; use {list(CASES)}"}))
            return 2
    args.work.mkdir(parents=True, exist_ok=True)
    p12e = _load("p12e_run", ROOT / "tools" / "_p12e_e2e_run.py")
    pid = host_boot.cold_boot()
    print(f"[r1-7] fresh host pid={pid}", flush=True)
    results: dict = {}
    for case in cases:
        pph = build_case(args.base, case, args.work)
        res = run_case(p12e, case, pph, args.work, args.work)
        results[case] = res
        print(f"[{case}] " + json.dumps(res, ensure_ascii=False), flush=True)
    summary = {"base": str(args.base), "cases": results,
               "passed": sum(1 for r in results.values() if r.get("ok")),
               "total": len(results)}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print("SUMMARY: " + json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
