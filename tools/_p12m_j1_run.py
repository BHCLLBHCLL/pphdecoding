"""P12-M J1 实机复验：遗留④/⑤ 时窗复验——MDL Wizard 重放 → 恢复腿（域 10）。

I3（§20.7）钉死的事实与本轮新证据（离线容器勘验，2026-09-05）：

- ``ImportPatchAsCAD`` = 组内换件，换件后 SaveProject 容器**丢失全部
  组员**（cv2b 仅 5 成员、无 ``meshinggroup1_*`` 族）且
  ``meshinggroup1_restore_cvol.his`` 存储数据被丢弃（快照/main.xml
  零闭体积标记）→ 纯 MDL Wizard 重放不足以走到恢复腿：**恢复源为
  空**。目录钉死 ``ImportPatchAsCAD(path)`` 无 Store-and-Open 变体
  （GUI 导入对话框的 [Store and Open] 按钮在 COM 面不可表达）。
- ``.his`` 格式全解（文本，UTF-8 BOM，``# his version="2.0"``）：
  ``registervolumeobserver`` 100 个采样点（绝对坐标，模型 bbox 内）+
  尾部 ``registervolumeregioninf(IVRI, ICSPC, 1)`` 体区域关联
  （FluidRegion）。恢复配对 = 存储点云对当前模型闭体积命中测试。
- main.xml 无 ``.his`` 文件名引用 → 组员命名约定自描述，
  **ZIP 级注入可行**（P12 写回面）。
- 历史 bam 产物容器证实模型状态经 ``main.sctsnapshot`` 内嵌
  （wizard + CreateOctree + CreateMeshMonitor + WaitForWorker 后
  SaveProject，重开 GetVMDL alive——p12e mesh 流实证）。

J1 场景链（同几何再导入 = 配对成功率最高形态）：

- **wiz**（单会话）：OpenProject(p12i_cv1b_out.pph，存储史 + box 模型)
  → ``ImportPatchAsCAD(p12m_patch2_boxshell.stl)``（离线从
  cv1b ``meshinggroup1_part.mdl`` 60492 面提取的**同几何** STL）
  → WaitForWorker → AF faceter 前置（P12-A 崩溃教训）→
  Analysis Model Wizard 最小核（box 录制 :351-528 逐步对齐，
  ``CreateMultiEntityInfo`` ×6→×1 适配单实体）→ EndMDLWizard →
  GetMDL/RecognizeClosedVolume/GetClosedVolumes 探针 →
  SetModeOctree + CreateOctree + CreateMeshMonitor + WaitForWorker →
  SaveProject(p12m_wiz_out.pph)。
- **inject**（离线）：把 cv1b 的 ``.his`` 字节复制注入
  p12m_wiz_out.pph → p12m_restore_in.pph（[Store and Open] 的
  存储侧经写回面携带；GUI 按钮本体在 COM 面不可表达，如实入册）。
- **restore**（新会话 = Store-and-Open 等价重开）：
  OpenProject(p12m_restore_in.pph) → ping 退避 → GetMDL（期望
  alive，快照内嵌）→ GetStoredClosedVolumes（期望 1，注入源）→
  GetClosedVolumes（期望 ≥1，目的地）→
  ``IsClosedVolumeRestorationAvailable`` →
  ``GetRestorationCandidateOfClosedVolume(LB0, True)`` →
  Dim+Set CVolPairs → ``RestoreClosedVolumes(True, Pairs)`` →
  SaveProject(p12m_restore_out.pph)。

业务三态（沿 I3 口径，先记录后判定）：
``restorable=1``（av=True 且 restore retval=True，NYI 可解禁）/
``0``（av=True 但 retval≠True）/``-1``（av≠True）。

用法：``py tools/_p12m_j1_run.py [wiz|restore|all]``
"""

from __future__ import annotations

import json
import re
import struct
import sys
import threading
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "_p12e_e2e_run", ROOT / "tools" / "_p12e_e2e_run.py")
p12e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p12e)

