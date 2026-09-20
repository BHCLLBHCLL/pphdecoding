#!/usr/bin/env python3
"""scFLOWpre VBScript 桥。

scFLOWpre 通过 VBScript 暴露自动化接口（File → Execute VBScript / 录制
history.vbs）。本模块提供：

- 纯函数：构建/写出/读取 VBScript 文件；
- ``VbsBridge``：定位 scFLOWpre、构造启动命令，并提供三种执行后端：

  - ``manual``：写出脚本并提示人工执行（最可靠，零侵入）；
  - ``cli``：**实测不存在，弃用**——2026-08-17 实机确认 scFLOWpre_Bx64net.exe
    没有 ``-vbs`` 命令行开关：两种形式（``-vbs <path>`` 与 ``-vbs=<path>``）
    均正常启动 GUI 且**忽略脚本**（标记脚本 90s/60s 无输出），选择 cli 后端
    返回显式 unsupported；
  - ``gui``：pywinauto 驱动菜单 File → Execute VBScript（对话框布局可注入 hook）。
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import scflowpre_probe
from automation.history_vbs import decode_vbs

DEFAULT_SCRIPT_ARG = "-vbs"

#: VBS 里「`Obj.Method "字面量"`」形态的调用点（R34-2 取值校验用）。
#: 要求字面量**紧跟**方法名（可带左括号）——这样它必然是第一个实参；
#: 行内更靠后的字符串（路径、说明）不参与校验。
VBS_CALL_LITERAL = re.compile(r'\.([A-Za-z_]\w*)\s*\(?\s*"([^"]{0,60})"')
#: 只校验标识符样字面量：路径/文件名/中文说明一律跳过（避免误报）
IDENT_LITERAL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: 最近一次生成的取值告警（三态口径：无词表 = None 不算告警）
value_warnings: list = []


def clear_value_warnings() -> None:
    del value_warnings[:]


def _method_value_set(method: str) -> set:
    """目录里某方法**第一个参数**的取值集（跨类取并集；找不到返回空集）。

    VBS 动作行不带类信息，只能按方法名查 —— 故取并集（宁可少报不可误报）。
    """
    try:
        from automation import scflowpre_api as api
        from automation.scflowpre_api import api_arg_values
        cat = api.load_catalog()
    except Exception:  # noqa: BLE001
        return set()
    out: set = set()
    for cls, info in cat["classes"].items():
        for kind in ("methods", "properties"):
            if not (info.get(kind) or {}).get(method):
                continue
            # 走 typed 桥的同一解析：setter 无词表时按 note_ref 回退到 getter
            for v in api_arg_values(cls, method):
                out.add(v["value"])
    return out


#: VBS 里「`Obj.Method`」的方法名（R37-2 名字纠错用）
VBS_CALL_NAME = re.compile(r"\.([A-Za-z_]\w*)")


def name_corrections() -> dict:
    """目录键 → 宿主真正接受的名字（仅收"改了才调得通"的那些）。

    来自 `schemas/name_verdicts.json`（R35/R36 实机 `GetIDsOfNames` 裁定）：
    实测 4 处「只有签名名能解析」—— 生成器若按目录键发出去**必然失败**。
    """
    out: dict = {}
    # 首选**目录**里的 `dispatch_name`（R38-3 起提取期灌入：只读目录的消费者也能纠名）
    try:
        from automation.scflowpre_api import load_catalog
        for info in load_catalog()["classes"].values():
            for key, entry in (info.get("methods") or {}).items():
                resolved = entry.get("dispatch_name")
                if resolved and resolved != key:
                    out[key] = resolved
    except Exception:  # noqa: BLE001
        pass
    if out:
        return out
    # 回退：裁定表
    try:
        from automation.scflowpre_api import load_name_verdicts
        table = load_name_verdicts()
    except Exception:  # noqa: BLE001
        return {}
    for members in table.values():
        for key, resolved in members.items():
            if resolved != key:
                out[key] = resolved
    return out


_ABSENT_CACHE: Optional[set] = None


def host_absent_methods() -> set:
    """宿主**未实现**且**无歧义**的成员名（R47-3）。

    无歧义 = **所有**声明它的类都标了 `host_absent`：同名成员可能只在部分类未实现
    （`ImportCSV` 在 FaceRegion/NumericalRegion 是好的），按名字一律拦会误杀。
    证据：`schemas/vb_api_catalog.json` 的 `host_absent`（R42 起由 GetIDsOfNames
    普查入册）。
    """
    global _ABSENT_CACHE
    if _ABSENT_CACHE is not None:
        return _ABSENT_CACHE
    flags: dict = {}
    try:
        from automation.scflowpre_api import load_catalog
        for info in (load_catalog().get("classes") or {}).values():
            for kind in ("methods", "properties"):
                for name, entry in (info.get(kind) or {}).items():
                    flags.setdefault(name, []).append(
                        bool(entry.get("host_absent")))
    except Exception:  # noqa: BLE001
        flags = {}
    _ABSENT_CACHE = {n for n, f in flags.items() if f and all(f)}
    return _ABSENT_CACHE


def validate_actions(actions: list) -> list:
    """扫动作行里的字符串实参，按目录词表三态校验（返回告警列表）。

    与 typed 桥（`scflowpre_api.ComObject._check_values`）同一口径：手册是**子集**
    （宿主还认 `octree` 之类未列取值），故这里只**产出告警**，是否拦下由调用方
    （`build_vbs(strict_values=True)`）决定。
    """
    out = []
    cache: dict = {}
    fixes = name_corrections()
    absent = host_absent_methods()      # R47-3：宿主未实现（无歧义）的成员
    for action in actions:
        # 名字纠错（R37-2）：目录键调不通的对，直接在生成期点名
        for method in VBS_CALL_NAME.findall(str(action)):
            fixed = fixes.get(method)
            if fixed:
                out.append(method + " 在宿主上不存在（手册标题拼写），应改用 "
                           + fixed)
            elif method in absent:
                # R47-3：**前置**拦下（生成期，早于任何宿主会话）——
                # 以前要等 COM 抛 com_error 才知道调不通
                out.append(method + " 宿主未实现（GetIDsOfNames → "
                           "DISP_E_UNKNOWNNAME；目录 schemas/vb_api_catalog.json "
                           "已标 host_absent），调用必然失败")
        for method, literal in VBS_CALL_LITERAL.findall(str(action)):
            if not IDENT_LITERAL.match(literal):
                continue
            if method not in cache:
                cache[method] = _method_value_set(method)
            values = cache[method]
            if values and literal not in values:
                out.append(method + " 的实参 " + repr(literal)
                           + " 不在手册词表内（" + str(len(values))
                           + " 项；目录 schemas/vb_api_catalog.json）")
    return out


def build_vbs(actions: list[str], title: str = "scFLOWpre automation",
              *, strict_values: bool = False) -> str:
    """把动作行组装成 VBScript 文本（CRLF）。

    `strict_values=True` 时，字符串实参越出目录词表即抛 `ApiValueError`
    （**在生成阶段**，早于任何宿主会话）；默认只记 `value_warnings`。
    """
    warnings = validate_actions(actions)
    if warnings:
        if strict_values:
            from automation.scflowpre_api import ApiValueError
            raise ApiValueError("; ".join(warnings))
        value_warnings.extend(warnings)
    lines = [
        f"' {title}",
        "' generated by pphdecoding automation/vbs_bridge.py",
        "",
    ]
    for action in actions:
        lines.append(str(action).rstrip())
    return "\r\n".join(lines) + "\r\n"


def write_vbs_file(actions: list[str], path: str | Path,
                   title: str = "scFLOWpre automation") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # scFLOWpre 的 VBScript 引擎要求 UTF-16LE + BOM（与 history.vbs 一致）。
    # 用 write_bytes 避免文本模式把 \r\n 再转成 \r\r\n。
    path.write_bytes(build_vbs(actions, title).encode("utf-16"))
    return path


def read_vbs_lines(path: str | Path) -> list[str]:
    """读取 VBS 文件，去掉注释/空行，并拼接续行（行尾 ``_``）。"""
    text = decode_vbs(Path(path).read_bytes())
    logical: list[str] = []
    pending = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("'") or line.lower().startswith("rem "):
            continue
        if pending:
            line = pending + " " + line
            pending = ""
        if line.rstrip()[-2:] == " _":
            pending = line.rstrip()[:-2].rstrip()
            continue
        logical.append(line)
    if pending:
        logical.append(pending)
    return logical


@dataclass
class VbsBridge:
    """定位 scFLOWpre 并执行 VBScript 的桥。"""

    install_dir: Optional[str] = None
    exe_name: str = "scFLOWpre_Bx64net.exe"
    script_arg: str = DEFAULT_SCRIPT_ARG
    timeout: float = 120.0
    _exe_cache: Optional[Path] = field(default=None, repr=False)

    def exe_path(self) -> Optional[Path]:
        if self._exe_cache is not None:
            return self._exe_cache
        root = Path(self.install_dir) if self.install_dir else None
        if root is None:
            root = scflowpre_probe.find_install()
        if root is None:
            return None
        exe = root / scflowpre_probe.PROGRAMS_SUBDIR / self.exe_name
        self._exe_cache = exe if exe.is_file() else None
        return self._exe_cache

    def launch_command(self, vbs_path: str | Path,
                       script_args: Optional[list[str]] = None) -> list[str]:
        """构造启动命令；脚本参数名可配置（默认 ``-vbs``）。"""
        exe = self.exe_path()
        if exe is None:
            raise FileNotFoundError("scFLOWpre 未安装或未找到")
        args = list(script_args) if script_args is not None \
            else [self.script_arg, str(vbs_path)]
        return [str(exe), *args]

    def execute(self, vbs_path: str | Path, *, backend: str = "manual",
                script_args: Optional[list[str]] = None,
                gui_hooks: Optional[dict] = None) -> dict:
        """执行 VBScript；backend ∈ {manual, cli, gui}。"""
        vbs_path = Path(vbs_path)
        if not vbs_path.is_file():
            raise FileNotFoundError(vbs_path)
        if backend == "cli":
            # 2026-08-17 实机确认：scFLOWpre 无 -vbs 命令行开关——两种形式
            # （-vbs <path> / -vbs=<path>）均正常启动 GUI 并忽略脚本（标记
            # 脚本 90s/60s 无输出，进程被终止）。继续静默尝试只会白白拉起 GUI。
            return {"backend": "cli", "ok": False,
                    "verified_absent": True,
                    "error": "scFLOWpre -vbs CLI 参数实测不存在，cli 后端不可用；"
                             "请用 com（ExecuteVBSWithFile）或 gui/manual"
                             "（File → Execute VBScript）后端"}
        if backend == "gui":
            return self._execute_gui(vbs_path, hooks=gui_hooks or {})
        return {"backend": "manual", "script": str(vbs_path),
                "hint": "请在 scFLOWpre 中执行 File → Execute VBScript，"
                        "选择该脚本文件"}

    def _execute_gui(self, vbs_path: Path, hooks: dict) -> dict:
        """pywinauto 驱动；菜单文本与对话框填充均可注入。"""
        exe = self.exe_path()
        if exe is None:
            raise FileNotFoundError("scFLOWpre 未安装或未找到")
        try:
            import pywinauto
            from pywinauto.application import Application
        except ImportError as exc:  # pragma: no cover - 依赖可选
            raise RuntimeError("pywinauto 未安装，无法使用 gui 后端") from exc

        app = Application(backend="uia").start(str(exe))
        win = app.window(title_re=".*scFLOWpre.*", timeout=self.timeout)
        win.wait("visible", timeout=self.timeout)
        menu = hooks.get("menu") or {"file": "File",
                                     "execute_vbs": "Execute VBScript"}
        win.menu_select(f"{menu['file']}->{menu['execute_vbs']}")
        dlg = app.window(title_re=hooks.get("dlg_title_re", ".*VBS.*"),
                         timeout=self.timeout)
        dlg.wait("visible", timeout=self.timeout)
        fill = hooks.get("fill_dialog")
        if fill is None:
            try:
                dlg.child_window(class_name="Edit").set_edit_text(str(vbs_path))
                ok = hooks.get("ok_button", "OK")
                dlg.child_window(title=ok).click()
            except Exception:  # noqa: BLE001
                return {"backend": "gui", "status": "dialog_fill_failed",
                        "script": str(vbs_path)}
        else:
            fill(dlg, vbs_path)
        return {"backend": "gui", "status": "submitted",
                "script": str(vbs_path)}


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="scFLOWpre VBScript 桥")
    ap.add_argument("--actions", nargs="*", default=[],
                    help="VBS 动作行（未提供则读 --input）")
    ap.add_argument("--input", help="已有 .vbs 文件（读取动作行）")
    ap.add_argument("--output", required=True, help="输出 .vbs 路径")
    args = ap.parse_args(argv)
    if args.input:
        actions = read_vbs_lines(args.input)
    else:
        actions = args.actions
    write_vbs_file(actions, args.output)
    print(f"written {args.output} ({len(actions)} actions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
