#!/usr/bin/env python3
"""P12-H3 特殊 6 类处置复验机。

Sprint C 遗留的 6 个特殊类（aliased 4 / FMI 未落盘 1 / save_poison 1）
+ H2 移交的 Thermoregulation 深页门控并轨。对 6 类中可达者逐类跑
隔离臂（独立 VBS：OpenProject 2025.2 原生基线 → 实测签名 create →
强制脏 → SaveProject 独立产物），落点离线归并 →
``p12h_special6_report.json`` 每类处置（键 / 别名 / 边界声明）。

复验动机（P12-C 产物考古结论）：
- ``BoundaryHumidity`` 唯一留有落盘证据（P12cHBoundaryHumidity →
  type=``HumidityBoundary``，= 已注册别名 CondHumidity）；
- ``OutputLFileWaterLevel`` create True 但产物缺行——落点未知；
- ``ParticleConcentrationFpDEM``/``Repulsion`` 末轮 noarg 重试返回
  Nothing，但 catalog 实测签名分别要求 ``particlepropertyname`` 与
  ``(target1, target2Type, target2Name)``——C 轮失败可能是签名问题
  而非门控，须按真实签名复验；
- ``FMIVariable`` create True 不落 main.xml——前置使能条件未查
  （本机补 SetFMIParam 配置臂 + 会话探针）；
- ``BatteryARCDataPreprocessing`` 保存毒不再实机复跑（C 轮 probe
  二分已钉死，隔离声明即可）。

CLI:
  plan              打印臂矩阵
  run <arm|all>     实机执行（rot 权威通道 + 模态看守线程）
  merge             离线归并 → 报告 + cond_types.json dispositions 入册
  all               run all + merge
"""
from __future__ import annotations

import json
import ctypes
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import host_pipeline  # noqa: E402

BASELINE = ROOT / "p12e_disc_e2e_out.pph"
REPORT = ROOT / "p12h_special6_report.json"
COND_TYPES = ROOT / "schemas" / "cond_types.json"
MERGED = ROOT / "schemas" / "merged.json"
PREFIX = "P12h3"

# 署名类名（universe）→ create 方法 + 各签名形状。每形状独立探针行；
# 形状间带 If Cnd_ Is Nothing 条件重试（成功不重复建）。
ARMS: dict[str, dict] = {
    "humidity": {
        "universe": "CondBoundaryHumidity",
        "note": "C 轮唯一留有落盘证据（→HumidityBoundary），复验钉死",
        "calls": [
            ("named", 'Conditions_.CreateCondBoundaryHumidity("'
             + PREFIX + 'BoundaryHumidity")'),
            ("noarg", "Conditions_.CreateCondBoundaryHumidity()"),
        ],
    },
    "waterlevel": {
        "universe": "CondOutputLFileWaterLevel",
        "note": "C 轮 create True 但产物缺行，落点未知",
        "locus": "main.xml:output_timing/condition@name（无 type 短名）",
        "calls": [
            ("named", 'Conditions_.CreateCondOutputLFileWaterLevel("'
             + PREFIX + 'OutputLFileWaterLevel")'),
            ("noarg", "Conditions_.CreateCondOutputLFileWaterLevel()"),
        ],
    },
    "fpdem": {
        "universe": "CondParticleConcentrationFpDEM",
        "note": "签名 = (particlepropertyname)；C 轮 noarg 返回 Nothing",
        "calls": [
            ("propname", 'Conditions_.CreateCondParticleConcentrationFpDEM("'
             + PREFIX + 'ParticleProperty")'),
            ("noarg", "Conditions_.CreateCondParticleConcentrationFpDEM()"),
        ],
    },
    "repulsion": {
        "universe": "CondRepulsion",
        "note": "签名 = (target1, target2Type, target2Name)；C 轮 noarg 返回 Nothing",
        "calls": [
            ("three", 'Conditions_.CreateCondRepulsion("' + PREFIX
             + 'RepTarget1", 0, "' + PREFIX + 'RepTarget2")'),
            ("named", 'Conditions_.CreateCondRepulsion("'
             + PREFIX + 'Repulsion")'),
            ("noarg", "Conditions_.CreateCondRepulsion()"),
        ],
    },
    "fmi_plain": {
        "universe": "CondFMIVariable",
        "note": "create + 会话探针（IsFMIVariableNameUsed/GetFMIVariables），无配置",
        "locus": "main.xml:cosim_struct_data/fmi/variables/variable@name",
        "calls": [
            ("named", 'Conditions_.CreateFMIVariable("'
             + PREFIX + 'FMIVariable")'),
        ],
        "probes": ["fmi_used", "fmi_list"],
    },
    "fmi_param": {
        "universe": "CondFMIVariable",
        "note": "create + SetFMIParam 配置置脏 + 会话探针",
        "locus": "main.xml:cosim_struct_data/fmi/variables/variable@name",
        "calls": [
            ("named", 'Conditions_.CreateFMIVariable("'
             + PREFIX + 'FMIVariableP")'),
        ],
        "fmi_param": ("P12h3Key", "1"),
        "probes": ["fmi_used", "fmi_list"],
    },
}

