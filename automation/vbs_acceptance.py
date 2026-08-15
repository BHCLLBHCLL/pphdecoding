#!/usr/bin/env python3
"""scFLOWpre VBS 验收：打开 PPH（含写端产出的改写 PPH）并验证宿主接受。

这是「布局一致」的实证：宿主（scFLOWpre）能打开本仓库写端产出的 PPH。
前置：宿主需经 Kicker 启动（设 ``CRADLE_LICENSE_FILE=27500@localhost``）。

两条路径：

- ``run_open``：直接 COM ``GetDocument → OpenProject(path, False)``；
- ``run_open_vbs``：生成 UTF-16 VBS（GetApplication → GetDocument →
  OpenProject + 分步写结果）经 ``ExecuteVBSWithFile`` 执行。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from automation import vbs_bridge

PROGID_HOST = "scFLOWpre_Bx64net.Application.2025"


def _dispatch():
    import win32com.client
    app = win32com.client.Dispatch(PROGID_HOST)
    app._FlagAsMethod("ExecuteVBSWithFile", "ExecuteVBS", "GetDocument")
    return app


def build_open_vbs(result_path: str | Path, project_path: str | Path) -> Path:
    """生成「打开工程 + 分步写结果」的 UTF-16 VBS，返回 .vbs 路径。"""
    result_path = Path(result_path)
    project_path = Path(project_path).resolve()
    actions = [
        "On Error Resume Next",
        'Set fso = CreateObject("Scripting.FileSystemObject")',
        f'Set log = fso.CreateTextFile("{result_path.as_posix()}", True)',
        'log.WriteLine "start"',
        "Set App_ = GetApplication()",
        'log.WriteLine "app=" & CStr(Not (App_ Is Nothing)) & " err=" & CStr(Err.Number)',
        "Err.Clear",
        "Set Doc_ = App_.GetDocument",
        'log.WriteLine "doc=" & CStr(Not (Doc_ Is Nothing)) & " err=" & CStr(Err.Number)',
        "Err.Clear",
        f'Param1_ = "{project_path.as_posix()}"',
        "Doc_.OpenProject Param1_, False",
        'log.WriteLine "open_err=" & CStr(Err.Number)',
        "Err.Clear",
        "log.Close",
    ]
    out = result_path.with_suffix(".vbs")
    vbs_bridge.write_vbs_file(actions, out)
    return out


def run_open(project_path: str | Path) -> dict:
    """直接 COM 打开工程，返回 ``{ok, method}``。"""
    import pythoncom
    import win32com.client

    project_path = str(Path(project_path).resolve())
    result: dict = {}

    def _call():
        pythoncom.CoInitialize()
        try:
            app = win32com.client.Dispatch(PROGID_HOST)
            app._FlagAsMethod("GetDocument")
            doc = app.GetDocument()
            doc._FlagAsMethod("OpenProject")
            ok = bool(doc.OpenProject(project_path, False))
            result["ok"] = ok
            result["method"] = "OpenProject"
            result["project"] = project_path
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["error"] = repr(exc)
        finally:
            pythoncom.CoUninitialize()

    import threading
    t = threading.Thread(target=_call, daemon=True)
    t.start()
    t.join(60)
    if t.is_alive():
        return {"ok": False, "error": "timeout waiting for scFLOWpre"}
    return result


def run_open_vbs(project_path: str | Path, result_path: str | Path | None = None,
                 timeout: float = 60.0) -> dict:
    """生成 VBS 并经 ExecuteVBSWithFile 在宿主内打开工程。

    返回 ``{ok, method, vbs, result_path, com_open}``——``com_open`` 是
    用直接 COM 复核 OpenProject 的结果（VBS 自身的 FSO 结果文件为辅助）。
    """
    import pythoncom
    import win32com.client

    project_path = Path(project_path).resolve()
    result_path = Path(result_path) if result_path else \
        project_path.with_suffix(".accept.txt")
    vbs = build_open_vbs(result_path, project_path)

    out: dict = {"ok": False, "vbs": str(vbs), "result_path": str(result_path)}
    pythoncom.CoInitialize()
    try:
        app = win32com.client.Dispatch(PROGID_HOST)
        app._FlagAsMethod("ExecuteVBSWithFile", "ExecuteVBS")
        ok = bool(app.ExecuteVBSWithFile(str(vbs)))
        out["exec_ok"] = ok
        if not ok:
            out["error"] = "ExecuteVBSWithFile returned False"
            return out
    except Exception as exc:  # noqa: BLE001
        out["error"] = repr(exc)
        return out
    finally:
        pythoncom.CoUninitialize()

    # 等待 VBS 结果文件（辅助）；主验证用直接 COM 复核
    deadline = time.time() + timeout
    while time.time() < deadline and result_path.is_file() \
            and result_path.stat().st_size == 0:
        time.sleep(0.5)
    if result_path.is_file() and result_path.stat().st_size:
        out["vbs_result"] = result_path.read_text(encoding="utf-16",
                                                    errors="replace")
    out["com_open"] = run_open(project_path)
    out["ok"] = bool(out["com_open"].get("ok"))
    return out