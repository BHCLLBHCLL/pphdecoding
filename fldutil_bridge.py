#!/usr/bin/env python3
"""FLDUTIL_Bx64.dll —— GPH/MDL 节语义罗塞塔石碑 + 子进程隔离探测（G4）。

scFLOW 的 FLD 工具库导出 C API（Node/Panel/Solid/Pregn/Sregn/Var），命名精确
对应 CRDL-FLD 的 LS_* 节，是钉死节语义的「地面真值」。本模块不依赖宿主：

- ROSETTA：导出名 → (角色, LS_* 节, 语义) 映射表；
- fldutil_dll() / fldutil_exports()：DLL 定位与导出枚举（纯 PE 解析，只读）；
- probe_counts(path)：子进程隔离调用 Open_File / Get_*Num（ABI 未钉死，
  崩溃只发生在子进程，尽力而为返回结构化结果）。

注：直接 ctypes 调用未知签名的 DLL 有崩溃风险，故真实调用一律放子进程。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

from scflowpre_probe import pe_exports, programs_dir

DLL_NAME = "FLDUTIL_Bx64.dll"

# 导出名 → (角色, 对应节, 语义)
ROSETTA: dict[str, tuple[str, str, str]] = {
    "FLDUTIL_Add_Node": ("node", "LS_Nodes", "新增顶点"),
    "FLDUTIL_Get_NodeNum": ("node", "LS_Nodes", "顶点总数"),
    "FLDUTIL_Get_NodePX": ("node", "LS_Nodes", "顶点 X 坐标"),
    "FLDUTIL_Get_NodePY": ("node", "LS_Nodes", "顶点 Y 坐标"),
    "FLDUTIL_Get_NodePZ": ("node", "LS_Nodes", "顶点 Z 坐标"),
    "FLDUTIL_Add_Panel": ("face", "LS_Links / LS_Faces", "新增面"),
    "FLDUTIL_Get_PanelNum": ("face", "LS_Links", "面总数"),
    "FLDUTIL_Get_TypeOfPanel": ("face", "LS_Links(npe)", "面类型（顶点数）"),
    "FLDUTIL_Get_NodeNumOfPanel": ("face", "LS_Links(conn)", "面顶点数"),
    "FLDUTIL_Get_NodeIdOfPanel": ("face", "LS_Links(conn)", "面→顶点"),
    "FLDUTIL_Add_Solid": ("cell", "LS_Links(owner/neigh)", "新增单元"),
    "FLDUTIL_Get_SolidNum": ("cell", "LS_Links", "单元总数"),
    "FLDUTIL_Get_TypeOfSolid": ("cell", "Element_InformationFlag", "单元类型标志"),
    "FLDUTIL_Get_NodeNumOfSolid": ("cell", "LS_Links", "单元顶点数"),
    "FLDUTIL_Get_NodeIdOfSolid": ("cell", "LS_Links", "单元→顶点"),
    "FLDUTIL_Add_Sregn": ("sregn", "LS_SurfaceRegions", "新增面区域"),
    "FLDUTIL_Get_SregnNum": ("sregn", "LS_SurfaceRegions", "面区域数"),
    "FLDUTIL_Get_NameOfSregn": ("sregn", "LS_SurfaceRegions", "面区域名"),
    "FLDUTIL_Get_SolidIdOfSregn": ("sregn", "LS_SurfaceRegions", "面区域→相邻单元"),
    "FLDUTIL_Get_NodeNumOfSregn": ("sregn", "LS_SurfaceRegions", "面区域顶点数"),
    "FLDUTIL_Add_Pregn": ("pregn", "LS_VolumeRegions", "新增体区域（压力区域）"),
    "FLDUTIL_Get_PregnNum": ("pregn", "LS_VolumeRegions", "体区域数"),
    "FLDUTIL_Get_NameOfPregn": ("pregn", "LS_VolumeRegions", "体区域名"),
    "FLDUTIL_Get_PanelIdOfPregn": ("pregn", "LS_VolumeRegions", "体区域→面"),
    "FLDUTIL_Get_NodeNumOfPregn": ("pregn", "LS_VolumeRegions", "体区域顶点数"),
    "FLDUTIL_Add_Var": ("var", "（求解器场）", "新增场变量"),
    "FLDUTIL_Get_VarNum": ("var", "（求解器场）", "场变量数"),
    "FLDUTIL_Get_VarName": ("var", "（求解器场）", "场变量名"),
    "FLDUTIL_Get_VarType": ("var", "（求解器场）", "场变量类型"),
    "FLDUTIL_Open_File": ("io", "容器", "打开 FLD 文件"),
    "FLDUTIL_Close_File": ("io", "容器", "关闭 FLD 文件"),
    "FLDUTIL_Save_File": ("io", "容器", "保存 FLD 文件"),
}

# gphstats 解析器已覆盖的 FLDUTIL 角色 → 节
COVERAGE = {
    "node": "LS_Nodes",
    "face": "LS_Links",
    "cell": "LS_Links / Element_InformationFlag",
    "sregn": "LS_SurfaceRegions",
    "pregn": "LS_VolumeRegions",
}

# 反汇编钉死的 ABI（capstone，RVA 见各注释）：
#   FLDUTIL_Open_File @0x32260：rcx=path，edx=a2，r8d=a3 → int
#   FLDUTIL_Get_NodeNum @0x31380：ecx=handle（仅日志用，数据在全局）→ int
#   FLDUTIL_Close_File @0x30f20：ecx=handle → int(0)
#   FLDUTIL_Get_NodePX @0x31570：edx=node index（全局指针表）→ double
#   FLDUTIL_Get_NodeNumOfPanel @0x31400：edx=panel index → int
#   FLDUTIL_GetLastErrorString @0x31140：void → const char*
# 状态保存在 DLL 全局（单一当前文件），handle 仅用于日志/校验。
SIGNATURES = {
    "FLDUTIL_Open_File": (("path", "char*"), ("a2", "int"), ("a3", "int"), "int"),
    "FLDUTIL_Close_File": (("handle", "int"), None, None, "int"),
    "FLDUTIL_Get_NodeNum": (("handle", "int"), None, None, "int"),
    "FLDUTIL_Get_NodePX": (("index", "int"), None, None, "double"),
    "FLDUTIL_Get_NodePY": (("index", "int"), None, None, "double"),
    "FLDUTIL_Get_NodePZ": (("index", "int"), None, None, "double"),
    "FLDUTIL_Get_NodeNumOfPanel": (("index", "int"), None, None, "int"),
    "FLDUTIL_Get_PanelNum": (("handle", "int"), None, None, "int"),
    "FLDUTIL_Get_SolidNum": (("handle", "int"), None, None, "int"),
    "FLDUTIL_Get_SregnNum": (("handle", "int"), None, None, "int"),
    "FLDUTIL_Get_PregnNum": (("handle", "int"), None, None, "int"),
    "FLDUTIL_GetLastErrorString": (None, None, None, "char*"),
}


def fldutil_dll() -> Optional[Path]:
    """定位 FLDUTIL_Bx64.dll，找不到返回 None。"""
    base = programs_dir()
    if base is None:
        return None
    p = Path(base) / DLL_NAME
    return p if p.exists() else None


def fldutil_exports() -> list[str]:
    """枚举 FLDUTIL_Bx64.dll 导出（纯 PE 解析，不加载 DLL）。"""
    p = fldutil_dll()
    return pe_exports(p) if p else []


def rosace(role: Optional[str] = None) -> list[tuple[str, str, str]]:
    """返回 ROSETTA 子集：[(导出名, 角色, 节)]；role 为 None 返回全部。"""
    out = []
    for name, (r, sec, desc) in sorted(ROSETTA.items()):
        if role is None or r == role:
            out.append((name, r, sec))
    return out


def coverage_gaps() -> dict:
    """把 FLDUTIL 概念面（node/face/cell/sregn/pregn）映射到 gphstats 覆盖节。"""
    return dict(COVERAGE)


def probe_counts(path: str | Path) -> dict:
    """子进程隔离探测 FLDUTIL 计数（尽力而为，ABI 未钉死）。

    真实 ctypes 调用放在子进程：签名是猜测（Open_File: int(char*)，
    Get_*Num: int(int)），崩溃/异常只影响子进程，父进程返回结构化结果。
    返回：{available, dll, returncode, stdout, stderr}。
    """
    dll = fldutil_dll()
    if dll is None:
        return {"available": False, "reason": "FLDUTIL_Bx64.dll not found"}

    script = f'''
import ctypes
p = r"{Path(path).resolve()}"
dll = ctypes.CDLL(r"{dll}")
print("loaded", dll._name)
try:
    # 反汇编钉死：Open_File(path, int, int) → int；状态在 DLL 全局
    f = dll.FLDUTIL_Open_File
    f.restype = ctypes.c_int
    f.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    h = f(p.encode("ascii"), 0, 0)
    print("open_handle", h)
    for nm, narg in (("FLDUTIL_Get_NodeNum", 1), ("FLDUTIL_Get_PanelNum", 1),
                     ("FLDUTIL_Get_SolidNum", 1), ("FLDUTIL_Get_SregnNum", 1),
                     ("FLDUTIL_Get_PregnNum", 1),
                     ("FLDUTIL_Get_NodeNumOfPanel", 1)):
        try:
            fn = getattr(dll, nm)
            fn.restype = ctypes.c_int
            fn.argtypes = [ctypes.c_int] * narg
            print(nm, fn(0 if narg == 1 else 0))
        except Exception as e:
            print(nm, "ERR", repr(e))
    try:
        gx = dll.FLDUTIL_Get_NodePX
        gx.restype = ctypes.c_double
        gx.argtypes = [ctypes.c_int]
        print("FLDUTIL_Get_NodePX(0)", gx(0))
    except Exception as e:
        print("NodePX ERR", repr(e))
    try:
        dll.FLDUTIL_Close_File.restype = ctypes.c_int
        dll.FLDUTIL_Close_File.argtypes = [ctypes.c_int]
        print("Close_File", dll.FLDUTIL_Close_File(int(h)))
    except Exception as e:
        print("Close ERR", repr(e))
except Exception as e:
    print("ERR", repr(e))
'''
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=30)
        return {
            "available": True,
            "dll": str(dll),
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"available": True, "dll": str(dll), "returncode": -1,
                "stdout": "", "stderr": "timeout (ABI hang?)"}


if __name__ == "__main__":
    print("DLL:", fldutil_dll())
    ex = fldutil_exports()
    print("exports:", len(ex))
    for name, r, sec in rosace():
        print(f"  {name:38s} {r:6s} -> {sec}")
