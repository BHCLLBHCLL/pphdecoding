"""P12-O Sprint J3：a1 BAD TERMINATION 隔离复验 + exB05-1 第 2 案例双跑。

§21.1-J3 ②/④（2026-09-05）。实机窗口纪律：独占宿主时段，与全量
回归绝不并发；证据落 ``_p12o_j3/``。用法（先看命令各自注释）：

* ``run-a1`` —— ② exA36-3 a1 隔离复验：冷启动新宿主 → 官方
  exA36-3.pph 干名副本 exA36_3_a1r → run_solve 等待窗口 45 min +
  资源采样线程（psutil 15 s 间隔：scFLOW*/mpiexec* 进程数、RSS、
  CPU 累计、scFLOWpre.l 的 ``### CYCLE`` 进度）落 JSONL → 判定
  （复现 = TIME(solver) 未越过 692 s 死亡点且 BAD TERMINATION 在
  位；未复现 = 越过死亡点 / CYCLE 2 开跑 / 正常收束）。
* ``probe`` —— ④ 探测腿：官方 exB05-1.pph + mechanism.bin（LWSR
  反应机制外部文件，须随 pph 入工作目录）单腿计时（上限 40 min），
  定 cadence/license 可解性取舍。
* ``dual`` —— ④ 双跑腿：c1/c2 两干名副本顺序 run_solve →
  compare_fph + gate_fph（默认容差 0 逐位复现线）→
  ``delta_table.md/.json`` + sph 指纹 + ``j3_summary.json``。

a1 背景（§20.9/I5 实录）：exA36-3 电热瞬态（TM_CYCLE=1000，
~10–16 min/周期，全量双跑不可行）；a1 腿 2026-09-05 于
TIME(solver)=692.097 s（CYCLE 1 内）BAD TERMINATION RANK 1–7
（exit -1）+ mpiexec exit -1，与全量回归并发窗口重叠 → 隔离复验
窗口 = 跑过 692 s 死亡点（~25–35 min）即收口。
"""

from __future__ import annotations

import json
import shutil
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LIB = Path(r"D:\training\cradle\CradleCFD_2025.2_scFLOW_Example_a\Exercise")
WORK = ROOT / "_p12o_j3"
A1_SRC = LIB / "exA36" / "exA36-3" / "Org" / "exA36-3.pph"
# ④ 第二案例：exA36-2（官方瞬态：5918 单元 + BATTERY p2d 电化学
# 内模，EQUA = ENERGY-only 全零余项，license-safe）。候选裁决三连：
# exB05-1 = license 硬门（LWSR checkout -97,121，证据
# _p12o_j3/probe_exb05/）；exA07-1（100 cycle 共轭传热）= 备选
# 未启用（exA36-2 探测腿即证可行）。**探测腿关键发现 = 外部中断**：
# 外部作业控制代理于 cycle 247（rest phase t=200-300 内）写入
# scFLOWpre.sph.instruction（cycle=-2, lapse_time=0 = 立即停）→
# 求解器优雅停（INTERRUPT FILE WAS FOUND + CALCULATION FINISH），
# TIME(solver)=974.3 s ≈ 16.2 min/腿——非脚本自然终止（TABLE
# (0,3)/(200,0)/(300,3) 在 t=300 才结束）。c1/c2 双跑同被外部
# 代理截停（c1 instruction@166、c2 terminate@70）→ 等时终态双跑
# 本夜不可达。详见 _p12o_j3/interrupt_forensics.md。
C2_SRC = LIB / "exA36" / "exA36-2" / "Org" / "exA36-2.pph"
C2_STEM = "exa36_2"
A1_WINDOW = 2700.0      # ② 等待窗口 45 min
C2_WINDOW = 2400.0      # ④ 探测/单腿上限 40 min


def _copy_run_asset(src: Path, tag_dir: Path, stem: str) -> Path:
    tag_dir.mkdir(parents=True, exist_ok=True)
    dst = tag_dir / f"{stem}.pph"
    shutil.copyfile(src, dst)
    return dst


