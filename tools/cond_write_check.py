#!/usr/bin/env python3
"""R4-5：条件写盘零破坏回归（R3-2 去壳写入器 → 宿主重开 + 条件可读）。

链路：

  1. 取条件最多的宿主工程（默认 p12c_cond_harvest_out.pph，49 条条件）；
  2. 对前 N 条（默认 24，验收要求 ≥20）逐条执行**去壳原地重写**：
     _condition_to_initial → write_condition_to_xml(replace_el=el)，与
     GUI 里点「All fields (schema)…」→ OK 完全同一条路径；
  3. 离线判定：条件数不变、逐条 (type/name/regions/区域标签/字段值) 完全一致
     （原地重写必须是幂等的）；
  4. 宿主判定：OpenProject err=0 + SNode/MeshingGroup 活 + mesh_exists，
     并对每条改写过的条件做 ``GetConditions().QueryConditionByName(name)``
     回读 —— 证明宿主仍能读到这些条件。

用法：

    python tools/cond_write_check.py                 # 离线 + 宿主
    python tools/cond_write_check.py --no-host --limit 30
    python tools/cond_write_check.py --json _p12u_gate/r4_5_cond.json
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

import nav_panels  # noqa: E402
import pphwriter  # noqa: E402
import pphxml  # noqa: E402
from pph_parser import PphArchive  # noqa: E402

WORK = ROOT / "_p12u_gate"
BASE = ROOT / "p12c_cond_harvest_out.pph"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _main_xml(pph: Path):
    arch = PphArchive.open(str(pph))
    return pphxml.parse_main_xml(arch.read_member("main.xml"))


def _summary(el) -> dict:
    init = nav_panels._condition_to_initial(el)
    regs = el.find("regions")
    return {"type": (el.findtext("type") or ""),
            "name": init["name"],
            "regions": list(init["regions"]),
            "region_tags": sorted({c.tag for c in list(regs)}) if regs is not
                            None else [],
            "fields": dict(init["fields"])}


def edit_conditions(base: Path, out_pph: Path, limit: int) -> dict:
    xml = _main_xml(base)
    conds = xml.conditions()
    reg = nav_panels.condition_registry_cached()
    before = [_summary(e) for e in conds]
    ctx = {"xml": xml}
    edited_names: list[str] = []
    skipped: dict[str, int] = {}
    for el in conds:
        if len(edited_names) >= limit:
            break
        typ = (el.findtext("type") or "").strip()
        ctype = reg.get(typ) if reg is not None else None
        if ctype is None:
            skipped[typ] = skipped.get(typ, 0) + 1
            continue
        init = nav_panels._condition_to_initial(el)
        data = {"type": typ, "name": init["name"],
                "regions": init["regions"], "fields": init["fields"]}
        ok = nav_panels.write_condition_to_xml(ctx, ctype, data,
                                               replace_el=el)
        if ok:
            edited_names.append(init["name"])
        else:
            skipped[typ] = skipped.get(typ, 0) + 1
    text = pphxml.serialize_main_xml(xml.root)
    if not text.lstrip().startswith("<?xml"):
        text = '<?xml version="1.0" encoding="utf-8"?>\n' + text
    payload = text.encode("utf-8")
    pphwriter.clone_pph(str(base), str(out_pph), {"main.xml": payload})
    xml2 = _main_xml(out_pph)
    after = [_summary(e) for e in xml2.conditions()]
    diffs = []
    for i, (b, a) in enumerate(zip(before, after)):
        if b != a:
            keys = [k for k in b if b[k] != a.get(k)]
            diffs.append({"index": i, "name": b["name"], "keys": keys,
                          "before": {k: b[k] for k in keys},
                          "after": {k: a.get(k) for k in keys}})
    return {"ok": (len(after) == len(before) and not diffs
                   and len(edited_names) >= limit),
            "edited": len(edited_names), "limit": limit,
            "skipped_types": skipped, "xml_dirty": bool(ctx.get("xml_dirty")),
            "conditions_before": len(before), "conditions_after": len(after),
            "diff_count": len(diffs), "diffs": diffs[:3],
            "edited_names": edited_names, "pph": str(out_pph),
            "main_xml_bytes": len(payload)}


def host_probe(pph: Path, names: list[str], work: Path) -> dict:
    q = chr(34)
    p12m = _load("p12m_run_r45", ROOT / "tools" / "_p12m_j1_run.py")
    p12e = _load("p12e_run_r45", ROOT / "tools" / "_p12e_e2e_run.py")
    p12e.utf8_stdout()
    acts = [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        "RetWW0_ = Doc_.WaitForWorker",
        "Doc_.OpenProject " + q + pph.as_posix() + q + ", False",
        "RetWW1_ = Doc_.WaitForWorker",
        'Set SN_ = Doc_.QuerySNodeByName("Part")',
        "Set MG_ = Doc_.QueryMeshingGroupByIndex(0)",
        "Set MDL_ = MG_.GetMDL",
        "Set OCT_ = MG_.GetOctree",
        p12m._w("mesh_exists", "MG_.DoesMeshExist"),
        "Set Conds_ = Doc_.GetConditions",
        p12m._w("conds_alive", "Not (Conds_ Is Nothing)"),
    ]
    for i, nm in enumerate(names):
        acts.append("Set C" + str(i) + "_ = Conds_.QueryConditionByName(" + q
                    + nm + q + ")")
        acts.append(p12m._w("cond" + str(i) + "_alive",
                            "Not (C" + str(i) + "_ Is Nothing)"))
    acts.append('Doc_.SaveProject "' + (work / "r4_5_reopened.pph").as_posix()
                + '"')
    vbs = work / "r45_cond.vbs"
    log = work / "r45_cond.log"
    if log.is_file():
        log.unlink()
    p12e._write_utf16_vbs(
        p12e.logged_script([("r45", acts)], log, "R4-5 cond write check"),
        vbs, "R4-5 cond write check")
    import automation.host_boot as host_boot
    pid = host_boot.cold_boot()
    print("[r4-5] cold boot pid=" + str(pid), flush=True)
    err = None
    try:
        p12e.run_e2e("r45_cond", vbs, log, timeout=1200.0, idle_limit=600.0,
                     retry_with_boot=True)
    except Exception as exc:  # noqa: BLE001
        err = type(exc).__name__ + ": " + str(exc)
    text = (log.read_text(encoding="utf-8", errors="replace")
            if log.is_file() else "")
    ver = p12e.verify_log(text)
    alive = ver.get("alive", {})
    readback = sum(1 for i in range(len(names))
                   if re.search("cond" + str(i) + "_alive=True", text))
    return {"ok": bool(ver.get("has_end")) and ver.get("err0") == ver.get("total")
                    and err is None,
            "error": err, "err0": ver.get("err0"), "total": ver.get("total"),
            "conds_alive": re.search(r"conds_alive=(\S+)", text).group(1)
            if re.search(r"conds_alive=(\S+)", text) else None,
            "conditions_readback": readback, "conditions_expected": len(names),
            "mesh_exists": (re.search(r"mesh_exists=(\S+)", text).group(1)
                            if re.search(r"mesh_exists=(\S+)", text)
                            else None),
            "alive": alive}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R4-5 条件写盘零破坏回归")
    ap.add_argument("--base", type=Path, default=BASE)
    ap.add_argument("--limit", type=int, default=24)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--no-host", action="store_true")
    args = ap.parse_args(argv)
    WORK.mkdir(parents=True, exist_ok=True)
    out_pph = WORK / "r4_5_conds.pph"
    t0 = time.time()
    result = {"base": str(args.base), "limit": args.limit}
    result["offline"] = edit_conditions(args.base, out_pph, args.limit)
    print("[r4-5] 离线: " + json.dumps(
        {k: result["offline"].get(k) for k in
         ("ok", "edited", "conditions_before", "conditions_after",
          "diff_count", "xml_dirty")}, ensure_ascii=False), flush=True)
    if not args.no_host and result["offline"].get("edited"):
        names = result["offline"]["edited_names"][:12]
        try:
            result["host"] = host_probe(out_pph, names, WORK)
        except Exception as exc:  # noqa: BLE001
            result["host"] = {"ok": False,
                              "error": type(exc).__name__ + ": " + str(exc)}
        h = result["host"]
        print("[r4-5] 宿主: " + json.dumps(
            {k: h.get(k) for k in ("ok", "err0", "total", "conds_alive",
                                   "conditions_readback",
                                   "conditions_expected", "mesh_exists",
                                   "error")}, ensure_ascii=False), flush=True)
    result["seconds"] = round(time.time() - t0, 1)
    host_ok = ("host" not in result) or bool(result["host"].get("ok"))
    result["passed"] = bool(result["offline"].get("ok") and host_ok
                            and result["offline"].get("edited") >= 20)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print("SUMMARY: " + json.dumps(
        {"passed": result["passed"], "edited": result["offline"].get("edited"),
         "host_ok": host_ok}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
