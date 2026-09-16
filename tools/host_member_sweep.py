#!/usr/bin/env python3
"""R45-3：宿主成员可用性普查的**常规入口**（一条命令复算覆盖率）。

之前普查只能直接敲 `tools/dispatch_name_probe.py --sweep --project ...`——
参数长、工程集靠记忆、覆盖率要另开脚本看。本工具把它固定成一条命令：

    python tools/host_member_sweep.py                 # 跑普查（默认工程集）
    python tools/host_member_sweep.py --report-only   # 不起宿主，只报当前证据
    python tools/host_member_sweep.py --project a.pph --project b.pph

产出与 `--sweep` 相同：`schemas/host_member_availability.json`（覆盖率、
未实现成员、空对象及其前置提示、自动配方证据）+ `schemas/name_verdicts.json`。

退出码：覆盖率低于 `--min-classes`（默认 84 = R44 收口基线）即**非零** ——
普查是"只增不减"的证据，掉下来就是回归。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console_utf8  # noqa: E402

console_utf8.enable()

PROBE = ROOT / "tools" / "dispatch_name_probe.py"
AVAIL = ROOT / "schemas" / "host_member_availability.json"
EXERCISE = Path(r"D:\training\cradle\CradleCFD_2025.2_scFLOW_Example_a"
                r"\Exercise")
#: 默认工程集：box（最小可开）+ 4 个有几何/条件/CoSim 语料的算例
DEFAULT_PROJECTS = [
    ROOT / "box.pph",
    EXERCISE / "exB01" / "exB01-1" / "Org" / "exB01-1_intake_manifold.pph",
    EXERCISE / "exA26" / "exA26-1" / "Org" / "exA26-1_ldc.pph",
    EXERCISE / "exA16" / "exA16-2" / "Org" / "exA16-2.pph",
    EXERCISE / "exA25" / "exA25-1" / "Org" / "exA25-1.pph",
]


def summarize(data: dict) -> dict:
    """覆盖率总账（缺字段一律按 0，不让证据格式变化把工具打崩）。"""
    cov = (data or {}).get("coverage") or {}
    classes = (data or {}).get("classes") or {}
    entries = [m for v in classes.values() for m in (v.get("unknown") or [])]
    errors = [m for v in classes.values() for m in (v.get("errors") or [])]
    return {
        "classes_swept": cov.get("classes_swept") or 0,
        "classes_total": cov.get("classes_total") or 0,
        "members_swept": cov.get("members_swept") or 0,
        "members_total": cov.get("members_total") or 0,
        "empty_objects": len(cov.get("empty_objects") or []),
        "no_member_classes": len(cov.get("no_member_classes") or []),
        "unswept_classes": len(cov.get("unswept_classes") or []),
        "absent_entries": len(entries),
        "absent_names": len(set(entries)),
        "probe_errors": len(errors),
        "auto_obtained": len(cov.get("auto_obtained") or {}),
        "identity_rejected": len(cov.get("identity_rejected") or []),
    }


def render(s: dict) -> str:
    pct = (100.0 * s["classes_swept"] / s["classes_total"]
           if s["classes_total"] else 0.0)
    lines = [
        "普查覆盖：{}/{} 类（{:.1f}%）、{}/{} 成员".format(
            s["classes_swept"], s["classes_total"], pct,
            s["members_swept"], s["members_total"]),
        "未实现成员 {} 条（去重 {} 个名字）；探针侧错误 {}".format(
            s["absent_entries"], s["absent_names"], s["probe_errors"]),
        "取不到实例 {} 类（各带前置提示）；手册无成员 {} 类；未普查 {} 类".format(
            s["empty_objects"], s["no_member_classes"], s["unswept_classes"]),
        "自动配方取得 {} 类（验身否 {} 条）".format(
            s["auto_obtained"], s["identity_rejected"]),
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="宿主成员可用性普查（常规入口）")
    ap.add_argument("--project", type=Path, action="append", default=None,
                    help="用哪个工程建实例，可重复；默认 5 个（见 DEFAULT_PROJECTS）")
    ap.add_argument("--budget", type=float, default=420.0,
                    help="自动配方扩面的时间预算（秒）")
    ap.add_argument("--min-classes", type=int, default=84,
                    help="覆盖率下限（默认 R44 收口基线 84）；低于即非零退出")
    ap.add_argument("--report-only", action="store_true",
                    help="不起宿主，只报已有证据的覆盖率")
    ap.add_argument("--json", action="store_true", help="总账以 JSON 输出")
    ap.add_argument("--keep-host", action="store_true", help="跑完不杀宿主")
    ap.add_argument("--out", type=Path, default=AVAIL)
    args = ap.parse_args(argv)

    if not args.report_only:
        projects = args.project or DEFAULT_PROJECTS
        missing = [p for p in projects if not Path(p).is_file()]
        projects = [p for p in projects if Path(p).is_file()]
        for p in missing:
            print("[warn] 工程不存在，跳过：" + str(p), file=sys.stderr)
        if not projects:
            print("[error] 没有任何可用工程（--project 给一个）", file=sys.stderr)
            return 2
        cmd = [sys.executable, str(PROBE), "--sweep",
               "--auto-budget", str(args.budget),
               "--json", str(ROOT / "_p12u_gate" / "r45" / "name_verdicts.json")]
        for p in projects:
            cmd += ["--project", str(p)]
        if args.keep_host:
            cmd.append("--keep-host")
        print("[sweep] " + " ".join(cmd[:4]) + " …"
              + "（" + str(len(projects)) + " 个工程）", flush=True)
        rc = subprocess.call(cmd, cwd=str(ROOT))     # 继承 stdio：不抓管道
        if rc != 0:
            print("[error] 探针退出码 " + str(rc), file=sys.stderr)

    if not args.out.is_file():
        print("[error] 没有普查证据：" + str(args.out), file=sys.stderr)
        return 2
    data = json.loads(args.out.read_text(encoding="utf-8"))
    s = summarize(data)
    print(json.dumps(s, ensure_ascii=False, indent=1) if args.json
          else render(s))
    if s["classes_swept"] < args.min_classes:
        print("[fail] 覆盖类数 " + str(s["classes_swept"]) + " < 下限 "
              + str(args.min_classes), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
