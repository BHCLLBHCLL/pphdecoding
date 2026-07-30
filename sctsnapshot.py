#!/usr/bin/env python3
"""SCTSNAPSHOT 快照文件解析（scFLOW ``main.sctsnapshot``）。

文件是 **小端** 的嵌套记录流（与 CRDL-FLD 的大端不同！）：

.. code-block:: text

    record := TAG[16] (ASCII，空格填充) + LEN (u32le) + PAYLOAD[LEN]

顶层结构（按序）：

1. ``CADTHRUVERSION`` = 8，``TREESTRUCT``   — GUI 树状态（TreeState）
2. ``CADTHRUVERSION`` = 8，``VIEWSTRUCT``   — 视图状态（ViewState，DOUBLEARRAY 18×f64）
3. ``CADTHRUVERSION`` = 3，``TOPASSYSTRUCT`` — 顶层装配 + Parasolid 体
   （``UNIQUEBODYNUMBER`` + N × (``PKBODY_T`` + ``ZIPBODYBYTES``) + ``ASSEMBLY`` 树）
4. ``TOPASSYSTRUCT`` — 八叉树装配（``MESHPRMDLGDATA`` + ``ZIPOCTREE``）
5. ``BSGSEX`` — BodyShapeGroups：网格组 / 八叉树参数 / 区域加密限制
6. N × (``CADTHRUVERSION`` + ``QUEUESTRUCT``) — 其他 GUI 队列

``*STRUCT`` / ``ASSEMBLY`` / ``BODY`` / ``BYTEARRAY`` / ``WRAPBYTEARRAY`` /
``FACEGROUPSW`` / ``FACEINFOMAP`` / ``FFREVERSEMAP`` 等为容器（负载是子记录）。

ZIP 压缩块（``ZIPBODYBYTES`` / ``ZIPOCTREE`` / ``ZIPFACETINGRULES``）整段负载
即为 **Microsoft LZMS** 压缩流（Windows Compression API，
``COMPRESSION_ALGORITHM_LZMS = 4``，``cabinet.dll``）。流首可读字段：

.. code-block:: text

    [magic u32le = 0xC0E5510A][hdr_len u16le = 24][stream_id u16le]
    [uncompressed_size u64le][uncompressed_size 重复 u64le]
    [compressed_size u32le][...LZMS 压缩数据...]

解压后内容：

- ``ZIPBODYBYTES`` → ``CADthru/PKBody3`` 包装的 Parasolid 体二进制
- ``ZIPOCTREE`` / ``ZIPFACETINGRULES`` → 嵌套的快照记录流
"""

from __future__ import annotations

import struct
import sys
from dataclasses import dataclass, field
from typing import Iterator, Optional

import numpy as np

ZIP_MAGIC = 0xC0E5510A
PKBODY3_MAGIC = b"CADthru/PKBody3"
COMPRESSION_ALGORITHM_LZMS = 4

# UTF-16-LE 字符串标签
_UTF16_TAGS = {"STRINGW", "NAMESTRINGW", "PRPFILESTRINGW", "SFILESTRINGW"}
# 原始字节串标签（不按 UTF-16 解码）
_BYTES_TAGS = {"LOCATIONSTRING", "REALPOSNAMES", "ORGFILENAMES"}
# u16 状态数组
_U16_TAGS = {"FACESTATES", "EDGESTATES", "VERTEXSTATES"}
# i32 PK id 数组
_I32_TAGS = {"FIDPKFACE", "EIDPKEDGE", "VIDPKVERTEX"}
# u8 数组
_U8_TAGS = {"EDGEISSEAMLINE", "BODYSELECTION"}
# 4 字节标量（u32/i32 值）标签
_SCALAR4_TAGS = {
    "CADTHRUVERSION", "QUEUEID", "INTEGER", "BOOL", "SGBOOL",
    "UNIQUEBODYNUMBER", "UNIQUEBODYNUM4", "PKBODY_T", "PKASSEMBLY_T",
    "CHILDRENNUMBER", "CHILDRENTYPE", "FACEGROUPNUMBER", "FACEARRAYSIZE",
    "NAMELENGTH", "LOCATIONLENGTH", "VPARTID", "MESHENABLED", "RECALCNODE",
    "COLOR", "COLORINDEX", "DATAKITORGFLG", "SPATIALSEPFLG", "POCTREEASM",
    "OCTREEBALANCING", "CSINFO_CECOUNT", "I777", "DUMMYASSYINFO_UNUSED",
    "FACESTATESLENGTH", "EDGESTATESLENGTH", "VERTEXSTATESLEN",
    "FIDPKFACELENGTH", "EIDPKEDGELENGTH", "VIDPKVERTEXLEN",
    "ZEROLENGTH", "ZEROLENGTH2", "EDGEISSEAMLINE_UNUSED", "MESH_CHORDTOL_UNUSED",
}
# 明确的叶子（不尝试按容器展开）
_LEAF_TAGS = (_UTF16_TAGS | _BYTES_TAGS | _U16_TAGS | _I32_TAGS | _U8_TAGS
              | {"STRING", "DOUBLE", "INTARRAY", "DOUBLEARRAY", "TRANSFORMMATRIX",
                 "ZIPBODYBYTES", "ZIPOCTREE", "ZIPFACETINGRULES"})


