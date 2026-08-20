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

SCF_ERR_OK = 0
SCF_ERR_ARG = -1
SCF_ERR_CONTEXT_NOT_READY = -100
SCF_ERR_EXCEPTION = -101
SCF_ERR_SYMBOL = -102
SCF_ERR_NULL_OBJECT = -103

_ERROR_MESSAGES = {
    SCF_ERR_ARG: "invalid argument",
    SCF_ERR_CONTEXT_NOT_READY: (
        "SCTprime host context is not ready: CreateShapeGroupSet must run "
        "inside a live scFLOWpre process (or after the host document is open)"),
    SCF_ERR_EXCEPTION: "access violation inside SCTprime",
    SCF_ERR_SYMBOL: "pipeline symbol not resolved",
    SCF_ERR_NULL_OBJECT: "SCTprime returned a null interface object",
}

_INITIALIZED_LIB: Optional[ctypes.CDLL] = None
_INITIALIZED_MODULES: int = 0
_OBJECT_BUFFERS: dict[int, object] = {}


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


def _ensure_initialized() -> ctypes.CDLL:
    """Load the bridge and keep the vendor DLLs resident for handle calls."""
    global _INITIALIZED_LIB
    if _INITIALIZED_LIB is not None:
        return _INITIALIZED_LIB
    lib = load()
    if lib is None:
        raise RuntimeError("NativeBridge not built; run native/build.ps1")
    programs_dir = scflowpre_probe.programs_dir()
    if programs_dir is None:
        raise RuntimeError("scFLOWpre not installed")
    lib.scf_initialize.argtypes = [ctypes.c_wchar_p]
    lib.scf_initialize.restype = ctypes.c_int
    lib.scf_status.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
    lib.scf_status.restype = ctypes.c_int
    lib.scf_pipeline_probe.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
    lib.scf_pipeline_probe.restype = ctypes.c_int
    lib.scf_call_zip_expand.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    lib.scf_call_zip_expand.restype = ctypes.c_int
    lib.scf_pipeline_context_ready.argtypes = []
    lib.scf_pipeline_context_ready.restype = ctypes.c_int
    lib.scf_pipeline_create_shape_group_set.argtypes = [
        ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
    lib.scf_pipeline_create_shape_group_set.restype = ctypes.c_int
    lib.scf_pipeline_create_shape_group.argtypes = [
        ctypes.c_uint64, ctypes.c_wchar_p, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int)]
    lib.scf_pipeline_create_shape_group.restype = ctypes.c_int
    lib.scf_pipeline_create_mdl.argtypes = [
        ctypes.c_uint64, ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int)]
    lib.scf_pipeline_create_mdl.restype = ctypes.c_int
    # P11 深管线（ErrorCode 返回；引用参数 IOctree& 按指针传）
    lib.scf_pipeline_create_facet_octree.argtypes = [
        ctypes.c_uint64, ctypes.c_wchar_p, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    lib.scf_pipeline_create_facet_octree.restype = ctypes.c_int
    lib.scf_pipeline_execute_wrapping.argtypes = [
        ctypes.c_uint64, ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int)]
    lib.scf_pipeline_execute_wrapping.restype = ctypes.c_int
    lib.scf_pipeline_create_mesh_octree.argtypes = [
        ctypes.c_uint64, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    lib.scf_pipeline_create_mesh_octree.restype = ctypes.c_int
    lib.scf_pipeline_convert_facet_to_xt.argtypes = [
        ctypes.c_wchar_p, ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    lib.scf_pipeline_convert_facet_to_xt.restype = ctypes.c_int
    global _INITIALIZED_MODULES
    _INITIALIZED_MODULES = int(lib.scf_initialize(str(programs_dir)))
    _INITIALIZED_LIB = lib
    return lib


def status() -> dict:
    """返回桥状态；未编译时给出纯 Python 探测回退。"""
    try:
        lib = _ensure_initialized()
    except RuntimeError:
        return {
            "bridge_compiled": False,
            "hint": "运行 native/build.ps1 编译 NativeBridge",
            "fallback": scflowpre_probe.probe(),
        }
    programs_dir = scflowpre_probe.programs_dir()
    if programs_dir is None:
        return {"bridge_compiled": True, "error": "scFLOWpre 未安装"}
    buf = ctypes.create_unicode_buffer(STATUS_BUFFER)
    n = lib.scf_status(buf, STATUS_BUFFER)
    summary = buf.value if n >= 0 else ""
    return {
        "bridge_compiled": True,
        "programs_dir": str(programs_dir),
        "loaded_modules": _INITIALIZED_MODULES,
        "status": summary,
    }


def pipeline_status() -> dict:
    """Probe key preprocessing pipeline symbols through the bridge."""
    if not is_compiled():
        return {
            "bridge_compiled": False,
            "hint": "run native/build.ps1 to build the NativeBridge",
            "symbols": {name: False for _, name in PIPELINE_SYMBOLS},
        }
    lib = _ensure_initialized()
    programs_dir = scflowpre_probe.programs_dir()
    if programs_dir is None:
        return {"bridge_compiled": True, "error": "scFLOWpre not installed"}
    buf = ctypes.create_unicode_buffer(STATUS_BUFFER)
    lib.scf_pipeline_probe(buf, STATUS_BUFFER)
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
    lib = _ensure_initialized()
    rc = lib.scf_call_zip_expand(str(zip_path), str(out_dir))
    return {"returncode": rc, "zip": str(zip_path), "out_dir": str(out_dir)}


def _error_message(code: int) -> str:
    return _ERROR_MESSAGES.get(code, f"unknown error {code}")


def _describe_wrapper(handle: int, buf) -> dict:
    ptr = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint64)).contents.value
    ident = ctypes.cast(ctypes.c_void_p(ctypes.addressof(buf) + 8),
                        ctypes.POINTER(ctypes.c_int32)).contents.value
    return {"handle": handle, "ptr": ptr, "id": ident, "valid": ptr != 0}


