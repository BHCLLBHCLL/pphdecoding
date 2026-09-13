#!/usr/bin/env python3
"""宿主路径纪律：交给宿主的路径必须绝对（R15-1）。

踩过两次的坑：

* CADthru 转换：它是独立进程，CWD 与本进程不同 → 相对路径被解析到别处（ret=0 且文件缺失）；
* 宿主 OpenCadFile：同样原因 → 静默返回 Nothing，表现为 sn_=False / ret_bam=False，
  看起来像「格式不被接受」。R14-1 因此一度把 CADthru 的 v37 产物误判为「宿主拒收」，
  真因是传了相对路径。

用法：凡是拼进 VBS 字符串的路径，先过 require_abs() —— 传相对路径当场报错，
而不是让宿主静默失败。
"""

from __future__ import annotations

from pathlib import Path


class RelativeHostPath(ValueError):
    """交给宿主的路径不是绝对路径（会导致静默 Nothing / ret=0）。"""


def require_abs(path, *, what: str = "host path") -> Path:
    """返回绝对 Path；相对路径直接抛 RelativeHostPath。

    已存在的绝对路径原样返回（不 resolve 软链接），避免破坏比对与缓存键。
    """
    p = Path(path)
    if not p.is_absolute():
        raise RelativeHostPath(
            what + " must be absolute: " + str(path) +
            " —— 宿主 CWD 与本进程不同，相对路径会静默失败（见 R14-1）")
    return p


def abs_str(path, *, what: str = "host path") -> str:
    """POSIX 风格绝对路径字符串（VBS 里用正斜杠最稳）。"""
    return require_abs(path, what=what).as_posix()
