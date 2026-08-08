#!/usr/bin/env python3
"""解析 scFLOWpre 录制的 history.vbs，得到结构化动作序列。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


def decode_vbs(data: bytes) -> str:
    """按 BOM 解码 scFLOWpre 录制的 VBS（UTF-8 / UTF-16LE / UTF-16BE）。"""
    if data.startswith(b"\xff\xfe"):
        return data.decode("utf-16-le", errors="replace")
    if data.startswith(b"\xfe\xff"):
        return data.decode("utf-16-be", errors="replace")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig", errors="replace")
    try:
        return data.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _split_args(text: str) -> list[str]:
    """按逗号切分参数，尊重双引号与括号。"""
    args: list[str] = []
    cur: list[str] = []
    in_str = False
    depth = 0
    for ch in text:
        if ch == '"':
            in_str = not in_str
            cur.append(ch)
        elif ch in "([" and not in_str:
            depth += 1
            cur.append(ch)
        elif ch in ")]" and not in_str:
            depth = max(0, depth - 1)
            cur.append(ch)
        elif ch == "," and depth == 0 and not in_str:
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        args.append(tail)
    return args


def _parse_line(line: str) -> Optional[dict]:
    """把一行 VBS 解析成 ``{"command", "args"}``。"""
    text = line.strip()
    if not text or text.startswith("'") or text.lower().startswith("rem "):
        return None
    set_match = re.match(r"^Set\s+(\w+)\s*=\s*(.+)$", text, re.S)
    if set_match:
        rhs = set_match.group(2).strip()
        m = re.match(r"^([A-Za-z_][\w.]*)\s*\((.*)\)\s*$", rhs, re.S)
        if m:
            return {"command": m.group(1), "args": _split_args(m.group(2))}
        return None
    m = re.match(r"^Call\s+([A-Za-z_][\w.]*)\s*\((.*)\)\s*$", text, re.S)
    if m:
        return {"command": m.group(1), "args": _split_args(m.group(2))}
    m = re.match(r"^([A-Za-z_][\w.]*)\s*(?:\(([^)]*)\))?\s*(.*)$", text, re.S)
    if m:
        cmd = m.group(1)
        args_text = (m.group(2) or m.group(3) or "").strip()
        if args_text.startswith(","):
            args_text = args_text[1:].strip()
        args = _split_args(args_text) if args_text else []
        return {"command": cmd, "args": args}
    return None


def parse_history(text: str) -> list[dict]:
    """解析 history.vbs 文本；自动拼接续行（行尾 ``_``）。"""
    actions: list[dict] = []
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
        parsed = _parse_line(line)
        if parsed is not None:
            actions.append(parsed)
    if pending:
        parsed = _parse_line(pending)
        if parsed is not None:
            actions.append(parsed)
    return actions


def parse_history_file(path: str | Path) -> list[dict]:
    return parse_history(decode_vbs(Path(path).read_bytes()))


def actions_to_hints(actions: list[dict]) -> dict:
    """按命令名聚合，输出每个命令出现次数与前几个参数样本。"""
    groups: dict[str, dict] = {}
    for action in actions:
        cmd = action["command"]
        entry = groups.setdefault(cmd, {"count": 0, "arg_samples": []})
        entry["count"] += 1
        if len(entry["arg_samples"]) < 5 and action["args"]:
            entry["arg_samples"].append(action["args"][:4])
    return groups


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    import json
    import sys

    ap = argparse.ArgumentParser(description="解析 history.vbs")
    ap.add_argument("vbs", help="history.vbs 路径")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)
    actions = parse_history_file(args.vbs)
    if args.json:
        json.dump(actions, sys.stdout, ensure_ascii=False, indent=2)
    else:
        for a in actions:
            print(f"{a['command']}({', '.join(a['args'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
