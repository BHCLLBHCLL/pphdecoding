#!/usr/bin/env python3
"""R32-1：实测宿主键 → **面板写入口**对账（执行法，不用正则猜）。

背景：R31-1 的提案写「OCT_MESH 6 键里只有 2 条接进面板」——实际是 5 条。
这类前提错误的根因是**没有一张现成的账**：`schemas/host_keys.json` 是账本
（18 条实测键，逐条可追溯到证据文件），本工具把「写入口」算出来：

  1. 逐个面板体实例化 → `load(ctx)` → `apply(ctx)`（offscreen Qt），
     从写出的 `main.xenv` 里读出 `SECTION.KEY` —— **执行得到**，不是扫源码；
  2. `tools/xenv_host_write_check.py` 的 `WRITES`/`WRITES_MORE` 另算一类
     （那是「已实机回读」的键，不等于面板写入口）；
  3. 逐键给结论：面板写入口 / 无写入口（缺口）。

用法::

    $env:QT_QPA_PLATFORM='offscreen'; python tools/host_key_coverage.py --json out.json
    python tools/host_key_coverage.py --no-qt        # 只列账本与实机回读面
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console_utf8  # noqa: E402

console_utf8.enable()

import pphxml  # noqa: E402

LEDGER = ROOT / "schemas" / "host_keys.json"
CHECK = ROOT / "tools" / "xenv_host_write_check.py"

#: 参与对账的面板体（构造签名统一为 () + load(ctx)/apply(ctx)）
BODIES = [
    "MesherFaceterBody", "OctreeParamBody", "MeshParamBody", "NonSolidBody",
    "OptionNavBody", "CreatePartsBody", "ExecuteBody", "RegisterRegionBody",
    "PartMaterialBody", "ImportPartBody", "ModifyPartsBody",
    "PartsControlBody",
]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_ledger(path: Path = LEDGER) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def ledger_ids(ledger: dict) -> list:
    return [e["section"] + "." + e["key"] for e in ledger["keys"]]


def host_readback_ids(check_path: Path = CHECK) -> list:
    """已实机回读的键（WRITES + WRITES_MORE）。"""
    chk = _load("xhw_coverage", check_path)
    out = [chk.SECTION + "." + k for k, _v, _g, _l in chk.WRITES]
    out += [s + "." + k for s, k, _v, _g, _e, _l in chk.WRITES_MORE]
    return out


def panel_writes(bodies: list = BODIES) -> tuple:
    """执行各面板体的 apply() → ({'SEC.KEY': [体名]}, {体名: 错误})。"""
    import nav_panels
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(
        ["coverage", "-platform", "offscreen"])
    written: dict = {}
    errors: dict = {}
    for name in bodies:
        cls = getattr(nav_panels, name, None)
        if cls is None:
            errors[name] = "no such body"
            continue
        xenv = pphxml.XenvSettings()
        ctx = {"xenv": xenv, "session": {}, "xml": None}
        try:
            body = cls()
            body.load(ctx)
            body.apply(ctx)
        except Exception as exc:  # noqa: BLE001
            errors[name] = type(exc).__name__ + ": " + str(exc)
            continue
        for sec, keys in xenv.sections.items():
            for k in keys:
                written.setdefault(sec + "." + k, []).append(name)
    del app  # 保活到函数结束（Qt 需要存活实例）
    return written, errors


def report(*, use_qt: bool = True) -> dict:
    ledger = load_ledger()
    ids = ledger_ids(ledger)
    host = host_readback_ids()
    written, errors = panel_writes() if use_qt else ({}, {})
    rows = []
    for entry in ledger["keys"]:
        ident = entry["section"] + "." + entry["key"]
        rows.append({
            "id": ident,
            "round": entry["round"],
            "setter": entry["setter"],
            "evidence": entry["evidence"],
            "panel_bodies": written.get(ident, []),
            "host_readback": ident in host,
        })
    gaps = [r["id"] for r in rows if not r["panel_bodies"]]
    return {
        "ledger_count": len(ids),
        "ledger_duplicates": sorted({i for i in ids if ids.count(i) > 1}),
        "host_readback_count": len(set(host) & set(ids)),
        "panel_written_count": len([r for r in rows if r["panel_bodies"]]),
        "rows": rows,
        "gaps": gaps,
        "known_gaps": ledger.get("known_gaps") or [],
        "known_gap_status": ledger.get("known_gap_status") or {},
        "body_errors": errors,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="实测宿主键 → 面板写入口对账")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--no-qt", action="store_true")
    args = ap.parse_args(argv)
    data = report(use_qt=not args.no_qt)
    print("[coverage] 账本 " + str(data["ledger_count"]) + " 条，"
          + "面板写入口 " + str(data["panel_written_count"]) + " 条，"
          + "实机回读 " + str(data["host_readback_count"]) + " 条")
    for row in data["rows"]:
        mark = ",".join(row["panel_bodies"]) or "--"
        print("   " + row["id"].ljust(44)
              + ("[host] " if row["host_readback"] else "       ")
              + mark)
    if data["body_errors"]:
        print("[coverage] 未能执行的面板体: "
              + json.dumps(data["body_errors"], ensure_ascii=False))
    print("[coverage] 缺口（无面板写入口）: " + json.dumps(data["gaps"]))
    print("[coverage] 已声明缺口: " + json.dumps(data["known_gaps"]))
    for gid, info in (data.get("known_gap_status") or {}).items():
        print("   - " + gid + " [" + str(info.get("status")) + "] :: "
              + str(info.get("reason")))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    ok = (not data["ledger_duplicates"]
          and data["gaps"] == data["known_gaps"])
    print("SUMMARY: " + json.dumps({"passed": bool(ok), "gaps":
                                    len(data["gaps"])}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
