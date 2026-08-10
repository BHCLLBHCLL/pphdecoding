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


def render_md(items: list[tuple[str, str]]) -> str:
    lines = [
        "# PPH Viewer NYI 菜单清单",
        "",
        "> 由 `tools/scan_nyi_menus.py` 自动生成。",
        "> 对应日志：`[…] not available in PPH viewer`（现已灰显）。",
        "",
        f"合计 **{len(items)}** 项。",
        "",
    ]
    cur = None
    for menu, label in items:
        if menu != cur:
            cur = menu
            lines.append(f"## {menu}")
            lines.append("")
        lines.append(f"- {label}")
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
