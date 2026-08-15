#!/usr/bin/env python3
"""FPH（scFLOW 多面体求解器结果文件）解析。

FPH = CRDL-FLD 容器 + 多面体网格 + 单元中心 / 面中心场量（Samples_POST/FPH）：

* 网格节
  - LS_Nodes：X/Y/Z 三个等长 f32 轴块；
  - LS_Links：owner / neigh / npe 三个等长 I4 块 + 平铺面→节点连接表，
    连接表节点号 0 基（与 GPH 的 1 基不同，由 minimumPolyhedral 验证）；
  - LS_CvolIdOfElements：每单元控制体 id（u32 块）；
  - LS_Parts / LS_MaterialOfParts / LS_VolumeRegions / LS_SurfaceRegions：
    命名列表 + 少量描述符；LS_SurfaceRegions 每个区域 = 名字 + 面 id 数组
    （1 基全局面号）+ 每面属性数组（标志/BC，语义未完全确认）；
  - LS_Assemblies：装配 XML；Element_Center：单元中心坐标 f32×3；
    LS_SPHFile：SDAT 设置文本。
* 场量节
  - EC_Scalar:* / EC_Vector:*（单元中心）/ FC_Scalar:*（面中心）为元数据节：
    若干描述符 + 末尾携带目标数据节名字符串
    （[12][1][32][1] + [12][32]"pressure"[32] 形式）；
  - 数据本体在与目标名相同的节（pressure / velocity / YPLS / SURT 等）：
    标量 = 1 个 f32 块；矢量 = 3 个 f32 块（X/Y/Z）；
    FC 场 = 3 个块 [面 id u32][标志 u32][值 f32]。

记录流与 FLD/GPH 相同：16 字节小记录 [12][type][dim0][dim1]（type 1/4/8，
type=1 时 dim0 = 后续字符串长度）与数据块 [12][bc][payload][bc]；[12][0]
为节终止哨兵。

注意：元数据节末尾的目标节名字符串以 [12][32] 开头，其中 [32] 会被通用节
扫描误认成下一节的 [I4=32] 节头（把下一节起点整体前移 40 字节）。本模块
一律用容错游标逐记录解析（跳过非 [12] 的 4 字节字），不依赖节边界精度，
因此两种边界都能正确读取。
"""

from __future__ import annotations

import struct
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

import numpy as np

import crdlfld
from gphstats import build_cells

MAGIC = crdlfld.MAGIC

# EC_/FC_ 元数据节 → 数据节名（元数据节自带目标名字符串时优先用它）
FIELD_TARGET_NAMES = {
    "EC_Scalar:PRES": "pressure",
    "EC_Scalar:DENS": "density",
    "EC_Scalar:TEMP": "temperature",
    "EC_Scalar:TURK": "turbulence energy",
    "EC_Scalar:TEPS": "turbulence dissipation rate",
    "EC_Scalar:EVIS": "eddy viscosity",
    "EC_Scalar:ENTL": "enthalpy",
    "EC_Vector:VEL": "velocity",
    "FC_Scalar:YPLS": "YPLS",
    "FC_Scalar:SURT": "SURT",
}


def iter_fph_records(data, start: int, end: int, slack: int = 0):
    """容错记录游标：逐条解析 [12] 记录流。

    yield ("desc", type_code, dim0, dim1) 或 ("blk", offset, bc)；
    非 [12] 开头的 4 字节字（如误判节边界带来的节头残片）被跳过。

    [12][0][0][0][12] 同时用作「空数组块」与「节终止哨兵」：消费 20 字节后
    偷看下一字，仍为 [12] 则当作空数组继续，否则（下一节节头 [32] 等）
    终止。slack 用于元数据节（其节尾因目标名字符串被误判前移 40 字节）。
    """
    pos = start
    n = min(end + slack, len(data))
    while pos + 8 <= n:
        if crdlfld.read_i32_be(data, pos) != 12:
            pos += 4
            continue
        v = crdlfld.read_i32_be(data, pos + 4)
        if v in (1, 4, 8) and pos + 16 <= n:
            dim0 = crdlfld.read_i32_be(data, pos + 8)
            dim1 = crdlfld.read_i32_be(data, pos + 12)
            if 0 <= dim0 < 100_000_000 and 0 < dim1 < 100_000_000:
                yield ("desc", v, dim0, dim1)
                pos += 16
                continue
        if v == 0 and pos + 12 <= n:
            # 空数组块 = [12][0][0]（12 字节）；节终止哨兵 = [12][0][0][0][12]
            # 或 [12][0][0][12]。统一消费 [12][0][0] 后偷看：后面还有 [12]
            # 记录则是空数组（继续），否则是节终止（停止）。
            pos += 12
            if pos + 8 <= n and crdlfld.read_i32_be(data, pos) == 12:
                continue
            return
        if v <= 0:
            return
        if pos + 8 + v + 4 > n:
            return
        if crdlfld.read_i32_be(data, pos + 8 + v) != v:
            pos += 4
            continue
        yield ("blk", pos + 8, v)
        pos += 8 + v + 4


