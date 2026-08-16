#!/usr/bin/env python3
"""全量回归：逐测试模块子进程隔离运行，汇总结果。

同进程 discover 会在 Qt offscreen + COM/桥 DLL 混载时触发访问冲突
（0xC0000005），故每个测试模块单独起进程；崩溃只影响该模块并可定位。

rc=5（no tests）的模块是 pytest 风格纯函数测试，unittest 收集不到，
标记 [pyst] 不计失败。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable


def main() -> int:
    mods = sorted(p.stem for p in (ROOT / "tests").glob("test_*.py"))
    print(f"{len(mods)} test modules; runner = {PY}\n")
    failed: list[str] = []
    crashed: list[str] = []
    stats = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for m in mods:
        r = subprocess.run(
            [PY, "-B", "-m", "unittest", f"tests.{m}", "-v"],
            cwd=str(ROOT), capture_output=True, timeout=900)
        text = (r.stdout + r.stderr).decode("utf-8", "replace")
        lines = text.splitlines()
        ran = next(
            (ln for ln in lines if ln.startswith("Ran ")), "")
        if ran:
            stats["tests"] += int(ran.split()[1])
        for ln in lines:
            if not (ln.startswith("OK") or ln.startswith("FAILED")):
                continue
            for part in ln.replace("(", " ").replace(")", " ").split():
                for key in ("skipped", "failures", "errors"):
                    if part.startswith(key + "="):
                        stats[key] += int(part.split("=")[1])
        if r.returncode == 0:
            print(f"[ ok ] {m} ({ran or '?'})")
        elif r.returncode == 5:
            print(f"[pyst] {m} (pytest 风格，unittest 收集不到)")
        elif r.returncode == 1:
            failed.append(m)
            print(f"[FAIL] {m} ({ran})")
        else:
            crashed.append(m)
            print(f"[CRSH] {m} rc={r.returncode} ({ran or '?'})")
    print(f"\n== {stats['tests']} tests, {stats['failures']} failures, "
          f"{stats['errors']} errors, {stats['skipped']} skipped; "
          f"{len(failed)} failed modules, {len(crashed)} crashed modules")
    for m in failed + crashed:
        print(f"  - {m}")
    return 1 if (failed or crashed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
