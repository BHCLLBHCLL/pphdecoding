#!/usr/bin/env python3
"""R9-2：两种 x_t 的格式差分（宿主原生 vs CADthru 产出）。

背景（R8-3）：CADthru 产出的 x_t 离线完全正常（1 body / 4358 三角 / bbox 正确），
但宿主 OpenCadFile 读不出 SNode；而宿主原生 x_t 同流程正常。本工具把两者的
**头部块**与**节点类型直方图**摆在一起，定位宿主拒收的字段级判据。

用法::

    python tools/xt_format_diff.py --a tests/box/box.x_t --b _p12u_gate/r8_3_keyv2.x_t
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console_utf8  # noqa: E402

console_utf8.enable()

import parasolid  # noqa: E402


def header_block(data: bytes) -> list:
    """头部块：从文件开头到 END_OF_HEADER 的**全部行**（含非 ** 行）。

    注意不能只收连续的 ** 行：XT 头部是 ** 行与字段行交替的，早先只收
    连续 ** 行导致两边都只剩 3 行，看起来完全一样（假阴性）。
    """
    out = []
    for raw in data.split(b"\n")[:200]:
        line = raw.strip(b"\r").decode("latin-1")
        out.append(line.rstrip())
        if "END_OF_HEADER" in line:
            break
    return out


def profile(path: Path) -> dict:
    data = path.read_bytes()
    info = {"path": str(path), "bytes": len(data),
            "header": header_block(data)}
    try:
        model = parasolid.parse_xt(data)
    except Exception as exc:  # noqa: BLE001
        info["parse_error"] = type(exc).__name__ + ": " + str(exc)
        return info
    hist = collections.Counter()
    for nd in (getattr(model, "order", []) or []):
        hist[getattr(nd, "name", None) or type(nd).__name__] += 1
    info["node_total"] = sum(hist.values())
    info["node_types"] = dict(hist.most_common(12))
    for attr in ("schema", "schema_name", "version", "precision"):
        if hasattr(model, attr):
            info[attr] = str(getattr(model, attr))[:80]
    return info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R9-2 x_t 格式差分")
    ap.add_argument("--a", type=Path, default=ROOT / "tests" / "box" / "box.x_t")
    ap.add_argument("--b", type=Path, default=ROOT / "_p12u_gate" / "r8_3_keyv2.x_t")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)
    a, b = profile(args.a), profile(args.b)
    result = {"a": a, "b": b}
    ha, hb = set(a.get("header", [])), set(b.get("header", []))
    result["header_only_in_a"] = sorted(ha - hb)
    result["header_only_in_b"] = sorted(hb - ha)
    ta, tb = a.get("node_types", {}), b.get("node_types", {})
    result["node_only_in_a"] = sorted(set(ta) - set(tb))
    result["node_only_in_b"] = sorted(set(tb) - set(ta))
    print("[r9-2] A(" + args.a.name + ") " + str(a.get("bytes")) + " B("
          + args.b.name + ") " + str(b.get("bytes")))
    print("--- header A ---")
    for line in a.get("header", []):
        print("  " + line)
    print("--- header B ---")
    for line in b.get("header", []):
        print("  " + line)
    print("--- header only in A: " + json.dumps(result["header_only_in_a"],
                                                   ensure_ascii=False))
    print("--- header only in B: " + json.dumps(result["header_only_in_b"],
                                                   ensure_ascii=False))
    print("--- node totals A/B: " + str(a.get("node_total")) + " / "
          + str(b.get("node_total")))
    print("--- node types A: " + json.dumps(a.get("node_types", {}),
                                              ensure_ascii=False))
    print("--- node types B: " + json.dumps(b.get("node_types", {}),
                                              ensure_ascii=False))
    print("--- node only in A: " + json.dumps(result["node_only_in_a"],
                                                ensure_ascii=False))
    print("--- node only in B: " + json.dumps(result["node_only_in_b"],
                                                ensure_ascii=False))
    for key in ("parse_error",):
        for tag, prof in (("A", a), ("B", b)):
            if key in prof:
                print("[" + tag + "] " + key + ": " + prof[key])
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
