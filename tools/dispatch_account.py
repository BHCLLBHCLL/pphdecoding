#!/usr/bin/env python3
"""R39-1：「标题名 ≠ 签名名」41 处的**总账**（每条必须有终态）。

两条终态：

* `verdict`：有实机裁定（R35–R38 用 `IDispatch::GetIDsOfNames` 只做名字解析），
  记下宿主真正接受的名字；
* `nyi`：本轮**无法裁定**，必须写清**原因**（取自最近一次驱动运行的 `chain_errors`）
  与**配方**（取自目录的类级 `instance` 字段）—— 不留"待办"。

用法::

    python tools/dispatch_account.py --json schemas/dispatch_account.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console_utf8  # noqa: E402

console_utf8.enable()

CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
VERDICT_TABLE = ROOT / "schemas" / "name_verdicts.json"
EVIDENCE_GLOB = "_p12u_gate/r*/name_verdicts.json"


def mismatches(cat: dict) -> list:
    out = []
    for cls, info in cat["classes"].items():
        for kind in ("methods", "properties"):
            for name, entry in (info.get(kind) or {}).items():
                sig = entry.get("signature_name")
                if sig and sig != name:
                    out.append({"class": cls, "heading": name,
                                "signature": sig, "kind": kind})
    return out


def latest_evidence() -> dict:
    """最近一次驱动运行的证据（取 mtime 最新者），用于取"为什么取不到"。"""
    best, best_m = None, -1.0
    for p in sorted(ROOT.glob(EVIDENCE_GLOB)):
        m = p.stat().st_mtime
        if m > best_m:
            best, best_m = p, m
    if best is None:
        return {}
    try:
        data = json.loads(best.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    data["_path"] = str(best.relative_to(ROOT))
    return data


def account(cat: dict | None = None, table: dict | None = None,
            evidence: dict | None = None) -> dict:
    cat = cat or json.loads(CATALOG.read_text(encoding="utf-8"))
    try:
        table = table if table is not None else json.loads(
            VERDICT_TABLE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        table = {}
    ev = evidence if evidence is not None else latest_evidence()
    resolved = table.get("resolved") or {}
    errors = ev.get("chain_errors") or {}
    rows = []
    for pair in mismatches(cat):
        cls, heading = pair["class"], pair["heading"]
        entry = ((cat["classes"].get(cls) or {}).get("methods") or {}).get(heading)
        got = (resolved.get(cls) or {}).get(heading)
        if got:
            rows.append({**pair, "state": "verdict", "resolved": got,
                         "source": (entry or {}).get("dispatch_source")
                         or "verdict:GetIDsOfNames"})
            continue
        info = cat["classes"].get(cls) or {}
        obtained = (ev.get("obtained_via") or {}).get(cls)
        if obtained:
            # 实例拿到了、名字仍解析不出来 → 是**探针侧**的限制（对象形态），
            # 不能说成"宿主不认"（R38/R39 两次假否证都出在这里）
            reason = ("实例已取到（" + str(obtained) + "）但名字解析失败："
                      "该对象形态不支持 GetIDsOfNames（探针侧限制，非宿主否证）")
        else:
            reason = errors.get(cls, "未取到实例（原因未记录）")
        rows.append({
            **pair, "state": "nyi", "reason": reason,
            "recipe": info.get("instance") or "（手册未给实例配方）",
            "evidence": ev.get("_path"),
        })
    counts = {"total": len(rows),
              "verdict": sum(1 for r in rows if r["state"] == "verdict"),
              "nyi": sum(1 for r in rows if r["state"] == "nyi")}
    return {"counts": counts, "rows": rows,
            "verdict_tally": table.get("tally"),
            "evidence": ev.get("_path")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="标题/签名分歧总账")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)
    data = account()
    print("[account] 分歧 " + str(data["counts"]["total"])
          + " 处：已裁定 " + str(data["counts"]["verdict"])
          + " / 终态 NYI " + str(data["counts"]["nyi"]))
    for row in data["rows"]:
        if row["state"] == "verdict":
            print("   裁定  " + row["class"] + "." + row["heading"]
                  + " -> " + row["resolved"])
        else:
            print("   NYI   " + row["class"] + "." + row["heading"]
                  + " :: " + str(row["reason"])[:90])
            print("         配方: " + str(row["recipe"])[:90])
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                             encoding="utf-8")
        print("[account] 已写 " + str(args.json))
    ok = (data["counts"]["verdict"] + data["counts"]["nyi"]
          == data["counts"]["total"])
    print("SUMMARY: " + json.dumps({"passed": bool(ok),
                                    **data["counts"]}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
