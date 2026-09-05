#!/usr/bin/env python3
"""扫描 pph_gui._build_menus 中无 slot 的 add_act，生成 NYI 清单。

用法：
  python tools/scan_nyi_menus.py
  python tools/scan_nyi_menus.py --out docs/NYI_INVENTORY.md
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUI = ROOT / "pph_gui.py"


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
    ("CATIA V4/V5/V6 导入（域 4）",
     "**J2 实测重注册（2026-09-05，DEV_PLAN §21.6 / gap §10.21；推翻"
     " §10.19-I7「V5 导入边界解除」）**：真样本在位（starcat5 15 件 "
     "V5_CFV2）但宿主 COM 读链对 CATPart **静默零几何**——4 格式裸宿主"
     "矩阵（J2 r3 cadmatrix）：XT（SNode alive + 1 零件 + bbox [0,0.01]）"
     "与 STEP（SNode alive + 2 零件 + 真实 bbox）几何落地 = Datakit 链"
     "在本机 COM 面活着，唯 CATPart ×2 样本零 SNode、`GetSParts` 空"
     "（早/晚两轮一致，排除异步慢导入）、bbox = ±DBL_MAX 空指纹，"
     "全程 err=0 无模态（29/29 × 4 冷启动）。I7 的 sn2__alive=True 实为 "
     "box.pph 自带 \"Part\" 节点混淆（c1_out 容器差分零 CATPart 几何）"
     "——I7 结论撤回。①MDL 产物级闭环不可达：P12-D snode 全链配方在 "
     "CATPart 上复放 err=0（137 checks）但跑在空组上（MDL/VMDL "
     "Nothing）。根因 = CATIA 特异性（同链 XT/STEP 均落地）：指向本机 "
     "CADthru CATIA V5 读特性未授权（许可矩阵唯 CATIA V5 带 R/RW 双"
     "变体 = 独立特性）或 Datakit CATIA 转换器 headless no-op；手册"
     "导入矩阵无许可注（导出才注）。**余边界**：复验前置 = CADthru "
     "CATIA 读特性授权（或 GUI 导入路线对照判别 license vs COM 特异）；"
     "V4/V6 样本全机缺失；原生存写向（CATIA V5 / SAT / IGES）为许可"
     "门控导出面，非域 4 导入缺口。`ImportCADAsFacet` 前置已钉死为"
     "输入格式 = 面片格式（STL True 落 part.mdl；XT/CATPart 干净业务"
     "拒 = 归 OpenCadFile 链，非许可门）。"),
    ("Actran Acoustic（域 3 菜单 / 域 8 链）",
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
