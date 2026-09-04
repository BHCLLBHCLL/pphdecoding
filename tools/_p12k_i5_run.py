"""P12-K Sprint I5：求解链数值等价双跑（recorded-only 首版 delta 表）。

§20.1-I5 / §20.4：同案例双跑 FPH/FLD/iFLD 逐变量 delta 表入册
（首版 recorded-only 不设通过线，§20.2）。严格「官方 vs 写端」
全工程 roundtrip 不存在（gphstats.write_gph 仅最小六面体），首版
口径如实记录：

1. 同案例双副本 box_b1 / box_b2（源 = ``_p12a_e2e/box.pph``——
   Sprint B 已验证可解且 2025.2 宿主自存无版本模态，~13 min/腿；
   工程干名区分产物通用名）；
2. 各自独立工作目录跑 :func:`automation.solver_run.run_solve`
   （rot 权威通道：OpenProject → SetModeMesh → SavePolyFile →
   SaveSphFile → ExecuteSolver → 等待求解退出 → FPH 场量验证）；
3. b1/b2 终态 FPH 逐变量对拍（:func:`solver_delta.compare_fph`）
   → ``delta_table.md/.json``——同案例同输入双跑的**求解器重复性
   噪声基线**；
4. 双腿 SaveSphFile 导出 sph 指纹互拍（输入面一致性记录）；
5. fld/ifld 产物若在位则结构对拍，缺席如实记录。

官方样例 exA36-3 双跑**先试后弃**（2026-09-05 实录）：a1 腿全部
8 个 MPI rank 于 692s BAD TERMINATION（exit -1；与全量回归并发
窗口重叠，疑似资源干扰——回归与实机求解此后不并发）；a2 腿实测
~27 s/周期，TM_CYCLE=1000 瞬态 ≈7.5 h，超出会话窗口于 ~48 周期
主动中止。两腿证据归档 ``_p12k_i5/exA36_attempt_*/``（a2 目录内
scFLOWpre.l 被残留句柄锁住，副本为准）。exA36-3 双跑转 backlog。

§20.3 风险 3：双跑同一宿主**顺序**执行（非并行），噪声项如实
入册。用法：``py tools/_p12k_i5_run.py``（先冷启动新宿主）。
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SRC_PPH = ROOT / "_p12a_e2e" / "box.pph"
WORK = ROOT / "_p12k_i5"
RUNS = ("b1", "b2")
WAIT_TIMEOUT = 3600.0


def make_work_copies(src: Path = SRC_PPH, work: Path = WORK) -> dict:
    """同案例拷贝为双跑工程副本（干名 → 产物名分流）。"""
    if not src.is_file():
        raise FileNotFoundError(str(src))
    out = {}
    for tag in RUNS:
        d = work / tag
        d.mkdir(parents=True, exist_ok=True)
        dst = d / f"box_{tag}.pph"
        shutil.copyfile(src, dst)
        out[tag] = {"dir": d, "pph": dst, "case": f"box_{tag}"}
    return out


def latest_fph(run_dir: Path, case: str) -> Path | None:
    fphs = sorted(run_dir.glob(f"{case}*.fph"),
                  key=lambda p: p.stat().st_mtime)
    return fphs[-1] if fphs else None


def scan_fld_ifld(run_dir: Path) -> dict:
    return {"fld": sorted(run_dir.glob("*.fld")),
            "ifld": sorted(run_dir.glob("*.ifld"))}


def run_one(tag: str, copy: dict,
            wait_timeout: float = WAIT_TIMEOUT) -> dict:
    """单腿：导出 + ExecuteSolver + 等待 + FPH 验证（rot 权威通道）。"""
    from automation import solver_run

    print(f"[i5:{tag}] run_solve start pph={copy['pph'].name}",
          flush=True)
    rep = solver_run.run_solve(copy["pph"], copy["dir"],
                               case=copy["case"],
                               wait_timeout=wait_timeout)
    wait = rep.get("wait") or {}
    verify = rep.get("verify") or {}
    fph = latest_fph(copy["dir"], copy["case"])
    brief = {
        "tag": tag,
        "pph": str(copy["pph"]),
        "work": str(copy["dir"]),
        "case": copy["case"],
        "vbs_ok": bool(rep.get("vbs_run", {}).get("ok")),
        "vbs_log": rep.get("vbs_log"),
        "wait_ok": bool(wait.get("ok")),
        "saw_solver": bool(wait.get("saw_solver")),
        "wait_timeout": bool(wait.get("timeout")),
        "wait_elapsed": wait.get("elapsed"),
        "verify_ok": bool(verify.get("ok")),
        "verify_strict": bool(verify.get("strict_ok")),
        "key_fields": verify.get("key_fields"),
        "fph": str(fph) if fph else None,
        "fld_ifld": {k: [str(p) for p in v]
                     for k, v in scan_fld_ifld(copy["dir"]).items()},
        "ok": bool(rep.get("ok")),
    }
    print(f"[i5:{tag}] done ok={brief['ok']} wait={brief['wait_elapsed']}s"
          f" verify={brief['verify_ok']} fph={brief['fph']}", flush=True)
    return brief


def assemble_report(run_briefs: dict, work: Path = WORK) -> dict:
    """双腿结果 → FPH delta 表 + sph 指纹 + fld/ifld 缺席记录。"""
    import solver_delta

    work.mkdir(parents=True, exist_ok=True)
    b1, b2 = run_briefs["b1"], run_briefs["b2"]
    cmp_rep = {"ok": False, "reason": "fph missing"}
    md = ""
    if b1.get("fph") and b2.get("fph"):
        cmp_rep = solver_delta.compare_fph(b1["fph"], b2["fph"])
        md = solver_delta.delta_table_markdown(
            cmp_rep, title="P12-K I5 dual-run FPH delta table "
                           "(box b1 vs b2, recorded-only)")
        (work / "delta_table.md").write_text(md, encoding="utf-8")
    (work / "delta_table.json").write_text(
        json.dumps(cmp_rep, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    sph = {
        "exported_b1": solver_delta.sph_fingerprint(
            Path(b1["work"]) / "scFLOWpre.sph"),
        "exported_b2": solver_delta.sph_fingerprint(
            Path(b2["work"]) / "scFLOWpre.sph"),
    }
    fld_cmp = ifld_cmp = None
    if b1["fld_ifld"]["fld"] and b2["fld_ifld"]["fld"]:
        fld_cmp = solver_delta.compare_fld(b1["fld_ifld"]["fld"][-1],
                                           b2["fld_ifld"]["fld"][-1])
    if b1["fld_ifld"]["ifld"] and b2["fld_ifld"]["ifld"]:
        ifld_cmp = solver_delta.compare_ifld(b1["fld_ifld"]["ifld"][-1],
                                             b2["fld_ifld"]["ifld"][-1])
    both_ok = b1["ok"] and b2["ok"] and cmp_rep.get("ok")
    summary = {
        "runs": run_briefs,
        "fph_compare_ok": bool(cmp_rep.get("ok")),
        "fph_compare_reason": cmp_rep.get("reason"),
        "n_fields": len(cmp_rep.get("fields", {})),
        "fld_compare": fld_cmp,
        "ifld_compare": ifld_cmp,
        "sph_fingerprints": sph,
        "ok": bool(both_ok),
    }
    (work / "i5_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    return summary


def main() -> int:
    from automation import host_boot

    t0 = time.time()
    pid = host_boot.cold_boot()
    print(f"[i5] fresh host pid={pid}", flush=True)
    copies = make_work_copies()
    briefs = {}
    for tag in RUNS:
        briefs[tag] = run_one(tag, copies[tag])
    summary = assemble_report(briefs)
    summary["elapsed_s"] = round(time.time() - t0, 1)
    print("SUMMARY: " + json.dumps(
        {k: v for k, v in summary.items() if k != "runs"},
        ensure_ascii=False, default=str))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