def _scan_l(log_path: Path) -> dict:
    """scFLOWpre.l 线级扫描 → {time_solver_s, bad_term_blocks,
    ranks, cycle_max, error_log, finish, interrupt, terminate_kill}。"""
    rep = {"exists": False}
    if not log_path.is_file():
        return rep
    txt = log_path.read_text(encoding="utf-8", errors="replace")
    rep["exists"] = True
    rep["size"] = log_path.stat().st_size
    rep["bad_term_blocks"] = txt.count("BAD TERMINATION OF ONE")
    rep["finish"] = "CALCULATION FINISH" in txt
    rep["interrupt"] = "INTERRUPT FILE" in txt and "WAS FOUND" in txt
    rep["terminate_kill"] = "monitor_termination::killProcess" in txt
    import re
    m = re.search(r"TIME \(solver\)\s*\*\*\*\*\*\*\*\*\*\s*\n\s*\d+ d \d+ h "
                  r"\d+ m \d+ s\s*\n\s*([\d.]+) sec", txt)
    if not m:
        m = re.search(r"\*\*\*\*\*\*\*\*\* TIME \(solver\) \*\*\*\*\*\*\*\*\*\*"
                      r".*?\n\s*([\d.]+) sec", txt, re.S)
    rep["time_solver_s"] = float(m.group(1)) if m else None
    ranks = re.findall(r"RANK (\d+) PID \d+", txt)
    rep["ranks_bad"] = sorted({int(r) for r in ranks})
    cy = re.findall(r"<CYCLE ID=\"(\d+)\"", txt)
    rep["cycle_max"] = max((int(c) for c in cy), default=0)
    rep["error_log"] = "ERROR LOG" in txt
    rep["mpiexec_error"] = "Unknown error is detected by mpiexec" in txt
    return rep


