#!/usr/bin/env python3
"""单变量逐档增量探针：setter ↔ 宿主 xenv 键（R29 口径，R30-1 首用）。

口径（docs/CODE_STATE_AUDIT_20260906.md §43 ★）：

    键映射必须**一次只改一个 setter**、**逐档 SaveProject**、**逐档增量 diff**；
    多 setter 同改只能做段落粗筛，**不得据以给出否证**（R26/R28 的假否证即此来）。

做法：

  1. 冷启宿主 → OpenProject(base)；
  2. 每一档：**新取**一次 QueryMeshingGroupByIndex(0).GetMeshingGroupSetting
     → 调一个 setter（**只调这一个**）→ 取返回值 → 可选 getter 读回
     → SaveProject step<n>.pph；
  3. 离线逐档 diff main.xenv：delta_vs_prev（增量归属）、delta_vs_base。

与 R29 一次性脚本的差别（本工具固化了两处改进）：

  * 每档记 **setter 返回值**（Set* 多数返回 True/False）—— 不经 xenv 也能判成败；
  * 每档记 **getter 读回**——「写进去了但 xenv 没动」与「根本没写进去」由此可分。

档位语法 SETTER=VALUE[:GETTER]（SETTER 可空 = 纯读档）：::

    python tools/xenv_setter_probe.py --no-host \
        --case "=:GetVoxelOctRefineType" \
        --case "SetVoxelOctRefineType=speed:GetVoxelOctRefineType"
    python tools/xenv_setter_probe.py --tag r30_voxel \
        --case "SetVoxelOctRefineType=speed:GetVoxelOctRefineType"

取值按字面量推断类型：true/false → 布尔、整数 → 整数、1.5 → 浮点、
其余 → **字符串（VBS 自动加引号）**。字符串档不能写成裸标识符，否则 VBScript
把它当变量名解析，错误被 On Error Resume Next 吞掉，得到**假否证**。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console_utf8  # noqa: E402

console_utf8.enable()

from pph_parser import PphArchive  # noqa: E402
import pphxml  # noqa: E402

WORK = ROOT / "_p12u_gate"
BASE = ROOT / "box.pph"

_CASE_RE = re.compile(r"^([A-Za-z_]\w*)?=(.*?)(?::([A-Za-z_]\w*))?$")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def parse_case(text: str) -> dict:
    """SETTER=VALUE[:GETTER] -> dict（SETTER 空 = 纯读档）。"""
    m = _CASE_RE.match(text.strip())
    if not m:
        raise ValueError("档位语法应为 SETTER=VALUE[:GETTER]：" + text)
    setter, value, getter = m.group(1) or "", m.group(2), m.group(3)
    if not setter and not getter:
        raise ValueError("空档必须带 getter（否则该档没有任何动作）：" + text)
    return {"setter": setter, "value": value, "getter": getter,
            "value_literal": vbs_literal(value) if setter else None}


def vbs_literal(text: str) -> str:
    """按字面量推断 VBS 取值表达式（字符串必须带引号 —— 见模块 docstring）。"""
    low = text.strip().lower()
    if low in ("true", "false"):
        return "True" if low == "true" else "False"
    body = text.strip()
    try:
        return str(int(body))
    except ValueError:
        pass
    try:
        return repr(float(body))
    except ValueError:
        pass
    return '"' + body.replace('"', '""') + '"'


def build_actions(base: Path, cases: list, steps_dir: Path) -> list:
    """单会话逐档脚本：每档只改一个 setter，逐档 SaveProject。"""
    q = chr(34)
    acts = [
        "Set App_ = GetApplication()",
        "If App_ Is Nothing Then Set App_ = "
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        "RetWW0_ = Doc_.WaitForWorker",
        "Doc_.OpenProject " + q + base.as_posix() + q + ", False",
        "RetWW1_ = Doc_.WaitForWorker",
    ]
    for i, case in enumerate(cases):
        n = str(i)
        acts += [
            "Set MG" + n + "_ = Doc_.QueryMeshingGroupByIndex(0)",
            "Set MGS" + n + "_ = MG" + n + "_.GetMeshingGroupSetting",
        ]
        if case["setter"]:
            acts += [
                "V" + n + "_ = " + case["value_literal"],
                "RetS" + n + "_ = MGS" + n + "_." + case["setter"]
                + "(V" + n + "_)",
                'out_.WriteLine "set' + n + '_ret=" & CStr(RetS' + n
                + '_) & " err=" & CStr(Err.Number)',
                "Err.Clear",
            ]
        if case["getter"]:
            acts += [
                "RetG" + n + "_ = MGS" + n + "_." + case["getter"],
                'out_.WriteLine "get' + n + '_val=" & CStr(RetG' + n
                + '_) & " err=" & CStr(Err.Number)',
                "Err.Clear",
            ]
        acts.append("Doc_.SaveProject " + q
                    + (steps_dir / ("step" + n + ".pph")).as_posix() + q)
    return acts


def xenv_of(pph: Path):
    arch = PphArchive.open(str(pph))
    names = [m.name for m in arch.members if m.name == "main.xenv"]
    if not names:
        return None
    return pphxml.parse_xenv(arch.read_member(names[0]))


def flatten(xenv) -> dict:
    return {sec + "." + k: v
            for sec, keys in xenv.sections.items() for k, v in keys.items()}


def diff_keys(before: dict, after: dict) -> dict:
    return {k: {"before": before.get(k), "after": v}
            for k, v in after.items() if before.get(k) != v}


def read_log_values(text: str) -> dict:
    """取 setN_ret / getN_val（每档唯一，不会被后档覆盖）。"""
    out = {}
    for m in re.finditer(r"^(set\d+_ret|get\d+_val)=(\S*) err=(-?\d+)$",
                         text, re.MULTILINE):
        out[m.group(1)] = {"value": m.group(2), "err": int(m.group(3))}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="单变量逐档增量键探针")
    ap.add_argument("--base", type=Path, default=BASE)
    ap.add_argument("--case", action="append", default=[],
                    help="SETTER=VALUE[:GETTER]，可重复")
    ap.add_argument("--tag", default="setter_probe")
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--keep-host", action="store_true")
    ap.add_argument("--no-host", action="store_true")
    args = ap.parse_args(argv)
    if not args.case:
        ap.error("至少一个 --case")
    cases = [parse_case(c) for c in args.case]
    steps_dir = WORK / args.tag
    steps_dir.mkdir(parents=True, exist_ok=True)
    result = {"tag": args.tag, "base": str(args.base), "cases": cases,
              "steps_dir": str(steps_dir)}

    before = xenv_of(args.base)
    if before is None:
        print("SUMMARY: " + json.dumps({"passed": False,
                                        "error": "base has no main.xenv"}))
        return 1
    base_flat = flatten(before)

    p12e = _load("p12e_run_" + args.tag, ROOT / "tools" / "_p12e_e2e_run.py")
    vbs = steps_dir / (args.tag + ".vbs")
    log = steps_dir / (args.tag + ".log")
    if args.no_host:
        p12e._write_ansi_vbs(
            p12e.logged_script([(args.tag, build_actions(
                args.base, cases, steps_dir))], log,
                "setter probe " + args.tag), vbs,
            "setter probe " + args.tag)
        print("[probe] 计划 " + str(len(cases)) + " 档 -> " + str(vbs))
        for c in cases:
            print("        " + c["setter"] + "(" + str(c["value_literal"])
                  + ") getter=" + str(c["getter"]))
        print("SUMMARY: " + json.dumps({"passed": True, "dry": True}))
        return 0

    import automation.host_boot as host_boot
    if log.is_file():
        log.unlink()
    p12e._write_ansi_vbs(
        p12e.logged_script([(args.tag, build_actions(args.base, cases,
                                                     steps_dir))], log,
                           "setter probe " + args.tag), vbs,
        "setter probe " + args.tag)
    t0 = time.time()
    pid = host_boot.cold_boot()
    print("[probe] cold boot pid=" + str(pid), flush=True)
    err = None
    try:
        p12e.run_e2e(args.tag, vbs, log, timeout=args.timeout,
                     idle_limit=min(args.timeout, 600.0), retry_with_boot=True)
    except Exception as exc:  # noqa: BLE001
        err = type(exc).__name__ + ": " + str(exc)
    text = (log.read_text(encoding="utf-8", errors="replace")
            if log.is_file() else "")
    ver = p12e.verify_log(text)
    result["host"] = {"error": err, "err0": ver.get("err0"),
                      "total": ver.get("total"),
                      "seconds": round(time.time() - t0, 1)}
    result["readbacks"] = read_log_values(text)

    prev = base_flat
    per_case = []
    for i, case in enumerate(cases):
        step = steps_dir / ("step" + str(i) + ".pph")
        row = {"index": i, "setter": case["setter"], "value": case["value"],
               "getter": case["getter"],
               "set_ret": result["readbacks"].get("set" + str(i) + "_ret"),
               "get_val": result["readbacks"].get("get" + str(i) + "_val"),
               "saved": step.is_file()}
        if step.is_file():
            x = xenv_of(step)
            flat = flatten(x) if x is not None else {}
            row["delta_vs_prev"] = diff_keys(prev, flat)
            row["delta_vs_base"] = diff_keys(base_flat, flat)
            prev = flat
        per_case.append(row)
    result["per_case"] = per_case
    if not args.keep_host:
        result["killed_hosts"] = host_boot.kill_all_hosts()
    fail_rows = [r for r in per_case
                 if (r.get("set_ret") or {}).get("err", 0) != 0
                 or (r.get("get_val") or {}).get("err", 0) != 0]
    result["passed"] = bool(err is None and ver.get("total")
                            and ver.get("bad") == 0 and not fail_rows)
    print("[probe] 档位结果: " + json.dumps(
        [{"i": r["index"], "setter": r["setter"], "value": r["value"],
          "set_ret": (r.get("set_ret") or {}).get("value"),
          "get": (r.get("get_val") or {}).get("value"),
          "delta": sorted((r.get("delta_vs_prev") or {}).keys())}
         for r in per_case], ensure_ascii=False), flush=True)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print("SUMMARY: " + json.dumps({"passed": result["passed"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
