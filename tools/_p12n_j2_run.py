"""P12-N J2 实机：域 4 复议 + CATIA 深闭环（snode 腿产物级 + facet 前置狩猎）。

I7（§20.11）钉死：真 CATPart（starccm starcat5，15 件 V5_CFV2）读链
绿——OpenCadFile retval Nothing 但 QuerySNodeByName("Part") alive
（P12-D STEP 同型 retval-unreliable 模式）；ImportCADAsFacet 对
CATPart 与 XT 对照同 False（err=0 干净业务拒 = 方法内部前置检查，
非异常）。GUI 手册 [File]-[Import] 钉死 Patch 族 = DXF/NASTRAN/STL/
MDL、无 "CAD as Facet" 菜单项；实现体 ImportCADAsFacet@Doc 在
scFLOWpreCmd/GUI DLL（native，无错误串外露）。P12-D snode 腿配方
（box_scflow_mdl.vbs 录制回放）+ J1 r4 WIZARD_CORE（几何无关全绿）
= ① 的全链配方。

J2 两腿：

- **catia_mdl（① 真 CATPart MDL 产物级闭环）**：裸宿主 →
  OpenCadFile(CATPart) → WaitForWorker → QuerySNodeByName("Part") →
  QueryMeshingGroupByIndex(0) → 别名（J1 r3 教训）→ AF 前置 +
  WIZARD_CORE 重放 → GetMDL/IsMDL 探针 → GetVMDL.Save 产物导出 →
  SaveProject。验收 = err=0 + 组/MDL alive + VMDL.Save 的 .mdl
  产物在位 + 容器内嵌 .gph。主样本 PorousMiddle（I7 已证读链）+
  副样本 wingSkin（异几何族对照，sn2 记录性）。
- **facet 矩阵（② ImportCADAsFacet 前置狩猎）**：五变体对照——
  ``f_stl``（12 tri 立方 STL，facet 格式对照）、``f_stl_af``（STL
  + AF faceter 前置）、``f_xt_af``（XT + AF 前置，I7 无前置 False
  的对照）、``f_catia_af``（CATPart + AF 前置）、``f_catia_empty``
  （裸空文档 + CATPart + AF 前置，排除「工程已含 CAD」因素）。
  任一 True = 前置钉死；全 False = 拒绝对 AF/格式/空文档不变 →
  许可/引擎硬门口径入册。

r2 裁决（2026-09-05）：facet 前置**钉死为输入格式 = 面片格式**——
f_stl/f_stl_af ``f_ret=True`` 且容器落 ``meshinggroup2_part.mdl``；
XT/CATPart（裸/带工程/±AF）全 ``False`` err=0（手册：Patch 导入族
= DXF/NASTRAN/STL/MDL，CAD kernel 格式归 OpenCadFile 链）。①两流
err=0 全绿但 ``sn2__alive=False`` → MDL/VMDL Nothing → s096=424。
**I7 翻案**：``_p12l_i7/c1_out.pph`` 容器差分仅 date/name/species
乱序、零 CATPart 几何——I7 的 ``sn2__alive=True`` 实为 box.pph 自带
"Part" 节点（box.x_t 顶节点名即 Part），非 CATPart 几何。

r3 ``cadmatrix``（4 格式裸宿主对照）：xt（P12-D 已证控制）/ step
（P12-A 仅 err=0 弱证据，本轮升几何级）/ catia / catia2。探针 =
名字无关的 ``GetSParts`` 枚举（ping 前后两轮，区分异步慢导入 vs
零几何 no-op）+ ``GetAllPartsBoundingBox`` + SaveProject 容器差分。

业务判定先记录后判定（沿 J1 口径）：gate 只管 err=0/alive/end，
f_ret / 产物在位作为业务面单独陈述。

用法：``py tools/_p12n_j2_run.py
[catia_mdl|catia_mdl2|facet|cadmatrix|all]``
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
import threading
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "_p12m_j1_run", ROOT / "tools" / "_p12m_j1_run.py")
p12m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p12m)
p12e = p12m.p12e

N_DIR = ROOT / "_p12n_j2"
CATIA_DIR = Path(r"D:\training\starccm\startutorialsdata\starcat5\data")
CATIA_PART = CATIA_DIR / "PorousMiddle.CATPart"
CATIA_PART2 = CATIA_DIR / "wingSkin.CATPart"
XT_PART = ROOT / "tests" / "box" / "box.x_t"
STEP_PART = Path(r"D:\training\3dprint\FunHome-main\funHomeFan\cad"
                 r"\FunDeskFan\base v7.step")
SRC_PPH = ROOT / "_p12a_e2e" / "box.pph"
CUBE_STL = N_DIR / "p12n_cube.stl"

CADMATRIX_CASES = (
    ("cm_xt", XT_PART),
    ("cm_step", STEP_PART),
    ("cm_catia", CATIA_PART),
    ("cm_catia2", CATIA_PART2),
)

MDL1 = N_DIR / "p12n_porous_mdl.mdl"
MDL2 = N_DIR / "p12n_wing_mdl.mdl"
M1_VBS = ROOT / "p12n_catia_mdl_e2e.vbs"
M1_LOG = ROOT / "p12n_catia_mdl_e2e.log"
M1_OUT = ROOT / "p12n_catia_mdl_out.pph"
M2_VBS = ROOT / "p12n_catia_mdl2_e2e.vbs"
M2_LOG = ROOT / "p12n_catia_mdl2_e2e.log"
M2_OUT = ROOT / "p12n_catia_mdl2_out.pph"

FACET_CASES = (
    # (name, cad, af_prelude, empty_doc)
    ("f_stl", "cube", False, False),
    ("f_stl_af", "cube", True, False),
    ("f_xt_af", "xt", True, False),
    ("f_catia_af", "catia", True, False),
    ("f_catia_empty", "catia", True, True),
)


def _cad(which: str) -> Path:
    return {"cube": CUBE_STL, "xt": XT_PART, "catia": CATIA_PART}[which]


def ensure_cube() -> Path:
    if not CUBE_STL.is_file():
        p12m.build_patch2_cube(CUBE_STL)
    return CUBE_STL


# ── VBS 生成 ───────────────────────────────────────────────────────────────

_HEADER = [
    "Set App_ = GetApplication()",
    'If App_ Is Nothing Then Set App_ = '
    'CreateObject("scFLOWpre_Bx64net.Application.2025")',
    "Set Doc_ = App_.GetDocument",
]


def _af_prelude() -> list[str]:
    return [
        "Param1_ = True",
        "Set Proj_ = Doc_.GetProjectSetting",
        "Proj_.SetUseAFFacetter Param1_",
    ]


def build_catia_mdl_groups(cad: Path, out_pph: Path, mdl_out: Path,
                           flow_name: str):
    """① snode 腿产物级闭环：裸宿主 OpenCadFile → WIZARD_CORE →
    VMDL.Save → SaveProject（P12-D 配方 + J1 r4 全绿核）。

    r1 教训（4/4 确定性）：EndMDLWizard 在真 CAD 几何（CATPart 导入
    组）上击杀脚本进程（s092 后无 s093、无 end、log 恒 1806B；
    CreateMDL 已 s062 err=0 建模成功，立方体几何 J1 r4 同动作全绿
    = 几何相关）。故流程去 EndMDLWizard，产物探针/导出/SaveProject
    全部置于 wizard 会话内（CreateMDL 后 MDL/VMDL 即已可用）。
    """
    actions = _HEADER + [
        f'Set SN_ = Doc_.OpenCadFile("{cad.as_posix()}")',
        "RetWW1_ = Doc_.WaitForWorker",
        'Set SN2_ = Doc_.QuerySNodeByName("Part")',
        "Set MGW_ = Doc_.QueryMeshingGroupByIndex(0)",
        # J1 r3 教训：WIZARD_CORE 沿用录制变量名 MeshingGroup_
        "Set MeshingGroup_ = MGW_",
    ] + _af_prelude() + p12m.WIZARD_CORE[:-1] + [
        "Set MDL2_ = MGW_.GetMDL",
        p12m._w("im1", "MGW_.IsMDL"),
        "Set VMDL2_ = MGW_.GetVMDL",
        f'RetVx_ = VMDL2_.Save("{mdl_out.as_posix()}")',
        "RetWW2_ = Doc_.WaitForWorker",
        f'Doc_.SaveProject "{out_pph.as_posix()}"',
    ]
    return [(flow_name, actions)]


def build_cadmatrix_groups(cad: Path, out_pph: Path, flow_name: str):
    """r3 格式矩阵单流：裸宿主 OpenCadFile → 名字无关几何探针两轮 →
    落盘。早轮探针在 ping×2（~10s）后，晚轮再 ping×3 后——区分
    「Datakit 异步慢导入」与「零几何 no-op」。stem 同名 SNode 探针
    兜名字差异假设（box.x_t 顶节点 = "Part" 的对照面）。"""
    stem = cad.stem
    ping = ('CreateObject("WScript.Shell").Run '
            '"cmd /c ping -n 6 127.0.0.1 > nul", 0, True')
    bbox_lines = [
        "Dim BBox_",
        "Doc_.GetAllPartsBoundingBox BBox_, False",
        'If IsArray(BBox_) Then out_.WriteLine "bbox_ub=" '
        '& CStr(UBound(BBox_)) & " b0=" & CStr(BBox_(0)) & " bL=" '
        '& CStr(BBox_(UBound(BBox_))) & " err=" & CStr(Err.Number) '
        'Else out_.WriteLine "bbox=NA err=" & CStr(Err.Number)',
        "Err.Clear",
    ]
    actions = _HEADER + [
        f'Set SN_ = Doc_.OpenCadFile("{cad.as_posix()}")',
        "RetWW1_ = Doc_.WaitForWorker",
        ping, ping,
        'Set SN2_ = Doc_.QuerySNodeByName("Part")',
        f'Set SN3_ = Doc_.QuerySNodeByName("{stem}")',
        'Parts_ = Doc_.GetSParts(False, False, False)',
    ] + p12m._ubound_guard("Parts_") + [
        ping, ping, ping,
        'Parts2_ = Doc_.GetSParts(False, False, False)',
    ] + p12m._ubound_guard("Parts2_") + bbox_lines + [
        f'Doc_.SaveProject "{out_pph.as_posix()}"',
    ]
    return [(flow_name, actions)]


def build_facet_groups(name: str, cad: Path, out_pph: Path | None,
                       src_pph: Path | None, af: bool, empty_doc: bool):
    """② 前置矩阵变体：±AF faceter 前置 × ±空文档 × 三种输入格式。"""
    header = list(_HEADER)
    if not empty_doc:
        header += [
            "RetWW_ = Doc_.WaitForWorker",
            f'Doc_.OpenProject "{src_pph.as_posix()}", False',
        ]
    body = (_af_prelude() if af else []) + [
        "Set MG_ = Doc_.CreateMeshingGroup",
        f'ret_ = Doc_.ImportCADAsFacet("{cad.as_posix()}", MG_)',
        p12m._w("f_ret", "ret_"),
        "Err.Clear",
        "RetWW2_ = Doc_.WaitForWorker",
        "Set MDL3_ = MG_.GetMDL",
        p12m._w("im2", "MG_.IsMDL"),
    ]
    if out_pph is not None:
        body.append(f'Doc_.SaveProject "{out_pph.as_posix()}"')
    return [(name, header + body)]


# ── 离线验收辅助 ───────────────────────────────────────────────────────────


def container_members(out_pph: Path) -> list[str] | None:
    if not out_pph.is_file():
        return None
    with zipfile.ZipFile(out_pph) as zf:
        return sorted(i.filename for i in zf.infolist())


def member_diff(out_pph: Path, src_pph: Path) -> dict:
    out = {"exists": out_pph.is_file(), "new": [], "gone": []}
    if not out["exists"] or not src_pph.is_file():
        return out
    with zipfile.ZipFile(out_pph) as zo, zipfile.ZipFile(src_pph) as zs:
        a, b = set(zs.namelist()), set(zo.namelist())
    out["new"] = sorted(b - a)
    out["gone"] = sorted(a - b)
    return out


# ── 驱动 ───────────────────────────────────────────────────────────────────


def _confirm_watchdog(stop_evt: threading.Event) -> None:
    from automation import modal_watch
    from automation import host_boot
    while not stop_evt.is_set():
        try:
            for hp in modal_watch.host_pids(host_boot.HOST_IMAGE):
                clicked = modal_watch.click_confirm_yes(hp)
                if clicked:
                    print("[modal] confirm-yes clicked: " + json.dumps(
                        [d.get("title") for d in clicked],
                        ensure_ascii=False), flush=True)
        except Exception:  # noqa: BLE001 - 看守线程绝不中断主流程
            pass
        stop_evt.wait(2.0)


def main(argv):
    which = argv[0] if argv else "all"
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    results = {}
    N_DIR.mkdir(exist_ok=True)
    ensure_cube()

    def flow(name, groups, vbs_p, log_p, timeout, alive, min_checks,
             end_wait=600.0, idle_limit=1200.0):
        from automation import host_boot
        pid = host_boot.cold_boot()
        print("[" + name + "] cold boot host pid " + str(pid), flush=True)
        stop_evt = threading.Event()
        watcher = threading.Thread(target=_confirm_watchdog,
                                   args=(stop_evt,), daemon=True)
        watcher.start()
        try:
            vbs = p12e._write_utf16_vbs(
                p12e.logged_script(groups, log_p,
                                   "pphdecoding P12-N " + name),
                vbs_p, title="pphdecoding P12-N " + name + " e2e")
            res = p12e.run_e2e(name, vbs, log_p, timeout=timeout,
                               end_wait=end_wait, idle_limit=idle_limit,
                               watch_modals=True, retry_with_boot=True)
        finally:
            stop_evt.set()
        results[name] = p12e.gate(name, res, alive_need=alive,
                                  min_checks=min_checks)
        return res

    def log_text(log_p):
        return log_p.read_text(encoding="utf-8", errors="replace") \
            if log_p.is_file() else ""

    # ① 真 CATPart MDL 产物级闭环（主样本 PorousMiddle + 副样本
    # wingSkin；裸宿主纪律——OpenCadFile 流最先跑）
    if which in ("catia_mdl", "all"):
        flow("catia_mdl",
             build_catia_mdl_groups(CATIA_PART, M1_OUT, MDL1, "catia_mdl"),
             M1_VBS, M1_LOG, timeout=2400.0,
             alive=("sn2_", "mgw_", "mdl2_"), min_checks=40)
        m1 = container_members(M1_OUT)
        art1 = {"mdl_file": MDL1.is_file(), "mdl_bytes":
                MDL1.stat().st_size if MDL1.is_file() else 0,
                "has_gph": bool(m1) and any(
                    n.endswith(".gph") for n in m1), "members": m1}
        print("[catia_mdl] artifact: " + json.dumps(
            {k: v for k, v in art1.items() if k != "members"},
            ensure_ascii=False), flush=True)

    if which in ("catia_mdl2", "all"):
        flow("catia_mdl2",
             build_catia_mdl_groups(CATIA_PART2, M2_OUT, MDL2,
                                    "catia_mdl2"),
             M2_VBS, M2_LOG, timeout=2400.0,
             alive=("mgw_", "mdl2_"), min_checks=40)
        m2 = container_members(M2_OUT)
        art2 = {"mdl_file": MDL2.is_file(), "mdl_bytes":
                MDL2.stat().st_size if MDL2.is_file() else 0,
                "has_gph": bool(m2) and any(
                    n.endswith(".gph") for n in m2), "members": m2}
        print("[catia_mdl2] artifact: " + json.dumps(
            {k: v for k, v in art2.items() if k != "members"},
            ensure_ascii=False), flush=True)

    # ② ImportCADAsFacet 前置矩阵（五变体）
    facet_fret = {}
    facet_members = {}
    if which in ("facet", "all"):
        for name, cad_key, af, empty in FACET_CASES:
            src = None
            out = None
            if not empty:
                src = N_DIR / (name + "_src.pph")
                out = ROOT / ("p12n_" + name + "_out.pph")
                shutil.copyfile(SRC_PPH, src)
            flow(name,
                 build_facet_groups(name, _cad(cad_key), out, src,
                                    af=af, empty_doc=empty),
                 ROOT / ("p12n_" + name + "_e2e.vbs"),
                 ROOT / ("p12n_" + name + "_e2e.log"),
                 timeout=900.0, alive=("mg_",), min_checks=5,
                 end_wait=300.0, idle_limit=600.0)
            text = log_text(ROOT / ("p12n_" + name + "_e2e.log"))
            info = {m.group(1): m.group(2)
                    for m in re.finditer(r"^(f_ret|im2)=(\S+)", text,
                                         re.MULTILINE)}
            facet_fret[name] = info
            if out is not None and out.is_file() and src is not None:
                facet_members[name] = member_diff(out, src)
        print("[facet] f_ret matrix: " + json.dumps(
            facet_fret, ensure_ascii=False), flush=True)

    # r3 格式矩阵（4 格式 × 几何级探针，XT 为 P12-D 已证控制）
    cadmatrix = {}
    if which in ("cadmatrix", "all"):
        if not STEP_PART.is_file():
            print("[cadmatrix] STEP sample missing: " + str(STEP_PART))
            cadmatrix["error"] = f"missing {STEP_PART}"
        for name, cad in CADMATRIX_CASES:
            if not cad.is_file():
                print("[cadmatrix] sample missing: " + str(cad))
                cadmatrix[name] = {"error": f"missing {cad}"}
                continue
            out = N_DIR / (name + "_out.pph")
            flow(name,
                 build_cadmatrix_groups(cad, out, name),
                 ROOT / ("p12n_" + name + "_e2e.vbs"),
                 ROOT / ("p12n_" + name + "_e2e.log"),
                 timeout=900.0, alive=(), min_checks=8,
                 end_wait=300.0, idle_limit=600.0)
            text = log_text(ROOT / ("p12n_" + name + "_e2e.log"))
            rec = {m.group(1): m.group(2)
                   for m in re.finditer(
                       r"^(sn2__alive|sn3__alive|parts_ub|parts2_ub)"
                       r"=(\S+)", text, re.MULTILINE)}
            bm = re.search(r"^bbox.*$", text, re.MULTILINE)
            rec["bbox"] = bm.group(0) if bm else None
            mem = container_members(out) or []
            rec["cad_members"] = [n for n in mem
                                  if n.endswith((".mdl", ".gph"))]
            cadmatrix[name] = rec
        print("[cadmatrix] matrix: " + json.dumps(
            cadmatrix, ensure_ascii=False), flush=True)

    # 业务裁决（先记录后判定）
    verdict = {}
    if which in ("catia_mdl", "all"):
        verdict["catia_mdl_artifact"] = bool(
            MDL1.is_file() and results.get("catia_mdl"))
    if which in ("catia_mdl2", "all"):
        verdict["catia_mdl2_artifact"] = bool(
            MDL2.is_file() and results.get("catia_mdl2"))
    if which in ("facet", "all"):
        rets = [v.get("f_ret") for v in facet_fret.values()]
        if "True" in rets:
            hit = [k for k, v in facet_fret.items()
                   if v.get("f_ret") == "True"]
            verdict["facet_branch"] = "precondition pinned: " + ",".join(hit)
        elif rets and all(r == "False" for r in rets):
            verdict["facet_branch"] = ("rejection invariant across "
                                       "af/format/empty-doc = "
                                       "license-or-engine hard gate")
        else:
            verdict["facet_branch"] = "incomplete"
    if which in ("cadmatrix", "all") and "error" not in cadmatrix:
        landed = lambda k: cadmatrix.get(k, {}).get("parts2_ub") \
            not in (None, "NA", "-1")  # noqa: E731
        if not landed("cm_xt"):
            verdict["cadmatrix_branch"] = ("control-xt-no-parts "
                                           "(matrix uninterpretable)")
        elif landed("cm_catia") or landed("cm_catia2"):
            verdict["cadmatrix_branch"] = "catia parts landed (proceed catia_mdl)"
        elif landed("cm_step"):
            verdict["cadmatrix_branch"] = ("catia-feature zero-geometry "
                                           "(datakit chain alive via step)")
        else:
            verdict["cadmatrix_branch"] = ("datakit chain zero-geometry in "
                                           "COM mode (step+catia both empty)")
    overall = bool(results) and all(results.values())
    print("[j2] BUSINESS: " + json.dumps(verdict, ensure_ascii=False),
          flush=True)
    print("SUMMARY: " + json.dumps(
        {"flows": results, "facet": facet_fret,
         "cadmatrix": cadmatrix, "members":
         {k: v for k, v in facet_members.items()},
         "verdict": verdict}, ensure_ascii=False), flush=True)
    print("OVERALL: " + ("PASS" if overall else "FAIL"), flush=True)
    (N_DIR / "p12n_run_summary.json").write_text(
        json.dumps({"flows": results, "facet": facet_fret,
                    "cadmatrix": cadmatrix,
                    "members": facet_members, "verdict": verdict},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
