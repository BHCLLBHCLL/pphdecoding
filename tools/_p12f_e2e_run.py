"""P12-F 冲刺 F 实机 e2e：NYI 五项接线 + D 遗留 patch 的 rot 权威通道证据。

流程（每 flow 独立源工程副本——宿主 OpenProject 挂起配方：挂起实例
长期持有目标文件，同文件后续打开全挂，不同文件正常）：

- **facet**（Define Facet Part）：``Doc.CreateMeshingGroup`` +
  ``Doc.ImportCADAsFacet(box.x_t)``（P12-D 已钉死配方）→ SaveProject。
- **coord**（Create Non-Facet/Closed Volume Part）：
  ``Doc.CreateCoordinatesSpecifiedPart("P12FCoordPart")`` → SaveProject；
  产物扫名（发现记录，不作 gate）。
- **submesh**（Create 2D Sub-mesh Meshing Unit）：
  ``Doc.CreateSubmeshMeshingGroup("P12FSubMG")`` → SaveProject。
- **fix**（Fix Marked Element Shape）：meshed 工程 →
  ``MeshingGroup.FixMarkedElements``（retval）→ SaveProject。
- **actran**（Create Actran Files）：meshed 工程 →
  ``MeshingGroup.CreateActranFilesMonitor(folder)``（retval True=成功，
  catalog 原文）→ 输出目录文件计数。

D 遗留 patch flow 不在此重写——直接跑 ``py tools/_p12d_e2e_run.py patch``。

用法：``py tools/_p12f_e2e_run.py [facet|coord|submesh|fix|actran|all]``
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import host_pipeline  # noqa: E402
from automation.vbs_bridge import build_vbs  # noqa: E402


def _write_ansi_vbs(actions, path, title):
    # P12-E 实测：UTF-16LE 脚本在部分宿主会话状态下 OpenProject 挂起，
    # ANSI/mbcs 秒过；flow VBS 全部落 ANSI。
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(build_vbs(actions, title), encoding="mbcs")
    return p


BOX = ROOT / "box.pph"
XT = ROOT / "tests" / "box" / "box.x_t"
MESH_OUT = ROOT / "p12e_mesh_e2e_out.pph"

COORD_NAME = "P12FCoordPart"
SUBMESH_NAME = "P12FSubMG"
ACTRAN_DIR = ROOT / "_p12f_e2e" / "actran_out"

FLOWS = ("facet", "coord", "submesh", "fix", "actran")
PATHS = {}
for _f in FLOWS:
    PATHS[_f] = {
        "vbs": ROOT / f"p12f_{_f}_e2e.vbs",
        "log": ROOT / f"p12f_{_f}_e2e.log",
        "in": ROOT / f"p12f_{_f}_in.pph",
        "out": ROOT / f"p12f_{_f}_out.pph",
    }

_SET_RE = re.compile(r"^Set (\w+) = ")
_INFO_KEYS = ("fix_ret", "actran_ret", "actran_files")


def logged_script(groups, log_path, title):
    """P5/P12-A 模式：每条动作后写 ``sNNN=<Err.Number>``。"""
    lines = [
        "' " + title,
        "On Error Resume Next",
        'Set fso_ = CreateObject("Scripting.FileSystemObject")',
        'Set out_ = fso_.CreateTextFile("' + log_path.as_posix() + '", True)',
        'out_.WriteLine "start"',
    ]
    n = 0
    for _name, actions in groups:
        for act in actions:
            n += 1
            lines.append(act)
            lines.append('out_.WriteLine "s' + str(n).zfill(3)
                         + '=" & CStr(Err.Number)')
            lines.append("Err.Clear")
            m = _SET_RE.match(act)
            if m and m.group(1) != "out_":
                var = m.group(1)
                lines.append(
                    'out_.WriteLine "' + var.lower() + '_alive=" & '
                    'CStr(Not (' + var + ' Is Nothing)) & " err=" & '
                    'CStr(Err.Number)')
                lines.append("Err.Clear")
    lines += ['out_.WriteLine "end"', "out_.Close"]
    return lines


def verify_log(text):
    """全量 err=0 校验（沿 P12-A/E）。"""
    total = err0 = 0
    problems = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line in ("start", "end"):
            continue
        m = re.match(r"^s\d+=(-?\d+)$", line)
        if m:
            code = int(m.group(1))
        else:
            m = re.search(r"(?:^|\s)err=(-?\d+)$", line)
            if not m:
                problems.append(line + " <unparsed>")
                continue
            code = int(m.group(1))
        total += 1
        if code == 0:
            err0 += 1
        else:
            problems.append(line)
    alive = {m.group(1): m.group(2)
             for m in re.finditer(r"^(\w+)_alive=(True|False)",
                                  text, re.MULTILINE)}
    info = {m.group(1): m.group(2)
            for m in re.finditer(r"^(" + "|".join(_INFO_KEYS) + r")=(\S+)",
                                 text, re.MULTILINE)}
    return {"total": total, "err0": err0, "bad": total - err0,
            "problems": problems[:20], "alive": alive, "info": info,
            "has_end": "end" in text.splitlines()}


def run_e2e(name, vbs, log, timeout=600.0, end_wait=180.0, retries=5):
    run = host_pipeline.run_vbs_authoritative(vbs, timeout=timeout)
    print("[" + name + "] run: " + json.dumps(run, ensure_ascii=False))
    # rot 通道接纳/拒绝逐次不稳定 + 慢 VBS 提前返回（P12-D/E 实测）：
    # 判据只能是日志 end 标记；拒绝（零执行）立即重试，接纳则轮询等待。
    def _log_done():
        return log.is_file() and "end" in log.read_text(
            encoding="utf-8", errors="replace").splitlines()

    deadline = time.time() + end_wait
    attempts = 1
    while not _log_done() and time.time() < deadline:
        if run.get("ok") or attempts > retries:
            time.sleep(2.0)
            continue
        print("[" + name + "] retry " + str(attempts) + "/" + str(retries)
              + " (rot 拒绝，零执行)")
        run = host_pipeline.run_vbs_authoritative(vbs, timeout=timeout)
        attempts += 1
    text = log.read_text(encoding="utf-8", errors="replace") \
        if log.is_file() else ""
    if not text:
        print("[" + name + "] LOG MISSING: " + str(log))
        return {"run": run, "log_missing": True}
    verdict = verify_log(text)
    print("[" + name + "] verdict: " + json.dumps(verdict,
                                                  ensure_ascii=False))
    return {"run": run, "verdict": verdict}


def gate(name, res, alive_need=(), min_checks=1):
    ok = (not res.get("log_missing")) and bool(res["run"].get("ok"))
    v = res.get("verdict") or {}
    ok = ok and v.get("bad") == 0 and v.get("total", 0) >= min_checks \
        and v.get("has_end")
    alive = v.get("alive", {})
    for key in alive_need:
        if alive.get(key) != "True":
            print("[" + name + "] ALIVE FAIL: " + json.dumps(alive))
            ok = False
    print("[" + name + "] GATE: " + ("PASS" if ok else "FAIL"))
    return ok


def check_out_members(name, out: Path, need_suffix=()):
    import zipfile
    if not out.is_file():
        print("[" + name + "] OUT PPH missing: " + str(out))
        return False
    with zipfile.ZipFile(out) as zf:
        members = [n.filename for n in zf.infolist()]
    print("[" + name + "] out members: " + str(members))
    ok = True
    for suf in need_suffix:
        if not any(n.endswith(suf) for n in members):
            print("[" + name + "] OUT PPH missing " + suf)
            ok = False
    return ok


def scan_name_landing(out: Path, name: str):
    """扫 pph 成员字节定位建组名的文件层落点（发现记录，不作 gate）。"""
    import zipfile
    hits = {}
    with zipfile.ZipFile(out) as zf:
        for info in zf.infolist():
            cnt = zf.read(info.filename).count(name.encode("ascii"))
            if cnt:
                hits[info.filename] = cnt
    print("[name_scan] " + json.dumps({name: hits}, ensure_ascii=False))
    return hits


# ── 流程构造 ───────────────────────────────────────────────────────────────


def _header(src: Path) -> list[str]:
    return [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        'Doc_.OpenProject "' + src.as_posix() + '", False',
    ]


def build_groups(which: str):
    p = PATHS[which]
    src, out = p["in"], p["out"]
    if which == "facet":
        return [("facet", _header(src) + [
            "Set MG_ = Doc_.CreateMeshingGroup",
            'Doc_.ImportCADAsFacet "' + XT.as_posix() + '", MG_',
            'Doc_.SaveProject "' + out.as_posix() + '"',
        ])]
    if which == "coord":
        return [("coord", _header(src) + [
            f'Set CP_ = Doc_.CreateCoordinatesSpecifiedPart("'
            f'{COORD_NAME}")',
            'Doc_.SaveProject "' + out.as_posix() + '"',
        ])]
    if which == "submesh":
        return [("submesh", _header(src) + [
            f'Set SM_ = Doc_.CreateSubmeshMeshingGroup("{SUBMESH_NAME}")',
            'Doc_.SaveProject "' + out.as_posix() + '"',
        ])]
    if which == "fix":
        return [("fix", _header(src) + [
            "Set MG_ = Doc_.QueryMeshingGroupByIndex(0)",
            "fix_ret_ = MG_.FixMarkedElements",
            'out_.WriteLine "fix_ret=" & CStr(fix_ret_) & " err=" '
            '& CStr(Err.Number)',
            "Err.Clear",
            'Doc_.SaveProject "' + out.as_posix() + '"',
        ])]
    if which == "actran":
        ACTRAN_DIR.mkdir(parents=True, exist_ok=True)
        return [("actran", _header(src) + [
            "Doc_.SetModeMesh",
            "Set MG_ = Doc_.QueryMeshingGroupByIndex(0)",
            "Doc_.SetActiveMeshingGroup 0, 0",
            'actran_ret_ = MG_.CreateActranFilesMonitor("'
            + ACTRAN_DIR.as_posix() + '")',
            'out_.WriteLine "actran_ret=" & CStr(actran_ret_) & " err=" '
            '& CStr(Err.Number)',
            "Err.Clear",
            'out_.WriteLine "actran_files=" & CStr('
            f'fso_.GetFolder("{ACTRAN_DIR.as_posix()}").Files.Count) '
            '& " err=0"',
        ])]
    raise ValueError(which)


def main(argv):
    which = argv[1] if len(argv) > 1 else "all"
    flows = list(FLOWS) if which == "all" else [which]
    if which not in ("all",) + FLOWS:
        print("unknown flow: " + which)
        return 2
    summary = {}
    for f in flows:
        p = PATHS[f]
        # 每 flow 独立源工程副本（OpenProject 挂起配方）
        src_of = BOX if f in ("facet", "coord", "submesh") else MESH_OUT
        if src_of.is_file():
            shutil.copyfile(src_of, p["in"])
        _write_ansi_vbs(logged_script(build_groups(f), p["log"],
                                      f"pphdecoding P12-F {f} e2e"),
                        p["vbs"], f"pphdecoding P12-F {f}")
        res = run_e2e(f, p["vbs"], p["log"])
        ok = gate(f, res, alive_need=(),
                  min_checks={"facet": 6, "coord": 6, "submesh": 6,
                              "fix": 7, "actran": 7}.get(f, 1))
        if f in ("facet", "coord", "submesh", "fix"):
            ok = check_out_members(f, p["out"]) and ok
        if f == "coord" and p["out"].is_file():
            scan_name_landing(p["out"], COORD_NAME)
        if f == "submesh" and p["out"].is_file():
            scan_name_landing(p["out"], SUBMESH_NAME)
        if f == "actran":
            v = res.get("verdict") or {}
            info = v.get("info", {})
            print("[actran] ret=" + info.get("actran_ret", "?")
                  + " files=" + info.get("actran_files", "?"))
            if info.get("actran_ret") != "True":
                print("[actran] business retval != True → gate FAIL")
                ok = False
        summary[f] = ok
    (ROOT / "_p12f_e2e").mkdir(exist_ok=True)
    (ROOT / "_p12f_e2e" / "p12f_run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print("SUMMARY: " + json.dumps(summary))
    print("OVERALL: " + ("PASS" if all(summary.values()) and summary
                        else "FAIL"))
    return 0 if all(summary.values()) and summary else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
