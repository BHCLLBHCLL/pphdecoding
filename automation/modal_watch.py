"""宿主模态看守：阻塞模态的发现 / 关闭 / 后台看守。

P12-E 实测：宿主 ``OpenProject`` 会弹出 "Initial Wizard Project
( 1/6 ) step" 模态阻塞 VBS 线程（§18.4 遗留③伴随现象）；对其
``WM_CLOSE`` 后阻塞调用随宿主取消路径返回。本模块把该配方模块化，
供批量编排器在流程执行期间后台看守（DEV_PLAN §20.1 I1/I2）。

枚举与投递均走纯 ctypes，不依赖 pywinauto；``find_visible_dialogs``
/``close_dialogs``/``ModalWatcher`` 的底层探针可注入替换以便离线
单测。
"""
from __future__ import annotations

import subprocess
import threading
import time
from ctypes import wintypes

import ctypes

WM_CLOSE = 0x0010
DIALOG_CLASS = "#32770"

user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def host_pids(image_name: str = "STpre_Bx64net") -> list[int]:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process " + image_name + " -ErrorAction SilentlyContinue "
         "| Select-Object -ExpandProperty Id"],
        capture_output=True, text=True, timeout=20).stdout.split()
    return [int(p) for p in out]


def _window_text(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def _class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _enum_top_windows(cb) -> None:
    user32.EnumWindows(EnumWindowsProc(cb), 0)


def _is_visible(hwnd: int) -> bool:
    return bool(user32.IsWindowVisible(hwnd))


def find_visible_dialogs(pid: int | None = None,
                         title_contains: str | None = None,
                         *, _enum=_enum_top_windows,
                         _text=_window_text, _cls=_class_name,
                         _wpid=_window_pid,
                         _vis=_is_visible) -> list[dict]:
    """枚举可见 ``#32770`` 对话框（可选 pid / 标题子串过滤）。"""
    hits: list[dict] = []

    def cb(hwnd, _lparam):
        if pid is not None and _wpid(hwnd) != pid:
            return True
        if not _vis(hwnd):
            return True
        if _cls(hwnd) != DIALOG_CLASS:
            return True
        title = _text(hwnd)
        if title_contains is not None and title_contains not in title:
            return True
        hits.append({"hwnd": hwnd, "title": title})
        return True

    _enum(cb)
    return hits


def close_dialogs(pid: int | None = None,
                  title_contains: str | None = "Initial Wizard",
                  *, _find=find_visible_dialogs,
                  _post=None) -> list[dict]:
    """对匹配模态投递 ``WM_CLOSE``，返回实际关闭列表。"""
    post = _post or (lambda hwnd: user32.PostMessageW(hwnd, WM_CLOSE, 0, 0))
    closed = []
    for dlg in _find(pid, title_contains):
        if post(dlg["hwnd"]):
            closed.append(dlg)
    return closed


class ModalWatcher:
    """后台线程周期关闭匹配模态。

    用法::

        with ModalWatcher(pid=host_pid) as w:
            run_flow()
        print(w.closures)
    """

    def __init__(self, pid: int | None = None,
                 title_contains: str | None = "Initial Wizard",
                 interval: float = 1.0,
                 *, _find=find_visible_dialogs, _post=None):
        self.pid = pid
        self.title_contains = title_contains
        self.interval = interval
        self.closures: list[dict] = []
        self._find = _find
        self._post = _post
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def watch_once(self) -> int:
        closed = close_dialogs(self.pid, self.title_contains,
                               _find=self._find, _post=self._post)
        for dlg in closed:
            dlg["t"] = time.time()
        self.closures.extend(closed)
        return len(closed)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.watch_once()
            except Exception:  # noqa: BLE001 - 看守线程绝不中断主流程
                pass
            self._stop.wait(self.interval)

    def start(self) -> "ModalWatcher":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> list[dict]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval * 3)
            self._thread = None
        return self.closures

    def __enter__(self) -> "ModalWatcher":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
