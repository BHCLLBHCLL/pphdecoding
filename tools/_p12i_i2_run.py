"""P12-I I2：批量自愈验收（DEV_PLAN §20.1/§20.4）。

连续 N 轮（默认 2）P12-E 六流批量（wrap/mesh/disc/overset/reopen/xt）
0 人工干预：单次冷启动后全部流程经 hang-watchdog 自愈执行器跑完，
modal/hang 全自动处置；断点续跑台账 ``_p12i/i2_batch_state.json``
（中断后重跑自动跳过已完成 (round, flow)）。

用法：``py tools/_p12i_i2_run.py [rounds] ``
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import host_boot  # noqa: E402

I2_DIR = ROOT / "_p12i"
STATE = I2_DIR / "i2_batch_state.json"
SUMMARY = I2_DIR / "i2_run_summary.json"
FLOWS = ["bam", "wrap", "mesh", "disc", "overset", "reopen", "xt"]


def load_p12e():
    spec = importlib.util.spec_from_file_location(
        "p12e_run", str(ROOT / "tools" / "_p12e_e2e_run.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_state() -> dict:
    if STATE.is_file():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"done": {}}


def save_state(st: dict) -> None:
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1),
                     encoding="utf-8")


def main(argv) -> int:
    rounds = int(argv[0]) if argv else 2
    I2_DIR.mkdir(exist_ok=True)
    st = load_state()

    t0 = time.time()
    pid = host_boot.cold_boot()
    print("[i2] cold boot host pid=" + str(pid))

    run = load_p12e()
    results = {}
    for r in range(1, rounds + 1):
        for flow in FLOWS:
            key = "r" + str(r) + ":" + flow
            if st["done"].get(key) == "pass":
                print("[i2] skip (resume) " + key)
                results[key] = True
                continue
            rc = run.main([flow])
            ok = rc == 0
            results[key] = ok
            st["done"][key] = "pass" if ok else "fail"
            save_state(st)
            print("[i2] " + key + " -> " + ("PASS" if ok else "FAIL"))

    all_ok = bool(results) and all(results.values())
    summary = {"rounds": rounds, "flows": FLOWS, "results": results,
               "all_ok": all_ok,
               "elapsed_s": round(time.time() - t0, 1)}
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    print("[i2] SUMMARY: " + json.dumps(summary, ensure_ascii=False))
    print("[i2] OVERALL: " + ("PASS" if all_ok else "FAIL"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
