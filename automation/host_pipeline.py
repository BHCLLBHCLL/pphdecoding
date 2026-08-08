"""Run the NativeBridge pipeline inside the scFLOWpre host via VBScript.

The bridge DLL is registered as a per-user in-proc COM server
(``pphdecoding.ScflowPipeline``). A VBScript executed inside the host
(File -> Execute VBScript) creates that object, so the bridge runs in the
host process where the SCTprime document context is already initialized.

Backends:

- ``manual``: write the script and ask the user to run it in the host;
- ``gui``: best-effort pywinauto automation of File -> Execute VBScript.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import scflowpre_probe
from automation.vbs_bridge import write_vbs_file

CLSID = "{9F8D2C1A-3B4E-4C5D-8E6F-1A2B3C4D5E6F}"
PROGID = "pphdecoding.ScflowPipeline"

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
                       output: Optional[str | Path] = None) -> Path:
    """Write the VBS that drives the COM bridge inside the host."""
    result_path = Path(result_path).resolve()
    lines = [
        "' pphdecoding NativeBridge host pipeline",
        "On Error Resume Next",
        'Set fso = CreateObject("Scripting.FileSystemObject")',
        f'Set log = fso.CreateTextFile("{result_path}", True)',
        'Set Pipe = CreateObject("pphdecoding.ScflowPipeline")',
        "If Pipe Is Nothing Then",
        '    log.WriteLine "error=create_failed"',
        "Else",
        "    log.WriteLine \"context_ready=\" & CStr(Pipe.ContextReady)",
        f'    hSet = Pipe.CreateShapeGroupSet("{set_name}")',
        '    log.WriteLine "set_handle=" & CStr(hSet) & "|last_error=" & CStr(Pipe.LastError())',
        "    If hSet > 0 Then",
        f'        hGroup = Pipe.CreateShapeGroup(hSet, "{group_name}")',
        '        log.WriteLine "group_handle=" & CStr(hGroup) & "|last_error=" & CStr(Pipe.LastError())',
        "        If hGroup > 0 Then",
        '            log.WriteLine "mdl=" & CStr(Pipe.CreateMDL(hGroup)) & "|last_error=" & CStr(Pipe.LastError())',
        "            Pipe.ReleaseHandle hGroup",
        "        End If",
        "        Pipe.ReleaseHandle hSet",
        "    End If",
        "End If",
        "log.Close",
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
    return {
        "ok": set_handle > 0 and group_handle > 0,
        "context_ready": data.get("context_ready", "").lower() == "true",
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
        raise ValueError(f"unknown backend: {backend}")
    return _run_gui(vbs_path, timeout=timeout, menu=menu or {})


def _run_gui(vbs_path: Path, timeout: float, menu: dict) -> dict:
    from pywinauto import Application

    exe = scflowpre_probe.find_program("scFLOWpre_Bx64net.exe")
    if exe is None:
        return {"backend": "gui", "ok": False,
                "error": "scFLOWpre not installed"}
    pids = _find_scflow_process()
    started_by_us = False
    if pids:
        app = Application(backend="win32").connect(process=pids[0])
    else:
        app = Application(backend="win32").start(str(exe))
        started_by_us = True

    _dismiss_warning_dialogs(app)
    try:
        win = app.window(title_re=menu.get("main_title_re",
                                           ".*scFLOWpre.*|.*SCFLOW.*"))
        win.wait("visible", timeout=20)
    except Exception as exc:  # noqa: BLE001
        return {"backend": "gui", "ok": False,
                "error": f"main window not found: {exc}",
                "started_by_us": started_by_us}

    file_menu = menu.get("file", "File")
    execute_item = menu.get("execute_vbs", "Execute VBScript")
    try:
        win.menu_select(f"{file_menu}->{execute_item}")
    except Exception as exc:  # noqa: BLE001
        return {"backend": "gui", "ok": False,
                "error": f"menu failed: {exc}",
                "started_by_us": started_by_us}

    try:
        dlg = app.window(title_re=menu.get("dlg_title_re", ".*VBS.*"))
        dlg.wait("visible", timeout=20)
        edit = dlg.child_window(class_name="Edit")
        edit.set_edit_text(str(vbs_path))
        ok = dlg.child_window(title=menu.get("ok_button", "OK"))
        ok.click()
    except Exception as exc:  # noqa: BLE001
        return {"backend": "gui", "ok": False,
                "error": f"dialog failed: {exc}",
                "started_by_us": started_by_us}
    return {"backend": "gui", "ok": True, "submitted": str(vbs_path),
            "started_by_us": started_by_us}


def run_pipeline(set_name: str = "Probe",
                 group_name: str = "ProbeGroup",
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
        build_pipeline_vbs(result_path, set_name=args.set_name, output=out)
        result = {"written": str(out), "result_path": str(result_path)}
    elif args.run:
        result = run_pipeline(set_name=args.set_name, backend=args.backend,
                              result_path=args.result)
    else:
        ap.print_help()
        return 1
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
