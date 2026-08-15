#!/usr/bin/env python3
"""scPOST 求解器 FLD 场文件轻量统计（基于官方 Samples_POST/FLD 样例逆向）。

FLD 与 GPH/OCT/MDL 共享 CRDL-FLD 大端容器（crdlfld），但存六面体连通、
每顶点场量与表面 BC，而非多面体 LS_Links 拓扑。本模块在 pphdecoding 仓内
独立实现 FLD 摘要（不依赖 flddecoding 仓），逻辑与 flddecoding/fld_model
（经 scPOST 验证）互相对拍。

官方 8 样例实测要点：

- 坐标/场量有 f32 / f64 两种方言：节内 (4, n, 4) 描述符 = n 个 f32
  （4 字节/值），(8, n, 1) = n 个 f64（8 字节/值）；minimumHexa 与
  scSTREAM_example1_* 用 f32，flddecoding 自建样例用 f64；
- LS_Nodes = X/Y/Z 三轴块；LS_Elements = I4[n×8] 六面体连通；
  LS_MatOfElements = I4[n] 材料 id（最小样例可为空节）；
- LS_VolumeGeometryArray = 256B 槽位体区域名；
- 区域/BC：LS_RegionName&Type + 以 BC 名为节的区域表
  （FLUX(velocity)/WALL(static)/THERM(adiabatic)/AMOM(noslip) 等）；
- 场量：LS_Scalar:<名> 标签节 + 场节（Pressure/Temperature/CN01 等）、
  LS_Vector:<名> + 向量场节（VECT/HVEC/VEL）；节尾 20B 哨兵
  [12][0][0][0][12] 与 GPH 一致。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

import crdlfld

# 场量节（值块按顶点数 n_vertices 存储）
SCALAR_SECTIONS = ("Pressure", "Temperature", "CN01", "POTENTIAL",
                   "Turbulence energy", "Turbulence dissipation rate",
                   "Eddy viscosity", "Yplus", "Heat transfer coefficient",
                   "Friction velocity", "Volume fraction")
VECTOR_SECTIONS = ("VECT", "HVEC", "VEL")
BC_PREFIXES = ("FLUX(", "WALL(", "THERM(", "AMOM(", "SYMM(", "PERI(")


@dataclass
class FldSection:
    name: str
    start: int
    end: int


def fld_section_table(data: bytes) -> list[FldSection]:
    """FLD 全节表（含场量/BC 节；crdlfld 40 字节节头扫描）。"""
    secs = crdlfld.scan_sections(data)
    out = []
    for i, s in enumerate(secs):
        end = secs[i + 1].start if i + 1 < len(secs) else len(data)
        out.append(FldSection(s.name, s.start, end))
    return out


def _find(table: list[FldSection], name: str) -> Optional[FldSection]:
    for s in table:
        if s.name == name:
            return s
    return None


def _elem_bytes(data: bytes, sec: FldSection) -> Optional[int]:
    """从描述符投票坐标/场量元素尺寸：4 = f32，8 = f64。"""
    counts = {4: 0, 8: 0}
    for d in crdlfld.iter_descriptors(
            data, crdlfld.Section("", sec.start, sec.end)):
        if d.dim0 > 1 and 0 < d.dim1 < 10_000_000:
            counts[d.type_code] += 1
    if counts[8] > counts[4]:
        return 8
    if counts[4] > counts[8]:
        return 4
    return None


def _axis_trio(data: bytes, sec: FldSection, elem: int):
    """节内最常见的三个等长坐标块（X/Y/Z）→ (n,3)。"""
    blocks = [(b.offset, b.byte_count)
              for b in crdlfld.iter_data_blocks(
                  data, crdlfld.Section("", sec.start, sec.end))
              if b.byte_count >= elem and b.byte_count % elem == 0]
    if len(blocks) < 3:
        return None
    sizes = [bc for _, bc in blocks]
    target = max(set(sizes), key=sizes.count)
    trio = [(p, bc) for p, bc in blocks if bc == target][:3]
    if len(trio) < 3:
        return None
    n = target // elem
    dtype = ">f8" if elem == 8 else ">f4"
    axes = [np.frombuffer(data, dtype=dtype, count=n, offset=p)
            for p, _ in trio]
    return np.column_stack(axes).astype(np.float64)


def fld_vertices(data: bytes, table=None) -> Optional[np.ndarray]:
    """LS_Nodes → 顶点坐标 (n_vertices, 3)。f32/f64 方言自适应。"""
    table = table if table is not None else fld_section_table(data)
    sec = _find(table, "LS_Nodes")
    if sec is None:
        return None
    elem = _elem_bytes(data, sec)
    if elem is None:
        return None
    return _axis_trio(data, sec, elem)


# 单元类型码 = 30 + 每单元节点数（实测严格验证：34=tet(4)、35=pyramid(5)、
# 36=prism(6)、38=hexa(8)；2cars/SCTeta/Klein 混合网格 conn 总长 =
# Σ(type-30) 逐项吻合，scSTREAM_example1_100 全 38 型 conn = n×8 吻合）
ELEM_TYPE_NODES = {34: 4, 35: 5, 36: 6, 37: 7, 38: 8}
ELEM_TYPE_NAMES = {34: "tetrahedron", 35: "pyramid", 36: "prism",
                   37: "7-node", 38: "hexahedron"}


def fld_cells(data: bytes, table=None):
    """LS_Elements + LS_MatOfElements → (types (n,), mat (n,), conn (flat I4))。

    LS_Elements 首个块 = 每单元类型码（34..37 = 节点数），随后为扁平连通
    （node id 流，按类型逐单元分组）。全 hexa 时 conn 长度为 n×8；
    混合网格（2cars/SCTeta/Klein）conn 长度 = Σ(type-30)（实测严格吻合）。
    """
    table = table if table is not None else fld_section_table(data)
    sec_mat = _find(table, "LS_MatOfElements")
    sec_elem = _find(table, "LS_Elements")
    if sec_mat is None or sec_elem is None:
        return None, None, None
    mat_blocks = [b for b in crdlfld.iter_data_blocks(
        data, crdlfld.Section("", sec_mat.start, sec_mat.end))
        if b.byte_count >= 4 and b.byte_count % 4 == 0]
    elem_blocks = [b for b in crdlfld.iter_data_blocks(
        data, crdlfld.Section("", sec_elem.start, sec_elem.end))
        if b.byte_count >= 4 and b.byte_count % 4 == 0]
    if not mat_blocks or not elem_blocks:
        return None, None, None
    mat = np.frombuffer(data, dtype=">i4", count=mat_blocks[0].byte_count // 4,
                        offset=mat_blocks[0].offset).astype(np.int64)
    n_cells = int(mat.size)
    types = np.frombuffer(data, dtype=">i4", count=elem_blocks[0].byte_count // 4,
                          offset=elem_blocks[0].offset).astype(np.int64)
    if types.size != n_cells:
        return None, mat, None
    # 连通流：类型块之后的 I4 块拼接（大网格可能拆成多块/裸尾，如 2cars）
    rest = elem_blocks[1:]
    if not rest:
        return types, mat, None
    expect = int(np.sum([ELEM_TYPE_NODES.get(t, 0) for t in types.tolist()]))
    parts = [np.frombuffer(data, dtype=">i4",
                           count=b.byte_count // 4, offset=b.offset)
             for b in rest]
    # 裸尾：最后一块之后、节尾之前的 I4 对齐数据（无块头包裹）
    last_end = rest[-1].offset + rest[-1].byte_count + 8
    tail_bytes = sec_elem.end - last_end
    if tail_bytes >= 4 and tail_bytes % 4 == 0:
        parts.append(np.frombuffer(data, dtype=">i4",
                                   count=tail_bytes // 4, offset=last_end))
    conn = np.concatenate(parts).astype(np.int64) if parts else None
    if conn is not None and expect and conn.size >= expect:
        conn = conn[:expect]
    return types, mat, conn


def fld_volume_names(data: bytes, table=None) -> list[str]:
    """LS_VolumeGeometryArray → 体区域名（256B 槽位）。"""
    table = table if table is not None else fld_section_table(data)
    sec = _find(table, "LS_VolumeGeometryArray")
    if sec is None:
        return []
    for b in crdlfld.iter_data_blocks(
            data, crdlfld.Section("", sec.start, sec.end)):
        raw = bytes(data[b.offset:b.offset + b.byte_count])
        if b.byte_count >= 256 and all(x == 0 or 32 <= x < 127 for x in raw):
            names = []
            for off in range(0, b.byte_count, 256):
                chunk = raw[off:off + 256]
                text = chunk.split(b"\x00")[0].decode(
                    "ascii", errors="replace").strip()
                if text:
                    names.append(text)
            if names:
                return names
    return []


def fld_region_names(data: bytes, table=None) -> list[str]:
    """区域/BC 名：BC 名节（FLUX(…)/WALL(…)/THERM(…)/AMOM(…) 等）。"""
    table = table if table is not None else fld_section_table(data)
    return [s.name for s in table if s.name.startswith(BC_PREFIXES)]


def fld_field_sections(data: bytes, table=None
                       ) -> list[tuple[str, str, list[int]]]:
    """场量节 → [(name, dtype, [每块值数...])]。"""
    table = table if table is not None else fld_section_table(data)
    out = []
    for s in table:
        nm = s.name
        if not (nm in SCALAR_SECTIONS or nm in VECTOR_SECTIONS):
            continue
        elem = _elem_bytes(data, s) or 8
        counts = [b.byte_count // elem
                  for b in crdlfld.iter_data_blocks(
                      data, crdlfld.Section("", s.start, s.end))
                  if b.byte_count >= elem and b.byte_count % elem == 0]
        out.append((nm, "f64" if elem == 8 else "f32", counts))
    return out


def summarize_fld(data: bytes) -> dict:
    """FLD 轻量摘要（节表 + 网格计数 + 材料 + 体区域 + BC + 场量）。"""
    from collections import Counter
    table = fld_section_table(data)
    verts = fld_vertices(data, table)
    types, mat, conn = fld_cells(data, table)
    fields = fld_field_sections(data, table)
    type_hist = None
    if types is not None:
        type_hist = {
            f"{ELEM_TYPE_NAMES.get(int(k), k)}({ELEM_TYPE_NODES.get(int(k), '?')})":
            int(v)
            for k, v in sorted(Counter(types.tolist()).items())}
    return {
        "sections": [s.name for s in table],
        "n_sections": len(table),
        "n_vertices": None if verts is None else int(verts.shape[0]),
        "n_cells": None if mat is None else int(mat.size),
        "material_bincount": None if mat is None
        else {int(k): int(v) for k, v in sorted(Counter(mat.tolist()).items())},
        "element_type_histogram": type_hist,
        "n_conn_entries": None if conn is None else int(conn.size),
        "volume_names": fld_volume_names(data, table),
        "region_names": fld_region_names(data, table),
        "field_sections": [(n, dt, sz) for n, dt, sz in fields],
    }


def summarize_fld_file(path: str | Path) -> dict:
    with crdlfld.CrdlFldFile.load(str(path)) as f:
        return summarize_fld(f.data)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="FLD 场文件轻量统计")
    ap.add_argument("path")
    ap.add_argument("--sections", action="store_true", help="仅打印节表")
    args = ap.parse_args()
    s = summarize_fld_file(args.path)
    print(f"n_sections={s['n_sections']} n_vertices={s['n_vertices']} "
          f"n_cells={s['n_cells']}")
    if args.sections:
        for nm in s["sections"]:
            print("  ", nm)
    else:
        if s["material_bincount"]:
            print("materials:", s["material_bincount"])
        if s["volume_names"]:
            print("volumes:", s["volume_names"])
        if s["region_names"]:
            print("regions:", s["region_names"])
        if s["field_sections"]:
            print("fields:", s["field_sections"])
