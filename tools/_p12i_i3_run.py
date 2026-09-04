"""P12-I I3 实机 e2e：Restore Closed Volume Data 场景收口（域 10）。

宿主帮助页钉死前置（Scf_pre_Edit-Restore_Closed_Volume_Data.html，
2025.2 安装原文）：``This function can only be used in the following
case: Patch data has been imported. And another patch data is
re-imported and [Store and Open] is selected at that time.``

**场景构造（r2，2026-09-04 深夜重跑）**——r1（box.pph 基座 + blades
STL 重导）钉死两条环境事实后重整：

- box.pph 是 2023.2 CAB 工程，OpenProject 会弹 ``Confirm``（CAB 版本
  警告）模态，后续 COM 全部排在模态后（③ 同型挂起）；r1 的
  ``ImportPatchAsCAD(blades 458KB)`` 在新旧宿主上均研磨 10min+ 且
  part.mdl 仅 +347B（几何未落地），再导探针甚至打断宿主进程
  （RPC -2147023170）。→ 基座改用 r1 产物 ``p12i_cv1_out.pph``
  （2025.2 宿主自存、无 CAB 弹窗、**已含 patch① 导入史 +
  meshinggroup1_restore_cvol.his 存储史**），昂贵的 STL 重导腿
  不再重复。
- Confirm 类模态由驱动侧 ``modal_watch.click_confirm_yes``
  （BM_CLICK「是」——WM_CLOSE 等价「否」不可用）后台看守点掉。

两流（单宿主会话内顺序执行，rot 权威通道）：

- **cvstore**（场景构造①）：OpenProject(p12i_cv1_out.pph，patch①
  导入史 + 闭体积存储史继承) → ``MG_.RecognizeClosedVolume False``
  → ``MDL_=GetMDL`` → GetClosedVolumes 边界 →
  ``IsClosedVolumeRestorationAvailable`` 基线 →
  ``StoreClosedVolumes`` → GetStoredClosedVolumes 边界 →
  SaveProject(p12i_cv1b_out.pph)。
- **cvrestore**（场景构造② = 另一 patch 再导入 + Store-and-Open）：
  WaitForWorker → ``ImportPatchAsCAD(sample_cube STL)``（帮助前置：
  另一 patch 再导入；若弹 Confirm 由看守点「是」）→
  SaveProject(p12i_cv2b_out.pph) → OpenProject(p12i_cv2b_out.pph)
  （[Store and Open] API 等价）→ ping 退避重取 MG2_/MD2_ →
  ``IsClosedVolumeRestorationAvailable``（菜单解灰 API 等价）→
  GetStoredClosedVolumes / GetClosedVolumes →
  GetRestorationCandidateOfClosedVolume → Dim+Set 构造 CVolPairs
  （避免 Array() 整型字面量 VT_I2 AV）→ ``RestoreClosedVolumes`` →
  SaveProject(p12i_cv_restore2_out.pph)。

业务三态（先记录后判定，沿 §20.2 I5 口径）：

- ``restorable=1``（av=True 且 restore retval=True）→ 场景可构造、
  e2e 全绿，NYI 边界项可解禁；
- ``restorable=0``（av=True 但 restore retval≠True）→ err=0 但业务
  不过，delta 如实入册（Actran 处置先例）；
- ``restorable=-1``（av≠True）→ 前置不可构造证据入册，边界维持
  （I3 验收句第二分支）。

r1 表征证据（`_p12i_e2e/r1_*.log` 归档）：存储腿跨 Save/Open 持久化
成立（``meshinggroup1_restore_cvol.his`` 12825B 新产物 + oct
101889→182857 + 重开后 str2/cur2 各 1 项、dest_/src_ 均 alive）；
av1=False + restore_ret=False 与「再导入腿未成立（sn6 Nothing）」
自洽。

用法：``py tools/_p12i_i3_run.py [cvstore|cvrestore|all]``
"""

from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "_p12e_e2e_run", ROOT / "tools" / "_p12e_e2e_run.py")
p12e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p12e)

I_DIR = ROOT / "_p12i_e2e"
# r1 产物作 r2 基座（2025.2 宿主自存：无 CAB Confirm、无 sctsnapshot）
CV1_OUT = ROOT / "p12i_cv1_out.pph"
CVSTORE_VBS = ROOT / "p12i_cvstore_e2e.vbs"
CVSTORE_LOG = ROOT / "p12i_cvstore_e2e.log"
CV1B_OUT = ROOT / "p12i_cv1b_out.pph"
CVRESTORE_VBS = ROOT / "p12i_cvrestore_e2e.vbs"
CVRESTORE_LOG = ROOT / "p12i_cvrestore_e2e.log"
CV2B_OUT = ROOT / "p12i_cv2b_out.pph"
CV_RESTORE2_OUT = ROOT / "p12i_cv_restore2_out.pph"
PATCH2 = I_DIR / "p12i_patch2_sample_cube.stl"
PATCH2_SRC = Path(
    "D:/training/caedecoder/cradlefolk-glm/tests/sample_cube.stl")

