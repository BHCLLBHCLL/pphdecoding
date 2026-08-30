#!/usr/bin/env python3
"""Disc/Overset 工程指纹（冲刺 E · 域 11）——黄金对照与「同类」判定。

黄金（``tests/box_disc.pph`` / ``tests/box_overset.pph``，本机录制）钉死：

- 判别键：``conditions/parts_control/Discontinuous``——disc=true /
  overset=false；``conditions/file/rotor_info/filename`` 随工程干名
  （``<stem>_RotorInfo``）；
- 共同骨架：``parts/meshinggroup/movinggroup``（group=box）+
  ``conditions/overset`` 五子节（static_region/moving_regions/
  overset_option/disconnect_regions/contact_regions）+ GPH 成员；
- 注意：两黄金 ``parts_control/overset`` 均为 false——overset 语义由
  条件块承载，不在 parts_control 开关（实测钉死，勿猜）。

实机建组（``Doc.CreateDiscontinuousMeshingGroupWith/WithoutMovingPart``）
产物经 :func:`fingerprint_same_class` 与黄金比对，只断言结构同类
（键集合与判别键取值），不逐值复制（§9.7「成员与黄金同类」）。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

OVERSET_SKELETON = ("static_region", "moving_regions", "overset_option",
                    "disconnect_regions", "contact_regions")


def _main_xml(pph_path) -> "object":
    import pphxml
    with zipfile.ZipFile(pph_path) as z:
        raw = z.read("main.xml")
    return pphxml.parse_main_xml(raw)


def golden_fingerprint(pph_path) -> dict:
    """提取 Disc/Overset 结构指纹（判别键 + 骨架存在性）。"""
    import project_persist

    mx = _main_xml(pph_path)
    fp: dict = {}
    fp["flags"] = project_persist.read_parts_control_flags(mx)
    cond = mx.section("conditions")
    rotor = None
    file_sec = cond.find("file") if cond is not None else None
    if file_sec is not None:
        ri = file_sec.find("rotor_info")
        if ri is not None:
            fn = ri.find("filename")
            rotor = (fn.text or "").strip() if fn is not None else ""
    fp["rotor_filename"] = rotor
    ov = cond.find("overset") if cond is not None else None
    fp["overset_skeleton"] = (
        [c.tag for c in ov] if ov is not None else [])
    parts = mx.section("parts")
    mg = parts.find("meshinggroup") if parts is not None else None
    mvg = mg.find("movinggroup") if mg is not None else None
    fp["has_movinggroup"] = mvg is not None
    fp["movinggroup_names"] = []
    if mvg is not None:
        for g in mvg.iter("group"):
            nm = g.find("name")
            if nm is not None and (nm.text or "").strip():
                fp["movinggroup_names"].append(nm.text.strip())
    with zipfile.ZipFile(pph_path) as z:
        names = z.namelist()
    fp["gph_members"] = sorted(n for n in names if n.endswith(".gph"))
    fp["oct_members"] = sorted(n for n in names if n.endswith(".oct"))
    return fp


# 同类判定忽略的键（随工程名/环境变化，不属结构）
DEFAULT_IGNORE = ("rotor_filename",)


def fingerprint_same_class(new: dict, golden: dict,
                           ignore=DEFAULT_IGNORE) -> tuple[bool, list]:
    """结构同类判定：键集合一致 + 非忽略键取值一致。返回 (ok, diffs)。"""
    diffs = []
    keys = set(new) | set(golden)
    for k in sorted(keys):
        if k in ignore:
            continue
        nv, gv = new.get(k), golden.get(k)
        if nv != gv:
            diffs.append({"key": k, "new": nv, "golden": gv})
    return len(diffs) == 0, diffs


def rotor_stem(filename: str) -> str:
    """``box_disc_RotorInfo`` → ``box_disc``（无后缀返回原文）。"""
    suffix = "_RotorInfo"
    if filename and filename.endswith(suffix):
        return filename[: -len(suffix)]
    return filename


if __name__ == "__main__":
    import json
    import sys
    for arg in sys.argv[1:]:
        print("==", arg)
        print(json.dumps(golden_fingerprint(Path(arg)),
                         ensure_ascii=False, indent=1))
