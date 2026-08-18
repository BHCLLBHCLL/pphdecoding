#!/usr/bin/env python3
"""从官方案例库精选 PPH 抽取 Cond* XML 键，并入 schemas/merged.json。

不复制 .pph 二进制。案例库缺失时以非零退出。

用法::

    python tools/merge_official_schema.py            # 精选 24 个
    python tools/merge_official_schema.py --all      # 全量扫描库内全部 PPH
    python tools/merge_official_schema.py --root D:\\training\\cradle\\...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import official_examples  # noqa: E402
from pph_parser import PphArchive  # noqa: E402
from schema_extract import (  # noqa: E402
    extract_archive_schema, extend_merged_schema, load_schema_json,
    merge_schemas, write_schema_json,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Merge official example Cond* XML keys into merged.json")
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--all", action="store_true",
                    help="扫描库内全部 PPH（默认仅精选 SCHEMA_CURATED）")
    ap.add_argument("-o", "--output", type=Path,
                    default=ROOT / "schemas" / "merged.json")
    args = ap.parse_args(argv)

    base_root = args.root or official_examples.example_root()
    if base_root is None:
        print("official example library not found "
              f"(set {official_examples.ENV_VAR})", file=sys.stderr)
        return 2

    schemas = []
    missing = []
    if args.all:
        # 全量：库内全部 PPH（Org 工程优先；同工程多解收敛变体共享键集）
        paths = sorted(base_root.rglob("*.pph"))
        print(f"full sweep: {len(paths)} PPH under {base_root}")
        for path in paths:
            rel = path.relative_to(base_root)
            try:
                arch = PphArchive.open(str(path))
                schemas.append(extract_archive_schema(arch))
            except Exception as exc:  # noqa: BLE001
                print(f"  SKIP {rel}: {exc}")
        if not schemas:
            print("no PPH extracted in full sweep", file=sys.stderr)
            return 2
    else:
        for rel in official_examples.SCHEMA_CURATED:
            path = official_examples.example_pph(rel, root=base_root)
            if path is None:
                missing.append(rel)
                continue
            print(f"extract {rel}")
            try:
                arch = PphArchive.open(str(path))
                schemas.append(extract_archive_schema(arch))
            except Exception as exc:  # noqa: BLE001
                print(f"  SKIP {rel}: {exc}")
                continue
        if not schemas:
            print("no curated PPH extracted", file=sys.stderr)
            return 2
        if missing:
            print(f"skip missing {len(missing)}: {missing[:5]}...")

    extra = merge_schemas(schemas)
    extra_types = extra.get("conditions", {}).get("types") or {}
    print(f"official unique Cond* {len(extra_types)}")

    out = args.output
    if out.is_file():
        merged = extend_merged_schema(load_schema_json(out), extra)
    else:
        merged = extra
    have = {
        k for k, v in (merged.get("conditions") or {}).get("types", {}).items()
        if v.get("fields")
    }
    write_schema_json(merged, out)
    print(f"wrote {out} types_with_fields={len(have)} "
          f"projects={len(merged.get('projects') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
