#!/usr/bin/env python3
"""R13-1 验证：把离线降版产物交给宿主 OpenCadFile。

`tools/xt_downgrade.py` 已能离线写出 Parasolid **v34** 的 x_t
（`transmit_version=340` → `SCH_3400000_340010`），而宿主接收端正是 v34。
本工具做最后一跳：宿主 `OpenCadFile` 该产物 → SNode 是否出现。

用法::

    python tools/xt_downgrade_host_check.py --json _p12u_gate/r13_1_host.json
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
DEFAULT = WORK / "r12_1_nw340.x_t"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def sch_of(p: Path):
    if not p.is_file():
        return None
    data = p.read_bytes()[:600].decode("latin-1")
    m = re.search(r"(SCH_\d+_\d+)", data)
    return m.group(1) if m else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R13-1 降版产物宿主验证")
    ap.add_argument("--xt", type=Path, default=DEFAULT)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)
    xt = args.xt.resolve()
    out = {"xt": str(xt), "sch": sch_of(xt)}
    if not xt.is_file():
        print("SUMMARY: " + json.dumps({"passed": False,
                                        "error": "xt missing"}))
        return 1
    p12e = _load("p12e_run_r131", ROOT / "tools" / "_p12e_e2e_run.py")
    p12m = _load("p12m_run_r131", ROOT / "tools" / "_p12m_j1_run.py")
    p12e.utf8_stdout()
    q = chr(34)
    pph = WORK / "r13_1_built.pph"
    acts = [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        "RetWW0_ = Doc_.WaitForWorker",
        "Set SN_ = Doc_.OpenCadFile(" + q + xt.as_posix() + q + ")",
        "RetWW1_ = Doc_.WaitForWorker",
        p12m._w("snode_alive", "Not (SN_ Is Nothing)"),
        "Set MG_ = Doc_.QueryMeshingGroupByIndex(0)",
        p12m._w("mg_alive", "Not (MG_ Is Nothing)"),
        "ret_bam_ = Doc_.BuildAnalysisModel",
        p12m._w("ret_bam", "ret_bam_"),
        "RetWW2_ = Doc_.WaitForWorker",
        "Set VMDL_ = MG_.GetVMDL",
        p12m._w("vmdl_alive", "Not (VMDL_ Is Nothing)"),
        "Doc_.GetAllPartsBoundingBox BBox_, False",
        'If IsArray(BBox_) Then out_.WriteLine "bbox=" & CStr(BBox_(0)) '
        '& "," & CStr(BBox_(3)) & " err=" & CStr(Err.Number) '
        'Else out_.WriteLine "bbox=NA" ',
        "Err.Clear",
        "Doc_.SaveProject " + q + pph.as_posix() + q,
    ]
    vbs = WORK / "r131_host.vbs"
    log = WORK / "r131_host.log"
    if log.is_file():
        log.unlink()
    p12e._write_ansi_vbs(
        p12e.logged_script([("r131", acts)], log, "R13-1 host check"),
        vbs, "R13-1 host check")
    import automation.host_boot as host_boot
    t0 = time.time()
    pid = host_boot.cold_boot()
    print("[r13-1] cold boot pid=" + str(pid), flush=True)
    err = None
    try:
        p12e.run_e2e("r131_host", vbs, log, timeout=900.0, idle_limit=600.0,
                     retry_with_boot=True)
    except Exception as exc:  # noqa: BLE001
        err = type(exc).__name__ + ": " + str(exc)
    text = (log.read_text(encoding="utf-8", errors="replace")
            if log.is_file() else "")
    ver = p12e.verify_log(text)
    out.update({"error": err, "err0": ver.get("err0"),
                "total": ver.get("total"), "alive": ver.get("alive"),
                "seconds": round(time.time() - t0, 1)})
    for key in ("snode_alive", "mg_alive", "ret_bam", "vmdl_alive"):
        m = re.search(key + r"=(\S+)", text)
        out[key] = m.group(1) if m else None
    m = re.search(r"^bbox=(\S+)$", text, re.MULTILINE)
    out["bbox"] = m.group(1) if m else None
    out["pph"] = str(pph) if pph.is_file() else None
    print("[r13-1] " + json.dumps({k: out.get(k) for k in
                                   ("sch", "snode_alive", "mg_alive",
                                    "ret_bam", "vmdl_alive", "bbox",
                                    "err0", "total", "error")},
                                  ensure_ascii=False), flush=True)
    out["passed"] = bool(err is None and out.get("snode_alive") == "True"
                         and ver.get("err0") == ver.get("total"))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print("SUMMARY: " + json.dumps({"passed": out["passed"],
                                     "snode": out.get("snode_alive")},
                                    ensure_ascii=False))
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
