#!/usr/bin/env python3
"""R1-4：CAD 导入矩阵 —— 多体 / 装配 / 损坏 / 超版本 / Unicode 路径。

对每个用例跑「裸宿主 OpenCadFile → 探针 → SaveProject」，并做**容器差分**
（宿主产物里是否落了 main.sctsnapshot = 是否有几何真正进入文档），从而把
"静默零几何"与"干净业务拒绝"区分开——这正是审计反复强调的判据。

用法：
    python tools/cad_matrix_check.py
    python tools/cad_matrix_check.py --json _p12u_matrix/summary.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import automation.host_boot as host_boot  # noqa: E402

WORK = ROOT / "_p12u_matrix"
D = Path(r"D:\training\3dprint\FunHome-main\funHomeFan\cad\FunDeskFan")

#: (用例名, CAD 路径, 期望) 期望 = "geometry"（应落几何）/ "reject"（应干净拒绝）
CASES = [
    ("xt_multibody", ROOT / "_p12r_step" / "cadthru_base_v7.x_t", "geometry"),
    ("step_ap214", D / "key v2.step", "geometry"),
    ("step_large", D / "top v5.step", "geometry"),
    ("step_unicode", WORK / "中文 目录 空格" / "键 v2 模型.step", "geometry"),
    ("step_corrupt", WORK / "corrupt.step", "reject"),
    ("step_garbage", WORK / "garbage.step", "reject"),
]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _members(pph: Path) -> dict:
    if not pph.is_file():
        return {}
    with zipfile.ZipFile(pph) as z:
        names = z.namelist()
        return {"count": len(names),
                "has_snapshot": "main.sctsnapshot" in names,
                "mdl": [n for n in names if n.endswith((".mdl", ".oct"))]}


def run_case(p12e, p12n, name: str, cad: Path, out_pph: Path) -> dict:
    vbs = WORK / f"r14_{name}.vbs"
    log = WORK / f"r14_{name}.log"
    if log.is_file():
        log.unlink()
    groups = p12n.build_cadmatrix_groups(cad, out_pph, name)
    script = p12e.logged_script(groups, log, f"R1-4 {name}")
    # R1-4 实测：ANSI(mbcs) 通道无法承载非 ASCII 路径（中文目录直接抛
    # UnicodeEncodeError）——含非 ASCII 时改走 UTF-16 通道。
    if any(ord(ch) > 127 for ch in str(cad)):
        p12e._write_utf16_vbs(script, vbs, f"R1-4 {name}")
    else:
        p12e._write_ansi_vbs(script, vbs, f"R1-4 {name}")
    t0 = time.time()
    try:
        p12e.run_e2e(name, vbs, log, timeout=900.0, retry_with_boot=True)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    ver = p12e.verify_log(text)
    rec = {m.group(1): m.group(2) for m in re.finditer(
        r"^(sn__alive|sn2__alive|sn3__alive|parts_ub|parts2_ub)=(\S+)", text,
        re.MULTILINE)}
    bm = re.search(r"^bbox.*$", text, re.MULTILINE)
    mem = _members(out_pph)
    return {"seconds": round(time.time() - t0, 1),
            "has_end": ver.get("has_end"), "err0": ver.get("err0"),
            "total": ver.get("total"), "probe": rec,
            "bbox": bm.group(0) if bm else None, "members": mem}


def judge(case: str, expectation: str, rec: dict) -> tuple:
    """→ (ok, verdict)。核心判据：期望落几何者必须有 snapshot 成员；
    期望拒绝者必须**没有** snapshot（否则就是静默零几何的反面——悄悄塞了东西）。
    """
    err = rec.get("error")
    if err:
        return False, "error: " + str(err)
    if not rec.get("has_end"):
        return False, "no end marker (truncated/hung)"
    if rec.get("err0") != rec.get("total"):
        return False, ("nonzero err: " + str(rec.get("total")) + " steps, "
                       + str(rec.get("err0")) + " ok")
    snap = bool(rec.get("members", {}).get("has_snapshot"))
    if expectation == "geometry":
        if snap:
            return True, "geometry landed (snapshot present)"
        return False, "no geometry landed (silent zero-geometry)"
    if snap:
        return False, ("expected reject but geometry landed: "
                       + str(rec.get("members")))
    return True, "clean business reject (no geometry, no hang)"

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R1-4 CAD 导入矩阵")
    ap.add_argument("--json", type=Path, default=WORK / "r1_4_summary.json")
    ap.add_argument("--cases", default=None,
                    help="逗号分隔的用例名子集（默认全部）")
    args = ap.parse_args(argv)
    cases = CASES
    if args.cases:
        want = {c.strip() for c in args.cases.split(",") if c.strip()}
        cases = [c for c in CASES if c[0] in want]
    WORK.mkdir(parents=True, exist_ok=True)
    p12e = _load("p12e_run", ROOT / "tools" / "_p12e_e2e_run.py")
    p12n = _load("p12n_run", ROOT / "tools" / "_p12n_j2_run.py")
    pid = host_boot.cold_boot()
    print(f"[r1-4] fresh host pid={pid}", flush=True)
    results: dict = {}
    passed = 0
    for name, cad, expectation in cases:
        if not cad.is_file():
            results[name] = {"ok": False, "verdict": f"fixture missing: {cad}"}
            continue
        rec = run_case(p12e, p12n, name, cad, WORK / f"{name}_out.pph")
        ok, verdict = judge(name, expectation, rec)
        results[name] = {"ok": ok, "expectation": expectation,
                         "verdict": verdict, "cad": str(cad), **rec}
        passed += 1 if ok else 0
        print(f"[{name}] " + json.dumps(
            {"ok": ok, "verdict": verdict, "probe": rec.get("probe"),
             "members": rec.get("members")}, ensure_ascii=False), flush=True)
    summary = {"cases": results, "passed": passed, "total": len(cases),
               "note": "本机 STEP 样本均为 AP214；AP203/AP242 无样本可测"}
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print("SUMMARY: " + json.dumps(
        {"passed": passed, "total": len(cases)}, ensure_ascii=False))
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