def _records(data, start, end, slack: int = 0) -> list:
    return list(iter_fph_records(data, start, end, slack))


def _blocks(data, start, end):
    out = []
    for rec in _records(data, start, end):
        if rec[0] == "blk":
            out.append((rec[1], rec[2]))
    return out


def _strings(data, start, end, slack: int = 0):
    """提取节内字符串：desc(1,L,1) + 紧跟的 L 字节 ASCII 数据块。"""
    recs = _records(data, start, end, slack)
    out = []
    for i, rec in enumerate(recs):
        if rec[0] != "desc" or rec[1] != 1 or rec[2] <= 0:
            continue
        L = rec[2]
        if (i + 1 < len(recs) and recs[i + 1][0] == "blk"
                and recs[i + 1][2] == L):
            off = recs[i + 1][1]
            raw = bytes(data[off:off + L])
            if all(b == 32 or 33 <= b < 127 for b in raw):
                out.append(raw.decode("ascii").rstrip())
    return out


def _u32_arrays(data, start, end):
    """节内所有 4 字节对齐数据块，按出现顺序转成 u32 数组。"""
    out = []
    for off, bc in _blocks(data, start, end):
        if bc >= 4 and bc % 4 == 0:
            out.append(np.frombuffer(data, dtype=">u4", count=bc // 4,
                                     offset=off).astype(np.uint64))
    return out


def _section_span(data, name, sections=None):
    """返回节的记录流区间（先精确后忽略大小写）；找不到返回 (0, 0)。"""
    secs = sections if sections is not None else crdlfld.scan_sections(data)
    for s in secs:
        if s.name == name:
            return s.records_start, s.end
    for s in secs:
        if s.name.lower() == name.lower():
            return s.records_start, s.end
    return 0, 0


def fph_vertices(data):
    """LS_Nodes：三个等长 f32 轴块 → (n,3) f64 坐标。"""
    start, end = _section_span(data, "LS_Nodes")
    if not end:
        return None
    blks = [(off, bc) for off, bc in _blocks(data, start, end)
            if bc >= 4 and bc % 4 == 0]
    sizes = [bc for _, bc in blks]
    if not sizes:
        return None
    target = max(set(sizes), key=sizes.count)
    trio = [(off, bc) for off, bc in blks if bc == target][:3]
    if len(trio) < 3 or target % 4:
        return None
    n = target // 4
    axes = [np.frombuffer(data, dtype=">f4", count=n, offset=off)
            for off, _ in trio]
    return np.column_stack(axes).astype(np.float64)


