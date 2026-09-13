#!/usr/bin/env python3
"""R11-2：宿主侧 x_t 导出（v34）—— CADthru 控版否证后的替代路线。

R9-2 判据：宿主接收端 Parasolid 是 v34（`SCH_3400153_34001`），CADthru 写的是 v37，
且 R10-2 已证 CADthru COM 无法控版。本工具试另一条：**让宿主自己导出 x_t**
（`Doc_.SaveXTFile`，用的是宿主自带的 Parasolid），再看：

  1. 导出物的 `SCH=` 是哪一版；
  2. 宿主能否**重新打开**这份导出物（`OpenCadFile` → SNode 在场）。

两条腿：宿主原生 `box.pph`（对照）与真 STEP（`key v2.step`）。

用法::

    python tools/host_xt_export_check.py --json _p12u_gate/r11_2_host_xt.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console_utf8  # noqa: E402

console_utf8.enable()

WORK = ROOT / "_p12u_gate"
BOX_PPH = ROOT / "box.pph"
STEP = Path(r"D:\training\3dprint\FunHome-main\funHomeFan\cad\FunDeskFan\key v2.step")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def sch_of(p: Path):
    if not p.is_file():
        return None
    data = p.read_bytes()[:1200].decode("latin-1")
    m = re.search(r"SCH=([^;\r\n]+);", data)
    return m.group(1) if m else None


def actions(box_pph: Path, step: Path, box_out: Path, step_out: Path,
            box_re: Path, step_re: Path) -> list:
    p12m = _load("p12m_run_r112", ROOT / "tools" / "_p12m_j1_run.py")
    q = chr(34)
    return [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        "RetWW0_ = Doc_.WaitForWorker",
        # 腿 1：宿主原生工程 → SaveXTFile
        "Doc_.OpenProject " + q + box_pph.as_posix() + q + ", False",
        "RetWW1_ = Doc_.WaitForWorker",
        "ret_save1_ = Doc_.SaveXTFile(" + q + box_out.as_posix() + q + ")",
        p12m._w("ret_save_box", "ret_save1_"),
        # 腿 1b：把导出物重新打开
        "Set SN1_ = Doc_.OpenCadFile(" + q + box_re.as_posix() + q + ")",
        "RetWW2_ = Doc_.WaitForWorker",
        p12m._w("reopen_box_sn", "Not (SN1_ Is Nothing)"),
        # 腿 2：真 STEP → SaveXTFile
        "Set SN2_ = Doc_.OpenCadFile(" + q + step.as_posix() + q + ")",
        "RetWW3_ = Doc_.WaitForWorker",
        "ret_save2_ = Doc_.SaveXTFile(" + q + step_out.as_posix() + q + ")",
        p12m._w("ret_save_step", "ret_save2_"),
        # 腿 2b：把导出物重新打开
        "Set SN3_ = Doc_.OpenCadFile(" + q + step_re.as_posix() + q + ")",
        "RetWW4_ = Doc_.WaitForWorker",
        p12m._w("reopen_step_sn", "Not (SN3_ Is Nothing)"),
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R11-2 宿主侧 x_t 导出")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)
    WORK.mkdir(parents=True, exist_ok=True)
    box_out = WORK / "r11_2_box_host.x_t"
    step_out = WORK / "r11_2_step_host.x_t"
    box_re = WORK / "r11_2_box_reopen.x_t"
    step_re = WORK / "r11_2_step_reopen.x_t"
    for p in (box_out, step_out, box_re, step_re):
        if p.is_file():
            p.unlink()
    p12e = _load("p12e_run_r112", ROOT / "tools" / "_p12e_e2e_run.py")
    p12e.utf8_stdout()
    import automation.host_boot as host_boot
    vbs = WORK / "r112_export.vbs"
    log = WORK / "r112_export.log"
    if log.is_file():
        log.unlink()
    p12e._write_ansi_vbs(
        p12e.logged_script([("r112", actions(BOX_PPH, STEP, box_out,
                                            step_out, box_re, step_re))],
                           log, "R11-2 host XT export"),
        vbs, "R11-2 host XT export")
    t0 = time.time()
    pid = host_boot.cold_boot()
    print("[r11-2] cold boot pid=" + str(pid), flush=True)
    err = None
    try:
        p12e.run_e2e("r112_export", vbs, log, timeout=900.0, idle_limit=600.0,
                     retry_with_boot=True)
    except Exception as exc:  # noqa: BLE001
        err = type(exc).__name__ + ": " + str(exc)
    text = (log.read_text(encoding="utf-8", errors="replace")
            if log.is_file() else "")
    ver = p12e.verify_log(text)
    out = {"error": err, "err0": ver.get("err0"), "total": ver.get("total"),
           "alive": ver.get("alive"), "seconds": round(time.time() - t0, 1)}
    for key in ("ret_save_box", "ret_save_step", "reopen_box_sn",
                "reopen_step_sn"):
        m = re.search(key + r"=(\S+)", text)
        out[key] = m.group(1) if m else None
    out["schemas"] = {
        "host_native_box_x_t": sch_of(ROOT / "tests" / "box" / "box.x_t"),
        "cadthru_keyv2": sch_of(WORK / "r8_3_keyv2.x_t"),
        "host_export_box": sch_of(box_out),
        "host_export_step": sch_of(step_out),
        "host_roundtrip_box": sch_of(box_re),
        "host_roundtrip_step": sch_of(step_re),
    }
    print("[r11-2] " + json.dumps(out, ensure_ascii=False), flush=True)
    ok = (err is None and ver.get("err0") == ver.get("total")
          and out["schemas"]["host_export_step"] is not None
          and out.get("reopen_step_sn") == "True")
    out["passed"] = bool(ok)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print("SUMMARY: " + json.dumps({"passed": out["passed"],
                                     "schemas": out["schemas"]},
                                    ensure_ascii=False))
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
