#!/usr/bin/env python3
"""R2-1 诊断：MeshingGroup.CreateMesh 前置条件探查（x_t 腿）。

目的：R1-3 gate 里 ``MG2_.CreateMesh`` 返回 False 且 ``DoesMeshExist=False``。
本探针在**同一条宿主会话**里把可利用的状态量全部打印出来（meshing group
setting 的 mesher/MDL method、OctParam 回读值、octree 存在性、当前 mode、
active meshing group、SetActiveMeshingGroup 前后、worker 状态、第二次查询
的结果），用于定位 CreateMesh 未生效的真实前置条件。

用法：python tools/_r21_mesh_probe.py [--json out.json]
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

import automation.host_boot as host_boot  # noqa: E402

WORK = ROOT / "_p12u_gate"
XT = ROOT / "tests" / "box" / "box.x_t"
Q = chr(34)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_actions(xt: Path, out_pph: Path) -> list[str]:
    p12m = _load("p12m_run", ROOT / "tools" / "_p12m_j1_run.py")
    w = p12m._w

    def t(key: str, expr: str) -> str:
        # TypeName 型探针：对象/数组/空值都安全
        head = "out_.WriteLine " + Q + key + "=" + Q + " & TypeName(" + expr + ")"
        tail = " & " + Q + " err=" + Q + " & CStr(Err.Number)"
        return head + tail

    a = [
        "Set App_ = GetApplication()",
        "If App_ Is Nothing Then Set App_ = CreateObject(" + Q
        + "scFLOWpre_Bx64net.Application.2025" + Q + ")",
        "Set Doc_ = App_.GetDocument",
        "RetWW0_ = Doc_.WaitForWorker",
        "Set SN_ = Doc_.OpenCadFile(" + Q + xt.as_posix() + Q + ")",
        "RetWW1_ = Doc_.WaitForWorker",
        w("ret_mode_oct", "Doc_.SetModeOctree"),
        "Set MG_ = Doc_.CreateMeshingGroup",
        "Set MG2_ = Doc_.QueryMeshingGroupByIndex(0)",
        w("ret_bam", "Doc_.BuildAnalysisModel"),
        "RetWW2_ = Doc_.WaitForWorker",
        t("mgs_t", "MG2_.GetMeshingGroupSetting"),
        "Set MGS_ = MG2_.GetMeshingGroupSetting",
        t("mesher_t", "MGS_.GetMesher"),
        t("mdlmethod_t", "MGS_.GetMDLMethod"),
        t("surfmesher_t", "MGS_.GetSurfMesher"),
        w("facet_spec_type", "MGS_.GetFacetAccuracySpecificationType"),
        w("facet_simple", "MGS_.GetFacetUseSimpleSetting"),
        w("oct_exists0", "MG2_.DoesMeshingOctreeExist"),
        "Set OctParam_ = MG2_.GetOctParam",
        "RetInit_ = OctParam_.Initialize",
        w("opt_type0", "OctParam_.GetOctType"),
        "P1_ = 3",
        "OctParam_.SetOctType P1_",
        "P1_ = 10000",
        "OctParam_.SetMeshNum P1_",
        "P1_ = 0",
        "OctParam_.SetMinSize P1_",
        w("opt_type1", "OctParam_.GetOctType"),
        w("opt_num1", "OctParam_.GetMeshNum"),
        w("opt_min1", "OctParam_.GetMinSize"),
        w("ret_oct", "MG2_.CreateOctree"),
        "RetWW3_ = Doc_.WaitForWorker",
        w("oct_exists1", "MG2_.DoesMeshingOctreeExist"),
        t("oct_t", "MG2_.GetOctree"),
        w("groups_ub", "UBound(Doc_.GetMeshingGroups)"),
        t("amg_t", "Doc_.GetActiveMeshingGroup"),
        w("amb", "MG2_.IsAnalysisModelBuilt"),
        w("ret_setmode_mesh", "Doc_.SetModeMesh"),
        w("is_mode_oct_after", "Doc_.IsModeOctree"),
        w("ret_act", "Doc_.SetActiveMeshingGroup(0, 0)"),
        w("ret_mesh", "MG2_.CreateMesh"),
        "RetWW4_ = Doc_.WaitForWorker",
        w("mesh_exists", "MG2_.DoesMeshExist"),
        w("mesh_err", "MG2_.DoesMeshErrorExist"),
        w("ws", "Doc_.GetWorkerStateString"),
        "Set MG3_ = Doc_.QueryMeshingGroupByIndex(0)",
        w("mesh_exists2", "MG3_.DoesMeshExist"),
        "Doc_.SaveProject " + Q + out_pph.as_posix() + Q,
    ]
    return a


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R2-1 CreateMesh 前置条件探针")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--nocold", action="store_true",
                    help="跳过冷启动（复用已有宿主）")
    args = ap.parse_args(argv)
    WORK.mkdir(parents=True, exist_ok=True)
    p12e = _load("p12e_run", ROOT / "tools" / "_p12e_e2e_run.py")
    pid = None if args.nocold else host_boot.cold_boot()
    print("[r2-1] cold_boot pid=" + str(pid), flush=True)
    out_pph = WORK / "xt_probe.pph"
    vbs = WORK / "r21_probe.vbs"
    log = WORK / "r21_probe.log"
    if log.is_file():
        log.unlink()
    p12e._write_ansi_vbs(p12e.logged_script(
        [("r21", build_actions(XT, out_pph))], log, "R2-1 mesh probe"),
        vbs, "R2-1 mesh probe")
    t0 = time.time()
    err = None
    try:
        p12e.run_e2e("r21_probe", vbs, log, timeout=args.timeout,
                     retry_with_boot=True)
    except Exception as exc:  # noqa: BLE001
        err = type(exc).__name__ + ": " + str(exc)
    text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    ver = p12e.verify_log(text)
    print("---- raw log ----")
    print(text)
    print("---- verify ----")
    print(json.dumps({"err0": ver.get("err0"), "total": ver.get("total"),
                      "problems": ver.get("problems"),
                      "alive": ver.get("alive"),
                      "seconds": round(time.time() - t0, 1),
                      "error": err}, ensure_ascii=False, indent=1))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(
            {"err0": ver.get("err0"), "total": ver.get("total"),
             "problems": ver.get("problems"), "alive": ver.get("alive"),
             "error": err, "raw": text}, ensure_ascii=False, indent=2),
            encoding="utf-8")
    return 0 if err is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