def pipeline_context_ready() -> dict:
    """Check whether the SCTprime host document context is available."""
    lib = _ensure_initialized()
    rc = int(lib.scf_pipeline_context_ready())
    return {"ready": rc == 1, "returncode": rc}


def create_shape_group_set(name: str) -> dict:
    """Call SCTprime::CreateShapeGroupSet and keep the wrapper alive."""
    lib = _ensure_initialized()
    buf = (ctypes.c_ubyte * 16)()
    err = ctypes.c_int(0)
    rc = lib.scf_pipeline_create_shape_group_set(
        name, ctypes.byref(buf), ctypes.byref(err))
    if rc != 1:
        return {"ok": False, "error_code": int(err.value),
                "message": _error_message(int(err.value))}
    handle = ctypes.addressof(buf)
    _OBJECT_BUFFERS[handle] = buf
    result = _describe_wrapper(handle, buf)
    result["ok"] = True
    return result


def create_shape_group(handle: int, name: str) -> dict:
    """Call IShapeGroupSet::CreateShapeGroup(handle, name, empty nodes)."""
    if handle not in _OBJECT_BUFFERS:
        return {"ok": False, "error_code": SCF_ERR_ARG,
                "message": "unknown shape group set handle"}
    lib = _ensure_initialized()
    out = (ctypes.c_ubyte * 16)()
    err = ctypes.c_int(0)
    rc = lib.scf_pipeline_create_shape_group(
        handle, name, ctypes.byref(out), ctypes.byref(err))
    if rc != 1:
        return {"ok": False, "error_code": int(err.value),
                "message": _error_message(int(err.value))}
    new_handle = ctypes.addressof(out)
    _OBJECT_BUFFERS[new_handle] = out
    result = _describe_wrapper(new_handle, out)
    result["ok"] = True
    return result


def create_mdl(handle: int) -> dict:
    """Call IShapeGroup::CreateMDL(handle)."""
    if handle not in _OBJECT_BUFFERS:
        return {"ok": False, "error_code": SCF_ERR_ARG,
                "message": "unknown shape group handle"}
    lib = _ensure_initialized()
    ok = ctypes.c_int(0)
    err = ctypes.c_int(0)
    rc = lib.scf_pipeline_create_mdl(handle, ctypes.byref(ok),
                                     ctypes.byref(err))
    if rc != 1:
        return {"ok": False, "error_code": int(err.value),
                "message": _error_message(int(err.value))}
    return {"ok": True, "result": bool(ok.value), "handle": handle}


def create_facet_octree(handle: int, name: str) -> dict:
    """Call IShapeGroup::CreateFacetOctree(name, IOctree&) (P11)."""
    if handle not in _OBJECT_BUFFERS:
        return {"ok": False, "error_code": SCF_ERR_ARG,
                "message": "unknown shape group handle"}
    lib = _ensure_initialized()
    out = (ctypes.c_ubyte * 16)()
    error_code = ctypes.c_int(0)
    err = ctypes.c_int(0)
    rc = lib.scf_pipeline_create_facet_octree(
        handle, name, ctypes.byref(out), ctypes.byref(error_code),
        ctypes.byref(err))
    if rc != 1:
        return {"ok": False, "error_code": int(err.value),
                "message": _error_message(int(err.value))}
    result = {"ok": True, "sct_error_code": int(error_code.value)}
    if int(error_code.value) == 0:
        new_handle = ctypes.addressof(out)
        _OBJECT_BUFFERS[new_handle] = out
        result.update(_describe_wrapper(new_handle, out))
    return result


