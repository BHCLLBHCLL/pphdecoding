"""Run the NativeBridge pipeline inside the scFLOWpre host via VBScript.

The bridge DLL is registered as a per-user in-proc COM server
(``pphdecoding.ScflowPipeline``). A VBScript executed inside the host
(File -> Execute VBScript) creates that object, so the bridge runs in the
host process where the SCTprime document context is already initialized.

Backends:

- ``manual``: write the script and ask the user to run it in the host;
- ``com``: ``Application.ExecuteVBSWithFile`` / ``ExecuteVBS`` via win32com
  (must ``_FlagAsMethod`` — late binding otherwise exposes them as bool props);
- ``gui``: best-effort pywinauto automation of File -> Execute VBScript.

宿主验证环境事实（2026-08-17 实测，规范记录见 DEV_SUMMARY §6.3 前置块）：
本机 CradleCFD2025.2 已安装、许可 27500@localhost 可达、Kicker 实例常驻。
COM ``Dispatch`` 会经 LocalServer32 拉起**瞬态新实例**（非 Kicker 注入，
SCTprime 全局上下文为空 → ``ContextReady`` 为 0，pipeline 调用返回
SCF_ERR_CONTEXT_NOT_READY）；命令类脚本（Open/Save/条件/网格）在该瞬态
实例内为真 in-proc 且实测可用。SCTprime 管线（CreateShapeGroupSet 等）
必须走 Kicker 实例：宿主内 File → Execute VBScript（gui/manual 后端）。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import scflowpre_probe
from automation.history_vbs import decode_vbs
from automation.vbs_bridge import write_vbs_file

CLSID = "{9F8D2C1A-3B4E-4C5D-8E6F-1A2B3C4D5E6F}"
PROGID = "pphdecoding.ScflowPipeline"
PROGID_HOST = "scFLOWpre_Bx64net.Application.2025"

_REG_ROOT = r"Software\Classes"


def _write_reg_string(root, path: str, name: str, value: str) -> None:
    import winreg

    key = winreg.CreateKeyEx(root, path, 0, winreg.KEY_WRITE)
    try:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    finally:
        winreg.CloseKey(key)


def _delete_reg_tree(root, path: str) -> None:
    import winreg

    try:
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        return
    except OSError:
        # Key still has subkeys; recurse.
        try:
            key = winreg.OpenKey(root, path, 0, winreg.KEY_READ)
        except FileNotFoundError:
            return
        subkeys: list[str] = []
        try:
            i = 0
            while True:
                try:
                    subkeys.append(winreg.EnumKey(key, i))
                    i += 1
                except OSError:
                    break
        finally:
            winreg.CloseKey(key)
        for sub in subkeys:
            _delete_reg_tree(root, f"{path}\\{sub}")
        try:
            winreg.DeleteKey(root, path)
        except FileNotFoundError:
            pass


def register_com(dll_path: Optional[str | Path] = None) -> dict:
    """Register the bridge as a per-user in-proc COM server (HKCU)."""
    import winreg

    import native_bridge

    dll = Path(dll_path) if dll_path else native_bridge.BRIDGE_DLL
    dll = dll.resolve()
    if not dll.is_file():
        raise FileNotFoundError(f"bridge DLL not found: {dll}")
    clsid_root = f"{_REG_ROOT}\\CLSID\\{CLSID}"
    inproc = clsid_root + "\\InprocServer32"
    progid_root = f"{_REG_ROOT}\\{PROGID}"
    _write_reg_string(winreg.HKEY_CURRENT_USER, clsid_root, "", PROGID)
    _write_reg_string(winreg.HKEY_CURRENT_USER, inproc, "", str(dll))
    _write_reg_string(winreg.HKEY_CURRENT_USER, inproc,
                      "ThreadingModel", "Apartment")
    _write_reg_string(winreg.HKEY_CURRENT_USER, progid_root, "",
                      "pphdecoding NativeBridge pipeline")
    _write_reg_string(winreg.HKEY_CURRENT_USER, progid_root + "\\CLSID",
                      "", CLSID)
    return {"registered": True, "dll": str(dll), "clsid": CLSID,
            "progid": PROGID}


def unregister_com() -> dict:
    """Remove the per-user COM registration (ignores missing keys)."""
    import winreg

    _delete_reg_tree(winreg.HKEY_CURRENT_USER, f"{_REG_ROOT}\\CLSID\\{CLSID}")
    _delete_reg_tree(winreg.HKEY_CURRENT_USER, f"{_REG_ROOT}\\{PROGID}")
    return {"registered": False}


def build_pipeline_vbs(result_path: str | Path,
                       set_name: str = "Probe",
                       group_name: str = "ProbeGroup",
                       project_path: Optional[str | Path] = None,
                       output: Optional[str | Path] = None) -> Path:
    """Write the VBS that drives the COM bridge inside the host."""
    result_path = Path(result_path).resolve()
    lines = [
        "' pphdecoding NativeBridge host pipeline",
        "' !! 仅限在 scFLOWpre 宿主内执行（File → Execute VBScript）。",
        "' !! 不要用 wscript/cscript 运行：下面的 CreateObject 兜底会触发",
        "' !! LocalServer 激活拉起裸 exe（绕过 Kicker 的许可注入）并崩溃",
        "' !! （SetupSCTpreLib RaiseException 0xE0000000，见 DEV_SUMMARY §6）。",
        "On Error Resume Next",
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        'Set fso = CreateObject("Scripting.FileSystemObject")',
        f'Set out = fso.CreateTextFile("{result_path}", True)',
    ]
    if project_path is not None:
        lines.append(f'Doc_.OpenProject "{Path(project_path)}", False')
        lines.append('out.WriteLine "open_err=" & CStr(Err.Number)')
        lines.append("Err.Clear")
    lines += [
        'Set Pipe = CreateObject("pphdecoding.ScflowPipeline")',
        "If Pipe Is Nothing Then",
        '    out.WriteLine "error=create_failed"',
        "Else",
        "    out.WriteLine \"context_ready=\" & CStr(Pipe.ContextReady)",
        '    out.WriteLine "context_ready_raw=" & CStr(Pipe.ContextReadyRaw)',
        '    out.WriteLine "last_exception_code=" & CStr(Pipe.LastExceptionCode)',
        '    out.WriteLine "bridge_status:"',
        "    out.WriteLine Pipe.Status",
        f'    hSet = Pipe.CreateShapeGroupSet("{set_name}")',
        '    out.WriteLine "set_handle=" & CStr(hSet) & "|last_error=" & CStr(Pipe.LastError())',
        "    If hSet > 0 Then",
        f'        hGroup = Pipe.CreateShapeGroup(hSet, "{group_name}")',
        '        out.WriteLine "group_handle=" & CStr(hGroup) & "|last_error=" & CStr(Pipe.LastError())',
        "        If hGroup > 0 Then",
        '            out.WriteLine "mdl=" & CStr(Pipe.CreateMDL(hGroup)) & "|last_error=" & CStr(Pipe.LastError())',
        "            Pipe.ReleaseHandle hGroup",
        "        End If",
        "        Pipe.ReleaseHandle hSet",
        "    End If",
        "End If",
        "out.Close",
    ]
    target = Path(output) if output else result_path.with_suffix(".vbs")
    return write_vbs_file(lines, target,
                          title="pphdecoding host pipeline")


def parse_result(result_path: str | Path) -> dict:
    """Parse the result file written by the host VBS."""
    path = Path(result_path)
    if not path.is_file():
        return {"ok": False, "error": "result file not found",
                "path": str(path)}
    data: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        for segment in raw.split("|"):
            segment = segment.strip()
            if not segment or "=" not in segment:
                continue
            key, _, value = segment.partition("=")
            data[key.strip()] = value.strip()
    if "error" in data:
        return {"ok": False, **data, "path": str(path)}
    set_handle = int(data.get("set_handle", "0") or 0)
    group_handle = int(data.get("group_handle", "0") or 0)
    raw_ready = data.get("context_ready_raw", "").strip()
    context_ready_raw: Optional[int] = None
    if raw_ready.lstrip("-").isdigit():
        context_ready_raw = int(raw_ready)
    last_exc = data.get("last_exception_code", "").strip()
    return {
        "ok": set_handle > 0 and group_handle > 0,
        "context_ready": data.get("context_ready", "").lower() == "true",
        "context_ready_raw": context_ready_raw,
        "last_exception_code": int(last_exc) if last_exc.lstrip("-").isdigit()
        else None,
        "set_handle": set_handle,
        "group_handle": group_handle,
        "mdl": data.get("mdl", "").lower() == "true",
        "last_error": data.get("last_error", ""),
        "raw": data,
        "path": str(path),
    }


def _find_scflow_process():
    import subprocess

    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process scFLOWpre_Bx64net -ErrorAction SilentlyContinue | "
         "Select-Object -ExpandProperty Id"],
        capture_output=True, text=True, timeout=15, check=False).stdout
    pids = [int(x) for x in out.split() if x.strip().isdigit()]
    return pids


def _instance_window_info(pid: int) -> dict:
    """返回某 scFLOWpre 进程的主框架窗口可见性（尽力而为，无 pywinauto
    时退化为仅 pid）。主框架类名为 ``Afx:...``（2025.2 实测）或
    ``AfxMDIFrame``；隐藏窗口（Kicker 长驻实例常隐藏）``visible=False``。

    ``findwindows.find_elements`` 返回 ``ElementInfo``，其窗口标题是
    ``.name`` 属性、可见性是 ``.visible`` 属性（非 BaseWrapper 的
    ``window_text()``/``is_visible()`` 方法）。
    """
    info: dict = {"pid": pid, "visible": False, "window_title": "",
                  "window_handle": None}
    try:
        from pywinauto import findwindows
    except Exception:  # noqa: BLE001
        return info
    try:
        for w in findwindows.find_elements(visible_only=False):
            if w.process_id != pid:
                continue
            cls = w.class_name or ""
            if not (cls.startswith("Afx:") or cls.startswith("AfxMDIFrame")):
                continue
            info["window_title"] = w.name or ""
            info["window_handle"] = w.handle
            info["visible"] = bool(w.visible)
            break
    except Exception:  # noqa: BLE001
        pass
    return info


def host_status() -> dict:
    """探测宿主运行态（P6-5「宿主交互环境收敛」诊断口）。

    返回 scFLOWpre 是否安装、Kicker 启动器位置、在跑实例及其主框架
    窗口可见性。gui 后端需要「带可见主框架的 Kicker 实例」才能完整
    驱动 File → Execute VBScript（隐藏窗口受 Win32 前台锁 + Kicker
    长驻闲置态交互限制，见 REANALYSIS_2026-08-17 §7.4）；manual 后端
    始终可用。实测（2026-08-17）：常驻实例由 svchost 拉起（headless），
    主框架窗口 MainWindowHandle=0，``any_visible=False``。
    """
    exe = scflowpre_probe.find_program("scFLOWpre_Bx64net.exe")
    kicker = scflowpre_probe.find_program("Kicker_Bx64.exe")
    pids = _find_scflow_process()
    instances = [_instance_window_info(pid) for pid in pids]
    visible = [i for i in instances if i.get("visible")]
    if visible:
        hint = "gui 后端可自动驱动（存在可见主框架）"
    elif pids:
        hint = ("scFLOWpre 在跑但无可见主框架：请经 Kicker_Bx64.exe 启动"
                "一个前台实例后再用 gui 后端（manual 后端始终可用）")
    else:
        hint = ("scFLOWpre 未运行：请经 Kicker_Bx64.exe 启动宿主"
                "（直接拉起裸 exe 会因缺少 Kicker 许可注入而崩溃）")
    return {
        "installed": exe is not None,
        "exe": str(exe) if exe else None,
        "kicker_launcher": str(kicker) if kicker else None,
        "running_pids": pids,
        "instances": instances,
        "any_visible": bool(visible),
        "gui_ready": bool(visible),
        "hint": hint,
    }


def _click_menu_item_real(frame, top_label: str, item_label: str) -> bool:
    """真实鼠标点击菜单项（2026-08-17 实机验证的配方）。

    前置：调用方应先 AttachThreadInput + ShowWindow + SetForegroundWindow
    让主框架可见且前台。GetMenuBarInfo 的 rcBar 是**屏幕坐标**；弹窗项
    坐标用 GetMenuItemRect(NULL, hsub, idx)（也是屏幕坐标）。
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    class _RECT(ctypes.Structure):
        _fields_ = [('left', wintypes.LONG), ('top', wintypes.LONG),
                    ('right', wintypes.LONG), ('bottom', wintypes.LONG)]

    class _MENUBARINFO(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('rcBar', _RECT),
                    ('hMenu', wintypes.HMENU), ('hwndMenu', wintypes.HWND),
                    ('fBarFocused', wintypes.BOOL),
                    ('fFocused', wintypes.BOOL)]

    user32.GetMenuBarInfo.restype = wintypes.BOOL
    user32.GetMenuBarInfo.argtypes = [wintypes.HWND, wintypes.LONG,
                                      wintypes.LONG,
                                      ctypes.POINTER(_MENUBARINFO)]
    user32.GetMenuItemRect.restype = wintypes.BOOL
    user32.GetMenuItemRect.argtypes = [wintypes.HWND, wintypes.HMENU,
                                       wintypes.UINT, ctypes.POINTER(_RECT)]
    user32.GetMenu.restype = wintypes.HMENU
    user32.GetMenu.argtypes = [wintypes.HWND]
    user32.GetSubMenu.restype = wintypes.HMENU
    user32.GetSubMenu.argtypes = [wintypes.HMENU, ctypes.c_int]
    user32.GetMenuItemCount.restype = ctypes.c_int
    user32.GetMenuItemCount.argtypes = [wintypes.HMENU]
    user32.GetMenuStringW.restype = ctypes.c_int
    user32.GetMenuStringW.argtypes = [wintypes.HMENU, wintypes.UINT,
                                      wintypes.LPWSTR, ctypes.c_int,
                                      wintypes.UINT]
    user32.SetCursorPos.restype = wintypes.BOOL
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.mouse_event.restype = None
    user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD,
                                   wintypes.DWORD, wintypes.DWORD,
                                   ctypes.c_void_p]

    def _click(x: int, y: int) -> None:
        user32.SetCursorPos(x, y)
        time.sleep(0.25)
        user32.mouse_event(2, 0, 0, 0, None)   # LEFTDOWN
        time.sleep(0.05)
        user32.mouse_event(4, 0, 0, 0, None)   # LEFTUP

    # 前台恢复（AttachThreadInput 突破后台进程前台锁）
    try:
        k32 = ctypes.windll.kernel32
        k32.GetCurrentThreadId.restype = wintypes.DWORD
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.AttachThreadInput.restype = wintypes.BOOL
        fg = user32.GetForegroundWindow()
        t_fg = user32.GetWindowThreadProcessId(fg, None)
        t_tgt = user32.GetWindowThreadProcessId(frame.handle, None)
        t_me = k32.GetCurrentThreadId()
        user32.AttachThreadInput(t_me, t_fg, True)
        user32.AttachThreadInput(t_me, t_tgt, True)
        user32.ShowWindow(frame.handle, 9)          # SW_RESTORE
        user32.SetForegroundWindow(frame.handle)
        user32.BringWindowToTop(frame.handle)
        user32.AttachThreadInput(t_me, t_fg, False)
        user32.AttachThreadInput(t_me, t_tgt, False)
        time.sleep(0.6)
    except Exception:  # noqa: BLE001
        pass

    hmenu = user32.GetMenu(frame.handle)
    if not hmenu:
        return False
    sub = None
    top_idx = -1
    for i in range(user32.GetMenuItemCount(hmenu)):
        buf = ctypes.create_unicode_buffer(256)
        if user32.GetMenuStringW(hmenu, i, buf, 256, 0x400) > 0:
            if buf.value.replace('&', '').lower() == top_label.lower():
                sub = user32.GetSubMenu(hmenu, i)
                top_idx = i
                break
    if sub is None:
        return False
    # 1) 点击菜单栏上的 File（rcBar 已是屏幕坐标，勿加窗口偏移）
    mbi = _MENUBARINFO()
    mbi.cbSize = ctypes.sizeof(_MENUBARINFO)
    if not user32.GetMenuBarInfo(frame.handle, 0xFFFFFFFD, top_idx,
                                 ctypes.byref(mbi)):
        return False
    _click((mbi.rcBar.left + mbi.rcBar.right) // 2,
           (mbi.rcBar.top + mbi.rcBar.bottom) // 2)
    time.sleep(1.0)
    # 2) 找弹窗菜单窗口（#32768）并点击目标项
    from pywinauto import findwindows
    popup = None
    deadline = time.time() + 5
    while time.time() < deadline and popup is None:
        for w in findwindows.find_elements(visible_only=False):
            if w.process_id == frame.process_id and w.class_name == '#32768':
                popup = w
                break
        time.sleep(0.3)
    if popup is None:
        return False
    item_idx = -1
    for j in range(user32.GetMenuItemCount(sub)):
        buf = ctypes.create_unicode_buffer(256)
        if user32.GetMenuStringW(sub, j, buf, 256, 0x400) > 0:
            if buf.value.replace('&', '').replace('...', '').lower() == \
                    item_label.replace('...', '').lower():
                item_idx = j
                break
    if item_idx < 0:
        return False
    rc = _RECT()
    if not user32.GetMenuItemRect(None, sub, item_idx, ctypes.byref(rc)) \
            or rc.right <= rc.left:
        return False
    _click((rc.left + rc.right) // 2, (rc.top + rc.bottom) // 2)
    return True


def _fill_execute_vbs_dialog(dlg_handle, vbs_path: Path) -> bool:
    """填充 "Specify VBScript or filename" 对话框并点击 Execute。

    优先 UIA（ValuePattern.SetValue + Invoke）——普通 Win32 消息
    （WM_SETTEXT/WM_CHAR/EM_REPLACESEL）实测被该自绘控件忽略；
    失败时回退经典消息路径。返回是否已提交。
    """
    vbs_path = Path(vbs_path)
    # 1) UIA 主路径
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        dlg_pid = user32.GetWindowThreadProcessId(dlg_handle, None)
        from pywinauto import Application
        app = Application(backend='uia').connect(process=dlg_pid,
                                                 timeout=15)
        dlg = app.window(handle=dlg_handle)
        edit = dlg.child_window(control_type='Edit')
        edit.wrapper_object().iface_value.SetValue(str(vbs_path))
        time.sleep(0.3)
        btn = None
        for cand in dlg.descendants(control_type='Button'):
            if 'Execute' in (cand.window_text() or ''):
                btn = cand
                break
        if btn is None:
            for cand in dlg.descendants(control_type='Button'):
                if 'Open' in (cand.window_text() or '') or 'OK' in (
                        cand.window_text() or ''):
                    btn = cand
                    break
        if btn is None:
            return False
        btn.wrapper_object().iface_invoke.Invoke()
        return True
    except Exception:  # noqa: BLE001
        pass
    # 2) 经典 Win32 消息回退
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.GetDlgItem.restype = wintypes.HWND
    user32.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SendMessageW.restype = wintypes.LPARAM
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                    wintypes.WPARAM, wintypes.LPARAM]
    edit = user32.GetDlgItem(dlg_handle, 0x480)
    if not edit:
        return False
    user32.SendMessageW(edit, 0x000C, 0, str(vbs_path))
    for btn_id in (1, 0x1):
        btn = user32.GetDlgItem(dlg_handle, btn_id)
        if btn:
            user32.SendMessageW(btn, 0x00F5, 0, 0)
            return True
    return False


def _post_menu_command(frame, top_label: str, item_label: str) -> bool:
    """按菜单文本定位命令 ID 并向主框架 PostMessage WM_COMMAND。

    对隐藏/最小化窗口同样有效（不需要前台与可见性），返回是否成功。
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.GetMenu.restype = wintypes.HMENU
    user32.GetMenu.argtypes = [wintypes.HWND]
    user32.GetSubMenu.restype = wintypes.HMENU
    user32.GetSubMenu.argtypes = [wintypes.HMENU, ctypes.c_int]
    user32.GetMenuItemCount.restype = ctypes.c_int
    user32.GetMenuItemCount.argtypes = [wintypes.HMENU]
    user32.GetMenuItemID.restype = wintypes.UINT
    user32.GetMenuItemID.argtypes = [wintypes.HMENU, ctypes.c_int]
    user32.GetMenuStringW.restype = ctypes.c_int
    user32.GetMenuStringW.argtypes = [wintypes.HMENU, wintypes.UINT,
                                      wintypes.LPWSTR, ctypes.c_int,
                                      wintypes.UINT]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                    wintypes.WPARAM, wintypes.LPARAM]

    hmenu = user32.GetMenu(frame.handle)
    if not hmenu:
        return False
    top_count = user32.GetMenuItemCount(hmenu)
    target_sub = None
    for i in range(top_count):
        buf = ctypes.create_unicode_buffer(256)
        if user32.GetMenuStringW(hmenu, i, buf, 256, 0x400) > 0:
            text = buf.value.replace("&", "")
            if text.lower() == top_label.lower():
                target_sub = user32.GetSubMenu(hmenu, i)
                break
    if not target_sub:
        return False
    n = user32.GetMenuItemCount(target_sub)
    for i in range(n):
        buf = ctypes.create_unicode_buffer(256)
        if user32.GetMenuStringW(target_sub, i, buf, 256, 0x400) > 0:
            text = buf.value.replace("&", "").replace("...", "")
            if text.lower() == item_label.replace("...", "").lower():
                cmd = user32.GetMenuItemID(target_sub, i)
                if cmd and cmd != 0xFFFFFFFF:
                    return bool(user32.PostMessageW(frame.handle, 0x111,
                                                   cmd, 0))
                return False
    return False


def _dismiss_warning_dialogs(app) -> None:
    from pywinauto import findwindows

    for _ in range(10):
        handles = findwindows.find_windows(title_re="Warnning|Warning")
        if not handles:
            return
        dlg = app.window(handle=handles[0])
        for c in dlg.children():
            if c.friendly_class_name() == "Button":
                c.click()
                break
        time.sleep(1.0)


def run_in_host(vbs_path: str | Path, *, backend: str = "manual",
                timeout: float = 180.0,
                menu: Optional[dict] = None) -> dict:
    """Run a VBS inside the scFLOWpre host."""
    vbs_path = Path(vbs_path)
    if not vbs_path.is_file():
        raise FileNotFoundError(vbs_path)
    if backend == "manual":
        return {
            "backend": "manual",
            "script": str(vbs_path),
            "hint": "请在 scFLOWpre 中执行 File → Execute VBScript，"
                    "选择该脚本文件",
        }
    if backend != "gui":
        if backend == "com":
            return _run_com_vbs(vbs_path, timeout=timeout)
        raise ValueError(f"unknown backend: {backend}")
    return _run_gui(vbs_path, timeout=timeout, menu=menu or {})


def run_vbs_if_ready(vbs_path: str | Path, *, timeout: float = 180.0) -> dict:
    """gui_ready 时用 gui 后端执行 VBS；否则跳过并返回诊断（不拉起裸 exe）。"""
    st = host_status()
    payload = {
        "script": str(vbs_path),
        "gui_ready": bool(st.get("gui_ready")),
        "status": {k: st.get(k) for k in (
            "installed", "kicker_launcher", "running_pids",
            "any_visible", "gui_ready", "hint")},
    }
    if not st.get("gui_ready"):
        payload.update({
            "ok": False,
            "skipped": True,
            "attempted": False,
            "hint": st.get("hint") or "host not gui_ready",
        })
        return payload
    run = run_in_host(vbs_path, backend="gui", timeout=timeout)
    payload.update(run)
    payload["skipped"] = False
    payload["attempted"] = True
    payload.setdefault("ok", True)
    return payload


def locate_scflowpre() -> dict:
    """自动定位 scFLOWpre 安装目录与 COM ProgID（供 GUI 日志/校验）。

    P4-3：附带 windtool VBS 背书的关联 ProgID（STpre / scConverter
    S/D 变体）注册状态，供自动化桥选择几何转换等宿主入口。
    """
    root = scflowpre_probe.find_install()
    if root is None:
        return {"installed": False, "progid": PROGID_HOST}
    return {
        "installed": True,
        "install_dir": str(root),
        "programs_dir": str(root / scflowpre_probe.PROGRAMS_SUBDIR),
        "progid": PROGID_HOST,
        "related_progpids": {
            k: v for k, v in
            scflowpre_probe.probe_com_progpids().items() if k != PROGID_HOST},
    }


def _run_com_vbs(vbs_path: Path, timeout: float) -> dict:
    """通过 COM Application.ExecuteVBSWithFile / ExecuteVBS 执行脚本。

    宿主未启动时 Dispatch 会自动拉起 scFLOWpre（LocalServer）。
    win32com 晚绑定会把这两个成员读成 bool 属性；必须先
    ``_FlagAsMethod``，切勿 ``app.ExecuteVBS = ...``（会触发
    ``Property ... can not be set``）。
    """
    import threading

    import pythoncom
    import win32com.client

    result: dict = {}
    path = str(Path(vbs_path).resolve())

    def _call() -> None:
        pythoncom.CoInitialize()
        try:
            app = win32com.client.Dispatch(PROGID_HOST)
            try:
                app._FlagAsMethod("ExecuteVBSWithFile", "ExecuteVBS")
            except Exception:  # noqa: BLE001
                pass
            last_error: Optional[BaseException] = None
            method = None
            ok: Optional[bool] = None
            # 1) 文件路径（与 File → Execute VBScript 等价）
            try:
                ok = bool(app.ExecuteVBSWithFile(path))
                method = "ExecuteVBSWithFile"
            except Exception as exc:  # noqa: BLE001
                last_error = exc
            # 2) 脚本文本
            if ok is None:
                try:
                    code = decode_vbs(Path(path).read_bytes())
                    ok = bool(app.ExecuteVBS(code))
                    method = "ExecuteVBS"
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
            if ok is None:
                raise last_error or RuntimeError(
                    "ExecuteVBSWithFile / ExecuteVBS unavailable; "
                    "call _FlagAsMethod before invoke")
            result["ok"] = bool(ok)
            result["method"] = method
            if not ok:
                result["error"] = (
                    f"{method} returned False "
                    "(script ran but reported failure; "
                    "check OpenProject path / host license / log)")
        except Exception as exc:  # noqa: BLE001
            result["error"] = repr(exc)
        finally:
            pythoncom.CoUninitialize()

    thread = threading.Thread(target=_call, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        return {"backend": "com", "ok": False,
                "error": "timeout waiting for scFLOWpre",
                "script": path}
    if result.get("ok"):
        return {"backend": "com", "ok": True, "script": path,
                "method": result.get("method")}
    return {"backend": "com", "ok": False,
            "error": result.get("error", "unknown COM failure"),
            "script": path, "method": result.get("method")}


def _run_gui(vbs_path: Path, timeout: float, menu: dict) -> dict:
    """GUI 后端：File → Execute VBScript 在宿主进程内执行脚本。

    多实例并存时（Kicker 实例 + COM LocalServer 瞬态实例）必须选带
    ``AfxMDIFrame`` 主框架的实例；对话框按"菜单点击后新出现的可见
    #32770"识别，Edit 填路径，Open/OK 按钮多重回退。
    """
    from pywinauto import Application

    exe = scflowpre_probe.find_program("scFLOWpre_Bx64net.exe")
    if exe is None:
        return {"backend": "gui", "ok": False,
                "error": "scFLOWpre not installed"}
    pids = _find_scflow_process()
    started_by_us = False
    if not pids:
        # 安全约束（DEV_SUMMARY §6.4）：绝不能直接 start 裸 exe——
        # scFLOWpre 必须经 Kicker 启动（许可/产品键注入），裸 exe 会在
        # SetupSCTpreLib 抛 0xE0000000 并弹模态错误框。要求用户先经
        # Kicker 启动宿主，再使用 gui 后端。
        return {
            "backend": "gui", "ok": False,
            "error": "scFLOWpre 未运行：请先经 Kicker_Bx64.exe 正常启动 "
                     "scFLOWpre，再选择 gui 后端（直接拉起裸 exe 会因缺少 "
                     "Kicker 注入的许可状态而崩溃，见 DEV_SUMMARY §6.1/§6.4）",
            "script": str(vbs_path),
        }

    app = None
    frame = None
    for pid in pids:
        try:
            cand = Application(backend="win32").connect(process=pid,
                                                        timeout=10)
            # Kicker 常驻实例的主框架可能隐藏（MainWindowHandle=0），且
            # 2025.2 实测主框架类名为 "Afx:00007FF683D10000:0"（标题
            # 'scFLOWpre'），并非 AfxMDIFrame 前缀。先按可见枚举，没有再
            # 放宽到不可见窗口——恢复可见由 _click_menu_item_real 的
            # AttachThreadInput + SW_RESTORE 负责。
            def _is_frame(w) -> bool:
                try:
                    cls = w.class_name()
                    if cls.startswith("AfxMDIFrame"):
                        return True
                    return (cls.startswith("Afx:")
                            and (w.window_text() or "") == "scFLOWpre")
                except Exception:  # noqa: BLE001
                    return False

            for w in cand.windows():
                if _is_frame(w):
                    app = cand
                    frame = w
                    break
            if frame is None:
                for w in cand.windows(visible_only=False):
                    if _is_frame(w):
                        app = cand
                        frame = w
                        break
            if frame is not None:
                break
        except Exception:  # noqa: BLE001
            continue
    if app is None or frame is None:
        return {"backend": "gui", "ok": False,
                "error": "scFLOWpre 已运行但没有可自动化的 MDI 主框架"
                         "（Kicker 实例未就绪？）",
                "script": str(vbs_path)}

    _dismiss_warning_dialogs(app)
    # 快照菜单点击前已有的对话框句柄，用于识别之后新弹出的脚本选择框
    try:
        before = {w.handle for w in app.windows()
                  if w.class_name() == "#32770"}
    except Exception:  # noqa: BLE001
        before = set()

    file_menu = menu.get("file", "File")
    execute_item = menu.get("execute_vbs", "Execute VBScript...")
    # 2026-08-17 实机配方（Kicker 实例 22468 验证到 Execute 步）：
    # 1) AttachThreadInput 突破 Win32 前台锁后 ShowWindow+SetForeground；
    # 2) 真实鼠标点击菜单——GetMenuBarInfo 的 rcBar 是**屏幕坐标**（曾经
    #    误加窗口偏移导致点空）；WM_COMMAND / menu_select 对该宿主实测
    #    不触发对话框（消息被吞 / 可见性检查失败），仅作回退。
    clicked_menu = _click_menu_item_real(frame, file_menu, execute_item)
    if not clicked_menu:
        if not _post_menu_command(frame, file_menu, execute_item):
            try:
                frame.menu_select(f"{file_menu}->{execute_item}")
            except Exception as exc:  # noqa: BLE001
                return {"backend": "gui", "ok": False,
                        "error": f"menu failed: {exc}",
                        "started_by_us": started_by_us}

    dlg = None
    deadline = time.time() + 25
    while time.time() < deadline and dlg is None:
        try:
            for w in app.windows():
                if w.class_name() != "#32770" or w.handle in before:
                    continue
                try:
                    if not (w.is_visible() and w.is_enabled()):
                        continue
                    r = w.rectangle()
                    if (r.right - r.left) > 150:
                        dlg = w
                        break
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            pass
        if dlg is None:
            time.sleep(0.5)
    if dlg is None:
        return {"backend": "gui", "ok": False,
                "error": "Execute VBScript 对话框未出现",
                "started_by_us": started_by_us, "script": str(vbs_path)}

    # 对话框是宿主自绘的 "Specify VBScript or filename"（Edit id=3123 +
    # Execute id=1085，无 Browse）：普通 Win32 消息（WM_SETTEXT/WM_CHAR/
    # EM_REPLACESEL）实测全部被忽略，必须走 UIA ValuePattern.SetValue +
    # Invoke；失败时回退经典 Win32 消息。
    filled = _fill_execute_vbs_dialog(dlg.handle, vbs_path)
    if not filled:
        return {"backend": "gui", "ok": False,
                "error": "Execute VBScript 对话框填充失败",
                "started_by_us": started_by_us, "script": str(vbs_path)}
    return {"backend": "gui", "ok": True, "submitted": str(vbs_path),
            "started_by_us": started_by_us, "pid": frame.process_id}


def run_pipeline(set_name: str = "Probe",
                 group_name: str = "ProbeGroup",
                 project_path: Optional[str | Path] = None,
                 result_path: Optional[str | Path] = None,
                 vbs_path: Optional[str | Path] = None,
                 backend: str = "manual",
                 timeout: float = 180.0,
                 menu: Optional[dict] = None,
                 register: bool = True) -> dict:
    """Register the COM bridge, build the VBS and run it in the host."""
    if register:
        register_com()
    result = Path(result_path) if result_path else \
        Path.cwd() / "host_pipeline_result.txt"
    vbs = Path(vbs_path) if vbs_path else result.with_suffix(".vbs")
    build_pipeline_vbs(result, set_name=set_name, group_name=group_name,
                       project_path=project_path,
                       output=vbs)
    run = run_in_host(vbs, backend=backend, timeout=timeout, menu=menu)
    if backend == "manual":
        return {"run": run, "result_path": str(result), "ok": False,
                "hint": run["hint"]}
    deadline = time.time() + timeout
    while time.time() < deadline:
        if result.is_file():
            parsed = parse_result(result)
            parsed["run"] = run
            return parsed
        time.sleep(1.0)
    return {"ok": False, "error": "timed out waiting for result file",
            "run": run, "result_path": str(result)}


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    import json
    import sys

    ap = argparse.ArgumentParser(
        description="pphdecoding host pipeline (COM + VBS)")
    ap.add_argument("--register", action="store_true",
                    help="register the bridge COM server (HKCU)")
    ap.add_argument("--unregister", action="store_true",
                    help="unregister the bridge COM server")
    ap.add_argument("--status", action="store_true",
                    help="report host runtime status (instances + window "
                         "visibility + Kicker launcher)")
    ap.add_argument("--run-if-ready", metavar="VBS",
                    help="run VBS via gui backend only when host_status "
                         "reports gui_ready")
    ap.add_argument("--write-vbs", metavar="OUT", help="write host VBS only")
    ap.add_argument("--run", action="store_true",
                    help="run the pipeline in the host")
    ap.add_argument("--backend", choices=["manual", "gui"], default="manual")
    ap.add_argument("--set-name", default="Probe")
    ap.add_argument("--project", default=None,
                    help="PPH/CAD path to open in the host before the pipeline")
    ap.add_argument("--result", default=None,
                    help="result file path (default: cwd/host_pipeline_result.txt)")
    args = ap.parse_args(argv)

    if args.register:
        result = register_com()
    elif args.unregister:
        result = unregister_com()
    elif args.status:
        result = host_status()
    elif args.run_if_ready:
        result = run_vbs_if_ready(args.run_if_ready)
    elif args.write_vbs:
        out = Path(args.write_vbs)
        result_path = out.with_name(out.stem + "_result.txt")
        build_pipeline_vbs(result_path, set_name=args.set_name,
                           project_path=args.project, output=out)
        result = {"written": str(out), "result_path": str(result_path)}
    elif args.run:
        result = run_pipeline(set_name=args.set_name, backend=args.backend,
                              result_path=args.result, project_path=args.project)
    else:
        ap.print_help()
        return 1
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
