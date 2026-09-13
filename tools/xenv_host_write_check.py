#!/usr/bin/env python3
"""R7-4：按**实测键**反向写宿主（写 main.xenv → 宿主 COM 回读）。

R6-5 用「宿主改设置 → diff xenv」拿到了 5 条键映射；本工具走反方向：

  1. 直接把值写进宿主工程 main.xenv 的 FACET.* 键（pphxml.set_xenv_value）；
  2. 克隆容器；
  3. 宿主 OpenProject → 用 MeshingGroupSetting 的 getter **回读**这些设置。

验收：≥3 个字段「写进去 = 读回来」且宿主全绿（err=0、SNode/MDL/OCT 在场）。
若 getter 不返回写入值，说明该键还有联动前置（如 USE_SIMPLE_SETTING），这也是结论。

用法::

    python tools/xenv_host_write_check.py --json out.json
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

import pphwriter  # noqa: E402
import pphxml  # noqa: E402
from pph_parser import PphArchive  # noqa: E402

WORK = ROOT / "_p12u_gate"
BASE = ROOT / "box.pph"

#: (xenv 键, 写入值, getter, 说明) —— 键名全部来自 R6-5 实测
WRITES = [
    ("SIMPLE_MAX_ANGLE", "8", "GetFacetSimpleMaxAngle", "角度=8"),
    ("SIMPLE_MAX_WIDTH", "9", "GetFacetSimpleMaxWidth", "最大宽度=9"),
    ("USE_DETAIL_MAX_WIDTH", "false", "GetFacetUseDetailMaxWidth",
     "细节最大宽度=off"),
]
SECTION = "FACET"


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


def write_keys(base: Path, out_pph: Path) -> dict:
    xenv = _xenv_of(base)
    if xenv is None:
        return {"ok": False, "error": "base has no main.xenv"}
    before = {k: xenv.get(SECTION, k) for k, _, _, _ in WRITES}
    for key, val, _getter, _label in WRITES:
        pphxml.set_xenv_value(xenv, SECTION, key, val)
    data = pphxml.serialize_xenv(xenv)
    pphwriter.clone_pph(str(base), str(out_pph), {"main.xenv": data})
    after = _xenv_of(out_pph)
    stored = {k: after.get(SECTION, k) for k, _, _, _ in WRITES}
    return {"ok": all(stored[k] == v for k, v, _, _ in WRITES),
            "before": before, "written": {k: v for k, v, _, _ in WRITES},
            "stored": stored, "pph": str(out_pph)}


def host_readback(pph: Path) -> dict:
    q = chr(34)
    p12e = _load("p12e_run_r74", ROOT / "tools" / "_p12e_e2e_run.py")
    p12m = _load("p12m_run_r74", ROOT / "tools" / "_p12m_j1_run.py")
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
        "Set MGS_ = MG_.GetMeshingGroupSetting",
    ]
    for key, _val, getter, _label in WRITES:
        acts.append(p12m._w("read_" + key, "MGS_." + getter))
    acts += [
        p12m._w("mesh_exists", "MG_.DoesMeshExist"),
        "Doc_.SaveProject " + q + (WORK / "r7_4_rewritten.pph").as_posix() + q,
    ]
    vbs = WORK / "r74_write.vbs"
    log = WORK / "r74_write.log"
    if log.is_file():
        log.unlink()
    p12e._write_ansi_vbs(
        p12e.logged_script([("r74", acts)], log, "R7-4 host write check"),
        vbs, "R7-4 host write check")
    import automation.host_boot as host_boot
    pid = host_boot.cold_boot()
    print("[r7-4] cold boot pid=" + str(pid), flush=True)
    err = None
    try:
        p12e.run_e2e("r74_write", vbs, log, timeout=900.0, idle_limit=600.0,
                     retry_with_boot=True)
    except Exception as exc:  # noqa: BLE001
        err = type(exc).__name__ + ": " + str(exc)
    text = (log.read_text(encoding="utf-8", errors="replace")
            if log.is_file() else "")
    ver = p12e.verify_log(text)
    reads = {}
    for key, _val, _getter, _label in WRITES:
        m = re.search("read_" + key + r"=(\S+)", text)
        if m:
            reads[key] = m.group(1)
    return {"error": err, "err0": ver.get("err0"), "total": ver.get("total"),
            "alive": ver.get("alive"), "reads": reads}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R7-4 反向写宿主键回读")
    ap.add_argument("--base", type=Path, default=BASE)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)
    WORK.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    result = {"base": str(args.base),
              "writes": [{"key": k, "value": v, "getter": g}
                         for k, v, g, _ in WRITES]}
    result["offline"] = write_keys(args.base, WORK / "r7_4_written.pph")
    print("[r7-4] 离线写入: " + json.dumps(
        {k: result["offline"].get(k) for k in ("ok", "before", "stored")},
        ensure_ascii=False), flush=True)
    if result["offline"].get("ok"):
        try:
            result["host"] = host_readback(WORK / "r7_4_written.pph")
        except Exception as exc:  # noqa: BLE001
            result["host"] = {"error": type(exc).__name__ + ": " + str(exc)}
        h = result["host"]
        print("[r7-4] 宿主回读: " + json.dumps(
            {k: h.get(k) for k in ("err0", "total", "reads", "error")},
            ensure_ascii=False), flush=True)
        want = {k: v for k, v, _, _ in WRITES}
        got = h.get("reads") or {}
        # VBS 的 CStr(Boolean) 是 "True"/"False"：布尔比较需忽略大小写
        hits = sum(1 for k, v in want.items()
                   if str(got.get(k, "")).strip().lower()
                   == str(v).strip().lower())
        result["hits"] = hits
        result["host_ok"] = (h.get("error") is None
                             and h.get("err0") == h.get("total"))
    else:
        result["hits"] = 0
        result["host_ok"] = False
    result["seconds"] = round(time.time() - t0, 1)
    result["passed"] = bool(result["host_ok"] and result["hits"] >= 3)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print("SUMMARY: " + json.dumps(
        {"passed": result["passed"], "hits": result["hits"]},
        ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
