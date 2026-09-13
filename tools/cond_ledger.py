#!/usr/bin/env python3
"""R9-5：条件体系账目口径固化（常量表 + 再生校验）。

R8-1 实测封顶：有 XML 落点的类型就 **92** 个（registry_key 90 + member_locus 2），
其余是设计上无落点的向导态。本工具把这份口径写成常量，并校验 `schemas/cond_types.json`
的 dispositions **与其一致** —— 任何后续再生（扫描/收割/重算）若改了账目，这里立刻红。

用法::

    python tools/cond_ledger.py            # 打印账目并与常量核对
    python tools/cond_ledger.py --json out.json
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

COND_TYPES = ROOT / "schemas" / "cond_types.json"

#: 账目口径（R8-1 实测；改这里必须同时给出新证据）
EXPECTED_UNIVERSE = 165
EXPECTED_KINDS = {
    "registry_key": 90,
    "member_locus": 2,
    "wizard_session_state": 71,
    "wizard_session_state_gated": 1,
    "alias": 1,
    "poison_isolated": 1,
}
#: 三类收束（H4 口径）
EXPECTED_BUCKETS = {"exact_key": 92, "alias": 1, "boundary": 72}
BUCKET_OF_KIND = {
    "registry_key": "exact_key",
    "member_locus": "exact_key",
    "alias": "alias",
    "wizard_session_state": "boundary",
    "wizard_session_state_gated": "boundary",
    "poison_isolated": "boundary",
}


def ledger() -> dict:
    data = json.loads(COND_TYPES.read_text(encoding="utf-8"))
    disp = data.get("dispositions") or {}
    kinds = collections.Counter()
    buckets = collections.Counter()
    unknown = []
    #: 族级注记（不在 165 宇宙内；H3 并轨入册、H4 原样保留）
    annotations = {"Thermoregulation"}
    for name, rec in disp.items():
        kind = (rec or {}).get("kind") if isinstance(rec, dict) else rec
        if name in annotations:
            kinds[kind] += 1          # 记 kind，但不计入宇宙内三类收束
            continue
        kinds[kind] += 1
        bucket = BUCKET_OF_KIND.get(kind)
        if bucket is None:
            unknown.append([name, kind])
        else:
            buckets[bucket] += 1
    return {"version": data.get("version"),
            "universe": len(data.get("types") or []),
            "annotations": ["Thermoregulation"],
            "dispositions": len(disp),
            "kinds": dict(kinds), "buckets": dict(buckets),
            "unknown_kinds": unknown[:10]}


def check(led: dict) -> list:
    problems = []
    if led["universe"] != EXPECTED_UNIVERSE:
        problems.append("universe " + str(led["universe"]) + " != "
                        + str(EXPECTED_UNIVERSE))
    for kind, want in EXPECTED_KINDS.items():
        got = led["kinds"].get(kind, 0)
        if got != want:
            problems.append("kind " + kind + " " + str(got) + " != "
                            + str(want))
    for bucket, want in EXPECTED_BUCKETS.items():
        got = led["buckets"].get(bucket, 0)
        if got != want:
            problems.append("bucket " + bucket + " " + str(got) + " != "
                            + str(want))
    if led["unknown_kinds"]:
        problems.append("unknown kinds: "
                        + json.dumps(led["unknown_kinds"], ensure_ascii=False))
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R9-5 条件账目口径固化")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)
    led = ledger()
    problems = check(led)
    print("[r9-5] " + json.dumps(
        {"universe": led["universe"], "kinds": led["kinds"],
         "buckets": led["buckets"]}, ensure_ascii=False))
    print("[r9-5] 口径: " + json.dumps(
        {"universe": EXPECTED_UNIVERSE, "kinds": EXPECTED_KINDS,
         "buckets": EXPECTED_BUCKETS}, ensure_ascii=False))
    if problems:
        print("[r9-5] MISMATCH:")
        for p in problems:
            print("   - " + p)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({"ledger": led, "expected": {
            "universe": EXPECTED_UNIVERSE, "kinds": EXPECTED_KINDS,
            "buckets": EXPECTED_BUCKETS}, "problems": problems},
            ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUMMARY: " + json.dumps({"passed": not problems,
                                     "problems": len(problems)},
                                    ensure_ascii=False))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
