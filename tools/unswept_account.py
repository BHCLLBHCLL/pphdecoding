#!/usr/bin/env python3
"""R46-1：未普查类的**终态归因**（每个类都要有结论，不许留"待办"）。

普查（R45）到 146/199 后，剩下的类不是"还没轮到"，而是各有原因。本工具把它们
逐类判成四种**终态**之一，并写进 `schemas/unswept_account.json`：

| 终态 | 含义 | 判据（证据） |
|---|---|---|
| `needs-corpus` | 需要**前置对象/语料**（材料、CoSim、粒子轨迹、映射表、MDL/VMDL 几何…） | 配方要的宿主对象本会话没有；或取法试过但返回空 |
| `host-interface-absent` | 宿主**根本没有**创建/取用该类的接口 | 自然宿主上 ≥2 个候选名全部 `DISP_E_UNKNOWNNAME` |
| `foreign-app` | 属于**别的应用对象**（Kicker 启动器） | 配方宿主是 `app`/`application` |
| `probe-limitation` | 试过，但结论不确定（对象形态/参数） | 有调用错误但不是"未知名称"，且没有"返回空"证据 |

口径：**宁可写 probe-limitation，也不许编一个理由**。任何一类缺终态 → `--check` 非零退出。

用法::

    python tools/unswept_account.py --json schemas/unswept_account.json
    python tools/unswept_account.py --check
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console_utf8  # noqa: E402

console_utf8.enable()

AVAIL = ROOT / "schemas" / "host_member_availability.json"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
OUT = ROOT / "schemas" / "unswept_account.json"

#: 探针里"配方宿主变量名 → 本探针 ctx 键"的同一张表（判定配方可不可执行）
HOST_KEYS = {
    "doc": "Doc", "document": "Doc",
    "conditions": "Conditions", "conds": "Conditions",
    "meshgroup": "MeshingGroup", "mesh_group": "MeshingGroup", "mg": "MeshingGroup",
    "meshgroupsetting": "MeshingGroupSetting",
    "env": "Env", "app": "Application", "application": "Application",
    "util": "Utility", "utility": "Utility", "mdl": "MDL",
}
#: 属于别的应用对象（Kicker 启动器）的宿主变量
FOREIGN_HOSTS = {"app", "application"}
TERMINALS = ("needs-corpus", "host-interface-absent", "no-creation-path",
             "call-rejected", "foreign-app", "probe-limitation")

#: 本会话**取得到**的宿主对象（判定"配方要的对象本会话有没有"）
OBTAINABLE = ("Doc", "Conditions", "MeshingGroup", "MeshingGroupSetting",
              "Env", "Application", "Utility", "MDL")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


#: 探针证据的**规范落点**（tools/host_member_sweep.py 的默认 --evidence）。
#: 只按 mtime 取"最新"曾经取错过（把恢复出来的旧轮次文件当成最新），故规范落点优先。
CANON_EVIDENCE = ROOT / "_p12u_gate" / "host_member_sweep" / "name_verdicts.json"


def latest_evidence() -> dict:
    """最近一次探针运行留下的证据（含 auto_call_errors / auto_empty_targets）。"""
    cands = []
    if CANON_EVIDENCE.is_file():
        cands.append(CANON_EVIDENCE)
    cands += [p for p in (ROOT / "_p12u_gate").glob("r*/name_verdicts.json")]
    cands += [p for p in (ROOT / "_p12u_gate").glob("name_verdicts.json")]
    if not cands:
        return {}
    best = max(cands, key=lambda p: (p != CANON_EVIDENCE,
                                     p.stat().st_mtime))
    data = json.loads(best.read_text(encoding="utf-8"))
    data["_path"] = str(best.relative_to(ROOT))
    return data


def recipe_host(cls: str, cat: dict):
    """类级 instance 配方里的宿主变量名（没有配方 → None）。"""
    inst = ((cat["classes"].get(cls) or {}).get("instance") or "").strip()
    m = re.match(r"^Set\s+\w+\s*=\s*(\w+)\.(\w+)", inst, re.S)
    return m.group(1).lower() if m else None


def _attempts(cls: str, cat: dict, ev: dict) -> list:
    """该类的候选调用留下的错误：[{host, member, err, unknown}]（R45 证据）。"""
    probe = _load("probe_r46", ROOT / "tools" / "dispatch_name_probe.py")
    cands = set(probe._candidate_members(cls))
    short = cls[4:] if cls.startswith("Cond") else cls
    out = []
    for key, err in (ev.get("auto_call_errors") or {}).items():
        host, _, member = key.partition(".")
        if member in cands or short.lower() in member.lower():
            out.append({"host": host, "member": member, "err": str(err),
                        "unknown": ("未知名称" in str(err)
                                    or "UNKNOWNNAME" in str(err).upper())})
    kerr = (ev.get("kicker_errors") or {}).get(cls)
    if kerr:
        out.append({"host": "Kicker.Application", "member": str(kerr).split(" ")[0],
                    "err": str(kerr), "unknown": False})
    for member, err in (ev.get("call_errors") or {}).items():
        if member in cands or short.lower() in member.lower():
            out.append({"host": "Conditions", "member": member, "err": str(err),
                        "unknown": ("未知名称" in str(err)
                                    or "UNKNOWNNAME" in str(err).upper())})
    return out


def declared_candidates(cls: str, cat: dict) -> list:
    """手册**声明在可取用宿主上**的候选成员（= 手册确实给了创建/取用路径）。

    与"名字家族乱猜"必须分清：手册没给路径的类，猜不中不代表宿主没有，
    只能如实记为 `no-creation-path`。
    """
    probe = _load("probe_r46", ROOT / "tools" / "dispatch_name_probe.py")
    held = {k: k for k in OBTAINABLE}
    return [p["how"] for p in probe.auto_plans(cat, cls, held)
            if p["how"].startswith("catalog:")]


#: 缺语料分组（R51-3）：关键词 → 组名（按 reason/recipe 里的实证字样匹配）
CORPUS_GROUPS = (
    ("CoSim", ("cosim",)),
    ("粒子/DEM", ("particle", "particletracking", "dem")),
    ("混合物/燃烧", ("mixedgas", "combustion", "species", "reaction")),
    ("材料/物性", ("propdata", "propitem", "material", "propgroup", "refprop")),
    ("映射", ("mapcond", "mapforstructure", "nastran")),
    ("几何/MDL", ("snode", "mdl", "vmdl", "region", "face", "edge",
                  "vertex", "wrapping", "octree")),
    ("条件/向导", ("cond", "条件")),
)


def corpus_group(row: dict) -> str:
    """一个 `needs-corpus` 类**缺什么**（R51-3）：按证据文本归类。

    分类只看 `reason`（+配方），不猜；匹配不到就进"其他"。
    """
    # 只看"缺什么"的证据：类名 + reason 的**结论句**（冒号前的部分，冒号后是
    # 具体取法示例，会带进无关宿主类名污染匹配）+ 配方（配方里的宿主变量正是
    # "缺的那个对象"）。**不猜**：匹配不到就进"其他"。
    head = str(row.get("reason") or "").split("：")[0]
    blob = (str(row.get("class") or "") + " " + head + " "
            + str(row.get("recipe") or "")).lower()
    for name, keys in CORPUS_GROUPS:
        if any(k in blob for k in keys):
            return name
    return "其他"


def classify(cls: str, cat: dict, ev: dict) -> dict:
    """一个类的终态 + 理由 + 证据（纯函数，可单测）。"""
    info = cat["classes"].get(cls) or {}
    recipe = (info.get("instance") or "").strip()
    host = recipe_host(cls, cat)
    attempts = _attempts(cls, cat, ev)
    empty = (ev.get("auto_empty_targets") or {}).get(cls)
    declared = declared_candidates(cls, cat)
    base = {"class": cls,
            "members": len(info.get("methods") or {})
            + len(info.get("properties") or {}),
            "recipe": recipe or "（手册未给实例配方）",
            "declared_candidates": declared,
            "attempts": attempts[:6],
            "evidence": ev.get("_path")}

    # ① Kicker.* 属于**别的应用对象**（本会话是 scFLOWpre 会话）。
    #    R47 起：附着 Kicker 会话**实测**过的类，用实测结论（成功→已普查；
    #    失败→call-rejected + 宿主原话），不再笼统写"取不到"。
    kicker_err = (ev.get("kicker_errors") or {}).get(cls)
    if cls.startswith("Kicker.") or host in FOREIGN_HOSTS:
        if kicker_err:
            return {**base, "terminal": "call-rejected",
                    "reason": ("Kicker 会话已实测（Kicker.Application/"
                               "LicenseStatus 都取到了），该类的取法被宿主拒绝："
                               + str(kicker_err))}
        return {**base, "terminal": "foreign-app",
                "reason": ("Kicker 启动器（Kicker.Application）的类；本会话是 "
                           "scFLOWpre 会话，取不到该对象" +
                           ("；配方：" + recipe if recipe else ""))}
    # ② 配方要的宿主对象本会话没有（snode / obj_R / condcosim / mixedgas…）
    if host and host not in HOST_KEYS and host not in ("doc", "conditions",
                                                       "conds", "meshgroup"):
        return {**base, "terminal": "needs-corpus",
                "reason": "配方需要先有 " + host + " 对象（本会话没有）"}
    # ③ 手册声明在可取用宿主上的候选**全部**未知名称 → 宿主没有这个接口
    names = {how.split(".")[-1] for how in declared}
    nat = [a for a in attempts if a["member"] in names]
    if names and nat and all(a["unknown"] for a in nat):
        return {**base, "terminal": "host-interface-absent",
                "reason": ("手册声明了 " + str(len(names)) + " 个取法，宿主全部 "
                           "DISP_E_UNKNOWNNAME：" + ", ".join(sorted(names)[:4]))}
    # ④ 取法试过但**返回空** → 前置对象/语料不在本机工程里
    if empty:
        return {**base, "terminal": "needs-corpus",
                "reason": "取法试过、返回空（本机工程没有该对象）：" + str(empty)}
    # ⑤ 手册确有取法，但实参被拒（取值/前置不满足）—— 不是"宿主没接口"
    if names and nat:
        return {**base, "terminal": "call-rejected",
                "reason": ("手册取法调用被拒（非「未知名称」）："
                           + "; ".join(sorted({a["member"] + " → " + a["err"][:60]
                                               for a in nat})[:2]))}
    # ⑥ 手册**没有**给任何创建/取用路径
    if not names:
        return {**base, "terminal": "no-creation-path",
                "reason": ("手册未声明任何可取用的创建/取用成员；名字家族乱猜"
                           "不构成「宿主无接口」的证据")}
    # ⑦ 条件类的通用解释：条件是流程/向导产物
    if cls.startswith("Cond"):
        return {**base, "terminal": "needs-corpus",
                "reason": ("条件类的实例由条件向导/流程产生；批量 CreateCond* "
                           "未产出该类（本机语料没有这种条件）")}
    # ⑧ 其余如实记为探针侧不确定（**不许**编理由）
    return {**base, "terminal": "probe-limitation",
            "reason": ("候选取法都试过但没有结论（调用错误非「未知名称」，"
                       "也没有「返回空」证据）")}


def account(avail: dict | None = None, cat: dict | None = None,
            ev: dict | None = None) -> dict:
    avail = avail if avail is not None else json.loads(
        AVAIL.read_text(encoding="utf-8"))
    cat = cat if cat is not None else json.loads(
        CATALOG.read_text(encoding="utf-8"))
    ev = ev if ev is not None else latest_evidence()
    unswept = ((avail.get("coverage") or {}).get("unswept_classes") or [])
    rows = {cls: classify(cls, cat, ev) for cls in sorted(unswept)}
    counts = {t: sum(1 for r in rows.values() if r["terminal"] == t)
              for t in TERMINALS}
    # R51-3：把 needs-corpus 的类按"缺什么"聚合（一处可查：schema + CLI）
    groups: dict = {}
    for cls, row in rows.items():
        if row["terminal"] != "needs-corpus":
            continue
        groups.setdefault(corpus_group(row), []).append(cls)
    groups = {g: sorted(v) for g, v in sorted(groups.items())}
    # R54-2：每组"补上语料后**预计能多覆盖几类**" —— 判据是该类**有已知取法**：
    # 目录/命名片段给了候选（declared_candidates 非空），或手册给了配方（配方的宿主
    # 正是"缺的那个前置对象"，补上语料后即可执行）。两者都没有的类即便补了语料
    # 也未必取得到，单列 no_path（排期时别把它们算进收益）。
    plan: dict = {}
    for g, members in groups.items():
        with_path = [c for c in members
                     if (rows[c].get("declared_candidates")
                         or (rows[c].get("recipe") or "").startswith("Set "))]
        plan[g] = {"classes": members,
                   "expected_gain": len(with_path),
                   "no_path": sorted(set(members) - set(with_path))}
    return {"source": "tools/unswept_account.py（R46-1）",
            "note": ("未普查类的**终态**：每个类都必须有一条，理由必须来自证据"
                     "（配方宿主 / 候选调用错误 / 返回空）；口径见模块 docstring。"
                     "终态不是待办 —— 除非将来补语料，这些类不会被再排期。"),
            "evidence": ev.get("_path"),
            "counts": {"total": len(rows), **counts},
            "needs_corpus_groups": groups,
            "needs_corpus_plan": plan,
            "classes": rows}


def _render(rows: dict) -> str:
    out = []
    for cls, r in rows.items():
        out.append("%-34s %-22s %s" % (cls, r["terminal"], r["reason"][:80]))
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="未普查类终态归因（R46-1）")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--check", action="store_true",
                    help="有类缺终态/终态非法即非零退出")
    args = ap.parse_args(argv)
    data = account()
    counts = data["counts"]
    print("[unswept] 未普查 " + str(counts["total"]) + " 类："
          + " / ".join(t + " " + str(counts[t]) for t in TERMINALS))
    print(_render(data["classes"]))
    groups = data.get("needs_corpus_groups") or {}
    if groups:
        print("[unswept] needs-corpus 按缺什么分组（补上语料后预计能覆盖几类）：")
        plan = data.get("needs_corpus_plan") or {}
        for g, members in groups.items():
            est = (plan.get(g) or {}).get("expected_gain")
            print("   %-12s %2d 类 → 预计可覆盖 %s 类：%s"
                  % (g, len(members), est, ", ".join(members)))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                             encoding="utf-8")
        print("[unswept] 已写 " + str(args.json))
    bad = [c for c, r in data["classes"].items() if r["terminal"] not in TERMINALS
           or not r.get("reason")]
    if bad:
        print("[unswept] 缺终态：" + ", ".join(bad), file=sys.stderr)
    if args.check and bad:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
