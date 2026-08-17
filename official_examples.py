#!/usr/bin/env python3
"""Cradle 2025.2 scFLOW 官方案例库路径（本机黄金，不入库）。

默认根目录：``D:\\training\\cradle\\CradleCFD_2025.2_scFLOW_Example_a``。
可用环境变量 ``PPH_OFFICIAL_EXAMPLES`` 覆盖。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

ENV_VAR = "PPH_OFFICIAL_EXAMPLES"

DEFAULT_ROOTS = (
    Path(r"D:\training\cradle\CradleCFD_2025.2_scFLOW_Example_a"),
)

# 覆盖 Cond* 精确 XML 键的精选 Org PPH（只读 main.xml/xenv/prp，不解析 GPH）
SCHEMA_CURATED = (
    "Exercise/exPRE01/exPRE01-1/Org/exPRE01-1.pph",
    "Exercise/exA03/exA03-1/Org/exA03-1.pph",
    "Exercise/exA06/exA06-2/Org/exA06-2_d_50.pph",
    "Exercise/exA10/exA10-1/Org/exA10-1.pph",
    "Exercise/exA11/exA11-1/Org/exA11-1.pph",
    "Exercise/exA13/exA13-1/Org/exA13-1.pph",
    "Exercise/exA16/exA16-1/Org/exA16-1.pph",
    "Exercise/exA16/exA16-3/Org/exA16-3.pph",
    "Exercise/exA17/exA17-9/Org/exA17-9.pph",
    "Exercise/exA17/exA17-10/Org/exA17-10.pph",
    "Exercise/exA18/exA18-4/Org/exA18-4.pph",
    "Exercise/exA24/exA24-1/Org/exA24-1.pph",
    "Exercise/exA25/exA25-1/Org/exA25-1.pph",
    "Exercise/exA26/exA26-1/Org/exA26-1_ldc.pph",
    "Exercise/exA32/exA32-1/Org/exA32-1.pph",
    "Exercise/exA34/exA34-2/Org/exA34-2_2.pph",
    "Exercise/exA36/exA36-1/Org/exA36-1.pph",
    "Exercise/exA36/exA36-4/Org/exA36-4_CASE1.pph",
    "Exercise/exB01/exB01-1/Org/exB01-1_intake_manifold.pph",
    "Exercise/exB03/exB03-1/Org/exB03-1_Acoustic.pph",
    "Exercise/exB03/exB03-1/Org/exB03-1_Fluid.pph",
    "Exercise/exB03/exB03-3/Org/exB03-3_Acoustic.pph",
    "Exercise/exB04/exB04-1/Org/exB04-1_Structural.pph",
    "Operation/tr03/Org/tr03.pph",
    "Operation/tut01/Org/tut01.pph",
)

DISC_PPH = "Exercise/exA16/exA16-1/Org/exA16-1.pph"
OVERSET_PPH = "Exercise/exA25/exA25-1/Org/exA25-1.pph"


def example_root() -> Optional[Path]:
    env = (os.environ.get(ENV_VAR) or "").strip()
    candidates = [Path(env)] if env else []
    candidates.extend(DEFAULT_ROOTS)
    for p in candidates:
        if p.is_dir() and (p / "Exercise").is_dir():
            return p
    return None


def example_pph(rel: str, *, root: Optional[Path] = None) -> Optional[Path]:
    base = root if root is not None else example_root()
    if base is None:
        return None
    path = base / rel
    return path if path.is_file() else None
