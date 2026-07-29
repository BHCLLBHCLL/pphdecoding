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

from dataclasses import dataclass

import numpy as np

from crdlfld import (CrdlFldFile, DataBlock, Descriptor, iter_data_blocks,
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
