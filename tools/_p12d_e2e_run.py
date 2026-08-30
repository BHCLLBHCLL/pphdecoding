"""P12-D 冲刺 D 实机 e2e：域 10/4 权威接线经 rot 通道 + err=0 证据归档。

背景（P7-2 §6.3 负面矩阵）：文件层写 region 名（main.xml / part/ridge
MDL 名表 / GPH LS_SurfaceRegions / snapshot FACEGROUPSW 共 7 场景）
全部「打开 ok 但新名不注册」——权威名表在宿主内部，唯一正路是走宿主
API 建区。本编排即验证该路线：

- **snode**（域 10 CreateMDL True 项，需裸宿主——录制含 OpenCadFile，
  P12-A 实测已开工程会挂起；故批量时**最先跑**）：``box_scflow_mdl.vbs``
  2662 行录制回放 + SNode 注入（``CreateGroupPart``/``QuerySNodeByName``
  紧跟 OpenCadFile）+ ``MDLWizard_.CreateMDL`` 返回值捕获（``create_mdl=``
  info 行）+ VMDL.Save 显式导出（沿 P12-A 权威导出路径）。验收 =
  err=0 + gp_/sn_ alive + ``create_mdl=True`` + out 含 .gph。
- **region**（域 10 纪律闸门 §8.5 #10）：OpenProject(box.pph) →
  ``Doc.CreateFaceRegion("P12DRegion")`` →
  ``Doc.QueryFaceRegionByName("P12DRegion")``（**首次非 Nothing** 即
  闸门达成）+ 负面对照查询（``_p12d_absent``，预期 Nothing，仅记录）→
  SaveProject。验收 = err=0 + fr_/qr_ alive。
- **region_reopen**（§8.5 #10 持久腿）：OpenProject(region 产物) →
  再 Query 非 Nothing；离线扫 pph 成员字节定位宿主把权威名表落到
  哪个文件层成员（P7-2 未定位项的发现口）。
- **facet**（域 4 第一腿，无 OpenCadFile 挂起风险）：OpenProject(box)
  → ``Doc.CreateMeshingGroup`` → ``Doc.ImportCADAsFacet(box.x_t, MG)``
  → SaveProject。验收 = err=0 + mg4_ alive。
- **patch**（域 4 尾，STL patch 样本）：OpenProject(box) →
  ``Doc.ImportPatchAsCAD(PotatoChips.stl)``（2025.2 例程 exA17-10
  真实样本）→ SaveProject。验收 = err=0（sn5_ alive 记录性——
  包装返回可能 headless，沿 snode 探针口径）。

用法：``py tools/_p12d_e2e_run.py [snode|region|region_reopen|facet|patch|all]``
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import host_pipeline  # noqa: E402
from automation.vbs_bridge import build_vbs  # noqa: E402

BOX = ROOT / "box.pph"
XT = ROOT / "tests" / "box" / "box.x_t"
MDL_REC = ROOT / "box_scflow_mdl.vbs"

REGION_NAME = "P12DRegion"
REGION_ABSENT = "_p12d_absent"

REGION_VBS = ROOT / "p12d_region_e2e.vbs"
REGION_LOG = ROOT / "p12d_region_e2e.log"
REGION_OUT = ROOT / "p12d_region_e2e_out.pph"
REOPEN_VBS = ROOT / "p12d_region_reopen_e2e.vbs"
REOPEN_LOG = ROOT / "p12d_region_reopen_e2e.log"
SNODE_VBS = ROOT / "p12d_snode_e2e.vbs"
SNODE_LOG = ROOT / "p12d_snode_e2e.log"
SNODE_OUT = ROOT / "p12d_snode_e2e_out.pph"
SNODE_MDL = ROOT / "p12d_snode_part.mdl"
FACET_VBS = ROOT / "p12d_facet_e2e.vbs"
FACET_LOG = ROOT / "p12d_facet_e2e.log"
FACET_OUT = ROOT / "p12d_facet_e2e_out.pph"
PATCH_STL = Path("D:/training/cradle/CradleCFD_2025.2_scFLOW_Example_a"
                 "/Exercise/exA17/exA17-10/PotatoChips.stl")
PATCH_VBS = ROOT / "p12d_patch_e2e.vbs"
PATCH_LOG = ROOT / "p12d_patch_e2e.log"
PATCH_OUT = ROOT / "p12d_patch_e2e_out.pph"

D_DIR = ROOT / "_p12d_e2e"

_SET_RE = re.compile(r"^Set (\w+) = ")


def _write_ansi_vbs(actions, path, title):
    # 沿 P12-E：flow VBS 全落 ANSI（UTF-16LE 在部分宿主状态下挂起）。
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(build_vbs(actions, title), encoding="mbcs")
    return p


def logged_script(groups, log_path, title):
    """P5/P12-A/P12-E 模式：每条动作后写 ``sNNN=<Err.Number>``。"""
    lines = [
        "' " + title,
        "On Error Resume Next",
        'Set fso_ = CreateObject("Scripting.FileSystemObject")',
        'Set out_ = fso_.CreateTextFile("' + log_path.as_posix() + '", True)',
        'out_.WriteLine "start"',
    ]
    n = 0
    for _name, actions in groups:
        for act in actions:
            n += 1
            lines.append(act)
            lines.append('out_.WriteLine "s' + str(n).zfill(3)
                         + '=" & CStr(Err.Number)')
            lines.append("Err.Clear")
            m = _SET_RE.match(act)
            if m and m.group(1) != "out_":
                var = m.group(1)
                lines.append(
                    'out_.WriteLine "' + var.lower() + '_alive=" & '
                    'CStr(Not (' + var + ' Is Nothing)) & " err=" & '
                    'CStr(Err.Number)')
                lines.append("Err.Clear")
    lines += ['out_.WriteLine "end"', "out_.Close"]
    return lines


def verify_log(text):
    """全量 err=0 校验（沿 P12-E，info 增加 create_mdl）。"""
    total = err0 = 0
    problems = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line in ("start", "end"):
            continue
        m = re.match(r"^s\d+=(-?\d+)$", line)
        if m:
            code = int(m.group(1))
        else:
            m = re.search(r"(?:^|\s)err=(-?\d+)$", line)
            if not m:
                problems.append(line + " <unparsed>")
                continue
            code = int(m.group(1))
        total += 1
        if code == 0:
            err0 += 1
        else:
            problems.append(line)
    alive = {m.group(1): m.group(2)
             for m in re.finditer(r"^(\w+)_alive=(True|False)",
                                  text, re.MULTILINE)}
    info = {}
    for m in re.finditer(r"^(create_mdl|create_ret|wait_ret|xt_ec)"
                         r"=(\S+)", text, re.MULTILINE):
        info[m.group(1)] = m.group(2)
    return {"total": total, "err0": err0, "bad": total - err0,
            "problems": problems[:20], "alive": alive, "info": info,
            "has_end": "end" in text.splitlines()}


def run_e2e(name, vbs, log, timeout=600.0, end_wait=180.0, retries=5):
    run = host_pipeline.run_vbs_authoritative(vbs, timeout=timeout)
    print("[" + name + "] run: " + json.dumps(run, ensure_ascii=False))
    # rot 通道 ExecuteVBSWithFile 实测（2026-08-30 第二宿主实例）：
    # ① 慢 VBS（多分钟 OpenProject）未写完日志调用即返回；② 接纳/拒绝
    # 逐次不稳定——同一脚本同状态可能一次拒（False、零执行）一次纳，
    # 拒绝无内容规律（截断版拒、去行版纳），宿主忙时幻影 True（返回
    # True 但脚本从未执行）。故判据只能是日志 end 标记：拒绝即立即
    # 重试（retries 次内），接纳则轮询等待。
    def _log_done():
        return log.is_file() and "end" in log.read_text(
            encoding="utf-8", errors="replace").splitlines()

    deadline = time.time() + end_wait
    attempts = 1
    while not _log_done() and time.time() < deadline:
        if run.get("ok") or attempts > retries:
            time.sleep(2.0)
            continue
        print("[" + name + "] retry " + str(attempts) + "/" + str(retries)
              + " (rot 拒绝，零执行)")
        run = host_pipeline.run_vbs_authoritative(vbs, timeout=timeout)
        attempts += 1
    text = log.read_text(encoding="utf-8", errors="replace") \
        if log.is_file() else ""
    if not text:
        print("[" + name + "] LOG MISSING: " + str(log))
        return {"run": run, "log_missing": True}
    verdict = verify_log(text)
    print("[" + name + "] verdict: " + json.dumps(verdict,
                                                  ensure_ascii=False))
    return {"run": run, "verdict": verdict}


def gate(name, res, alive_need=(), min_checks=1):
    ok = (not res.get("log_missing")) and bool(res["run"].get("ok"))
    v = res.get("verdict") or {}
    ok = ok and v.get("bad") == 0 and v.get("total", 0) >= min_checks \
        and v.get("has_end")
    alive = v.get("alive", {})
    for key in alive_need:
        if alive.get(key) != "True":
            print("[" + name + "] ALIVE FAIL: " + json.dumps(alive))
            ok = False
    print("[" + name + "] GATE: " + ("PASS" if ok else "FAIL"))
    return ok


# ── 流程构造 ───────────────────────────────────────────────────────────────


def _read_recording(path: Path) -> list[str]:
    raw = path.read_bytes()
    text = raw.decode("utf-16-le", errors="replace") \
        if raw[:2] == b"\xff\xfe" else raw.decode("utf-8", errors="replace")
    return [ln.lstrip(chr(65279)) for ln in text.splitlines()]


def build_snode_groups():
    """域 10：BAM 录制回放 + SNode 注入 + CreateMDL 执行证据。

    变换沿 P12-A ``build_bam_groups``（``On Error Goto 0`` →
    ``Resume Next``、AFFaceter 前置、SaveProject 重定向 + VMDL.Save
    显式导出），追加三处注入：
    - OpenCadFile 行后 ``CreateGroupPart``（前探针）+ ``SN2_ =
      QuerySNodeByName("Part")``——录制 :275 自身即用该路线拿活
      SNode（P12-D 首跑实测：CreateGroupPart 在 OpenCadFile 点返回
      Nothing，Query 路线 SNode_ alive=True，故闸门走 SN2_）；
    - ``MDLWizard_.CreateMDL`` 改写为返回值捕获 + ``create_mdl=``
      info 行（首跑实测：CreateMDL 为 **void 方法**，赋值无错但
      Empty——catalog retval None 实机证实；验收改用产物证据
      .gph + VMDL.Save 的 MDL，info 行仅存档）；
    - CreateMDL 捕获后再补一次 ``CreateGroupPart``（后探针，wizard
      完成后的文档上下文）。
    """
    rec = _read_recording(MDL_REC)
    actions = []
    seen_begin_wiz = False
    for ln in rec:
        s = ln.strip()
        if s == "On Error Goto 0":
            actions.append("On Error Resume Next")
        elif s == "Doc_.OpenCadFile Param1_":
            actions.append(ln)
            actions.append('Set GP_ = Doc_.CreateGroupPart("'
                           + REGION_NAME + 'Group")')
            actions.append('Set SN2_ = Doc_.QuerySNodeByName("Part")')
        elif s == "MeshingGroup_.BeginMDLWizard" and not seen_begin_wiz:
            # AFFaceter 前置（P12-A 实测：无 faceter 时
            # FindAFFaceMatching RPC_E_SERVERFAULT 崩溃）。原行保留。
            seen_begin_wiz = True
            actions.append("Param1_ = True")
            actions.append("Set Proj_ = Doc_.GetProjectSetting")
            actions.append("Proj_.SetUseAFFacetter Param1_")
            actions.append(ln)
        elif s == "MDLWizard_.CreateMDL":
            actions.append("RetMdl_ = MDLWizard_.CreateMDL")
            actions.append('out_.WriteLine "create_mdl=" & CStr(RetMdl_) '
                           '& " err=" & CStr(Err.Number)')
            actions.append("Err.Clear")
            actions.append('Set GP2_ = Doc_.CreateGroupPart("'
                           + REGION_NAME + 'Group2")')
        elif s.startswith("Doc_.SaveProject"):
            actions.append("Set MGx_ = Doc_.QueryMeshingGroupByIndex(0)")
            actions.append("Set VMDLx_ = MGx_.GetVMDL")
            actions.append('RetVx_ = VMDLx_.Save("'
                           + SNODE_MDL.as_posix() + '")')
            actions.append('Doc_.SaveProject "' + SNODE_OUT.as_posix() + '"')
        else:
            actions.append(ln)
    return [("snode", actions)]


def build_region_groups():
    """域 10 纪律闸门：宿主 API 建区 → Query 非 Nothing。"""
    return [("region", [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        'Doc_.OpenProject "' + BOX.as_posix() + '", False',
        'Set FR_ = Doc_.CreateFaceRegion("' + REGION_NAME + '")',
        'Set QR_ = Doc_.QueryFaceRegionByName("' + REGION_NAME + '")',
        'Set QN_ = Doc_.QueryFaceRegionByName("' + REGION_ABSENT + '")',
        'Doc_.SaveProject "' + REGION_OUT.as_posix() + '"',
    ])]


def build_region_reopen_groups():
    """§8.5 #10 持久腿：Save 后重开再 Query 非 Nothing。"""
    return [("region_reopen", [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        'Doc_.OpenProject "' + REGION_OUT.as_posix() + '", False',
        'Set QR2_ = Doc_.QueryFaceRegionByName("' + REGION_NAME + '")',
    ])]


