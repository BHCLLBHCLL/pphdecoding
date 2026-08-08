#!/usr/bin/env python3
"""抽取 PPH 项目 Schema 到 JSON。

用法::

    python tools/extract_schema.py box.pph -o schemas/box.json
    python tools/extract_schema.py a.pph b.pph --merge -o schemas/merged.json
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="抽取 PPH 条件/环境/物性 Schema")
    ap.add_argument("pph", nargs="+", help="PPH 文件路径")
    ap.add_argument("-o", "--output", required=True,
                    help="输出 JSON 路径（--merge 时为合并结果）")
    ap.add_argument("--merge", action="store_true",
                    help="把多个 PPH 合并为一个 schema")
    args = ap.parse_args(argv)

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