class ResourceSampler(threading.Thread):
    """15 s 间隔采样求解器进程 + L 日志 CYCLE 进度 → JSONL。"""

    def __init__(self, log_path: Path, out_jsonl: Path,
                 interval: float = 15.0):
        super().__init__(daemon=True)
        self.log_path = log_path
        self.out = out_jsonl
        self.interval = interval
        self._stop = threading.Event()
        self.prev: dict[int, float] = {}

    def stop(self):
        self._stop.set()

    def run(self):
        import psutil
        rows = []
        while not self._stop.is_set():
            t0 = time.time()
            row = {"t": round(t0 - self.t_start, 1)}
            cpu_total = mem_total = 0.0
            procs = []
            for p in psutil.process_iter(["pid", "name", "memory_info",
                                          "cpu_times"]):
                try:
                    nm = (p.info["name"] or "").lower()
                    if not any(k in nm for k in
                               ("scflow", "mpiexec", "stpre")):
                        continue
                    cpu = p.info["cpu_times"]
                    cpu_s = (cpu.user + cpu.system) if cpu else 0.0
                    mem = p.info["memory_info"]
                    mem_mb = (mem.rss if mem else 0) / 1048576.0
                    delta = cpu_s - self.prev.get(p.info["pid"], cpu_s)
                    self.prev[p.info["pid"]] = cpu_s
                    cpu_total += delta
                    mem_total += mem_mb
                    procs.append({"pid": p.info["pid"],
                                  "name": p.info["name"],
                                  "mem_mb": round(mem_mb, 1)})
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            row.update(n_procs=len(procs), procs=procs,
                       mem_mb=round(mem_total, 1),
                       cpu_sec=round(cpu_total, 2))
            if self.log_path.is_file():
                try:
                    txt = self.log_path.read_text(
                        encoding="utf-8", errors="replace")
                    import re
                    cy = re.findall(r"### CYCLE\s+(\d+)", txt)
                    row["log_cycle_max"] = max(
                        (int(c) for c in cy), default=0)
                    row["log_size"] = self.log_path.stat().st_size
                except OSError:
                    pass
            rows.append(row)
            if len(rows) >= 4:      # 批次落盘（防进程被杀丢数据）
                with self.out.open("a", encoding="utf-8") as f:
                    for r in rows:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
                rows.clear()
            self._stop.wait(max(0.0, self.interval - (time.time() - t0)))
        if rows:
            with self.out.open("a", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def start(self):
        self.t_start = time.time()
        super().start()


def _kill_solvers() -> list[int]:
    """按名清场 scflow*/mpiexec* 进程（超时窗口后的孤儿防线）。"""
    import psutil
    killed = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            nm = (p.info["name"] or "").lower()
            if any(k in nm for k in ("scflow", "mpiexec", "stpre")):
                p.kill()
                killed.append(p.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return killed


def _run_one(tag: str, pph: Path, case: str, tag_dir: Path,
             wait_timeout: float) -> dict:
    from automation import solver_run

    print(f"[j3:{tag}] run_solve start pph={pph.name} case={case}",
          flush=True)
    res = solver_run.run_solve(pph, tag_dir, case=case,
                               wait_timeout=wait_timeout)
    wait = res.get("wait") or {}
    verify = res.get("verify") or {}
    fphs = sorted(tag_dir.glob(f"{case}*.fph"),
                  key=lambda p: p.stat().st_mtime)
    log = tag_dir / "scFLOWpre.l"
    scan = _scan_l(log)
    ok = bool(res.get("ok"))
    if scan.get("bad_term_blocks", 0) > 0:
        ok = False
    brief = {
        "tag": tag,
        "pph": str(pph),
        "work": str(tag_dir),
        "case": case,
        "vbs_ok": bool(res.get("vbs_run", {}).get("ok")),
        "wait_ok": bool(wait.get("ok")),
        "saw_solver": bool(wait.get("saw_solver")),
        "wait_timeout": bool(wait.get("timeout")),
        "wait_elapsed": wait.get("elapsed"),
        "verify_ok": bool(verify.get("ok")),
        "key_fields": verify.get("key_fields"),
        "fph": str(fphs[-1]) if fphs else None,
        "log_scan": scan,
        "ok": ok,
    }
    print(f"[j3:{tag}] done ok={brief['ok']} wait={brief['wait_elapsed']}s"
          f" fph={brief['fph']}", flush=True)
    return brief


def cmd_a1_rerun() -> int:
    """② exA36-3 a1 隔离复验（独占宿主，无并发 + 资源采样）。"""
    from automation import host_boot

    if not A1_SRC.is_file():
        raise FileNotFoundError(str(A1_SRC))
    d = WORK / "a1r"
    d.mkdir(parents=True, exist_ok=True)
    pph = _copy_run_asset(A1_SRC, d, "exA36_3_a1r")
    pid = host_boot.cold_boot()
    print(f"[j3:a1r] fresh host pid={pid}", flush=True)
    sampler = ResourceSampler(d / "scFLOWpre.l", d / "resources.jsonl")
    sampler.start()
    try:
        brief = _run_one("a1r", pph, "exA36_3_a1r", d, A1_WINDOW)
    finally:
        sampler.stop()
    scan = brief.get("log_scan") or {}
    ts = scan.get("time_solver_s")
    if not ts and brief.get("wait_timeout"):
        ts = brief.get("wait_elapsed")
    if ts is not None:
        brief["verdict"] = ("REPRODUCED" if (
            scan.get("bad_term_blocks", 0) > 0 and ts < 700.0)
            else "NOT_REPRODUCED_IN_WINDOW")
    else:
        brief["verdict"] = "INCONCLUSIVE"
    if brief.get("wait_timeout"):
        brief["verdict"] += "_TIMEOUT"
        brief["killed_after_window"] = _kill_solvers()
    (d / "a1r_verdict.json").write_text(
        json.dumps(brief, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    print("A1R VERDICT: " + json.dumps(brief, ensure_ascii=False,
                                       default=str))
    return 0


def _prep_c2(tag: str) -> tuple[Path, Path]:
    d = WORK / tag
    d.mkdir(parents=True, exist_ok=True)
    pph = _copy_run_asset(C2_SRC, d, f"{C2_STEM}_{tag}")
    return pph, d


def cmd_probe() -> int:
    """④ exA36-2 探测腿：单跑计时 + 可解性/许可判别。"""
    from automation import host_boot

    if not C2_SRC.is_file():
        raise FileNotFoundError(str(C2_SRC))
    host_boot.cold_boot()
    pph, d = _prep_c2("probe")
    t0 = time.time()
    brief = _run_one("probe", pph, f"{C2_STEM}_probe", d, C2_WINDOW)
    brief["wall_s"] = round(time.time() - t0, 1)
    scan = brief.get("log_scan") or {}
    brief["verdict"] = ("SOLVABLE" if brief.get("fph") else
                        ("LICENSE_OR_SETUP_FAIL" if brief.get("vbs_ok")
                         else "HOST_FAIL"))
    if brief.get("wait_timeout") and not brief.get("fph"):
        brief["verdict"] = "TOO_SLOW_IN_WINDOW"
        brief["killed_after_window"] = _kill_solvers()
    print("PROBE tail: " + json.dumps(scan, ensure_ascii=False,
                                      default=str))
    (d / "probe_verdict.json").write_text(
        json.dumps(brief, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    print("PROBE VERDICT: " + json.dumps(
        {k: v for k, v in brief.items() if k != "log_scan"},
        ensure_ascii=False, default=str))
    return 0


def cmd_dual() -> int:
    """④ exA36-2 双跑 c1/c2 + FPH gate 判定 + 入册表。"""
    from automation import host_boot
    import solver_delta

    host_boot.cold_boot()
    briefs = {}
    killed = []
    for tag in ("c1", "c2"):
        pph, d = _prep_c2(tag)
        briefs[tag] = _run_one(tag, pph, f"{C2_STEM}_{tag}", d,
                               C2_WINDOW)
        if briefs[tag].get("wait_timeout"):
            killed.extend(_kill_solvers())
    cmp_rep = {"ok": False, "reason": "fph missing"}
    md = ""
    f1, f2 = briefs["c1"].get("fph"), briefs["c2"].get("fph")
    if f1 and f2:
        cmp_rep = solver_delta.compare_fph(f1, f2)
        gate = solver_delta.gate_fph(cmp_rep)
        cmp_rep["gate"] = gate
        md = solver_delta.delta_table_markdown(
            cmp_rep, gate=gate,
            title=f"P12-O J3 {C2_STEM} dual-run FPH delta table "
                  "(c1 vs c2, gate tol 0)")
        (WORK / "delta_table.md").write_text(md, encoding="utf-8")
    (WORK / "delta_table.json").write_text(
        json.dumps(cmp_rep, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    sph = {
        "c1": solver_delta.sph_fingerprint(
            Path(briefs["c1"]["work"]) / "scFLOWpre.sph"),
        "c2": solver_delta.sph_fingerprint(
            Path(briefs["c2"]["work"]) / "scFLOWpre.sph"),
    }
    summary = {
        "runs": briefs,
        "fph_compare_ok": bool(cmp_rep.get("ok")),
        "gate": cmp_rep.get("gate"),
        "reason": cmp_rep.get("reason"),
        "sph_fingerprints": sph,
        "killed_after_window": killed or None,
        "ok": bool(briefs["c1"]["ok"] and briefs["c2"]["ok"]
                   and cmp_rep.get("ok")
                   and (cmp_rep.get("gate") or {}).get("ok")),
    }
    (WORK / "j3_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    print("DUAL SUMMARY: " + json.dumps(
        {k: v for k, v in summary.items() if k != "runs"},
        ensure_ascii=False, default=str))
    return 0 if summary["ok"] else 1


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="P12-O J3 实机窗口驱动")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("a1-rerun", "probe", "dual"):
        sub.add_parser(name)
    args = ap.parse_args(argv)
    return {"a1-rerun": cmd_a1_rerun, "probe": cmd_probe,
            "dual": cmd_dual}[args.cmd]()


if __name__ == "__main__":
    raise SystemExit(main())
