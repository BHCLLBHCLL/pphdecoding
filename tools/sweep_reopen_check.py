#!/usr/bin/env python3
"""R51-2：普查**复验窗口**检查 —— 一条命令回答"要不要重开普查"。

普查在 R50 收口（见审计 §64.3），收口时写明三个复验窗口。本工具把那条人工判断
变成可跑的检查，输入是三份**客观事实**：

| 事实 | 来源 | 触发重开 |
|---|---|---|
| 宿主版本变了 | 注册表里的 @@scFLOWpre_Bx64net.Application.*@@ vs 证据里的 @@progid@@ | ✅ 硬 |
| 目录在普查**之后**改过 | @@schemas/vb_api_catalog.json@@ 的 mtime vs 证据时间 | ✅ 硬 |
| 覆盖率掉到收口下限以下 | 证据 coverage vs @@--floor@@（默认 155） | ✅ 硬 |
| 工程集变了 | @@tools/host_member_sweep.DEFAULT_PROJECTS@@ vs 证据里的工程名 | ⚠️ 软（只记不改判） |

用法::

    python tools/sweep_reopen_check.py            # 打印结论（建议重开 → exit 1）
    python tools/sweep_reopen_check.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console_utf8  # noqa: E402

console_utf8.enable()

AVAIL = ROOT / "schemas" / "host_member_availability.json"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
#: R50-3 收口下限（只许升）
FLOOR_CLASSES = 155


def host_versions() -> list:
    """注册表里已安装的 scFLOWpre ProgID 版本（取不到就空表，不猜）。"""
    try:
        import winreg
        out = []
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, r"SOFTWARE\Classes") as key:
                    i = 0
                    while True:
                        try:
                            name = winreg.EnumKey(key, i)
                        except OSError:
                            break
                        i += 1
                        if name.lower().startswith("scflowpre") \
                                and "application" in name.lower():
                            out.append(name)
            except OSError:
                continue
        return sorted(set(out))
    except Exception:  # noqa: BLE001
        return []


def _progid_version(progid: str) -> str:
    """ProgID → 版本串。形态是 @@<前缀>.Application.<版本>@@ —— 取 @@Application.@@
    之后那一段（R56 实测：按"最后一个点"切会把 @@…Application.2025.2@@ 切成 "2"）。
    """
    s = str(progid or "")
    low = s.lower()
    if ".application." in low:
        return s[low.index(".application.") + len(".application."):]
    return s.rsplit(".", 1)[-1]


def installed_versions() -> list:
    """本机装了哪些 Cradle 版本（读安装目录；取不到就空表）。

    R56-3：比注册表更贴近"在用哪个版本" —— 注册表里旧版本的 ProgID 可能还在，
    但安装目录里已经只剩新版本。
    """
    try:
        base = Path(r"C:\Program Files\Cradle")
        if not base.is_dir():
            return []
        out = []
        for p in base.iterdir():
            m = p.name.lower()
            if p.is_dir() and m.startswith("cradlecfd"):
                out.append(p.name[len("CradleCFD"):] if m.startswith(
                    "cradlecfd") else p.name)
        return sorted(set(out))
    except Exception:  # noqa: BLE001
        return []


def version_verdict(evidence_progid: str, registry: list,
                    installed: list | None = None) -> dict:
    """R56-3：三种情形分开说 —— **证据版本没了** / **仍在装但有更新的** / **只有它**。

    以前只判"证据里的版本在不在注册表集合里"，于是"装了 2025.3、2025.2 还留着"
    与"只剩 2025.3"给的是同一个结论（都是"在"），没有指向该用哪个版本复验。
    """
    want = _progid_version(evidence_progid)
    reg_versions = sorted({_progid_version(p) for p in registry}) if registry \
        else []
    dirs = sorted(set(installed if installed is not None
                      else installed_versions()))
    res = {"evidence_version": want, "registry_versions": reg_versions,
           "installed_versions": dirs, "reopen": False, "warnings": [],
           "reasons": []}
    if not want or want == "":
        res["warnings"].append("证据里没写宿主版本，无法比对")
        return res
    pool = set(reg_versions) | set(dirs)
    # 版本串形态不一：ProgID 尾缀是 "2025"（主版本）、安装目录是 "2025.2"（细分）。
    # 判据按**主版本**比：主版本不在 → 版本变了（硬理由）。
    want_major = want.split(".")[0]
    majors = {v.split(".")[0] for v in pool}
    if pool and want_major not in majors:
        res["reopen"] = True
        res["reasons"].append("宿主版本变了：证据是 " + want + "，本机现在是 "
                              + ", ".join(sorted(pool)))
        return res
    if "." in want:
        # 证据记的是**细版本**：安装目录里找不到它、但有更高的 → 也算变了
        gone = sorted(v for v in dirs if v > want)
        if dirs and want not in dirs and gone:
            res["reopen"] = True
            res["reasons"].append("证据版本 " + want + " 不在装，本机是 "
                                  + ", ".join(gone) + " —— 版本变了")
            return res
        newer = sorted(v for v in dirs if v > want)
        if newer:
            res["warnings"].append("证据版本（" + want + "）仍在装，但本机还有更新的 "
                                   + ", ".join(newer)
                                   + " —— 建议在**默认版本**上复验（不必立刻重开）")
        return res
    # 证据只记了主版本：细版本差异（2025.2 → 2025.3）**判不出来**，如实写限制
    if any("." in v for v in dirs):
        res["warnings"].append(
            "证据只记了主版本（" + want + "），而安装目录更细（"
            + ", ".join(dirs) + "）—— 同主版本内的升级（如 2025.2 → 2025.3）"
            "**判不出来**；重开普查时请在 evidence_run 里记细版本（host_install）")
    return res


def decide(evidence: dict, catalog_path: Path = CATALOG,
           installed: list | None = None,
           workspace_projects: list | None = None,
           floor: int = FLOOR_CLASSES,
           now: float | None = None,
           installed_dirs: list | None = None) -> dict:
    """三份客观事实 → 是否建议重开（纯函数，可单测）。"""
    run = (evidence or {}).get("evidence_run") or {}
    cov = (evidence or {}).get("coverage") or {}
    reasons: list = []
    notes: list = []

    # ① 宿主版本
    # **合成数据要自洽**（R56 实测）：显式给了 installed（测试/外部注入）时，安装目录
    # 默认取空 —— 否则会混进本机真实目录，把"版本变了"判成"没变"
    if installed is None:
        installed = host_versions()
        dirs = installed_dirs if installed_dirs is not None \
            else installed_versions()
    else:
        dirs = installed_dirs if installed_dirs is not None else []
    verdict = version_verdict(str(run.get("progid") or ""), installed, dirs)
    reasons += verdict["reasons"]
    notes += verdict["warnings"]

    # ② **成员集**变了（不是 mtime —— 每轮收口都会用同一份证据重生成目录，
    #    那是正常流程；真正该重开的是"目录与证据对不上"）
    when = run.get("when") or ""
    try:
        cat = json.loads(catalog_path.read_text(encoding="utf-8"))
        n_cls = len(cat.get("classes") or {})
        n_mem = sum(len(i.get("methods") or {}) + len(i.get("properties") or {})
                    for i in (cat.get("classes") or {}).values())
        if n_cls != int(cov.get("classes_total") or 0) or \
                n_mem != int(cov.get("members_total") or 0):
            reasons.append("目录成员集与证据对不上：目录 " + str(n_cls) + " 类/"
                           + str(n_mem) + " 成员，证据 "
                           + str(cov.get("classes_total")) + " 类/"
                           + str(cov.get("members_total")) + " 成员")
        elif catalog_path.stat().st_mtime > (
                time.mktime(time.strptime(when, "%Y-%m-%dT%H:%M:%S")) + 1
                if when else 0):
            notes.append("目录在普查后被重生成（提取期灌证据的正常流程），"
                         "成员集未变 → 不触发重开")
    except Exception as exc:  # noqa: BLE001
        notes.append("目录不可读或时间不可解析（" + type(exc).__name__
                     + "），跳过成员集检查")

    # ③ 覆盖率下限
    swept = int(cov.get("classes_swept") or 0)
    if swept < floor:
        reasons.append("覆盖率 " + str(swept) + " < 收口下限 " + str(floor))

    # ④ 工程集（软）
    ran = sorted(run.get("projects") or [])
    if workspace_projects:
        now_names = sorted(Path(p).name for p in workspace_projects)
        if now_names != ran:
            added = sorted(set(now_names) - set(ran))
            missing = sorted(set(ran) - set(now_names))
            notes.append("工程集变了：新增 " + str(added) + "；缺失 "
                         + str(missing) + "（软理由，不单独触发重开）")

    return {"reopen": bool(reasons), "reasons": reasons, "notes": notes,
            "checked": {"installed_progids": installed,
                        "installed_versions": verdict["installed_versions"],
                        "evidence_round": run.get("round"),
                        "evidence_when": when,
                        "classes_swept": swept, "floor": floor,
                        "projects_ran": ran}}


#: 盯防清单的判定元数据（每档都写清"为什么盯它"）
WATCH_KINDS = {
    "swept_suspect": "整类成员未知过半（拿错对象，整类没记）——重开时优先复查",
    "near_threshold": "验身否掉但离阈值很近（|2r−s| ≤ 1）——判据脆，重开时复验",
    "probe_limitation": "终态 probe-limitation（试过但没结论）——重开时优先试",
    "empty_object": "取不到实例（缺前置流程）——有语料后第一个该试",
    "no_member": "取到了对象但手册页 0 成员——重开时看手册是否补了成员",
}


def _action(kind: str, cls: str, cov: dict, account: dict) -> str:
    """每档的**可执行动作**（R53-2）：试哪个取法 / 看哪条证据。"""
    row = (account.get("classes") or {}).get(cls) or {}
    plans = row.get("declared_candidates") or []
    plan = plans[0] if plans else ""
    empty = (cov.get("auto_empty_targets") or {}).get(cls)
    if kind == "swept_suspect":
        detail = (cov.get("swept_suspect") or {}).get(cls) or {}
        return ("重取该类实例并用**更大的独有成员样本**重验（上次 "
                + str(detail.get("unknown")) + "/" + str(detail.get("total"))
                + " 未知）")
    if kind == "near_threshold":
        for m in (cov.get("guard_audit") or {}).get("rejection_margins") or []:
            if str(m.get("how") or "").startswith(cls + " "):
                return ("复验取法 " + str(m.get("how")) + "：样本 "
                        + str(m.get("sample")) + " 解析 " + str(m.get("resolved"))
                        + "（margin " + str(m.get("margin")) + "，差一点翻案）")
        return "复验被否的取法（近阈）"
    if kind == "empty_object":
        hint = (cov.get("empty_hints") or {}).get(cls) or "先补前置流程"
        return ("先跑：" + hint + "；再试 " + (empty or plan or "原取法"))
    if kind == "probe_limitation":
        return "试 " + (plan or "手册声明的取法") + "；看 " + str(
            row.get("evidence") or "证据") + " 里的调用错误"
    if kind == "no_member":
        return "看手册该页是否补了成员（当前 0 成员）"
    return "复查该类"


def watchlist(evidence: dict, account: dict | None = None) -> dict:
    """重开普查时**优先复查**的类（R52-3；纯函数，可单测）。"""
    cov = (evidence or {}).get("coverage") or {}
    out: dict = {}
    for cls in sorted(cov.get("swept_suspect") or {}):
        out.setdefault(cls, []).append("swept_suspect")
    for row in ((evidence or {}).get("coverage") or {}).get(
            "guard_audit", {}).get("rejection_margins") or []:
        cls = str(row.get("how") or "").split(" <- ")[0].strip()
        if cls and abs(int(row.get("margin") or 0)) <= 1:
            out.setdefault(cls, []).append("near_threshold")
    for cls in sorted(cov.get("empty_objects") or []):
        out.setdefault(cls, []).append("empty_object")
    for cls in sorted(cov.get("no_member_classes") or []):
        out.setdefault(cls, []).append("no_member")
    if account:
        for cls, row in (account.get("classes") or {}).items():
            if row.get("terminal") == "probe-limitation":
                out.setdefault(cls, []).append("probe_limitation")
    return {cls: {"kinds": sorted(set(k)),
                  "why": [WATCH_KINDS[k] for k in sorted(set(k))],
                  "actions": [_action(k, cls, cov, account or {})
                              for k in sorted(set(k))]}
            for cls, k in sorted(out.items())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="普查复验窗口检查（R51-2）")
    ap.add_argument("--avail", type=Path, default=AVAIL)
    ap.add_argument("--floor", type=int, default=FLOOR_CLASSES)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--watchlist", action="store_true",
                    help="R52-3：只输出「重开时优先复查的类」")
    args = ap.parse_args(argv)
    if not args.avail.is_file():
        print("[reopen] 缺证据：" + str(args.avail), file=sys.stderr)
        return 2
    evidence = json.loads(args.avail.read_text(encoding="utf-8"))
    projects = []
    try:
        from tools.host_member_sweep import DEFAULT_PROJECTS
        projects = list(DEFAULT_PROJECTS)
    except Exception:  # noqa: BLE001
        projects = []
    if args.watchlist:
        acct = {}
        p = ROOT / "schemas" / "unswept_account.json"
        if p.is_file():
            acct = json.loads(p.read_text(encoding="utf-8"))
        wl = watchlist(evidence, acct)
        if args.json:
            print(json.dumps(wl, ensure_ascii=False, indent=1))
        else:
            print("[watchlist] 重开普查时优先复查 " + str(len(wl)) + " 个类：")
            for cls, meta in wl.items():
                print("  · " + cls + "（" + "/".join(meta["kinds"]) + "）")
                for why in meta["why"]:
                    print("      " + why)
                for act in meta.get("actions") or []:
                    print("      → " + act)
        return 0
    res = decide(evidence, floor=args.floor, workspace_projects=projects)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        run = res["checked"]
        print("[reopen] 证据轮次 " + str(run["evidence_round"]) + "（"
              + str(run["evidence_when"]) + "）、覆盖率 "
              + str(run["classes_swept"]) + "/下限 " + str(run["floor"]))
        for r in res["reasons"]:
            print("  ★ 硬理由：" + r)
        for n in res["notes"]:
            print("  · 软信息：" + n)
        print("[reopen] 结论：" + ("**建议重开普查**" if res["reopen"]
                                  else "无需重开（收口判据仍成立）"))
    return 1 if res["reopen"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
