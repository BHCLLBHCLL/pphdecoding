#!/usr/bin/env python3
"""R34-3：目录 ↔ typed 桥落差账（逐类：目录成员数 vs 包装方法数）。

R32-3 把返回值补齐到 **4177 条**，但 typed 桥（`automation/scflowpre_api.py`）按
「高频成员」手写包装 —— 两边从未对过账。本工具把落差算出来：

* 逐类：目录成员数（methods+properties）/ 包装方法数 / 覆盖率；
* **反向不变量**：包装方法名必须能在目录里找到（否则调的是手册外成员，
  需要像 `SetIntersectionDetectionDepth` 那样显式登记）。

用法::

    python tools/api_bridge_coverage.py --json _p12u_gate/r34/bridge_coverage.json
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

from automation import scflowpre_api as api  # noqa: E402

CATALOG = ROOT / "schemas" / "vb_api_catalog.json"


#: 签名里的真实方法名（手册 h3 标题可能有拼写错：实测
#: `CreateDiscontinuousMeshingGroupWitouthMovingPart` 标题 vs
#: `…WithoutMovingPart` 签名 —— 包装类按**签名**写，故对账必须两处都认）
_SIG_NAME = re.compile(r"\.([A-Za-z_]\w*)\s*[\( ]")


def _signature_names(entry: dict) -> set:
    if entry.get("signature_name"):
        return {entry["signature_name"]}
    m = _SIG_NAME.search(entry.get("signature") or "")
    return {m.group(1)} if m else set()


def heading_signature_mismatches(cat: dict) -> list:
    """标题名 ≠ 签名名的方法（手册标题拼写错的完整清单）。"""
    out = []
    for cls, info in cat["classes"].items():
        for kind in ("methods", "properties"):
            for name, entry in (info.get(kind) or {}).items():
                sig = entry.get("signature_name")
                if not sig:
                    names = _signature_names(entry)
                    sig = sorted(names)[0] if names else None
                if sig and sig != name:
                    out.append({"class": cls, "heading": name,
                                "signature": sig, "kind": kind})
    return out


def _wrapped_members(klass: type) -> set:
    """包装类**自己**定义的公开方法（不含继承自 ComObject 的通用入口）。"""
    base = set(dir(api.ComObject))
    out = set()
    for name, obj in vars(klass).items():
        if name.startswith("_"):
            continue
        if callable(obj) and name not in base:
            out.add(name)
    return out


def report(catalog: dict | None = None) -> dict:
    # R35-3：按目录物化包装（属性名 = 目录键、派发名 = signature_name 优先），
    # 让账目反映"目录成员是否可经 typed 类调用且带取值校验"
    materialized = api.materialize_catalog_wrappers()
    cat = catalog or json.loads(CATALOG.read_text(encoding="utf-8"))
    classes = cat["classes"]
    rows = []
    unknown: list = []
    for cls_name, klass in sorted(api.TYPED_CLASSES.items()):
        info = classes.get(cls_name) or {}
        catalog_members = set(info.get("methods") or {}) | set(
            info.get("properties") or {})
        sig_names = set()
        for kind in ("methods", "properties"):
            for entry in (info.get(kind) or {}).values():
                sig_names |= _signature_names(entry)
        catalog_members |= sig_names
        wrapped = _wrapped_members(klass)
        for m in sorted(wrapped - catalog_members):
            # 自研便捷方法（非 COM 命名：小写开头/带下划线）不算"目录外成员"
            if m[:1].islower() or "_" in m:
                continue
            unknown.append(cls_name + "." + m)
        rows.append({
            "class": cls_name,
            "wrapper": klass.__name__,
            "catalog_members": len(catalog_members),
            "wrapped": len(wrapped & catalog_members),
            "coverage": round(len(wrapped & catalog_members)
                              / max(1, len(catalog_members)), 3),
            "unwrapped_sample": sorted(catalog_members - wrapped)[:6],
        })
    rows.sort(key=lambda r: (-r["catalog_members"], r["class"]))
    total_cat = sum(r["catalog_members"] for r in rows)
    total_wrapped = sum(r["wrapped"] for r in rows)
    return {
        "materialized_now": materialized,
        "classes": len(rows),
        "catalog_members_in_typed_classes": total_cat,
        "wrapped": total_wrapped,
        "coverage": round(total_wrapped / max(1, total_cat), 3),
        "rows": rows,
        "unknown_wrapped_members": unknown,
        "heading_signature_mismatch": heading_signature_mismatches(cat),
        "catalog_members_total": sum(
            len(v.get("methods") or {}) + len(v.get("properties") or {})
            for v in classes.values()),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="目录 ↔ typed 桥落差账")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args(argv)
    data = report()
    print("[bridge] typed 类 " + str(data["classes"])
          + " | 字典成员 " + str(data["catalog_members_in_typed_classes"])
          + " | 已包装 " + str(data["wrapped"])
          + " | 覆盖率 " + str(data["coverage"]))
    print("[bridge] 目录全量成员 " + str(data["catalog_members_total"]))
    for row in data["rows"][:args.top]:
        print("   " + row["class"].ljust(30) + str(row["wrapped"]).rjust(4)
              + "/" + str(row["catalog_members"]).ljust(5)
              + " 覆盖 " + str(row["coverage"]))
    mism = data.get("heading_signature_mismatch") or []
    print("[bridge] 手册标题名 ≠ 签名名: " + str(len(mism))
          + (" -> " + json.dumps(mism, ensure_ascii=False) if mism else ""))
    if data["unknown_wrapped_members"]:
        print("[bridge] ⚠ 包装了目录外成员: "
              + json.dumps(data["unknown_wrapped_members"]))
    else:
        print("[bridge] 包装方法全部可在目录中找到 ✓")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    print("SUMMARY: " + json.dumps({"passed": not data[
        "unknown_wrapped_members"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
