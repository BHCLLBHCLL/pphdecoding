#!/usr/bin/env python3
"""R55-1：把收口结论写成**一页**可读总结（`docs/HOST_API_COVERAGE.md`）。

结论散在 ROUNDS 十条记录与审计九节里，排期/复验时不好找。本工具从**证据**
生成一页：口径（怎么判的）→ 数字（覆盖率与桶）→ 未实现成员 → 终态分布 →
缺语料收益与成本 → 复验窗口 → 适用边界（**不许外推**的地方）。

数字全部取自 `schemas/`（不手写），测试逐项对账；口径与边界是**写死的判断**，
刻意留在文档里以便被审阅和反驳。

用法::

    python tools/host_coverage_doc.py            # 生成 docs/HOST_API_COVERAGE.md
    python tools/host_coverage_doc.py --check     # 只对账，不写文件（CI/测试用）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console_utf8  # noqa: E402

console_utf8.enable()

AVAIL = ROOT / "schemas" / "host_member_availability.json"
UNSWEPT = ROOT / "schemas" / "unswept_account.json"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
OUT = ROOT / "docs" / "HOST_API_COVERAGE.md"

#: 口径（怎么判的）—— 写死在这里，便于审阅
METHOD = [
    "**成员可用性**：`IDispatch::GetIDsOfNames` 逐个解析手册成员名，只解析不调用"
    "（零副作用）；`DISP_E_UNKNOWNNAME` 即宿主未实现。",
    "**对象取法**：三层配方（手册 `instance` → 目录声明在已持有宿主上的取用成员 → "
    "命名片段），实参按手册词表与阶梯给；**验身**（该类独有成员解析率 ≥ 半数）"
    "通过才收。",
    "**假证据闸门**：整类未知过半不记（`swept_suspect`）；派发名不通时回退成员键名；"
    "标量返回不算对象。",
]

#: 适用边界（**不许外推**的地方）—— 同样写死，便于反驳
BOUNDARY = [
    "只覆盖本机 Cradle 2025.2 + `scFLOWpre_Bx64net.Application.2025`；换版本必须重跑。",
    "只覆盖**6 个算例**（box.pph + 5 个 Exercise）能提供的对象；语料缺失的类一律"
    "记 `needs-corpus`，**不代表宿主没有**该功能。",
    "`host_absent` 只说明「这个名字在宿主上解析不到」，**不**说明「功能不存在」"
    "（手册拼写错、别名、宿主另有入口都可能）。",
    "普查结论**不替代**实机功能验收：单个功能的验收仍以端到端跑通为准。",
]


def build(avail: dict, unswept: dict, catalog: dict) -> str:
    """生成文档文本（纯函数，可单测；数字只来自入参）。"""
    cov = avail.get("coverage") or {}
    run = avail.get("evidence_run") or {}
    lines = [
        "# 宿主 VB API 覆盖与能力边界（收口一页）",
        "",
        "> 自动生成：`python tools/host_coverage_doc.py`（数字取自 `schemas/`；"
        "口径与边界写死在本工具里，便于审阅与反驳）。",
        "> 详细轮次记录见 `docs/ROUNDS.md`（R45–R55），审计细节见 "
        "`docs/CODE_STATE_AUDIT_20260906.md`（§59–§67）。",
        "",
        "## 1. 结论（一行）",
        "",
        "**" + str(cov.get("classes_swept")) + "/" + str(cov.get("classes_total"))
        + " 类**（" + str(cov.get("members_swept")) + "/"
        + str(cov.get("members_total")) + " 成员）已用 `GetIDsOfNames` 逐名普查；"
        "宿主未实现 **" + str(_absent_entries(catalog)) + " 条**；"
        "取不到实例的类 **" + str(len(cov.get("empty_objects") or [])) + " 个**；"
        "剩余 " + str(len(cov.get("unswept_classes") or [])) + " 个**全部有终态**。",
        "",
        "证据轮次：" + str(run.get("round")) + "（" + str(run.get("when"))
        + "），日志 `" + str(run.get("log") or "-") + "`，工程集 "
        + ", ".join(run.get("projects") or []) + "。",
        "",
        "## 2. 口径（怎么判的）",
        "",
    ]
    lines += ["- " + m for m in METHOD]
    lines += ["", "## 3. 桶分布（互斥且守恒）", "",
              "| 桶 | 数量 |", "|---|---|",
              "| 已普查 | **" + str(cov.get("classes_swept")) + "** |",
              "| 取不到实例（缺前置流程） | "
              + str(len(cov.get("empty_objects") or [])) + " |",
              "| 取到但手册无成员 | "
              + str(len(cov.get("no_member_classes") or [])) + " |",
              "| 从未尝试 | " + str(len(cov.get("unswept_classes") or []))
              + " |",
              "| **合计** | **" + str(cov.get("classes_total")) + "** |", ""]
    lines += ["## 4. 未实现成员（" + str(_absent_entries(catalog)) + " 条 / "
              + str(len(_absent_by_class(catalog))) + " 类）", "",
              "> Python 侧不会为这些条目造包装；调用前会被拦下（typed 直调与 VBS "
              "生成共用同一判据），并给出下一步。", ""]
    for cls, members in sorted(_absent_by_class(catalog).items()):
        lines.append("- `" + cls + "` — " + " / ".join(members))
    lines += ["", "## 5. 未普查类终态分布", "",
              "| 终态 | 数量 |", "|---|---|"]
    counts = (unswept.get("counts") or {})
    for k in ("needs-corpus", "host-interface-absent", "no-creation-path",
              "call-rejected", "foreign-app", "probe-limitation"):
        lines.append("| `" + k + "` | " + str(counts.get(k, 0)) + " |")
    lines += ["", "## 6. 缺语料：补上能多覆盖几类、要什么算例", "",
              "| 组 | 类数 | 预计可覆盖 | 成本档 | 要什么算例 |", "|---|---|---|---|---|"]
    for g, info in sorted((unswept.get("needs_corpus_plan") or {}).items()):
        lines.append("| " + g + " | " + str(len(info.get("classes") or [])) + " | "
                     + str(info.get("expected_gain")) + " | "
                     + str(info.get("tier")) + " | " + str(info.get("what")) + " |")
    total = sum(int(v.get("expected_gain") or 0)
                for v in (unswept.get("needs_corpus_plan") or {}).values())
    lines += ["", "合计预计可覆盖 **" + str(total) + " 类**（无取法的类单列在 "
              "`no_path`，见 `schemas/unswept_account.json`）。", ""]
    lines += ["## 7. 复验窗口（何时重开）", "",
              "一条命令：`python tools/sweep_reopen_check.py`（建议重开 → exit 1）。",
              "硬理由：宿主版本变化 / 目录成员集与证据对不上 / 覆盖率低于收口下限"
              "（155）。软信息：工程集变化、目录被重生成。",
              "重开时先复查谁：`python tools/sweep_reopen_check.py --watchlist`"
              "（suspect / 近阈否 / 无结论 / 空对象 / 无成员五档，各有可执行动作）。", ""]
    lines += ["## 8. 适用边界（不许外推）", ""]
    lines += ["- " + b for b in BOUNDARY]
    lines += ["", "---", "",
              "复验入口汇总：`tools/host_member_sweep.py`（重跑普查）、"
              "`tools/unswept_account.py`（终态归因）、"
              "`tools/sweep_reopen_check.py`（复验窗口/盯防）、"
              "`tools/api_contract_check.py`（契约门 10 项 + `--self-test`）。", ""]
    return "\n".join(lines)


def _absent_by_class(catalog: dict) -> dict:
    out: dict = {}
    for cls, info in (catalog.get("classes") or {}).items():
        names = [m for kind in ("methods", "properties")
                 for m, e in (info.get(kind) or {}).items() if e.get("host_absent")]
        if names:
            out[cls] = sorted(names)
    return out


def _absent_entries(catalog: dict) -> int:
    return sum(len(v) for v in _absent_by_class(catalog).values())


def generate() -> str:
    avail = json.loads(AVAIL.read_text(encoding="utf-8"))
    unswept = json.loads(UNSWEPT.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    return build(avail, unswept, catalog)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="收口一页（R55-1）")
    ap.add_argument("--check", action="store_true",
                    help="只对账：现有文档是否与证据一致（不写文件）")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    text = generate()
    if args.check:
        if not args.out.is_file():
            print("[coverage-doc] 缺文档：" + str(args.out), file=sys.stderr)
            return 1
        same = args.out.read_text(encoding="utf-8") == text
        print("[coverage-doc] " + ("与证据一致" if same else "**与证据不一致**"))
        if not same:
            cur = args.out.read_text(encoding="utf-8").splitlines()
            new = text.splitlines()
            diff = [a for a, b in zip(cur, new) if a != b][:3]
            print("   差异示例：" + str(diff))
            return 1
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print("[coverage-doc] 已写 " + str(args.out) + "（"
          + str(len(text.splitlines())) + " 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