def lzms_available() -> bool:
    """当前平台是否可通过 ``cabinet.dll`` 解压 LZMS。"""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        ctypes.WinDLL("cabinet.dll")
        return True
    except OSError:
        return False


def lzms_decompress(compressed: bytes,
                    uncompressed_size: Optional[int] = None) -> bytes:
    """用 Windows Compression API（``cabinet.dll``）解压 LZMS 流。

    ``compressed`` 必须是完整记录负载（含流首 28 字节可读字段）。
    """
    if sys.platform != "win32":
        raise RuntimeError("LZMS 解压需要 Windows cabinet.dll")
    import ctypes
    from ctypes import wintypes

    cab = ctypes.WinDLL("cabinet.dll")
    CreateDecompressor = cab.CreateDecompressor
    CreateDecompressor.argtypes = [
        wintypes.DWORD, wintypes.LPVOID, ctypes.POINTER(wintypes.LPVOID)]
    CreateDecompressor.restype = wintypes.BOOL
    Decompress = cab.Decompress
    Decompress.argtypes = [
        wintypes.LPVOID, wintypes.LPCVOID, ctypes.c_size_t,
        wintypes.LPVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    Decompress.restype = wintypes.BOOL
    CloseDecompressor = cab.CloseDecompressor
    CloseDecompressor.argtypes = [wintypes.LPVOID]
    CloseDecompressor.restype = wintypes.BOOL

    handle = wintypes.LPVOID()
    if not CreateDecompressor(COMPRESSION_ALGORITHM_LZMS, None,
                              ctypes.byref(handle)):
        raise OSError(ctypes.GetLastError(), "CreateDecompressor(LZMS) 失败")
    try:
        needed = ctypes.c_size_t(0)
        ok = Decompress(handle, compressed, len(compressed),
                        None, 0, ctypes.byref(needed))
        err = ctypes.GetLastError()
        # ERROR_INSUFFICIENT_BUFFER = 122：查询输出尺寸时的预期返回
        if not ok and err not in (0, 122):
            raise OSError(err, "Decompress(LZMS) 查询尺寸失败")
        cap = needed.value or (uncompressed_size or 0)
        if uncompressed_size and uncompressed_size > cap:
            cap = uncompressed_size
        if cap <= 0:
            raise OSError(err, "Decompress(LZMS) 无法确定输出尺寸")
        buf = ctypes.create_string_buffer(cap)
        got = ctypes.c_size_t(0)
        if not Decompress(handle, compressed, len(compressed),
                          buf, cap, ctypes.byref(got)):
            raise OSError(ctypes.GetLastError(), "Decompress(LZMS) 失败")
        return buf.raw[:got.value]
    finally:
        CloseDecompressor(handle)


@dataclass
class PKBody3:
    """``ZIPBODYBYTES`` 解压后的 CADThru Parasolid 体包装。

    布局：``CADthru/PKBody3`` (15B) + ``u32le size`` + ``data[size]``，
    部分体其后还有固定尾标 ``u32le = 0x17DA2940``（本样例大体有、小体无；
    非内容 CRC）。
    """

    data: bytes
    checksum: Optional[int] = None  # 实为可选尾标，字段名保留兼容

    @classmethod
    def parse(cls, raw: bytes) -> "PKBody3":
        if not raw.startswith(PKBODY3_MAGIC):
            raise ValueError("不是 CADthru/PKBody3 包装")
        if len(raw) < 19:
            raise ValueError("PKBody3 过短")
        size = struct.unpack("<I", raw[15:19])[0]
        if 19 + size + 4 == len(raw):
            data = raw[19:19 + size]
            checksum = struct.unpack("<I", raw[19 + size:19 + size + 4])[0]
            return cls(data, checksum)
        if 19 + size == len(raw):
            return cls(raw[19:19 + size], None)
        raise ValueError(
            f"PKBody3 尺寸不匹配: size={size} file={len(raw)}")


@dataclass
class ZipBlob:
    """LZMS 压缩块（整段 ``raw`` 即为可解压流）。"""

    codec_id: int                 # 流首 u16（非独立编解码选择器）
    uncompressed_size: int
    compressed_size: int
    payload: bytes = b""          # 流首 28 字节之后的压缩数据
    raw: bytes = b""              # 完整 LZMS 流（含流首字段）

    @classmethod
    def parse(cls, payload: bytes) -> "ZipBlob":
        if len(payload) >= 28 and struct.unpack("<I", payload[:4])[0] == ZIP_MAGIC:
            codec = struct.unpack("<H", payload[6:8])[0]
            unc = struct.unpack("<Q", payload[8:16])[0]
            comp = struct.unpack("<I", payload[24:28])[0]
            return cls(codec, unc, comp, payload[28:], payload)
        return cls(0, 0, len(payload), payload, payload)

    def decompress(self) -> bytes:
        """LZMS 解压，返回明文。"""
        return lzms_decompress(self.raw, self.uncompressed_size)

    def decompress_body(self) -> PKBody3:
        """``ZIPBODYBYTES`` → ``PKBody3``。"""
        return PKBody3.parse(self.decompress())

    def decompress_records(self, max_depth: int = 24) -> list["SnapRecord"]:
        """``ZIPOCTREE`` / ``ZIPFACETINGRULES`` → 嵌套记录树。"""
        data = self.decompress()
        records, _, _ = _parse_region(data, 0, len(data), 0, max_depth)
        return records


@dataclass
class SnapRecord:
    """快照记录树节点。"""

    tag: str
    offset: int
    length: int
    value: object = None          # 标量/字符串/数组（叶子）
    children: list["SnapRecord"] = field(default_factory=list)
    skipped: int = 0              # 负载中无法对齐跳过的字节数

    def find_all(self, tag: str) -> Iterator["SnapRecord"]:
        if self.tag == tag:
            yield self
        for c in self.children:
            yield from c.find_all(tag)

    def first(self, tag: str) -> Optional["SnapRecord"]:
        return next(self.find_all(tag), None)

    def text(self, max_value_len: int = 60) -> str:
        """单行显示。"""
        v = self.value
        if v is None and self.children:
            return f"{self.tag} [{self.length}] {{{len(self.children)} 子记录}}"
        if isinstance(v, bytes):
            return f"{self.tag} [{self.length}] <{len(v)} bytes>"
        if isinstance(v, np.ndarray):
            return f"{self.tag} [{self.length}] array{v.shape} {v[:6].tolist()}{'...' if v.size > 6 else ''}"
        if isinstance(v, ZipBlob):
            return (f"{self.tag} [{self.length}] LZMS id={v.codec_id} "
                    f"unc={v.uncompressed_size} comp={v.compressed_size}")
        s = repr(v)
        if len(s) > max_value_len:
            s = s[:max_value_len] + "..."
        return f"{self.tag} [{self.length}] = {s}"

    def dump(self, depth: int = 0, max_depth: int = 99) -> list[str]:
        pad = "  " * depth
        lines = [pad + f"@{self.offset:#x} " + self.text()]
        if self.skipped:
            lines.append(pad + f"  (+{self.skipped} 字节未对齐填充)")
        if depth < max_depth:
            for c in self.children:
                lines.extend(c.dump(depth + 1, max_depth))
        return lines


def _decode_scalar(tag: str, payload: bytes):
    """已知叶子标签的类型化解码；返回 None 表示按容器/原始处理。"""
    n = len(payload)
    if tag in _UTF16_TAGS:
        return payload.decode("utf-16-le", errors="replace")
    if tag == "STRING":
        return payload.decode("utf-8", errors="replace")
    if tag in _BYTES_TAGS:
        return payload
    if tag == "DOUBLE" and n == 8:
        return struct.unpack("<d", payload)[0]
    if tag == "INTARRAY" and n % 4 == 0:
        return np.frombuffer(payload, dtype="<i4").astype(np.int64).copy()
    if tag in ("DOUBLEARRAY", "TRANSFORMMATRIX") and n % 8 == 0:
        return np.frombuffer(payload, dtype="<f8").astype(np.float64).copy()
    if tag in _U16_TAGS and n % 2 == 0:
        return np.frombuffer(payload, dtype="<u2").copy()
    if tag in _I32_TAGS and n % 4 == 0:
        return np.frombuffer(payload, dtype="<i4").astype(np.int64).copy()
    if tag in _U8_TAGS:
        return np.frombuffer(payload, dtype=np.uint8).copy()
    if tag in ("ZIPBODYBYTES", "ZIPOCTREE", "ZIPFACETINGRULES"):
        return ZipBlob.parse(payload)
    if tag in _SCALAR4_TAGS and n == 4:
        return struct.unpack("<i", payload)[0]
    return None


def _is_plausible_record(data: bytes, pos: int, end: int) -> bool:
    if pos + 20 > end:
        return False
    tagb = data[pos : pos + 16]
    if not all(32 <= b < 127 for b in tagb):
        return False
    if not tagb.strip():
        return False
    ln = struct.unpack("<I", data[pos + 16 : pos + 20])[0]
    return pos + 20 + ln <= end


def _resync(data: bytes, pos: int, end: int, limit: int = 65536) -> int:
    """从 pos 之后寻找下一条看似合法的记录头；找不到返回 -1。"""
    stop = min(end - 20, pos + limit)
    cand = pos + 1
    while cand <= stop:
        if _is_plausible_record(data, cand, end):
            return cand
        cand += 1
    return -1


def _parse_region(data: bytes, start: int, end: int, depth: int,
                  max_depth: int) -> tuple[list[SnapRecord], int, int]:
    """解析 [start, end) 内的记录序列。

    返回 ``(records, parsed_end, skipped_bytes)``。遇到无法对齐的字节时
    尝试向前重新同步（厂商在部分结构后写入未初始化/保留空间）。
    """
    records: list[SnapRecord] = []
    pos = start
    skipped = 0
    while pos + 20 <= end:
        if not _is_plausible_record(data, pos, end):
            nxt = _resync(data, pos, end)
            if nxt < 0:
                skipped += end - pos
                pos = end
                break
            skipped += nxt - pos
            pos = nxt
            continue
        tag = data[pos : pos + 16].decode("ascii", errors="replace").rstrip()
        ln = struct.unpack("<I", data[pos + 16 : pos + 20])[0]
        payload = data[pos + 20 : pos + 20 + ln]
        rec = SnapRecord(tag, pos, ln)
        value = _decode_scalar(tag, payload)
        if value is not None:
            rec.value = value
        elif (ln >= 20 and depth < max_depth and tag not in _LEAF_TAGS
              and _is_plausible_record(payload, 0, len(payload))):
            children, reached, sub_skipped = _parse_region(
                payload, 0, len(payload), depth + 1, max_depth)
            if children and reached >= len(payload) - 0:
                rec.children = children
                rec.skipped = sub_skipped
            else:
                rec.value = payload
        else:
            rec.value = payload
        records.append(rec)
        pos = pos + 20 + ln
    return records, pos, skipped


@dataclass
class SctSnapshot:
    """解析后的 sctsnapshot 文件。"""

    filepath: str
    records: list[SnapRecord]
    skipped_bytes: int

    @classmethod
    def load(cls, filepath: str, max_depth: int = 24) -> "SctSnapshot":
        with open(filepath, "rb") as f:
            data = f.read()
        records, _, skipped = _parse_region(data, 0, len(data), 0, max_depth)
        return cls(filepath, records, skipped)

    def find_all(self, tag: str) -> Iterator[SnapRecord]:
        for r in self.records:
            yield from r.find_all(tag)

    def first(self, tag: str) -> Optional[SnapRecord]:
        return next(self.find_all(tag), None)

    def dump(self, max_depth: int = 99) -> str:
        lines: list[str] = []
        for r in self.records:
            lines.extend(r.dump(0, max_depth))
        return "\n".join(lines)

    # ── 语义提取 ─────────────────────────────────────────────────────
    def bodies(self) -> list[dict]:
        """Parasolid 体清单：``[{pk_body, zip}]``。"""
        out = []
        for top in self.find_all("TOPASSYSTRUCT"):
            pk = None
            for c in top.children:
                if c.tag == "PKBODY_T":
                    pk = c.value
                elif c.tag == "ZIPBODYBYTES" and isinstance(c.value, ZipBlob):
                    out.append({"pk_body": pk, "zip": c.value})
                    pk = None
        return out

    def zip_blobs(self, tag: str) -> list[ZipBlob]:
        """收集指定标签的全部 LZMS 块。"""
        return [r.value for r in self.find_all(tag)
                if isinstance(r.value, ZipBlob)]

    def decompress_bodies(self) -> list[dict]:
        """解压全部 ``ZIPBODYBYTES`` → ``PKBody3``。"""
        out = []
        for b in self.bodies():
            body = b["zip"].decompress_body()
            out.append({
                "pk_body": b["pk_body"],
                "zip": b["zip"],
                "pkbody3": body,
                "data_size": len(body.data),
            })
        return out

    def decompress_octree(self, max_depth: int = 8) -> list[SnapRecord]:
        """解压 ``ZIPOCTREE`` 为嵌套记录树（含 OCTREEBODY 等）。"""
        blobs = self.zip_blobs("ZIPOCTREE")
        if not blobs:
            return []
        return blobs[0].decompress_records(max_depth=max_depth)

    def octree_crdlfld_bytes(self) -> Optional[bytes]:
        """从 ``ZIPOCTREE`` 提取 ``OCTREEBODY`` 内的 CRDL-FLD 字节
        （与 ``*.oct`` 成员字节级一致）。"""
        records = self.decompress_octree(max_depth=8)

        def walk(recs: list[SnapRecord]) -> Optional[bytes]:
            for r in recs:
                if r.tag == "OCTREEBODY":
                    for qb in r.find_all("QUEUEBODY"):
                        for c in qb.children:
                            if (c.tag == "BYTEARRAY"
                                    and isinstance(c.value, bytes)
                                    and b"CRDL-FLD" in c.value[:16]):
                                return c.value
                found = walk(r.children)
                if found is not None:
                    return found
            return None

        return walk(records)

    def decompress_faceting_rules(self, max_depth: int = 12) -> list[SnapRecord]:
        """解压 ``ZIPFACETINGRULES`` 为嵌套记录树。"""
        blobs = self.zip_blobs("ZIPFACETINGRULES")
        if not blobs:
            return []
        return blobs[0].decompress_records(max_depth=max_depth)

    def assembly_tree(self) -> list[dict]:
        """装配树（名称 + 子节点 + 关联 PKBODY_T）。"""

        def walk(rec: SnapRecord) -> dict:
            name = None
            pk = None
            children = []
            node_type = rec.tag
            for c in rec.children:
                if c.tag == "NAMESTRINGW":
                    name = c.value
                elif c.tag in ("PKBODY_T", "PKASSEMBLY_T"):
                    pk = c.value
                elif c.tag in ("ASSEMBLY", "BODY"):
                    children.append(walk(c))
            return {"type": node_type, "name": name, "pk": pk, "children": children}

        return [walk(r) for r in self.find_all("ASSEMBLY")
                if any(p.tag == "TOPASSYSTRUCT" for p in self.records)]

    def face_groups(self) -> list[dict]:
        """所有命名的面组（FACEGROUPW）：所属体 + 面数等。"""
        out = []
        for fg in self.find_all("FACEGROUPW"):
            entry = {}
            for c in fg.children:
                if c.tag == "NAMESTRINGW":
                    entry["name"] = c.value
                elif c.tag == "FACEARRAYSIZE":
                    entry.setdefault("face_array_sizes", []).append(c.value)
                elif c.tag == "COLOR":
                    entry["color"] = c.value
                elif c.tag == "COLORINDEX":
                    entry["color_index"] = c.value
                elif c.tag == "MESHENABLED":
                    entry["mesh_enabled"] = c.value
            if entry:
                out.append(entry)
        return out

    def meshing_groups(self) -> list[dict]:
        """BSGSEX 中的网格组参数摘要。"""
        out = []
        for grp in self.find_all("BODYSHAPEGROUP"):
            entry = {"name": None, "parent": None, "octree_param": {}}
            for c in grp.children:
                if c.tag == "STRINGW":
                    if entry["name"] is None:
                        entry["name"] = c.value
                    elif entry["parent"] is None:
                        entry["parent"] = c.value
                elif c.tag == "OCTREEPARAM":
                    op = c.first("OCTREESIZEBYPRM")
                    if op:
                        vals = [x.value for x in op.children
                                if x.tag in ("DOUBLE", "INTEGER")]
                        entry["octree_param"]["size_by_param"] = vals
                    bal = c.first("OCTREEBALANCING")
                    if bal:
                        entry["octree_param"]["balancing"] = [
                            x.value for x in bal.children]
                    restr = []
                    for rr in c.find_all("OCTREERESTRRGN"):
                        info = {}
                        ints = [x.value for x in rr.children if x.tag == "INTEGER"]
                        nm = rr.first("STRING")
                        info["integers"] = ints
                        if nm:
                            info["region"] = nm.value
                        restr.append(info)
                    if restr:
                        entry["octree_param"]["restrictions"] = restr
            out.append(entry)
        return out
