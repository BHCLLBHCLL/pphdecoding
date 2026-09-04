"""P12-I Sprint I4：Actran Acoustic 前置狩猎（CreateActranFiles 业务复验）。

P12-F §10.8 遗留：``MeshingGroup.CreateActranFilesMonitor`` typed 链
err=0 但业务 retval=False——Acoustic Session（scFLOW2Actran 耦合）前置
未构造。本流按 catalog 自文档化构成（CondActranAnalysisControl =
"analysis condition for the acoustic session of scFLOW2Actran"）做
构造复验：

1. OpenProject（BAM 网格工程，真网格在位）→ SetModeMesh；
2. ``GetCondActranAnalysisControl`` + 逐参数探针
   （``GetParam("cfd_analysis_type")``——C3 收割产物 XML 实键）；
3. 构造全套 CondActran 条件（Source / OutputSolution /
   BoundaryNonReflection / BoundaryAbsorption / PointSource）；
4. ``CreateActranFilesMonitor(folder)`` → 业务 retval + 产物文件数；
5. SaveProject → 离线检 XML 落键（actran_analysis_control 等）。

验收（§20.4-I4 双分支）：retval=True（前置构造成功）或
retval=False 但前置构成证据入册（条件全建 err=0 仍被拒 →
前置检查点钉死）。

用法：``py tools/_p12j_i4_run.py [actran]``
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BASE_PPH = ROOT / "p12a_bam_e2e_out.pph"
OUT_PPH = ROOT / "p12j_actran_e2e_out.pph"
VBS = ROOT / "p12j_actran_e2e.vbs"
LOG = ROOT / "p12j_actran_e2e.log"
MON_DIR = ROOT / "_p12j_e2e" / "actran_out"

ACTRAN_CONDS = (
    ("Src_", "CreateCondActranSource", "P12JActranSource"),
    ("Outs_", "CreateCondActranOutputSolution", "P12JActranOutSol"),
    ("NRBC_", "CreateCondActranBoundaryNonReflection", "P12JActranNRBC"),
    ("Absb_", "CreateCondActranBoundaryAbsorption", "P12JActranAbsorb"),
    ("PSrc_", "CreateCondActranPointSource", "P12JActranPointSrc"),
)


def build_actran_groups():
    """Acoustic Session 构造 + CreateActranFilesMonitor 业务复验。"""
    actions = [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        # 前流 SaveProject 落盘未完会拖死 OpenProject（I2 实证）
        "RetWW_ = Doc_.WaitForWorker",
        f'Doc_.OpenProject "{BASE_PPH.as_posix()}", False',
        "Doc_.SetModeMesh",
        "Set Conditions_ = Doc_.GetConditions",
        # Acoustic Session 的分析控制（catalog：scFLOW2Actran 会话的
        # analysis condition）；GetParam 探 C3 实测 XML 键
        "Set Ctrl_ = Conditions_.GetCondActranAnalysisControl",
        'gp1_ = Ctrl_.GetParam("cfd_analysis_type", gpv1_)',
        'out_.WriteLine "ctrl_g1=" & CStr(gp1_) & "|" & CStr(gpv1_) '
        '& " err=" & CStr(Err.Number)',
        "Err.Clear",
    ]
    for var, method, name in ACTRAN_CONDS:
        actions.append(f"Set {var} = Conditions_.{method}(\"{name}\")")
    actions += [
        "Set MG_ = Doc_.QueryMeshingGroupByIndex(0)",
        "Doc_.SetActiveMeshingGroup 0, 0",
        f'monRet_ = MG_.CreateActranFilesMonitor("{MON_DIR.as_posix()}")',
        'out_.WriteLine "mon_ret=" & CStr(monRet_) & " err=" '
        '& CStr(Err.Number)',
        f'monDirOK_ = fso_.FolderExists("{MON_DIR.as_posix()}")',
        "monFiles_ = -1",
        f'If monDirOK_ Then monFiles_ = '
        f'fso_.GetFolder("{MON_DIR.as_posix()}").Files.Count',
        # IIf 两分支皆求值（r1 实测 Err 76），文件计数须惰性 If
        'out_.WriteLine "mon_files=" & CStr(monFiles_) & " err=" '
        '& CStr(Err.Number)',
        f'Doc_.SaveProject "{OUT_PPH.as_posix()}"',
    ]
    return [("actran", actions)]


def verify_actran_log(text: str) -> dict:
    """err=0 全量 + alive + I4 info 行（mon_ret/mon_files/ctrl_g1）。"""
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
    info = {}
    for m in re.finditer(r"^(mon_ret|mon_files|ctrl_g1)=(\S+)",
                         text, re.MULTILINE):
        info[m.group(1)] = m.group(2)
    return {"total": total, "err0": err0, "bad": total - err0,
            "problems": problems[:20], "alive": alive, "info": info,
            "has_end": "end" in text.splitlines()}


def check_out_xml(pph_path: Path = OUT_PPH) -> dict:
    """SaveProject 后离线检 XML：actran 键与构造条件名落键。"""
    out = {"exists": pph_path.is_file(), "keys": [], "names": []}
    if not out["exists"]:
        return out
    with zipfile.ZipFile(pph_path) as zf:
        names = zf.namelist()
        if "main.xml" not in names:
            out["no_xml"] = True
            return out
        xml = zf.read("main.xml").decode("utf-8", "replace")
    out["keys"] = sorted(set(re.findall(
        r"<([A-Za-z_]*[Aa]ctran[A-Za-z_]*)", xml)))
    for _var, _method, name in ACTRAN_CONDS:
        if name in xml:
            out["names"].append(name)
    return out


def load_p12e():
    spec = importlib.util.spec_from_file_location(
        "p12e_run", str(ROOT / "tools" / "_p12e_e2e_run.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    p12e = load_p12e()
    MON_DIR.mkdir(parents=True, exist_ok=True)
    groups = build_actran_groups()
    p12e._write_ansi_vbs(p12e.logged_script(groups, LOG, "p12j I4 actran"),
                         VBS, "p12j I4 actran")
    res = p12e.run_e2e("actran", VBS, LOG, timeout=900.0)
    ok = p12e.gate("actran", res,
                   alive_need=("conditions_", "ctrl_", "mg_", "src_"))
    ver4 = verify_actran_log(
        LOG.read_text(encoding="utf-8", errors="replace")
        if LOG.is_file() else "")
    info = ver4["info"]
    xml = check_out_xml()
    print("[actran] info: " + json.dumps(info, ensure_ascii=False))
    print("[actran] out xml: " + json.dumps(xml, ensure_ascii=False))
    mon_ret = info.get("mon_ret")
    branch = None
    if mon_ret == "True":
        branch = "constructed: CreateActranFiles retval=True"
    elif mon_ret == "False" and ok:
        branch = ("precondition-pinned: 条件全建 err=0 仍 retval=False"
                  "（前置检查点证据入册）")
    print("[actran] BRANCH: " + (branch or "incomplete"))
    summary = {"actran_gate": ok, "mon_ret": mon_ret,
               "mon_files": info.get("mon_files"),
               "xml_keys": xml.get("keys"), "xml_names": xml.get("names"),
               "branch": branch}
    print("SUMMARY: " + json.dumps(summary, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
