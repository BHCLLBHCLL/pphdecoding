#!/usr/bin/env python3
"""P12-H4：域 8 条件注册表 165/165 全覆盖对账（三类归属收束）。

三类归属（DEV_PLAN §19.2 H4 验收口径）：

  exact_key  精确键 — main.xml 有真实落点（registry_key 90 + member_locus 2）
  alias      别名   — create 落盘别名到已注册键类（CondBoundaryHumidity→CondHumidity）
  boundary   边界   — 无键但有声明归属（wizard_session_state 71 + poison_isolated 1）

证据输入（全部在册，逐一交叉核对，不新增实测）：

  schemas/cond_types.json        宇宙 165 + aliases + H3 dispositions
  schemas/merged.json            161 官方案例库实样（typed 落点计数）
  p12c_registry_report.json      C 轮 75 缺口五分类 + 90 键口径
  p12h_wizard_report.json        H2 27 族 batch 裁决（25 session_state /
                                 1 keys_projected / 1 not_run）
  p12h_special6_report.json      H3 特殊 6+1 处置

输出：

  p12h_registry_report.json      165/165 对账报告（unclassified=0）
  schemas/cond_types.json        dispositions 全量入册（version 递增；
                                 Thermoregulation 族级注记保留）

用法：python tools/_p12h_reconcile.py [--dry-run]
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

COND_TYPES = ROOT / "schemas" / "cond_types.json"
MERGED = ROOT / "schemas" / "merged.json"
P12C_REPORT = ROOT / "p12c_registry_report.json"
P12H_WIZARD_REPORT = ROOT / "p12h_wizard_report.json"
P12H_SPECIAL6_REPORT = ROOT / "p12h_special6_report.json"
OUT_REPORT = ROOT / "p12h_registry_report.json"

#: H4 三类桶（验收口径）。kind 为更细的归属形态。
BUCKET_OF_KIND = {
    "registry_key": "exact_key",
    "member_locus": "exact_key",
    "alias": "alias",
    "wizard_session_state": "boundary",
    "poison_isolated": "boundary",
}
KIND_VOCABULARY = set(BUCKET_OF_KIND)

#: H3 已定谳、H4 沿用（kind 来自 special6 报告；evidence 原文保留）。
SPECIAL6 = "p12h_special6_report.json"

#: 族级账面注记（不在 165 宇宙内；H3 并轨入册，H4 原样保留）。
FAMILY_ANNOTATIONS = ("Thermoregulation",)


def load_inputs() -> dict:
    ct = json.loads(COND_TYPES.read_text(encoding="utf-8"))
    merged = json.loads(MERGED.read_text(encoding="utf-8"))
    p12c = json.loads(P12C_REPORT.read_text(encoding="utf-8"))
    wizard = json.loads(P12H_WIZARD_REPORT.read_text(encoding="utf-8"))
    special6 = json.loads(P12H_SPECIAL6_REPORT.read_text(encoding="utf-8"))
    return {"ct": ct, "merged": merged, "p12c": p12c,
            "wizard": wizard, "special6": special6}


def missing_types(p12c: dict) -> set[str]:
    miss: set[str] = set()
    for v in p12c["missing_classification"].values():
        miss |= set(v["types"])
    return miss


def sample_counts(merged: dict) -> dict[str, int]:
    types = merged["conditions"]["types"]
    return {k: v.get("count", 0) for k, v in types.items()}


def wizard_verdicts(wizard: dict) -> dict[str, str]:
    return {k: v.get("verdict", v.get("status", "?"))
            for k, v in wizard.get("families", {}).items()}


_WIZ_EVIDENCE = (
    "H2 终审四向证据链：①无 COM 创建器（P12-C missing_classification）；"
    "②官方样本库 merged.json 全量从未出现；③Condition Wizard 24 页无 "
    "Cond* 实体创建入口（scratch/_p12h_h2_deeppage2 深页探针）；"
    "④27 族 batch 族勾选零键（p12h_wizard_report.json：25 session_state "
    "+ Electric current 仅 mesh 四成员重投影无 XML 键 + Thermoregulation "
    "深页门控）；H1 代表类 CondFreeSurface 落点钉死（scratch/_p12h_h1_*）")


def attribute(inputs: dict) -> tuple[dict[str, dict], dict[str, str]]:
    """逐类归属 → (165 dispositions, 校验失败的 problems)。"""
    ct, p12c, special6 = inputs["ct"], inputs["p12c"], inputs["special6"]
    universe = set(ct["types"])
    miss = missing_types(p12c)
    counts = sample_counts(inputs["merged"])
    s6 = special6["dispositions"]
    no_com = set(p12c["missing_classification"]["no_com_creator"]["types"])
    # H3 修正：aliased 4 → 1 alias + 2 member_locus + 2 create_returns_nothing
    alias_to_have = set(p12c["missing_classification"]
                        ["create_ok_aliased_to_haved"]["types"])

    dispositions: dict[str, dict] = {}
    problems: list[str] = []
    for name in sorted(universe):
        if name in s6:
            kind = s6[name]["kind"]
            evidence = s6[name]["evidence"]
            if kind == "create_returns_nothing":
                # H3 终审：真实签名复验仍 Nothing → 向导唯一路径族，
                # 账面归属 wizard_session_state（§19.6 处置表）。
                kind = "wizard_session_state"
                evidence = (evidence + "；H3 实测 kind="
                            "create_returns_nothing；H4 收束归属 "
                            "wizard_session_state（向导唯一路径族，与 68 "
                            "类同归属）")
            elif kind == "member_locus":
                pass  # 真实键（内联形态），桶 = exact_key
            elif kind == "alias":
                pass
            elif kind == "poison_isolated":
                pass
            else:
                problems.append(f"{name}: unexpected special6 kind {kind}")
        elif name in no_com or name == "CondCoSim":
            extra = ""
            if name == "CondCoSim":
                extra = "；C 轮 create_returns_nothing（创建器返回 Nothing）→ 向导唯一路径族"
            kind = "wizard_session_state"
            evidence = _WIZ_EVIDENCE + extra
        elif name in miss:
            problems.append(f"{name}: in missing75 but unhandled")
            kind, evidence = None, ""
        else:
            # 精确键（registry_key）：C 轮口径 = 宇宙 - 75 缺口；
            # 硬约束：官方案例库必有实样落点（C 轮 keys_source 双源）。
            kind = "registry_key"
            n = counts.get(name, 0)
            if n <= 0:
                problems.append(
                    f"{name}: registry_key but no official-sample evidence")
            evidence = (f"官方案例库实样 {n} 例（schemas/merged.json "
                        f"conditions.types）；P12-C 收割链 keys_source："
                        "301 样例 PPH 全量扫描 + 宿主 CreateCond* 收割产物 "
                        "main.xml（p12c_registry_report.json）")
        if kind is None:
            continue
        dispositions[name] = {
            "bucket": BUCKET_OF_KIND[kind],
            "kind": kind,
            "target": s6[name].get("target") if name in s6 else None,
            "evidence": evidence,
        }
    # 顺带核对：C 轮 aliased 名单全部被 H3 重归属（无遗留）
    leftover = alias_to_have & {n for n, d in dispositions.items()
                                if d["kind"] == "registry_key"}
    if leftover:
        problems.append(f"aliased_to_haved leaked to registry_key: {leftover}")
    return dispositions, problems


def check_closure(dispositions: dict[str, dict], inputs: dict) -> list[str]:
    """验收硬检查：165/165、桶划分、别名目标、member_locus 键形态。"""
    ct = inputs["ct"]
    universe = set(ct["types"])
    problems: list[str] = []
    if set(dispositions) != universe:
        problems.append("dispositions != universe: "
                        f"+{set(dispositions) - universe} "
                        f"-{universe - set(dispositions)}")
    buckets = collections.Counter(d["bucket"] for d in dispositions.values())
    if set(buckets) - set(BUCKET_OF_KIND.values()):
        problems.append(f"unknown buckets: {buckets}")
    if buckets.get("exact_key") != 92 or buckets.get("alias") != 1 \
            or buckets.get("boundary") != 72:
        problems.append(f"bucket counts off: {dict(buckets)} (want 92/1/72)")
    for name, d in dispositions.items():
        if d["kind"] not in KIND_VOCABULARY:
            problems.append(f"{name}: kind {d['kind']!r} not in vocabulary")
        if d["bucket"] != BUCKET_OF_KIND[d["kind"]]:
            problems.append(f"{name}: bucket/kind mismatch {d}")
    alias_targets = set(ct["aliases"].values())
    for name, d in dispositions.items():
        if d["kind"] == "alias":
            if d["target"] not in alias_targets:
                problems.append(f"{name}: alias target {d['target']!r} "
                                "not registered")
            elif dispositions[d["target"]]["bucket"] != "exact_key":
                problems.append(f"{name}: alias target not exact_key")
        if d["kind"] == "member_locus" \
                and not str(d["target"]).startswith("main.xml:"):
            problems.append(f"{name}: member_locus target not main.xml:")
    return problems


def build_report(dispositions: dict[str, dict], inputs: dict) -> dict:
    buckets = collections.Counter(d["bucket"] for d in dispositions.values())
    kinds = collections.Counter(d["kind"] for d in dispositions.values())
    return {
        "generated": date.today().isoformat(),
        "universe": len(inputs["ct"]["types"]),
        "universe_source": inputs["p12c"]["universe_source"],
        "bucket_rule": ("exact_key=main.xml 真实落点（registry_key/"
                        "member_locus）；alias=create 落盘别名到已注册键类；"
                        "boundary=无键但有声明归属（wizard_session_state/"
                        "poison_isolated），对齐实现见 pph_gui 面板覆盖"
                        "（DEV_PLAN §19.3-1 域 8 口径重估）"),
        "inputs": {
            "cond_types": "schemas/cond_types.json",
            "official_samples": "schemas/merged.json",
            "p12c_registry_report": "p12c_registry_report.json",
            "p12h_wizard_report": "p12h_wizard_report.json",
            "p12h_special6_report": "p12h_special6_report.json",
        },
        "wizard_batch_verdicts": wizard_verdicts(inputs["wizard"]),
        "official_sample_projects": len(inputs["merged"]["projects"]),
        "summary": {
            "exact_key": buckets.get("exact_key", 0),
            "alias": buckets.get("alias", 0),
            "boundary": buckets.get("boundary", 0),
            "unclassified": 0,
        },
        "kinds": dict(kinds),
        "family_annotations": {
            name: inputs["ct"]["dispositions"][name]
            for name in FAMILY_ANNOTATIONS
            if name in inputs["ct"]["dispositions"]},
        "dispositions": dispositions,
    }


def upsert_cond_types(report: dict, inputs: dict) -> bool:
    """dispositions 全量入册（version 递增；族级注记保留）。

    幂等：账本内容无变化时不重写、不递增 version。返回是否写入。
    """
    ct = inputs["ct"]
    merged_disp = dict(report["dispositions"])
    for name, anno in report["family_annotations"].items():
        merged_disp[name] = anno
    if ct.get("dispositions") == merged_disp:
        return False
    ct["version"] = int(ct.get("version", 0)) + 1
    ct["dispositions"] = merged_disp
    COND_TYPES.write_text(json.dumps(ct, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="只校验并打印摘要，不写任何文件")
    args = ap.parse_args(argv)

    inputs = load_inputs()
    dispositions, problems = attribute(inputs)
    problems += check_closure(dispositions, inputs)
    report = build_report(dispositions, inputs)
    print("summary:", json.dumps(report["summary"], ensure_ascii=False))
    print("kinds:", json.dumps(report["kinds"], ensure_ascii=False))
    if problems:
        for p in problems:
            print("PROBLEM:", p)
        return 1
    if args.dry_run:
        print("dry-run: no files written")
        return 0
    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    changed = upsert_cond_types(report, inputs)
    if changed:
        print(f"written: {OUT_REPORT.name} + {COND_TYPES.name} "
              f"(version {inputs['ct']['version']})")
    else:
        print(f"written: {OUT_REPORT.name}; {COND_TYPES.name} unchanged "
              f"(version {inputs['ct']['version']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