def execute_wrapping(handle: int) -> dict:
    """Call IShapeGroup::ExecuteWrapping() (P11)."""
    if handle not in _OBJECT_BUFFERS:
        return {"ok": False, "error_code": SCF_ERR_ARG,
                "message": "unknown shape group handle"}
    lib = _ensure_initialized()
    error_code = ctypes.c_int(0)
    err = ctypes.c_int(0)
    rc = lib.scf_pipeline_execute_wrapping(handle, ctypes.byref(error_code),
                                           ctypes.byref(err))
    if rc != 1:
        return {"ok": False, "error_code": int(err.value),
                "message": _error_message(int(err.value))}
    return {"ok": True, "sct_error_code": int(error_code.value)}


def create_mesh_octree(handle: int) -> dict:
    """Call IVMDL::CreateMeshOctreeByDefaultParam(IOctree&) (P11)."""
    if handle not in _OBJECT_BUFFERS:
        return {"ok": False, "error_code": SCF_ERR_ARG,
                "message": "unknown mdl handle"}
    lib = _ensure_initialized()
    out = (ctypes.c_ubyte * 16)()
    error_code = ctypes.c_int(0)
    err = ctypes.c_int(0)
    rc = lib.scf_pipeline_create_mesh_octree(
        handle, ctypes.byref(out), ctypes.byref(error_code), ctypes.byref(err))
    if rc != 1:
        return {"ok": False, "error_code": int(err.value),
                "message": _error_message(int(err.value))}
    result = {"ok": True, "sct_error_code": int(error_code.value)}
    if int(error_code.value) == 0:
        new_handle = ctypes.addressof(out)
        _OBJECT_BUFFERS[new_handle] = out
        result.update(_describe_wrapper(new_handle, out))
    return result


def convert_facet_to_xt(src: str | Path, dst: str | Path) -> dict:
    """Call SCTprime::ConvertFacetToXT(src, dst) (P11)."""
    lib = _ensure_initialized()
    error_code = ctypes.c_int(0)
    err = ctypes.c_int(0)
    rc = lib.scf_pipeline_convert_facet_to_xt(
        str(src), str(dst), ctypes.byref(error_code), ctypes.byref(err))
    if rc != 1:
        return {"ok": False, "error_code": int(err.value),
                "message": _error_message(int(err.value))}
    return {"ok": True, "sct_error_code": int(error_code.value)}


def release(handle: int) -> bool:
    """Drop the Python-side wrapper buffer for a pipeline handle."""
    return _OBJECT_BUFFERS.pop(handle, None) is not None


def main() -> int:
    import argparse
    import json
    import sys

    ap = argparse.ArgumentParser(description="NativeBridge status/calls")
    ap.add_argument("--pipeline", action="store_true",
                    help="print preprocessing pipeline symbol probe")
    ap.add_argument("--expand-zip", nargs=2, metavar=("ZIP", "OUT"),
                    help="call ZipLibrary.ExpandZip")
    ap.add_argument("--pipeline-context", action="store_true",
                    help="check SCTprime host context readiness")
    ap.add_argument("--pipeline-create-set", metavar="NAME",
                    help="call CreateShapeGroupSet")
    ap.add_argument("--pipeline-create-group", nargs=2,
                    metavar=("HANDLE", "NAME"),
                    help="call CreateShapeGroup")
    ap.add_argument("--pipeline-create-mdl", metavar="HANDLE",
                    help="call CreateMDL")
    ap.add_argument("--pipeline-release", metavar="HANDLE",
                    help="drop a pipeline handle")
    args = ap.parse_args()
    if args.pipeline_context:
        result = pipeline_context_ready()
    elif args.pipeline_create_set:
        result = create_shape_group_set(args.pipeline_create_set)
    elif args.pipeline_create_group:
        handle = int(args.pipeline_create_group[0], 0)
        result = create_shape_group(handle, args.pipeline_create_group[1])
    elif args.pipeline_create_mdl:
        result = create_mdl(int(args.pipeline_create_mdl, 0))
    elif args.pipeline_release:
        result = {"released": release(int(args.pipeline_release, 0))}
    elif args.expand_zip:
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
