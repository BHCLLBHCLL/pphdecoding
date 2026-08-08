#!/usr/bin/env python3
"""NativeBridge Python 加载器（M2）。

优先加载 ``native/out/scflow_bridge.dll``（由 native/build.ps1 编译）；
未编译时回退到 :mod:`scflowpre_probe` 的纯 Python 探测结果。
"""

from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Optional

import scflowpre_probe

ROOT = Path(__file__).resolve().parent
BRIDGE_DLL = ROOT / "native" / "out" / "scflow_bridge.dll"
STATUS_BUFFER = 8192


def bridge_path() -> Path:
    return BRIDGE_DLL


def is_compiled() -> bool:
    return BRIDGE_DLL.is_file()


def load() -> Optional[ctypes.CDLL]:
    """加载桥 DLL；未编译/加载失败返回 None。"""
    if not is_compiled():
        return None
    try:
        return ctypes.CDLL(str(BRIDGE_DLL))
    except OSError:
        return None


def status() -> dict:
    """返回桥状态；未编译时给出纯 Python 探测回退。"""
    lib = load()
    if lib is None:
        return {
            "bridge_compiled": False,
            "hint": "运行 native/build.ps1 编译 NativeBridge",
            "fallback": scflowpre_probe.probe(),
        }
    programs_dir = scflowpre_probe.programs_dir()
    if programs_dir is None:
        return {"bridge_compiled": True, "error": "scFLOWpre 未安装"}
    lib.scf_initialize.argtypes = [ctypes.c_wchar_p]
    lib.scf_initialize.restype = ctypes.c_int
    lib.scf_status.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
    lib.scf_status.restype = ctypes.c_int
    lib.scf_finalize.argtypes = []

    loaded = lib.scf_initialize(str(programs_dir))
    buf = ctypes.create_unicode_buffer(STATUS_BUFFER)
    n = lib.scf_status(buf, STATUS_BUFFER)
    summary = buf.value if n >= 0 else ""
    lib.scf_finalize()
    return {
        "bridge_compiled": True,
        "programs_dir": str(programs_dir),
        "loaded_modules": loaded,
        "status": summary,
    }


def main() -> int:
    import json
    import sys

    json.dump(status(), sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
