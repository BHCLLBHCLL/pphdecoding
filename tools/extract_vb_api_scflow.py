#!/usr/bin/env python3
"""从 scFLOW 官方 VB 接口手册 HTML 提取 scFLOWpre/Kicker 类目录。

源：CradleCFD2025.2 ``Manuals/scFLOW/HTML/VB_Interface_eng``（MediaWiki
导出）。每个方法在 HTML 中为::

    <h3><span class="mw-headline" id="Name">Name</span></h3>
    <dl><dd>retval=doc.OpenProject(path, flag)</dd></dl>
    <dl><dd><table class="vbmethod"> ... </table></dd></dl>

表内行：``[Explanation]``（说明）、``[Argument]``（参数，每参数一行：
``(VARIANT) name`` / ``:`` / 描述）、``[Return Value]``（返回值）。

输出 ``schemas/vb_api_catalog.json``：类 → 方法/属性 → 签名、说明、
参数表、返回值。该目录是 typed COM 桥（``scflowpre_api.py``）与
VBS 生成器共用的权威 API 面。

用法::

    python tools/extract_vb_api_scflow.py            # 全量提取
    python tools/extract_vb_api_scflow.py --list     # 仅类清单统计
"""

from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANUAL = Path(r"C:\Program Files\Cradle\CradleCFD2025.2\Manuals\scFLOW"
              r"\HTML\VB_Interface_eng")
OUT = ROOT / "schemas" / "vb_api_catalog.json"

PROGID = "scFLOWpre_Bx64net.Application.2025"

# scFLOWpre Preprocessor 类（含 150+ Cond* 子类）+ Kicker 三类。
# 不提取 Post/Solver/Monitor/scConverter/LFileView/SmartBlades（非本仓域）。
_FILE_PATTERNS = [
    ("Scf_vb_Preprocessor_*_Class.html", ""),
    ("Scf_vb_Preprocessor_*_class.html", ""),
    ("Scf_vb_Kicker_Application_class.html", "Kicker."),
    ("Cmn_vb_Kicker_ApplicationLaunchSetting_class.html", "Kicker."),
    ("Cmn_vb_Kicker_LicenseStatus_class.html", "Kicker."),
]
# 手册文件名中类名的正则捕获组
_NAME_RE = re.compile(r"^Scf_vb_Preprocessor_(.+?)_[Cc]lass(?:_Supplement)?\.html$"
                      r"|^(?:Scf|Cmn)_vb_Kicker_(.+?)_[Cc]lass\.html$")

_H2 = re.compile(r'<h2><span class="mw-headline"[^>]*>([^<]+)</span></h2>')
_H3 = re.compile(r'<h3><span class="mw-headline"[^>]*>([^<]+)</span></h3>')
_TAG = re.compile(r"<[^>]+>")
_TR = re.compile(r"<tr>(.*?)</tr>", re.S)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
# 手册两种表格并存：Utility 等类用 <table class="vbmethod">，Doc 等类用裸 <table>
_TABLE = re.compile(
    r'<dl><dd><table(?: class="vbmethod")?>(.*?)</table></dd></dl>', re.S)
_SIGNATURE = re.compile(r"<dl><dd>([^<]*(?:<(?!/?dd)[^<]*)*)</dd></dl>")
_NOTE = re.compile(r"<dl><dd><b>\(Note\)</b>(.*?)</dd></dl>", re.S)
_ARG_CELL = re.compile(r"^\(([^)]+)\)\s*(.+)$")


def _strip(s: str) -> str:
    s = _TAG.sub(" ", s)
    s = htmllib.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_method_block(body: str) -> dict:
    """解析一个 h3 方法块：签名 + vbmethod 表 + (Note)。"""
    entry: dict = {}
    m = _SIGNATURE.search(body)
    if m:
        entry["signature"] = _strip(m.group(1))
    nm = _NOTE.search(body)
    if nm:
        entry["note"] = _strip(nm.group(1))
    tm = _TABLE.search(body)
    if not tm:
        return entry
    mode = None
    for row in _TR.findall(tm.group(1)):
        cells = [_strip(c) for c in _TD.findall(row)]
        if not cells:
            continue
        head = cells[0]
        if "[Explanation]" in head:
            mode = "expl"
            entry["explanation"] = " ".join(c for c in cells[1:] if c)
        elif "[Argument]" in head:
            mode = "arg"
            if len(cells) >= 4:
                _push_arg(entry, cells[1], cells[3])
        elif "[Return Value]" in head:
            mode = "ret"
            if len(cells) >= 4:
                _push_arg(entry, cells[1], cells[3], ret=True)
        elif not head and mode == "arg" and len(cells) >= 3:
            # 续行：[空] [(VARIANT) name] [:] [desc]
            _push_arg(entry, cells[0] or cells[1], cells[-1])
    return entry


