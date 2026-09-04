"""宿主冷启动（P12-E boot 配方模块化，DEV_PLAN §20.1 I2）。

配方（2025.2 实测名）：Kicker_Bx64.exe → ``STPRE`` 按钮 BM_CLICK →
宿主进程 ``STpre_Bx64net`` → 启动期 Initial Wizard 模态 WM_CLOSE
处置。移植自 ``scratch/_p12e_boot.py``（实测可用版本），供批量
自愈基建在杀宿主后重建会话。
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import ctypes

from automation.modal_watch import close_dialogs, host_pids

user32 = ctypes.windll.user32
BM_CLICK = 0x00F5
SW_RESTORE = 9
KICKER = (r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64"
          r"\Kicker_Bx64.exe")
KICKER_DIR = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64"
BUTTON = "STPRE"
HOST_IMAGE = "STpre_Bx64net"


def _pids_via_ps(name: str) -> list[int]:
    return host_pids(name)


def kill_all_hosts(host_image: str = HOST_IMAGE) -> list[int]:
    """强杀全部宿主实例并返回仍未消失的 pid（空 = 清场干净）。

    I2 批量教训：挂起处置只杀单个 pid 可能留下僵尸宿主，僵尸与新
    宿主并存时 rot 附着会选到僵尸（其内 VBS 仍在跑），后续 flow 的
    OpenProject 被级联阻塞。cold_boot 前必须清场。
    """
    import time as _t
    stuck: list[int] = []
    for pid in _pids_via_ps(host_image):
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                       capture_output=True, text=True, timeout=15)
    # 按映像名兜底（/T 可能漏杀重父进程下的实例）
    subprocess.run(["taskkill", "/F", "/IM", host_image + ".exe"],
                   capture_output=True, text=True, timeout=15)
    deadline = _t.time() + 15.0
    while _t.time() < deadline:
        left = _pids_via_ps(host_image)
        if not left:
            return []
        stuck = left
        _t.sleep(1.0)
    return stuck


def _click_tool_button() -> bool:
    """在 Kicker 对话框上找到 ``STPRE`` 按钮并投递 BM_CLICK。

    pywinauto 仅用于枚举 Kicker 窗口树（按钮句柄定位），
    点击本身走 PostMessage，与 P12-E 实测配方一致。
    """
    from pywinauto import Application

    for kpid in _pids_via_ps("Kicker_Bx64"):
        try:
            app = Application().connect(process=kpid)
        except Exception:  # noqa: BLE001
            continue
        for dlg in app.windows():
            if dlg.class_name() != "#32770" or dlg.rectangle().width() <= 0:
                continue
            try:
                btns = [c for c in dlg.descendants()
                        if c.window_text() == BUTTON]
            except Exception:  # noqa: BLE001
                continue
            if btns:
                user32.ShowWindow(dlg.handle, SW_RESTORE)
                time.sleep(1)
                user32.PostMessageW(btns[0].handle, BM_CLICK, 0, 0)
                return True
    return False


def _wait_pids(name: str, timeout: float) -> list[int]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        ids = _pids_via_ps(name)
        if ids:
            return ids
        time.sleep(2)
    return []


def _dispose_startup_modals(pid: int, timeout: float = 90.0) -> list[str]:
    """启动期模态处置循环：出现即 WM_CLOSE，直到窗口干净且关闭过。"""
    deadline = time.time() + timeout
    closed: list[str] = []
    while time.time() < deadline:
        closed_now = close_dialogs(pid, None)
        if not closed_now:
            if closed:
                return closed
            time.sleep(2)
            continue
        closed.extend(d["title"] for d in closed_now)
        time.sleep(3)
    return closed


def _vbs_ready_probe(tries: int = 6, gap: float = 10.0) -> bool:
    """宿主 VBS 可达性健康检查（cold_boot 收尾用）。

    I2 表征：宿主冷启动后若 Initial Wizard 未弹出（初始化未走完），
    ExecuteVBSWithFile 一律恒 ~5s 返回 False（对任何脚本，含一行
    probe）；wizard 正常弹出并处置过的宿主则一切可达。因此 boot
    尾部探测一次：False 则宿主不可用，交由调用方重试。
    """
    import tempfile
    from automation import scflowpre_api

    log = Path(tempfile.gettempdir()) / "pphdecoding_boot_probe.log"
    vbs = Path(tempfile.gettempdir()) / "pphdecoding_boot_probe.vbs"
    vbs.write_bytes((
        'Dim f_, o_\r\n'
        'Set f_ = CreateObject("Scripting.FileSystemObject")\r\n'
        'Set o_ = f_.CreateTextFile("%s", True)\r\n'
        'o_.WriteLine "alive"\r\n'
        'o_.Close\r\n' % log.as_posix().replace("\\", "/")
    ).encode("mbcs"))
    for _ in range(tries):
        log.unlink(missing_ok=True)
        s = scflowpre_api.ScFlowpreSession()
        try:
            if not s.connect():
                time.sleep(gap)
                continue
            if s.execute_vbs_file(vbs) and log.is_file() \
                    and b"alive" in log.read_bytes():
                return True
        except Exception:  # noqa: BLE001
            pass
        finally:
            s.close()
        time.sleep(gap)
    return False


def cold_boot(*, kicker_path: str = KICKER,
              button: str = BUTTON,
              host_image: str = HOST_IMAGE,
              host_timeout: float = 180.0,
              modal_timeout: float = 90.0,
              dispose_modals: bool = True) -> int:
    """冷启动一个干净宿主会话，返回宿主 pid（失败抛 RuntimeError）。

    若 Kicker 未运行则先拉起；随后 6 次重试点击按钮、等宿主进程、
    处置启动期模态。启动前先清场杀掉全部现存宿主实例——僵尸宿主
    留在 ROT 里会让后续 rot 附着选错实例（I2 批量级联挂起根因）。

    ``dispose_modals=False`` 保留启动期 Initial Wizard 模态：
    I2 实证 wrap replay 的 ``MeshingGroup_.GetMDL()`` 依赖 wizard
    模态在场（wizard 被 WM_CLOSE 后全程 Nothing → MDL_/ClosedVolume_
    批量 424；8/30 wizard 未处置的会话同脚本 3501 全 0）。
    """
    stuck = kill_all_hosts(host_image)
    if stuck:
        raise RuntimeError(
            "stale host processes survived cleanup: " + str(stuck))
    if not _pids_via_ps("Kicker_Bx64"):
        subprocess.Popen([kicker_path], cwd=KICKER_DIR)
        if not _wait_pids("Kicker_Bx64", 60):
            raise RuntimeError("kicker did not start")
        time.sleep(8)  # 对话框 settle
    clicked = False
    for _ in range(6):
        if _click_tool_button():
            clicked = True
            break
        time.sleep(5)
    if not clicked:
        raise RuntimeError(button + " button not found")
    host = _wait_pids(host_image, host_timeout)
    if not host:
        raise RuntimeError("host did not start")
    pid = host[0]
    if dispose_modals:
        _dispose_startup_modals(pid, modal_timeout)
    time.sleep(5)
    # VBS 可达性健康检查：wizard 未弹出（初始化未完）的宿主对一切
    # ExecuteVBSWithFile 恒 False（I2 表征）——不可用则整体重试一次。
    if _vbs_ready_probe():
        return pid
    stuck = kill_all_hosts(host_image)
    if not _pids_via_ps("Kicker_Bx64"):
        subprocess.Popen([kicker_path], cwd=KICKER_DIR)
        if not _wait_pids("Kicker_Bx64", 60):
            raise RuntimeError("kicker did not start (retry)")
        time.sleep(8)
    clicked = False
    for _ in range(6):
        if _click_tool_button():
            clicked = True
            break
        time.sleep(5)
    if not clicked:
        raise RuntimeError(button + " button not found (retry)")
    host = _wait_pids(host_image, host_timeout)
    if not host:
        raise RuntimeError("host did not start (retry)")
    pid = host[0]
    if dispose_modals:
        _dispose_startup_modals(pid, modal_timeout)
    time.sleep(5)
    if not _vbs_ready_probe():
        raise RuntimeError("host booted but VBS channel not reachable")
    return pid
