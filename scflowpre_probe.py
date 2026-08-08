#!/usr/bin/env python3
"""scFLOWpre 安装与 API 探测（只读）。

用于确认本机 Cradle 安装路径、关键 DLL 导出符号数量与 CLI 辅助工具，
为自动化桥（VBS/API/Native/Batch）提供可行性证据，不执行任何 GUI。
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Optional


INSTALL_DIR_CANDIDATES = [
    Path(r"C:\Program Files\Cradle\CradleCFD2025.2"),
    Path(r"C:\Program Files\Cradle\CradleCFD2025.1"),
    Path(r"C:\Program Files (x86)\Cradle\CradleCFD2025.2"),
]

PROGRAMS_SUBDIR = "Programs_x64"

KEY_DLLS = [
    "scFLOWpreCmd_Bx64net.dll",
    "scFLOWpreAPI_Bx64.dll",
    "scFLOWpreDB_Bx64.dll",
    "scFLOWpreGUI_Bx64net.dll",
    "SCTpreCore_Dx64.dll",
    "SCTpreLib_Dx64.dll",
    "SCTpreSolver_Dx64.dll",
    "SCTprime_Bx64.dll",
    "ParasolidGW_Bx64.dll",
    "ImportGeometry_Bx64.dll",
    "ZipLibrary.dll",
]

KEY_EXES = [
    "scFLOWpre_Bx64net.exe",
    "SCTpreCLIHelper_Bx64.exe",
    "SCTpref_Dx64net.exe",
    "scConverter_Dx64net.exe",
]


def find_install() -> Optional[Path]:
    """返回存在 ``Programs_x64/scFLOWpre_Bx64net.exe`` 的安装目录。"""
    for root in INSTALL_DIR_CANDIDATES:
        exe = root / PROGRAMS_SUBDIR / "scFLOWpre_Bx64net.exe"
        if exe.is_file():
            return root
    return None


def programs_dir() -> Optional[Path]:
    root = find_install()
    return root / PROGRAMS_SUBDIR if root else None


def find_program(name: str) -> Optional[Path]:
    base = programs_dir()
    if base is None:
        return None
    p = base / name
    return p if p.is_file() else None


def pe_exports(path: str | Path) -> list[str]:
    """纯 Python 读取 PE 导出表（无第三方依赖）。"""
    data = Path(path).read_bytes()
    if data[:2] != b"MZ":
        return []
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        return []
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsz = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    is64 = magic == 0x20B
    dd = opt + (112 if is64 else 96)
    exp_rva, exp_sz = struct.unpack_from("<II", data, dd)
    if not exp_rva:
        return []

    sections: list[tuple[int, int, int, int]] = []
    sec = opt + optsz
    for i in range(nsec):
        vsz, va, rs, raw = struct.unpack_from("<IIII", data, sec + i * 40 + 8)
        sections.append((va, vsz, raw, rs))

    def rva2off(rva: int) -> Optional[int]:
        for va, vsz, raw, rs in sections:
            if va <= rva < va + max(vsz, rs):
                return raw + (rva - va)
        return None

    off = rva2off(exp_rva)
    if off is None:
        return []
    nnames = struct.unpack_from("<I", data, off + 24)[0]
    naddr_off = rva2off(struct.unpack_from("<I", data, off + 32)[0])
    if naddr_off is None:
        return []
    names: list[str] = []
    for i in range(nnames):
        name_rva = struct.unpack_from("<I", data, naddr_off + i * 4)[0]
        no = rva2off(name_rva)
        if no is None:
            continue
        end = data.find(b"\x00", no)
        if end < 0:
            end = len(data)
        try:
            names.append(data[no:end].decode("ascii", "replace"))
        except UnicodeDecodeError:
            pass
    return names


def probe() -> dict:
    """汇总安装/API 探测结果。"""
    root = find_install()
    if root is None:
        return {"installed": False}
    base = root / PROGRAMS_SUBDIR
    dlls: dict[str, int] = {}
    for name in KEY_DLLS:
        p = base / name
        if p.is_file():
            try:
                dlls[name] = len(pe_exports(p))
            except OSError:
                dlls[name] = -1
    exes = {name: (base / name).is_file() for name in KEY_EXES}
    return {
        "installed": True,
        "install_dir": str(root),
        "programs_dir": str(base),
        "exes": exes,
        "dll_export_counts": dlls,
    }


def main() -> int:
    import json
    import sys
    result = probe()
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
