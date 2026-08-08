#!/usr/bin/env python3
"""黄金语料清单构建工具。

扫描目录下所有 ``*.pph``，记录成员名/角色/大小/压缩比/SHA-256，
输出 ``corpus.json``，作为字节级回归与跨样例不变式测试的语料清单。

用法::

    python tools/build_corpus.py tests -o corpus.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pph_parser import PphArchive  # noqa: E402


def iter_pph_files(root: str | Path) -> list[Path]:
    return sorted(Path(root).rglob("*.pph"))


def member_record(arch: PphArchive, name: str) -> dict:
    data = arch.read_member(name)
    member = next(m for m in arch.members if m.name == name)
    return {
        "name": name,
        "role": member.role,
        "size": len(data),
        "compress_size": member.compress_size,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def build_corpus(root: str | Path, limit: int = 0) -> dict:
    files = iter_pph_files(root)
    if limit > 0:
        files = files[:limit]
    samples = []
    for p in files:
        try:
            arch = PphArchive.open(str(p))
        except ValueError as exc:
            samples.append({"path": str(p), "error": str(exc)})
            continue
        members = [member_record(arch, m.name) for m in arch.members]
        samples.append({
            "path": str(p),
            "member_count": len(members),
            "total_size": sum(m["size"] for m in members),
            "members": members,
        })
    return {
        "schema_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(Path(root).resolve()),
        "sample_count": len(samples),
        "samples": samples,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="构建 PPH 黄金语料清单")
    ap.add_argument("root", help="扫描目录")
    ap.add_argument("-o", "--output", required=True, help="corpus.json 输出路径")
    ap.add_argument("--limit", type=int, default=0,
                    help="最多处理的 PPH 数量（0=不限）")
    args = ap.parse_args(argv)

    corpus = build_corpus(args.root, args.limit)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(corpus, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"samples={corpus['sample_count']} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