def fph_links(data) -> dict:
    """LS_Links：owner/neigh/npe（I4/u4）+ 平铺连接表（0 基节点号）。

    与 gphstats.parse_mesh 相同的块分组逻辑；返回 n_faces / owner /
    neigh（0xFFFFFFFF=边界面）/ npe / conn / face_offsets /
    boundary_mask。
    """
    start, end = _section_span(data, "LS_Links")
    if not end:
        return {}
    blocks = [(off, bc) for off, bc in _blocks(data, start, end)
              if bc > 0 and bc % 4 == 0]
    if len(blocks) < 4:
        return {}
    sizes = [bc for _, bc in blocks]
    n_faces_block_size = None
    for size, count in Counter(sizes).most_common():
        if count >= 3 and size % 4 == 0 and size >= 4:
            n_faces_block_size = size
            break
    if n_faces_block_size is None:
        return {}
    n_faces = n_faces_block_size // 4
    triples = [b for b in blocks if b[1] == n_faces_block_size][:3]
    if len(triples) < 3:
        return {}
    (owner_p, _), (neigh_p, _), (npe_p, _) = triples
    owner = np.frombuffer(data, dtype=">i4", count=n_faces,
                          offset=owner_p).astype(np.int64)
    neigh = np.frombuffer(data, dtype=">u4", count=n_faces,
                          offset=neigh_p).astype(np.int64)
    npe = np.frombuffer(data, dtype=">u4", count=n_faces,
                        offset=npe_p).astype(np.int64)
    conn_total = int(npe.sum())
    conn_parts = [b for b in blocks if b[1] == conn_total * 4 and b[1] > 0]
    if not conn_parts:
        return {}
    conn = np.concatenate([
        np.frombuffer(data, dtype=">u4", count=conn_total, offset=p)
        for p, bc in conn_parts if bc == conn_total * 4])
    if conn.size != conn_total:
        return {}
    offsets = np.empty(n_faces + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(npe, out=offsets[1:])
    return {
        "n_faces": n_faces,
        "owner": owner,
        "neigh": neigh,
        "npe": npe,
        "conn": conn.astype(np.int64),
        "face_offsets": offsets,
        "boundary_mask": neigh == 0xFFFFFFFF,
    }


def fph_cvol_ids(data):
    """LS_CvolIdOfElements：每单元控制体 id（u32）。"""
    start, end = _section_span(data, "LS_CvolIdOfElements")
    if not end:
        return None
    arrs = [a for a in _u32_arrays(data, start, end) if a.size > 0]
    if not arrs:
        return None
    return max(arrs, key=lambda a: a.size)


def fph_names(data, section: str):
    """LS_Parts / LS_VolumeRegions 等命名节的全部名字。"""
    start, end = _section_span(data, section)
    if not end:
        return []
    return _strings(data, start, end)


def fph_parts(data):
    return fph_names(data, "LS_Parts")


def fph_materials(data) -> dict:
    """LS_MaterialOfParts：材料名 + 每零件→材料映射。

    节内布局 = 材料子表（名字 + 尾随描述符）+ 零件子表（名字 + 尾随
    [1, 材料 id] 描述符对）；本函数用 LS_Parts 的零件名把两个子表分开，
    再按尾随 id（1 基）映射回材料名。实测：minimumPolyhedral 的
    Part1→1→Fluid、Part2→2→Solid；scFLOW_tutorial 的 Domain→1→water。
    """
    names = fph_names(data, "LS_MaterialOfParts")
    part_names = set(fph_parts(data))
    if not names:
        return {"materials": [], "part_materials": {}, "ref_ids": {}}
    start, end = _section_span(data, "LS_MaterialOfParts")
    recs = _records(data, start, end)
    ref_ids = {}
    for i, rec in enumerate(recs):
        if rec[0] == "desc" and rec[1] == 1 and rec[2] > 0:
            L = rec[2]
            if (i + 1 < len(recs) and recs[i + 1][0] == "blk"
                    and recs[i + 1][2] == L):
                off = recs[i + 1][1]
                raw = bytes(data[off:off + L])
                if not all(b == 32 or 33 <= b < 127 for b in raw):
                    continue
                name = raw.decode("ascii").rstrip()
                # 尾随两个描述符 (1,1),(X,4) = 引用 id X
                if (i + 2 < len(recs) and recs[i + 2][0] == "desc"
                        and recs[i + 2][2:] == (1, 1)
                        and recs[i + 3][0] == "desc"
                        and recs[i + 3][3] == 4):
                    ref_ids[name] = recs[i + 3][2]
    materials = [n for n in names if n not in part_names]
    part_materials = {}
    for name in names:
        if name in part_names:
            idx = ref_ids.get(name, 0)
            mat = (materials[idx - 1] if 1 <= idx <= len(materials)
                   else "?")
            part_materials[name] = mat
    return {"materials": materials, "part_materials": part_materials,
            "ref_ids": ref_ids}


def fph_volume_regions(data):
    return fph_names(data, "LS_VolumeRegions")


def fph_surface_regions(data):
    """LS_SurfaceRegions：每个区域 = 名字 + 面 id 数组（1 基）+ 属性数组。

    每个区域条目 = desc(1,L,1)+名字，随后是若干等长 u32 数组（实测
    scFLOW_tutorial 为 [面 id][标志]，minimumPolyhedral 为
    [面 id][?][标志]）。返回 [{"name","face_ids","extra"}] 列表。
    """
    start, end = _section_span(data, "LS_SurfaceRegions")
    if not end:
        return []
    recs = _records(data, start, end)
    regions = []
    current = None
    for i, rec in enumerate(recs):
        if rec[0] == "desc" and rec[1] == 1 and rec[2] > 0:
            L = rec[2]
            if (i + 1 < len(recs) and recs[i + 1][0] == "blk"
                    and recs[i + 1][2] == L):
                off = recs[i + 1][1]
                raw = bytes(data[off:off + L])
                if all(b == 32 or 33 <= b < 127 for b in raw):
                    current = {"name": raw.decode("ascii").rstrip(),
                               "face_ids": None, "extra": []}
                    regions.append(current)
                    continue
        if rec[0] == "blk" and current is not None:
            off, bc = rec[1], rec[2]
            if bc >= 4 and bc % 4 == 0:
                arr = np.frombuffer(data, dtype=">u4", count=bc // 4,
                                    offset=off).astype(np.uint64)
                if current["face_ids"] is None:
                    current["face_ids"] = arr
                else:
                    current["extra"].append(arr)
    return regions


def fph_assemblies(data):
    """LS_Assemblies：装配 XML 文本。"""
    start, end = _section_span(data, "LS_Assemblies")
    if not end:
        return None
    texts = _strings(data, start, end)
    for text in texts:
        if text.startswith("<"):
            return text
    for off, bc in _blocks(data, start, end):
        raw = bytes(data[off:off + bc])
        if raw.startswith(b"<?xml"):
            return raw.decode("utf-8", errors="replace")
    return None


def fph_element_center(data):
    """Element_Center：单元中心坐标 (n,3) f32。"""
    start, end = _section_span(data, "Element_Center")
    if not end:
        return None
    blks = [(off, bc) for off, bc in _blocks(data, start, end)
            if bc >= 4 and bc % 4 == 0]
    sizes = [bc for _, bc in blks]
    if not sizes:
        return None
    target = max(set(sizes), key=sizes.count)
    trio = [(off, bc) for off, bc in blks if bc == target][:3]
    if len(trio) < 3 or target % 4:
        return None
    n = target // 4
    axes = [np.frombuffer(data, dtype=">f4", count=n, offset=off)
            for off, _ in trio]
    return np.column_stack(axes).astype(np.float64)


def fph_sphfile(data):
    """LS_SPHFile：SDAT 设置文本。"""
    start, end = _section_span(data, "LS_SPHFile")
    if not end:
        return None
    for off, bc in _blocks(data, start, end):
        raw = bytes(data[off:off + bc])
        if raw.startswith(b"SDAT"):
            return raw.decode("utf-8", errors="replace")
    return None


def _field_data_arrays(data, target: str):
    """数据节（pressure/velocity/YPLS…）内的等长数组。

    返回 [(类别, u32 数组)]，类别：values（f32 场值）/ ids / flags ——
    仅按位置与节类型推定（FC 场 = [ids, flags, values]；矢量 = 3×values）。
    """
    start, end = _section_span(data, target)
    if not end:
        return []
    arrs = _u32_arrays(data, start, end)
    if not arrs:
        return []
    n = max(a.size for a in arrs)
    arrs = [a for a in arrs if a.size == n]
    if target in ("YPLS", "SURT"):
        kinds = ["ids", "flags", "values"][:len(arrs)]
    else:
        kinds = ["values"] * len(arrs)
    return list(zip(kinds, arrs))


def fph_fields(data) -> dict:
    """EC_*/FC_* 场量：元数据节 → 目标数据节数组配对。

    返回 {节名: {"kind": "EC"|"FC", "target": str, "components": int,
    "arrays": [(类别, u32 数组)]}}。
    """
    sections = crdlfld.scan_sections(data)
    out = {}
    for s in sections:
        if not (s.name.startswith("EC_") or s.name.startswith("FC_")):
            continue
        kind = s.name[:3]
        # 元数据节节尾因目标名字符串被误判前移 40 字节，加 48 字节余量
        # 才能读到该字符串；余量内只有真实下一节头 + 描述符，无副作用。
        strings = _strings(data, s.records_start, s.end, slack=48)
        target = (strings[-1] if strings
                  else FIELD_TARGET_NAMES.get(s.name, ""))
        recs = _records(data, s.records_start, s.end, slack=48)
        components = 1
        if kind == "EC_":
            dims = [(r[2], r[3]) for r in recs
                    if r[0] == "desc" and r[1] == 4]
            if any(d == (0, 4) for d in dims):
                components = 3
        arrays = _field_data_arrays(data, target) if target else []
        out[s.name] = {
            "kind": kind,
            "target": target,
            "components": components,
            "arrays": arrays,
        }
    return out


def parse_fph(data) -> dict:
    """FPH 全量解析（网格 + 区域 + 场量）。"""
    links = fph_links(data)
    if links:
        cells = build_cells(links["owner"], links["neigh"], links["npe"])
    else:
        cells = {}
    cvol = fph_cvol_ids(data)
    return {
        "vertices": fph_vertices(data),
        "links": links,
        "cells": cells,
        "cvol_ids": cvol,
        "n_cvols": int(cvol.max()) if cvol is not None and cvol.size else 0,
        "parts": fph_parts(data),
        "materials": fph_materials(data),
        "volume_regions": fph_volume_regions(data),
        "surface_regions": fph_surface_regions(data),
        "assemblies": fph_assemblies(data),
        "element_center": fph_element_center(data),
        "sphfile": fph_sphfile(data),
        "fields": fph_fields(data),
    }


def as_f32(arr) -> np.ndarray:
    """把 u32 位模式数组按大端 f32 重解释（场值块用）。

    数组元素为文件大端 u32 的数值；先转回大端字节序再按 f32 重解释
    （小端主机上 astype(uint32) 会改变字节序，不能直接 view）。
    """
    return arr.astype(">u4").view(">f4").astype(np.float64)


def _fmt_array(a, limit: int = 3) -> str:
    if a is None or a.size == 0:
        return "-"
    head = ", ".join(str(int(v)) for v in a[:limit])
    tail = "" if a.size <= limit else ", ..."
    return f"n={a.size} [{head}{tail}]"


def summarize_fph(filepath) -> str:
    """FPH 摘要（网格统计 + 区域 + 场量表）。"""
    data, handles = crdlfld.open_buffer(filepath)
    try:
        m = parse_fph(data)
    finally:
        if handles is not None:
            mm, f = handles
            mm.close()
            f.close()
    lines = [f"FPH: {Path(filepath).name} ({len(data):,} bytes)"]
    v = m["vertices"]
    links = m["links"]
    cells = m["cells"]
    n_cells = cells.get("n_cells", 0) if cells else 0
    lines.append(f"节点: {v.shape[0]:,} (f32 xyz)" if v is not None
                 and v.size else "节点: -")
    lines.append(f"面: {links.get('n_faces', 0):,}  单元: {n_cells:,}"
                 if links else "面/单元: -")
    if links:
        lines.append(f"边界面: {int(links['boundary_mask'].sum()):,}  "
                     f"npe 范围 [{int(links['npe'].min())}.."
                     f"{int(links['npe'].max())}]")
    if cells and cells.get("type_histogram"):
        hist = ", ".join(f"{k}={v:,}" for k, v in
                         sorted(cells["type_histogram"].items()))
        lines.append(f"单元类型: {hist}")
    if m["cvol_ids"] is not None:
        lines.append(f"控制体: {m['n_cvols']} "
                     f"（每单元 id 数组 n={m['cvol_ids'].size}）")
    lines.append(f"零件: {', '.join(m['parts']) or '-'}")
    mats = m["materials"]
    part_mats = ", ".join(f"{k}={v}" for k, v in
                          mats["part_materials"].items()) or "-"
    lines.append(f"材料: {', '.join(mats['materials']) or '-'}"
                 f"  零件→材料: {part_mats}")
    lines.append(f"体区域: {', '.join(m['volume_regions']) or '-'}")
    if m["surface_regions"]:
        lines.append("面区域:")
        for r in m["surface_regions"]:
            extra = (f" +{len(r['extra'])} 属性数组" if r["extra"] else "")
            if r["face_ids"] is None or r["face_ids"].size == 0:
                lines.append(f"  {r['name']}: 0 面（空区域）")
            else:
                lines.append(f"  {r['name']}: {r['face_ids'].size:,} 面"
                             f"（id {_fmt_array(r['face_ids'])}）{extra}")
    if m["assemblies"]:
        lines.append(f"装配 XML: {m['assemblies'].splitlines()[0][:80]}")
    if m["element_center"] is not None:
        lines.append(f"单元中心坐标: ({m['element_center'].shape[0]:,}, 3) f32")
    if m["sphfile"]:
        first = m["sphfile"].splitlines()
        tail = first[1] if len(first) > 1 else ""
        lines.append(f"SDAT: {len(first)} 行（{tail}）")
    if m["fields"]:
        lines.append("场量:")
        for name, f in m["fields"].items():
            arrs = f["arrays"]
            desc = (f"{f['kind']} {f['components']} 分量"
                    f" → {f['target'] or '(无目标)'}")
            if arrs:
                kinds = [k for k, _ in arrs]
                lines.append(f"  {name}: {desc}  数组[{', '.join(kinds)}] "
                             f"n={arrs[0][1].size:,}")
            else:
                lines.append(f"  {name}: {desc}  （无数据节）")
    return "\n".join(lines)
