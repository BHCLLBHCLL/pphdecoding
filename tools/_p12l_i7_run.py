"""P12-L Sprint I7（可选 backlog）：CATIA 样本实机导入探针。

I7 全机再扫（``tools/_p12l_i7_scan.py``）推翻 §18.8-G3「全机 0 真
CATIA 样本」前提：``D:\\training\\starccm\\startutorialsdata\\
starcat5\\data\\`` 发现 15 个真 CATIA V5 文件（魔数 ``V5_CFV2``，
STAR-CCM+ 教程数据；G3 扫描漏网）。本驱动把域 4「CATIA 样本缺失」
边界项升级为实测：

1. **catia_open 流**：裸宿主 → OpenProject（2025.2 自存 box 副本）
   → ``Set SN_ = Doc_.OpenCadFile("<CATPart>")``（SNode retval，
   括号形式 §10.8）+ ``QuerySNodeByName("Part")`` 双探针 → SaveProject；
2. **catia_facet 流**：OpenProject（独立副本）→ CreateMeshingGroup
   → ``ret_ = Doc_.ImportCADAsFacet("<CATPart>", MG_)`` retval 捕获
   → SaveProject。

验收：retval 接纳（非 Nothing / True）→ 域 4 CATIA 导入链实测绿，
边界项升级；拒 → 拒绝证据入册（许可特性 "CAD Translator - CATIA V5
R/RW" 是否授权 / 产品闸门）。注意许可缺失时 CADthru 可能弹
"No valid license found to import CATIA V5 File" 模态——watchdog
模态处置兜底，info 行照记。

用法：``py tools/_p12l_i7_run.py``
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import automation.host_boot as host_boot  # noqa: E402

SRC_PPH = ROOT / "_p12a_e2e" / "box.pph"
WORK = ROOT / "_p12l_i7"
CATIA_PART = Path(
    r"D:\training\starccm\startutorialsdata\starcat5\data"
    r"\PorousMiddle.CATPart")
XT_PART = ROOT / "tests" / "box" / "box.x_t"
FLOWS = (
    ("catia_open", "c1"),
    ("catia_facet", "c2"),
    ("facet_xt", "c3"),
)


def load_p12e():
    spec = importlib.util.spec_from_file_location(
        "p12e_run", str(ROOT / "tools" / "_p12e_e2e_run.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_groups(which: str, src: Path, out: Path):
    header = [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        # 前流 SaveProject 落盘未完会拖死 OpenProject（I2 实证）
        "RetWW_ = Doc_.WaitForWorker",
        f'Doc_.OpenProject "{src.as_posix()}", False',
    ]
    if which == "catia_open":
        actions = header + [
            f'Set SN_ = Doc_.OpenCadFile("{CATIA_PART.as_posix()}")',
            'If SN_ Is Nothing Then out_.WriteLine "sn__alive=False" '
            'Else out_.WriteLine "sn__alive=True"',
            'Set SN2_ = Doc_.QuerySNodeByName("Part")',
            'If SN2_ Is Nothing Then out_.WriteLine "sn2__alive=False" '
            'Else out_.WriteLine "sn2__alive=True"',
            f'Doc_.SaveProject "{out.as_posix()}"',
        ]
    else:
        cad = CATIA_PART if which == "catia_facet" else XT_PART
        actions = header + [
            "Set MG_ = Doc_.CreateMeshingGroup",
            f'ret_ = Doc_.ImportCADAsFacet("{cad.as_posix()}", MG_)',
            'out_.WriteLine "f_ret=" & CStr(ret_) & " err=" '
            '& CStr(Err.Number)',
            "Err.Clear",
            'If MG_ Is Nothing Then out_.WriteLine "mg__alive=False" '
            'Else out_.WriteLine "mg__alive=True"',
            f'Doc_.SaveProject "{out.as_posix()}"',
        ]
    return actions


def verify_log(text: str) -> dict:
    total = err0 = 0
    problems = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line in ("start", "end"):
            continue
        m = re.match(r"^s\d+=(-?\d+)$", line)
        if not m:
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
            for m in re.finditer(r"^(f_ret|f_err)=(\S+)", text,
                                 re.MULTILINE)}
    return {"total": total, "err0": err0, "bad": total - err0,
            "problems": problems[:20], "alive": alive, "info": info,
            "has_end": "end" in text.splitlines()}


def member_diff(out_pph: Path, src_pph: Path = SRC_PPH) -> dict:
    out = {"exists": out_pph.is_file(), "new": [], "gone": []}
    if not out["exists"]:
        return out
    with zipfile.ZipFile(out_pph) as zo, zipfile.ZipFile(src_pph) as zs:
        a, b = set(zs.namelist()), set(zo.namelist())
    out["new"] = sorted(b - a)
    out["gone"] = sorted(a - b)
    return out


def main() -> int:
    p12e = load_p12e()
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if not CATIA_PART.is_file():
        print("SUMMARY: " + json.dumps(
            {"error": f"CATIA sample missing: {CATIA_PART}"}))
        return 1
    WORK.mkdir(parents=True, exist_ok=True)
    flows = [(n, t) for n, t in FLOWS if only in (None, n)]
    if not flows:
        print(f"unknown flow: {only}; choose from {[n for n, _ in FLOWS]}")
        return 1
    pid = host_boot.cold_boot()
    print(f"[i7] fresh host pid={pid}", flush=True)
    results = {}
    for name, tag in flows:
        src = WORK / f"{tag}.pph"
        out = WORK / f"{tag}_out.pph"
        vbs = ROOT / f"p12l_{name}_e2e.vbs"
        log = ROOT / f"p12l_{name}_e2e.log"
        shutil.copyfile(SRC_PPH, src)
        groups = [(name, build_groups(name, src, out))]
        p12e._write_ansi_vbs(
            p12e.logged_script(groups, log, f"p12l I7 {name}"),
            vbs, f"p12l I7 {name}")
        res = p12e.run_e2e(name, vbs, log, timeout=1200.0,
                           retry_with_boot=True)
        ok = p12e.gate(name, res, min_checks=4)
        ver = verify_log(
            log.read_text(encoding="utf-8", errors="replace")
            if log.is_file() else "")
        md = member_diff(out)
        print(f"[{name}] alive: " + json.dumps(ver["alive"]))
        print(f"[{name}] info: " + json.dumps(ver["info"]))
        print(f"[{name}] members: " + json.dumps(md))
        results[name] = {"gate": ok, "verify": ver, "members": md,
                         "vbs_ret": res.get("vbs_ret")}
    open_r = results.get("catia_open")
    facet_r = results.get("catia_facet")
    accepted = (open_r and open_r["verify"]["alive"].get("sn_") == "True") \
        or (facet_r and facet_r["verify"]["info"].get("f_ret") == "True")
    ended = [r["verify"]["has_end"] for r in results.values()]
    if accepted:
        branch = ("imported: 真 CATIA V5 样本经宿主 Datakit 链接纳——"
                  "域 4 边界项实测升级")
    elif all(ended) and ended:
        branch = ("rejected: 样本在位但导入链拒（ret/alive 证据入册，"
                  "许可或产品闸门）")
    else:
        branch = "incomplete"
    summary = {
        "catia_open_gate": open_r["gate"] if open_r else None,
        "catia_facet_gate": facet_r["gate"] if facet_r else None,
        "sn_alive": open_r["verify"]["alive"].get("sn_")
        if open_r else None,
        "sn2_alive": open_r["verify"]["alive"].get("sn2_")
        if open_r else None,
        "f_ret": facet_r["verify"]["info"].get("f_ret")
        if facet_r else None,
        "c1_members": open_r["members"] if open_r else None,
        "c2_members": facet_r["members"] if facet_r else None,
        "branch": branch,
    }
    print("SUMMARY: " + json.dumps(summary, ensure_ascii=False))
    return 0 if all(r["gate"] for r in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
