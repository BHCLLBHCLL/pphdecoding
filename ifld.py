#!/usr/bin/env python3
"""iFLD（CRDL-PST 插值源场文件）解析。

iFLD = scPOST 的插值源文件（Samples_POST/iFLD，如 minimumHexa.iFLD /
scSTREAM_example1_100.iFLD），把求解器结果网格上的场量打包成插值用
采样数据。容器与 CRDL-FLD 不同：

* 魔数 "CRDL-PST"（8 字节 ASCII，前后各带 大端 I4=8 长度）；
* 随后 16 字节头字为 小端 u32：目录区大小（恒 0x400=1024）、
  条目数 n、版本号 0x01321AF1、保留 0；
* 偏移 32 起为目录（TOC）：n 条 32 字节记录
  [名字 16B][偏移 u64 LE][大小 u64 LE]，名字如 FILEINFO / BASE /
  APX / SURFBLOCK1 / SURFHASH / ELEMBLOCK1 / ELEMHASH / ELEMINFO /
  NODEINFO / VAR_MS_* / VAR_OS_* / VAR_MV_* / VAR_OV_*。

已解析的记录：

* FILEINFO = 容器头自身的副本（20 字节）；
* BASE / APX = 目录条目序列（与 TOC 相同格式），BASE+APX 拼接即完整目录；
* VAR_MS_* / VAR_OS_* / VAR_MV_* / VAR_OV_* = 小端 f32 数组
  （example1_100：MS=70 值 = 23 块 x [min, mean, max] 行主序统计三元组 + 1，
  OS=21145 个插值采样值，MV/OV 为矢量分量）；无数据处填哨兵 0x60AD78EC
  （LE u32，f32 约 1.0e20），另有 NaN 与空块垃圾大值填充；
* SURFBLOCK1 / ELEMBLOCK1（面/单元采样块）、SURFHASH / ELEMHASH（哈希桶）、
  ELEMINFO / NODEINFO（索引）为插值加速结构，内容为哈希/索引编码，
  本模块只按原始字节暴露并给出统计，不做字段级解码。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

MAGIC = b"CRDL-PST"
TOC_OFFSET = 32
ENTRY_SIZE = 32

# 无数据哨兵（LE u32 0x60AD78EC -> f32 约 1.0e20，SURT/HTFX/VECT 等未启用
# 场量整段填充该值）
NODATA_U32 = 0x60AD78EC


@dataclass
class IfldRecord:
    name: str
    offset: int
    size: int


def parse_toc(data, offset: int = TOC_OFFSET, count: Optional[int] = None,
              limit: int = 4096) -> list:
    """解析 32 字节目录条目流（可用于文件 TOC 与 BASE/APX 载荷）。"""
    if count is None:
        count = limit
    out = []
    pos = offset
    for _ in range(count):
        if pos + ENTRY_SIZE > len(data):
            break
        raw = bytes(data[pos:pos + 16])
        if not raw.strip(b"\x00"):
            break
        name = raw.decode("ascii", errors="replace").rstrip("\x00 ")
        off, size = struct.unpack("<QQ", data[pos + 16:pos + 32])
        if name == "" and off == 0 and size == 0:
            break
        out.append(IfldRecord(name, off, size))
        pos += ENTRY_SIZE
    return out


def crdlfld_open(filepath):
    """返回 (bytes-like, handles)；>512 MiB 用 mmap（同 crdlfld）。"""
    import mmap as _mmap
    size = Path(filepath).stat().st_size
    if size <= 512 * 1024 * 1024:
        with open(filepath, "rb") as f:
            return f.read(), None
    f = open(filepath, "rb")
    mm = _mmap.mmap(f.fileno(), 0, access=_mmap.ACCESS_READ)
    return mm, (mm, f)


class IfldFile:
    """CRDL-PST 插值源场文件。"""

    def __init__(self, filepath, data, words, records):
        self.filepath = filepath
        self.data = data
        self.words = words          # {toc_size, n_entries, version, reserved}
        self.records = records      # list[IfldRecord]

    @classmethod
    def load(cls, filepath):
        data, handles = crdlfld_open(filepath)
        if bytes(data[0:4]) != b"\x00\x00\x00\x08" \
                or bytes(data[4:12]) != MAGIC:
            raise ValueError(f"{filepath}: 不是 CRDL-PST (iFLD) 文件")
        words = {
            "toc_size": struct.unpack("<I", data[16:20])[0],
            "n_entries": struct.unpack("<I", data[20:24])[0],
            "version": struct.unpack("<I", data[24:28])[0],
            "reserved": struct.unpack("<I", data[28:32])[0],
        }
        records = parse_toc(data, TOC_OFFSET, words["n_entries"])
        return cls(filepath, data, words, records)

    def record(self, name: str):
        for r in self.records:
            if r.name == name:
                return r
        return None

    def payload(self, name: str):
        r = self.record(name)
        if r is None:
            return None
        return bytes(self.data[r.offset:r.offset + r.size])

    def var_names(self):
        return [r.name for r in self.records if r.name.startswith("VAR_")]

    def var_array(self, name: str):
        """VAR_* 载荷 -> 小端 f32 数组（大小非 4 倍时返回 None）。"""
        p = self.payload(name)
        if p is None or len(p) % 4:
            return None
        return np.frombuffer(p, dtype="<f4")

    def var_stats(self, name: str):
        """VAR_* 载荷统计（剔除无数据哨兵后）。"""
        a = self.var_array(name)
        if a is None:
            return None
        bits = a.view(np.uint32)
        # 无效填充：哨兵 0x60AD78EC、NaN/Inf、以及空块的垃圾大值
        # （|v|>1e12；实测空块填充可达 1e14..1e21 量级）
        valid = ((bits != NODATA_U32) & np.isfinite(a)
                 & (np.abs(a) < 1e12))
        n_nodata = int(a.size - int(valid.sum()))
        vals = a[valid].astype(np.float64)
        stats = {"count": int(a.size), "nodata": n_nodata}
        if vals.size:
            stats.update({
                "min": float(vals.min()),
                "max": float(vals.max()),
                "mean": float(vals.mean()),
                "p50": float(np.median(vals)),
            })
        return stats

    def embedded_toc(self):
        """BASE/APX 载荷内嵌的目录（文件 TOC 的分片副本）。

        BASE 与 APX 的记录把 32 字节条目流拦腰截断且接缝处缺字节
        （minimumHexa 缺 2 字节、example1_100 缺 9 字节），拼接后条目
        会错位。此处尽力解析，仅作完整性参考，以文件 TOC（偏移 32）
        为准。
        """
        joined = b""
        for name in ("BASE", "APX"):
            p = self.payload(name)
            if p is not None:
                joined += p
        return parse_toc(joined, 0, None)


def _fmt_stats(s: dict) -> str:
    if s is None:
        return "-"
    if "min" not in s:
        return f"n={s['count']} 全为无数据哨兵"
    return (f"n={s['count']} min={s['min']:.6g} max={s['max']:.6g} "
            f"mean={s['mean']:.6g} p50={s['p50']:.6g} nodata={s['nodata']}")


def summarize_ifld(filepath) -> str:
    """iFLD 摘要（头 + 目录表 + 各记录概况 + VAR 场量统计）。"""
    f = IfldFile.load(filepath)
    lines = [f"iFLD: {Path(filepath).name} ({len(f.data):,} bytes)"]
    w = f.words
    lines.append(f"目录区 {w['toc_size']} B / {w['n_entries']} 条 / "
                 f"版本 0x{w['version']:08X}")
    lines.append("记录:")
    for r in f.records:
        if r.name.startswith("VAR_"):
            lines.append(f"  {r.name:16s} @{r.offset:8d} sz={r.size:8d}"
                         f"  f32LE {_fmt_stats(f.var_stats(r.name))}")
        elif r.name in ("FILEINFO", "BASE", "APX"):
            lines.append(f"  {r.name:16s} @{r.offset:8d} sz={r.size:8d}"
                         f"  (目录/头副本)")
        else:
            lines.append(f"  {r.name:16s} @{r.offset:8d} sz={r.size:8d}"
                         f"  (插值索引块，原始字节)")
    emb = f.embedded_toc()
    names_toc = [r.name for r in f.records]
    names_emb = [r.name for r in emb]
    if emb:
        n_ok = sum(1 for a, b in zip(names_toc, names_emb) if a == b)
        lines.append(f"BASE+APX 内嵌目录 {len(emb)} 条：前 {n_ok} 名与 "
                     f"文件 TOC 一致（分片副本，以 TOC 为准）")
    os_names = [n for n in f.var_names() if n.startswith("VAR_OS_")]
    ms_names = [n for n in f.var_names() if n.startswith("VAR_MS_")]
    if os_names and ms_names:
        os0 = f.var_stats(os_names[0])
        ms0 = f.var_stats(ms_names[0])
        lines.append(f"采样规模：MS（基准/统计）= {ms0['count']} 值，"
                     f"OS（插值采样）= {os0['count']} 值")
    return "\n".join(lines)