HOST_IMAGE = "scFLOWpre_Bx64net"


def _ensure_patches():
    if not PATCH2.is_file():
        if not PATCH2_SRC.is_file():
            raise SystemExit("patch sample missing: " + str(PATCH2_SRC))
        PATCH2.write_bytes(PATCH2_SRC.read_bytes())


def _w(key, expr):
    """诊断行：``KEY=<expr> err=``（随行捕获探针错误码）。"""
    return ('out_.WriteLine "' + key + '=" & CStr(' + expr + ')'
            ' & " err=" & CStr(Err.Number)')


def _ubound_guard(var):
    """IsArray 守卫的边界探针（空/非数组时记 NA，不污染 err 流）。"""
    lo = var.rstrip("_").lower() + "_ub"
    return [
        "If IsArray(" + var + ") Then " + _w(lo, "UBound(" + var + ")")
        + " Else out_.WriteLine \"" + lo + "=NA err=0\"",
    ]


# ── 流程构造 ───────────────────────────────────────────────────────────────


def build_cvstore_groups():
    return [("cvstore", [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        "RetWW_ = Doc_.WaitForWorker",
        'Doc_.OpenProject "' + CV1_OUT.as_posix() + '", False',
        "Set MG_ = Doc_.QueryMeshingGroupByIndex(0)",
        # 闭体积识别（fluid 侧：box 内腔）
        "MG_.RecognizeClosedVolume False",
        "Set MDL_ = MG_.GetMDL",
        "Cvs_ = MDL_.GetClosedVolumes()",
    ] + _ubound_guard("Cvs_") + [
        "Av0_ = MDL_.IsClosedVolumeRestorationAvailable",
        _w("av0", "Av0_"),
        "SRet_ = MDL_.StoreClosedVolumes()",
        _w("store_ret", "SRet_"),
        "Str_ = MDL_.GetStoredClosedVolumes(False)",
    ] + _ubound_guard("Str_") + [
        'Doc_.SaveProject "' + CV1B_OUT.as_posix() + '"',
    ])]


def build_cvrestore_groups():
    # OpenProject 后 MDL 成员恢复滞后主工程反序列化（I2 reopen 同型）：
    # ping 退避 + 单行重查；alive 行手工补写（If 行不触发自动探针）。
    # r2 钉死：ImportPatchAsCAD 成功路径 = 组内换件（同文档、条件
    # 保留，<mdl> 闭体积块被重置，成员文件落盘滞后）——再导入后须
    # WaitForWorker + RecognizeClosedVolume 重建 MDL，重开后同。
    md_alive = ('out_.WriteLine "md2_alive=" '
                '& CStr(Not (MD2_ Is Nothing)) & " err=" & CStr(Err.Number)')
    ping = ('CreateObject("WScript.Shell").Run '
            '"cmd /c ping -n 6 127.0.0.1 > nul", 0, True')
    return [("cvrestore", [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        "RetWW_ = Doc_.WaitForWorker",
        # 帮助前置②：另一 patch 数据再导入（Confirm 弹窗由看守点「是」）
        'Set SN6_ = Doc_.ImportPatchAsCAD("' + PATCH2.as_posix() + '")',
        "RetWW2_ = Doc_.WaitForWorker",
        "Set MG1_ = Doc_.QueryMeshingGroupByIndex(0)",
        "MG1_.RecognizeClosedVolume False",
        "Set MD1_ = MG1_.GetMDL",
        "Cvs1_ = MD1_.GetClosedVolumes()",
    ] + _ubound_guard("Cvs1_") + [
        # [Store and Open] API 等价：SaveProject → OpenProject
        'Doc_.SaveProject "' + CV2B_OUT.as_posix() + '"',
        'Doc_.OpenProject "' + CV2B_OUT.as_posix() + '", False',
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
        # 菜单解灰 API 等价
        "Av1_ = MD2_.IsClosedVolumeRestorationAvailable",
        _w("av1", "Av1_"),
        "Err.Clear",
        "Str2_ = MD2_.GetStoredClosedVolumes(False)",
    ] + _ubound_guard("Str2_") + [
        "LB1_ = 0",
        "If IsArray(Str2_) Then LB1_ = LBound(Str2_)",
        "Cur2_ = MD2_.GetClosedVolumes()",
    ] + _ubound_guard("Cur2_") + [
        "LB0_ = 0",
        "If IsArray(Cur2_) Then LB0_ = LBound(Cur2_)",
        # 默认配对候选（帮助 Note：位置/体积几乎相同的组合默认置入）
        "Set Cand_ = MD2_.GetRestorationCandidateOfClosedVolume(LB0_, True)",
        "Set Dest_ = Cur2_(LB0_)",
        "Set Src_ = Str2_(LB1_)",
        # CVolPairs：偶数位=恢复目标，奇数位=存储源（Multiple of 2/2+1）
        "Dim Pairs_(1)",
        "Set Pairs_(0) = Dest_",
        "Set Pairs_(1) = Src_",
        "RRet_ = MD2_.RestoreClosedVolumes(True, Pairs_)",
        _w("restore_ret", "RRet_"),
        "Err.Clear",
        'Doc_.SaveProject "' + CV_RESTORE2_OUT.as_posix() + '"',
    ])]


