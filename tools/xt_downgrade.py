#!/usr/bin/env python3
"""R12-1：x_t 离线降版（v37 → 宿主可读的 v34）。

R9-2 判据：宿主接收端是 `SCH_3400153_34001`（v34），而本机 CADthru 产物是
`SCH_3701153_37102`（v37）→ 宿主静默零几何。R10-2 证明 CADthru COM 无法控版；
R11-2 证明宿主自己写出的也是 v37（写得出、读不了）。

本工具走**离线**路线：`PK_PART_receive` → `PK_PART_transmit(nw_version=?)`，
枚举 `transmit_nw_version`（此前该字段恒为 0），看哪一档写出 v34 的 `SCH=`。

用法::

    python tools/xt_downgrade.py --src _p12u_gate/r8_3_keyv2.x_t
    python tools/xt_downgrade.py --src in.x_t --values 0,1,34,100 --json out.json
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

import ps_facet2_nodes as ps  # noqa: E402

#: 宿主接收端的主版本（`SCH_3400153_34001` → Parasolid 34）；同主版本的不同
#: build（如 `SCH_3400000_340010` = 标准 34.0 发布）也应被宿主接受，故按主版本判定。
TARGET_MAJOR = "34"
TARGET_SCH = "SCH_3400153_34001"


VERSION_RE = re.compile(r"modeller version (\d+)\s+(SCH_\d+_\d+)")


def sch_of(data: bytes):
    """两种头部形态都认：**PART2 段里的 SCH= 行，以及首行 modeller version 串。"""
    if not data:
        return None
    head = data[:1200].decode("latin-1")
    m = re.search(r"SCH=([^;\r\n]+);", head)
    if m:
        return m.group(1)
    m = VERSION_RE.search(head)
    return m.group(2) if m else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R12-1 x_t 离线降版")
    ap.add_argument("--src", type=Path,
                    default=ROOT / "_p12u_gate" / "r8_3_keyv2.x_t")
    ap.add_argument("--values", default="0,1,34,100,1000,2025")
    ap.add_argument("--o-t-version", type=int, default=4,
                    help="V37 正确取值 = 4（guide §11.5；1/2/3 为旧布局）")
    ap.add_argument("--format", type=int, default=18220,
                    help="18220=text / 18221=binary（非 0..5）")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)
    src = args.src.resolve()
    if not src.is_file():
        print("SUMMARY: " + json.dumps({"passed": False,
                                        "error": "src missing"}))
        return 1
    raw = src.read_bytes()
    values = [int(v) for v in args.values.split(",") if v.strip()]
    out = {"src": str(src), "src_sch": sch_of(raw), "target_sch": TARGET_SCH,
           "attempts": []}
    print("[r12-1] src=" + src.name + " SCH=" + str(out["src_sch"]))
    for v in values:
        rec = {"nw_version": v}
        try:
            data = ps.transmit_xt(raw, nw_version=v,
                                  o_t_version=args.o_t_version,
                                  transmit_format=args.format)
            rec["bytes"] = len(data or b"")
            rec["sch"] = sch_of(data or b"")
            dst = ROOT / "_p12u_gate" / ("r12_1_nw%d.x_t" % v)
            if data:
                dst.write_bytes(data)
                rec["dst"] = str(dst)
            sch = rec["sch"] or ""
            rec["same_major"] = sch.startswith("SCH_%s" % TARGET_MAJOR)
            rec["ok"] = bool(data) and rec["same_major"]
        except Exception as exc:  # noqa: BLE001
            rec["error"] = type(exc).__name__ + ": " + str(exc)
            rec["ok"] = False
        out["attempts"].append(rec)
        print("[r12-1] nw_version=" + str(v) + " -> SCH=" + str(rec.get("sch"))
              + " bytes=" + str(rec.get("bytes")) + " ok=" + str(rec["ok"]))
    hits = [a for a in out["attempts"] if a.get("ok")]
    out["hit"] = hits[0] if hits else None
    out["passed"] = bool(hits)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print("SUMMARY: " + json.dumps({"passed": out["passed"],
                                     "hit": out["hit"]}, ensure_ascii=False))
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