# 不实机复跑的静态处置（证据在册）
STATIC_DISPOSITIONS = {
    "CondBatteryARCDataPreprocessing": {
        "kind": "poison_isolated",
        "target": None,
        "evidence": "P12-C probe 二分钉死：create err=0 但序列化毒杀同脚本 "
                    "SaveProject（p12c_save_probe 轮）；收割机毒类型排除；"
                    "H3 隔离声明不复跑（防宿主状态污染）",
    },
    "Thermoregulation": {
        "kind": "wizard_session_state_gated",
        "target": None,
        "evidence": "H2 batch：分析族 checkbox BM_CLICK 3 轮无效（Heat 前置"
                    "解锁链未通，深页门控）；按 §19.5 族勾选零键模型，解锁后"
                    "预期仍为纯会话态（与 68 类同归属），账面归属 "
                    "wizard_session_state 并保留门控注记",
    },
}


def arm_paths(arm: str) -> tuple[Path, Path, Path]:
    base = ROOT / f"p12h3_{arm}"
    return base.with_suffix(".vbs"), base.with_suffix(".log"), \
        ROOT / f"p12h3_{arm}_out.pph"


def build_arm_vbs(arm: str) -> list[str]:
    spec = ARMS[arm]
    vbs, log, out = arm_paths(arm)
    lines = [
        "' P12-H3 special-6 disposition arm: " + arm,
        "' !! Run inside scFLOWpre host only (rot authoritative channel).",
        "On Error Resume Next",
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        'Set fso = CreateObject("Scripting.FileSystemObject")',
        f'Set out = fso.CreateTextFile("{log.as_posix()}", True)',
        f'Doc_.OpenProject "{BASELINE.as_posix()}", False',
        'out.WriteLine "open_err=" & CStr(Err.Number)',
        "Err.Clear",
        "Set Conditions_ = Doc_.GetConditions",
        'out.WriteLine "cond_alive=" & CStr(Not (Conditions_ Is Nothing))'
        ' & " err=" & CStr(Err.Number)',
        "Err.Clear",
        "Set Cnd_ = Nothing",
    ]
    for i, (shape, call) in enumerate(spec["calls"]):
        kw = "If" if i else "If"  # 首形状必执行，其余仅在前者失败时
        if i:
            lines += [f"{kw} Cnd_ Is Nothing Then"]
        lines += [f"    Set Cnd_ = {call}",
                  f'    out.WriteLine "create_{shape}=" '
                  '& CStr(Not (Cnd_ Is Nothing)) & " err=" & CStr(Err.Number)',
                  "    Err.Clear"]
        if i:
            lines += ["End If"]
    if "fmi_param" in spec:
        k, v = spec["fmi_param"]
        lines += [
            f"pv_ = Conditions_.SetFMIParam(\"{k}\", \"{v}\")",
            'out.WriteLine "fmi_param_err=" & CStr(Err.Number)',
            "Err.Clear",
        ]
    for probe in spec.get("probes", []):
        if probe == "fmi_used":
            lines += [
                f'pu_ = Conditions_.IsFMIVariableNameUsed("{PREFIX}'
                'FMIVariable")',
                'out.WriteLine "fmi_used=" & CStr(pu_) & " err=" '
                '& CStr(Err.Number)',
                "Err.Clear",
            ]
        elif probe == "fmi_list":
            lines += [
                "pl_ = Conditions_.GetFMIVariables()",
                'out.WriteLine "fmi_list_err=" & CStr(Err.Number)',
                "Err.Clear",
            ]
    lines += [
        "v_ = Conditions_.SetDefaultTemperature(300.0)",
        'out.WriteLine "dirty_err=" & CStr(Err.Number)',
        "Err.Clear",
        f'Doc_.SaveProject "{out.as_posix()}"',
        'out.WriteLine "save_err=" & CStr(Err.Number)',
        "Err.Clear",
        'out.WriteLine "out_exists=" & CStr(fso.FileExists("'
        + out.as_posix() + '"))',
        'out.WriteLine "end"',
        "out.Close",
    ]
    return lines


