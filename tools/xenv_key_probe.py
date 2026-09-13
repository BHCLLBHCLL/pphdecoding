#!/usr/bin/env python3
"""R6-5：MeshParam → 宿主 key 映射核实（宿主改一项、xenv 差分定位）。

做法（不猜键名）：

  1. 取宿主原生工程（默认 box.pph）的 main.xenv 作基线；
  2. 用 COM 打开工程、在 **MeshingGroupSetting** 上改 2–3 项 facet 设置
     （如 SimpleChordTol / SimpleMaxAngle / UseAbsoluteValue）；
  3. SaveProject 到新工程；
  4. 离线 diff 两份 main.xenv → 值发生变化的键**就是**这些设置的真实宿主键。

这样得到的映射可以直接用于 R6-4 之后的「写宿主键」而不会猜错（写错宿主键
会真的改变宿主网格行为，代价高于本工具自己存一份）。

用法::

    python tools/xenv_key_probe.py                # 实机 + diff
    python tools/xenv_key_probe.py --no-host      # 只打印计划（离线）
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console_utf8  # noqa: E402

console_utf8.enable()

import pphxml  # noqa: E402
from pph_parser import PphArchive  # noqa: E402

WORK = ROOT / "_p12u_gate"
BASE = ROOT / "box.pph"

#: (setter 名, 参数, 新值, 说明) —— 只改 facet 数值项，不动网格器选择
#: R10-3：新一批待核实键（前一批 5 条已在 R6-5/R7-4 定谳）
EDITS = [
    ("SetFacetUseSimpleSetting", [False], "UseSimpleSetting=false"),
    ("SetMDLMethod", [0], "MDLMethod=0"),
    ("SetFacetDetailChordAngle", [20.0], "DetailChordAngle=20"),
]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _xenv_of(pph: Path):
    arch = PphArchive.open(str(pph))
    names = [m.name for m in arch.members if m.name == "main.xenv"]
    if not names:
        return None
    return pphxml.parse_xenv(arch.read_member(names[0]))


def actions(pph: Path, out_pph: Path) -> list:
    p12m = _load("p12m_run_r65", ROOT / "tools" / "_p12m_j1_run.py")
    q = chr(34)
    acts = [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        "RetWW0_ = Doc_.WaitForWorker",
        "Doc_.OpenProject " + q + pph.as_posix() + q + ", False",
        "RetWW1_ = Doc_.WaitForWorker",
        "Set MG_ = Doc_.QueryMeshingGroupByIndex(0)",
        "Set MGS_ = MG_.GetMeshingGroupSetting",
        p12m._w("mesher_before", "MGS_.GetMesher"),
        p12m._w("surf_before", "MGS_.GetSurfMesher"),
        p12m._w("chord_before", "MGS_.GetFacetSimpleChordTol"),
        p12m._w("angle_before", "MGS_.GetFacetSimpleMaxAngle"),
        p12m._w("width_before", "MGS_.GetFacetSimpleMaxWidth"),
        p12m._w("detailw_before", "MGS_.GetFacetUseDetailMaxWidth"),
    ]
    for i, (setter, params, label) in enumerate(EDITS):
        for j, val in enumerate(params):
            acts.append("P" + str(i) + str(j) + "_ = " + (
                "True" if val is True else "False" if val is False
                else str(val)))
            args = ", ".join("P" + str(i) + str(k)
                             for k in range(len(params)))
            acts.append("MGS_." + setter + " " + args)
        acts.append(p12m._w("edit" + str(i) + "_err", "Err.Number"))
    acts += [
        "Set MGS2_ = MG_.GetMeshingGroupSetting",
        p12m._w("chord_after", "MGS2_.GetFacetSimpleChordTol"),
        p12m._w("angle_after", "MGS2_.GetFacetSimpleMaxAngle"),
        p12m._w("width_after", "MGS2_.GetFacetSimpleMaxWidth"),
        p12m._w("detailw_after", "MGS2_.GetFacetUseDetailMaxWidth"),
        "Doc_.SaveProject " + q + out_pph.as_posix() + q,
    ]
    return acts


def diff(before, after, limit: int = 40) -> dict:
    changed = {}
    for sec, keys in after.sections.items():
        for k, v in keys.items():
            old = before.get(sec, k, None)
            if old != v:
                changed[sec + "." + k] = {"before": old, "after": v}
    missing = {sec + "." + k: v
               for sec, keys in before.sections.items()
               for k, v in keys.items()
               if after.get(sec, k, None) is None}
    return {"changed": dict(list(changed.items())[:limit]),
            "changed_count": len(changed),
            "missing_count": len(missing),
            "missing_sample": dict(list(missing.items())[:10])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R6-5 宿主 key 映射核实")
    ap.add_argument("--base", type=Path, default=BASE)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--no-host", action="store_true")
    args = ap.parse_args(argv)
    WORK.mkdir(parents=True, exist_ok=True)
    out_pph = WORK / "r6_5_keyprobe.pph"
    result = {"base": str(args.base),
              "edits": [{"setter": s, "params": p, "label": l}
                        for s, p, l in EDITS]}
    before = _xenv_of(args.base)
    if before is None:
        print("SUMMARY: " + json.dumps({"passed": False,
                                        "error": "base has no main.xenv"}))
        return 1
    if args.no_host:
        print("[r6-5] 计划改动: " + json.dumps([l for _, _, l in EDITS]))
        print("SUMMARY: " + json.dumps({"passed": True, "dry": True}))
        return 0
    p12e = _load("p12e_run_r65", ROOT / "tools" / "_p12e_e2e_run.py")
    p12e.utf8_stdout()
    import automation.host_boot as host_boot
    vbs = WORK / "r65_keys.vbs"
    log = WORK / "r65_keys.log"
    if log.is_file():
        log.unlink()
    p12e._write_ansi_vbs(
        p12e.logged_script([("r65", actions(args.base, out_pph))], log,
                           "R6-5 key probe"), vbs, "R6-5 key probe")
    t0 = time.time()
    pid = host_boot.cold_boot()
    print("[r6-5] cold boot pid=" + str(pid), flush=True)
    err = None
    try:
        p12e.run_e2e("r65_keys", vbs, log, timeout=900.0, idle_limit=600.0,
                     retry_with_boot=True)
    except Exception as exc:  # noqa: BLE001
        err = type(exc).__name__ + ": " + str(exc)
    text = (log.read_text(encoding="utf-8", errors="replace")
            if log.is_file() else "")
    ver = p12e.verify_log(text)
    result["host"] = {"error": err, "err0": ver.get("err0"),
                      "total": ver.get("total"),
                      "alive": ver.get("alive"),
                      "seconds": round(time.time() - t0, 1)}
    for key in ("chord_before", "chord_after", "angle_before", "angle_after",
                "width_before", "width_after", "detailw_before",
                "detailw_after", "mesher_before", "surf_before"):
        m = __import__("re").search(key + r"=(\S+)", text)
        if m:
            result[key] = m.group(1)
    if out_pph.is_file():
        after = _xenv_of(out_pph)
        if after is not None:
            result["xenv_diff"] = diff(before, after)
    print("[r6-5] 宿主: " + json.dumps(
        {k: result.get(k) for k in ("width_before", "width_after",
                                    "detailw_before", "detailw_after",
                                    "angle_before", "angle_after")},
        ensure_ascii=False), flush=True)
    if "xenv_diff" in result:
        print("[r6-5] xenv 变化 " + str(result["xenv_diff"]["changed_count"])
              + " 个键: " + json.dumps(result["xenv_diff"]["changed"][:6]
                                        if isinstance(
            result["xenv_diff"]["changed"], list)
            else result["xenv_diff"]["changed"], ensure_ascii=False),
              flush=True)
    ok = (err is None and ver.get("err0") == ver.get("total")
          and result.get("xenv_diff", {}).get("changed_count", 0) > 0)
    result["passed"] = bool(ok)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print("SUMMARY: " + json.dumps({"passed": result["passed"]},
                                   ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
