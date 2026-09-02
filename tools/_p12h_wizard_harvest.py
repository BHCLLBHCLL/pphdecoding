#!/usr/bin/env python3
"""P12-H 向导收割机 v2：分析族勾选 → Finish 全量投影 → byte-diff 归属。

纪律（DEV_PLAN §19.2/§19.4）：一次一类型、独立工程副本（Finish 全量
投影语义）；基线为 2025.2 原生 CreateProject 工程；归属三类 = 精确键
/ 别名证据 / 纯会话态。GUI 配方 = H1 钉死的 Win32 通道：
WM_COMMAND 34062 开向导 → BM_GETCHECK/BM_CLICK 勾选 → invoke Finish
→ Confirm 循环清模态（确定/关闭）→ COM SaveProject。

用法::

    python tools/_p12h_wizard_harvest.py plan     # 离线：族清单
    python tools/_p12h_wizard_harvest.py base     # 实机：造基线工程
    python tools/_p12h_wizard_harvest.py run      # 实机：逐族收割
    python tools/_p12h_wizard_harvest.py run NAME # 实机：单族
    python tools/_p12h_wizard_harvest.py merge    # 离线：diff → 报告
    python tools/_p12h_wizard_harvest.py all      # base + run + merge
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import hashlib
import json
import subprocess
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCRATCH = ROOT / "scratch"
BASELINE = SCRATCH / "_p12h_h2_base.pph"
OUTDIR = SCRATCH / "_p12h_h2"
REPORT = ROOT / "p12h_wizard_report.json"

USER32 = ctypes.windll.user32
WM_COMMAND = 0x0111
WM_CLOSE = 0x0010
BM_GETCHECK = 0x00F0
BM_CLICK = 0x00F5
SW_RESTORE = 9
CONFIRM_WORDS = {"确定", "OK", "Yes"}

#: 向导第一页 26 分析族（H1 wizdiag2 children 实测；Free surface 已由
#: H1 判定纯会话态，仍纳入批跑作对照锚点）。
FAMILIES = [
    "Flow", "Heat", "Solar radiation", "Radiation", "Humidity", "Lamp",
    "Diffusion", "Reaction", "Particle", "Porous media",
    "Ventilation efficiency", "Air conditioner unit", "Plant canopy",
    "Solidification/melting", "Free surface", "Moving object",
    "Boil/condensation", "Electric current", "Electrostatic field",
    "Thermoregulation model", "Marangoni convection", "MSC CoSim",
    "Topology optimization", "BCI-ROM", "Evaporation(free surf.)",
    "Phase change material", "Variable Registration",
]

WIZ_CMD = 34062  # 菜单 Wizard(&W) → Condition Setting...
HOST_NAME = "STpre_Bx64net"
KICKER_EXE = (r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64"
              r"\Kicker_Bx64.exe")
KICKER_BUTTON = "STPRE"


# ── Win32 基础 ────────────────────────────────────────────────────────────

def host_pids() -> list[int]:
    out = subprocess.run(["tasklist", "-FO", "CSV"], capture_output=True,
                         text=True).stdout
    ps = []
    for line in out.splitlines():
        if HOST_NAME in line:
            try:
                ps.append(int(line.split('","')[1].split('","')[0]))
            except (ValueError, IndexError):
                pass
    return ps


def wins_of(pid: int) -> list[tuple[int, str, str]]:
    proc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    res = []

    def cb(h, lp):
        p = wt.DWORD()
        USER32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and USER32.IsWindowVisible(h):
            c = ctypes.create_unicode_buffer(256)
            USER32.GetClassNameW(h, c, 256)
            t = ctypes.create_unicode_buffer(256)
            USER32.GetWindowTextW(h, t, 256)
            res.append((h, c.value, t.value))
        return True

    USER32.EnumWindows(proc(cb), 0)
    return res


def main_hwnd(pid: int) -> int | None:
    for h, c, t in wins_of(pid):
        if c.startswith("Afx:") and "STpre" in t:
            return h
    return None


def wizard_hwnd(pid: int) -> int | None:
    for h, c, t in wins_of(pid):
        if c == "#32770" and t == "Condition Wizard":
            return h
    return None


def wait_wizard(pid: int, timeout_s: float = 30.0) -> int | None:
    for _ in range(int(timeout_s / 2)):
        time.sleep(2)
        h = wizard_hwnd(pid)
        if h:
            return h
    return None


def boot_host(timeout_s: float = 240.0) -> int | None:
    """Kicker 冷启动宿主（2025.2 名称：STPRE / STpre_Bx64net）。"""
    subprocess.Popen([KICKER_EXE])
    time.sleep(3)
    kick = [p for p in subprocess.run(["tasklist", "-FO", "CSV"],
                                      capture_output=True,
                                      text=True).stdout.splitlines()
            if "Kicker_Bx64" in p]
    if not kick:
        print("kicker failed to start")
        return None
    kpid = int(kick[0].split('","')[1].split('","')[0])
    from pywinauto import Application
    app = Application().connect(process=kpid)
    for _round in range(10):
        for dlg in app.windows():
            if dlg.class_name() != "#32770" or \
                    dlg.rectangle().width() <= 0:
                continue
            try:
                btns = [c for c in dlg.descendants()
                        if c.window_text() == KICKER_BUTTON]
            except Exception:  # noqa: BLE001
                continue
            if btns:
                USER32.ShowWindow(dlg.handle, SW_RESTORE)
                time.sleep(1)
                USER32.PostMessageW(btns[0].handle, 0x00F5, 0, 0)  # BM_CLICK
                print(f"BM_CLICK sent to {KICKER_BUTTON} on kicker {kpid}")
                break
        else:
            time.sleep(2)
            continue
        break
    for _ in range(int(timeout_s / 5)):
        time.sleep(5)
        pids = host_pids()
        if pids:
            # 关 Initial Wizard 模态
            for _w in range(10):
                wz = [(h, t) for h, c, t in wins_of(pids[0])
                      if c == "#32770" and "Initial Wizard" in t]
                if not wz:
                    break
                USER32.PostMessageW(wz[0][0], WM_CLOSE, 0, 0)
                time.sleep(1.5)
            print("host up, pid", pids[0])
            time.sleep(12)  # GUI 就绪等待（实测启动后立即操作不稳）
            return pids[0]
    print("host did not come up")
    return None


# ── COM 段（VBS：OpenProject / SaveProject / GetProjectName） ─────────────

def com_vbs(lines: list[str], name: str, timeout: float = 300.0) -> tuple:
    from automation import host_pipeline
    vbs = OUTDIR / name
    log = OUTDIR / name.replace(".vbs", ".log")
    vbs.write_bytes("\r\n".join(lines).encode("utf-16"))
    run = host_pipeline.run_vbs_authoritative(vbs, timeout=timeout)
    txt = log.read_text(encoding="mbcs", errors="replace") \
        if log.is_file() else "(no log)"
    print(f"[{name}] ok={run.get('ok')}")
    for ln in txt.splitlines():
        if not ln.startswith(("' ", "out.WriteLine", "Set ", "If ", "Err.")):
            print("   ", ln)
    return run, txt


def com_open(pph: Path, tag: str) -> bool:
    _, txt = com_vbs([
        "On Error Resume Next",
        'Set fso = CreateObject("Scripting.FileSystemObject")',
        f'Set out = fso.CreateTextFile("'
        f'{(OUTDIR / f"open_{tag}.log").as_posix()}", True)',
        'out.WriteLine "start"',
        "Set App_ = GetApplication()",
        "Set Doc_ = App_.GetDocument",
        f'Doc_.OpenProject "{pph.as_posix()}", False',
        'out.WriteLine "open_err=" & CStr(Err.Number)',
        "Err.Clear",
        'out.WriteLine "end"',
        "out.Close",
    ], f"open_{tag}.vbs")
    return "open_err=0" in txt and "end" in txt


def com_save(pph: Path, tag: str) -> bool:
    _, txt = com_vbs([
        "On Error Resume Next",
        'Set fso = CreateObject("Scripting.FileSystemObject")',
        f'Set out = fso.CreateTextFile("'
        f'{(OUTDIR / f"save_{tag}.log").as_posix()}", True)',

        'out.WriteLine "start"',
        "Set App_ = GetApplication()",
        "Set Doc_ = App_.GetDocument",
        f'Doc_.SaveProject "{pph.as_posix()}"',
        'out.WriteLine "save_err=" & CStr(Err.Number)',
        "Err.Clear",
        'out.WriteLine "end"',
        "out.Close",
    ], f"save_{tag}.vbs")
    return "save_err=0" in txt and "end" in txt


def com_create_base() -> bool:
    _, txt = com_vbs([
        "On Error Resume Next",
        'Set fso = CreateObject("Scripting.FileSystemObject")',
        f'Set out = fso.CreateTextFile("'
        f'{(OUTDIR / "base_prep.log").as_posix()}", True)',
        'out.WriteLine "start"',
        "Set App_ = GetApplication()",
        "Set Doc_ = App_.GetDocument",
        f'Doc_.CreateProject "{BASELINE.as_posix()}"',
        'out.WriteLine "create_err=" & CStr(Err.Number)',
        "Err.Clear",
        f'Doc_.SaveProject "{BASELINE.as_posix()}"',
        'out.WriteLine "save_err=" & CStr(Err.Number)',
        "Err.Clear",
        'out.WriteLine "end"',
        "out.Close",
    ], "base_prep.vbs")
    return BASELINE.is_file() and "create_err=0" in txt


def current_project_name() -> str | None:
    _, txt = com_vbs([
        "On Error Resume Next",
        'Set fso = CreateObject("Scripting.FileSystemObject")',
        f'Set out = fso.CreateTextFile("'
        f'{(OUTDIR / "curdiag.log").as_posix()}", True)',
        'out.WriteLine "start"',
        "Set App_ = GetApplication()",
        "Set Doc_ = App_.GetDocument",
        'out.WriteLine "name=" & CStr(Doc_.GetProjectName)',
        'out.WriteLine "end"',
        "out.Close",
    ], "curdiag.vbs")
    for ln in txt.splitlines():
        if ln.startswith("name="):
            return ln[5:].strip()
    return None


# ── GUI 段（H1 配方） ─────────────────────────────────────────────────────

def clear_modals(pid: int, max_rounds: int = 10) -> list[str]:
    """循环清 Confirm 类模态（invoke 确定），其余 WM_CLOSE。返回动作日志。"""
    from pywinauto import Application
    actions = []
    for _round in range(max_rounds):
        modals = [m for m in wins_of(pid)
                  if m[1] == "#32770"
                  and m[2] != "Condition Wizard"]
        if not modals:
            return actions
        for h, _cls, title in modals:
            confirm = None
            btn_texts = []
            try:
                app2 = Application(backend="uia").connect(handle=h)
                for b in app2.window(handle=h).descendants():
                    if b.element_info.control_type == "Button":
                        btn_texts.append(b.window_text())
                        if b.window_text() in CONFIRM_WORDS and \
                                not confirm:
                            confirm = b
            except Exception:  # noqa: BLE001
                pass
            print(f"    modal {title!r} buttons={btn_texts}")
            if confirm is not None:
                try:
                    confirm.invoke()
                    actions.append(f"confirm:{title}")
                except Exception:  # noqa: BLE001
                    USER32.PostMessageW(h, WM_CLOSE, 0, 0)
                    actions.append(f"confirm_fail_close:{title}")
            else:
                USER32.PostMessageW(h, WM_CLOSE, 0, 0)
                actions.append(f"close:{title}")
            time.sleep(1.5)
        time.sleep(1.5)
    return actions


def harvest_family(pid: int, family: str, tag: str,
                   out_pph: Path, pre_families: tuple = ()) -> dict:
    """单族收割轮：开向导 → 勾前置族 → 勾目标族 → Finish → Save。"""
    from pywinauto import Application
    rec: dict = {"family": family, "tag": tag,
                 "pre": list(pre_families)}
    main = main_hwnd(pid)
    if main is None:
        rec["error"] = "main window not found"
        return rec
    USER32.ShowWindow(main, SW_RESTORE)
    time.sleep(0.5)
    USER32.PostMessageW(main, WM_COMMAND, wt.WPARAM(WIZ_CMD), 0)
    wz = wait_wizard(pid, 30.0)
    if wz is None:
        rec["error"] = "wizard did not open"
        return rec
    rec["wizard_hwnd"] = hex(wz)
    app2 = Application(backend="uia").connect(handle=wz)
    wiz = app2.window(handle=wz)
    boxes = {c.window_text(): c.handle for c in wiz.children()}

    def check(name: str) -> bool:
        h = boxes.get(name)
        if not h:
            return False
        st = USER32.SendMessageW(h, BM_GETCHECK, 0, 0)
        if not st:
            USER32.SendMessageW(h, BM_CLICK, 0, 0)
            time.sleep(1)
            st = USER32.SendMessageW(h, BM_GETCHECK, 0, 0)
        return bool(st)

    rec["pre_checked"] = {p: check(p) for p in pre_families}
    rec["checked"] = check(family)
    if not rec["checked"]:
        rec["error"] = "BM_CLICK did not check"
        USER32.PostMessageW(wz, WM_CLOSE, 0, 0)
        return rec
    fins = [c for c in wiz.children() if c.window_text() == "Finish"]
    if not fins:
        rec["error"] = "finish button not found"
        USER32.PostMessageW(wz, WM_CLOSE, 0, 0)
        return rec
    try:
        fins[0].invoke()
        rec["finish"] = "uia"
    except Exception:  # noqa: BLE001
        USER32.SendMessageW(fins[0].handle, BM_CLICK, 0, 0)
        rec["finish"] = "bm_click"
    time.sleep(8)
    if not host_pids():
        rec["error"] = "host died after finish"
        return rec
    rec["modals"] = clear_modals(pid)
    time.sleep(2)
    rec["saved"] = com_save(out_pph, tag) and out_pph.is_file()
    return rec


# ── 离线 diff / 归属 ──────────────────────────────────────────────────────

SELF_REF = ("date>", "<name>", "<filename>")

#: Finish 全量投影固有噪声（H2 对照轮实测，与勾选内容无关）：
#: main.xml species value_obj 重排；main.prp 头部 date 字节；
#: main.sctsnapshot 每次 Finish 必重写（+182B）。归一化剔除后再判定。
NOISE_SNAPSHOT = "main.sctsnapshot"


def member_map(p: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(p) as zf:
        return {i.filename: zf.read(i.filename) for i in zf.infolist()}


def _strip_elements(root, tag: str) -> None:
    for parent in root.iter():
        for child in list(parent):
            if child.tag == tag:
                parent.remove(child)


def _norm_member(name: str, raw: bytes):
    """归一化成员：返回可比文本行（或二进制原样）。"""
    if name.endswith(".xml"):
        root = _parse_xml(raw)
        _strip_elements(root, "species")
        text = ET.tostring(root, encoding="unicode")
        return [l for l in text.splitlines()
                if not any(s in l for s in SELF_REF)]
    if name.endswith(".prp"):
        root = ET.fromstring(raw)
        root.attrib.pop("date", None)
        text = ET.tostring(root, encoding="unicode")
        return text.splitlines()
    return raw


def _parse_xml(raw: bytes):
    import pphxml
    return pphxml.parse_main_xml(raw).root


def compare_family(base: dict[str, bytes], out: dict[str, bytes]) -> dict:
    """归一化逐成员比较 → 族判定输入（含内容级哈希供组合归因）。"""
    res: dict = {"added": sorted(set(out) - set(base)),
                 "removed": sorted(set(base) - set(out)),
                 "changed": [], "changed_detail": {},
                 "snapshot_changed": False}
    for k in sorted(set(base) & set(out)):
        if base[k] == out[k]:
            continue
        if k == NOISE_SNAPSHOT:
            res["snapshot_changed"] = True
            continue
        nb, no = _norm_member(k, base[k]), _norm_member(k, out[k])
        if nb != no:
            res["changed"].append(k)
            res["changed_detail"][k] = {
                "base": _content_hash(nb), "out": _content_hash(no)}
    return res


def _content_hash(norm) -> str:
    import hashlib
    data = norm if isinstance(norm, bytes) else \
        "\n".join(norm).encode("utf-8", "replace")
    return hashlib.sha1(data).hexdigest()[:12]


def merge() -> dict:
    if not BASELINE.is_file():
        return {"error": "baseline missing"}
    base = member_map(BASELINE)
    report: dict = {"baseline": str(BASELINE), "families": {}}
    for family in FAMILIES:
        tag = _tag(family)
        out_p = OUTDIR / f"out_{tag}.pph"
        if not out_p.is_file():
            report["families"][family] = {"status": "not_run"}
            continue
        out = member_map(out_p)
        cmp_res = compare_family(base, out)
        pre_p = OUTDIR / f"out_{tag}_pre.pph"
        if pre_p.is_file():
            pre_cmp = compare_family(base, member_map(pre_p))
            pre_changed = set(pre_cmp["changed"])
            pre_detail = pre_cmp.get("changed_detail", {})
            extra = [k for k in cmp_res["changed"]
                     if k not in pre_changed
                     or pre_detail.get(k, {}).get("out")
                     != cmp_res["changed_detail"].get(k, {}).get("out")]
            extra += [k for k in cmp_res["added"]
                      if k not in pre_cmp["added"]]
            extra += [k for k in cmp_res["removed"]
                      if k not in pre_cmp["removed"]]
            cmp_res["pre_changed"] = pre_cmp["changed"]
            cmp_res["target_contribution"] = extra
            verdict = ("keys_projected" if extra or cmp_res["added"]
                       or cmp_res["removed"] else "session_state")
            cmp_res["attribution"] = "combo_vs_pre"
        else:
            if not cmp_res["changed"] and not cmp_res["added"] \
                    and not cmp_res["removed"]:
                verdict = "session_state"
            else:
                verdict = "keys_projected"
            cmp_res["attribution"] = "vs_base"
        cmp_res["verdict"] = verdict
        report["families"][family] = {"status": "ok", **cmp_res}
    REPORT.write_text(json.dumps(report, indent=1, ensure_ascii=False),
                      encoding="utf-8")
    return report


def _tag(family: str) -> str:
    keep = "".join(ch if ch.isalnum() else "_" for ch in family)
    return keep[:28]


# ── 命令 ──────────────────────────────────────────────────────────────────

def ensure_env() -> int:
    pid = host_pids()
    if not pid:
        b = boot_host()
        if not b:
            raise SystemExit("no host")
        pid = [b]
    OUTDIR.mkdir(exist_ok=True)
    return pid[0]


def ensure_base(pid: int) -> None:
    if BASELINE.is_file():
        return
    if not com_create_base():
        raise SystemExit("baseline create failed")


def cmd_run(only: str | None = None) -> None:
    pid = ensure_env()
    ensure_base(pid)
    for family in FAMILIES:
        if only and family != only:
            continue
        tag = _tag(family)
        out_p = OUTDIR / f"out_{tag}.pph"
        if out_p.is_file():
            print(f"[{family}] already harvested, skip")
            continue
        print(f"===== {family} ({tag}) =====")
        if not com_open(BASELINE, tag):
            print(f"[{family}] open failed — recheck host")
            if not host_pids():
                print("[host] died — cold rebooting")
                pid = boot_host() or pid
                ensure_base(pid)
            else:
                print(f"[{family}] current project: "
                      f"{current_project_name()}")
            continue
        time.sleep(2)
        pid, rec = run_family_with_retry(pid, family, tag, out_p)
        print(f"[{family}] result:", json.dumps(rec, ensure_ascii=False))
    print("merge:")
    rep = merge()
    verdicts = {k: v.get("verdict", v.get("status"))
                for k, v in (rep.get("families") or {}).items()}
    print(json.dumps(verdicts, ensure_ascii=False, indent=1))


def run_family_with_retry(pid: int, family: str, tag: str,
                          out_pph: Path, pre_families: tuple = (),
                          attempts: int = 3) -> tuple[int, dict]:
    """BM_CLICK 勾选跨向导会话不稳定（实测）——失败即冷重启宿主重试。"""
    rec = {}
    for attempt in range(1, attempts + 1):
        time.sleep(5)
        rec = harvest_family(pid, family, tag, out_pph,
                             pre_families=pre_families)
        if not rec.get("error") and rec.get("saved"):
            rec["attempt"] = attempt
            return pid, rec
        print(f"[{family}] attempt {attempt} failed: "
              f"{rec.get('error')} — reboot")
        if host_pids():
            subprocess.run(["taskkill", "-F", "-PID", str(host_pids()[0])],
                           capture_output=True)
            time.sleep(3)
        pid = boot_host() or pid
        if not pid:
            break
        ensure_base(pid)
    rec["attempt"] = attempts
    return pid, rec


def cmd_runcombo(target: str, prereqs: str) -> None:
    pid = ensure_env()
    ensure_base(pid)
    pre = tuple(p.strip() for p in prereqs.split(",") if p.strip())
    tag = _tag(target)
    pre_tag = tag + "_pre"
    print("===== pre-only control:", pre, "=====")
    if not (OUTDIR / f"out_{pre_tag}.pph").is_file():
        if not com_open(BASELINE, pre_tag):
            raise SystemExit("pre open failed")
        time.sleep(2)
        pid, rec = run_family_with_retry(
            pid, pre[0], pre_tag, OUTDIR / f"out_{pre_tag}.pph",
            pre_families=pre[1:])
        print("pre result:", json.dumps(rec, ensure_ascii=False))
    print("===== combo:", target, "+", pre, "=====")
    if not com_open(BASELINE, tag):
        raise SystemExit("combo open failed")
    time.sleep(2)
    pid, rec = run_family_with_retry(
        pid, target, tag, OUTDIR / f"out_{tag}.pph", pre_families=pre)
    print("combo result:", json.dumps(rec, ensure_ascii=False))
    rep = merge()
    fam = rep.get("families", {}).get(target)
    print("merge verdict:", json.dumps(fam, ensure_ascii=False)[:400])


def main(argv: list[str]) -> None:
    cmd = argv[1] if len(argv) > 1 else "plan"
    if cmd == "plan":
        print(json.dumps({"families": FAMILIES, "n": len(FAMILIES),
                          "baseline": str(BASELINE)}, indent=1))
    elif cmd == "base":
        pid = ensure_env()
        ensure_base(pid)
        print("baseline:", BASELINE.is_file())
    elif cmd == "run":
        cmd_run(argv[2] if len(argv) > 2 else None)
    elif cmd == "runcombo":
        if len(argv) < 4:
            raise SystemExit("runcombo TARGET PRE1,PRE2")
        cmd_runcombo(argv[2], argv[3])
    elif cmd == "merge":
        rep = merge()
        print(json.dumps(
            {k: v.get("verdict", v.get("status"))
             for k, v in (rep.get("families") or {}).items()},
            ensure_ascii=False, indent=1))
    elif cmd == "all":
        cmd_run(None)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
