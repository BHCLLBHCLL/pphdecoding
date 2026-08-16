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
            "error": "scFLOWpre 未运行：请先经 Kicker 正常启动 scFLOWpre，"
                     "再选择 gui 后端（直接拉起裸 exe 会因缺少 Kicker 注入"
                     "的许可状态而崩溃，见 DEV_SUMMARY §6.1/§6.4）",
            "script": str(vbs_path),
        }

    app = None
    frame = None
    for pid in pids:
        try:
            cand = Application(backend="win32").connect(process=pid,
                                                        timeout=10)
            for w in cand.windows():
                try:
                    if w.class_name().startswith("AfxMDIFrame"):
                        app = cand
                        frame = w
                        break
                except Exception:  # noqa: BLE001
                    continue
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
    # 菜单点击优先走 WM_COMMAND：宿主主框架常被最小化/隐藏，且后台进程
    # 无法 SetForegroundWindow（Win32 前台锁），menu_select 的可见性检查
    # 会失败。WM_COMMAND 对隐藏窗口同样生效。
    if not _post_menu_command(frame, file_menu, execute_item):
        try:
            frame.menu_select(f"{file_menu}->{execute_item}")
        except Exception as exc:  # noqa: BLE001
            return {"backend": "gui", "ok": False,
                    "error": f"menu failed: {exc}",
                    "started_by_us": started_by_us}

    dlg = None
    deadline = time.time() + 20
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

    # 对话框交互全部走原生 Win32 消息（前台无关）：Edit 设 WM_SETTEXT，
    # 确认按钮按 IDOK 兜底 BM_CLICK。
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.GetDlgItem.restype = wintypes.HWND
    user32.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SendMessageW.restype = wintypes.LPARAM
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                    wintypes.WPARAM, wintypes.LPARAM]

    edit = user32.GetDlgItem(dlg.handle, 0x480)   # 文件对话框文件名 Edit
    if not edit:
        return {"backend": "gui", "ok": False,
                "error": "对话框文件名 Edit 控件未找到",
                "started_by_us": started_by_us, "script": str(vbs_path)}
    user32.SendMessageW(edit, 0x000C, 0, str(vbs_path))   # WM_SETTEXT
    time.sleep(0.3)
    clicked = False
    for btn_id in (1, 0x1):   # IDOK（FileDialog 中为 Open/OK 按钮）
        btn = user32.GetDlgItem(dlg.handle, btn_id)
        if btn:
            user32.SendMessageW(btn, 0x00F5, 0, 0)        # BM_CLICK
            clicked = True
            break
    if not clicked:
        return {"backend": "gui", "ok": False,
                "error": "对话框确认按钮未找到",
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
