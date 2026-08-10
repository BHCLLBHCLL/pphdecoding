#!/usr/bin/env python3
"""抽取 PPH 项目 Schema 到 JSON（或 Conditions YAML 草稿）。

用法::

    python tools/extract_schema.py box.pph -o schemas/box.json
    python tools/extract_schema.py a.pph b.pph --merge -o schemas/merged.json
    python tools/extract_schema.py box.pph --yaml-conditions -o schemas/conditions.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pph_parser import PphArchive  # noqa: E402
from schema_extract import (extract_archive_schema, merge_schemas,  # noqa: E402
                            write_schema_json)


def _emit_conditions_yaml(schema: dict, out: Path) -> None:
    """从已抽取的 conditions.types 写出 YAML 草稿（合并进 bc_filters）。"""
    types = sorted((schema.get("conditions") or {}).get("types") or {})
    buckets: dict[str, list[str]] = {
        "bc_flow": [], "bc_wall": [], "bc_thermal": [],
        "bc_sym": [], "bc_periodic": [], "source": [],
        "fixed": [], "initial": [],
    }
    for t in types:
        tl = t.lower()
        if "flow" in tl or "fan" in tl or "pressure" in tl or "io" in tl:
            buckets["bc_flow"].append(t)
        elif "thermal" in tl or "heat" in tl:
            buckets["bc_thermal"].append(t)
        elif "wall" in tl:
            buckets["bc_wall"].append(t)
        elif "sym" in tl:
            buckets["bc_sym"].append(t)
        elif "period" in tl:
            buckets["bc_periodic"].append(t)
        elif "source" in tl:
            buckets["source"].append(t)
        elif "fix" in tl:
            buckets["fixed"].append(t)
        elif "initial" in tl:
            buckets["initial"].append(t)
    lines = [
        "# Auto-draft from extract_schema.py --yaml-conditions",
        "version: 1",
        "bc_filters:",
    ]
    for key, vals in buckets.items():
        lines.append(f"  {key}:")
        if not vals:
            lines.append("    []")
            continue
        for v in vals:
            lines.append(f"    - {v}")
    lines.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="抽取 PPH 条件/环境/物性 Schema")
    ap.add_argument("pph", nargs="+", help="PPH 文件路径")
    ap.add_argument("-o", "--output", required=True,
                    help="输出 JSON 路径（--merge 时为合并结果）")
    ap.add_argument("--merge", action="store_true",
                    help="把多个 PPH 合并为一个 schema")
    ap.add_argument("--yaml-conditions", action="store_true",
                    help="写出 conditions.yaml 草稿（用首个 PPH）")
    args = ap.parse_args(argv)

    if args.yaml_conditions:
        arch = PphArchive.open(args.pph[0])
        schema = extract_archive_schema(arch)
        _emit_conditions_yaml(schema, Path(args.output))
        print(f"{args.pph[0]} -> {args.output} (yaml conditions draft)")
        return 0

    schemas = []
    for p in args.pph:
        arch = PphArchive.open(p)
        schema = extract_archive_schema(arch)
        if not args.merge:
            out = Path(args.output)
            if len(args.pph) > 1:
                out = out / (Path(p).stem + ".json")
            write_schema_json(schema, out)
            print(f"{p} -> {out}")
        else:
            schemas.append(schema)
    if args.merge:
        merged = merge_schemas(schemas)
        write_schema_json(merged, args.output)
        print(f"merged {len(schemas)} projects -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
