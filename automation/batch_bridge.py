#!/usr/bin/env python3
"""scFLOWpre 批处理桥（Windows CLI bat + SCTpreCLIHelper）。"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import scflowpre_probe

CLI_BATS = {
    "pre": "scFLOWpreCLI_Bx64net.bat",
    "sctpre": "SCTpreCLI_Bx64net.bat",
    "comb": "SCTcombCLI_Bx64net.bat",
}


def find_cli_bat(kind: str = "pre") -> Optional[Path]:
    name = CLI_BATS.get(kind)
    if name is None:
        raise ValueError(f"unknown CLI kind: {kind}")
    return scflowpre_probe.find_program(name)


@dataclass
class BatchCommand:
    """一条批处理命令。"""

    program: Path
    args: list[str]
    dry_run_text: str = ""

    def as_list(self) -> list[str]:
        return [str(self.program), *self.args]

    def as_shell(self) -> str:
        return " ".join(shlex.quote(a) for a in self.as_list())


def build_command(bat: str | Path, cmb: str | Path, np_: int = 1,
                  license_file: Optional[str | Path] = None,
                  extra: Optional[list[str]] = None) -> BatchCommand:
    """构造 ``<bat> [options] <cmb> <np> [extra...]``。"""
    args: list[str] = []
    if license_file is not None:
        args += ["--license-file", str(license_file)]
    args += [str(cmb), str(np_)]
    if extra:
        args += list(extra)
    return BatchCommand(program=Path(bat), args=args)


def _run_helper(helper: Path, command: str, bat: Path,
                args: list[str]) -> list[str]:
    """调用 SCTpreCLIHelper 并返回输出行。"""
    proc = subprocess.run(
        [str(helper), command, str(bat), *args],
        capture_output=True, text=True, timeout=60, check=False)
    out = (proc.stdout or "").splitlines()
    if proc.returncode != 0 and not out:
        out = (proc.stderr or "").splitlines()
    return out


def inspect(bat: str | Path, args: list[str], *,
            helper: Optional[Path] = None,
            command: str = "all-cmdline") -> dict:
    """dry-run：让 SCTpreCLIHelper 打印将执行的完整命令行。"""
    bat = Path(bat)
    if helper is None:
        helper = scflowpre_probe.find_program("SCTpreCLIHelper_Bx64.exe")
    if helper is None:
        return {"available": False, "hint": "SCTpreCLIHelper 未找到"}
    lines = _run_helper(helper, command, bat, args)
    return {"available": True, "command": command, "lines": lines}


class BatchBridge:
    """预处理器/组合处理批处理入口。"""

    def __init__(self, kind: str = "pre"):
        self.kind = kind
        self.bat = find_cli_bat(kind)

    def available(self) -> bool:
        return self.bat is not None

    def plan(self, cmb: str | Path, np_: int = 1,
             license_file: Optional[str | Path] = None,
             extra: Optional[list[str]] = None) -> BatchCommand:
        if self.bat is None:
            raise FileNotFoundError(f"CLI bat 未找到: {CLI_BATS[self.kind]}")
        return build_command(self.bat, cmb, np_, license_file, extra)

    def dry_run(self, cmb: str | Path, np_: int = 1,
                license_file: Optional[str | Path] = None,
                extra: Optional[list[str]] = None) -> dict:
        cmd = self.plan(cmb, np_, license_file, extra)
        return inspect(self.bat, cmd.args)


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="scFLOWpre 批处理桥")
    ap.add_argument("--kind", choices=sorted(CLI_BATS), default="pre")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--license-file")
    ap.add_argument("cmb")
    ap.add_argument("np", type=int, default=1, nargs="?")
    args = ap.parse_args(argv)
    bridge = BatchBridge(args.kind)
    if not bridge.available():
        print(f"{args.kind}: CLI bat 未找到", file=sys.stderr)
        return 1
    cmd = bridge.plan(args.cmb, args.np, args.license_file)
    print(cmd.as_shell())
    if args.dry_run:
        result = inspect(cmd.program, cmd.args)
        print("\n".join(result.get("lines", [])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
