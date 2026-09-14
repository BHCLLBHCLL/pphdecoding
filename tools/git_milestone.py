#!/usr/bin/env python3
"""里程碑自动提交 + 推送（R 轮次收口纪律）。

约定（2026-09-14 起，见 docs/ROUNDS.md 的「提交纪律」）：**每个关键功能/
每轮 R 收口后，自动提交并推送到 GitHub 远程**。本脚本把这件事做成一条命令，
并用白名单把「代码/文档/测试/小证据」与「大运行产物」分开 —— 后者永不入库：

* 收录：根目录与 automation/tools/tests 下的 *.py、*.md、schemas/*.json、
  以及 _p12u_* 证据目录下的 *.json / *.jsonl / *.vbs / *.log；
* 排除：*.pph / *.mdl / *.oct / *.gph / *.x_t / *.X_T / *.stl / *.fph /
  *.sph / *.l / *.dmp / *.prp / *.xenv / *.js / *.sctsnapshot 等二进制或
  大产物（哪怕被 git 跟踪）；单文件超过 1 MB 也跳过并告警。
* **权威文本资产例外**（schemas/*.json、docs/*.md）上限放宽到 8 MB：
  schemas/vb_api_catalog.json 在 R30 已达 2.14 MB，1 MB 上限会把它**静默跳过**
  —— 实测该文件自 2026-08-20（0cecf53, P9）起就没再进过仓库，
  目录更新一直躺在工作树里（R30-5）。

注意：.gitignore 里有 tests/*，所以新增测试模块必须 git add -f。

用法::

    python tools/git_milestone.py --dry-run            # 只看会提交什么
    python tools/git_milestone.py --round R3 -m "..."  # 提交 + 推送
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console_utf8  # noqa: E402

console_utf8.enable()

#: 收录模式（相对仓库根，** 表示任意深度）
INCLUDE = [
    "*.py",
    "*.md",
    "*.json",
    "*.jsonl",
    "automation/*.py",
    "tools/*.py",
    "tests/*.py",
    "schemas/*.json",
    "_p12*/*.json",
    "_p12*/*.jsonl",
    "_p12*/*.vbs",
    "_p12*/*.log",
    "_p12*/*.md",
]

#: 被 .gitignore 忽略但**必须入库**的文本资产：git status 看不见它们，
#: 必须用 filesystem glob + git add -f（tests/* 被 .gitignore 覆盖）。
FORCE_GLOBS = [
    "tests/*.py",
]

#: 永不入库的扩展名（二进制 / 大产物）
EXCLUDE_EXT = {
    ".pph", ".mdl", ".oct", ".gph", ".x_t", ".stl", ".fph", ".sph",
    ".dmp", ".prp", ".xenv", ".js", ".sctsnapshot", ".cab", ".zip",
    ".his", ".bmp", ".png", ".jpg", ".log.bak", ".exe", ".dll",
}

#: 允许的大体积上限（收录集都是文本；超过即视为误配）
MAX_BYTES = 1_000_000

#: 权威文本资产（schema/文档）放宽上限。理由见模块 docstring：1 MB 上限曾把
#: 2.14 MB 的 vb_api_catalog.json 静默跳过，导致仓库里的目录停在 2026-08-20。
BIG_TEXT_GLOBS = ("schemas/*.json", "docs/*.md")
MAX_BYTES_BIG = 8_000_000


def _size_limit(rel: str) -> int:
    """按路径取体量上限（权威文本资产放宽）。"""
    if any(fnmatch.fnmatch(rel, pat) for pat in BIG_TEXT_GLOBS):
        return MAX_BYTES_BIG
    return MAX_BYTES


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    # encoding 必须显式给：默认按 ANSI 代码页解码，git 输出里的 UTF-8
    # 字节会抛 UnicodeDecodeError（读线程里的异常让 stdout 变 None）。
    return subprocess.run(["git", *args], cwd=str(ROOT), text=True,
                          encoding="utf-8", errors="replace",
                          capture_output=True, check=check)


def _is_excluded(rel: str) -> bool:
    ext = Path(rel).suffix.lower()
    if ext in EXCLUDE_EXT:
        return True
    return rel.endswith("_part.mdl") or rel.endswith("_ridge.mdl")


def candidates() -> tuple[list[str], list[str]]:
    """返回 (收录文件, 跳过告警)。只收 git 视角下「有改动」的文件。"""
    try:
        status = _git("status", "--porcelain",
                      "--untracked-files=all").stdout.splitlines()
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        raise SystemExit("git status 失败: " + (exc.stderr or ""))
    take: list[str] = []
    skipped: list[str] = []
    for line in status:
        if len(line) < 4:
            continue
        rel = line[3:].strip().strip(chr(34))
        if " -> " in rel:
            rel = rel.split(" -> ", 1)[1]
        if not any(fnmatch.fnmatch(rel, pat) for pat in INCLUDE):
            continue
        p = ROOT / rel
        if not p.is_file():
            continue
        if _is_excluded(rel):
            skipped.append(rel + " (扩展名排除)")
            continue
        size = p.stat().st_size
        limit = _size_limit(rel)
        if size > limit:
            skipped.append(rel + " (" + str(size) + " B > "
                            + str(limit) + " B)")
            continue
        take.append(rel)
    for pat in FORCE_GLOBS:
        for p in sorted(ROOT.glob(pat)):
            if not p.is_file():
                continue
            rel = p.relative_to(ROOT).as_posix()
            if _is_excluded(rel) or p.stat().st_size > _size_limit(rel):
                continue
            take.append(rel)
    return sorted(set(take)), sorted(set(skipped))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="里程碑自动提交 + 推送")
    ap.add_argument("--round", default="", help="轮次号，如 R3（进提交信息）")
    ap.add_argument("-m", "--message", default="",
                    help="提交信息正文（无则用轮次号占位）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args(argv)

    take, skipped = candidates()
    print("[milestone] 收录 " + str(len(take)) + " 个文件")
    for rel in take:
        print("   + " + rel)
    if skipped:
        print("[milestone] 跳过 " + str(len(skipped)) + " 个：")
        for rel in skipped[:20]:
            print("   - " + rel)
    if not take:
        print("[milestone] 无改动可提交")
        return 0
    if args.dry_run:
        return 0

    _git("add", "-f", "--", *take)
    staged = _git("diff", "--cached", "--name-only").stdout.split()
    if not staged:
        print("[milestone] 暂存区为空，放弃提交")
        return 0
    bad = [f for f in staged if _is_excluded(f)
           or (ROOT / f).stat().st_size > MAX_BYTES]
    if bad:
        _git("reset", "-q", "--", *bad, check=False)
        print("[milestone] 从暂存区剔除越界文件：" + ", ".join(bad))
    prefix = "feat" if any(f.endswith(".py") for f in staged) else "chore"
    head = (args.round + " " if args.round else "") + (args.message or "milestone")
    subject = prefix + ": " + head.strip()
    body = ("自动提交：轮次 " + (args.round or "-") + " 收口。\n\n"
            + "纳入 " + str(len(staged)) + " 个源码/文档/测试/小证据文件；"
            + "大运行产物（.pph/.mdl/.oct/.gph/.x_t 等）按仓库纪律不入库。")
    _git("commit", "-m", subject, "-m", body)
    print(_git("log", "-1", "--stat", "--format=%h %s").stdout.rstrip())

    if args.no_push:
        print("[milestone] --no-push：跳过推送")
        return 0
    branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    push = _git("push", "origin", branch, check=False)
    out = (push.stdout + push.stderr).strip()
    print("[milestone] push origin " + branch + " -> rc=" + str(push.returncode))
    if out:
        print("   " + out.replace("\n", "\n   "))
    return 0 if push.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
