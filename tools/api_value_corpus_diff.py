#!/usr/bin/env python3
"""R33-3：手册词表 vs 宿主语料对拍（宿主自己写出的 main.xml 才是实测口径）。

语料 = 官方算例库（`official_examples.example_root()`，151 个工程）里宿主写出的
`main.xml`。取值写成 `<xxx_type><name>VALUE</name>` —— 这正是**宿主承认的取值**。

对拍两个方向：

* `only_corpus`：语料里出现、**整本手册词表都没有**的取值 → 手册漏项候选
  （R30 的 `octree` 就是这么发现的，那里靠 getter 读回，这里靠 XML 落盘）；
* `only_manual`：手册有、语料没出现 —— 样本量所限的弱信号，只计数。

用法::

    python tools/api_value_corpus_diff.py --json _p12u_gate/r33/corpus_diff.json
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
#: 取值容器：`<xxx_type><name>VALUE</name>`（用户自取的名字不在此列）
CONTAINER = re.compile(r"<(\w*type\w*)>\s*<name>([^<]{1,60})</name>")
#: 已建立「容器 → 目录成员」映射的族（可做精确对拍）
KNOWN_LINKS = {
    "stability_type": ("Conditions", "GetPresetStabilityParam", "param"),
    "stabilitygeom_type": ("Conditions", "GetPresetStabilityParamGeom",
                           "param"),
}


def catalog_values(cls: str, member: str, arg: str) -> list:
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    entry = ((cat["classes"].get(cls) or {}).get("methods") or {}).get(member)
    if not entry:
        return []
    for a in entry.get("arguments") or []:
        if a.get("name") == arg:
            return [v["value"] for v in (a.get("values") or [])]
    return []


def all_catalog_values() -> set:
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    out = set()
    for info in cat["classes"].values():
        for kind in ("methods", "properties"):
            for e in (info.get(kind) or {}).values():
                for a in (e.get("arguments") or []) + [e.get("return") or {}]:
                    if isinstance(a, dict):
                        out.update(v["value"] for v in (a.get("values") or []))
    return out


def scan_corpus() -> dict:
    root = official_examples.example_root()
    if root is None:
        raise SystemExit("官方算例库未找到（official_examples.example_root()）")
    per_parent: dict = collections.defaultdict(collections.Counter)
    files = errors = 0
    for p in sorted(root.rglob("*.pph")):
        try:
            arch = PphArchive.open(str(p))
            text = arch.read_member("main.xml").decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            errors += 1
            continue
        files += 1
        for parent, value in CONTAINER.findall(text):
            per_parent[parent][value] += 1
    return {"files": files, "errors": errors,
            "per_parent": {k: dict(v) for k, v in per_parent.items()}}


def diff(scan: dict) -> dict:
    manual_all = all_catalog_values()
    corpus_all = {v for vals in scan["per_parent"].values() for v in vals}
    links = []
    for parent, (cls, member, arg) in KNOWN_LINKS.items():
        manual = set(catalog_values(cls, member, arg))
        corpus = set(scan["per_parent"].get(parent) or {})
        links.append({
            "parent": parent, "member": cls + "." + member + "." + arg,
            "manual": sorted(manual), "corpus": sorted(corpus),
            "only_manual": sorted(manual - corpus),
            "only_corpus": sorted(corpus - manual),
            "agree": manual == corpus,
        })
    return {
        "files": scan["files"], "errors": scan["errors"],
        "parents": {k: len(v) for k, v in sorted(scan["per_parent"].items())},
        "links": links,
        "corpus_only_global": sorted(corpus_all - manual_all),
        "manual_value_count": len(manual_all),
        "corpus_value_count": len(corpus_all),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="手册词表 vs 宿主语料对拍")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args(argv)
    data = diff(scan_corpus())
    print("[corpus] 工程 " + str(data["files"]) + "（读失败 "
          + str(data["errors"]) + "）| 取值容器 "
          + str(len(data["parents"])) + " 种")
    for link in data["links"]:
        print("   " + link["parent"] + " ↔ " + link["member"]
              + " 一致=" + str(link["agree"])
              + " 手册=" + str(len(link["manual"]))
              + " 语料=" + str(len(link["corpus"]))
              + " only_corpus=" + json.dumps(link["only_corpus"]))
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
    print("SUMMARY: " + json.dumps({"all_links_agree": bool(ok),
                                    "links": len(data["links"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
