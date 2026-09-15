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


def contract_gate() -> int:
    """R40-2：先跑 API 面契约门（目录/账本/总账/桥接/语料/守卫六项）。

    契约门查的是"跨模块不变量"，测试模块各查各的；放在最前面，
    一进门就知道 API 面是否仍自洽（失败不阻断跑测试，但计入结论）。
    """
    r = subprocess.run([PY, "-B", str(ROOT / "tools" / "api_contract_check.py")],
                       cwd=str(ROOT), capture_output=True, timeout=600)
    text = (r.stdout + r.stderr).decode("utf-8", "replace")
    for ln in text.splitlines():
        if "PASS" in ln or "FAIL" in ln or ln.startswith("SUMMARY"):
            print("  " + ln.strip())
    print(f"[{' ok ' if r.returncode == 0 else 'FAIL'}] api_contract_check\n")
    return r.returncode


def main() -> int:
    mods = sorted(p.stem for p in (ROOT / "tests").glob("test_*.py"))
    print(f"{len(mods)} test modules; runner = {PY}\n")
    gate_rc = contract_gate()
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
                        stats[key] += int(part.split("=")[1].rstrip(","))
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
    if gate_rc != 0:
        print("  - api_contract_check（契约门未过）")
    return 1 if (failed or crashed or gate_rc != 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
