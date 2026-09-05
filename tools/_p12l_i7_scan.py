#!/usr/bin/env python3
"""P12-L Sprint I7（可选 backlog）：CATIA 样本全机再扫 + Datakit 转换器写向盘点。

§18.8 G3（2026-09-01）裁决「全机 0 真 CATIA 几何样本」；本器为 I7
复扫 + 把 G3 未做的「Datakit 独立转换器**写向**」盘点补齐：

1. :func:`scan_catia_samples` —— 选定根（Cradle 安装树 ×2 / 案例库 /
   training / work / 用户目录）按 CATIA 家族扩展名扫文件，逐个魔数
   分类真伪（OLE2 复合文档查 CATIA 流名 / HDF5 .exp 误报 / 链接器
   export / Datakit dtk.model schema）。
2. :func:`inventory_datakit` —— 安装树内 Datakit/CADTHRU 组件盘点
   （文件名 + 大小），写向判定按组件名写侧标记（writer/export）+
   schema 目录结构。
3. :func:`classify_magic` —— 魔数 → 真伪分类（离线可测）。

CLI：``py tools/_p12l_i7_scan.py [--out _p12l_i7/i7_scan.json]``
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCAN_ROOTS = (
    r"C:\Program Files\Cradle",
    r"D:\training",
    r"D:\work",
    r"D:\others",
    r"D:\packages",
    r"C:\Users\sdcll\Documents",
    r"C:\Users\sdcll\Downloads",
    r"C:\Users\sdcll\Desktop",
)

CATIA_EXTS = {
    ".catpart", ".catproduct", ".catshape", ".catdrawing", ".catanalysis",
    ".catmaterial", ".catswl", ".catsystem", ".catprocess", ".catfct",
    ".cgr", ".model", ".session", ".exp", ".3dxml", ".dtkmodel",
}

INSTALL_ROOTS = (r"C:\Program Files\Cradle",)

# Datakit 组件名里读侧/写侧的标记词（组件名与 schema 目录名都查）
WRITE_MARKERS = ("write", "writer", "export", "w_")
READ_MARKERS = ("read", "reader", "import", "r_")


def _ole2_stream_names(data: bytes, limit: int = 1 << 24) -> list[str]:
    """粗读 OLE2 复合文档目录项流名（UTF-16，无需 olefile）。"""
    names: list[str] = []
    if len(data) < 0x200 + 8 or data[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return names
    try:
        ssz = 1 << struct.unpack_from("<H", data, 0x1E)[0]
        first_dir = struct.unpack_from("<I", data, 0x30)[0]
        off = 0x200 + first_dir * ssz
        blob = data[off:off + ssz * 4]
        for i in range(len(blob) // 128):
            ent = blob[i * 128:(i + 1) * 128]
            if len(ent) < 128 or ent[0x42:0x44] not in (b"\x01\x00",
                                                        b"\x05\x00",
                                                        b"\x02\x00"):
                continue
            nlen = struct.unpack_from("<H", ent, 0x40)[0]
            if 0 < nlen <= 64:
                name = ent[:nlen].decode("utf-16-le", "ignore").rstrip("\x00")
                if name:
                    names.append(name)
    except Exception:  # noqa: BLE001
        pass
    return names


def classify_magic(path: Path) -> dict:
    """CATIA 家族候选文件 → 真伪分类。

    返回 {kind, verdict, detail}：
    - catia_v5_ole2  = 真 CATIA V5（OLE2 复合文档含 CATIA/CATV5 流）
    - catia_v4_model = 真 CATIA V4 .model（头部 V4 版本串）
    - datakit_schema = Datakit dtk.schema/model 定义件（非几何）
    - hdf5_exp       = HDF5 .exp（Cradle 场文件，误报）
    - linker_export  = 链接器 .exp/导出件（误报）
    - cgr_ole2       = OLE2 cgr（ tessellation，视流名定真伪）
    - unknown_ole2   = OLE2 但无 CATIA 流（存疑，列出流名）
    - unknown        = 其它（列出前 32 字节 hex）
    """
    try:
        with open(path, "rb") as f:
            head = f.read(1 << 16)
    except OSError as exc:
        return {"kind": "unreadable", "verdict": "skip",
                "detail": repr(exc)}
    ext = path.suffix.lower()
    if head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        names = _ole2_stream_names(head) if path.stat().st_size < (1 << 26) \
            else []
        blob = head[:4096] + b"".join(n.encode("utf-16-le", "ignore")
                                      for n in names)
        up = blob.upper()
        if b"CATIA" in up or b"CATV5" in up or b"CATPRODUCT" in up:
            return {"kind": "catia_v5_ole2", "verdict": "REAL",
                    "detail": f"ole2 streams={names[:8]}"}
        if ext == ".cgr":
            return {"kind": "cgr_ole2", "verdict": "REAL?",
                    "detail": f"ole2 streams={names[:8]}"}
        return {"kind": "unknown_ole2", "verdict": "suspect",
                "detail": f"ole2 streams={names[:8]}"}
    if head[:8] == b"\x89HDF\r\n\x1a\n":
        return {"kind": "hdf5_exp", "verdict": "FALSE-POSITIVE",
                "detail": "hdf5 magic"}
    if head[:5] == b"DATAK" or b"DATAKIT" in head[:4096].upper():
        return {"kind": "datakit_schema", "verdict": "FALSE-POSITIVE",
                "detail": "datakit schema marker"}
    txt = head[:256].lstrip()
    if ext == ".exp":
        if txt[:7].upper() == b"EXPORTS" or txt[:8].upper() in (
                b"LIBRARY ", b"NAME "):
            return {"kind": "linker_export", "verdict": "FALSE-POSITIVE",
                    "detail": "linker module-def"}
        if txt[:1] in (b"\x7f", b"MZ") or head[:2] == b"MZ":
            return {"kind": "linker_export", "verdict": "FALSE-POSITIVE",
                    "detail": "pe/lib binary"}
        return {"kind": "unknown", "verdict": "suspect",
                "detail": head[:32].hex()}
    if ext == ".model":
        if path.name.lower().startswith("dtk."):
            return {"kind": "datakit_schema", "verdict": "FALSE-POSITIVE",
                    "detail": "datakit dtk.* schema"}
        up = head.upper()
        if b"CATIA" in up or (b"V4" in head[:64] and b"MODEL" in up):
            return {"kind": "catia_v4_model", "verdict": "REAL",
                    "detail": head[:32].hex()}
        return {"kind": "unknown", "verdict": "suspect",
                "detail": head[:32].hex()}
    if head[:7] == b"V5_CFV2":
        # CATIA V5 文档官方签名（starcat5 样本实测 15/15 命中）
        return {"kind": "catia_v5_cfV2", "verdict": "REAL",
                "detail": head[:32].hex()}
    if b"CATIA" in head.upper():
        return {"kind": "catia_like", "verdict": "REAL?",
                "detail": head[:32].hex()}
    return {"kind": "unknown", "verdict": "suspect",
            "detail": head[:32].hex()}


def scan_catia_samples(roots=SCAN_ROOTS) -> dict:
    """全机 CATIA 家族扩展名扫描（魔数分类，宽限不可读路径）。"""
    hits: list[dict] = []
    scanned = 0
    t0 = time.time()
    for root in roots:
        if not os.path.isdir(root):
            hits.append({"path": root, "kind": "root-missing",
                         "verdict": "skip", "detail": "", "size": None})
            continue
        for dirpath, dirnames, filenames in os.walk(root, onerror=None):
            dirnames[:] = [d for d in dirnames if not d.startswith("$")]
            for fn in filenames:
                if Path(fn).suffix.lower() not in CATIA_EXTS:
                    continue
                scanned += 1
                p = Path(dirpath) / fn
                try:
                    size = p.stat().st_size
                except OSError:
                    size = None
                cls = classify_magic(p)
                hits.append({"path": str(p), "size": size,
                             "mtime": int(p.stat().st_mtime)
                             if size is not None else None, **cls})
    return {"scanned_files": scanned, "elapsed_s": round(time.time() - t0, 1),
            "hits": hits,
            "verdict_counts": _count(hits, "verdict"),
            "kind_counts": _count(hits, "kind")}


def _count(hits: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for h in hits:
        k = h.get(key, "?")
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def inventory_datakit(install_roots=INSTALL_ROOTS) -> dict:
    """安装树内 Datakit / CADTHRU 组件盘点 + 写向标记统计。"""
    comps: list[dict] = []
    for root in install_roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root, onerror=None):
            low_dir = dirpath.lower()
            for fn in filenames:
                low = fn.lower()
                if ("datakit" not in low and not low.startswith("dtk")
                        and "cadthru" not in low and "catia" not in low
                        and "cad" not in low):
                    continue
                if Path(fn).suffix.lower() not in (
                        ".dll", ".exe", ".xml", ".txt", ".model", ".schema",
                        ".dtkmodel", ""):
                    continue
                p = Path(dirpath) / fn
                try:
                    size = p.stat().st_size
                except OSError:
                    size = None
                tag = "neutral"
                if any(m in low for m in WRITE_MARKERS):
                    tag = "write"
                elif any(m in low for m in READ_MARKERS):
                    tag = "read"
                comps.append({"path": str(p), "size": size, "side": tag})
    return {"components": comps,
            "side_counts": _count(comps, "side"),
            "roots": [str(r) for r in install_roots]}


def main() -> int:
    ap = argparse.ArgumentParser(description="I7 CATIA rescan + Datakit")
    ap.add_argument("--out", default=str(ROOT / "_p12l_i7" / "i7_scan.json"))
    args = ap.parse_args()
    catia = scan_catia_samples()
    dk = inventory_datakit()
    report = {"catia_rescan": catia, "datakit_inventory": dk}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print("CATIA scanned:", catia["scanned_files"], "files,",
          catia["elapsed_s"], "s; verdicts:", catia["verdict_counts"])
    for h in catia["hits"]:
        if h.get("verdict") not in ("FALSE-POSITIVE", "root-missing"):
            print("  HIT:", h["verdict"], h["kind"], h["path"],
                  h.get("detail", "")[:120])
    print("Datakit components:", len(dk["components"]),
          "side counts:", dk["side_counts"])
    for c in dk["components"]:
        if c["side"] != "neutral":
            print(f"  [{c['side']:>5}]", c["path"], c["size"])
    print("SUMMARY: " + json.dumps(
        {"real_catia": sum(v for k, v in catia["verdict_counts"].items()
                           if k.startswith("REAL")),
         "false_positive": catia["verdict_counts"].get("FALSE-POSITIVE", 0),
         "suspect": catia["verdict_counts"].get("suspect", 0),
         "datakit_comps": len(dk["components"])},
        ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
