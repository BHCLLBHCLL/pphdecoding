#!/usr/bin/env python3
"""R4-4：面板状态落盘验收（main.xenv 通道 + 宿主零破坏）。

链路：

  1. 读宿主工程（默认 box.pph）的 main.xenv；
  2. 用 nav_panels.panel_xenv_set 把 OptionNavBody 的三项开关写进
     [OPTION_NAV]（R4-3 审计出的 memory_only 面板之一，R4-4 首批落盘）；
  3. **离线闭环**：pphwriter.clone_pph 以新 main.xenv 重写容器 → 重新解析
     → 断言三项值原样回来（等价于「重启后设置保留」）；
  4. **宿主闭环**（--no-host 跳过）：OpenProject → SNode / MeshingGroup /
     GetVMDL / DoesMeshExist / bbox 全绿 err=0 —— 证明多出一个 xenv 段
     不会破坏宿主读工程。

用法：

    python tools/panel_persist_check.py                 # 离线 + 宿主
    python tools/panel_persist_check.py --no-host       # 只做离线闭环
    python tools/panel_persist_check.py --json out.json
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

import nav_panels  # noqa: E402
import pphwriter  # noqa: E402
import pphxml  # noqa: E402
from pph_parser import PphArchive  # noqa: E402

WORK = ROOT / "_p12u_gate"
BASE = ROOT / "box.pph"
SECTION = "OPTION_NAV"
VALUES = {"always_show_wizard": True, "show_bam_item": False,
          "show_mesher_item": True}


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
        return None, None
    return arch, pphxml.parse_xenv(arch.read_member(names[0]))


def offline_roundtrip(base: Path, out_pph: Path) -> dict:
    _arch, xenv = _xenv_of(base)
    if xenv is None:
        return {"ok": False, "error": "base has no main.xenv"}
    ctx = {"xenv": xenv, "session": {}}
    wrote = nav_panels.panel_xenv_set(
        ctx, SECTION,
        {k: nav_panels.panel_bool_str(v) for k, v in VALUES.items()})
    data = pphxml.serialize_xenv(xenv)
    pphwriter.clone_pph(str(base), str(out_pph), {"main.xenv": data})
    # 离线「重启」：重新打开容器、重新解析 xenv
    _arch2, xenv2 = _xenv_of(out_pph)
    got = {} if xenv2 is None else {k: xenv2.get(SECTION, k) for k in VALUES}
    want = {k: nav_panels.panel_bool_str(v) for k, v in VALUES.items()}
    # 再用面板自身读端回读（xenv 优先 / session 兜底）
    ctx2 = {"xenv": xenv2, "session": {}}
    read_back = {k: nav_panels.panel_xenv_get(ctx2, SECTION, k, "<missing>")
                 for k in VALUES}
    return {"ok": bool(wrote) and got == want and read_back == want,
            "wrote": wrote, "xenv_dirty": bool(ctx.get("xenv_dirty")),
            "written": want, "reparsed": got, "panel_readback": read_back,
            "pph": str(out_pph), "xenv_bytes": len(data)}


def host_reopen(out_pph: Path, work: Path) -> dict:
    gate = _load("cad_gate_r44", ROOT / "tools" / "cad_pipeline_gate.py")
    p12e = _load("p12e_run_r44", ROOT / "tools" / "_p12e_e2e_run.py")
    p12e.utf8_stdout()
    import automation.host_boot as host_boot
    pid = host_boot.cold_boot()
    print("[r4-4] cold boot pid=" + str(pid), flush=True)
    res = gate._run(p12e, "r44_xenv",
                    gate.reopen_actions(out_pph, work / "r4_4_reopened.pph"),
                    work, timeout=900.0, idle_limit=600.0)
    res["mesh_exists"] = (res.get("info") or {}).get("mesh_exists")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R4-4 面板落盘验收")
    ap.add_argument("--base", type=Path, default=BASE)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--no-host", action="store_true")
    args = ap.parse_args(argv)
    work = WORK
    work.mkdir(parents=True, exist_ok=True)
    out_pph = work / "r4_4_xenv.pph"
    t0 = time.time()
    result = {"base": str(args.base), "section": SECTION,
              "values": {k: nav_panels.panel_bool_str(v)
                         for k, v in VALUES.items()}}
    result["offline"] = offline_roundtrip(args.base, out_pph)
    print("[r4-4] 离线闭环: " + json.dumps(
        {k: result["offline"].get(k) for k in
         ("ok", "wrote", "xenv_dirty", "written", "reparsed")},
        ensure_ascii=False), flush=True)
    if not args.no_host and result["offline"].get("ok"):
        try:
            host = host_reopen(out_pph, work)
        except Exception as exc:  # noqa: BLE001
            host = {"ok": False, "error": type(exc).__name__ + ": " + str(exc)}
        result["host"] = host
        print("[r4-4] 宿主重开: " + json.dumps(
            {"ok": host.get("ok"), "err0": host.get("err0"),
             "total": host.get("total"), "alive": host.get("alive"),
             "mesh_exists": host.get("mesh_exists"),
             "error": host.get("error")}, ensure_ascii=False), flush=True)
    result["seconds"] = round(time.time() - t0, 1)
    offline_ok = bool(result["offline"].get("ok"))
    host_ok = ("host" not in result) or bool(result["host"].get("ok"))
    result["passed"] = bool(offline_ok and host_ok)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print("SUMMARY: " + json.dumps({"passed": result["passed"]},
                                   ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
