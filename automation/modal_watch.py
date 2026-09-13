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
BM_CLICK = 0x00F5
DIALOG_CLASS = "#32770"

user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
EnumChildProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


#: R3-1：进程枚举改走 Toolhelp32 快照（纯 ctypes，毫秒级、无子进程）。
#: 原实现用 ``powershell Get-Process`` 且 20 s 上限：重网格计算期间整机
#: 繁忙，PowerShell 冷启动可超 20 s → ``TimeoutExpired`` 直接崩掉 flow
#: （``_p12u_gate/r13_step_mesh.log`` 实测）；更糟的是探针无输出会被判成
#: 宿主消失而误杀健康宿主（``hang_characterization.jsonl`` step_mesh 行）。
TH32CS_SNAPPROCESS = 0x00000002
MAX_PATH = 260
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
STILL_ACTIVE = 259


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * MAX_PATH)]


def _kernel32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k.Process32FirstW.restype = wintypes.BOOL
    k.Process32FirstW.argtypes = [ctypes.c_void_p,
                                  ctypes.POINTER(_PROCESSENTRY32W)]
    k.Process32NextW.restype = wintypes.BOOL
    k.Process32NextW.argtypes = [ctypes.c_void_p,
                                 ctypes.POINTER(_PROCESSENTRY32W)]
    k.CloseHandle.restype = wintypes.BOOL
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    k.OpenProcess.restype = ctypes.c_void_p
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.GetExitCodeProcess.restype = wintypes.BOOL
    k.GetExitCodeProcess.argtypes = [ctypes.c_void_p,
                                     ctypes.POINTER(wintypes.DWORD)]
    return k


#: R5-1：进程活性/资源探针（同样是纯 ctypes）。网格计算期间日志必然长时间
#: 不动，只按日志静默判活会误杀正常计算；CPU 在推进是唯一可靠的"还在干活"
#: 信号。内存在宿主消失后问不到，必须在**它还在**的时候采样。
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x00000008


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD),
                ("dwHighDateTime", wintypes.DWORD)]


class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


def process_memory(pid: int) -> dict | None:
    """进程内存画像（WS / 峰值 WS / 提交），失败返回 None。"""
    try:
        k = _kernel32()
        h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return None
        try:
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            psapi.GetProcessMemoryInfo.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(_PROCESS_MEMORY_COUNTERS),
                wintypes.DWORD]
            c = _PROCESS_MEMORY_COUNTERS()
            c.cb = ctypes.sizeof(_PROCESS_MEMORY_COUNTERS)
            if not psapi.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb):
                return None
            mb = 1048576.0
            return {"pid": int(pid),
                    "ws_mb": round(c.WorkingSetSize / mb, 1),
                    "peak_ws_mb": round(c.PeakWorkingSetSize / mb, 1),
                    "pagefile_mb": round(c.PagefileUsage / mb, 1)}
        finally:
            k.CloseHandle(h)
    except Exception:  # noqa: BLE001
        return None


def process_cpu_seconds(pid: int) -> float | None:
    """进程累计 CPU 秒数（kernel+user），失败返回 None。"""
    try:
        k = _kernel32()
        k.GetProcessTimes.restype = wintypes.BOOL
        k.GetProcessTimes.argtypes = [ctypes.c_void_p,
                                      ctypes.POINTER(_FILETIME),
                                      ctypes.POINTER(_FILETIME),
                                      ctypes.POINTER(_FILETIME),
                                      ctypes.POINTER(_FILETIME)]
        h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return None
        try:
            c_, e_, kern, usr = _FILETIME(), _FILETIME(), _FILETIME(), _FILETIME()
            if not k.GetProcessTimes(h, ctypes.byref(c_), ctypes.byref(e_),
                                     ctypes.byref(kern), ctypes.byref(usr)):
                return None
            def _secs(ft) -> float:
                return ((ft.dwHighDateTime << 32) | ft.dwLowDateTime) / 1e7
            return _secs(kern) + _secs(usr)
        finally:
            k.CloseHandle(h)
    except Exception:  # noqa: BLE001
        return None


def total_cpu_seconds(pids) -> float | None:
    """一组进程的 CPU 秒数之和；一个都问不到时返回 None（未知）。"""
    vals = [process_cpu_seconds(p) for p in pids]
    got = [v for v in vals if v is not None]
    if not got:
        return None
    return float(sum(got))


def host_and_worker_cpu(host_image: str = "STpre_Bx64net",
                        work_image: str = "scFLOWpre_Bx64net") -> float | None:
    """宿主 + 工作进程的 CPU 秒数（网格计算跑在工作进程里）。"""
    try:
        pids = host_pids(host_image) + host_pids(work_image)
    except Exception:  # noqa: BLE001
        return None
    return total_cpu_seconds(pids)


