#!/usr/bin/env python3
"""R4-3 面板状态存储审计（静态扫描，逐面板给出 store + file:line 证据）。

目的：GUI 面板「参数可编辑 ≠ 参数生效」的根因是**状态住在哪个存储**。
本工具把每个面板类（nav_panels.py 的 *Body / *Dialog）按 5 个存储归类：

  session     仅内存 ctx["session"]（重启即失）
  xml         main.xml（落盘）
  xenv        main.xenv（落盘）
  prp         main.prp（落盘）
  snapshot    main.sctsnapshot（落盘，写通道见 sctsnapshot.SctSnapshot.serialize）

分类口径（保守）：只要出现该存储的**写标记**（*_dirty、["store"] =、
setdefault("session"、serialize(）即记 written；只出现读取则记 read。
扫描是静态启发式 —— 每条判定都带 file:line 证据，便于人工复核与再生。

用法::

    python tools/panel_store_audit.py            # 打印表 + 写 docs/PANEL_STORE_MAP.md
    python tools/panel_store_audit.py --json schemas/panel_store_map.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console_utf8  # noqa: E402

console_utf8.enable()

NAV = ROOT / "nav_panels.py"
OUT_MD = ROOT / "docs" / "PANEL_STORE_MAP.md"
OUT_JSON = ROOT / "schemas" / "panel_store_map.json"

#: store -> (读标记, 写标记) 的正则（写标记命中即判 written）
STORES: dict[str, tuple[list[str], list[str]]] = {
    "session": (
        [r"session"],
        [r'setdefault\("session"', r'\["session"\]\s*=', r'get\("session"\)\s*\]',
         r'\["session"\]\["'],
    ),
    "xml": (
        [r"xml"],
        # 本仓约定：动过 xml 就置 xml_dirty（见 write_condition_to_xml /
        # _set_flow_bc）。泛化的 .append(/.set( 会误判布局代码，不用。
        [r"xml_dirty", r"ET\.SubElement"],
    ),
    "xenv": (
        [r"xenv"],
        # panel_xenv_set 是 R4-4 的统一落盘口：面板自身不出现 xenv_dirty，
        # 但语义上就是写 main.xenv（否则审计会把落盘后的面板仍判 memory_only）。
        [r"xenv_dirty", r"panel_xenv_set", r'\["xenv"\]\s*='],
    ),
    "prp": (
        [r"\bprp\b"],
        [r"prp_dirty", r'\["prp"\]\s*='],
    ),
    "snapshot": (
        [r"sctsnapshot", r"\bsnapshot\b"],
        [r"snapshot_dirty", r"\.serialize\("],
    ),
}

CLASS_RE = re.compile(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*:")

#: 顶层块边界：下一个 class / def / 模块级赋值 —— 否则类块会吞掉紧随其后的
#: 模块级函数（实测 OptionNavBody 吞到 condition_registry_cached 造成误判）。
BOUNDARY_RE = re.compile(
    r"^(class\s|def\s|[A-Za-z_][A-Za-z0-9_]*\s*[:=])")


def class_blocks(path: Path) -> list[dict]:
    """把模块切成 class 块（start/end 行号 + 源文本）。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    heads: list[tuple[int, str, str]] = []
    for i, ln in enumerate(lines):
        m = CLASS_RE.match(ln)
        if m:
            heads.append((i, m.group(1), m.group(2)))
    out: list[dict] = []
    for k, (i, name, bases) in enumerate(heads):
        # 先看下一个顶层边界；类之间还有模块级 def/赋值时以边界为准
        nxt = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        for j in range(i + 1, nxt):
            if BOUNDARY_RE.match(lines[j]):
                nxt = j
                break
        end = nxt
        out.append({"name": name, "bases": bases, "start": i + 1, "end": end,
                    "lines": lines[i:end]})
    return out


def _first_hit(hay: list[tuple[int, str]], pats: list[str]):
    """返回第一个命中（行号, 原文, store 模式）。"""
    for pat in pats:
        rx = re.compile(pat)
        for lineno, text in hay:
            if rx.search(text):
                return (lineno, text.strip()[:120], pat)
    return None


