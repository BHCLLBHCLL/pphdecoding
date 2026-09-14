#!/usr/bin/env python3
"""R33-3/R34-1：手册词表 vs 宿主语料对拍（宿主自己写出的 main.xml 才是实测口径）。

语料 = 官方算例库（`official_examples.example_root()`，151 个工程）里宿主写出的
`main.xml`。取值有两种写法，都收：

* `<X><name>VALUE</name>…`（方程/参数名族，如 `stability_type`、`solv_param`）；
* `<X>VALUE</X>` 且 X 以 `_type` 结尾（枚举族，如 `connection_type`）。

对拍两个方向：

* `only_corpus`：语料里出现、**手册词表里没有**的取值 → 手册漏项候选；
* `only_manual`：手册有、语料没出现 —— 样本量所限的弱信号，只计数。

链接（容器 ↔ 目录成员）有两种来源：

1. `KNOWN_LINKS`：人工确认过的精确链接（R33-3）；
2. `--auto`：按**取值集交叉**自动发现 —— 语料取值与某目录槽的取值集
   交集占语料侧多数（默认 ≥2 个且 ≥50%）即认定同一族，再看差集。

用法::

    python tools/api_value_corpus_diff.py --json out.json          # 仅 KNOWN_LINKS
    python tools/api_value_corpus_diff.py --auto --json out.json   # 含自动发现
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console_utf8  # noqa: E402

console_utf8.enable()

import official_examples  # noqa: E402
from pph_parser import PphArchive  # noqa: E402

CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
#: 取值容器写法一：`<xxx_type><name>VALUE</name>`
CONTAINER_NAME = re.compile(r"<(\w*)>\s*<name>([^<]{1,60})</name>")
#: 取值容器写法二：`<xxx_type>VALUE</xxx_type>`（值本身是标识符样）
CONTAINER_TEXT = re.compile(r"<(\w*_type)>([A-Za-z_][A-Za-z0-9_]{1,39})</\1>")
#: 已人工确认的精确链接：容器 → (类, 成员, 参数)
KNOWN_LINKS = {
    "stability_type": ("Conditions", "GetPresetStabilityParam", "param"),
    "stabilitygeom_type": ("Conditions", "GetPresetStabilityParamGeom",
                           "param"),
}


def load_catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def _slots(cat: dict):
    """yield (cls, member, arg, values) —— arg 为 "return" 时指返回值。"""
    for cls, info in cat["classes"].items():
        for kind in ("methods", "properties"):
            for member, entry in (info.get(kind) or {}).items():
                for a in entry.get("arguments") or []:
                    if a.get("values"):
                        yield cls, member, a.get("name"), a["values"]
                r = entry.get("return") or {}
                if r.get("values"):
                    yield cls, member, "return", r["values"]


def catalog_values(cls: str, member: str, arg: str) -> list:
    for c, m, a, values in _slots(load_catalog()):
        if (c, m, a) == (cls, member, arg):
            return [v["value"] for v in values]
    return []


def all_catalog_values() -> set:
    return {v["value"] for _c, _m, _a, values in _slots(load_catalog())
            for v in values}


def scan_corpus() -> dict:
    root = official_examples.example_root()
    if root is None:
        raise SystemExit("官方算例库未找到（official_examples.example_root()）")
    per_container: dict = collections.defaultdict(collections.Counter)
    files = errors = 0
    for p in sorted(root.rglob("*.pph")):
        try:
            arch = PphArchive.open(str(p))
            text = arch.read_member("main.xml").decode("utf-8",
                                                       errors="replace")
        except Exception:  # noqa: BLE001
            errors += 1
            continue
        files += 1
        for parent, value in CONTAINER_NAME.findall(text):
            per_container[parent][value] += 1
        for parent, value in CONTAINER_TEXT.findall(text):
            per_container[parent][value] += 1
    return {"files": files, "errors": errors,
            "per_container": {k: dict(v) for k, v in per_container.items()}}


def _link(parent: str, cls: str, member: str, arg: str, corpus: set) -> dict:
    manual = set(catalog_values(cls, member, arg))
    return {
        "parent": parent, "member": cls + "." + member + "." + arg,
        "manual": sorted(manual), "corpus": sorted(corpus),
        "only_manual": sorted(manual - corpus),
        "only_corpus": sorted(corpus - manual),
        "agree": manual == corpus,
    }


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _name_matches(parent: str, member: str) -> bool:
    """容器名与成员名是否同源（`connection_type` ↔ `GetConnectionType`）。

    取值集交叉**只能**用来找候选：同一批取值可能挂在多个设置上
    （实测 `loop_eq_param`/`equa_start_param` 都"匹配"到 `GetUpwdParam`）。
    只有名字同源的链接才允许据以入库 —— 否则只是「取值重叠」提示。
    """
    p, m = _norm(parent), _norm(member)
    if not p or not m:
        return False
    m = re.sub(r"^(get|set)", "", m)
    return p == m or p.rstrip("type") == m.rstrip("type")


def discover_links(scan: dict, *, min_shared: int = 2,
                   min_ratio: float = 0.5, limit: int = 60) -> tuple:
    """按取值集交叉自动发现候选，并按**名字同源**分成可入库/仅提示两桶。"""
    slots = [(cls, member, arg, {v["value"] for v in values})
             for cls, member, arg, values in _slots(load_catalog())]
    actionable, overlap_only = [], []
    for parent, values in sorted(scan["per_container"].items()):
        corpus = set(values)
        if len(corpus) < min_shared:
            continue
        best = None
        for cls, member, arg, manual in slots:
            shared = len(corpus & manual)
            if shared < min(min_shared, len(corpus)):
                continue
            if shared < min_ratio * len(corpus):
                continue
            named = _name_matches(parent, member)
            score = (shared + (100 if named else 0))
            if best is None or score > best[0]:
                best = (score, cls, member, arg, named)
        if not best:
            continue
        _score, cls, member, arg, named = best
        link = _link(parent, cls, member, arg, corpus)
        link["name_matched"] = named
        (actionable if named else overlap_only).append(link)
    return actionable[:limit], overlap_only[:limit]


def diff(scan: dict, auto: bool = False) -> dict:
    manual_all = all_catalog_values()
    corpus_all = {v for vals in scan["per_container"].values() for v in vals}
    links = [_link(parent, *KNOWN_LINKS[parent],
                   set(scan["per_container"].get(parent) or {}))
             for parent in KNOWN_LINKS]
    discovered, overlap_only = discover_links(scan) if auto else ([], [])
    known_pairs = {tuple(KNOWN_LINKS[p]) for p in KNOWN_LINKS}
    discovered = [d for d in discovered
                  if d["member"] not in {c + "." + m + "." + a
                                         for c, m, a in known_pairs}]
    return {
        "files": scan["files"], "errors": scan["errors"],
        "containers": {k: len(v)
                       for k, v in sorted(scan["per_container"].items())},
        "links": links, "discovered": discovered,
        "overlap_only": overlap_only,
        "corpus_only_global": sorted(corpus_all - manual_all),
        "manual_value_count": len(manual_all),
        "corpus_value_count": len(corpus_all),
    }


def _print_link(link: dict, tag: str) -> None:
    print("   " + tag + " " + link["parent"] + " ↔ " + link["member"]
          + " 一致=" + str(link["agree"])
          + " 手册=" + str(len(link["manual"]))
          + " 语料=" + str(len(link["corpus"]))
          + " only_corpus=" + json.dumps(link["only_corpus"])
          + " only_manual=" + json.dumps(link["only_manual"][:4]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="手册词表 vs 宿主语料对拍")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--auto", action="store_true",
                    help="按取值集交叉自动发现链接")
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args(argv)
    data = diff(scan_corpus(), auto=args.auto)
    print("[corpus] 工程 " + str(data["files"]) + "（读失败 "
          + str(data["errors"]) + "）| 取值容器 "
          + str(len(data["containers"])) + " 种")
    for link in data["links"]:
        _print_link(link, "known")
    for link in data["discovered"]:
        _print_link(link, "auto ")
    print("[corpus] 仅取值重叠（名字不同源，**不入库**，只作提示）: "
          + str(len(data["overlap_only"])))
    for link in data["overlap_only"][:8]:
        _print_link(link, "ovlp ")
    print("[corpus] 手册词表 " + str(data["manual_value_count"])
          + " 条 | 语料取值 " + str(data["corpus_value_count"])
          + " 条 | 语料独有（全库手册都没有）"
          + str(len(data["corpus_only_global"])) + " 条")
    for v in data["corpus_only_global"][:args.limit]:
        print("   corpus-only: " + v)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    ok = all(link["agree"] for link in data["links"])
    print("SUMMARY: " + json.dumps({
        "all_known_links_agree": bool(ok),
        "known": len(data["links"]),
        "auto": len(data["discovered"]),
        "auto_with_gap": sum(1 for d in data["discovered"]
                             if d["only_corpus"]),
        "overlap_only": len(data["overlap_only"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
