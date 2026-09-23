#!/usr/bin/env python3
"""扫描 pph_gui._build_menus 中无 slot 的 add_act，生成 NYI 清单。

用法：
  python tools/scan_nyi_menus.py
  python tools/scan_nyi_menus.py --out docs/NYI_INVENTORY.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 能力汇总要从**产品面**取（R53-1）：脚本方式运行时仓库根不在 sys.path
sys.path.insert(0, str(ROOT))
GUI = ROOT / "pph_gui.py"
#: R45-2：宿主侧边界的两个证据源（普查结果 + 目录的 host_absent 标记）
AVAIL = ROOT / "schemas" / "host_member_availability.json"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"


def host_boundary_lines() -> list:
    """R45-2 / R53-1：宿主侧能力边界（**四段**，与产品面同源）。

    为什么进这份清单：用户看到的"功能不可用"有两种根因 —— 菜单没接线，或
    **宿主 COM 面**没有对应的东西。后者此前只在 schemas 里，这里给出可读面。

    渲染**直接调** `automation.scflowpre_api.render_capability_report()`（R52-2 的
    汇总入口）：未实现成员 / 取法不可照抄 / 取不到实例 / 缺语料分组四段一次到位，
    文档与 API、面板三面永远一致（测试逐行对账）。取不到 API 时退回"证据缺失"说明。
    """
    lines = ["## 宿主侧能力边界（R53 自动生成，四段）", "",
             "> 与 `automation.scflowpre_api.host_capability_report()` 同源"
             "（证据 `schemas/host_member_availability.json` + 目录的 "
             "`host_absent`/`recipe_unreliable` 标记 + "
             "`schemas/unswept_account.json` 的缺语料分组）。",
             "> 这一节**不是菜单缺口**，是宿主 COM 面的实测边界；"
             "复验窗口见 `tools/sweep_reopen_check.py`。", ""]
    try:
        from automation.scflowpre_api import render_capability_report
        report = render_capability_report()
    except Exception as exc:  # noqa: BLE001
        report = "（能力汇总不可用：" + type(exc).__name__ + "）"
    lines += ["```text", report, "```", ""]
    return lines
def _balanced_call(src: str, start: int) -> str:
    """从 ``add_act(`` 的 '(' 起取到配对 ')' 的完整调用文本。"""
    i = start
    assert src[i] == "("
    depth = 0
    in_str = None
    escape = False
    for j in range(i, len(src)):
        ch = src[j]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            continue
        if ch in ("'", '"'):
            in_str = ch
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return src[i: j + 1]
    return src[i:]


def _extract_nyi_from_source(src: str) -> list[tuple[str, str]]:
    """返回 [(menu_guess, label), ...]。"""
    items: list[tuple[str, str]] = []
    menu = "?"
    # 预处理：按行跟踪当前菜单名
    line_menus: list[str] = []
    cur = "?"
    for line in src.splitlines():
        if "addMenu(" in line:
            m = re.search(r'addMenu\("([^"]+)"', line)
            if m:
                cur = m.group(1)
        line_menus.append(cur)

    for m in re.finditer(r"\badd_act\s*\(", src):
        call = "add_act" + _balanced_call(src, m.end() - 1)
        # 行号 → 菜单
        line_no = src[: m.start()].count("\n")
        menu = line_menus[line_no] if line_no < len(line_menus) else "?"

        lm = re.match(
            r'add_act\(\s*\w+\s*,\s*"((?:\\.|[^"\\])*)"\s*(.*)\)$',
            call,
            re.DOTALL,
        )
        if not lm:
            continue
        label = lm.group(1).replace('\\"', '"').replace("\\\\", "\\")
        rest = lm.group(2).lstrip()
        has_slot = False
        if rest.startswith(","):
            after = rest[1:].lstrip()
            if after and not after.startswith(
                    ("key=", "checkable=", "shortcut=", "tip=", ")")):
                has_slot = True
        if has_slot:
            continue
        items.append((menu, label))
    return items


# P4-4 逐项评估结论（依据 Manuals\scFLOW\HTML\Pre_eng 帮助页，
# 2026-08-16）。key 为菜单标签，value 为处置说明。
# P12-F：Define Facet Part / Create Non-Facet/Closed Volume Part /
# Create 2D Sub-mesh Meshing Unit / Fix Marked Element Shape /
# Create Actran Files 五项已接宿主 typed 路线（automation/edit_ops.py），
# 不再出现在扫描结果中。
EVALUATIONS: dict[str, str] = {
    "Restore Closed Volume Data…":
        "**产品边界**：仅 patch 导入 + Store and Open 再导入场景可用。",
}

# Sprint H5 边界项统一入册（DEV_PLAN §19.2 H5 / gap §10.14）。
# 非菜单 NYI，而是跨域产品边界声明：随扫描清单一并再生，保证
# 手册重生成不丢账。
BOUNDARY_DECLARATIONS: list[tuple[str, str]] = [
    ("CAD 格式范围：仅 x_t / STEP（域 4 · 产品决策 2026-09-13，R1-5）",
     "**范围收敛**：本仓 CAD 导入只支持 **x_t** 与 **STEP**；CATIA V4/V5/V6、"
     "3DXML、SolidEdge、JT、Rhino、VDAFS 移出 backlog（不再排期）。依据："
     "① **许可实测**（审计 §10，license.dat + lmstat 实证）：本机授权 "
     "CADTHRUSTD、OP_CATIAV5R/RW、OP_CATIAV4、OP_IGES、OP_SAT、OP_PROE、"
     "OP_SLDWRKS、OP_UNIGRAPHICS、OP_INVENTOR，但**无** 3DXML / SolidEdge / "
     "JT / Rhino / VDAFS 的 OP_*；② CATIA V5 读特性虽已授权，转换核仍"
     "**静默零几何**（6/6 样本、容器无 snapshot 成员，§9/§15）；③ x_t 与 STEP "
     "既有宿主通道，x_t 另有**免宿主免许可**离线通道（§12–§15：pskernel 剖分 + "
     "CADthru 独立 COM 转换）。**前置钉死**：STEP 不在按格式许可门控名单内"
     "（CADthru 的 13 条 No valid license found to import 不含 STEP；DKCTCore "
     "0 处 step）；ImportCADAsFacet 只接受面片格式（STL/MDL），CAD kernel "
     "格式一律走 OpenCadFile。**复验前置**（若将来恢复 CATIA）：CADthru CATIA "
     "读特性授权，或 GUI 导入路线对照以判别 license vs COM/headless 特异。"),    ("Actran Acoustic（域 3 菜单 / 域 8 链）",
     "**产品边界**：typed 接线链绿（`CreateActranFiles` e2e err=0）但"
     "业务 retval=False——Acoustic Session 前置在本机无样本可构造；"
     "菜单已接线，前置具备即可复验（P12-F §10.8 如实记录）。"),
    ("Restore Closed Volume Data…（域 10）",
     "**J1 实测升级（2026-09-05，DEV_PLAN §21.5 / gap §10.20）**："
     "全链前三腿打通——①同几何 12 三角立方体换件秒级成立（60k 三角"
     "同几何 STL 使 ImportPatchAsCAD 在工作进程内病态空转 2/2 复现，"
     "面片规模边界实证）；②MDL Wizard 重放 **151/151 err=0 全绿**"
     "（遗留⑤向导腿解除：录制变量别名 + AF 前置 + 模型状态 1.8MB "
     "snapshot 内嵌实证）；③容器级成对注入（`.his` 成员 + main.xml "
     "`<storedclosedvolumes>` 声明——装载开关，COM 换件重置该块的"
     "精确元素落点）→ 重开 `GetStoredClosedVolumes`=1。**恢复腿产品"
     "闸门维持关闭**：重开场景 `IsClosedVolumeRestorationAvailable`"
     "=False、候选查询空数组（cand_ub=-1）、`RestoreClosedVolumes` "
     "err=0 retval=False——两独立场景复现（I3 r3 cv1b 原生存储 + "
     "J1 r7 向导重建+注入），restorable 三态=-1 如实入册。域 10 "
     "边界维持：恢复可用性闸门在 COM 面不可构造（GUI [Store and "
     "Open] 对话钮无 COM 等价物），前置具备即可复验。遗留④宿主 "
     "VBS 能力时变当日未复现（重载日午后向导段正常执行）。"),
]


def render_md(items: list[tuple[str, str]]) -> str:
    lines = [
        "# PPH Viewer NYI 菜单清单",
        "",
        "> 由 `tools/scan_nyi_menus.py` 自动生成。",
        "> 对应日志：`[…] not available in PPH viewer`（现已灰显）。",
        "",
        f"合计 **{len(items)}** 项。P4-4 逐项评估见各条附注。",
        "",
    ]
    cur = None
    for menu, label in items:
        if menu != cur:
            cur = menu
            lines.append(f"## {menu}")
            lines.append("")
        note = EVALUATIONS.get(label)
        lines.append(f"- {label}"
                     + (f" — {note}" if note else ""))
    lines += ["", "## 产品边界声明（Sprint H5 统一入册）", ""]
    for title, note in BOUNDARY_DECLARATIONS:
        lines.append(f"### {title}")
        lines.append("")
        lines.append(note)
        lines.append("")
    lines.append("")
    lines += host_boundary_lines()
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=ROOT / "docs" / "NYI_INVENTORY.md")
    args = ap.parse_args(argv)
    src = GUI.read_text(encoding="utf-8")
    items = _extract_nyi_from_source(src)
    text = render_md(items)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out} ({len(items)} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
