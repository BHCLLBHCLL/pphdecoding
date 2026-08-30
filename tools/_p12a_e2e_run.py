"""P12-A 工作项3 e2e 实机执行：四项流程经 rot 权威通道跑通 + err=0 日志归档。

- A ridge：edit_ops Ridge（set/unset/recalc30）——fresh OpenCadFile(box.x_t)
  → CreateVMDL（Ridge 方法仅在虚拟部件模型上，solid MDL 工程 GetVMDL
  返回 Nothing，P12-A 实测）→ SaveProject 新 pph；
- B octant：edit_ops Octant（refine/merge/refine_rec/refine_num/
  refine_curv/show_all）——同名副本 ``_p12a_e2e/box.pph``（改名副本会
  触发 "Project name and PPH file name are different" 模态框，P12-A
  实测；内部工程名 box 见 main.xml <project><name>）；
- C bam：OpenCadFile(box.x_t) → parts_control → BAM Wizard 全步
  （BAM_WIZARD_ACTIONS，来自 box_scflow_mdl.vbs 录制）→ SaveProject
  新 pph——由 ``automation/pipeline_plan.py`` 生成器产出；
- D cad：OpenCadFile(STEP)（真实 STEP 文件）。

日志格式沿 P5 先例（p5_wrapping_e2e.log）：VBS 内 ``On Error Resume
Next`` + 每条动作后 ``out.WriteLine "sNNN=" & Err.Number`` + ``Err.Clear``；
对象取回行（``Set X_ = ...``）追加 ``x_alive`` 非空校验。验收：全量
err=0 + 关键对象 alive=True，日志/VBS/输出 pph 归档到仓库根目录。
ExecuteVBSWithFile 在脚本无错时返回 True（P12-A 实测，有错返回
False）——run.ok 与日志 err=0 双重验收。

用法：py tools/_p12a_e2e_run.py [ridge|octant|bam|cad|all]（默认 all）
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(r"d:\training\cgns\pphdecoding")
sys.path.insert(0, str(ROOT))

from automation import edit_ops, host_pipeline, pipeline_plan  # noqa: E402
from automation.vbs_bridge import write_vbs_file  # noqa: E402

BOX = ROOT / "box.pph"
BOX_XT = ROOT / "tests" / "box" / "box.x_t"
STEP = Path(r"D:\training\3dprint\FunHome-main\funHomeFan\cad"
            r"\FunDeskFan\base v7.step")

OCT_DIR = ROOT / "_p12a_e2e"          # 同名副本目录（stem=box=内部名）
OCT_SRC = OCT_DIR / "box.pph"
RIDGE_VBS = ROOT / "p12a_ridge_e2e.vbs"
RIDGE_LOG = ROOT / "p12a_ridge_e2e.log"
RIDGE_OUT = ROOT / "p12a_ridge_e2e_out.pph"
RIDGE_MDL = ROOT / "p12a_ridge_e2e_part.mdl"
OCT_VBS = ROOT / "p12a_octant_e2e.vbs"
OCT_LOG = ROOT / "p12a_octant_e2e.log"
OCT_OUT = ROOT / "p12a_octant_e2e_out.pph"
BAM_VBS = ROOT / "p12a_bam_e2e.vbs"
BAM_LOG = ROOT / "p12a_bam_e2e.log"
BAM_OUT = ROOT / "p12a_bam_e2e_out.pph"
BAM_MDL = ROOT / "p12a_bam_e2e_part.mdl"
CAD_VBS = ROOT / "p12a_cad_e2e.vbs"
CAD_LOG = ROOT / "p12a_cad_e2e.log"

_SET_RE = re.compile(r"^Set (\w+) = ")


def logged_script(groups, log_path, title):
    """P5 模式：每条动作后写 ``sNNN=<Err.Number>``，Set 行附 aliveness。"""
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


def build_ridge_groups():
    """Ridge 编辑组——fresh CAD + CreateVMDL（P12-A 探针实测全链）。

    虚拟阶段（CreateVMDL 后 IsPhaseVirtual=True）SaveProject 不内嵌
    .mdl 成员（diag15 钉死，与 BAM wizard VMDL 同一事实）；MDL 产物走
    权威显式导出 ``VMDL_.Save(RIDGE_MDL)``（末组 recalc 后、SaveProject
    前），pph 本体仅校验落盘存在性。
    """
    cad = BOX_XT.as_posix()
    set_acts = edit_ops.ridge_actions(cad, "set", create_vmdl=True,
                                      save_path=RIDGE_OUT)
    unset_acts = edit_ops.ridge_actions(cad, "unset", save_path=RIDGE_OUT)
    recalc_acts = edit_ops.ridge_actions(cad, "recalc", angle=30.0,
                                         save_path=RIDGE_OUT)
    export = ['RetV_ = VMDL_.Save("' + RIDGE_MDL.as_posix() + '")']
    recalc_body = recalc_acts[5:]
    recalc_body = recalc_body[:-1] + export + [recalc_body[-1]]
    return [
        ("ridge_set", set_acts),
        ("ridge_unset", unset_acts[5:]),
        ("ridge_recalc30", recalc_body),
    ]


def build_octant_groups():
    """Octant 编辑组——同名 box 副本（含八叉树）。"""
    src = OCT_SRC.as_posix()

    def body(actions):
        return actions[5:]

    return [
        ("oct_refine", edit_ops.octant_actions(src, "refine")),
        ("oct_merge", body(edit_ops.octant_actions(src, "merge"))),
        ("oct_refine_rec", body(edit_ops.octant_actions(
            src, "refine_rec", level=1, range_=1))),
        ("oct_refine_num", body(edit_ops.octant_actions(
            src, "refine_num", level=1, num=2))),
        ("oct_refine_curv", body(edit_ops.octant_actions(
            src, "refine_curv",
            rmin=[-1000.0, -1000.0, -1000.0],
            rmax=[1000.0, 1000.0, 1000.0],
            lowerlimit=0.01))),
        ("oct_show_all", body(edit_ops.octant_actions(src, "show_all"))),
    ]


def build_bam_groups():
    """BAM 全流程组——完整回放 box_scflow_mdl.vbs 录制（2662 行）。

    P12-A 实测（diag11-14）钉死的事实链：
    - EndMDLWizard 的 VMDL 不经 SaveProject 内嵌为 ``_part.mdl``
      （main.xml 无 ``<mdl>`` 段；DeleteMDL 返回 False、CreateVMDL/
      RecognizeClosedVolume 均无法触发内嵌序列化）；
    - 权威 MDL 导出路径 = ``VMDL.Save(path)``（手册 VMDL_Class，实测
      返回 True、1.7MB 产物）——在尾部 SaveProject 前显式调用；
    - pph 内嵌产物（meshinggroup1.gph + meshinggroup1_ridge.mdl）需
      完整回放（wizard×2 + CreateOctree + CreateMeshMonitor +
      WaitForWorker）才有；纯 wizard（diag11）零 mdl 产物。

    回放变换：``On Error Goto 0`` → ``On Error Resume Next``（防运行
    时错误弹 GUI 模态卡死，diag11 先例）；尾部 SaveProject 重定向到
    BAM_OUT 并前置 VMDL.Save 显式导出（BAM_MDL）。
    """
    raw = (ROOT / "box_scflow_mdl.vbs").read_bytes()
    text = raw.decode("utf-16-le", errors="replace") \
        if raw[:2] == b"\xff\xfe" else raw.decode("utf-8", errors="replace")
    rec = [ln.lstrip(chr(65279)) for ln in text.splitlines()]
    actions = []
    seen_begin_wiz = False
    for ln in rec:
        s = ln.strip()
        if s == "On Error Goto 0":
            actions.append("On Error Resume Next")
        elif s == "MeshingGroup_.BeginMDLWizard" and not seen_begin_wiz:
            # 前置 AF faceter（防御性）：录制自身在 :185（MeshingGroup
            # Setting）与 :371（ProjectSetting）均设 SetUseAFFacetter=
            # True，但均在 wizard 启动后；FindAFFaceMatching（:481）无
            # faceter 时 RPC_E_SERVERFAULT（P12-A 实测，e2e 首跑崩溃），
            # 故 wizard 启动前先钉一次。原 BeginMDLWizard 行必须保留
            # （回归修复：prelude 曾把它整个替换掉，导致 GetMDLWizard
            # 全程返回 Nothing、后续 MDLWizard_ 调用批量 424）。
            seen_begin_wiz = True
            actions.append("Param1_ = True")
            actions.append("Set Proj_ = Doc_.GetProjectSetting")
            actions.append("Proj_.SetUseAFFacetter Param1_")
            actions.append(ln)
        elif s.startswith("Doc_.SaveProject"):
            actions.append("Set MGx_ = Doc_.QueryMeshingGroupByIndex(0)")
            actions.append("Set VMDLx_ = MGx_.GetVMDL")
            actions.append('RetVx_ = VMDLx_.Save("'
                           + BAM_MDL.as_posix() + '")')
            actions.append('Doc_.SaveProject "' + BAM_OUT.as_posix() + '"')
        else:
            actions.append(ln)
    return [("bam", actions)]


def build_cad_groups():
    """OpenCadFile(STEP) 组——真实 STEP 文件经权威通道导入。"""
    actions = [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        'Doc_.OpenCadFile "' + STEP.as_posix() + '"',
        "Set Env_ = Doc_.GetEnv",
        "Set Conditions_ = Doc_.GetConditions",
        "Set MeshingGroup_ = Doc_.QueryMeshingGroupByIndex(0)",
    ]
    return [("cad", actions)]


def verify_log(text):
    """全量 err=0 校验：每行 sNNN=<n> 或 ... err=<n>，n 必须为 0。"""
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
    has_end = "end" in text.splitlines()
    return {"total": total, "err0": err0, "bad": total - err0,
            "problems": problems[:20], "alive": alive, "has_end": has_end}


def run_e2e(name, vbs, log, timeout=600.0):
    run = host_pipeline.run_vbs_authoritative(vbs, timeout=timeout)
    print("[" + name + "] run: " + json.dumps(run, ensure_ascii=False))
    text = log.read_text(encoding="utf-8", errors="replace") \
        if log.is_file() else ""
    if not text:
        print("[" + name + "] LOG MISSING: " + str(log))
        return {"run": run, "log_missing": True}
    verdict = verify_log(text)
    print("[" + name + "] verdict: "
          + json.dumps(verdict, ensure_ascii=False))
    return {"run": run, "verdict": verdict}


def check(name, res, alive_need, out=None, out_need=None):
    """验收：run.ok + 全量 err0 + has_end + alive 全 True + 产物成员。"""
    v = res.get("verdict") or {}
    if res.get("log_missing"):
        return False
    ok = bool(res["run"].get("ok")) and v.get("bad") == 0 \
        and v.get("total", 0) > 0 and v.get("has_end")
    if not ok:
        return False
    alive = v.get("alive", {})
    for key in alive_need:
        if alive.get(key) != "True":
            print("[" + name + "] ALIVE FAIL: " + json.dumps(alive))
            return False
    if out is not None:
        if not out.is_file():
            print("[" + name + "] OUT PPH missing")
            return False
        import zipfile
        with zipfile.ZipFile(out) as zf:
            members = [n.filename for n in zf.infolist()]
        print("[" + name + "] out members: " + str(members))
        for suffix in out_need or ():
            if not any(n.endswith(suffix) for n in members):
                print("[" + name + "] OUT PPH missing " + suffix)
                return False
    return True


def main(argv):
    which = argv[0] if argv else "all"
    ok = True

    if which in ("ridge", "all"):
        vbs = write_vbs_file(
            logged_script(build_ridge_groups(), RIDGE_LOG,
                          "pphdecoding P12-A ridge e2e (rot)"),
            RIDGE_VBS, title="pphdecoding P12-A ridge e2e")
        res = run_e2e("ridge", vbs, RIDGE_LOG)
        if not check("ridge", res, ["vmdl_"], out=RIDGE_OUT):
            ok = False
        if not RIDGE_MDL.is_file() or RIDGE_MDL.stat().st_size < 100_000:
            print("[ridge] explicit VMDL.Save MDL missing/too small: "
                  + str(RIDGE_MDL))
            ok = False
        else:
            print("[ridge] explicit MDL: "
                  + str(RIDGE_MDL.stat().st_size) + " bytes")

    if which in ("octant", "all"):
        OCT_DIR.mkdir(exist_ok=True)
        shutil.copyfile(BOX, OCT_SRC)
        vbs = write_vbs_file(
            logged_script(build_octant_groups(), OCT_LOG,
                          "pphdecoding P12-A octant e2e (rot)"),
            OCT_VBS, title="pphdecoding P12-A octant e2e")
        res = run_e2e("octant", vbs, OCT_LOG)
        if not check("octant", res, ["octree_"], out=None):
            ok = False
        else:
            shutil.copyfile(OCT_SRC, OCT_OUT)
            import zipfile
            with zipfile.ZipFile(OCT_OUT) as zf:
                members = [n.filename for n in zf.infolist()]
            print("[octant] out members: " + str(members))
            if not any(n.endswith(".oct") for n in members):
                print("[octant] OUT PPH missing .oct")
                ok = False

    if which in ("bam", "all"):
        vbs = write_vbs_file(
            logged_script(build_bam_groups(), BAM_LOG,
                          "pphdecoding P12-A BAM full-flow e2e (rot)"),
            BAM_VBS, title="pphdecoding P12-A BAM full-flow e2e")
        res = run_e2e("bam", vbs, BAM_LOG, timeout=1200.0)
        if not check("bam", res, ["mdlwizard_", "vmdlx_"], out=BAM_OUT,
                     out_need=[".gph", "_ridge.mdl"]):
            ok = False
        if not BAM_MDL.is_file() or BAM_MDL.stat().st_size < 100_000:
            print("[bam] explicit VMDL.Save MDL missing/too small: "
                  + str(BAM_MDL))
            ok = False
        else:
            print("[bam] explicit MDL: " + str(BAM_MDL.stat().st_size)
                  + " bytes")

    if which in ("cad", "all"):
        if not STEP.is_file():
            print("[cad] STEP not found: " + str(STEP))
            ok = False
        else:
            vbs = write_vbs_file(
                logged_script(build_cad_groups(), CAD_LOG,
                              "pphdecoding P12-A OpenCadFile STEP e2e (rot)"),
                CAD_VBS, title="pphdecoding P12-A OpenCadFile STEP e2e")
            res = run_e2e("cad", vbs, CAD_LOG)
            if not check("cad", res, ["doc_", "env_", "conditions_"]):
                ok = False

    print("OVERALL: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

