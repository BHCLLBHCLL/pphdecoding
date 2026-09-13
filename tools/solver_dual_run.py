#!/usr/bin/env python3
"""R16-2：50 Pa 双跑的窗口化分段驱动（可断点续跑）。

背景：数值等价（R10-1/R11-1/R13-2/R14-2/R15-2）连续多轮拿不到 ≥1 h 连续实机窗口。
本工具把双跑拆成三段，每段独立冷启动、独立入册：

  leg1   官方 50 Pa 算例跑一腿 → 取 FPH 指纹入册
  leg2   再跑一腿（独立会话）→ 取 FPH 指纹入册
  delta  两腿 FPH 对拍（solver_delta，带 zero_field 判据）→ md + json

任一段单独跑完都能入册；中断只丢当前段。默认算例 = 本机 2025.2 官方样本
exA06-2_d_50.pph（50 Pa 变体）。

用法::

    python tools/solver_dual_run.py leg1            # 第一段
    python tools/solver_dual_run.py leg2            # 第二段
    python tools/solver_dual_run.py delta           # 对拍
    python tools/solver_dual_run.py status          # 看各段落册情况
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console_utf8  # noqa: E402

console_utf8.enable()

import solver_delta  # noqa: E402
from automation import solver_run  # noqa: E402

WORK = ROOT / "_p12u_gate" / "r16_dual"
CASES = [
    Path(r"D:\training\cradle\CradleCFD_2025.2_scFLOW_Example_a")
    / "Exercise" / "exA06" / "exA06-2" / "Org" / "exA06-2_d_50.pph",
    Path(r"D:\training\cradle\CradleCFD_2023.2_scFLOW_Example")
    / "Exercise" / "exA06" / "exA06-2" / "Org" / "exA06-2_d_50.pph",
]
LEGS = ("leg1", "leg2")


def case_pph() -> Path | None:
    for p in CASES:
        if p.is_file():
            return p
    return None


def stage_path(leg: str) -> Path:
    return WORK / (leg + ".json")


def run_leg(leg: str, *, wait_timeout: float = 1800.0,
            vbs_timeout: float = 3600.0) -> dict:
    src = case_pph()
    if src is None:
        return {"ok": False, "stage": leg,
                "error": "官方 50 Pa 算例未找到（exA06-2_d_50.pph）"}
    WORK.mkdir(parents=True, exist_ok=True)
    work = WORK / leg
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    pph = work / src.name
    shutil.copyfile(src, pph)
    out = {"stage": leg, "src": str(src), "work": str(work),
           "pph": str(pph), "ok": False}
    t0 = time.time()
    try:
        res = solver_run.run_solve(str(pph), str(work),
                                   wait_timeout=wait_timeout,
                                   vbs_timeout=vbs_timeout)
        out["run"] = res if isinstance(res, dict) else {"raw": str(res)[:400]}
        out["ok"] = bool((res or {}).get("ok")) if isinstance(res, dict) else False
    except Exception as exc:  # noqa: BLE001
        out["error"] = type(exc).__name__ + ": " + str(exc)
    arts = []
    try:
        arts = solver_run.find_solver_artifacts(case=work.name)
    except Exception:  # noqa: BLE001
        pass
    fphs = [str(a) for a in (arts or []) if str(a).endswith(".fph")]
    if not fphs:
        fphs = [str(p) for p in work.glob("*.fph")]
    out["fph"] = sorted(fphs)[-1] if fphs else None
    if out["fph"]:
        try:
            out["verify"] = solver_run.verify_fph_file(out["fph"])
        except Exception as exc:  # noqa: BLE001
            out["verify_error"] = type(exc).__name__ + ": " + str(exc)
    out["seconds"] = round(time.time() - t0, 1)
    stage_path(leg).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    return out


def stage_delta() -> dict:
    legs = {}
    for leg in LEGS:
        p = stage_path(leg)
        if p.is_file():
            legs[leg] = json.loads(p.read_text(encoding="utf-8"))
    out = {"stage": "delta", "legs": {k: v.get("fph") for k, v in legs.items()}}
    a, b = (legs.get("leg1", {}).get("fph"), legs.get("leg2", {}).get("fph"))
    if not (a and b):
        out["ok"] = False
        out["error"] = "两腿 FPH 未齐（先跑 leg1/leg2）"
    else:
        rep = solver_delta.compare_fph(a, b)
        gate = solver_delta.gate_fph(rep)
        out.update({"ok": bool(gate.get("ok")),
                    "zero_field": rep.get("zero_field"),
                    "primary_nonzero": rep.get("primary_nonzero"),
                    "n_fields": len(rep.get("fields") or {}),
                    "gate_ok": gate.get("ok"),
                    "gate_reason": gate.get("reason")})
        (WORK / "delta_table.md").write_text(
            solver_delta.delta_table_markdown(rep, gate=gate),
            encoding="utf-8")
        (WORK / "delta_table.json").write_text(
            json.dumps({"rep": rep, "gate": gate}, ensure_ascii=False,
                       indent=2, default=str), encoding="utf-8")
    (WORK / "delta.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R16-2 50 Pa 双跑分段驱动")
    ap.add_argument("stage", choices=("leg1", "leg2", "leg-ours", "delta",
                                     "status"))
    ap.add_argument("--wait-timeout", type=float, default=1800.0)
    ap.add_argument("--vbs-timeout", type=float, default=3600.0)
    args = ap.parse_args(argv)
    if args.stage == "status":
        st = {"case": str(case_pph()),
              "stages": {leg: stage_path(leg).is_file() for leg in LEGS},
              "delta": (WORK / "delta.json").is_file()}
        print(json.dumps(st, ensure_ascii=False, indent=1))
        return 0
    if args.stage in LEGS:
        res = run_leg(args.stage, wait_timeout=args.wait_timeout,
                      vbs_timeout=args.vbs_timeout)
    else:
        res = stage_delta()
    print(json.dumps({k: res.get(k) for k in
                      ("stage", "ok", "fph", "zero_field",
                       "primary_nonzero", "gate_ok", "gate_reason",
                       "seconds", "error")}, ensure_ascii=False), flush=True)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
