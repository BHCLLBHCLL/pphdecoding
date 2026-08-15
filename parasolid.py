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

# 类型 token 字母表（Parasolid transmit 字段类型编码，V37 观测；前缀/字母语义
# 为最佳推断，C 与 $ 的确切含义待与 entity 数据区对拍钉死）。
TOKEN_ALPHABET = {
    "I": "integer (4B)",
    "D": "double (8B)",
    "A": "array (of ints, length-prefixed)",
    "C": "tag-or-count (待钉死)",
    "$": "tag / entity reference 前缀",
    "l": "list 前缀",
    "u": "unsigned 前缀",
    "d": "double-array 前缀",
}


def field_data_offsets(stream: "ParasolidStream") -> dict[str, int]:
    """字段名 → 数据区偏移（P2）。

    共享同偏移的字段互为别名——实测 lattice/boundary_lattice 同 222、
    mesh/boundary_mesh 同 1006、polyline/boundary_polyline 同 1008。
    """
    return {f.name: f.data_offset
            for f in stream.fields if f.data_offset >= 0}


# V37 实体 class 枚举（PK_ENTITY_ask_class 实测，见 ps_facet2_nodes.extract_brep）。
PK_CLASS_NAMES = {
    2501: "point", 3001: "curve", 4001: "surface",
    5001: "vertex", 5002: "edge", 5003: "loop",
    5004: "face", 5005: "fin", 5006: "body", 5007: "part",
}


def parse_text_entities(xt_text: str) -> dict:
    """解析文本 x_t（无内核）：头元数据 + 实体类型码 + 回引计数（P3）。

    文本 x_t（FORMAT=text, GUISE=transmit）头为 **PART1/2/3 元数据，之后是
    实体流：T<n> 为实体类型定义（每类一次），?n 为对已定义实体的回引
    （≈ 实体实例数）。返回 {header, version, schema, type_counts, n_refs,
    sdl_attributes}。
    """
    header: dict[str, str] = {}
    for key in ("MC", "FORMAT", "GUISE", "KEY", "MC_MODEL"):
        m = re.search(rf"^{key}=(.*?);", xt_text, re.M)
        if m:
            header[key] = m.group(1)
    ver = _parse_version(xt_text.encode("ascii", "replace"))
    sch = SCHEMA_RE.search(xt_text.encode("ascii", "replace"))
    from collections import Counter
    type_counts = {int(k): v
                   for k, v in sorted(Counter(
                       int(x) for x in re.findall(r"\bT(\d+)\b", xt_text)
                   ).items())}
    n_refs = len(re.findall(r"\?(\d+)", xt_text))
    sdl = sorted(set(re.findall(r"SDL/[A-Z_]+", xt_text)))
    return {
        "header": header,
        "version": ver,
        "schema": sch.group().decode("ascii") if sch else None,
        "type_counts": type_counts,
        "n_refs": n_refs,
        "sdl_attributes": sdl,
    }


@dataclass
class ParasolidField:
    """schema 字段定义记录。"""

    token: str       # 类型 token（I / A / Z / CI / CCCI / CCCA / CCCC…DI 等）
    name: str        # 字段名（lattice / mesh / owner / CADthru/PKEdge 等）
    pos: int         # 记录在流中的字节偏移
    data_offset: int = -1   # 字段数据区偏移（名字之后的小端 u32；-1 未解析）


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
        suffix = 0
        while (end + 1 < n and 65 <= data[end] <= 90 and data[end + 1] == 0
               and _NAME_RE.fullmatch(
                   name + bytes([data[end]]))):
            name = name + bytes([data[end]])
            end += 1
            suffix += 1
        # 数据区偏移：名字（含 R/P 后缀）之后的小端 u32；R/P 后缀紧接 0x00
        # 分隔符再跟 u32（实测 index_mapR / node_id_index_mapR 等）。
        doff_pos = end
        if suffix and doff_pos + 5 <= n and data[doff_pos] == 0:
            doff_pos += 1
        data_offset = -1
        if doff_pos + 4 <= n:
            data_offset = int.from_bytes(data[doff_pos:doff_pos + 4], "little")
        out.append(ParasolidField(
            m.group().decode("ascii"), name.decode("ascii"), pos, data_offset))
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