# ── 业务判定 ───────────────────────────────────────────────────────────────


_INFO_RE = re.compile(
    r"^([a-z0-9_]+)=(True|False|NA|-?\d+) err=(-?\d+)$", re.MULTILINE)


def business_info(text):
    return {m.group(1): m.group(2) for m in _INFO_RE.finditer(text)}


def business_state(info):
    """1=场景可构造且恢复成功；0=restorable 但恢复 retval≠True；
    -1=restoration 不可用（前置不可构造证据）。"""
    if info.get("av1") == "True":
        return 1 if info.get("restore_ret") == "True" else 0
    return -1


# ── 驱动 ───────────────────────────────────────────────────────────────────


def _confirm_watchdog(stop_evt: threading.Event) -> None:
    """流程执行期后台看守：Confirm 模态点「是」（CAB/导入确认）。"""
    from automation import modal_watch
    while not stop_evt.is_set():
        try:
            for hp in modal_watch.host_pids(HOST_IMAGE):
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
    results = {}
    I_DIR.mkdir(exist_ok=True)
    _ensure_patches()

    def flow(name, groups, vbs_p, log_p, timeout=900.0, alive=(),
             min_checks=1, end_wait=300.0, idle_limit=900.0):
        from automation import modal_watch
        for _hp in modal_watch.host_pids(HOST_IMAGE):
            _closed = modal_watch.close_dialogs(_hp, None)
            _yes = modal_watch.click_confirm_yes(_hp)
            if _closed or _yes:
                print("[" + name + "] pre-flow modal: "
                      + json.dumps([d.get("title") for d in _closed]
                                   + [d.get("title") for d in _yes],
                                   ensure_ascii=False), flush=True)
        stop_evt = threading.Event()
        watcher = threading.Thread(target=_confirm_watchdog,
                                   args=(stop_evt,), daemon=True)
        watcher.start()
        try:
            vbs = p12e._write_ansi_vbs(
                p12e.logged_script(groups, log_p,
                                   "pphdecoding P12-I " + name),
                vbs_p, title="pphdecoding P12-I " + name + " e2e")
            res = p12e.run_e2e(name, vbs, log_p, timeout=timeout,
                               end_wait=end_wait, idle_limit=idle_limit,
                               watch_modals=True, retry_with_boot=True)
        finally:
            stop_evt.set()
        results[name] = p12e.gate(name, res, alive_need=alive,
                                  min_checks=min_checks)
        return res

    if which in ("cvstore", "all"):
        flow("cvstore", build_cvstore_groups(), CVSTORE_VBS, CVSTORE_LOG,
             alive=("mg_", "mdl_"), min_checks=14)

    if which in ("cvrestore", "all"):
        p12e.wait_out_stable(CV1B_OUT)
        res = flow("cvrestore", build_cvrestore_groups(), CVRESTORE_VBS,
                   CVRESTORE_LOG, timeout=1200.0, end_wait=600.0,
                   # md2（手工行）= 重查后的最终状态；md2_（自动探针）
                   # 定格在首次 GetMDL，不进 gate
                   alive=("sn6_", "mg2_", "md2", "dest_", "src_"),
                   min_checks=26)

    text = CVRESTORE_LOG.read_text(encoding="utf-8", errors="replace") \
        if CVRESTORE_LOG.is_file() else ""
    info = business_info(text)
    state = business_state(info)
    print("[i3] business info: " + json.dumps(info, ensure_ascii=False))
    print("[i3] BUSINESS restorable=" + str(state) + " (" + {
        1: "场景可构造 + RestoreClosedVolumes e2e 全绿",
        0: "restorable 但 restore retval!=True，delta 如实入册",
        -1: "IsClosedVolumeRestorationAvailable=False，前置不可构造证据",
    }[state] + ")", flush=True)
    overall = bool(results) and all(results.values())
    print("SUMMARY: " + json.dumps(
        {"flows": results, "business": info, "restorable": state},
        ensure_ascii=False), flush=True)
    print("OVERALL: " + ("PASS" if overall else "FAIL"), flush=True)
    (I_DIR / "p12i_run_summary.json").write_text(
        json.dumps({"flows": results, "business": info,
                    "restorable": state}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