def build_facet_groups():
    """域 4 第一腿：ImportCADAsFacet typed 直调（无 OpenCadFile 风险）。"""
    return [("facet", [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        'Doc_.OpenProject "' + BOX.as_posix() + '", False',
        "Set MG4_ = Doc_.CreateMeshingGroup",
        'Doc_.ImportCADAsFacet "' + XT.as_posix() + '", MG4_',
        'Doc_.SaveProject "' + FACET_OUT.as_posix() + '"',
    ])]


def build_patch_groups():
    """域 4 尾：ImportPatchAsCAD（STL patch，2025.2 例程真实样本）。"""
    return [("patch", [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        'Doc_.OpenProject "' + BOX.as_posix() + '", False',
        'Set SN5_ = Doc_.ImportPatchAsCAD "' + PATCH_STL.as_posix() + '"',
        'Doc_.SaveProject "' + PATCH_OUT.as_posix() + '"',
    ])]


# ── 离线验收 ───────────────────────────────────────────────────────────────


def check_out_members(name, out: Path, need_suffix):
    import zipfile
    if not out.is_file():
        print("[" + name + "] OUT PPH missing: " + str(out))
        return False
    with zipfile.ZipFile(out) as zf:
        members = [n.filename for n in zf.infolist()]
    print("[" + name + "] out members: " + str(members))
    ok = True
    for suf in need_suffix:
        if not any(n.endswith(suf) for n in members):
            print("[" + name + "] OUT PPH missing " + suf)
            ok = False
    return ok


