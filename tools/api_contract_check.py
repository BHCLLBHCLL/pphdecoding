#!/usr/bin/env python3
"""R39-3：API 面**契约门**（一条命令查完 R29–R39 建立的全部不变量）。

把这些轮次散落的断言收进一个只读入口，便于"改完就跑一下"：

1. **目录**：假参数 0、取值全为标识符样、`dispatch_name` 已入册；
2. **实测键账本**：条数、缺口 ↔ 终态一一对应、终态带理由；
3. **名字总账**：41 处标题/签名分歧**全有终态**（裁定 或 NYI+配方）；
4. **typed 桥**：目录成员覆盖率、包装方法全部可追溯；
5. **语料对拍**：名字同源链接不再有手册漏项（取最近一次证据）；
6. **取值守卫三态**：无词表 → `None`（不拦），有词表越界 → `False`。

用法::

    python tools/api_contract_check.py            # 人读
    python tools/api_contract_check.py --json out.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import console_utf8  # noqa: E402

console_utf8.enable()

from automation import scflowpre_api as api  # noqa: E402

CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
LEDGER = ROOT / "schemas" / "host_keys.json"
ACCOUNT = ROOT / "schemas" / "dispatch_account.json"
IDENT = re.compile(r"^[A-Za-z0-9_.:/\-]+$")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def check_catalog(catalog_path: Path | None = None) -> dict:
    cat = json.loads((catalog_path or CATALOG).read_text(encoding="utf-8"))
    bogus, bad_values, with_dispatch = 0, [], 0
    for cls, info in cat["classes"].items():
        for kind in ("methods", "properties"):
            for name, e in (info.get(kind) or {}).items():
                if e.get("dispatch_name"):
                    with_dispatch += 1
                for a in (e.get("arguments") or []):
                    if (not a.get("type")
                            and str(a.get("name", "")).startswith(('"', "“", "”"))):
                        bogus += 1
                for slot in (e.get("arguments") or []) + [e.get("return") or {}]:
                    if not isinstance(slot, dict):
                        continue
                    for v in (slot.get("values") or []):
                        if not IDENT.match(v["value"]):
                            bad_values.append(cls + "." + name + "=" + v["value"])
    return {"bogus_args": bogus, "non_identifier_values": bad_values[:5],
            "non_identifier_count": len(bad_values),
            "dispatch_names": with_dispatch,
            "ok": bogus == 0 and not bad_values and with_dispatch > 0}


def check_ledger(ledger_path: Path | None = None) -> dict:
    led = json.loads((ledger_path or LEDGER).read_text(encoding="utf-8"))
    gaps = set(led.get("known_gaps") or [])
    status = led.get("known_gap_status") or {}
    missing = sorted(gaps - set(status))
    bad_terminal = [g for g, info in status.items()
                    if not info.get("terminal") or not info.get("reason")]
    return {"keys": len(led.get("keys") or []), "gaps": sorted(gaps),
            "gaps_without_status": missing, "gaps_without_terminal": bad_terminal,
            "ok": not missing and not bad_terminal and len(led["keys"]) >= 18}


def check_account(account_path: Path | None = None) -> dict:
    path = account_path or ACCOUNT
    if not path.is_file():
        return {"ok": False, "error": "缺 schemas/dispatch_account.json"}
    data = json.loads(path.read_text(encoding="utf-8"))
    counts = data["counts"]
    bad = [r for r in data["rows"] if r["state"] == "nyi" and not r.get("reason")]
    return {"total": counts["total"], "verdict": counts["verdict"],
            "nyi": counts["nyi"], "nyi_without_reason": len(bad),
            "ok": (counts["verdict"] + counts["nyi"] == counts["total"]
                   and counts["total"] > 0 and not bad)}


def check_bridge() -> dict:
    cov = _load("contract_cov", ROOT / "tools" / "api_bridge_coverage.py")
    data = cov.report()
    return {"coverage": data["coverage"], "wrapped": data["wrapped"],
            "unknown_wrapped": data["unknown_wrapped_members"],
            "ok": data["coverage"] >= 0.9
            and not data["unknown_wrapped_members"]}


def check_corpus() -> dict:
    best, best_m = None, -1.0
    for p in sorted(ROOT.glob("_p12u_gate/r*/corpus_diff_attr.json")):
        m = p.stat().st_mtime
        if m > best_m:
            best, best_m = p, m
    if best is None:
        return {"ok": False, "error": "缺语料对拍证据"}
    data = json.loads(best.read_text(encoding="utf-8"))
    gaps = {d["parent"]: d["only_corpus"] for d in data.get("discovered") or []
            if d.get("only_corpus")}
    return {"evidence": best.name, "links": len(data.get("discovered") or []),
            "links_with_gap": sorted(gaps), "ok": not gaps}


def check_sweep_convergence(avail_path: Path | None = None,
                           unswept_path: Path | None = None,
                           floor: int = 155) -> dict:
    """R53-3：普查**收口结论**的自动守卫（第 8 项）。

    收口判据（审计 §64.3）三条，这里逐条查：

    1. 覆盖率 ≥ 收口下限（**只许升不许降**）；
    2. 未普查类**全部有终态**（`unswept_account.json` 与证据的类集一致）；
    3. 复验窗口结论为"无需重开"（宿主版本/成员集/覆盖率三份客观事实）。
    """
    # 路径可注入：测试要能拿**合成证据**验"掉线会被挡住"，而不是只跑现状
    avail = avail_path or ROOT / "schemas" / "host_member_availability.json"
    unswept = unswept_path or ROOT / "schemas" / "unswept_account.json"
    res = {"floor": floor, "ok": False}
    if not avail.is_file() or not unswept.is_file():
        res["error"] = "缺证据（host_member_availability.json / unswept_account.json）"
        return res
    ev = json.loads(avail.read_text(encoding="utf-8"))
    cov = ev.get("coverage") or {}
    swept = int(cov.get("classes_swept") or 0)
    res["classes_swept"] = swept
    res["coverage_ok"] = swept >= floor
    acct = json.loads(unswept.read_text(encoding="utf-8"))
    want = set(cov.get("unswept_classes") or [])
    got = set(acct.get("classes") or {})
    res["unswept"] = len(want)
    res["unattributed"] = sorted(want - got)
    res["extra_rows"] = sorted(got - want)
    res["terminals_ok"] = not res["unattributed"] and not res["extra_rows"]
    bad = [c for c, row in (acct.get("classes") or {}).items()
           if not (row.get("terminal") and str(row.get("reason") or "").strip())]
    res["missing_terminal"] = sorted(bad)
    res["terminals_ok"] = res["terminals_ok"] and not bad
    try:
        tool = _load("reopen_r53", ROOT / "tools" / "sweep_reopen_check.py")
        dec = tool.decide(ev)
        res["reopen_reasons"] = dec.get("reasons") or []
        res["reopen_ok"] = not dec.get("reopen")
    except Exception as exc:  # noqa: BLE001
        res["reopen_error"] = type(exc).__name__ + ": " + str(exc)[:80]
        res["reopen_ok"] = False
    res["ok"] = bool(res["coverage_ok"] and res["terminals_ok"]
                     and res["reopen_ok"])
    return res


def check_guard() -> dict:
    """三态口径：无词表 → None；越界 → False；命中 → True。"""
    none_state = api.check_api_value("MeshingGroupSetting",
                                     "SetCompleteParallelFlag", "true", "bFlag")
    bad = api.check_api_value("MeshingGroupSetting", "ChangeMesher", "voxel",
                              "type")
    good = api.check_api_value("MeshingGroupSetting", "ChangeMesher", "poly",
                               "type")
    return {"none_state": none_state, "invalid": bad, "valid": good,
            "ok": none_state is None and bad is False and good is True}


def check_host_absent(catalog_path: Path | None = None,
                      avail_path: Path | None = None,
                      roots: list | None = None) -> dict:
    """R42-2：仓内**不得**引用宿主未实现的成员（引用了就是"注定调不通"）。

    路径可注入（R54-1）：自测要能拿**合成仓**验"引用了就挡住"。
    """
    cat = json.loads((catalog_path or CATALOG).read_text(encoding="utf-8"))
    # 只在**无歧义**时才判：同名成员若在别的类里是实现了的（如 `ImportCSV`），
    # 单看名字会把正常引用误判成"引用未实现成员"（第一版就这么假阳性了一次）
    all_members: dict = {}
    for info in cat["classes"].values():
        for kind in ("methods", "properties"):
            for mem, e in (info.get(kind) or {}).items():
                all_members.setdefault(mem, []).append(bool(e.get("host_absent")))
    # R43：普查证据同时要看**探针侧错误必须为 0**（error:* 是对象为空/过时，不得当结论）
    probe_errors = 0
    coverage: dict = {}
    av_path = avail_path or (ROOT / "schemas" / "host_member_availability.json")
    if av_path.is_file():
        ev = json.loads(av_path.read_text(encoding="utf-8"))
        coverage = ev.get("coverage") or {}
        probe_errors = sum(len(v.get("errors") or [])
                           for v in (ev.get("classes") or {}).values())
    absent = [mem for mem, flags in all_members.items() if all(flags)]
    if not absent:
        return {"absent_members": 0, "references": [], "coverage": coverage,
                "probe_errors": probe_errors, "ok": probe_errors == 0}
    hits = []
    scan_roots = roots or [ROOT / "tools", ROOT / "automation"]
    files = [p for r in scan_roots for p in r.glob("*.py")]
    files += [p for p in ROOT.glob("*.py")]
    for path in files:
        if path.name in ("extract_vb_api_scflow.py", "api_contract_check.py",
                         "dispatch_name_probe.py", "dispatch_account.py"):
            continue          # 生成器/门/探针自己会提到这些名字（发现它们的正是它们）
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        for mem in absent:
            if mem in src:
                hits.append(path.name + " -> " + mem)
    return {"absent_members": len(absent), "references": hits[:10],
            "reference_count": len(hits), "coverage": coverage,
            "probe_errors": probe_errors,
            "ok": not hits and probe_errors == 0}


CHECKS = (("catalog", check_catalog), ("ledger", check_ledger),
          ("host_absent", check_host_absent),
          ("account", check_account), ("bridge", check_bridge),
          ("corpus", check_corpus), ("guard", check_guard),
          ("convergence", check_sweep_convergence))


def _self_test_cases(tmp: Path) -> dict:
    """每一项的**合成反例**（R54-1）：喂假证据，必须 FAIL。

    每例只改一处、跑完即还原 ——"门能不能挡住"从此有总账，而不是只跑现状。
    """
    cases: dict = {}

    # ① catalog：假参数（参数名以引号开头）
    p = tmp / "cat_bad.json"
    p.write_text(json.dumps({"classes": {"X": {"methods": {"M": {
        "arguments": [{"type": "", "name": '"bogus'}],
        "dispatch_name": "M"}}}}}, ensure_ascii=False), encoding="utf-8")
    cases["catalog"] = lambda path=p: check_catalog(path)

    # ② ledger：有缺口却没终态
    p = tmp / "ledger_bad.json"
    p.write_text(json.dumps({"keys": [str(i) for i in range(18)],
                             "known_gaps": ["GAP.A"],
                             "known_gap_status": {}}, ensure_ascii=False),
                 encoding="utf-8")
    cases["ledger"] = lambda path=p: check_ledger(path)

    # ③ host_absent：仓内**引用了**无歧义的未实现成员
    r53 = tmp / "repo"
    (r53 / "schemas").mkdir(parents=True, exist_ok=True)
    (r53 / "tools").mkdir(parents=True, exist_ok=True)
    (r53 / "schemas" / "vb_api_catalog.json").write_text(json.dumps(
        {"classes": {"Y": {"methods": {"DeadMember": {
            "host_absent": True}}}}}, ensure_ascii=False), encoding="utf-8")
    (r53 / "schemas" / "host_member_availability.json").write_text(
        json.dumps({"coverage": {"classes_swept": 155, "classes_total": 199,
                                 "members_total": 1}, "classes": {}},
                   ensure_ascii=False), encoding="utf-8")
    (r53 / "tools" / "offender.py").write_text("x.DeadMember()\n",
                                               encoding="utf-8")
    cases["host_absent"] = lambda: check_host_absent(
        catalog_path=r53 / "schemas" / "vb_api_catalog.json",
        avail_path=r53 / "schemas" / "host_member_availability.json",
        roots=[r53 / "tools"])

    # ④ account：计数对不上（verdict + nyi ≠ total）
    p = tmp / "acct_bad.json"
    p.write_text(json.dumps({"counts": {"total": 10, "verdict": 3, "nyi": 3},
                             "rows": []}, ensure_ascii=False), encoding="utf-8")
    cases["account"] = lambda path=p: check_account(path)

    # ⑤ bridge：覆盖率掉到 0.5
    class _Cov:
        @staticmethod
        def report():
            return {"coverage": 0.5, "wrapped": 1, "unknown_wrapped_members": []}

    cases["bridge"] = lambda: _with_patched_load(
        lambda: _Cov, check_bridge)

    # ⑥ corpus：链接有"只有语料有"的漏项
    r54 = tmp / "repo2"
    (r54 / "_p12u_gate" / "r99").mkdir(parents=True, exist_ok=True)
    (r54 / "_p12u_gate" / "r99" / "corpus_diff_attr.json").write_text(
        json.dumps({"discovered": [{"parent": "P", "only_corpus": ["Q"]}]},
                   ensure_ascii=False), encoding="utf-8")
    cases["corpus"] = lambda: _with_patched_root(r54, check_corpus)

    # ⑦ guard：三态判据坏掉（越界却判 True）
    class _Api:
        @staticmethod
        def check_api_value(*_a):
            return True

    cases["guard"] = lambda: _with_patched_api(_Api, check_guard)

    # ⑧ convergence：覆盖率掉线
    p = tmp / "avail_bad.json"
    p.write_text(json.dumps({"coverage": {"classes_swept": 3,
                                          "classes_total": 199,
                                          "unswept_classes": []}},
                            ensure_ascii=False), encoding="utf-8")
    cases["convergence"] = lambda path=p: check_sweep_convergence(
        path, ROOT / "schemas" / "unswept_account.json")
    return cases


class _Patch:
    """临时替换模块级名字（跑完还原）。"""

    def __init__(self, **kw):
        self.kw = kw
        self.old: dict = {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.old[k] = globals()[k]
            globals()[k] = v
        return self

    def __exit__(self, *exc):
        for k, v in self.old.items():
            globals()[k] = v
        return False


def _with_patched_load(factory, fn):
    with _Patch(_load=lambda name, path: factory()):
        return fn()


def _with_patched_root(new_root: Path, fn):
    with _Patch(ROOT=new_root):
        return fn()


def _with_patched_api(stub, fn):
    with _Patch(api=stub):
        return fn()


def self_test() -> int:
    """跑 8 项合成反例：每项都必须 FAIL，否则这门是**摆设**。"""
    import tempfile
    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cases = _self_test_cases(tmp)
        for name, fn in CHECKS:
            case = cases.get(name)
            if case is None:
                rows.append((name, "MISSING", False))
                continue
            try:
                res = case()
                detected = not res.get("ok")
            except Exception as exc:  # noqa: BLE001
                detected = False
                res = {"error": type(exc).__name__ + ": " + str(exc)[:60]}
            rows.append((name, json.dumps(res, ensure_ascii=False)[:90],
                         detected))
    all_ok = True
    print("[self-test] 每项一个合成反例（必须 FAIL）")
    for name, detail, detected in rows:
        all_ok = all_ok and detected
        print(("  挡住  " if detected else "  放行  ") + name.ljust(12) + detail)
    print("SUMMARY: " + json.dumps({"self_test_passed": bool(all_ok),
                                    "checks": len(rows)}))
    return 0 if all_ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="API 面契约门")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--self-test", action="store_true",
                    help="R54-1：给 8 项各喂一个合成反例，必须全部 FAIL")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    results = {}
    all_ok = True
    for name, fn in CHECKS:
        try:
            res = fn()
        except Exception as exc:  # noqa: BLE001
            res = {"ok": False, "error": type(exc).__name__ + ": " + str(exc)}
        results[name] = res
        all_ok = all_ok and bool(res.get("ok"))
        print(("  PASS  " if res.get("ok") else "  FAIL  ") + name.ljust(10)
              + json.dumps({k: v for k, v in res.items() if k != "ok"},
                           ensure_ascii=False)[:150])
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({"all_ok": all_ok, "checks": results},
                                        ensure_ascii=False, indent=1),
                             encoding="utf-8")
    print("SUMMARY: " + json.dumps({"passed": bool(all_ok),
                                    "checks": len(results)}))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
