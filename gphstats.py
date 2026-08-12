#!/usr/bin/env python3
"""仓库内轻量 GPH 统计（``gphdecoding`` 仓不可用时的降级路径）。

`gphdecoding` 是同级仓库，提供完整的 `gph_model`（LS_* 节解析、深度统计）。
本模块只实现 CLI 摘要所需的最小统计集合，且只依赖本仓库的 `crdlfld`
（节扫描 / 数据块迭代），保证 pphdecoding 可以独立运行：

- LS_Links：面数、单元数、边界面数、npe 范围、多面体标记；
- LS_CvolIdOfElements：单元数 + 唯一 cvol 列表；
- LS_Nodes：顶点数 + 坐标方言（BE f64 / word-reversed f64 / BE f32）；
- LS_SurfaceRegions：面区域名 + 面数；
- LS_VolumeRegions / 其他字符串节：字符串列表；
- LS_Parts：部件名 + cvol 规格（简单单值或复合 frozenset）。

统计口径与 `gph_model.py` 保持一致（均为"最常见 I4 块尺寸 → 面数"等启发式），
已在 box 样例上对拍：n_faces=3168 / n_cells=944 / boundary=600 / npe 4..6 /
顶点 1305 / open=600 全部一致。
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import numpy as np

import crdlfld


# 同一 buffer 上反复 _find_section 时复用节表（laptop GPH 上 scan≈2s）
_sections_cache: dict[int, list] = {}


@contextmanager
def open_buffer(path: str):
    """读取 GPH 文件（大文件用 mmap），用法同 gph_model.open_gph_buffer。"""
    from pathlib import Path
    import mmap

    size = Path(path).stat().st_size
    # >32 MiB 用 mmap，避免把数百 MB 再拷进进程堆（打开工程时会卡死）
    if size <= 32 * 1024 * 1024:
        with open(path, "rb") as f:
            data = f.read()
        try:
            yield data
        finally:
            _sections_cache.pop(id(data), None)
        return

    f = open(path, "rb")
    try:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            yield mm
        finally:
            _sections_cache.pop(id(mm), None)
            mm.close()
    finally:
        f.close()


def _all_sections(data) -> list:
    key = id(data)
    secs = _sections_cache.get(key)
    if secs is None:
        secs = crdlfld.scan_sections(data)
        _sections_cache[key] = secs
    return secs


def _find_section(data, name: str) -> Optional[crdlfld.Section]:
    """按名定位节，返回 ``Section``（节尾 = 下一节头或文件尾）。"""
    sec_start = crdlfld.find_section(data, name)
    if sec_start < 0:
        return None
    sections = _all_sections(data)
    for i, s in enumerate(sections):
        if s.start == sec_start:
            end = sections[i + 1].start if i + 1 < len(sections) else len(data)
            return crdlfld.Section(name, sec_start, end)
    return crdlfld.Section(name, sec_start, len(data))


def links_summary(data) -> Optional[dict]:
    """LS_Links 拓扑摘要：n_faces / n_cells / boundary / npe / polyhedral。"""
    section = _find_section(data, "LS_Links")
    if section is None:
        return None
    blocks = [(b.offset, b.byte_count)
              for b in crdlfld.iter_data_blocks(data, section) if b.byte_count > 0]
    if not blocks:
        return None
    sizes = [bc for _, bc in blocks]
    n_faces_block_size = None
    for size, count in Counter(sizes).most_common():
        if count >= 3 and size % 4 == 0 and size >= 4:
            n_faces_block_size = size
            break
    if n_faces_block_size is None:
        return None
    n_faces = n_faces_block_size // 4
    triples = [b for b in blocks if b[1] == n_faces_block_size][:3]
    if len(triples) < 3:
        return None
    owner_p, _ = triples[0]
    neigh_p, _ = triples[1]
    npe_p, _ = triples[2]
    npe = np.frombuffer(data, dtype=">u4", count=n_faces, offset=npe_p)
    neigh = np.frombuffer(data, dtype=">u4", count=n_faces, offset=neigh_p)
    owner = np.frombuffer(data, dtype=">u4", count=n_faces, offset=owner_p)
    return {
        "n_faces": int(n_faces),
        "n_cells": int(owner.max()) + 1,
        "boundary_faces": int((neigh == 0xFFFFFFFF).sum()),
        "npe_min": int(npe.min()),
        "npe_max": int(npe.max()),
        "conn_entries": int(npe.sum()),
        "polyhedral": bool(npe.max() > 3),
    }


def cvol_ids(data) -> Optional[np.ndarray]:
    """LS_CvolIdOfElements → I4[n_cells]（节内最大 I4 块）。"""
    section = _find_section(data, "LS_CvolIdOfElements")
    if section is None:
        return None
    best: Optional[tuple[int, int]] = None
    for b in crdlfld.iter_data_blocks(data, section):
        p, bc = b.offset, b.byte_count
        if bc % 4 == 0 and bc >= 4:
            if best is None or bc > best[1]:
                best = (p, bc)
    if best is None:
        return None
    p, bc = best
    return np.frombuffer(data, dtype=">i4", count=bc // 4, offset=p).astype(
        np.int64).copy()


def _ls_nodes_elem_bytes(data, sec_start: int, sec_end: int) -> Optional[int]:
    """从 LS_Nodes 类型描述符投票得到坐标元素尺寸（4=f32，8=f64）。"""
    counts = {4: 0, 8: 0}
    pos = sec_start + 40
    n = len(data)
    while pos + 16 <= sec_end and pos + 16 <= n:
        if crdlfld.read_i32_be(data, pos) == 12:
            tc = crdlfld.read_i32_be(data, pos + 4)
            if tc in (4, 8):
                dim0 = crdlfld.read_i32_be(data, pos + 8)
                dim1 = crdlfld.read_i32_be(data, pos + 12)
                if dim0 > 1 and 0 < dim1 < 10_000_000:
                    counts[tc] += 1
        pos += 4
    if counts[8] > counts[4]:
        return 8
    if counts[4] > counts[8]:
        return 4
    return None


def nodes_vertex_count(data) -> tuple[Optional[int], str]:
    """LS_Nodes → (n_vertices, dialect)。轻量实现：最常见的等长三块 → 顶点数。"""
    section = _find_section(data, "LS_Nodes")
    if section is None:
        return None, ""
    blocks = [(b.offset, b.byte_count)
              for b in crdlfld.iter_data_blocks(data, section)
              if b.byte_count >= 4 and b.byte_count % 4 == 0]
    if len(blocks) < 3:
        return None, ""
    sizes = [bc for _, bc in blocks]
    target = max(set(sizes), key=sizes.count)
    trio = [(p, bc) for p, bc in blocks if bc == target][:3]
    if len(trio) < 3:
        return None, ""
    elem = _ls_nodes_elem_bytes(data, section.start, section.end)
    if elem == 8 and target % 8 == 0:
        return target // 8, "standard BE float64"
    if elem == 4 and target % 4 == 0:
        return target // 4, "BE float32"
    if target % 8 == 0:
        return target // 8, "BE float64 (or word-reversed)"
    if target % 4 == 0:
        return target // 4, "BE float32"
    return None, ""


def _iter_surface_region_blocks(data):
    """LS_SurfaceRegions → 迭代 ``(name, face_ids_i32_be_offset, n_faces)``。"""
    section = _find_section(data, "LS_SurfaceRegions")
    if section is None:
        return
    blocks = [(b.offset, b.byte_count)
              for b in crdlfld.iter_data_blocks(data, section)]
    i = 0
    while i + 2 < len(blocks):
        p_n, bc_n = blocks[i]
        p_i, bc_i = blocks[i + 1]
        p_w, bc_w = blocks[i + 2]
        name_raw = bytes(data[p_n:p_n + bc_n])
        if not all(b == 0 or 32 <= b < 127 for b in name_raw):
            i += 1
            continue
        name = name_raw.decode("ascii", errors="replace").strip("\x00").rstrip()
        if not name:
            i += 1
            continue
        if bc_i > 0 and bc_i == bc_w and bc_i % 4 == 0:
            yield name, p_i, bc_i // 4
            i += 3
        else:
            i += 1


def surface_regions_summary(data) -> list[tuple[str, int]]:
    """LS_SurfaceRegions → [(name, n_faces)]。"""
    return [(name, n) for name, _off, n in _iter_surface_region_blocks(data)]


def surface_region_face_ids(data) -> dict[str, np.ndarray]:
    """LS_SurfaceRegions → ``{name: face_index_i32}``（0-based 面号）。"""
    out: dict[str, np.ndarray] = {}
    for name, off, n in _iter_surface_region_blocks(data):
        out[name] = np.frombuffer(
            data, dtype=">i4", count=n, offset=off).astype(np.int64, copy=True)
    return out


def string_list(data, section_name: str) -> list[str]:
    """任意节（如 LS_VolumeRegions）中的 ASCII 字符串列表。"""
    section = _find_section(data, section_name)
    if section is None:
        return []
    out: list[str] = []
    for b in crdlfld.iter_data_blocks(data, section):
        p, bc = b.offset, b.byte_count
        raw = bytes(data[p:p + bc])
        if all(b == 0 or 32 <= b < 127 for b in raw):
            s = raw.decode("ascii", errors="replace").strip("\x00").rstrip()
            if s:
                out.append(s)
    return out


def _ls_parts_name_blocks(data, sec_start: int, sec_end: int):
    """LS_Parts 内 ASCII 名称块（启发式同 gph_model）。"""
    name_blocks: list[tuple[str, int, int]] = []
    for b in crdlfld.iter_data_blocks(data, crdlfld.Section("", sec_start, sec_end)):
        p, bc = b.offset, b.byte_count
        if bc <= 0 or bc > 512:
            continue
        raw = bytes(data[p:p + bc])
        if not all(b == 0 or 32 <= b < 127 for b in raw):
            continue
        name = raw.decode("ascii", errors="replace").strip("\x00").rstrip()
        if not name or not any(c.isalpha() for c in name):
            continue
        name_blocks.append((name, p, bc))
    return name_blocks


def _scan_cvol_descriptor_chain(data, start: int, end: int) -> list[int]:
    """收集 ``[12,4,X,4]`` 描述符链（简单部件 ``[1,cvol_id]`` / 复合 ``[12,4,N,4]``）。"""
    chain: list[int] = []
    pos = start
    while pos + 16 <= end:
        if (crdlfld.read_i32_be(data, pos) == 12
                and crdlfld.read_i32_be(data, pos + 4) == 4
                and crdlfld.read_i32_be(data, pos + 12) == 4):
            chain.append(crdlfld.read_i32_be(data, pos + 8))
        pos += 4
    return chain


def format_part_cvol_spec(spec) -> str:
    if isinstance(spec, frozenset):
        ids = sorted(spec)
        if len(ids) <= 10:
            return "{" + ", ".join(str(i) for i in ids) + "}"
        return f"{{{ids[0]}..{ids[-1]} ... n={len(ids)}}}"
    return str(spec)


def parts_summary(data, cvol: Optional[np.ndarray] = None) -> list[tuple[str, object]]:
    """LS_Parts → [(name, cvol 规格)]，规格为 int 或 frozenset[int]。"""
    section = _find_section(data, "LS_Parts")
    if section is None:
        return []
    names = _ls_parts_name_blocks(data, section.start, section.end)
    actual_set: Optional[set[int]] = None
    if cvol is not None and len(cvol) > 0:
        actual_set = {int(x) for x in np.unique(cvol)}
    out: list[tuple[str, object]] = []
    for i, (name, p, bc) in enumerate(names):
        scan_end = names[i + 1][1] if i + 1 < len(names) else section.end
        after = p + bc + 4  # 名称块 + 尾随 I4
        chain = _scan_cvol_descriptor_chain(data, after, scan_end)
        if chain and chain[0] == 1:
            out.append((name, int(chain[-1])))
            continue
        # 复合部件：[12,4,N,4] + I4[N] 的 cvol 列表
        spec: Optional[frozenset[int]] = None
        if chain:
            chain_counts = set(chain)
            for b in crdlfld.iter_data_blocks(
                    data, crdlfld.Section("", after, scan_end)):
                bp, bbc = b.offset, b.byte_count
                if bbc < 8 or bbc % 4 != 0:
                    continue
                n = bbc // 4
                if n not in chain_counts:
                    continue
                vals = [int(x) for x in np.frombuffer(
                    data, dtype=">i4", count=n, offset=bp)]
                if len(vals) != n or len(set(vals)) != n:
                    continue
                if actual_set is not None and not all(v in actual_set for v in vals):
                    continue
                if n >= 2:
                    spec = frozenset(vals)
                    break
        out.append((name, spec if spec is not None else 1))
    return out


def summarize(data) -> dict:
    """汇总全部轻量统计（供 CLI 使用）。"""
    links = links_summary(data)
    cvol = cvol_ids(data)
    n_vertices, dialect = nodes_vertex_count(data)
    return {
        "links": links,
        "cvol_unique": None if cvol is None else np.unique(cvol).tolist(),
        "n_cells": None if cvol is None else int(cvol.size),
        "n_vertices": n_vertices,
        "dialect": dialect,
        "surface_regions": surface_regions_summary(data),
        "volume_regions": string_list(data, "LS_VolumeRegions"),
        "parts": parts_summary(data, cvol),
    }


def summarize_quick(data) -> dict:
    """打开工程用的快速摘要：跳过耗时的节点扫描 / 全量 cvol unique。

    laptop 级 GPH 上 ``nodes_vertex_count`` 可达十余秒；Part Tree 只需
    面/单元数与零件名。
    """
    links = links_summary(data)
    return {
        "links": links,
        "cvol_unique": None,
        "n_cells": links.get("n_cells"),
        "n_vertices": 0,
        "dialect": "",
        "surface_regions": surface_regions_summary(data),
        "volume_regions": string_list(data, "LS_VolumeRegions"),
        "parts": parts_summary(data, None),
    }


def summarize_file(path: str) -> dict:
    with open_buffer(path) as data:
        return summarize(data)


def parse_mesh(data) -> dict:
    """轻量网格提取：顶点坐标 + 面拓扑（供 3D 渲染）。

    返回：``vertices (n,3) f64``、``owner/neigh/npe``（I4/u4 数组，
    ``neigh == 0xFFFFFFFF`` = 边界面）、``conn``（CSR 连接表）与
    ``face_offsets``。大网格由调用方按面数上限抽样，本函数不切片。
    """
    # ── LS_Links：owner / neigh / npe 三个等长 I4 块 + 连接表 ───────
    section = _find_section(data, "LS_Links")
    if section is None:
        return {}
    blocks = [(b.offset, b.byte_count)
              for b in crdlfld.iter_data_blocks(data, section)
              if b.byte_count > 0 and b.byte_count % 4 == 0]
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
    owner = np.frombuffer(data, dtype=">i4", count=n_faces, offset=owner_p).astype(
        np.int64)
    neigh = np.frombuffer(data, dtype=">u4", count=n_faces, offset=neigh_p).astype(
        np.int64)
    npe = np.frombuffer(data, dtype=">u4", count=n_faces, offset=npe_p).astype(
        np.int64)
    conn_total = int(npe.sum())
    conn_parts = [b for b in blocks
                  if b[1] == conn_total * 4 and b[1] > 0]
    if not conn_parts:
        return {}
    conn = np.concatenate([
        np.frombuffer(data, dtype=">u4", count=conn_total, offset=p)
        for p, bc in conn_parts
        if bc == conn_total * 4])
    if conn.size != conn_total:
        return {}
    offsets = np.empty(n_faces + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(npe, out=offsets[1:])

    # ── LS_Nodes：三个等长 R8 轴块 ──────────────────────────────────
    nsec = _find_section(data, "LS_Nodes")
    vertices = np.empty((0, 3), dtype=np.float64)
    if nsec is not None:
        fblocks = [(b.offset, b.byte_count)
                   for b in crdlfld.iter_data_blocks(data, nsec)
                   if b.byte_count >= 8 and b.byte_count % 8 == 0]
        if len(fblocks) >= 3:
            sizes = [bc for _, bc in fblocks]
            target = max(set(sizes), key=sizes.count)
            trio = [b for b in fblocks if b[1] == target][:3]
            if len(trio) == 3:
                n = target // 8
                axes = [np.frombuffer(data, dtype=">f8", count=n, offset=p)
                        for p, _ in trio]
                vertices = np.column_stack(axes)
    return {
        "n_faces": n_faces,
        "vertices": vertices,
        "owner": owner,
        "neigh": neigh,
        "npe": npe,
        "conn": conn.astype(np.int64),
        "face_offsets": offsets,
        "boundary_mask": neigh == 0xFFFFFFFF,
    }


def _i32(value: int) -> bytes:
    import struct
    return struct.pack(">i", int(value))


def _descriptor(type_code: int, dim0: int, dim1: int) -> bytes:
    return _i32(12) + _i32(type_code) + _i32(dim0) + _i32(dim1)


def _block(payload: bytes) -> bytes:
    return _i32(12) + _i32(len(payload)) + payload + _i32(len(payload))


def _section(name: str, body: bytes) -> bytes:
    return _i32(32) + name.ljust(32).encode("ascii") + body


def write_gph(filepath,
              vertices,
              faces,
              app: str = "SCTpre",
              date: int = 20260812) -> "Path":
    """写最小 CRDL-FLD GPH（单 owner=0 的边界面集合，可被读回）。"""
    import numpy as _np

    n_faces = len(faces)
    owner = _np.zeros(n_faces, dtype=">i4")
    neigh = _np.full(n_faces, 0xFFFFFFFF, dtype=">u4")
    return write_gph_volume(filepath, vertices, faces, owner, neigh,
                            app=app, date=date)


def write_gph_volume(filepath,
                     vertices,
                     faces,
                     owner,
                     neigh,
                     app: str = "SCTpre",
                     date: int = 20260812) -> "Path":
    """写完整 CRDL-FLD GPH 体网格（``LS_Links`` 含 owner/neigh）。

    ``vertices``：(n,3) 浮点坐标；``faces``：多边形顶点索引列表（0-based），
    ``owner``/``neigh``：与 ``faces`` 等长的单元索引；``neigh == -1`` 表示
    边界面（写盘时转存为 0xFFFFFFFF）。
    """
    import numpy as _np

    verts = _np.asarray(vertices, dtype=float).reshape(-1, 3)
    n_vertices = len(verts)
    n_faces = len(faces)
    conn_flat = [int(v) for face in faces for v in face]
    conn_total = len(conn_flat)
    owner = _np.asarray(owner, dtype=">i4").reshape(-1)
    neigh_u4 = _np.asarray(neigh, dtype=">i4").reshape(-1)
    if owner.size != n_faces or neigh_u4.size != n_faces:
        raise ValueError("owner/neigh length must equal faces length")
    neigh_u4 = _np.where(neigh_u4 < 0, 0xFFFFFFFF, neigh_u4).astype(">u4")

    out = bytearray()
    out += _i32(8) + crdlfld.MAGIC + _i32(8) + _i32(4) + _i32(4)
    out += _section("FileRevision",
                    _descriptor(4, 1, 1) + _descriptor(4, 2025, 4))
    out += _section("Application",
                    _block(app.encode("ascii")[:8].ljust(8)))
    out += _section("Dimension",
                    _descriptor(4, 1, 1) + _descriptor(4, 3, 4))
    out += _section("Date",
                    _descriptor(4, 1, 1) + _descriptor(4, date, 4))
    out += _section("HeaderDataEnd", b"")
    out += _section("OverlapStart_0", b"")

    npe = _np.array([len(f) for f in faces], dtype=">u4")
    conn = _np.asarray(conn_flat, dtype=">u4")
    links = (
        _descriptor(4, 1, 1) + _descriptor(4, 1, 4) +
        _descriptor(4, 1, 1) + _descriptor(4, n_faces, 4) +
        _descriptor(4, n_faces, 1) +
        _block(owner.tobytes()) + _block(neigh_u4.tobytes()) +
        _block(npe.tobytes()) +
        _descriptor(4, 1, 1) + _descriptor(4, conn_total, 4) +
        _descriptor(4, conn_total, 1) + _block(conn.tobytes()))
    out += _section("LS_Links", links)

    nodes = (
        _descriptor(4, 1, 1) + _descriptor(4, 1, 4) +
        _descriptor(4, 1, 1) + _descriptor(4, n_vertices, 4) +
        _descriptor(8, n_vertices, 1) +
        _block(verts[:, 0].astype(">f8").tobytes()) +
        _block(verts[:, 1].astype(">f8").tobytes()) +
        _block(verts[:, 2].astype(">f8").tobytes()))
    out += _section("LS_Nodes", nodes)
    out += _section("OverlapEnd", b"")

    path = Path(filepath)
    path.write_bytes(bytes(out))
    return path