M_DIR = ROOT / "_p12m_j1"
CV1B = ROOT / "p12i_cv1b_out.pph"
CV1B_MODEL_MEMBER = "meshinggroup1_part.mdl"
HIS_MEMBER = "meshinggroup1_restore_cvol.his"
PATCH2 = M_DIR / "p12m_patch2_cube.stl"
WIZ_VBS = ROOT / "p12m_wiz_e2e.vbs"
WIZ_LOG = ROOT / "p12m_wiz_e2e.log"
WIZ_OUT = ROOT / "p12m_wiz_out.pph"
RESTORE_IN = M_DIR / "p12m_restore_in.pph"
RESTORE_VBS = ROOT / "p12m_restore_e2e.vbs"
RESTORE_LOG = ROOT / "p12m_restore_e2e.log"
RESTORE_OUT = ROOT / "p12m_restore_out.pph"


# ── 离线场景构造 ───────────────────────────────────────────────────────────


def stl_bytes(tris) -> bytes:
    """三角面片 (n, 3, 3) → binary STL（法线 = 叉积单位化）。"""
    import numpy as np
    tris = np.asarray(tris, dtype=float)
    n = tris.shape[0]
    buf = bytearray(b"\0" * 80)
    buf += struct.pack("<I", n)
    for t in tris:
        e1 = t[1] - t[0]
        e2 = t[2] - t[0]
        nx = float(e1[1] * e2[2] - e1[2] * e2[1])
        ny = float(e1[2] * e2[0] - e1[0] * e2[2])
        nz = float(e1[0] * e2[1] - e1[1] * e2[0])
        ln = (nx * nx + ny * ny + nz * nz) ** 0.5 or 1.0
        buf += struct.pack("<3f", nx / ln, ny / ln, nz / ln)
        for v in t:
            buf += struct.pack("<3f", float(v[0]), float(v[1]), float(v[2]))
        buf += b"\0\0"
    return bytes(buf)


