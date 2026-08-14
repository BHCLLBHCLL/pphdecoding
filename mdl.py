#!/usr/bin/env python3
"""MDL 几何文件解析（scFLOW 面片几何 / ``*_part.mdl``、``*_ridge.mdl``）。

节布局（CRDL-FLD 容器，详见 crdlfld.py）：

* ``LS_Nodes`` — 顶点坐标：3 个等长 R8 数据块，按 X/Y/Z 轴块存储。
* ``LS_Faces`` — 多边形面片：``face_type I4[n_faces]`` + ``conn I4[sum(npe)]``
  （CSR 布局，0-based 顶点索引）。``face_type`` 为单元类型码：
  **133 = 三角形（3 顶点），134 = 四边形（4 顶点）**，即 ``npe = type - 130``
  （验证：``sum(npe) == len(conn)`` 在 part/ridge 两个样例上均精确成立）。
* ``LS_CsidOfFaces`` — 两个 ``I4[n_faces]`` 块：面两侧的闭曲面/体 id
  （观测值：block1 全 0 = 外部，block2 ∈ 1..n_closed_volumes）。
* ``LS_FridOfFaces`` — 两个相同的 ``I4[n_faces]`` 块：面区域 id（frid），
  与 ``LS_MdlSurfaceRegions`` 中的区域记录对应。
* ``LS_EdgeStateOfFaces`` — ``U1[sum(npe)]`` 每半边状态（1 = 特征/ridge 边）。
* ``LS_StateOfNodes`` — ``I4[n_nodes]`` 顶点状态（1 = 特征点）。
* ``LS_MdlClosedVolumes`` — 闭体列表（255B 名称块 + 描述符链，
  末值 = 体索引 0..N-1）。
* ``LS_MdlVolumeRegions`` — 体区域名（如 FluidRegion）+ 内部种子点 R8[3]。
* ``LS_MdlSurfaceRegions`` — 面区域名 + frid 索引。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from crdlfld import (CrdlFldFile, DataBlock, Descriptor, MAGIC, iter_data_blocks,
                     iter_descriptors, iter_records)


@dataclass
class MdlSurfaceRegion:
    """面区域记录：名称 + 描述符链数值 + 可选附加数组。

    ``index`` 取名称块之后最后一个 ``[*,4]`` 描述符的 dim0，在
    ``*_part.mdl`` 中与 ``LS_FridOfFaces`` 的面区域 id 对应
    （观测：open/air_domain=0, case1=1, rotation1=2, impeller1=3）；
    ``*_ridge.mdl`` 中区域记录结构不同（可能附带 I4 列表），
    此时 ``descriptors`` / ``arrays`` 保留原始数据。
    """

    name: str
    index: int
    descriptors: list[int]
    arrays: list[np.ndarray]


@dataclass
class MdlModel:
    """解析后的 MDL 面片几何。"""

    n_vertices: int
    n_faces: int
    xyz: np.ndarray            # (n_vertices, 3) float64
    face_type: np.ndarray      # (n_faces,) 单元类型码（133=三角, 134=四边）
    conn: np.ndarray           # (sum(npe),) 0-based 顶点索引（CSR）
    csid: tuple[np.ndarray, np.ndarray]   # 面两侧闭体 id
    frid: np.ndarray                       # 面区域 id
    edge_state: np.ndarray                 # (sum(npe),) uint8 半边状态
    node_state: np.ndarray                 # (n_vertices,) 顶点状态
    closed_volumes: list[str]              # 闭体名（可能为空名）
    volume_regions: list[str]
    surface_regions: list[MdlSurfaceRegion]

    @property
    def npe(self) -> np.ndarray:
        """每面顶点数（由类型码推导：133→3, 134→4）。"""
        if self.face_type.size == 0:
            return np.empty(0, dtype=np.int64)
        return self.face_type - 130

    @property
    def face_offsets(self) -> np.ndarray:
        off = np.empty(self.n_faces + 1, dtype=np.int64)
        off[0] = 0
        np.cumsum(self.npe, out=off[1:])
        return off

    def face_nodes(self, face_id: int) -> np.ndarray:
        off = self.face_offsets
        return self.conn[off[face_id] : off[face_id + 1]]

    @property
    def csid_sides(self) -> tuple[np.ndarray, np.ndarray]:
        """面两侧闭体 id ``(volA, volB)``（0 = 外部/空，1..N = 闭体索引）。

        语义（已用 box / laptop 钉死）：

        - 边界面一侧为 0（另一侧 = 所属闭体，``b2 = frid + 1``）；
        - 体间界面两侧均非零（laptop ridge 中 ``(2,1)`` 有 412,644 面，
          即 body2/body1 的界面）；
        - ``LS_MdlClosedVolumes`` 记录数 = ``max(b1,b2) + 1``（含索引 0 的
          "外部"记录）。
        """
        return self.csid

    @property
    def n_closed_volumes(self) -> int:
        """闭体数 = 两侧闭体 id 的最大值（0 为外部，不计入）。"""
        b1, b2 = self.csid
        if b1.size == 0 and b2.size == 0:
            return 0
        top = 0
        if b1.size:
            top = max(top, int(b1.max()))
        if b2.size:
            top = max(top, int(b2.max()))
        return top


def _largest_i4_block_indices(blocks: list[DataBlock], count: int) -> list[int]:
    sized = sorted(range(len(blocks)), key=lambda i: -blocks[i].byte_count)
    return sorted(sized[:count])


def parse_mdl(filepath: str, load_arrays: bool = True) -> MdlModel:
    """解析 MDL 文件，返回 :class:`MdlModel`。

    ``load_arrays=False`` 时仅解析计数与区域表（大文件快速预览），
    坐标 / 连接数组保持为空。
    """
    with CrdlFldFile.load(filepath) as f:
        data = f.data

        # ── LS_Nodes：3 个等长 R8 块（X/Y/Z 轴块）────────────────────
        sec = f.get_section("LS_Nodes")
        n_vertices = 0
        xyz = np.empty((0, 3))
        if sec:
            desc_max = max((d.dim0 for d in iter_descriptors(data, sec)
                            if d.dim0 > 1), default=0)
            blocks = list(iter_data_blocks(data, sec))
            f_blocks = [b for b in blocks if b.byte_count % 8 == 0 and b.byte_count >= 8]
            if len(f_blocks) >= 3:
                sizes = [b.byte_count for b in f_blocks]
                target = max(set(sizes), key=sizes.count)
                trio = [b for b in f_blocks if b.byte_count == target][:3]
                n_vertices = target // 8
                if desc_max:
                    n_vertices = desc_max
                if load_arrays:
                    axes = [b.as_f8(data)[:n_vertices] for b in trio]
                    xyz = np.column_stack(axes)

        # ── LS_Faces：face_type + conn（CSR，npe = type - 130）────────
        sec = f.get_section("LS_Faces")
        n_faces = 0
        face_type = np.empty(0, dtype=np.int64)
        conn = np.empty(0, dtype=np.int64)
        if sec:
            counts = [d.dim0 for d in iter_descriptors(data, sec) if d.dim0 > 1]
            if counts:
                n_faces = counts[0]
            blocks = list(iter_data_blocks(data, sec))
            if blocks:
                if load_arrays:
                    face_type = blocks[0].as_i4(data)
                    n_faces = len(face_type)
                    if len(blocks) > 1:
                        conn = blocks[1].as_i4(data)
                        expect = int((face_type - 130).sum())
                        if expect != len(conn):
                            raise ValueError(
                                f"{filepath}: LS_Faces 连接表长度 {len(conn)} "
                                f"!= sum(face_type-130) {expect}")
                else:
                    n_faces = blocks[0].byte_count // 4

        # ── LS_CsidOfFaces / LS_FridOfFaces：各两个 I4[n_faces] 块 ────
        def _i4_pairs(name: str) -> tuple[np.ndarray, np.ndarray]:
            s = f.get_section(name)
            if not s or not load_arrays:
                return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)
            blks = [b for b in iter_data_blocks(data, s) if b.byte_count % 4 == 0]
            a = blks[0].as_i4(data) if len(blks) > 0 else np.empty(0, dtype=np.int64)
            b = blks[1].as_i4(data) if len(blks) > 1 else np.empty(0, dtype=np.int64)
            return a, b

        csid = _i4_pairs("LS_CsidOfFaces")
        frid_pair = _i4_pairs("LS_FridOfFaces")
        frid = frid_pair[0]

        # ── LS_EdgeStateOfFaces：U1[sum(npe)] ─────────────────────────
        sec = f.get_section("LS_EdgeStateOfFaces")
        edge_state = np.empty(0, dtype=np.uint8)
        if sec and load_arrays:
            for b in iter_data_blocks(data, sec):
                if b.byte_count >= 1:
                    edge_state = b.as_u1(data)
                    break

        # ── LS_StateOfNodes：I4[n_nodes] ──────────────────────────────
        sec = f.get_section("LS_StateOfNodes")
        node_state = np.empty(0, dtype=np.int64)
        if sec and load_arrays:
            for b in iter_data_blocks(data, sec):
                if b.byte_count % 4 == 0 and b.byte_count >= 4:
                    node_state = b.as_i4(data)
                    break

        # ── LS_MdlClosedVolumes：255B 名称块列表 ──────────────────────
        closed_volumes: list[str] = []
        sec = f.get_section("LS_MdlClosedVolumes")
        if sec:
            for b in iter_data_blocks(data, sec):
                raw = bytes(data[b.offset : b.offset + b.byte_count])
                if all(x == 0 or 32 <= x < 127 for x in raw):
                    closed_volumes.append(
                        raw.decode("ascii", errors="replace").strip("\x00").rstrip())

        # ── LS_MdlVolumeRegions：体区域名 ─────────────────────────────
        volume_regions: list[str] = []
        sec = f.get_section("LS_MdlVolumeRegions")
        if sec:
            for b in iter_data_blocks(data, sec):
                raw = bytes(data[b.offset : b.offset + b.byte_count])
                if all(x == 0 or 32 <= x < 127 for x in raw):
                    s = raw.decode("ascii", errors="replace").strip("\x00").rstrip()
                    if s:
                        volume_regions.append(s)

        # ── LS_MdlSurfaceRegions：名称块 + 紧随描述符链末值 = frid ─────
        surface_regions: list[MdlSurfaceRegion] = []
        sec = f.get_section("LS_MdlSurfaceRegions")
        if sec:
            name_positions: list[tuple[str, int]] = []
            records = list(iter_records(data, sec))
            for i, rec in enumerate(records):
                if isinstance(rec, DataBlock):
                    raw = bytes(data[rec.offset : rec.offset + rec.byte_count])
                    if all(x == 0 or 32 <= x < 127 for x in raw):
                        nm = raw.decode("ascii", errors="replace").strip("\x00").rstrip()
                        if nm:
                            name_positions.append((nm, i))
            for j, (nm, i) in enumerate(name_positions):
                end_i = (name_positions[j + 1][1]
                         if j + 1 < len(name_positions) else len(records))
                desc_vals = [r.dim0 for r in records[i + 1 : end_i]
                             if isinstance(r, Descriptor)]
                arrays = []
                for r in records[i + 1 : end_i]:
                    if isinstance(r, DataBlock) and r.byte_count % 4 == 0:
                        arrays.append(r.as_i4(data))
                index = desc_vals[-1] if desc_vals else 0
                surface_regions.append(
                    MdlSurfaceRegion(nm, index, desc_vals, arrays))

        return MdlModel(
            n_vertices=n_vertices, n_faces=n_faces, xyz=xyz, face_type=face_type,
            conn=conn, csid=csid, frid=frid, edge_state=edge_state,
            node_state=node_state, closed_volumes=closed_volumes,
            volume_regions=volume_regions, surface_regions=surface_regions,
        )


def _i32(value: int) -> bytes:
    return struct.pack(">i", int(value))


def _descriptor(type_code: int, dim0: int, dim1: int) -> bytes:
    return _i32(12) + _i32(type_code) + _i32(dim0) + _i32(dim1)


def _block(payload: bytes) -> bytes:
    return _i32(12) + _i32(len(payload)) + payload + _i32(len(payload))


def _section(name: str, body: bytes) -> bytes:
    return _i32(32) + name.ljust(32).encode("ascii") + body


def _name255(text: str) -> bytes:
    raw = text.encode("ascii", errors="replace")[:255]
    return raw.ljust(255, b" ")


def _name_record(text: str) -> bytes:
    """255B 名称记录：``desc(type=1, 255, 1) + block(name255)``（原生布局）。"""
    return _descriptor(1, 255, 1) + _block(_name255(text))


# 区域/闭体三节共用的 20 字节节尾（box/laptop 实测一致）：I4=12 + 16×0
_SECTION_TRAILER = _i32(12) + b"\x00" * 16


def _regions_section(names_idx: list) -> bytes:
    """LS_MdlSurfaceRegions 原生布局（box/laptop 钉死）。

    头：``desc(4,1,1) desc(4,1,4) desc(4,1,1) desc(4,N,4)`` +
    名称头 ``desc(4,1,1) desc(4,255,4)``；每区域：名称记录 +
    ``desc(4,1,1) desc(4,1,4) desc(4,1,1) desc(4,frid,4)``；节尾 20B。
    """
    body = bytearray()
    body += _descriptor(4, 1, 1) + _descriptor(4, 1, 4)
    body += _descriptor(4, 1, 1) + _descriptor(4, len(names_idx), 4)
    body += _descriptor(4, 1, 1) + _descriptor(4, 255, 4)
    for name, idx in names_idx:
        body += _name_record(name)
        body += (_descriptor(4, 1, 1) + _descriptor(4, 1, 4) +
                 _descriptor(4, 1, 1) + _descriptor(4, int(idx), 4))
    body += _SECTION_TRAILER
    return _section("LS_MdlSurfaceRegions", bytes(body))


def _closed_volumes_section(names: list) -> bytes:
    """LS_MdlClosedVolumes 原生布局（box/laptop 钉死）。

    记录数 = N+1（记录 0 = 外部，空名）；记录 i 尾随 6 个描述符：
    ``(1,1) (i%2,4) (1,1) (1,4) (1,1) (i,4)``（laptop 5 记录验证）。
    """
    body = bytearray()
    body += _descriptor(4, 1, 1) + _descriptor(4, 1, 4)
    body += _descriptor(4, 1, 1) + _descriptor(4, len(names), 4)
    body += _descriptor(4, 1, 1) + _descriptor(4, 255, 4)
    for i, name in enumerate(names):
        body += _name_record(name)
        body += (_descriptor(4, 1, 1) + _descriptor(4, i % 2, 4) +
                 _descriptor(4, 1, 1) + _descriptor(4, 1, 4) +
                 _descriptor(4, 1, 1) + _descriptor(4, i, 4))
    body += _SECTION_TRAILER
    return _section("LS_MdlClosedVolumes", bytes(body))


def _volume_regions_section(names: list) -> bytes:
    """LS_MdlVolumeRegions 原生布局（box 风格：无内部种子点）。"""
    body = bytearray()
    body += _descriptor(4, 1, 1) + _descriptor(4, 1, 4)
    body += _descriptor(4, 1, 1) + _descriptor(4, len(names), 4)
    body += _descriptor(4, 1, 1) + _descriptor(4, 255, 4)
    for name in names:
        body += _name_record(name)
        body += (_descriptor(4, 1, 1) + _descriptor(4, 1, 4) +
                 _descriptor(4, 1, 1) + _descriptor(4, 1, 4))
    body += _SECTION_TRAILER
    return _section("LS_MdlVolumeRegions", bytes(body))


def write_mdl(filepath,
              points,
              faces,
              *,
              app: str = "SCTpre",
              date: int = 20260814,
              unit: str = "m",
              csid=None,
              frid=None,
              edge_state=None,
              node_state=None,
              surface_regions=None,
              closed_volumes=None,
              volume_regions=None) -> "Path":
    """写最小 CRDL-FLD MDL 面片（``*_part.mdl``，可被 :func:`parse_mdl` 读回）。

    ``points``：(n,3) 坐标；``faces``：多边形顶点索引（3 或 4 顶点，
    ``face_type = 130 + npe``，133=三角 / 134=四边）。

    ``csid``：面两侧闭体 id 元组，默认 ``(zeros, ones)`` —— 全部面为
    body 1 的边界面；``frid`` 默认全 0；``edge_state`` 默认全 0；
    ``surface_regions`` 默认 ``[("@PartSurface_Part", 0)]``，便于 Part Tree
    识别零件名。

    ``closed_volumes``：闭体名列表（**含**记录 0 = 外部，通常空名），
    传入时按原生布局写 ``LS_MdlClosedVolumes``；``volume_regions``：
    体区域名列表（如 ``["FluidRegion"]``），传入时写
    ``LS_MdlVolumeRegions``。两者缺省不写（保持最小写端行为）。
    """
    verts = np.asarray(points, dtype=float).reshape(-1, 3)
    n_vertices = len(verts)
    face_list = [np.asarray(f, dtype=np.int64).reshape(-1) for f in faces]
    npe = np.asarray([len(f) for f in face_list], dtype=np.int64)
    if npe.size == 0 or np.any((npe != 3) & (npe != 4)):
        raise ValueError("write_mdl supports triangle/quad faces only")
    n_faces = len(face_list)
    face_type = (130 + npe).astype(">i4")
    conn_flat = np.concatenate(face_list) if n_faces else \
        np.empty(0, dtype=np.int64)
    conn_total = int(conn_flat.size)

    b1, b2 = (csid if csid is not None
              else (np.zeros(n_faces, dtype=np.int64),
                    np.ones(n_faces, dtype=np.int64)))
    b1 = np.asarray(b1, dtype=">i4").reshape(-1)
    b2 = np.asarray(b2, dtype=">i4").reshape(-1)
    if b1.size != n_faces or b2.size != n_faces:
        raise ValueError("csid length must equal faces length")
    fr = np.asarray(frid if frid is not None
                    else np.zeros(n_faces, dtype=np.int64),
                    dtype=">i4").reshape(-1)
    if fr.size != n_faces:
        raise ValueError("frid length must equal faces length")
    es = np.asarray(edge_state if edge_state is not None
                    else np.zeros(conn_total, dtype=np.uint8),
                    dtype=np.uint8).reshape(-1)
    if es.size != conn_total:
        raise ValueError("edge_state length must equal sum(npe)")
    ns = np.asarray(node_state if node_state is not None
                    else np.zeros(n_vertices, dtype=np.int64),
                    dtype=">i4").reshape(-1)
    if ns.size != n_vertices:
        raise ValueError("node_state length must equal n_vertices")

    regions = list(surface_regions if surface_regions is not None
                   else [("@PartSurface_Part", 0)])
    unit8 = unit.encode("ascii")[:8].ljust(8)
    unit32 = unit.encode("ascii")[:32].ljust(32)
    out = bytearray()
    out += _i32(8) + MAGIC + _i32(8) + _i32(4) + _i32(4)
    out += _section("FileRevision",
                    _descriptor(4, 1, 1) + _descriptor(4, 2025, 4))
    out += _section("Application", _block(app.encode("ascii")[:8].ljust(8)))
    out += _section("GridType", _descriptor(4, 1, 1) + _descriptor(4, 1, 4))
    out += _section("Dimension",
                    _descriptor(4, 1, 1) + _descriptor(4, 3, 4))
    out += _section("Bias", _descriptor(4, 1, 1) + _descriptor(4, 0, 4))
    out += _section("Date", _descriptor(4, 1, 1) + _descriptor(4, date, 4))
    out += _section("ApplicationVersion",
                    _descriptor(4, 1, 1) + _descriptor(4, 2025, 4))
    out += _section("ReleaseDate",
                    _descriptor(4, 1, 1) + _descriptor(4, 20251217, 4))
    out += _section("Encoding", _block(b" " * 32))
    out += _section(
        "UnitOfCoordinates",
        _descriptor(8, 1, 1) + _block(unit8) + _block(unit32) + _block(unit32))
    out += _section("HeaderDataEnd", b"")
    out += _section("OverlapStart_0", b"")
    out += _section("LS_CoordinateSystem",
                    _descriptor(4, 1, 1) + _descriptor(4, 1, 4) +
                    _descriptor(4, 1, 1) + _descriptor(4, 0, 4))

    nodes = (
        _descriptor(4, 1, 1) + _descriptor(4, 1, 4) +
        _descriptor(4, 1, 1) + _descriptor(4, n_vertices, 4) +
        _descriptor(8, n_vertices, 1) +
        _descriptor(8, n_vertices, 1) + _descriptor(8, n_vertices, 1) +
        _block(verts[:, 0].astype(">f8").tobytes()) +
        _block(verts[:, 1].astype(">f8").tobytes()) +
        _block(verts[:, 2].astype(">f8").tobytes()))
    out += _section("LS_Nodes", nodes)

    faces_sec = (
        _descriptor(4, 1, 1) + _descriptor(4, 1, 4) +
        _descriptor(4, 1, 1) + _descriptor(4, n_faces, 4) +
        _descriptor(4, n_faces, 1) +
        _descriptor(4, 1, 1) + _descriptor(4, conn_total, 4) +
        _descriptor(4, conn_total, 1) +
        _block(face_type.tobytes()) +
        _block(conn_flat.astype(">i4").tobytes()))
    out += _section("LS_Faces", faces_sec)

    pair_sec = (
        _descriptor(4, 1, 1) + _descriptor(4, 1, 4) +
        _descriptor(4, 1, 1) + _descriptor(4, n_faces, 4) +
        _descriptor(4, n_faces, 1) + _descriptor(4, n_faces, 1))
    out += _section("LS_CsidOfFaces",
                    pair_sec + _block(b1.tobytes()) + _block(b2.tobytes()))
    out += _section("LS_FridOfFaces",
                    pair_sec + _block(fr.tobytes()) + _block(fr.tobytes()))
    out += _section(
        "LS_EdgeStateOfFaces",
        _descriptor(4, 1, 1) + _descriptor(4, 1, 4) +
        _descriptor(4, 1, 1) + _descriptor(4, conn_total, 4) +
        _block(es.tobytes()))
    out += _section(
        "LS_StateOfNodes",
        _descriptor(4, 1, 1) + _descriptor(4, 1, 4) +
        _descriptor(4, 1, 1) + _descriptor(4, n_vertices, 4) +
        _descriptor(4, n_vertices, 1) + _block(ns.tobytes()))

    # 节序与原生一致：ClosedVolumes → VolumeRegions → SurfaceRegions
    if closed_volumes is not None:
        out += _closed_volumes_section(list(closed_volumes))
    if volume_regions is not None:
        out += _volume_regions_section(list(volume_regions))
    if regions:
        out += _regions_section(regions)
    out += _section("OverlapEnd", b"")

    path = Path(filepath)
    path.write_bytes(bytes(out))
    return path


def detect_tiny_faces(model: MdlModel, width_tol: float) -> list[dict]:
    """按“面最大边长 < 容差”识别 tiny face（宽度指标取最大边）。

    返回 ``[{face_id, width, n_facets}]``；n_facets 按 MDL 面片粒度记为 1。
    """
    if model.n_faces == 0 or model.xyz.size == 0 or width_tol <= 0:
        return []
    off = model.face_offsets
    xyz = model.xyz
    conn = model.conn
    out: list[dict] = []
    for fid in range(model.n_faces):
        nodes = conn[off[fid]:off[fid + 1]]
        if nodes.size < 3:
            continue
        pts = xyz[nodes]
        d = np.linalg.norm(np.roll(pts, -1, axis=0) - pts, axis=1)
        width = float(d.max()) if d.size else 0.0
        if width < float(width_tol):
            out.append({"face_id": fid, "width": width, "n_facets": 1})
    return out


def detect_multifold_edges(model: MdlModel) -> dict[tuple[int, int], list[int]]:
    """识别被 >2 个面共享的边（multi-fold edges）。

    返回 ``{(v0,v1): [face_id, ...]}``，键按顶点序号升序。
    """
    from collections import defaultdict

    if model.n_faces == 0 or model.xyz.size == 0:
        return {}
    edge_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    off = model.face_offsets
    conn = model.conn
    for fid in range(model.n_faces):
        nodes = conn[off[fid]:off[fid + 1]]
        n = len(nodes)
        for k in range(n):
            a = int(nodes[k])
            b = int(nodes[(k + 1) % n])
            key = (min(a, b), max(a, b))
            edge_faces[key].append(fid)
    return {k: v for k, v in edge_faces.items() if len(v) > 2}


def detect_matching_faces(model: MdlModel) -> list[dict]:
    """启发式识别重合匹配面：质心/面积相近且法向相反的面对面。

    返回 ``[{group1, group2, direction}]``；direction 取 "Forward"/"Reverse"，
    这里把法向相反的一对标记为 "Reverse"。
    """
    if model.n_faces == 0 or model.xyz.size == 0:
        return []
    off = model.face_offsets
    xyz = model.xyz
    conn = model.conn
    groups: dict[tuple, list] = {}
    for fid in range(model.n_faces):
        nodes = conn[off[fid]:off[fid + 1]]
        if nodes.size < 3:
            continue
        pts = xyz[nodes]
        centroid = pts.mean(axis=0)
        v1 = pts[1] - pts[0]
        v2 = pts[2] - pts[0]
        n = np.cross(v1, v2)
        norm = float(np.linalg.norm(n))
        if norm < 1e-12:
            continue
        n = n / norm
        area = norm / 2.0
        key = (tuple(np.round(centroid, 5)),
               round(area, 6),
               tuple(np.round(np.abs(n), 4)))
        groups.setdefault(key, []).append((fid, n))
    out: list[dict] = []
    for faces in groups.values():
        if len(faces) < 2:
            continue
        for i in range(len(faces)):
            fi, ni = faces[i]
            for fj, nj in faces[i + 1:]:
                if float(np.dot(ni, nj)) < -0.999:
                    out.append({"group1": fi, "group2": fj,
                                "direction": "Reverse"})
    return out