def _push_arg(entry: dict, name_cell: str, desc: str, ret: bool = False) -> None:
    name_cell = (name_cell or "").strip()
    if not name_cell:
        return
    am = _ARG_CELL.match(name_cell)
    item = {
        "type": am.group(1) if am else "",
        "name": (am.group(2) if am else name_cell).strip(),
        "description": (desc or "").strip(),
    }
    if ret:
        entry["return"] = item
    else:
        entry.setdefault("arguments", []).append(item)


def _split_sections(text: str):
    """yield (section_mode, name, block) —— 按 h2(Method/Property)/h3 切分。"""
    marks: list[tuple[int, str, str]] = []  # (pos, kind, text)
    for m in _H2.finditer(text):
        marks.append((m.start(), "h2", m.group(1).strip()))
    for m in _H3.finditer(text):
        marks.append((m.start(), "h3", m.group(1).strip()))
    marks.sort()
    mode = None
    for i, (pos, kind, label) in enumerate(marks):
        if kind == "h2":
            if label in ("Method", "Property"):
                mode = label.lower()
            continue
        if mode is None:
            continue  # Method 区之前的内容（类概述等）
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        yield mode, label, text[pos:end]


_CLASS_EXPL = re.compile(r"<h1>([^<]+) Class</h1>.*?<table>(.*?)</table>",
                         re.S)
_INSTANCE = re.compile(r"Set (\w+)\s*=\s*(\w+)\.(\w+)\(([^)]*)\)")


def _class_info(text: str) -> dict:
    """类级信息：说明、实例获取示例、Condition 基类继承推断。"""
    info: dict = {}
    m = _CLASS_EXPL.search(text)
    if m:
        rows = _TR.findall(m.group(2))
        for row in rows:
            cells = [_strip(c) for c in _TD.findall(row)]
            if cells and "[Explanation]" in cells[0] and len(cells) > 1:
                info["explanation"] = cells[1]
                if "methods of Condition class can be used" in cells[1]:
                    info["inherits"] = "Condition"
                break
    inst = _INSTANCE.search(text)
    if inst:
        info["instance"] = f"Set {inst.group(1)} = {inst.group(2)}.{inst.group(3)}({inst.group(4)})"
    return info


def extract_class(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    out: dict = {"file": path.name}
    out.update(_class_info(text))
    out["methods"] = {}
    out["properties"] = {}
    for mode, name, block in _split_sections(text):
        entry = _parse_method_block(block)
        target = out["methods"] if mode == "method" else out["properties"]
        target[name] = entry
    if not out["properties"]:
        del out["properties"]
    return out


def class_files() -> list[tuple[str, Path]]:
    """[(类名, 文件)]，按手册文件名规约排序。"""
    seen: dict[str, Path] = {}
    for pattern, prefix in _FILE_PATTERNS:
        for path in sorted(MANUAL.glob(pattern)):
            m = _NAME_RE.match(path.name)
            if not m:
                continue
            name = prefix + (m.group(1) or m.group(2))
            seen.setdefault(name, path)
    return sorted(seen.items())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", action="store_true",
                    help="仅打印类清单与统计，不写 JSON")
    args = ap.parse_args(argv)

    if not MANUAL.is_dir():
        print(f"manual not found: {MANUAL}", file=sys.stderr)
        return 2
    files = class_files()
    if not files:
        print("no class file matched", file=sys.stderr)
        return 2

    catalog = {
        "source": "CradleCFD2025.2 Manuals scFLOW HTML VB_Interface_eng",
        "progid": PROGID,
        "extracted": date.today().isoformat(),
        "classes": {},
    }
    total = 0
    for name, path in files:
        info = extract_class(path)
        catalog["classes"][name] = info
        total += len(info["methods"]) + len(info.get("properties", {}))
        if args.list:
            print(f"{name:42s} methods={len(info['methods']):4d} "
                  f"props={len(info.get('properties', {})):3d}  {path.name}")

    if args.list:
        print(f"== {len(files)} classes, {total} members")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    n_cond = sum(1 for n in catalog["classes"] if n.startswith("Cond"))
    print(f"wrote {OUT}")
    print(f"classes={len(catalog['classes'])} "
          f"(Cond*={n_cond}) members={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
