#!/usr/bin/env python3
"""Parasolid 二进制传输流（``.x_b`` 类）轻量部分提取。

``PKBody3.decrypt()`` 得到 scFLOW 内嵌的 Parasolid 传输流：开头为

.. code-block:: text

    A3.: TRANSMIT FILE created by modeller version 3701153
    SCH_3701153_37102_13006

随后是 schema 字段定义表（类型 token + 字段名 + 数据区偏移）与
CADthru 拓扑数据（lattice / mesh / polyline / owner / boundary_* /
index_map_* / child / lowest_node_id / mesh_offset_data …），以及
实体类型（``CADthru/PKEdge``、``CADthru/PKFace``、``CADthru/PKVertex``）
和 SDL 属性（``SDL/TYSA_NAME``、``SDL/TYSA_LAYER``、``SDL/TYSA_UNAME``）。

本模块只做**轻量部分提取**（不还原完整 B-rep 拓扑）：

- 文件头与 schema 标识（版本号）；
- schema 字段表：``(token, 字段名, 位置)``——按 ``[ASCII token][u8 长度]
  [ASCII 名]`` 记录帧扫描，不依赖完整布局；
- 实体类型与 SDL 属性出现位置。

完整实体几何（顶点/边/面的连接与坐标）需要 Parasolid 内核或完整逆向，
超出本模块范围（见 DEV_SUMMARY 3.1）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


HEADER_PREFIX = b"TRANSMIT FILE created by modeller version "
SCHEMA_RE = re.compile(rb"SCH_\d+_\d+_\d+")
ENTITY_RE = re.compile(rb"CADthru/PK[A-Z][A-Za-z]*[a-z]")
SDL_RE = re.compile(rb"SDL/TYSA_(?:NAME|LAYER|UNAME)")

# 字段记录帧：[token][u8 len][name]。
# token = 类型字母（可带 $ / l / u / d 前缀，如 $CCCI、CCCA、lCCCDCCDI、dA、uI）。
_TOKEN_RE = re.compile(rb"\$?[A-Z]+|[lud][A-Z]+")
_NAME_RE = re.compile(rb"[A-Za-z_$][A-Za-z0-9_/$]*")


@dataclass
class ParasolidField:
    """schema 字段定义记录。"""

    token: str       # 类型 token（I / A / Z / CI / CCCI / CCCA / CCCC…DI 等）
    name: str        # 字段名（lattice / mesh / owner / CADthru/PKEdge 等）
    pos: int         # 记录在流中的字节偏移


@dataclass
class ParasolidStream:
    """部分提取结果。"""

    size: int
    version: Optional[int] = None
    schema: Optional[str] = None
    header_line: str = ""
    fields: list[ParasolidField] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)      # 出现顺序
    sdl_attributes: list[str] = field(default_factory=list)

    @property
    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]

    def summary(self) -> str:
        lines = [f"Parasolid 传输流: {self.size} B"
                 f" version={self.version} schema={self.schema}"]
        lines.append(f"字段 {len(self.fields)} 个: "
                     + ", ".join(f"{f.name}({f.token})" for f in self.fields))
        if self.entities:
            from collections import Counter
            counts = Counter(self.entities)
            lines.append("实体: " + ", ".join(
                f"{name}×{counts[name]}" for name in sorted(counts)))
        if self.sdl_attributes:
            lines.append("SDL 属性: " + ", ".join(self.sdl_attributes))
        return "\n".join(lines)


def _parse_version(header: bytes) -> Optional[int]:
    m = re.search(rb"version (\d+)", header)
    return int(m.group(1)) if m else None


def _is_printable_name(raw: bytes) -> bool:
    return bool(raw) and all(32 <= b < 127 for b in raw)


def scan_fields(data: bytes, start: int = 0, end: Optional[int] = None
                ) -> list[ParasolidField]:
    """按 ``[token][u8 len][name]`` 帧扫描 schema 字段记录。

    该帧在流中多处出现（schema 定义表 + 内嵌定义），用 token 字符集与
    可打印名字双重校验；位置为记录帧起点（token 首字节偏移）。
    """
    n = end if end is not None else len(data)
    out: list[ParasolidField] = []
    pos = start
    while pos + 2 <= n:
        m = _TOKEN_RE.match(data, pos)
        if not m or m.end() >= n:
            pos += 1
            continue
        ln = data[m.end()]
        name_start = m.end() + 1
        name_end = name_start + ln
        if not (1 <= ln <= 128 and name_end <= n):
            pos += 1
            continue
        name = bytes(data[name_start:name_end])
        if not _is_printable_name(name) or not _NAME_RE.fullmatch(name):
            pos += 1
            continue
        # 尾随标记字节（'R'/'P' 等）不计入 len，但紧跟 0x00 时并入名字
        # （实测 index_mapR / node_id_index_mapR / schema_embedding_mapR）。
        end = name_end
        while (end + 1 < n and 65 <= data[end] <= 90 and data[end + 1] == 0
               and _NAME_RE.fullmatch(
                   name + bytes([data[end]]))):
            name = name + bytes([data[end]])
            end += 1
        out.append(ParasolidField(
            m.group().decode("ascii"), name.decode("ascii"), pos))
        pos = end
    return out


def parse_transmit(data: bytes) -> ParasolidStream:
    """轻量解析：头/schema + 字段表 + 实体类型 + SDL 属性。"""
    result = ParasolidStream(size=len(data))
    # ── 文件头 ─────────────────────────────────────────────────────
    idx = data.find(HEADER_PREFIX)
    if idx >= 0:
        head = data[idx:]
        line_end = head.find(b"\x00")
        if line_end < 0:
            line_end = len(head)
        result.header_line = head[:line_end].decode("ascii", "replace")
        result.version = _parse_version(head[:line_end])
    m = SCHEMA_RE.search(data)
    if m:
        result.schema = m.group().decode("ascii")
    # ── 字段表 ─────────────────────────────────────────────────────
    result.fields = scan_fields(data)
    # ── 实体类型 / SDL 属性 ────────────────────────────────────────
    result.entities = [m.group().decode("ascii")
                       for m in ENTITY_RE.finditer(data)]
    result.sdl_attributes = [m.group().decode("ascii")
                             for m in SDL_RE.finditer(data)]
    return result


def parse_file(path: str) -> ParasolidStream:
    with open(path, "rb") as f:
        return parse_transmit(f.read())
