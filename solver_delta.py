#!/usr/bin/env python3
"""P12-K Sprint I5：FPH/FLD/iFLD 数值等价对拍（首版 recorded-only）。

口径（DEV_PLAN §20.1-I5 / §20.2）：同案例双跑的逐变量容差表——
``max/mean delta`` 先记录后判定，首版只入册不设通过线。

* FPH ↔ FPH：:func:`compare_fph` 按 fields 键对齐逐变量对拍；
  同 shape 逐点 ``max|a-b|`` / ``mean|a-b|``，shape 不齐只记分布级
  （min/max/mean 差）并标 ``pointwise=False``。
* FLD ↔ FLD：:func:`compare_fld` 经 :mod:`fldstats` 求结构摘要
  （顶点/单元/场节）差。
* iFLD ↔ iFLD：:func:`compare_ifld` 经 :mod:`ifld` 目录对拍。
* 求解器输入面：:func:`sph_fingerprint`（md5 + 大小）供 sph 导出
  与官方自带 sph 的字节级对拍记录。

CLI：``python solver_delta.py --a A.fph --b B.fph [--json OUT]``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import crdlfld  # noqa: E402
import fph  # noqa: E402


def _load_fph_fields(path: str | Path) -> dict:
    """读 FPH → {字段名: (n_cells, values_f32)}（values 取首个非空）。"""
    data, handles = crdlfld.open_buffer(str(path))
    try:
        mesh = fph.parse_fph(data)
    finally:
        if handles is not None:
            mm, f = handles
            mm.close()
            f.close()
    out = {}
    for name, fld in (mesh.get("fields") or {}).items():
        vals = None
        for kind, arr in fld["arrays"]:
            if kind == "values" and arr.size:
                vals = fph.as_f32(arr)
                break
        out[name] = {
            "n": int(vals.size) if vals is not None else 0,
            "values": vals,
            "kind": fld["kind"],
            "target": fld["target"],
        }
    return out


def compare_fph(path_a: str | Path, path_b: str | Path) -> dict:
    """FPH 逐变量对拍（先记录后判定：不设通过线）。"""
    pa, pb = Path(path_a), Path(path_b)
    rep: dict = {
        "a": str(pa), "b": str(pb),
        "a_size": pa.stat().st_size if pa.is_file() else None,
        "b_size": pb.stat().st_size if pb.is_file() else None,
        "fields": {}, "only_a": [], "only_b": [], "ok": True,
    }
    if not pa.is_file() or not pb.is_file():
        rep["ok"] = False
        rep["reason"] = "missing file"
        return rep
    try:
        fa = _load_fph_fields(pa)
        fb = _load_fph_fields(pb)
    except Exception as exc:  # noqa: BLE001
        rep["ok"] = False
        rep["reason"] = f"parse failed: {exc!r}"
        return rep
    if not fa and not fb:
        rep["ok"] = False
        rep["reason"] = "no fields parsed (not an FPH?)"
        return rep
    ka, kb = set(fa), set(fb)
    rep["only_a"] = sorted(ka - kb)
    rep["only_b"] = sorted(kb - ka)
    for name in sorted(ka & kb):
        va, vb = fa[name]["values"], fb[name]["values"]
        entry: dict = {"n_a": fa[name]["n"], "n_b": fb[name]["n"],
                       "pointwise": False}
        if va is not None and va.size:
            entry.update(a_min=float(np.nanmin(va)),
                         a_max=float(np.nanmax(va)),
                         a_mean=float(np.nanmean(va)))
        if vb is not None and vb.size:
            entry.update(b_min=float(np.nanmin(vb)),
                         b_max=float(np.nanmax(vb)),
                         b_mean=float(np.nanmean(vb)))
        if (va is not None and vb is not None and va.shape == vb.shape
                and va.size):
            d = np.abs(va.astype(np.float64) - vb.astype(np.float64))
            fin = np.isfinite(d)
            entry["pointwise"] = True
            entry["delta_max"] = float(d[fin].max()) if fin.any() else 0.0
            entry["delta_mean"] = (float(d[fin].mean())
                                   if fin.any() else 0.0)
            scale = max(abs(entry.get("a_max", 0.0)),
                        abs(entry.get("b_max", 0.0)))
            entry["delta_rel"] = (entry["delta_max"] / scale
                                  if scale > 0 else 0.0)
        elif va is not None and vb is not None:
            entry["shape_mismatch"] = [list(va.shape), list(vb.shape)]
        rep["fields"][name] = entry
    return rep


def compare_fld(path_a: str | Path, path_b: str | Path) -> dict:
    """FLD 结构级对拍（fldstats 摘要差；recorded-only）。"""
    import fldstats

    rep: dict = {"a": str(path_a), "b": str(path_b), "ok": True}
    try:
        sa = fldstats.summarize_fld_file(path_a)
        sb = fldstats.summarize_fld_file(path_b)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"parse failed: {exc!r}"}
    rep["a_summary"] = sa
    rep["b_summary"] = sb
    for key in ("n_vertices", "n_cells"):
        va, vb = sa.get(key), sb.get(key)
        if va is not None and vb is not None:
            rep[f"{key}_delta"] = int(vb) - int(va)
    return rep


def compare_ifld(path_a: str | Path, path_b: str | Path) -> dict:
    """iFLD 目录级对拍（TOC 条目名/大小差；recorded-only）。"""
    import ifld

    rep: dict = {"a": str(path_a), "b": str(path_b), "ok": True,
                 "only_a": [], "only_b": [], "size_delta": {}}
    try:
        ta = {r.name: r.size for r in ifld.parse_toc(
            Path(path_a).read_bytes())}
        tb = {r.name: r.size for r in ifld.parse_toc(
            Path(path_b).read_bytes())}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"parse failed: {exc!r}"}
    rep["only_a"] = sorted(set(ta) - set(tb))
    rep["only_b"] = sorted(set(tb) - set(ta))
    for name in sorted(set(ta) & set(tb)):
        if ta[name] != tb[name]:
            rep["size_delta"][name] = int(tb[name]) - int(ta[name])
    return rep


def sph_fingerprint(path: str | Path) -> dict:
    """sph 字节指纹（导出 vs 官方自带 sph 的对拍记录）。"""
    p = Path(path)
    if not p.is_file():
        return {"path": str(p), "exists": False}
    data = p.read_bytes()
    return {"path": str(p), "exists": True, "size": len(data),
            "md5": hashlib.md5(data).hexdigest()}


def delta_table_markdown(rep: dict, title: str = "FPH delta table") -> str:
    """对拍报告 → markdown 逐变量表（recorded-only，无通过线）。"""
    lines = [f"## {title}", ""]
    lines.append(f"- a: `{rep.get('a')}` ({rep.get('a_size')} B)")
    lines.append(f"- b: `{rep.get('b')}` ({rep.get('b_size')} B)")
    if rep.get("only_a"):
        lines.append(f"- only in a: {', '.join(rep['only_a'])}")
    if rep.get("only_b"):
        lines.append(f"- only in b: {', '.join(rep['only_b'])}")
    lines.append("")
    lines.append("| field | n_a | n_b | pointwise | delta_max | "
                 "delta_mean | delta_rel | a_mean | b_mean |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for name, e in rep.get("fields", {}).items():
        lines.append(
            "| {f} | {na} | {nb} | {pw} | {dmx} | {dmn} | {drl} "
            "| {am} | {bm} |".format(
                f=name, na=e.get("n_a"), nb=e.get("n_b"),
                pw=str(e.get("pointwise")),
                dmx=_fmt(e.get("delta_max")),
                dmn=_fmt(e.get("delta_mean")),
                drl=_fmt(e.get("delta_rel")),
                am=_fmt(e.get("a_mean")), bm=_fmt(e.get("b_mean"))))
    lines.append("")
    return "\n".join(lines)


def _fmt(v):
    if v is None:
        return "n/a"
    return f"{v:.6g}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="I5 FPH/FLD/iFLD delta")
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--kind", choices=("fph", "fld", "ifld"),
                    default="fph")
    ap.add_argument("--json", default=None)
    ap.add_argument("--md", default=None)
    args = ap.parse_args(argv)
    fn = {"fph": compare_fph, "fld": compare_fld,
          "ifld": compare_ifld}[args.kind]
    rep = fn(args.a, args.b)
    print(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
    if args.kind == "fph":
        if args.md:
            Path(args.md).write_text(
                delta_table_markdown(rep), encoding="utf-8")
    if args.json:
        Path(args.json).write_text(
            json.dumps(rep, ensure_ascii=False, indent=1, default=str),
            encoding="utf-8")
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
