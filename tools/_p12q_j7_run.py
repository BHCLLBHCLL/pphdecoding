"""P12-Q J7 宿主在线验收：GUI 驱动路径带自愈通过 1 次批量（0 人工干预）。

J4（§21.7）钉死的事实：GUI 三路径接 FlowExecutor + ModalWatcher 自愈，
接线层已具备 0 人工干预能力。J7 实机验收 = 跑一轮真实批量，验证 J4 声明
在宿主在线时成立。

验收场景（3 VBS，覆盖简单→复杂）：

- **p12d_region_e2e**（域 10 面区域）：OpenProject(box.pph) →
  CreateFaceRegion → QueryFaceRegionByName → SaveProject。8 步，最简形态，
  验证基础 COM 通路 + ModalWatcher 不干扰正常流程。
- **p12e_mesh_e2e**（域 9 网格）：OpenProject(p12a_bam_e2e_out.pph) →
  MeshingGroup.CreateMesh → WaitForWorker → SaveProject。中等复杂度，
  验证 WaitForWorker 长时阻塞期间 ModalWatcher 持续轮询。
- **p12m_wiz_e2e**（域 10 MDL Wizard）：OpenProject(p12i_cv1b_out.pph) →
  ImportPatchAsCAD → BeginMDLWizard → 97 步向导序列 → EndMDLWizard →
  CreateOctree → SaveProject。110 步，GUI 密集，Exercise ModalWatcher
  自动dismiss "Initial Wizard" 模态（如出现）。

验收口径：3/3 VBS 经 FlowExecutor（watch_modals=True）执行，全部
outcome="ok" 且日志含 "end" 标记 + 所有 sNNN=0（err=0）。0 人工干预 =
无模态阻塞、无挂起、无手动重启宿主。

用法：``py tools/_p12q_j7_run.py``
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "_p12e_e2e_run", ROOT / "tools" / "_p12e_e2e_run.py")
p12e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p12e)


# ── 验收场景定义 ─────────────────────────────────────────────────────────────

SCENARIOS = [
    {
        "name": "p12d_region",
        "vbs": ROOT / "p12d_region_e2e.vbs",
        "log": ROOT / "p12d_region_e2e.log",
        "timeout": 120.0,
        "desc": "域 10 面区域（8 步，基础 COM 通路）",
    },
    {
        "name": "p12e_mesh",
        "vbs": ROOT / "p12e_mesh_e2e.vbs",
        "log": ROOT / "p12e_mesh_e2e.log",
        "timeout": 300.0,
        "desc": "域 9 网格创建（WaitForWorker 长时阻塞）",
    },
    {
        "name": "p12m_wiz",
        "vbs": ROOT / "p12m_wiz_e2e.vbs",
        "log": ROOT / "p12m_wiz_e2e.log",
        "timeout": 600.0,
        "desc": "域 10 MDL Wizard（110 步，GUI 密集）",
    },
]


def main():
    print("=" * 70)
    print("J7 宿主在线验收：GUI 驱动路径带自愈批量（0 人工干预）")
    print("=" * 70)
    print(f"场景数：{len(SCENARIOS)}")
    print(f"自愈模式：PPH_SELFHEAL={p12e.SELFHEAL}")
    print()

    results = []
    for i, sc in enumerate(SCENARIOS, 1):
        print(f"[{i}/{len(SCENARIOS)}] {sc['name']}: {sc['desc']}")
        print(f"  VBS: {sc['vbs'].name}")
        print(f"  LOG: {sc['log'].name}")

        if not sc["vbs"].exists():
            print(f"  SKIP: VBS 不存在")
            results.append({"name": sc["name"], "ok": False, "error": "vbs missing"})
            continue

        res = p12e.run_e2e(
            sc["name"],
            sc["vbs"],
            sc["log"],
            timeout=sc["timeout"],
            watch_modals=True,
        )

        run = res.get("run", {})
        verdict = res.get("verdict", {})
        ok = run.get("ok", False) and verdict.get("has_end", False) and verdict.get("bad", 1) == 0

        result = {
            "name": sc["name"],
            "ok": ok,
            "run_ok": run.get("ok"),
            "outcome": run.get("outcome"),
            "verdict": verdict,
        }
        results.append(result)

        status = "OK" if ok else "FAIL"
        print(f"  [{status}] run_ok={run.get('ok')} outcome={run.get('outcome')}")
        print(f"         verdict: end={verdict.get('has_end')} bad={verdict.get('bad')} total={verdict.get('total')}")
        if verdict.get("problems"):
            print(f"         problems: {verdict['problems']}")
        print()

    print("=" * 70)
    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    print(f"验收结果：{passed}/{total} 通过")
    print("=" * 70)

    summary_path = ROOT / "_p12q_j7_summary.json"
    summary_path.write_text(
        json.dumps({"passed": passed, "total": total, "results": results},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"摘要：{summary_path.name}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
