#!/usr/bin/env python3
"""R18-1：对照腿（本仓重写成员的工程 → 求解 → 与宿主原生 FPH 对拍）。

把 R17 的一次性脚本固化为正式工具。链路：

  1. 取宿主原生工程的网格成员（默认 meshinggroup1.gph）；
  2. 用**本仓写端**重写（host_reopen_check._rewrite_gph = gphstats 读→写），clone_pph 回注；
  3. 用该工程跑一次求解（automation.solver_run.run_solve）；
  4. 与原生腿 FPH 对拍（solver_delta.compare_fph + gate_fph，带零流场判据）。

R17 实测结论（官方 exA06-2_d_50）：zero_field=false、gate_ok=true、n_fail=0 ——
主变量逐点一致（容差 0 = 逐位复现线）。

用法::

    python tools/solver_leg_ours.py --base <official.pph> --native-fph <native.fph>
    python tools/solver_leg_ours.py --base box.pph --member meshinggroup1.gph
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console_utf8

console_utf8.enable()

import pphwriter
import solver_delta
from automation import solver_run

DEFAULT_BASE = (Path(r"D:\training\cradle\CradleCFD_2025.2_scFLOW_Example_a")
                / "Exercise" / "exA06" / "exA06-2" / "Org" / "exA06-2_d_50.pph")
DEFAULT_NATIVE = (ROOT / "_p12u_gate" / "r16_dual" / "leg1"
                  / "exA06-2_d_50_139.fph")
REWRITERS = {"meshinggroup1.gph": "_rewrite_gph",
             "meshinggroup1.oct": "_rewrite_oct",
             "meshinggroup1_part.mdl": "_rewrite_mdl"}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def build_ours(base: Path, member: str, work: Path) -> Path:
    """重写 member 并用 clone_pph 回注，返回对照工程路径。"""
    hrc = _load("hrc_leg_ours", ROOT / "tools" / "host_reopen_check.py")
    fn = getattr(hrc, REWRITERS.get(member, "_rewrite_gph"))
    with zipfile.ZipFile(base) as z:
        raw = z.read(member)
    src_member = work / "orig_member.bin"
    src_member.write_bytes(raw)
    new_member = work / "rewritten_member.bin"
    fn(src_member, new_member)
    ours = work / "ours.pph"
    pphwriter.clone_pph(str(base), str(ours),
                        {member: new_member.read_bytes()})
    return ours


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R18-1 对照腿")
    ap.add_argument("--base", type=Path, default=DEFAULT_BASE)
    ap.add_argument("--member", default="meshinggroup1.gph")
    ap.add_argument("--native-fph", type=Path, default=DEFAULT_NATIVE)
    ap.add_argument("--work", type=Path,
                    default=ROOT / "_p12u_gate" / "r18_leg_ours")
    ap.add_argument("--wait-timeout", type=float, default=1500.0)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)
    base = Path(args.base)
    if not base.is_file():
        print("SUMMARY: " + json.dumps({"passed": False,
                                        "error": "base missing"}))
        return 1
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    out = {"base": str(base), "member": args.member,
           "native_fph": str(args.native_fph), "ok": False}
    t0 = time.time()
    ours = build_ours(base, args.member, work)
    out["ours_pph"] = str(ours)
    res = solver_run.run_solve(str(ours), str(work),
                               wait_timeout=args.wait_timeout)
    out["run_ok"] = bool((res or {}).get("ok")) if isinstance(res, dict) \
        else None
    fphs = sorted(str(p) for p in work.glob("*.fph"))
    out["ours_fph"] = fphs[-1] if fphs else None
    native = Path(args.native_fph)
    if out["ours_fph"] and native.is_file():
        rep = solver_delta.compare_fph(native, out["ours_fph"])
        gate = solver_delta.gate_fph(rep)
        out.update({"zero_field": rep.get("zero_field"),
                    "primary_nonzero": rep.get("primary_nonzero"),
                    "n_fields": len(rep.get("fields") or {}),
                    "gate_ok": gate.get("ok"), "n_fail": gate.get("n_fail"),
                    "gate_reason": gate.get("reason"),
                    "ok": bool(gate.get("ok"))})
        (work / "delta.json").write_text(
            json.dumps({"rep": rep, "gate": gate}, ensure_ascii=False,
                       indent=2, default=str), encoding="utf-8")
        (work / "delta.md").write_text(
            solver_delta.delta_table_markdown(
                rep, title="native vs our-" + args.member), encoding="utf-8")
    out["seconds"] = round(time.time() - t0, 1)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(out, ensure_ascii=False, indent=2,
                                        default=str), encoding="utf-8")
    print("[r18-1] " + json.dumps(
        {k: out.get(k) for k in ("zero_field", "primary_nonzero", "gate_ok",
                                 "n_fail", "seconds", "run_ok",
                                 "ours_fph")}, ensure_ascii=False), flush=True)
    print("SUMMARY: " + json.dumps({"passed": out["ok"]}, ensure_ascii=False))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
