#!/usr/bin/env python3
"""P12-C 条件收割机：CreateCond* 实机批量 create → SaveProject → diff。

纪律（DEV_PLAN §18.2）：键必须来自真实 XML——本工具只收录
``p12c_cond_harvest_out.pph`` 的 main.xml 中真实出现的条件实体
（经 schema_extract 深扫规则），HTML 显示名猜测禁令沿用。

用法::

    python tools/_p12c_cond_harvest.py plan     # 离线：打印目标清单
    python tools/_p12c_cond_harvest.py build    # 离线：生成 VBS
    python tools/_p12c_cond_harvest.py run      # 实机：rot 权威通道执行
    python tools/_p12c_cond_harvest.py merge    # 离线：diff → merged.json
    python tools/_p12c_cond_harvest.py all      # run + merge
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pph_parser import PphArchive  # noqa: E402
from schema_extract import (  # noqa: E402
    extract_archive_schema, extend_merged_schema, load_schema_json,
    write_schema_json,
)

CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
COND_TYPES = ROOT / "schemas" / "cond_types.json"
MERGED = ROOT / "schemas" / "merged.json"
# 基线须为 2025.2 原生工程：tests/box/box.pph 是 2023.2 旧版 CAB，
# SaveProject 触发版本转换确认链（Confirm→Region 校验 Error→再
# Confirm，首跑实测 58/58 create err=0 但保存无法完成）。
BASELINE = ROOT / "p12e_disc_e2e_out.pph"
OUT = ROOT / "p12c_cond_harvest_out.pph"
VBS = ROOT / "p12c_cond_harvest.vbs"
LOG = ROOT / "p12c_cond_harvest.log"
REPORT = ROOT / "p12c_harvest_report.json"

#: 实测毒类型：create 成功但其序列化毒杀同脚本 SaveProject（脚本静默
#: 死亡、无 save_err 行；三层版本转换 Confirm 后仍死）。全部批死案例
#: （0-13/0-15/0-29/58）都由它解释——其余类型单测 create+save 全绿。
#: 该类型单独隔离处置（如实记录，不入批量）。
SAVE_POISON = {"CreateCondBatteryARCDataPreprocessing"}

#: CreateCond* 之外的使能型创建（目标类型在 universe 缺口内才纳入）
EXTRA_ENABLERS = {
    "CondFMIVariable": "CreateFMIVariable",
}


def load_registries() -> tuple[list[str], set[str], set[str]]:
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    conds = cat["classes"]["Conditions"]["methods"]
    creators = sorted(k for k in conds if k.startswith("CreateCond"))
    ct = json.loads(COND_TYPES.read_text(encoding="utf-8"))
    univ = set(ct["types"])
    merged = load_schema_json(MERGED)
    have = set((merged.get("conditions") or {}).get("types") or {})
    return creators, univ, have


def harvest_targets() -> list[tuple[str, str, str]]:
    """返回 [(目标类型名, 方法名, 唯一短名)]。

    1. CreateCond* 直建且目标类型在 universe（主路径；缺口优先级由
       merge 阶段的 diff 决定，这里全量纳入已注册 universe 目标）；
    2. 目标类型不在 universe 的 CreateCond*（别名探针——落盘的真实
       type= 可能对上缺口类型或揭示注册表拼写差异，不猜测）；
    3. 使能型创建（EXTRA_ENABLERS，仅当目标在缺口内）。
    """
    creators, univ, have = load_registries()
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for idx, c in enumerate(creators):
        if c in SAVE_POISON:
            continue
        target = "Cond" + c[len("CreateCond"):]
        if target in univ and target in have:
            continue  # 已有精确键，无需重收
        short = c[len("CreateCond"):]
        if short in seen:
            short = f"{short}{idx}"
        seen.add(short)
        out.append((target, c, short))
    for target, method in EXTRA_ENABLERS.items():
        if target in univ and target not in have and target not in {
                t for t, _c, _s in out}:
            short = target[len("Cond"):]
            if short not in seen:
                seen.add(short)
                out.append((target, method, short))
    return out


def build_harvest_vbs(targets: list[tuple[str, str, str]],
                      baseline: Path = BASELINE,
                      out_pph: Path = OUT,
                      with_save: bool = True) -> list[str]:
    """生成收割 VBS：逐类型 create（带 name → 无参重试）→ SaveProject。

    ``with_save=False`` 为两阶段收割的 Phase A（只创建不保存）：
    实测同脚本内 create→SaveProject 对特定类型（首抓
    ``CondBatteryARCDataPreprocessing``）会静默杀死脚本（三层
    版本转换 Confirm 后仍死），而**事后对同一脏文档的纯保存
    VBS 可成功**（Phase B）——两阶段绕开该缺陷。
    """
    lines = _vbs_header(baseline)
    for n, (_target, method, short) in enumerate(targets, 1):
        name = f"P12cH{short}"
        lines += _create_block(n, method, short, name)
    if with_save:
        lines += _vbs_save_tail(out_pph)
    else:
        lines += ['out.WriteLine "end"', "out.Close"]
    return lines


def _vbs_header(baseline: Path, open_project: bool = True) -> list[str]:
    lines = [
        "' P12-C condition harvest (CreateCond* batch)",
        "' !! 仅限在 scFLOWpre 宿主内执行（File → Execute VBScript / rot）。",
        "On Error Resume Next",
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        'Set fso = CreateObject("Scripting.FileSystemObject")',
        f'Set out = fso.CreateTextFile("{LOG.as_posix()}", True)',
    ]
    if open_project:
        lines += [
            f'Doc_.OpenProject "{baseline.as_posix()}", False',
            'out.WriteLine "open_err=" & CStr(Err.Number)',
            "Err.Clear",
            "Set Conditions_ = Doc_.GetConditions",
            'out.WriteLine "cond_alive=" '
            '& CStr(Not (Conditions_ Is Nothing))'
            ' & " err=" & CStr(Err.Number)',
            "Err.Clear",
        ]
    return lines


def _vbs_save_tail(out_pph: Path) -> list[str]:
    # 实测模型：COM CreateCond* 条件存活于脚本会话事务层——只有
    # 「同脚本内 create → 改动强制脏 → SaveProject」才能落进
    # main.xml；脚本一结束（或跨脚本纯保存）未提交条件即被丢弃。
    return [
        "v_ = Conditions_.SetDefaultTemperature(300.0)",
        'out.WriteLine "dirty_err=" & CStr(Err.Number)',
        "Err.Clear",
        f'Doc_.SaveProject "{out_pph.as_posix()}"',
        'out.WriteLine "save_err=" & CStr(Err.Number)',
        "Err.Clear",
        'out.WriteLine "out_exists=" & CStr(fso.FileExists("'
        + out_pph.as_posix() + '"))',
        'out.WriteLine "end"',
        "out.Close",
    ]


def _create_block(n: int, method: str, short: str, name: str) -> list[str]:
    return [
        "Set Cnd_ = Nothing",
        f'Set Cnd_ = Conditions_.{method}("{name}")',
        "If Cnd_ Is Nothing Then",
        "    Err.Clear",
        f"    Set Cnd_ = Conditions_.{method}()",
        f'    out.WriteLine "mk{n:03d}_{short}_mode=noarg err=0"',
        "End If",
        (f'out.WriteLine "mk{n:03d}_{short}=" '
         '& CStr(Not (Cnd_ Is Nothing)) & " err=" & CStr(Err.Number)'),
        "Err.Clear",
    ]


def write_vbs(lines: list[str], target: Path) -> Path:
    # scFLOWpre 的 VBScript 引擎要求 UTF-16LE + BOM（与 history.vbs 一致）
    target.write_bytes("\r\n".join(lines).encode("utf-16"))
    return target


def parse_log(path: Path) -> dict:
    """解析收割日志：mk 行 / open/save err / mode 标记。"""
    res: dict = {"mk": {}, "modes": {}, "open_err": None, "save_err": None,
                 "cond_alive": None, "has_end": False, "total": 0, "bad": 0}
    if not path.is_file():
        res["error"] = "log not found"
        return res
    for raw in path.read_text(encoding="mbcs",
                              errors="replace").splitlines():
        line = raw.strip()
        if line == "end":
            res["has_end"] = True
            continue
        if line.startswith("open_err="):
            res["open_err"] = line.split("=", 1)[1]
            continue
        if line.startswith("save_err="):
            res["save_err"] = line.split("=", 1)[1]
            continue
        if line.startswith("cond_alive="):
            res["cond_alive"] = line
            continue
        if "_mode=noarg" in line:
            short = line[len("mk"):].split("_mode", 1)[0]
            res["modes"][short] = "noarg"
            res["total"] += 1
            continue
        if line.startswith("mk") and "=" in line and "mode=" not in line:
            head, _, tail = line.partition("=")
            # head 形如 mk001_Acceleration；tail 形如 True err=0
            short = head[len("mk"):]
            alive, _, err = tail.partition(" err=")
            err = err.strip().split(" ", 1)[0]
            res["mk"][short] = {"alive": alive.strip(), "err": err}
            res["total"] += 1
            if alive.strip() != "True" or err.strip() != "0":
                res["bad"] += 1
    return res


def run_host(timeout: float = 900.0, vbs: Path | None = None) -> dict:
    from automation import host_pipeline
    run = host_pipeline.run_vbs_authoritative(vbs or VBS, timeout=timeout)
    return run


def merge(baseline: Path = BASELINE, out_pph: Path = OUT,
          merged_path: Path = MERGED) -> dict:
    """diff 收割产物 vs 基线 → 新类型入 merged.json + 报告。"""
    base = extract_archive_schema(PphArchive.open(str(baseline)))
    base_types = set((base.get("conditions") or {}).get("types") or {})
    harch = PphArchive.open(str(out_pph))
    hschema = extract_archive_schema(harch)
    htypes = (hschema.get("conditions") or {}).get("types") or {}

    _, univ, have_before = load_registries()
    new_in_universe = sorted(k for k in htypes
                             if k not in base_types and k in univ
                             and k not in have_before)
    alias_evidence = sorted(k for k in htypes
                            if k not in base_types and k not in univ)

    report = {
        "baseline": str(baseline),
        "harvest_out": str(out_pph),
        "types_before": len(have_before),
        "universe": len(univ),
        "new_in_universe": new_in_universe,
        "alias_evidence": alias_evidence,
    }

    if new_in_universe or alias_evidence:
        extra = {"conditions": {"types": {k: htypes[k] for k in htypes
                                          if k not in base_types}}}
        merged = extend_merged_schema(load_schema_json(merged_path), extra)
        write_schema_json(merged, merged_path)
        _, _u, have_after = load_registries()
        report["types_after"] = len(have_after)
    else:
        report["types_after"] = len(have_before)
    report["remaining_missing"] = sorted(univ - set(
        (load_schema_json(merged_path).get("conditions")
         or {}).get("types") or {}))
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    global LOG, OUT
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "plan"
    if cmd == "plan":
        targets = harvest_targets()
        print(f"targets: {len(targets)}")
        for t, c, s in targets:
            print(f"  {t:42s} <- {c}")
        return 0
    if cmd == "build":
        targets = harvest_targets()
        write_vbs(build_harvest_vbs(targets), VBS)
        print(f"vbs written: {VBS} ({len(targets)} targets)")
        return 0
    if cmd == "run":
        run = run_host()
        print("run:", json.dumps(run))
        return 0 if run.get("ok") else 1
    if cmd == "merge":
        rep = merge()
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 0
    if cmd == "create":
        targets = harvest_targets()
        lines = build_harvest_vbs(targets, with_save=False)
        write_vbs(lines, VBS)
        run = run_host()
        print("create run:", json.dumps(run))
        rep = parse_log(LOG)
        print("creates:", rep["total"], "bad:", rep["bad"])
        return 0 if run.get("ok") and rep["bad"] == 0 else 1
    if cmd == "save":
        lines = (_vbs_header(BASELINE, open_project=False)
                 + ["Set Conditions_ = Doc_.GetConditions"]
                 + _vbs_save_tail(OUT))
        write_vbs(lines, VBS)
        run = run_host()
        print("save run:", json.dumps(run))
        rep = parse_log(LOG)
        print("save_err:", rep.get("save_err"), "has_end:", rep["has_end"])
        return 0 if run.get("ok") and rep.get("save_err") == "0" else 1
    if cmd == "all":
        # 单脚本 = create 全量 + 强制脏 + SaveProject（事务层模型：
        # 跨脚本边界未提交条件即被丢弃；create/save 两阶段仅作诊断）
        targets = harvest_targets()
        write_vbs(build_harvest_vbs(targets), VBS)
        run = run_host()
        print("run:", json.dumps(run))
        if not run.get("ok"):
            return 1
        rep = merge()
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 0
    if cmd == "probe":
        start, end = int(argv[1]), int(argv[2])
        targets = harvest_targets()[start:end]
        pvbs = ROOT / "scratch" / "_p12c_probe.vbs"
        plog = ROOT / "scratch" / "_p12c_probe.log"
        pout = ROOT / "scratch" / "_p12c_probe_out.pph"
        old_log, old_out = LOG, OUT
        LOG, OUT = plog, pout
        write_vbs(build_harvest_vbs(targets), pvbs)
        LOG, OUT = old_log, old_out
        run = run_host(vbs=pvbs)
        print("run:", json.dumps(run))
        if plog.exists():
            txt = plog.read_text(encoding="mbcs", errors="replace")
            keep = [l for l in txt.splitlines()
                    if l.startswith(("open_err", "save_err", "out_exists",
                                     "end")) or "_mode=" in l]
            print("\n".join(keep[-6:]))
        print("out exists:", pout.exists())
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