# ── 模态看守（P12-C 看门狗内联：否按钮优先，否则 WM_CLOSE） ──────────────


def _watch_modals(pid: int, stop: threading.Event) -> None:
    user32 = ctypes.windll.user32
    EnumWindowsProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def text(hwnd, fn):
        buf = ctypes.create_unicode_buffer(256)
        fn(hwnd, buf, 256)
        return buf.value

    def pid_of(hwnd):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        return p.value

    while not stop.is_set():
        modals = []

        def cb(hwnd, lp):
            if pid_of(hwnd) == pid and user32.IsWindowVisible(hwnd) \
                    and text(hwnd, user32.GetClassNameW) == "#32770" \
                    and text(hwnd, user32.GetWindowTextW):
                modals.append((hwnd, text(hwnd, user32.GetWindowTextW)))
            return True

        user32.EnumWindows(EnumWindowsProc(cb), 0)
        for hwnd, title in modals:
            print("[watch] modal:", repr(title), flush=True)
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        stop.wait(2.0)


def run_arm(arm: str) -> dict:
    vbs, _log, _out = arm_paths(arm)
    vbs.write_text("\r\n".join(build_arm_vbs(arm)), encoding="mbcs")
    host_pid = _find_host_pid()
    stop = threading.Event()
    th = threading.Thread(target=_watch_modals,
                          args=(host_pid, stop), daemon=True)
    th.start()
    try:
        run = host_pipeline.run_vbs_authoritative(vbs, timeout=300.0)
    finally:
        stop.set()
        th.join(timeout=5)
    log_text = _log.read_text(encoding="mbcs", errors="replace") \
        if _log.is_file() else ""
    print(f"[{arm}] run:", json.dumps(run, ensure_ascii=False))
    for line in log_text.splitlines():
        print(f"[{arm}]", line)
    ok = ("end" in log_text and "save_err=0" in log_text
          and "open_err=0" in log_text)
    return {"ok": ok, "log": log_text}


def _find_host_pid() -> int:
    out = subprocess_run(["tasklist", "/FO", "CSV"])
    for line in out.splitlines()[1:]:
        parts = line.split('","')
        if parts and "STpre_Bx64net" in parts[0]:
            return int(parts[1].strip('"'))
    raise RuntimeError("host not running")


def subprocess_run(cmd: list[str]) -> str:
    import subprocess
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=20).stdout


# ── 离线归并 ──────────────────────────────────────────────────────────────


def parse_log(arm: str) -> dict:
    _vbs, log, _out = arm_paths(arm)
    facts: dict = {"creates": {}, "probes": {}}
    if not log.is_file():
        return facts
    for line in log.read_text(encoding="mbcs", errors="replace").splitlines():
        if "=" not in line:
            continue
        key, _, val = line.strip().partition("=")
        if key.startswith("create_"):
            facts["creates"][key[len("create_"):]] = val.split()[0]
        elif key.startswith(("fmi_", "open_", "save_", "dirty_",
                             "out_exists", "cond_alive")):
            facts["probes"][key] = val.split()[0]
    return facts


def parse_out_conditions(arm: str) -> tuple[list[tuple[str, str]],
                                            list[str]]:
    """产物四选一扫描：(PREFIX* 条件 (name, type) 列表, 含 PREFIX
    字样的 zip 成员名列表)。只看 main.xml 会漏 main.prp/xenv 落点
    （H1 方法学：四选一要全成员 byte 扫描）。"""
    import zipfile

    import pphxml
    _vbs, _log, out = arm_paths(arm)
    if not out.is_file():
        return [], []
    pairs: list[tuple[str, str]] = []
    prefix_members: list[str] = []
    with zipfile.ZipFile(out) as zf:
        for info in zf.infolist():
            data = zf.read(info.filename)
            if PREFIX.encode() in data:
                prefix_members.append(info.filename)
            if info.filename != "main.xml":
                continue
            mx = pphxml.parse_main_xml(data)
            for c in mx.root.iter("condition"):
                t = c.find("type")
                n = c.find("name")
                if t is None or n is None:
                    continue
                name = (n.text or "").strip()
                if name.startswith(PREFIX):
                    pairs.append((name, (t.text or "").strip()))
    return pairs, prefix_members