def check_region_landing(out: Path):
    """扫 pph 成员字节定位权威名表文件层落点（P7-2 未定位项发现口）。

    基线 = box.pph（不含 ``P12DRegion``）；产物中命中成员即宿主
    SaveProject 写回的权威落点。仅发现记录，不作 gate。
    """
    import zipfile
    hits = {}
    for label, p in (("baseline_box", BOX), ("region_out", out)):
        if not p.is_file():
            print("[region_scan] missing: " + str(p))
            continue
        with zipfile.ZipFile(p) as zf:
            for info in zf.infolist():
                data = zf.read(info.filename)
                cnt = data.count(REGION_NAME.encode("ascii"))
                if cnt:
                    hits.setdefault(label, {})[info.filename] = cnt
    print("[region_scan] " + json.dumps(hits, ensure_ascii=False))
    return hits


def main(argv):
    which = argv[0] if argv else "all"
    results = {}
    D_DIR.mkdir(exist_ok=True)

    def flow(name, groups, vbs_p, log_p, timeout=600.0, alive=(),
             min_checks=1, end_wait=180.0):
        vbs = _write_ansi_vbs(
            logged_script(groups, log_p, "pphdecoding P12-D " + name),
            vbs_p, title="pphdecoding P12-D " + name + " e2e")
        res = run_e2e(name, vbs, log_p, timeout=timeout, end_wait=end_wait)
        results[name] = gate(name, res, alive_need=alive,
                             min_checks=min_checks)
        return res

    # 批量顺序：snode 最先（录制含 OpenCadFile，需裸宿主，P12-A 实测
    # 已开工程会挂起）；region/facet 为工程内操作随时可插。
    if which in ("snode", "all"):
        res = flow("snode", build_snode_groups(), SNODE_VBS, SNODE_LOG,
                   timeout=1800.0, min_checks=300, end_wait=600.0,
                   alive=("sn2_",))
        if results["snode"]:
            v = res["verdict"]
            # CreateMDL 为 void（首跑实测：赋值无错但 Empty）——
            # 验收走产物：VMDL.Save 的 MDL + 内嵌 .gph。
            print("[snode] create_mdl=" + repr(v["info"].get("create_mdl"))
                  + " (void 方法实测记录，非验收键)")
            print("[snode] grouppart probes: pre=" + v["alive"].get("gp_", "?")
                  + " post=" + v["alive"].get("gp2_", "?")
                  + " (记录性，非 gate)")
            results["snode"] = results["snode"] and SNODE_MDL.is_file()
            if not SNODE_MDL.is_file():
                print("[snode] VMDL.Save MDL missing: " + str(SNODE_MDL))
            results["snode"] = results["snode"] and check_out_members(
                "snode", SNODE_OUT, [".gph"])

    if which in ("region", "all"):
        res = flow("region", build_region_groups(), REGION_VBS, REGION_LOG,
                   alive=("fr_", "qr_"))
        if results["region"]:
            v = res["verdict"]
            neg = v["alive"].get("qn_", "?")
            print("[region] negative control (" + REGION_ABSENT
                  + ") alive=" + neg + " (expect False)")
            if neg == "True":
                print("[region] WARNING: absent name resolved — "
                      "Query 语义与预期不符，须复核")
            results["region"] = results["region"] and check_out_members(
                "region", REGION_OUT, [])

    if which in ("region_reopen", "all"):
        res = flow("region_reopen", build_region_reopen_groups(),
                   REOPEN_VBS, REOPEN_LOG, alive=("qr2_",),
                   end_wait=600.0)
        if results["region_reopen"]:
            check_region_landing(REGION_OUT)

    if which in ("facet", "all"):
        flow("facet", build_facet_groups(), FACET_VBS, FACET_LOG,
             alive=("mg4_",))

    if which in ("patch", "all"):
        res = flow("patch", build_patch_groups(), PATCH_VBS, PATCH_LOG)
        v = res.get("verdict") or {}
        print("[patch] sn5_ alive=" + v.get("alive", {}).get("sn5_", "?")
              + " (记录性——包装返回可能 headless，沿 snode 探针口径)")

    print("SUMMARY: " + json.dumps(results, ensure_ascii=False))
    print("OVERALL: " + ("PASS" if all(results.values()) and results
                         else "FAIL"))
    (D_DIR / "p12d_run_summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return 0 if (results and all(results.values())) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
