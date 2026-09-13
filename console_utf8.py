#!/usr/bin/env python3
"""控制台编码兜底：把 stdout/stderr 切成 UTF-8 + replace。

背景（R3-1 实测）：经 PowerShell 管道运行脚本时，Python 的 stdout 使用
ANSI 代码页（本机 cp1252）。任何非该代码页字符（中文、方框字符）一打印就抛
UnicodeEncodeError —— 结果是「报告失败的过程本身失败」，把真实原因掩盖掉。

用法：在脚本入口尽早调用 ``console_utf8.enable()``。
"""

from __future__ import annotations

import sys


def enable() -> None:
    """幂等地把 stdout/stderr 切到 UTF-8 + errors=replace。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass          # 非 TextIOWrapper（如被重定向为管道包装）时跳过


if __name__ == "__main__":  # 自检
    enable()
    print("console_utf8 ok: " + str(sys.stdout.encoding))