def audit_class(block: dict) -> dict:
    hay = [(block["start"] + off, t)
           for off, t in enumerate(block["lines"])]
    evidence = []
    written: list[str] = []
    read: list[str] = []
    for store, (read_pats, write_pats) in STORES.items():
        w = _first_hit(hay, write_pats)
        if w is not None:
            written.append(store)
            evidence.append({"store": store, "mode": "write", "line": w[0],
                             "text": w[1]})
        r = _first_hit(hay, read_pats)
        if r is not None:
            read.append(store)
            evidence.append({"store": store, "mode": "read", "line": r[0],
                             "text": r[1]})
    disk = [s for s in written if s != "session"]
    if disk:
        persistence = "persisted:" + ",".join(sorted(disk))
    elif "session" in written:
        persistence = "memory_only"
    elif read:
        persistence = "read_only"
    else:
        persistence = "none"
    return {"panel": block["name"], "bases": block["bases"],
            "lines": [block["start"], block["end"]],
            "stores_read": sorted(set(read)),
            "stores_written": sorted(set(written)),
            "persistence": persistence, "evidence": evidence}


def page_key_map() -> dict[str, list[str]]:
    """BODY_CLASSES 反查：panel 类 -> 页面 key 列表。"""
    src = NAV.read_text(encoding="utf-8")
    m = re.search(r"BODY_CLASSES[^=]*=\s*\{(.*?)\n\}", src, re.S)
    if not m:
        return {}
    out: dict[str, list[str]] = {}
    for key, cls in re.findall(
            r'"([^"]+)"\s*:\s*([A-Za-z_][A-Za-z0-9_]*)', m.group(1)):
        out.setdefault(cls, []).append(key)
    return out


def build() -> dict:
    blocks = [b for b in class_blocks(NAV)
              if b["name"].endswith(("Body", "Dialog"))
              or b["name"] in ("GenericCondBody",)]
    keymap = page_key_map()
    panels = []
    for b in blocks:
        rec = audit_class(b)
        rec["page_keys"] = sorted(keymap.get(rec["panel"], []))
        panels.append(rec)
    counts: dict[str, int] = {}
    for p in panels:
        head = p["persistence"].split(":")[0]
        counts[head] = counts.get(head, 0) + 1
    return {"source": str(NAV.relative_to(ROOT)).replace(chr(92), "/"),
            "panels": panels, "counts": counts}


def to_markdown(data: dict) -> str:
    lines = ["# 面板状态存储映射（R4-3 静态审计）",
             "",
             "> 由 tools/panel_store_audit.py 生成（静态启发式，逐条带 file:line 证据）。",
             "> 口径：session=仅内存；xml/xenv/prp/snapshot=落盘存储。",
             "> 源：" + data["source"] + "（共 " + str(len(data["panels"])) + " 个面板类）",
             "",
             "## 汇总",
             "",
             "| 分类 | 面板数 |",
             "|---|---|"]
    for k, v in sorted(data["counts"].items(), key=lambda kv: -kv[1]):
        lines.append("| " + k + " | " + str(v) + " |")
    lines += ["", "## 明细", "",
              "| 面板 | 页面 key | 判类 | 读 | 写 | 证据（首个写/读命中） |",
              "|---|---|---|---|---|---|"]
    for p in sorted(data["panels"], key=lambda x: (x["persistence"], x["panel"])):
        ev = "; ".join(e["store"] + ":" + e["mode"] + "@L" + str(e["line"])
                       for e in p["evidence"][:3])
        lines.append("| " + p["panel"] + " | " + (", ".join(p["page_keys"]) or "-")
                     + " | " + p["persistence"] + " | "
                     + (", ".join(p["stores_read"]) or "-") + " | "
                     + (", ".join(p["stores_written"]) or "-") + " | " + ev + " |")
    lines += ["", "## 落盘候选（R4-4 用）", ""]
    pers = [p for p in data["panels"] if p["persistence"].startswith("persisted")]
    if not pers:
        lines.append("（无：所有面板都只写 session）")
    for p in pers:
        lines.append("* " + p["panel"] + " -> " + p["persistence"] + "，页面 key "
                     + (", ".join(p["page_keys"]) or "-"))
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R4-3 面板状态存储审计")
    ap.add_argument("--json", type=Path, default=OUT_JSON)
    ap.add_argument("--md", type=Path, default=OUT_MD)
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)
    data = build()
    print("[r4-3] 面板类 " + str(len(data["panels"])) + " 个：",
          json.dumps(data["counts"], ensure_ascii=False))
    for p in data["panels"]:
        if p["persistence"].startswith("persisted"):
            print("   " + p["panel"] + " -> " + p["persistence"])
    if not args.no_write:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(to_markdown(data), encoding="utf-8")
        print("[r4-3] 写入 " + str(args.json.name) + " / " + str(args.md.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
