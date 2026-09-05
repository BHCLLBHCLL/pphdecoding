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
     "**I7 实测升级（2026-09-05，DEV_PLAN §20.11 / gap §10.19）**："
     "全机再扫推翻 G3「0 真样本」前提——`starcat5` 教程数据 15 个真 "
     "CATIA V5 文件（魔数 `V5_CFV2`，10 CATPart + 5 CATProduct）在位；"
     "宿主读链 e2e 绿（`OpenCadFile` 真样本 → SNode \"Part\" 落地 + "
     "全步 err=0，与 P12-D STEP 同型；`ImportCADAsFacet` 对 CATPart 与 "
     "XT 对照同 retval=False——非 CATIA 特异拒绝）。**V5 导入边界解除**；"
     "余边界：V4/V6 样本仍全机缺失；原生存写向（CATIA V5 / SAT / IGES）"
     "为许可门控的 CADthru 导出面，非域 4 导入缺口。Datakit 转换器"
     "许可特性矩阵（二进制串级）：9 家 CAD 读向，唯 CATIA V5 带 "
     "R/RW 双变体。"),
    ("Actran Acoustic（域 3 菜单 / 域 8 链）",
     "**产品边界**：typed 接线链绿（`CreateActranFiles` e2e err=0）但"
     "业务 retval=False——Acoustic Session 前置在本机无样本可构造；"
     "菜单已接线，前置具备即可复验（P12-F §10.8 如实记录）。"),
    ("Restore Closed Volume Data…（域 10）",
     "**产品边界**：仅 patch 导入 + Store and Open 再导入场景可用"
     "（P4-4 评估沿用；P12-I I3 实测升级：帮助页前置原文钉死 + 存储腿"
     "持久化成立 `meshinggroup1_restore_cvol.his` + 再导入腿成立；恢复"
     "腿受 MDL Wizard 重放前置阻塞——patch 换件重置 `<mdl>` 块致 "
     "`GetMDL` Nothing，重建须 bam 级向导重放，受遗留③-e 宿主能力"
     "时变约束。前置不可构造证据入册 DEV_PLAN §20.7，遗留⑤待复验）。"),
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