def build_patch2_cube(out: Path = PATCH2, side: float = 0.01) -> Path:
    """patch② = [0,side]³ 12 三角 binary STL。

    part.mdl 流形分析（J1 r2 教训）：60492 三角 = 6 面 × 71×71 网格
    ×2、顶点 30248 = 6·70²+12·70+8、法线 6 轴各 10082 且 |cos|=1、
    顶点全在 bbox 平面——闭体积就是 [0,0.01]³ 全立方体，无腔体。
    由 part.mdl 提取的 60k 三角同几何 STL 使 ImportPatchAsCAD 在
    工作进程内病态计算（r1/r2 两连挂，2/2 复现），12 三角同区域
    立方体绕开病态面片规模。.his 100 采样点均在 [0,0.01]³ 内部。
    """
    s = side
    v = {
        "000": (0.0, 0.0, 0.0), "100": (s, 0.0, 0.0),
        "010": (0.0, s, 0.0), "110": (s, s, 0.0),
        "001": (0.0, 0.0, s), "101": (s, 0.0, s),
        "011": (0.0, s, s), "111": (s, s, s),
    }
    faces = [
        ("000", "110", "100"), ("000", "010", "110"),          # bottom -z
        ("001", "101", "111"), ("001", "111", "011"),          # top +z
        ("000", "101", "001"), ("000", "100", "101"),          # front -y
        ("010", "011", "111"), ("010", "111", "110"),          # back +y
        ("000", "001", "011"), ("000", "011", "010"),          # left -x
        ("100", "110", "111"), ("100", "111", "101"),          # right +x
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(stl_bytes([[v[a], v[b], v[c]] for a, b, c in faces]))
    return out


_STORED_RE = re.compile(
    r"<storedclosedvolumes\s*/>|<storedclosedvolumes>.*?</storedclosedvolumes>",
    re.S)


def inject_his(src_pph: Path = CV1B, dst_pph: Path = WIZ_OUT,
               out: Path = RESTORE_IN,
               member: str = HIS_MEMBER) -> Path:
    """把存储闭体积成员字节 + main.xml 存储声明成对注入目标容器。

    r5 教训：只注入 .his 成员时重开 str2_ub=-1——装载由 main.xml
    ``<mdl><storedclosedvolumes>`` 声明驱动（COM 换件把该块重置为空，
    I3 mesh_state 教训的精确元素级落点），声明与成员必须成对。
    """
    with zipfile.ZipFile(src_pph) as z:
        payload = z.read(member)
        src_xml = z.read("main.xml").decode("utf-8", errors="replace")
    m = _STORED_RE.search(src_xml)
    if not (m and "<closedvolume>" in m.group(0)):
        raise SystemExit(f"{src_pph.name}: no populated storedclosedvolumes")
    block = m.group(0)
    with zipfile.ZipFile(dst_pph) as z:
        names = z.namelist()
        if member in names:
            raise SystemExit(f"{dst_pph.name} already has {member}")
        items = [(info, z.read(info.filename)) for info in z.infolist()]
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for info, data in items:
            if info.filename == "main.xml":
                data = _STORED_RE.sub(lambda _m: block,
                                      data.decode("utf-8", errors="replace"),
                                      count=1).encode("utf-8")
            z.writestr(info.filename, data)
        z.writestr(member, payload)
    return out


# ── VBS 生成 ───────────────────────────────────────────────────────────────


def _w(key, expr):
    return ('out_.WriteLine "' + key + '=" & CStr(' + expr + ')'
            ' & " err=" & CStr(Err.Number)')


def _ubound_guard(var):
    lo = var.rstrip("_").lower() + "_ub"
    return [
        "If IsArray(" + var + ") Then " + _w(lo, "UBound(" + var + ")")
        + " Else out_.WriteLine \"" + lo + "=NA err=0\"",
    ]


# Analysis Model Wizard 最小核：box_scflow_mdl.vbs :351-528 逐步对齐
# （去 RemoveHighlight 修饰行；CreateMultiEntityInfo ×6→×1 适配单实体）。
WIZARD_CORE: list[str] = [
    "MeshingGroup_.BeginMDLWizard",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.RemoveMDLFacetPreview",
    "Doc_.SetModePart",
    "Param1_ = True",
    "Set Proj_ = Doc_.GetProjectSetting",
    "Proj_.SetRidgeProjectSolids Param1_",
    "Param1_ = True",
    "Set Proj_ = Doc_.GetProjectSetting",
    "Proj_.SetRidgeProjectSheets Param1_",
    "Param1_ = True",
    "Set Proj_ = Doc_.GetProjectSetting",
    "Proj_.SetUseAFFacetter Param1_",
    "Param1_ = 0",
    "Set Proj_ = Doc_.GetProjectSetting",
    "Proj_.SetFacetAccuracySpecificationType Param1_",
    "Param1_ = True",
    "Set MeshingGroupSetting_ = MeshingGroup_.GetMeshingGroupSetting",
    "MeshingGroupSetting_.SetUseOctLengthParam Param1_",
    "Param1_ = 5",
    "Set MeshingGroupSetting_ = MeshingGroup_.GetMeshingGroupSetting",
    "MeshingGroupSetting_.SetOctLengthParamType Param1_",
    "Param1_ = 5",
    "Set MeshingGroupSetting_ = MeshingGroup_.GetMeshingGroupSetting",
    "MeshingGroupSetting_.SetOctLengthParamItr Param1_",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.CreateBoundary",
    "Param1_ = True",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.CreateMultiEntityInfo Param1_",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.SetBoundaryConfigured",
    "Param1_ = False",
    "Set MeshingGroupSetting_ = MeshingGroup_.GetMeshingGroupSetting",
    "MeshingGroupSetting_.SetFacetUseAbsoluteValue Param1_",
    "Param1_ = 0.05",
    "Set MeshingGroupSetting_ = MeshingGroup_.GetMeshingGroupSetting",
    "MeshingGroupSetting_.SetAFFaceterLengthFactor Param1_",
    "Param1_ = 10",
    "Set MeshingGroupSetting_ = MeshingGroup_.GetMeshingGroupSetting",
    "MeshingGroupSetting_.SetAFFaceterMinimumAngle Param1_",
    "Param1_ = 5",
    "Set MeshingGroupSetting_ = MeshingGroup_.GetMeshingGroupSetting",
    "MeshingGroupSetting_.SetFacetSimpleMaxWidth Param1_",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.RemoveMDLFacetPreview",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.SetSpatialSeparationSettingsConfigured",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.RemoveMDLFacetPreview",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.ReconfigureSpatialSeparationSettings",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.SetAutoRemoveTinyFaceConfigured",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.CreateMDL",
    "Param1_ = 0.05",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.FindAFFaceMatching Param1_",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.SetFaceMatched",
    "Param1_ = 1e-05",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.FindTinyFace Param1_",
    "Doc_.ClearPreview",
    "Param1_ = 1e-05",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.FindTinyFace Param1_",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.SetTinyFacesRemoved",
    'Param1_ = "TINYFACEARROW"',
    "Doc_.DeleteTemporaryDrawingObject Param1_",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.RepairMDL",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.CheckMDLErrors",
    "Doc_.ClearPreview",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.RemoveMDLFacetPreview",
    'Param1_ = "TINYFACEARROW"',
    "Doc_.DeleteTemporaryDrawingObject Param1_",
    "MeshingGroup_.EndMDLWizard",
]


def build_wiz_groups():
    """swap（同几何再导入）+ MDL Wizard 重放 + 内嵌全链，单会话。"""
    prelude = [
        "Param1_ = True",
        "Set Proj_ = Doc_.GetProjectSetting",
        "Proj_.SetUseAFFacetter Param1_",
    ]
    octree = [
        "Doc_.SetModeOctree",
        "Set MGO_ = Doc_.QueryMeshingGroupByIndex(0)",
        "MGO_.CreateOctree",
        "Set MGM_ = Doc_.QueryMeshingGroupByIndex(0)",
        "MGM_.CreateMeshMonitor",
        "RetWW3_ = Doc_.WaitForWorker",
    ]
    actions = [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        "RetWW_ = Doc_.WaitForWorker",
        'Doc_.OpenProject "' + CV1B.as_posix() + '", False',
        "RetWW2_ = Doc_.WaitForWorker",
        # 另一 patch 再导入（同几何 box 壳；Confirm 由看守点「是」）
        'Set SN6_ = Doc_.ImportPatchAsCAD("' + PATCH2.as_posix() + '")',
        "RetWW4_ = Doc_.WaitForWorker",
        "Set MGW_ = Doc_.QueryMeshingGroupByIndex(0)",
        # WIZARD_CORE 沿用录制变量名 MeshingGroup_（r3 教训：只赋值
        # MGW_ 时全段 424 Object required，wizard 重放整段静默失败）
        "Set MeshingGroup_ = MGW_",
    ] + prelude + WIZARD_CORE + [
        # wizard 后探针（会话内态）
        "Set MDL2_ = MGW_.GetMDL",
        "MGW_.RecognizeClosedVolume False",
        "Cvs_ = MDL2_.GetClosedVolumes()",
    ] + _ubound_guard("Cvs_") + [
        "Av0_ = MDL2_.IsClosedVolumeRestorationAvailable",
        _w("av0", "Av0_"),
        "Str0_ = MDL2_.GetStoredClosedVolumes(False)",
    ] + _ubound_guard("Str0_") + [
        # bam 结构尾段（模型状态经 main.sctsnapshot 内嵌的实证形态）
    ] + octree + [
        'Doc_.SaveProject "' + WIZ_OUT.as_posix() + '"',
    ]
    return [("wiz", actions)]


def build_restore_groups():
    """Store-and-Open 等价重开 + 恢复链（I3 cvrestore 骨架复用）。"""
    md_alive = ('out_.WriteLine "md2_alive=" '
                '& CStr(Not (MD2_ Is Nothing)) & " err=" & CStr(Err.Number)')
    ping = ('CreateObject("WScript.Shell").Run '
            '"cmd /c ping -n 6 127.0.0.1 > nul", 0, True')
    return [("restore", [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        "RetWW_ = Doc_.WaitForWorker",
        'Doc_.OpenProject "' + RESTORE_IN.as_posix() + '", False',
        ping, ping, ping,
        "Set MG2_ = Doc_.QueryMeshingGroupByIndex(0)",
        "MG2_.RecognizeClosedVolume False",
        "Set MD2_ = MG2_.GetMDL",
        "If MD2_ Is Nothing Then Set MD2_ = MG2_.GetMDL",
        md_alive,
        "Err.Clear",
        ping, ping,
        "If MD2_ Is Nothing Then Set MD2_ = MG2_.GetMDL",
        md_alive,
        "Err.Clear",
        "Str2_ = MD2_.GetStoredClosedVolumes(False)",
    ] + _ubound_guard("Str2_") + [
        "LB1_ = 0",
        "If IsArray(Str2_) Then LB1_ = LBound(Str2_)",
        "Cur2_ = MD2_.GetClosedVolumes()",
    ] + _ubound_guard("Cur2_") + [
        "LB0_ = 0",
        "If IsArray(Cur2_) Then LB0_ = LBound(Cur2_)",
        "Av1_ = MD2_.IsClosedVolumeRestorationAvailable",
        _w("av1", "Av1_"),
        "Err.Clear",
        # catalog：返回 VARIANT 数组（候选+相关度），Set 接收必 424（r6）
        "Cand_ = MD2_.GetRestorationCandidateOfClosedVolume(LB0_, True)",
    ] + _ubound_guard("Cand_") + [
        "Set Dest_ = Cur2_(LB0_)",
        "Set Src_ = Str2_(LB1_)",
        "Dim Pairs_(1)",
        "Set Pairs_(0) = Dest_",
        "Set Pairs_(1) = Src_",
        "RRet_ = MD2_.RestoreClosedVolumes(True, Pairs_)",
        _w("restore_ret", "RRet_"),
        "Err.Clear",
        'Doc_.SaveProject "' + RESTORE_OUT.as_posix() + '"',
    ])]


# ── 业务判定 ───────────────────────────────────────────────────────────────


_INFO_RE = re.compile(
    r"^([a-z0-9_]+)=(True|False|NA|-?\d+) err=(-?\d+)$", re.MULTILINE)


def business_info(text):
    return {m.group(1): m.group(2) for m in _INFO_RE.finditer(text)}


def business_state(info):
    if info.get("av1") == "True":
        return 1 if info.get("restore_ret") == "True" else 0
    return -1


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
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    which = argv[0] if argv else "all"
    results = {}
    M_DIR.mkdir(exist_ok=True)
    if not PATCH2.is_file():
        build_patch2_cube()
        print("[j1] patch2 cube STL built: " + str(PATCH2)
              + " (" + str(PATCH2.stat().st_size) + "B)", flush=True)

    def flow(name, groups, vbs_p, log_p, timeout, alive, min_checks,
             end_wait=600.0, idle_limit=1200.0, watch_modals=False,
             utf16=True, boot=True):
        from automation import modal_watch, host_boot
        if boot:
            pid = host_boot.cold_boot()
            print("[" + name + "] cold boot host pid " + str(pid),
                  flush=True)
        stop_evt = threading.Event()
        watcher = threading.Thread(target=_confirm_watchdog,
                                   args=(stop_evt,), daemon=True)
        watcher.start()
        try:
            writer = p12e._write_utf16_vbs if utf16 else p12e._write_ansi_vbs
            vbs = writer(
                p12e.logged_script(groups, log_p,
                                   "pphdecoding P12-M " + name),
                vbs_p, title="pphdecoding P12-M " + name + " e2e")
            res = p12e.run_e2e(name, vbs, log_p, timeout=timeout,
                               end_wait=end_wait, idle_limit=idle_limit,
                               watch_modals=watch_modals,
                               retry_with_boot=True)
        finally:
            stop_evt.set()
        results[name] = p12e.gate(name, res, alive_need=alive,
                                  min_checks=min_checks)
        return res

    if which in ("wiz", "all"):
        flow("wiz", build_wiz_groups(), WIZ_VBS, WIZ_LOG,
             timeout=2400.0, alive=("sn6_", "mgw_", "mdl2_"),
             min_checks=40)

    if which in ("restore", "all"):
        if not WIZ_OUT.is_file():
            raise SystemExit("wiz output missing: " + str(WIZ_OUT))
        p12e.wait_out_stable(WIZ_OUT)
        inject_his(dst_pph=WIZ_OUT)
        print("[j1] .his injected -> " + str(RESTORE_IN), flush=True)
        flow("restore", build_restore_groups(), RESTORE_VBS, RESTORE_LOG,
             timeout=1500.0,
             alive=("mg2_", "md2", "dest_", "src_"),
             min_checks=24)

    text = RESTORE_LOG.read_text(encoding="utf-8", errors="replace") \
        if RESTORE_LOG.is_file() else ""
    info = business_info(text)
    state = business_state(info)
    print("[j1] business info: " + json.dumps(info, ensure_ascii=False))
    print("[j1] BUSINESS restorable=" + str(state) + " (" + {
        1: "场景可构造 + RestoreClosedVolumes e2e 全绿（NYI 可解禁）",
        0: "restorable 但 restore retval!=True，delta 如实入册",
        -1: "IsClosedVolumeRestorationAvailable!=True，前置证据入册",
    }[state] + ")", flush=True)
    overall = bool(results) and all(results.values())
    print("SUMMARY: " + json.dumps(
        {"flows": results, "business": info, "restorable": state},
        ensure_ascii=False), flush=True)
    print("OVERALL: " + ("PASS" if overall else "FAIL"), flush=True)
    (M_DIR / "p12m_run_summary.json").write_text(
        json.dumps({"flows": results, "business": info,
                    "restorable": state}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
