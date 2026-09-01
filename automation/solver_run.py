#!/usr/bin/env python3
"""P12-B 求解链路：SPH 导出 → ExecuteSolver → 完成等待 → FPH 读回验证。

链路（权威通道 = rot，host_pipeline.run_vbs_authoritative）：

1. ``build_solve_vbs`` 生成宿主内 VBS：OpenProject → SetModeMesh →
   SavePolyFile(gph) → SaveSphFile(sph, gph) →（可选）ExecuteSolver(sph)，
   每步记录 Err.Number 与产物存在性；
2. VBS 提交后，Python 侧轮询求解器进程（JobLauncher/scFLOWsol/scMonitor）
   等待退出——ExecuteSolver 阻塞或非阻塞两种语义都收敛；
3. ``find_solver_artifacts`` 在工作目录 / Cradle Work 目录收集
   ``<case>_*.fph``（场量）/ ``.rph``（重启）/ 日志；
4. ``verify_fph_file`` 用仓库根 :mod:`fph` 解析结果文件，判定
   pressure / velocity 等场量非空且数值有限。

验收口径（DEV_PLAN §18 Sprint B）：求解完成日志 + FLD 场量非空。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.vbs_bridge import write_vbs_file  # noqa: E402

# ExecuteSolver 实机拉起的**计算**进程（退出=求解结束；2025.2 实测）。
# scMonitor 是监视器 GUI，CALCULATION FINISH 后仍常驻，不得计入
# 「求解在跑」判据（P12-B 实测：求解完 13 分钟 monitor pid 仍在）。
SOLVER_PROC_NAMES = (
    "JobLauncher_Bx64",
    "scFLOWsol_Dx64net",
    "scflowsol*",
    "mpiexec",
    "mpirun",
)
MONITOR_PROC_NAMES = ("scMonitorSCFLOW_Bx64net",)

# 结果文件通用名（与 sph 内 FPH/RPH/ETCO 条目一致，来自工程名）
DEFAULT_CASE = "box"


def build_solve_vbs(project_pph: str | Path,
                    work_dir: str | Path,
                    log_path: str | Path,
                    *,
                    execute: bool = True,
                    gph_name: str = "scFLOWpre.gph",
                    sph_name: str = "scFLOWpre.sph",
                    quit_after: bool = False) -> Path:
    """生成求解链路 VBS（UTF-16，宿主内执行）。

    ``execute=False`` 时只导出 gph/sph（探测用，不拉起求解器）。
    ``quit_after=True`` 时用 ``QuitAndExecuteSolver``（语义：宿主
    提交求解后退出前处理 GUI），不利批量多会话编排，默认走
    ``ExecuteSolver``（只异步拉起求解器，宿主不退）。
    路径一律正斜杠（P12-A e2e 先例）。
    """
    pph = Path(project_pph).resolve().as_posix()
    work = Path(work_dir).resolve().as_posix()
    gph = f"{work}/{gph_name}"
    sph = f"{work}/{sph_name}"
    log = Path(log_path).resolve().as_posix()
    lines = [
        "' pphdecoding P12-B solve chain (rot)",
        "On Error Resume Next",
        'Set fso_ = CreateObject("Scripting.FileSystemObject")',
        f'Set out_ = fso_.CreateTextFile("{log}", True)',
        'out_.WriteLine "start"',
        "Set App_ = GetApplication()",
        "If App_ Is Nothing Then "
        'Set App_ = CreateObject("scFLOWpre_Bx64net.Application.2025")',
        'out_.WriteLine "app_alive=" & CStr(Not (App_ Is Nothing)) '
        '& " err=" & CStr(Err.Number)',
        "Err.Clear",
        "Set Doc_ = App_.GetDocument",
        'out_.WriteLine "doc_alive=" & CStr(Not (Doc_ Is Nothing)) '
        '& " err=" & CStr(Err.Number)',
        "Err.Clear",
        f'Doc_.OpenProject "{pph}", False',
        'out_.WriteLine "open_err=" & CStr(Err.Number)',
        "Err.Clear",
        "Doc_.SetModeMesh",
        'out_.WriteLine "setmode_err=" & CStr(Err.Number)',
        "Err.Clear",
        f'Doc_.SavePolyFile "{gph}"',
        'out_.WriteLine "savepoly_err=" & CStr(Err.Number)',
        f'out_.WriteLine "gph_exists=" & CStr(fso_.FileExists("{gph}"))',
        "Err.Clear",
        f'Doc_.SaveSphFile "{sph}", "{gph}"',
        'out_.WriteLine "savesph_err=" & CStr(Err.Number)',
        f'out_.WriteLine "sph_exists=" & CStr(fso_.FileExists("{sph}"))',
        "Err.Clear",
    ]
    if execute:
        method_ = "QuitAndExecuteSolver" if quit_after else "ExecuteSolver"
        lines += [
            f'RetExec_ = Doc_.{method_}("{sph}")',
            f'out_.WriteLine "exec_method={method_}"',
            'out_.WriteLine "exec_err=" & CStr(Err.Number)',
            'out_.WriteLine "exec_ret=" & CStr(RetExec_)',
            "Err.Clear",
        ]
    lines += ['out_.WriteLine "end"', "out_.Close"]
    return write_vbs_file(lines, Path(log_path).with_suffix(".vbs"),
                          title="pphdecoding P12-B solve chain")


def _proc_pids(names) -> list[int]:
    joined = ",".join(names)
    cmd = (f"Get-Process -Name {joined} -ErrorAction SilentlyContinue | "
           "Select-Object -ExpandProperty Id")
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=20, check=False).stdout
    except Exception:  # noqa: BLE001
        return []
    return sorted({int(x) for x in out.split() if x.strip().isdigit()})


def solver_processes() -> list[int]:
    """当前在位的求解**计算**进程 pid（退出=求解结束；无则空表）。"""
    return _proc_pids(SOLVER_PROC_NAMES)


def monitor_processes() -> list[int]:
    """scMonitor 监视器进程（求解完后仍常驻，仅诊断用）。"""
    return _proc_pids(MONITOR_PROC_NAMES)


def cradle_work_dirs() -> list[Path]:
    """本机 Cradle Work 目录候选（求解器经宿主拉起时的常见落点）。"""
    docs = Path.home() / "Documents" / "Cradle"
    if not docs.is_dir():
        return []
    out = []
    for work in sorted(docs.glob("scFLOW*/Work")):
        if work.is_dir():
            out.append(work)
    return out


def find_solver_artifacts(case=None,
                          cases: Optional[list] = None,
                          dirs: Optional[list] = None) -> dict:
    """在候选目录收集求解产物（去重按绝对路径）。

    实测命名分裂：场文件 ``<工程名>_400.fph/.rph`` 跟 sph 内
    FPH/RPH 条目的通用名（=工程名）；而 L 日志 ``<sph 干名>.l`` /
    ``.ccdt`` / ``.csln`` 跟 sph 文件干名——故支持多通用名扫描。
    """
    names: list[str]
    if cases:
        names = list(cases)
    elif case:
        names = [case]
    else:
        # 无 case/cases 时不按工程名前缀扫（此前回退 DEFAULT_CASE="box"
        # 会把与 box 无关的工程产物漏报，是 STATUS CLI 的误判根因）。
        # 空 names = 扫所有候选目录下的 fph/rph/log/... 通用后缀。
        names = []
    cands = [Path(d) for d in (dirs or [])]
    cands += cradle_work_dirs()
    seen: dict[str, dict] = {}
    patterns: list[str]
    if names:
        patterns = []
        for c in dict.fromkeys(names):
            patterns += [f"{c}*.fph", f"{c}*.rph", f"{c}*.log",
                         f"{c}*.l", f"{c}*.xml", f"{c}*.csln",
                         f"{c}*.fld"]
    else:
        patterns = ["*.fph", "*.rph", "*.log",
                    "*.l", "*.xml", "*.csln", "*.fld"]
    for d in cands:
        if not d.is_dir():
            continue
        for pat in patterns:
            for p in d.glob(pat):
                if p.is_file():
                    st = p.stat()
                    seen[str(p.resolve())] = {
                        "path": str(p.resolve()),
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                    }
    arts = sorted(seen.values(), key=lambda a: a["mtime"])
    return {
        "case": names,
        "dirs": [str(d) for d in cands],
        "artifacts": arts,
        "fph": [a for a in arts if a["path"].endswith(".fph")],
        "logs": [a for a in arts
                 if a["path"].endswith((".log", ".l", ".csln", ".xml"))],
    }


def wait_for_solver(timeout: float = 1800.0, poll: float = 3.0,
                    case: str = DEFAULT_CASE,
                    cases: Optional[list] = None,
                    extra_dirs: Optional[list] = None,
                    progress=None) -> dict:
    """轮询等待求解器退出（或产物落盘）。

    判定：曾观察到求解进程 → 其全部退出即完成；始终未见进程 →
    以 ``<case>*.fph`` 产物出现并稳定一轮为准（ExecuteSolver 拉起
    瞬时进程 / 已提前跑完的兜底）。
    """
    names = cases or [case]
    start = time.time()
    saw = False
    stable = 0
    last_fph: set = set()
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            break
        procs = solver_processes()
        if procs:
            saw = True
            stable = 0
            if progress:
                progress(f"solver running pid={procs} t={elapsed:.0f}s")
        else:
            arts = find_solver_artifacts(cases=names, dirs=extra_dirs)
            fph_now = {a["path"] for a in arts["fph"]}
            if saw:
                if progress:
                    progress(f"solver exited t={elapsed:.0f}s")
                return {"ok": True, "saw_solver": True,
                        "elapsed": round(elapsed, 1),
                        "artifacts": arts}
            if fph_now and fph_now == last_fph:
                stable += 1
                if stable >= 2:
                    return {"ok": True, "saw_solver": False,
                            "elapsed": round(elapsed, 1),
                            "artifacts": arts,
                            "note": "未见求解进程，以产物稳定判定"}
            else:
                stable = 0
            last_fph = fph_now
        time.sleep(poll)
    arts = find_solver_artifacts(cases=names, dirs=extra_dirs)
    return {"ok": saw or bool(arts["fph"]),
            "saw_solver": saw, "elapsed": round(timeout, 1),
            "timeout": True, "artifacts": arts}


def verify_fph_file(path: str | Path) -> dict:
    """解析求解产物 FPH，判定场量非空且数值有限。"""
    import numpy as np

    import fph

    path = Path(path)
    data, handles = None, None
    try:
        import crdlfld
        data, handles = crdlfld.open_buffer(path)
        mesh = fph.parse_fph(data)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "path": str(path), "reason": f"解析失败: {exc!r}"}
    finally:
        if handles is not None:
            mm, f = handles
            mm.close()
            f.close()
    cells = mesh.get("cells") or {}
    fields_out = {}
    for name, fld in (mesh.get("fields") or {}).items():
        info = {"kind": fld["kind"], "target": fld["target"],
                "components": fld["components"], "ok": False}
        for kind, arr in fld["arrays"]:
            if kind != "values" or arr.size == 0:
                continue
            fin = fph.as_f32(arr)
            fin = fin[np.isfinite(fin)]
            if fin.size == 0:
                continue
            info.update({
                "n": int(arr.size),
                "min": float(fin.min()),
                "max": float(fin.max()),
                "mean": float(fin.mean()),
                "ok": True,
            })
            break
        fields_out[name] = info
    key_ok = []
    for probe in ("EC_Scalar:PRES", "EC_Vector:VEL"):
        f = fields_out.get(probe)
        if f and f.get("ok"):
            key_ok.append(probe)
    any_ok = [n for n, f in fields_out.items() if f.get("ok")]
    nonzero = [n for n, f in fields_out.items()
               if f.get("ok") and abs(f.get("max", 0.0)) > 0.0]
    verdict = {
        "ok": bool(any_ok),
        # strict：至少一个场量数值非全零（退化物理与解析失败区分）
        "strict_ok": bool(nonzero),
        "path": str(path),
        "size": path.stat().st_size,
        "n_cells": int(cells.get("n_cells", 0)),
        "n_faces": int((mesh.get("links") or {}).get("n_faces", 0)),
        "key_fields": key_ok,
        "fields_ok": any_ok,
        "nonzero_fields": nonzero,
        "fields": fields_out,
    }
    if not any_ok:
        verdict["reason"] = "无任何非空场量数组"
    elif not nonzero:
        verdict["reason"] = "场量数组在位但全零（物理退化，非解析失败）"
    return verdict


def run_solve(project_pph: str | Path,
              work_dir: str | Path,
              *,
              case: Optional[str] = None,
              execute: bool = True,
              quit_after: bool = False,
              vbs_timeout: float = 3600.0,
              wait_timeout: float = 1800.0,
              sph_name: str = "scFLOWpre.sph") -> dict:
    """完整求解链路编排（rot 权威通道）。

    ``case`` 缺省 = 双通用名扫描（实测产物命名分裂：场文件跟工程名
    ``box_400.fph``，L 日志跟 sph 干名 ``scFLOWpre.l``）。
    ``quit_after=True`` 走 ``QuitAndExecuteSolver``（提交后退出前
    处理宿主，不利批量；默认 ``ExecuteSolver`` 仅异步拉起求解器）。
    """
    from automation import host_pipeline

    sph_stem = Path(sph_name).stem
    proj_stem = Path(project_pph).stem
    names = [case] if case else list(dict.fromkeys([proj_stem, sph_stem]))
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    log = work / "solve_vbs.log"
    vbs = build_solve_vbs(project_pph, work, log, execute=execute,
                          quit_after=quit_after)
    report: dict = {"vbs": str(vbs), "log": str(log),
                    "backend": "rot", "execute": execute,
                    "quit_after": quit_after}
    res = host_pipeline.run_vbs_authoritative(vbs, timeout=vbs_timeout)
    report["vbs_run"] = res
    if log.exists():
        report["vbs_log"] = log.read_text(encoding="utf-8",
                                          errors="replace").splitlines()
    if not res.get("ok"):
        report["ok"] = False
        report["reason"] = "VBS 提交失败（宿主在位？许可？工程可开？）"
        return report
    if not execute:
        arts = find_solver_artifacts(cases=names, dirs=[work])
        report.update({"ok": True, "artifacts": arts})
        return report
    wait = wait_for_solver(timeout=wait_timeout, cases=names,
                           extra_dirs=[work],
                           progress=lambda m: print(f"[wait] {m}",
                                                    flush=True))
    report["wait"] = wait
    fphs = wait["artifacts"]["fph"]
    if fphs:
        latest = max(fphs, key=lambda a: a["mtime"])["path"]
        report["verify"] = verify_fph_file(latest)
    report["ok"] = bool(wait.get("ok")) and bool(
        report.get("verify", {}).get("ok"))
    return report


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="P12-B 求解链路")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_build = sub.add_parser("build", help="仅生成 VBS")
    p_prep = sub.add_parser("prep", help="导出 gph/sph（不拉求解器）")
    p_run = sub.add_parser("run", help="完整链路（提交+等待+验证）")
    p_wait = sub.add_parser("wait", help="等待外部拉起的求解器")
    p_ver = sub.add_parser("verify", help="验证单个 FPH 结果文件")
    p_status = sub.add_parser("status", help="求解进程/产物现状")
    for p in (p_build, p_prep, p_run):
        p.add_argument("--pph", required=True, help="工程 .pph 路径")
        p.add_argument("--work", required=True, help="gph/sph 工作目录")
    for p in (p_build, p_prep, p_run):
        p.add_argument(
            "--quit-after", action="store_true",
            help="用 QuitAndExecuteSolver（提交后退出前处理宿主，不利批量；"
                 "prep/build 仅影响 VBS 内容占位，实际作用在 run 阶段）")
    p_run.add_argument("--case", default=None,
                       help="产物通用名（缺省=工程名干名 + sph 干名双扫）")
    p_run.add_argument("--vbs-timeout", type=float, default=3600.0)
    p_run.add_argument("--wait-timeout", type=float, default=1800.0)
    # wait/status 不指定 case => 按通用后缀全扫（此前 DEFAULT_CASE="box"
    # 会漏报非 box 工程，现更符合运维视角）。
    p_wait.add_argument("--case", default=None,
                        help="通用名（缺省=所有候选目录按 FPH/RPH/LOG 后缀全扫）")
    p_wait.add_argument("--timeout", type=float, default=1800.0)
    p_wait.add_argument("--dir", action="append", default=[],
                        help="额外产物扫描目录（可重复）")
    p_ver.add_argument("fph", help="FPH 结果文件路径")
    args = ap.parse_args(argv)

    if args.cmd == "build":
        vbs = build_solve_vbs(args.pph, args.work,
                               Path(args.work) / "solve_vbs.log",
                               quit_after=args.quit_after)
        print(vbs)
        return 0
    if args.cmd == "prep":
        rep = run_solve(args.pph, args.work, execute=False,
                        quit_after=args.quit_after)
        print(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
        return 0 if rep.get("ok") else 1
    if args.cmd == "run":
        rep = run_solve(args.pph, args.work, case=args.case,
                        quit_after=args.quit_after,
                        vbs_timeout=args.vbs_timeout,
                        wait_timeout=args.wait_timeout)
        print(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
        return 0 if rep.get("ok") else 1
    if args.cmd == "wait":
        rep = wait_for_solver(timeout=args.timeout, case=args.case,
                              extra_dirs=args.dir or None,
                              progress=lambda m: print(f"[wait] {m}",
                                                       flush=True))
        print(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
        return 0 if rep.get("ok") else 1
    if args.cmd == "verify":
        rep = verify_fph_file(args.fph)
        keep = {k: v for k, v in rep.items() if k != "fields"}
        print(json.dumps(keep, ensure_ascii=False, indent=1, default=str))
        return 0 if rep.get("ok") else 1
    if args.cmd == "status":
        rep = {"solver_pids": solver_processes(),
               "monitor_pids": monitor_processes(),
               "work_dirs": [str(d) for d in cradle_work_dirs()],
               "artifacts": find_solver_artifacts()}
        print(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
