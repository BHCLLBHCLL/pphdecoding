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

PIPELINE_SYMBOLS = [
    ("SCTprime_Bx64.dll", "CreateShapeGroupSet"),
    ("SCTprime_Bx64.dll", "CreateShapeGroup"),
    ("SCTprime_Bx64.dll", "CreateMDL"),
    ("SCTprime_Bx64.dll", "CreateFacetOctree"),
    ("SCTprime_Bx64.dll", "ExecuteWrapping"),
    ("SCTprime_Bx64.dll", "CreateMeshOctreeByDefaultParam"),
    ("SCTprime_Bx64.dll", "ConvertFacetToXT"),
    ("ZipLibrary.dll", "ExpandZip"),
    ("scFLOWpreAPI_Bx64.dll", "ExecuteVBS"),
]


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


def pipeline_status() -> dict:
    """Probe key preprocessing pipeline symbols through the bridge."""
    lib = load()
    if lib is None:
        return {
            "bridge_compiled": False,
            "hint": "run native/build.ps1 to build the NativeBridge",
            "symbols": {name: False for _, name in PIPELINE_SYMBOLS},
        }
    programs_dir = scflowpre_probe.programs_dir()
    if programs_dir is None:
        return {"bridge_compiled": True, "error": "scFLOWpre not installed"}
    lib.scf_initialize.argtypes = [ctypes.c_wchar_p]
    lib.scf_initialize.restype = ctypes.c_int
    lib.scf_pipeline_probe.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
    lib.scf_pipeline_probe.restype = ctypes.c_int
    lib.scf_finalize.argtypes = []
    lib.scf_initialize(str(programs_dir))
    buf = ctypes.create_unicode_buffer(STATUS_BUFFER)
    lib.scf_pipeline_probe(buf, STATUS_BUFFER)
    lib.scf_finalize()
    symbols: dict[str, bool] = {}
    for line in (buf.value or "").splitlines():
        if "|" in line and "=" in line:
            head, _, tail = line.rpartition("=")
            module, _, name = head.partition("|")
            symbols[f"{module}:{name}"] = tail == "1"
    return {
        "bridge_compiled": True,
        "programs_dir": str(programs_dir),
        "symbols": symbols,
    }


def expand_zip(zip_path: str | Path, out_dir: str | Path) -> dict:
    """Actually call ZipLibrary.ExpandZip through the bridge."""
    lib = load()
    if lib is None:
        raise RuntimeError("NativeBridge not built; run native/build.ps1")
    programs_dir = scflowpre_probe.programs_dir()
    if programs_dir is None:
        raise RuntimeError("scFLOWpre not installed")
    lib.scf_initialize.argtypes = [ctypes.c_wchar_p]
    lib.scf_initialize.restype = ctypes.c_int
    lib.scf_call_zip_expand.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    lib.scf_call_zip_expand.restype = ctypes.c_int
    lib.scf_finalize.argtypes = []
    lib.scf_initialize(str(programs_dir))
    rc = lib.scf_call_zip_expand(str(zip_path), str(out_dir))
    lib.scf_finalize()
    return {"returncode": rc, "zip": str(zip_path), "out_dir": str(out_dir)}


def main() -> int:
    import argparse
    import json
    import sys

    ap = argparse.ArgumentParser(description="NativeBridge status/calls")
    ap.add_argument("--pipeline", action="store_true",
                    help="print preprocessing pipeline symbol probe")
    ap.add_argument("--expand-zip", nargs=2, metavar=("ZIP", "OUT"),
                    help="call ZipLibrary.ExpandZip")
    args = ap.parse_args()
    if args.expand_zip:
        result = expand_zip(args.expand_zip[0], args.expand_zip[1])
    elif args.pipeline:
        result = pipeline_status()
    else:
        result = status()
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