def host_pids_toolhelp(image_name: str = "STpre_Bx64net") -> list[int]:
    """按映像名枚举 pid（Toolhelp32 快照；不区分扩展名，同 Get-Process 语义）。"""
    k = _kernel32()
    snap = k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == ctypes.c_void_p(-1).value:
        raise OSError("CreateToolhelp32Snapshot failed")
    want = image_name.lower()
    if want.endswith(".exe"):
        want = want[:-4]
    pids: list[int] = []
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        ok = k.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            exe = entry.szExeFile or ""
            stem = exe[:-4] if exe.lower().endswith(".exe") else exe
            if stem.lower() == want:
                pids.append(int(entry.th32ProcessID))
            ok = k.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k.CloseHandle(snap)
    return pids


def pid_alive(pid: int) -> bool:
    """pid 是否存活（OpenProcess + GetExitCodeProcess；无子进程）。"""
    k = _kernel32()
    h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE,
                      False, int(pid))
    if not h:
        return False
    try:
        code = wintypes.DWORD()
        if not k.GetExitCodeProcess(h, ctypes.byref(code)):
            return True          # 有句柄但读不到退出码 → 保守当作存活
        return int(code.value) == STILL_ACTIVE
    finally:
        k.CloseHandle(h)


def _host_pids_powershell(image_name: str = "STpre_Bx64net") -> list[int]:
    """回退探针（仅快照不可用时）。超时向上抛，由调用方判为未知。"""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process " + image_name + " -ErrorAction SilentlyContinue "
         "| Select-Object -ExpandProperty Id"],
        capture_output=True, text=True, timeout=60).stdout.split()
    return [int(p) for p in out if p.isdigit()]


def host_pids(image_name: str = "STpre_Bx64net") -> list[int]:
    """宿主 pid 列表：优先 Toolhelp32 快照；非 Windows / 快照失败才回退 PowerShell。"""
    try:
        return host_pids_toolhelp(image_name)
    except Exception:  # noqa: BLE001
        return _host_pids_powershell(image_name)


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
        if not title:
            return True
        if title_contains is not None and title_contains not in title:
            return True
        hits.append({"hwnd": hwnd, "title": title})
        return True

    _enum(cb)
    return hits


def visible_windows(pid: int, *, _enum=_enum_top_windows,
                    _text=_window_text, _cls=_class_name,
                    _wpid=_window_pid, _vis=_is_visible) -> list[dict]:
    """枚举进程全部可见顶层窗口（class+title，诊断用，不限 #32770）。"""
    hits: list[dict] = []

    def cb(hwnd, _lparam):
        if _wpid(hwnd) != pid or not _vis(hwnd):
            return True
        hits.append({"hwnd": hwnd, "cls": _cls(hwnd),
                     "title": _text(hwnd)})
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


def _enum_child_windows(cb, hwnd: int, *, _enum=None) -> None:
    user32.EnumChildWindows(hwnd, EnumChildProc(cb), 0)


def find_confirm_yes(pid: int | None = None, *,
                     _enum=_enum_top_windows, _text=_window_text,
                     _cls=_class_name, _wpid=_window_pid,
                     _vis=_is_visible,
                     _children=_enum_child_windows) -> list[dict]:
    """定位标题 ``Confirm`` 的 Yes/No 模态及其「是/Y」按钮。

    实测（2026-09-04 I3）：2023.2 CAB 工程载入（OpenProject box.pph）
    与 patch 导入路径会弹标题 ``Confirm`` 的 Yes/No 模态，后续 COM
    调用全部排在模态之后——``WM_CLOSE`` 等价「否」，须 BM_CLICK
    「是」按钮才继续。返回 ``[{"hwnd", "title", "yes_hwnd"}]``。
    """
    hits: list[dict] = []

    def cb(hwnd, _lparam):
        if pid is not None and _wpid(hwnd) != pid:
            return True
        if not _vis(hwnd) or _cls(hwnd) != DIALOG_CLASS:
            return True
        if _text(hwnd) != "Confirm":
            return True
        state = {"yes_hwnd": None}

        def child(ch, _lp):
            if state["yes_hwnd"] is None and _cls(ch) == "Button":
                t = _text(ch)
                if "是" in t or "&Y" in t or t.strip() == "Y(&Y)":
                    state["yes_hwnd"] = ch
                    return False
            return True

        _children(child, hwnd)
        hits.append({"hwnd": hwnd, "title": _text(hwnd),
                     "yes_hwnd": state["yes_hwnd"]})
        return True

    _enum(cb)
    return hits


def click_confirm_yes(pid: int | None = None, *,
                      _find=find_confirm_yes, _click=None) -> list[dict]:
    """对 Confirm 模态点「是」，返回点击列表（无按钮则跳过）。"""
    click = _click or (lambda hwnd: bool(
        user32.PostMessageW(hwnd, BM_CLICK, 0, 0)))
    clicked = []
    for dlg in _find(pid):
        if dlg.get("yes_hwnd") and click(dlg["yes_hwnd"]):
            clicked.append(dlg)
    return clicked


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
