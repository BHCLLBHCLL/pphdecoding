#!/usr/bin/env python3
"""解析 SCTpre 英文帮助 HTML（184 页）→ 条件元数据 + 与 Cond\* 交叉核对。

数据源：``Programs_x64\\HTML_STpre_Eng\\*.html``（每页对应一个条件/参数
对话框：``<TITLE>[Topic]</TITLE>`` + ``<H3>`` 标题 + 简介 + ``<B>[术语]``
列表 + 参数表 ``<TABLE>``）。

产出 ``schemas/cond_html_meta.json``：

* ``pages`` —— 每页 ``{file, title, intro, terms, params}``（params 来自
  表格首列/加粗项，含取值样本）；
* ``cond_help`` —— Cond\* 类型 → 帮助页（先用 extract_cond_types 的人工
  核对表，再按标题/术语关键词自动补配）；
* ``crosscheck`` —— 配对报告（人工表验证 + 自动匹配 + 未覆盖类型）。

用法::

    python tools/html_cond_extract.py           # 生成 JSON
    python tools/html_cond_extract.py --check   # 打印交叉核对报告
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schemas"
META_OUT = SCHEMAS / "cond_html_meta.json"
COND_OUT = SCHEMAS / "cond_types.json"
DEFAULT_HTML_DIR = Path(
    r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64"
    r"\HTML_STpre_Eng")


class _PageParser(HTMLParser):
    """轻量结构提取：title / h3 / 段落文本 / 加粗术语 / 表格首列。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.in_title = False
        self._buf: list[str] = []
        self.paras: list[str] = []          # 正文段落（含列表项）
        self.terms: list[str] = []          # <B>[Term]</B> / <LI><B>...
        self._in_b = False
        self._b_buf: list[str] = []
        self._in_li = False
        self._li_buf: list[str] = []
        self.tables: list[list[list[str]]] = []
        self._table: list[list[list[str]]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    # -- 标题 ------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
            self._buf = []
        elif tag == "b":
            self._in_b = True
            self._b_buf = []
        elif tag == "li":
            self._in_li = True
            self._li_buf = []
        elif tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
            self.title = "".join(self._buf).strip()
        elif tag == "b":
            self._in_b = False
            text = _clean("".join(self._b_buf))
            if text:
                self._collect_bold(text)
        elif tag == "li":
            self._in_li = False
            text = _clean("".join(self._li_buf))
            if text:
                self.paras.append(text)
        elif tag in ("td", "th") and self._cell is not None \
                and self._row is not None:
            self._row.append(_clean("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._table is not None and any(c for c in self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self.tables is None:
                self.tables = []
            self.tables.append(self._table)
            self._table = None

    def handle_data(self, data):
        if self.in_title:
            self._buf.append(data)
        if self._in_b:
            self._b_buf.append(data)
        if self._in_li:
            self._li_buf.append(data)
        if self._cell is not None:
            self._cell.append(data)
        elif not self.in_title and data.strip() and not self._in_li:
            # 正文段落（粗略：由 _clean 阶段拼接近邻文本）
            self.paras.append(data.strip()) if len(data.strip()) > 2 else None

    def _collect_bold(self, text: str):
        m = re.match(r"^\[(.+)\]$", text)
        if m:
            term = m.group(1).strip()
            if term and term not in self.terms:
                self.terms.append(term)
            return
        # <LI><B>Heat transfer</B> 样式：保留首行短词
        if self._in_li and len(text) <= 48 and " " in text:
            if text not in self.terms:
                self.terms.append(text)


def _clean(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_page(path: Path) -> dict:
    p = _PageParser()
    p.feed(path.read_text(encoding="utf-8", errors="replace"))
    intro = _clean(" ".join(
        t for t in p.paras if len(t) > 20))[:400]
    params: list[dict] = []
    seen: set[str] = set()
    for tbl in p.tables or []:
        if not tbl:
            continue
        header = tbl[0]
        for row in tbl[1:]:
            if not row:
                continue
            name = row[0]
            if (not name or len(name) > 40 or name.lower() in
                    ("type", "no.", "item")):
                continue
            if name in seen:
                continue
            seen.add(name)
            params.append({
                "name": name,
                "values": [c for c in row[1:6] if c][:4],
                "header": [c for c in header[1:4] if c],
            })
    return {
        "file": path.name,
        "title": re.sub(r"^\[(.*)\]$", r"\1", p.title or path.stem),
        "intro": intro,
        "terms": p.terms[:24],
        "params": params[:40],
        "columns": [c for c in (p.tables[0][0] if p.tables and
                                p.tables[0] else []) if c],
    }


# Cond* → 帮助页人工核对表（extract_cond_types.py 同源维护）
_MANUAL_HELP: dict[str, str] = {
    "CondBoundaryFlowIO": "Flux_Inout.html",
    "CondBoundaryFlowIOLiquidFilm": "FreeSurface_Type.html",
    "CondBoundaryRadiation": "radiation_bc.html",
    "CondBoundarySolarRadiation": "SOLAR_Boundary.html",
    "CondBoundaryWallThermal": "Aent_Condition.html",
    "CondBoundaryWallStress": "Wall_Condition.html",
    "CondSymmetricalBoundary": "SymBd.html",
    "CondPeriodicBoundary": "Period_Explain.html",
    "CondSource": "Source_Condition.html",
    "CondPorousMedia": "PorousMedia_Main.html",
    "CondHumidity": "Humidity_Condition.html",
    "CondParticleTracking": "Particle_Kind.html",
    "CondMoving": "Moving_Body_Condition.html",
    "CondReaction": "Reaction_Type.html",
    "CondFreeSurface": "FreeSurface_Type.html",
    "CondInitial": "LES_Init.html",
    "CondBoussinesqBaseTemp": "BaseTemperature.html",
    "CondJOSModel": "JOS_TSV.html",
    "CondWaveGeneration": "MARS_Wave_Source.html",
    "CondWaveDamping": "MARS_Wave_Source.html",
}

# 自动补配关键词（类型名小写子串 ↔ 页面标题/文件名关键词）
_AUTO_KEYWORDS: dict[str, str] = {
    "CondHumidity": "humidity",
    "CondRadiationLamp": "lamp",
    "CondParticlePropertyDEM": "particle",
    "CondMovingStability": "moving",
    "CondCombustion": "reaction",
    "CondCavitation": "hydrostatic",
    "CondOutputLFileHeatTransfer": "heat",
}


def extract_all(html_dir: Path) -> list[dict]:
    pages = []
    for p in sorted(html_dir.glob("*.html")):
        try:
            pages.append(parse_page(p))
        except Exception as e:  # noqa: BLE001
            print(f"warn: {p.name}: {e}", file=sys.stderr)
    return pages


def crosscheck(pages: list[dict],
               cond_types: dict[str, dict]) -> dict:
    files = {pg["file"] for pg in pages}
    titles = {pg["file"]: pg["title"].lower() for pg in pages}
    cond_help: dict[str, str] = {}
    manual_ok, manual_bad = [], []
    for tname, fname in _MANUAL_HELP.items():
        if fname in files and tname in cond_types:
            cond_help[tname] = fname
            manual_ok.append(tname)
        elif tname not in cond_types:
            manual_bad.append(f"{tname} (unknown type)")
        else:
            manual_bad.append(f"{tname} -> {fname} (missing html)")
    auto = []
    for tname, kw in _AUTO_KEYWORDS.items():
        if tname in cond_help or tname not in cond_types:
            continue
        for pg in pages:
            hay = f'{pg["file"]} {pg["title"]}'.lower()
            if kw in hay:
                cond_help[tname] = pg["file"]
                auto.append(f"{tname} -> {pg['file']}")
                break
    return {
        "manual_matched": manual_ok,
        "manual_issues": manual_bad,
        "auto_matched": auto,
        "cond_help": cond_help,
        "pages_without_cond_link": sorted(
            f for f in files if f not in cond_help.values()),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--html-dir", type=Path, default=DEFAULT_HTML_DIR)
    ap.add_argument("--check", action="store_true",
                    help="打印交叉核对报告，不写 JSON")
    args = ap.parse_args(argv)

    if not args.html_dir.is_dir():
        print(f"html dir not found: {args.html_dir}", file=sys.stderr)
        return 1
    pages = extract_all(args.html_dir)
    print(f"parsed pages: {len(pages)}")

    cond_types: dict[str, dict] = {}
    if COND_OUT.is_file():
        data = json.loads(COND_OUT.read_text(encoding="utf-8"))
        cond_types = data.get("types", {})
    rep = crosscheck(pages, cond_types)
    print(f"manual help links ok: {len(rep['manual_matched'])}")
    if rep["manual_issues"]:
        print("manual issues:", "; ".join(rep["manual_issues"]))
    print(f"auto matched: {len(rep['auto_matched'])}")

    # 回填 help 到 cond_types.json
    updated = False
    if COND_OUT.is_file() and rep["cond_help"]:
        data = json.loads(COND_OUT.read_text(encoding="utf-8"))
        for tname, fname in rep["cond_help"].items():
            if tname in data["types"] and \
                    not data["types"][tname].get("help"):
                data["types"][tname]["help"] = fname
                updated = True
        if updated:
            COND_OUT.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8")
            print(f"help links backfilled -> {COND_OUT.name}")

    if not args.check:
        SCHEMAS.mkdir(parents=True, exist_ok=True)
        META_OUT.write_text(json.dumps({
            "version": 1,
            "source_dir": str(args.html_dir),
            "pages": pages,
            "crosscheck": {
                k: v for k, v in rep.items() if k != "cond_help"},
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"written: {META_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