def classify(arm: str, facts: dict, landed: list[tuple[str, str]],
             prefix_members: list[str], aliases: dict,
             exact_keys: set[str], universe: str) -> dict:
    """单臂归类：exact_key / alias / aliased_to_known / member_locus /
    not_serialized / create_returns_nothing。"""
    created = any(v == "True" for v in facts["creates"].values())
    if landed:
        types = sorted({t for _n, t in landed})
        if universe in types:
            return {"kind": "exact_key", "landed_types": types}
        alias_hits = {t: aliases[t] for t in types if t in aliases}
        if alias_hits:
            return {"kind": "alias", "landed_types": types,
                    "targets": sorted(set(alias_hits.values()))}
        known = [t for t in types if t in exact_keys]
        if known:
            return {"kind": "aliased_to_known", "landed_types": types,
                    "targets": known}
        return {"kind": "new_shortname", "landed_types": types}
    if prefix_members:
        return {"kind": "member_locus", "landed_types": [],
                "members": prefix_members}
    if created:
        return {"kind": "not_serialized", "landed_types": []}
    return {"kind": "create_returns_nothing", "landed_types": []}


def merge() -> dict:
    aliases = json.loads(COND_TYPES.read_text(encoding="utf-8"))["aliases"]
    merged = json.loads(MERGED.read_text(encoding="utf-8"))
    exact_keys = set(merged["conditions"]["types"])
    report: dict = {
        "baseline": str(BASELINE),
        "prefix": PREFIX,
        "arms": {},
        "dispositions": {},
        "static_dispositions": STATIC_DISPOSITIONS,
    }
    for arm, spec in ARMS.items():
        facts = parse_log(arm)
        landed, prefix_members = parse_out_conditions(arm)
        verdict = classify(arm, facts, landed, prefix_members, aliases,
                           exact_keys, spec["universe"])
        report["arms"][arm] = {
            "universe": spec["universe"], "note": spec["note"],
            "creates": facts["creates"], "probes": facts["probes"],
            "landed": landed, "prefix_members": prefix_members,
            "verdict": verdict,
        }
        target = (verdict.get("targets") or [None])[0]
        if target is None and verdict["kind"] == "member_locus":
            target = spec.get("locus")
        report["dispositions"][spec["universe"]] = {
            "kind": verdict["kind"],
            "target": target,
            "evidence": f"p12h3_{arm} 臂（{arm_paths(arm)[1].name} + "
                        f"{arm_paths(arm)[2].name}）；{spec['note']}",
        }
    report["dispositions"].update(STATIC_DISPOSITIONS)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    _patch_cond_types(report["dispositions"])
    print("report ->", REPORT)
    for name, d in report["dispositions"].items():
        print(f"  {name}: {d['kind']} -> {d.get('target')}")
    return report


def _patch_cond_types(dispositions: dict) -> None:
    data = json.loads(COND_TYPES.read_text(encoding="utf-8"))
    merged_disp = dict(data.get("dispositions", {}))
    merged_disp.update(dispositions)
    data["dispositions"] = merged_disp
    data["version"] = data.get("version", 1) + 1
    COND_TYPES.write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv: list[str]) -> int:
    if not argv or argv[0] == "plan":
        for arm, spec in ARMS.items():
            print(f"{arm:12s} {spec['universe']:36s} {spec['note']}")
        print("static      " + ", ".join(STATIC_DISPOSITIONS))
        return 0
    cmd = argv[0]
    if cmd == "merge":
        merge()
        return 0
    if cmd in ("run", "all"):
        arms = list(ARMS) if len(argv) < 2 else [argv[1]]
        bad = []
        for arm in arms:
            res = run_arm(arm)
            if not res["ok"]:
                bad.append(arm)
        if bad:
            print("ARMS FAILED:", bad)
        if cmd == "all" and not bad:
            merge()
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
