#!/usr/bin/env python3
"""R17-1：本仓重写 GPH 成员的工程 vs 宿主原生工程 —— 求解对照腿。

官方 exA06-2_d_50 只带 meshinggroup1.gph + _ridge.mdl（无 _part.mdl/.oct），
故对照腿的重写对象 = **GPH**（本仓写端；P2 已证字节保真）。
"""
from __future__ import annotations

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

WORK = ROOT / "_p12u_gate" / "r17_ours"
BASE = Path(r"D:\training\cradle\CradleCFD_2025.2_scFLOW_Example_a") / "Exercise" / "exA06" / "exA06-2" / "Org" / "exA06-2_d_50.pph"
NATIVE_FPH = ROOT / "_p12u_gate" / "r16_dual" / "leg1" / "exA06-2_d_50_139.fph"
MEMBER = "meshinggroup1.gph"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    out = {"base": str(BASE), "native_fph": str(NATIVE_FPH), "member": MEMBER}
    hrc = _load("hrc_r171", ROOT / "tools" / "host_reopen_check.py")
    with zipfile.ZipFile(BASE) as z:
        raw = z.read(MEMBER)
    src_member = WORK / "orig.gph"
    src_member.write_bytes(raw)
    new_member = WORK / "rewritten.gph"
    hrc._rewrite_gph(src_member, new_member)
    out["member_bytes"] = [len(raw), new_member.stat().st_size]
    ours = WORK / "ours.pph"
    pphwriter.clone_pph(str(BASE), str(ours),
                        {MEMBER: new_member.read_bytes()})
    out["ours_pph"] = str(ours)
    print("[r17-1] gph", out["member_bytes"], "->", ours.stat().st_size, "B",
          flush=True)
    t0 = time.time()
    res = solver_run.run_solve(str(ours), str(WORK), wait_timeout=1500.0,
                               vbs_timeout=1800.0)
    out["run_ok"] = bool((res or {}).get("ok")) if isinstance(res, dict) else None
    fphs = sorted(str(p) for p in WORK.glob("*.fph"))
    out["ours_fph"] = fphs[-1] if fphs else None
    out["seconds"] = round(time.time() - t0, 1)
    print("[r17-1] ours fph =", out["ours_fph"], flush=True)
    if out["ours_fph"] and NATIVE_FPH.is_file():
        rep = solver_delta.compare_fph(NATIVE_FPH, out["ours_fph"])
        gate = solver_delta.gate_fph(rep)
        out.update({"zero_field": rep.get("zero_field"),
                    "primary_nonzero": rep.get("primary_nonzero"),
                    "n_fields": len(rep.get("fields") or {}),
                    "gate_ok": gate.get("ok"), "n_fail": gate.get("n_fail"),
                    "gate_reason": gate.get("reason")})
        (WORK / "delta_native_vs_ours.json").write_text(
            json.dumps({"rep": rep, "gate": gate}, ensure_ascii=False,
                       indent=2, default=str), encoding="utf-8")
        (WORK / "delta_native_vs_ours.md").write_text(
            solver_delta.delta_table_markdown(
                rep, title="R17-1 native vs our-GPH FPH"), encoding="utf-8")
    (WORK / "summary.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    print("[r17-1] " + json.dumps(
        {k: out.get(k) for k in ("zero_field", "primary_nonzero", "gate_ok",
                                 "n_fail", "gate_reason", "seconds",
                                 "run_ok")}, ensure_ascii=False), flush=True)
    return 0 if out.get("ours_fph") else 1


if __name__ == "__main__":
    raise SystemExit(main())
