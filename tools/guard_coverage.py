#!/usr/bin/env python3
"""R40-3：**写路径 × 守卫覆盖**盘点。

本仓有四类"把设置写到宿主"的路径，守卫强度不同，此前没有一张总表：

| 路径 | 入口 | 现有守卫 |
|---|---|---|
| typed 桥 | `scflowpre_api.ComObject.call` | 取值三态 + 参数个数（`strict_values` 可抛） |
| VBS 生成 | `vbs_bridge.build_vbs` | 取值三态 + 方法名纠错（裁定表） |
| 面板写 xenv | `nav_panels` → `pphxml.set_xenv_value` | 键名来自实测账本；枚举走实测编码表白名单 |
| 工具直写 | `tools/*.py` 里的 `set_xenv_value(` | **逐个声明**（本工具负责把未声明者列出来） |

用法::

    python tools/guard_coverage.py --json out.json
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console_utf8  # noqa: E402

console_utf8.enable()

from automation import scflowpre_api as api  # noqa: E402
from automation import vbs_bridge as vb  # noqa: E402

#: 直写 xenv 的工具 → 为什么可以接受（**必须显式声明**）
DECLARED_DIRECT = {
    "xenv_host_write_check.py": "值来自 WRITES/WRITES_MORE 声明表，写后由宿主 getter 回读",
    "xenv_key_probe.py": "探针：写的是候选 setter 取值，键名靠 diff 反推（不落产品）",
    "panel_persist_check.py": "写的是面板 apply() 的产物（面板侧已受键名/白名单约束）",
}


def _src(fn) -> str:
    try:
        return inspect.getsource(fn)
    except Exception:  # noqa: BLE001
        return ""


def check_typed_bridge() -> dict:
    src = _src(api.ComObject.call)
    has_check = "_check_values" in src
    has_values = "value_warnings" in _src(api.ComObject._check_values)
    has_arity = "signature_arity" in _src(api.ComObject._check_values)
    return {"entry": "scflowpre_api.ComObject.call", "guarded": has_check,
            "value_tristate": has_values, "arity": has_arity,
            "ok": has_check and has_values and has_arity}


def check_vbs() -> dict:
    src = _src(vb.build_vbs)
    has_val = "validate_actions" in src
    has_corr = "name_corrections" in _src(vb.validate_actions)
    return {"entry": "vbs_bridge.build_vbs", "guarded": has_val,
            "name_correction": has_corr, "ok": has_val and has_corr}


def check_panel() -> dict:
    nav = (ROOT / "nav_panels.py").read_text(encoding="utf-8")
    uses_setter = "pphxml.set_xenv_value(" in nav
    enum_whitelisted = "voxel_oct_refine_code(" in nav
    keys_measured = (ROOT / "schemas" / "host_keys.json").is_file()
    return {"entry": "nav_panels → pphxml.set_xenv_value",
            "writes_via_helper": uses_setter,
            "enum_whitelisted": enum_whitelisted,
            "measured_key_ledger": keys_measured,
            "ok": uses_setter and enum_whitelisted and keys_measured}


def _calls_set_xenv(path: Path) -> bool:
    """**AST** 判定：只认真的函数调用。

    用文本匹配会把文档字符串里提到的 `set_xenv_value(` 也算进来
    （本工具第一版就把自己列成了"未声明的直写者"——假阳性）。
    """
    import ast
    import warnings
    src = path.read_text(encoding="utf-8", errors="replace")
    with warnings.catch_warnings():
        # 仓里有旧文件带无效转义（\*），ast.parse 会为它们发 SyntaxWarning；
        # 那是**别人的**既有问题，不该借我的扫描器污染输出
        warnings.simplefilter("ignore", SyntaxWarning)
        try:
            tree = ast.parse(src)
        except SyntaxError:
            return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if name == "set_xenv_value":
                return True
    return False


def direct_writers() -> tuple:
    hits = [p.name for p in sorted(ROOT.glob("tools/*.py"))
            if _calls_set_xenv(p)]
    undeclared = [h for h in hits if h not in DECLARED_DIRECT]
    return hits, undeclared


def report() -> dict:
    typed = check_typed_bridge()
    vbs = check_vbs()
    panel = check_panel()
    hits, undeclared = direct_writers()
    return {"paths": [typed, vbs, panel],
            "direct_writers": hits, "undeclared_direct": undeclared,
            "ok": all(p["ok"] for p in (typed, vbs, panel)) and not undeclared}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="写路径 × 守卫覆盖盘点")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)
    data = report()
    for p in data["paths"]:
        mark = "PASS" if p["ok"] else "GAP "
        print("  " + mark + "  " + p["entry"] + "  "
              + json.dumps({k: v for k, v in p.items()
                            if k not in ("ok", "entry")}, ensure_ascii=False))
    print("  直写 xenv 的工具: " + json.dumps(data["direct_writers"]))
    print("  未声明: " + json.dumps(data["undeclared_direct"]))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    print("SUMMARY: " + json.dumps({"passed": bool(data["ok"])}))
    return 0 if data["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
