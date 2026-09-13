#!/usr/bin/env python3
"""R1-3 / R2-1：CAD 双格式（x_t / STEP）端到端 gate。

链路（三段会话）：

  1. ``build``   OpenCadFile → BuildAnalysisModel（BAM 面片）→ CreateOctree
                 → SaveProject
  2. ``mesh``    OpenProject(1 的产物) → QueryMeshingGroupByIndex(0) →
                 ``MG_.CreateMesh`` → WaitForWorker → DoesMeshExist
                 → SaveProject
  3. ``reopen``  OpenProject(2 的产物) → 全量探针（SNode / MeshingGroup /
                 GetMDL / GetVMDL / GetOctree / DoesMeshExist / bbox）

R2-1 根因（``tools/_r21_mesh_probe.py``，证据 ``_p12u_gate/r2_1_probe.json``，
84/84 err=0）：**同一会话内** ``BuildAnalysisModel`` 之后直接 ``CreateMesh``
恒定 False，且 ``DoesMeshErrorExist=True``（OctParam 怎么设都一样）；而历史
已验证配方 ``p12e_mesh_e2e.vbs`` 是 ``OpenProject``（BAM 已建）→
``CreateMesh`` → ``WaitForWorker=1`` → ``create_ret=True``，产物
``p12e_mesh_e2e_out.pph`` 被 R1-7 回读确认为 ``mesh_exists=True``。
故 mesh 腿必须拆成"先存盘、再重开工程建网格"的第二段会话。

用法：
    python tools/cad_pipeline_gate.py                      # x_t + STEP
    python tools/cad_pipeline_gate.py --cases xt           # 只跑 x_t
    python tools/cad_pipeline_gate.py --json out.json
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
STEP_DEFAULT = Path(r"D:\training\3dprint\FunHome-main\funHomeFan\cad\FunDeskFan\key v2.step")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _bbox_lines(var: str = "BBox_") -> list[str]:
    return [
        f"Doc_.GetAllPartsBoundingBox {var}, False",
        f'If IsArray({var}) Then out_.WriteLine "bbox=" & CStr({var}(0)) '
        f'& "," & CStr({var}(3)) & "," & CStr({var}(4)) & "," '
        f'& CStr({var}(5)) & " err=" & CStr(Err.Number) '
        'Else out_.WriteLine "bbox=NA" ',
        "Err.Clear",
    ]


def build_actions_full(cad: Path, out_pph: Path) -> list[str]:
    p12m = _load("p12m_run", ROOT / "tools" / "_p12m_j1_run.py")
    acts = [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        "RetWW0_ = Doc_.WaitForWorker",
        f'Set SN_ = Doc_.OpenCadFile("{cad.as_posix()}")',
        "RetWW1_ = Doc_.WaitForWorker",
        "Set MG_ = Doc_.CreateMeshingGroup",
        "If MG_ Is Nothing Then Set MG_ = Doc_.QueryMeshingGroupByIndex(0)",
    ] + _bbox_lines() + [
        "ret_bam_ = Doc_.BuildAnalysisModel",
        p12m._w("ret_bam", "ret_bam_"),
        "RetWW2_ = Doc_.WaitForWorker",
        # 注意：MG_.CreateVMDL 在本机实测抛 Err 91（Object variable not set），
        # 而 Doc_.BuildAnalysisModel 已返回 True；故改为直接取 BAM 产物。
        "Set MG2_ = Doc_.QueryMeshingGroupByIndex(0)",
        "Set VMDL_ = MG2_.GetVMDL",
        "Set MDL_ = MG2_.GetMDL",
        # octree 参数需先初始化（对齐录制：GetOctParam → Initialize → Set*）
        "Set OctParam_ = MG2_.GetOctParam",
        "OctParam_.Initialize",
        "Param1_ = 3",
        "OctParam_.SetOctType Param1_",
        "Param1_ = 10000",
        "OctParam_.SetMeshNum Param1_",
        "Param1_ = 0",
        "OctParam_.SetMinSize Param1_",
        "ret_oct_ = MG2_.CreateOctree",
        p12m._w("ret_oct", "ret_oct_"),
        "RetWW3_ = Doc_.WaitForWorker",
        "Set OCT_ = MG2_.GetOctree",
        # R2-1：本段**不再**调用 CreateMesh —— 同会话内它恒定 False 并留下
        # DoesMeshErrorExist=True（见 r2_1_probe.json）；网格改由 mesh 段
        # 在"重开工程"后生成。
        f'Doc_.SaveProject "{out_pph.as_posix()}"',
    ]
    return acts


def mesh_actions(pph: Path, out_pph: Path) -> list[str]:
    p12m = _load("p12m_run", ROOT / "tools" / "_p12m_j1_run.py")
    return [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        "RetWW0_ = Doc_.WaitForWorker",
        f'Doc_.OpenProject "{pph.as_posix()}", False',
        "RetWW1_ = Doc_.WaitForWorker",
        "Set MG_ = Doc_.QueryMeshingGroupByIndex(0)",
        "Set VMDL_ = MG_.GetVMDL",
        "ret_mesh_ = MG_.CreateMesh",
        p12m._w("ret_mesh", "ret_mesh_"),
        "RetWait_ = Doc_.WaitForWorker",
        p12m._w("wait_ret", "RetWait_"),
        p12m._w("mesh_exists", "MG_.DoesMeshExist"),
        p12m._w("mesh_err", "MG_.DoesMeshErrorExist"),
        f'Doc_.SaveProject "{out_pph.as_posix()}"',
    ]


def _vbs_lit(v: str) -> str:
    """VBS 字面量：能当数字就当数字，否则加引号。"""
    try:
        float(v)
        return v
    except ValueError:
        return chr(34) + v + chr(34)


#: 录制 ``box_scflow_mdl.vbs`` :562-632 的八叉树参数表（键/值交替 70 槽）
OCT_PARAM_PAIRS: list[tuple[str, str]] = [["BALANCING","3"],["BASELEV.MAX","6"],["BASELEV.MIN","-1"],["BASELEV.ROOTFAC","1.3999999999999999"],["BASEMODE","2"],["BASENAME",""],["BASENELEM","0"],["BASEPOS","1"],["BASEPOS.X","0.0050000000000000001"],["BASEPOS.Y","0.0050000000000000001"],["BASEPOS.Z","0.0050000000000000001"],["BASESIZE.MAX","-1"],["BASESIZE.MIN","0.00021875"],["BASESIZEFORAUTOGEN","0"],["BOUNDARYRANGE","0"],["CHECKONLYFLUID","0"],["CSPCGROUPINGTYPE","0"],["IGNOREDRATIO","0.0001"],["INITIALIZED","0"],["NUMERICALREGION.N","0"],["OCTNAME",""],["PATCHEFFECTMODE","0"],["PROXIMITYITEM.N","0"],["REFMODEL.N","0"],["REFSECTITEM.N","0"],["REGNMODE","0"],["REGNNAME",""],["SECTAVOIDORDERDEPENDENCY","1"],["SECTGRP2","0"],["SECTITEM.N","1"],["SECTITEM[0].NAME","@PartSurface_Part"],["SECTITEM[0].NEIGHBOR","0"],["SECTITEM[0].SIZE","0.001"],["SECTTYPE","1"],["TARGETNUMBER","100000"]]


def _recorded_oct_param_lines() -> list[str]:
    """录制八叉树参数表 → ``OctParam.SetParams`` 动作行（R2-1）。

    这是与最小配方（SetOctType/SetMeshNum/SetMinSize 三件套）的**关键差异**：
    录制把 ``SECTITEM[0].NAME = @PartSurface_Part``、``SECTITEM[0].SIZE =
    0.001``、``TARGETNUMBER = 100000``、``BASESIZE.MIN = 0.00021875`` 等 35 对
    键值整体下发；最小配方里 ``SetMinSize 0`` 很可能就是 mesh error 的来源。
    """
    out = ["Redim ArrayParam1_(" + str(2 * len(OCT_PARAM_PAIRS) - 1) + ")"]
    for i, (k, v) in enumerate(OCT_PARAM_PAIRS):
        out.append("ArrayParam1_(" + str(2 * i) + ") = " + chr(34) + k
                   + chr(34))
        out.append("ArrayParam1_(" + str(2 * i + 1) + ") = " + _vbs_lit(v))
    out += [
        "Set MG4_ = Doc_.QueryMeshingGroupByIndex(0)",
        "Set OctParam4_ = MG4_.GetOctParam",
        "OctParam4_.SetParams ArrayParam1_",
        'Param1_ = "default"',
        "Set MG5_ = Doc_.QueryMeshingGroupByIndex(0)",
        "MG5_.SetOctCreateTypeWithSolidBaseOct Param1_",
    ]
    return out


def _fluid_region_lines(part: str = "Part",
                        material: str = "air(incompressible/20C)") -> list[str]:
    """录制 ``box_scflow_mdl.vbs`` :274-348 的**流体区域登记块**（R2-1 关键缺口）。

    诊断依据（2026-09-14）：四条最小配方跑出的 ``meshinggroup1_error.mdl``
    内容是 **17150 faces / 8577 verts**，与绿色参照 ``p12a_bam_e2e_out.pph`` 的
    ``meshinggroup1_ridge.mdl``（同 17150/8577）**完全同规模** —— 面/ridge 阶段
    是忠实的；差别只在角色名 ``_error`` vs ``_ridge`` 与**缺失的 gph**。
    录制里紧接 SetModePart 之后就是本登记块（:274-348）：建 ``FluidRegion``、
    指定材料、``RegisterSPart`` 把 Part 挂进去。缺了它八叉树能建、网格必错
    （``NUMERICALREGION.N = 0``）。
    """
    q = chr(34)
    p12m = _load("p12m_run", ROOT / "tools" / "_p12m_j1_run.py")
    return [
        "Param1_ = True",
        "Set SNode_ = Doc_.QuerySNodeByName(" + q + part + q + ")",
        "SNode_.SetSelect Param1_",
        "Param1_ = " + q + "FluidRegion" + q,
        "Doc_.CreateFluidRegion Param1_",
        "Param1_ = " + q + material + q,
        "Set FluidRegion_ = Doc_.QueryFluidRegionByName(" + q
        + "FluidRegion" + q + ")",
        "FluidRegion_.SetMaterial Param1_",
        "Param1_ = False",
        "Dim ArrayParam2_()",
        "Redim ArrayParam2_(0)",
        "Set ArrayParam2_(0) = Doc_.QuerySNodeByName(" + q + part + q + ")",
        "Set FluidRegion_ = Doc_.QueryFluidRegionByName(" + q
        + "FluidRegion" + q + ")",
        "FluidRegion_.RegisterSPart Param1_, ArrayParam2_",
        "Param1_ = False",
        "Redim ArrayParam2_(-1)",
        "Set FluidRegion_ = Doc_.QueryFluidRegionByName(" + q
        + "FluidRegion" + q + ")",
        "FluidRegion_.RegisterVPart Param1_, ArrayParam2_",
        "Param1_ = False",
        "Param2_ = True",
        "Doc_.SetSelectAllSPart Param1_, Param2_",
        p12m._w("fluid_alive", "Not (Doc_.QueryFluidRegionByName(" + q
                + "FluidRegion" + q + ") Is Nothing)"),
    ]


def mesh_wizard_actions(cad: Path, out_pph: Path) -> list[str]:
    """R2-1：录制配方（box_scflow_mdl.vbs :71-535 + :2600-2610）的网格段。

    关键差异（对齐录制，逐条有据）：
      * ``ChangeMesher "poly", False`` / ``ChangeSurfMesher "facet_base"``
        —— 网格器与面网格器必须先落定；
      * ``SetMDLMethod 1`` + ``SetUseAFFacetter True`` +
        ``SetFacetAccuracySpecificationType 0``；
      * ``Proj_.SetUseAFFacetter True``（wizard 前，防 FindAFFaceMatching
        RPC_E_SERVERFAULT）；
      * ``BeginMDLWizard`` → ``GetMDLWizard`` → ``EndMDLWizard``（**必须
        UTF-16 通道**：ANSI 下 wizard 静默失败，GetMDLWizard 恒 Nothing）；
      * ``CreateOctree`` → ``CreateMeshMonitor``（监控型，非 typed
        CreateMesh）→ ``WaitForWorker``。
    """
    p12m = _load("p12m_run", ROOT / "tools" / "_p12m_j1_run.py")
    w = p12m._w
    return [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        "RetWW0_ = Doc_.WaitForWorker",
        f'Set SN_ = Doc_.OpenCadFile("{cad.as_posix()}")',
        "RetWW1_ = Doc_.WaitForWorker",
        "RetMode_ = Doc_.SetModePart",
        "RetWW2_ = Doc_.WaitForWorker",
        "Set MG_ = Doc_.QueryMeshingGroupByIndex(0)",
        "Set MGS_ = MG_.GetMeshingGroupSetting",
        'Param1_ = "poly"',
        "Param2_ = False",
        "MGS_.ChangeMesher Param1_, Param2_",
        'Param1_ = "facet_base"',
        "MGS_.ChangeSurfMesher Param1_",
        "Param1_ = 1",
        "MGS_.SetMDLMethod Param1_",
        "Param1_ = True",
        "MGS_.SetUseAFFacetter Param1_",
        "Param1_ = 0",
        "MGS_.SetFacetAccuracySpecificationType Param1_",
        "Param1_ = True",
        "Set Proj_ = Doc_.GetProjectSetting",
        "Proj_.SetUseAFFacetter Param1_",
    ] + _fluid_region_lines() + [
        "MG_.BeginMDLWizard",
        "RetWW3_ = Doc_.WaitForWorker",
        "Set MG2_ = Doc_.QueryMeshingGroupByIndex(0)",
        "Set Wiz_ = MG2_.GetMDLWizard",
        t_line("wiz_alive", "Not (Wiz_ Is Nothing)"),
        "If Not (Wiz_ Is Nothing) Then Wiz_.RemoveMDLFacetPreview",
        "MG2_.EndMDLWizard",
        "RetWW4_ = Doc_.WaitForWorker",
        "Set MG3_ = Doc_.QueryMeshingGroupByIndex(0)",
        t_line("vmdl_alive", "Not (MG3_.GetVMDL Is Nothing)"),
        "Set OctParam_ = MG3_.GetOctParam",
        "OctParam_.Initialize",
        "Param1_ = 3",
        "OctParam_.SetOctType Param1_",
        "Param1_ = 100000",
        "OctParam_.SetMeshNum Param1_",
        "Param1_ = 0.00021875",
        "OctParam_.SetMinSize Param1_",
    ] + _recorded_oct_param_lines() + [
        "ret_oct_ = MG3_.CreateOctree",
        w("ret_oct", "ret_oct_"),
        "RetWW5_ = Doc_.WaitForWorker",
        "ret_mesh_ = MG3_.CreateMeshMonitor",
        w("ret_mesh", "ret_mesh_"),
        "RetWait_ = Doc_.WaitForWorker",
        w("wait_ret", "RetWait_"),
        w("mesh_exists", "MG3_.DoesMeshExist"),
        w("mesh_err", "MG3_.DoesMeshErrorExist"),
        f'Doc_.SaveProject "{out_pph.as_posix()}"',
    ]


def t_line(key: str, expr: str) -> str:
    """``key=TypeName(expr)`` 型探针（对象/空值安全）。"""
    q = chr(34)
    return ("out_.WriteLine " + q + key + "=" + q + " & TypeName(" + expr
            + ") & " + q + " err=" + q + " & CStr(Err.Number)")

def reopen_actions(pph: Path, out_pph: Path) -> list[str]:
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
        "Set VMDL_ = MG_.GetVMDL",
        "Set OCT_ = MG_.GetOctree",
        p12m._w("mesh_exists", "MG_.DoesMeshExist"),
    ] + _bbox_lines() + [
        f'Doc_.SaveProject "{out_pph.as_posix()}"',
    ]


def _run(p12e, name: str, actions: list, log_dir: Path, timeout=900.0,
         utf16: bool = False, idle_limit: float | None = None) -> dict:
    # idle_limit（R3-1）：网格/重开段在**同一条 VBS 行内**长时间不写日志
    # （实测 STEP mesh ≈8.5 min、STEP reopen ≈6 min），会撞默认 420 s 惰性
    # 阈值被自愈判成 hung 并杀宿主。按段放宽阈值，而不是关掉监视。
    vbs = log_dir / f"r13_{name}.vbs"
    log = log_dir / f"r13_{name}.log"
    if log.is_file():
        log.unlink()
    script = p12e.logged_script([(name, actions)], log, f"R1-3 {name}")
    writer = p12e._write_utf16_vbs if utf16 else p12e._write_ansi_vbs
    writer(script, vbs, f"R1-3 {name}")
    t0 = time.time()
    try:
        p12e.run_e2e(name, vbs, log, timeout=timeout, idle_limit=idle_limit,
                     retry_with_boot=True)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    ver = p12e.verify_log(text)
    info = {}
    for key in ("ret_bam", "ret_vmdl", "ret_oct", "ret_mesh", "wait_ret",
                "mesh_exists", "mesh_err"):
        m = re.search(rf"{key}=(\S+)", text)
        if m:
            info[key] = m.group(1)
    bbox = re.search(r"^bbox=(\S+)$", text, re.MULTILINE)
    if bbox:
        info["bbox"] = bbox.group(1)
    return {"ok": bool(ver.get("has_end")) and ver.get("err0") == ver.get("total"),
            "seconds": round(time.time() - t0, 1),
            "err0": ver.get("err0"), "total": ver.get("total"),
            "alive": ver.get("alive", {}), "info": info}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R1-3 / R2-1 CAD 端到端 gate")
    ap.add_argument("--cases", default="xt,step")
    ap.add_argument("--step", type=Path, default=STEP_DEFAULT)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--mesh-mode", choices=("wizard", "reopen"),
                    default="wizard", help="mesh 段配方（默认 R2-1 wizard 配方）")
    ap.add_argument("--skip-mesh", action="store_true",
                    help="只跑 build+reopen（R1-3 口径），跳过 mesh 段")
    args = ap.parse_args(argv)
    cases = [c.strip() for c in args.cases.split(",") if c.strip()]
    WORK.mkdir(parents=True, exist_ok=True)
    p12e = _load("p12e_run", ROOT / "tools" / "_p12e_e2e_run.py")
    # R3-1：先切 UTF-8 stdout，否则 ensure_ascii=False 的结果打印时
    # UnicodeEncodeError 会掩盖真实失败（宿主在 STEP 网格中崩溃）。
    p12e.utf8_stdout()
    pid = host_boot.cold_boot()
    print(f"[r1-3] fresh host pid={pid}", flush=True)
    results: dict = {}
    for case in cases:
        cad = XT if case == "xt" else args.step
        if not cad.is_file():
            results[case] = {"ok": False, "error": f"cad missing: {cad}"}
            continue
        built = WORK / f"{case}_built.pph"
        meshed = WORK / f"{case}_meshed.pph"
        build = _run(p12e, f"{case}_build",
                     build_actions_full(cad, built), WORK)
        mesh = {"skipped": "build failed"}
        if build.get("ok") and built.is_file():
            if args.mesh_mode == "wizard":
                mesh = _run(p12e, f"{case}_mesh",
                            mesh_wizard_actions(cad, meshed), WORK,
                            timeout=2700.0, utf16=True,
                            idle_limit=1500.0)
            else:
                mesh = _run(p12e, f"{case}_mesh",
                            mesh_actions(built, meshed), WORK)
            mesh["mesh_exists_in_session"] = mesh.get("info", {}).get("mesh_exists")
        else:
            mesh.setdefault("ok", False)
        probe_src = meshed if mesh.get("ok") and meshed.is_file() else built
        reo = {"skipped": "no project"}
        if probe_src.is_file():
            reo = _run(p12e, f"{case}_reopen",
                       reopen_actions(probe_src, WORK / f"{case}_reopened.pph"),
                       WORK, timeout=1800.0, idle_limit=900.0)
            reo["mesh_exists_after_reopen"] = reo.get("info", {}).get("mesh_exists")
        else:
            reo.setdefault("ok", False)
        results[case] = {"cad": str(cad), "build": build, "mesh": mesh,
                         "reopen": reo,
                         "built_pph": str(built) if built.is_file() else None,
                         "meshed_pph": str(meshed) if meshed.is_file() else None}
        print(f"[{case}] " + json.dumps(results[case], ensure_ascii=False),
              flush=True)
    def _pass(r: dict) -> bool:
        if not (r.get("build", {}).get("ok") and r.get("reopen", {}).get("ok")):
            return False
        if args.skip_mesh:
            return True
        return (r.get("mesh", {}).get("ok")
                and r.get("mesh", {}).get("info", {}).get("mesh_exists") == "True"
                and r.get("reopen", {}).get("info", {}).get("mesh_exists") == "True")
    summary = {"cases": results,
               "passed": sum(1 for r in results.values() if _pass(r))}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print("SUMMARY: " + json.dumps(
        {"passed": summary["passed"], "total": len(cases)}, ensure_ascii=False))
    return 0 if summary["passed"] == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
