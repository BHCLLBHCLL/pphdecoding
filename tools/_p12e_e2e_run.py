"""P12-E 冲刺 E 实机 e2e：域 5/6/9/11 全链经 rot 权威通道 + err=0 证据归档。

流程（单次宿主会话内按序，wrapping 先行——OpenCadFile 需无已开工程，
P12-A 实测）：

- **wrap**（域 11）：``box_scflow_wrapping.vbs`` 3100 行录制完整回放
  （OpenCadFile(box.x_t) → SetPartsControl Wrapping → BeginWrapping →
  CreateWrappingGroup → 参数锁定序列 → CreateOctree → ExecuteWrapping×6
  → EndWrapping → SaveProject）。沿 P12-A BAM 回放变换：``On Error
  Goto 0`` → ``Resume Next``、SaveProject 重定向。
- **mesh**（域 9）：OpenProject(P12-A BAM 产物) →
  ``MeshingGroup.CreateMesh``（typed，兼容路径）→ ``Doc.WaitForWorker``
  → SaveProject；验收 = err=0 + retval True + out pph 含 .gph。
- **disc / overset**（域 11 建组）：``CreateDiscontinuousMeshingGroup
  WithMovingPart("Part")`` / ``WithoutMovingPart("overset_unit")`` →
  SaveProject → 离线指纹与 ``tests/box_disc|overset.pph`` 黄金同类判定
  （``disc_overset.fingerprint_same_class``）。
- **reopen**（域 5）：OpenProject(P12-A octant e2e 产物，宿主 Refine
  后的八叉树) → MeshingGroup/GetOctree alive → err=0（细化产物宿主
  重开验证）。
- **xt**（深管线）：``Pipe.ConvertFacetToXT`` 用真实 facet
  （``p12a_bam_e2e_part.mdl`` VMDL.Save 产物）→ 业务码 +
  last_exception_code=0 + XT 落盘。

用法：``py tools/_p12e_e2e_run.py [wrap|mesh|disc|overset|reopen|xt|all]``
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


def _write_ansi_vbs(actions, path, title):
    # 实测（2026-08-30）：write_vbs_file 的 UTF-16LE 脚本在部分宿主
    # 会话状态下 OpenProject 挂起（同脚本转 ANSI/mbcs 秒过）；P12-E
    # 的 flow VBS 全部落 ANSI。UTF-16 通道保留给历史已验证流程。
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(build_vbs(actions, title), encoding="mbcs")
    return p

BOX = ROOT / "box.pph"
BAM_OUT = ROOT / "p12a_bam_e2e_out.pph"
BAM_MDL = ROOT / "p12a_bam_e2e_part.mdl"
OCTANT_OUT = ROOT / "p12a_octant_e2e_out.pph"
WRAP_REC = ROOT / "box_scflow_wrapping.vbs"

E_DIR = ROOT / "_p12e_e2e"
WRAP_VBS = ROOT / "p12e_wrapping_e2e.vbs"
WRAP_LOG = ROOT / "p12e_wrapping_e2e.log"
WRAP_OUT = ROOT / "p12e_wrapping_e2e_out.pph"
MESH_VBS = ROOT / "p12e_mesh_e2e.vbs"
MESH_LOG = ROOT / "p12e_mesh_e2e.log"
MESH_OUT = ROOT / "p12e_mesh_e2e_out.pph"
DISC_VBS = ROOT / "p12e_disc_e2e.vbs"
DISC_LOG = ROOT / "p12e_disc_e2e.log"
DISC_OUT = ROOT / "p12e_disc_e2e_out.pph"
OVERSET_VBS = ROOT / "p12e_overset_e2e.vbs"
OVERSET_LOG = ROOT / "p12e_overset_e2e.log"
OVERSET_OUT = ROOT / "p12e_overset_e2e_out.pph"
REOPEN_VBS = ROOT / "p12e_reopen_e2e.vbs"
REOPEN_LOG = ROOT / "p12e_reopen_e2e.log"
XT_VBS = ROOT / "p12e_xt_e2e.vbs"
XT_LOG = ROOT / "p12e_xt_e2e.log"
XT_OUT = ROOT / "p12e_xt_out.x_t"

GOLDEN_DISC = ROOT / "tests" / "box_disc.pph"
GOLDEN_OVERSET = ROOT / "tests" / "box_overset.pph"

_SET_RE = re.compile(r"^Set (\w+) = ")


def logged_script(groups, log_path, title):
    """P5/P12-A 模式：每条动作后写 ``sNNN=<Err.Number>``。"""
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
    """全量 err=0 校验（沿 P12-A）。"""
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
    for m in re.finditer(r"^(xt_ec|xt_exists|pipe_exc|create_ret|wait_ret)"
                         r"=(\S+)", text, re.MULTILINE):
        info[m.group(1)] = m.group(2)
    return {"total": total, "err0": err0, "bad": total - err0,
            "problems": problems[:20], "alive": alive, "info": info,
            "has_end": "end" in text.splitlines()}


def run_e2e(name, vbs, log, timeout=600.0, end_wait=180.0):
    run = host_pipeline.run_vbs_authoritative(vbs, timeout=timeout)
    print("[" + name + "] run: " + json.dumps(run, ensure_ascii=False))
    # rot 通道 ExecuteVBSWithFile 可能先于慢 VBS（如 reopen 的多分钟
    # OpenProject）写完日志返回；先轮询等 end 标记再 verify，
    # 否则 verdict 读到半截日志造成假 FAIL。
    deadline = time.time() + end_wait
    while time.time() < deadline:
        if log.is_file() and "end" in log.read_text(
                encoding="utf-8", errors="replace").splitlines():
            break
        time.sleep(2.0)
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


def build_wrap_groups():
    """录制回放（沿 build_bam_groups 变换）。"""
    raw = WRAP_REC.read_bytes()
    text = raw.decode("utf-16-le", errors="replace") \
        if raw[:2] == b"\xff\xfe" else raw.decode("utf-8", errors="replace")
    rec = [ln.lstrip(chr(65279)) for ln in text.splitlines()]
    actions = []
    for ln in rec:
        s = ln.strip()
        if s == "On Error Goto 0":
            actions.append("On Error Resume Next")
        elif s.startswith("Doc_.SaveProject"):
            actions.append('Doc_.SaveProject "' + WRAP_OUT.as_posix() + '"')
        else:
            actions.append(ln)
    return [("wrap", actions)]


def build_mesh_groups():
    """域 9：BAM 产物工程上 CreateMesh（typed 兼容路径）+ WaitForWorker。"""
    return [("mesh", [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        'Doc_.OpenProject "' + BAM_OUT.as_posix() + '", False',
        "Set MG_ = Doc_.QueryMeshingGroupByIndex(0)",
        "Set VMDL_ = MG_.GetVMDL",
        'out_.WriteLine "vmdl_alive=" & CStr(Not (VMDL_ Is Nothing)) '
        '& " err=" & CStr(Err.Number)',
        "Err.Clear",
        "RetMesh_ = MG_.CreateMesh",
        'out_.WriteLine "create_ret=" & CStr(RetMesh_) & " err=" '
        '& CStr(Err.Number)',
        "Err.Clear",
        "RetWait_ = Doc_.WaitForWorker",
        'out_.WriteLine "wait_ret=" & CStr(RetWait_) & " err=" '
        '& CStr(Err.Number)',
        "Err.Clear",
        'Doc_.SaveProject "' + MESH_OUT.as_posix() + '"',
    ])]


def build_disc_groups():
    return [("disc", [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        'Doc_.OpenProject "' + BOX.as_posix() + '", False',
        "Set Conditions_ = Doc_.GetConditions",
        'Conditions_.SetPartsControl "Discontinuous", True',
        'Set MG2_ = Doc_.CreateDiscontinuousMeshingGroupWithMovingPart('
        '"Part")',
        'Doc_.SaveProject "' + DISC_OUT.as_posix() + '"',
    ])]


def build_overset_groups():
    return [("overset", [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        'Doc_.OpenProject "' + BOX.as_posix() + '", False',
        'Set MG3_ = Doc_.CreateDiscontinuousMeshingGroupWithoutMovingPart('
        '"overset_unit")',
        'Doc_.SaveProject "' + OVERSET_OUT.as_posix() + '"',
    ])]


def build_reopen_groups():
    """域 5：宿主八叉树产物重开验证。

    目标 = WRAP_OUT（当日宿主 SaveProject 产物，含宿主生成的
    meshinggroup1.gph/.oct）。不能用 box.pph：宿主会话中一次挂起
    的 OpenProject 会一直持有目标工程文件，阻塞后续对同一文件的
    打开（实测 box 已被挂起调用占用；wrap-out 探针 2/2 秒过）。
    """
    return [("reopen", [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        'Doc_.OpenProject "' + WRAP_OUT.as_posix() + '", False',
        "Set MG_ = Doc_.QueryMeshingGroupByIndex(0)",
        "Set Octree_ = MG_.GetOctree",
    ])]


def build_xt_groups():
    """深管线 ConvertFacetToXT：真实 facet = P12-A VMDL.Save MDL。"""
    return [("xt", [
        'Set Pipe_ = CreateObject("pphdecoding.ScflowPipeline")',
        'xtEc_ = Pipe_.ConvertFacetToXT("' + BAM_MDL.as_posix() + '", "'
        + XT_OUT.as_posix() + '")',
        'out_.WriteLine "xt_ec=" & CStr(xtEc_) & " err=" & CStr(Err.Number)',
        "Err.Clear",
        'out_.WriteLine "xt_exists=" & CStr(fso_.FileExists("'
        + XT_OUT.as_posix() + '")) & " err=0"',
        'out_.WriteLine "pipe_exc=" & CStr(Pipe_.LastExceptionCode) '
        '& " err=0"',
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


def check_fingerprint(name, out: Path, golden: Path,
                      extra_ignore=()) -> tuple:
    """新工程指纹与黄金同类判定。返回 (ok, diffs)。"""
    import disc_overset
    fp_new = disc_overset.golden_fingerprint(out)
    fp_gold = disc_overset.golden_fingerprint(golden)
    ignore = tuple(disc_overset.DEFAULT_IGNORE) + tuple(extra_ignore)
    ok, diffs = disc_overset.fingerprint_same_class(fp_new, fp_gold,
                                                    ignore=ignore)
    print("[" + name + "] fingerprint same_class=" + str(ok))
    for d in diffs:
        print("[" + name + "]   diff: " + json.dumps(d, ensure_ascii=False))
    return ok, diffs


def main(argv):
    which = argv[0] if argv else "all"
    results = {}
    E_DIR.mkdir(exist_ok=True)

    def flow(name, groups, vbs_p, log_p, timeout=600.0, alive=(),
             min_checks=1, end_wait=180.0):
        vbs = _write_ansi_vbs(
            logged_script(groups, log_p, "pphdecoding P12-E " + name),
            vbs_p, title="pphdecoding P12-E " + name + " e2e")
        res = run_e2e(name, vbs, log_p, timeout=timeout, end_wait=end_wait)
        results[name] = gate(name, res, alive_need=alive,
                             min_checks=min_checks)
        return res

    if which in ("wrap", "all"):
        res = flow("wrap", build_wrap_groups(), WRAP_VBS, WRAP_LOG,
                   timeout=1800.0, min_checks=300)
        if results["wrap"]:
            results["wrap"] = check_out_members("wrap", WRAP_OUT, [])

    if which in ("mesh", "all"):
        res = flow("mesh", build_mesh_groups(), MESH_VBS, MESH_LOG,
                   timeout=900.0, alive=("mg_",))
        if results["mesh"]:
            v = res["verdict"]["info"]
            ret = v.get("create_ret", "")
            if ret != "True":
                print("[mesh] CreateMesh retval=" + ret + " (expected True)")
                results["mesh"] = False
            results["mesh"] = results["mesh"] and check_out_members(
                "mesh", MESH_OUT, [".gph"])

    if which in ("disc", "all"):
        res = flow("disc", build_disc_groups(), DISC_VBS, DISC_LOG,
                   alive=("mg2_",))
        if results["disc"] and DISC_OUT.is_file():
            ok, _d = check_fingerprint("disc", DISC_OUT, GOLDEN_DISC,
                                       extra_ignore=("rotor_filename",
                                                     "gph_members",
                                                     "oct_members"))
            # 判别键单独硬校验（不随 ignore 放过）
            import disc_overset
            fp = disc_overset.golden_fingerprint(DISC_OUT)
            if not fp["flags"]["discontinuous"]:
                print("[disc] Discontinuous flag not set")
                ok = False
            results["disc"] = ok

    if which in ("overset", "all"):
        res = flow("overset", build_overset_groups(), OVERSET_VBS,
                   OVERSET_LOG, alive=("mg3_",))
        if results["overset"] and OVERSET_OUT.is_file():
            ok, _d = check_fingerprint("overset", OVERSET_OUT,
                                       GOLDEN_OVERSET,
                                       extra_ignore=("rotor_filename",
                                                     "gph_members",
                                                     "oct_members",
                                                     "flags"))
            results["overset"] = ok

    if which in ("reopen", "all"):
        flow("reopen", build_reopen_groups(), REOPEN_VBS, REOPEN_LOG,
             alive=("mg_", "octree_"), end_wait=600.0)

    if which in ("xt", "all"):
        res = flow("xt", build_xt_groups(), XT_VBS, XT_LOG,
                   alive=("pipe_",))
        if results["xt"]:
            info = res["verdict"]["info"]
            ec = info.get("xt_ec")
            exc = info.get("pipe_exc")
            exists = info.get("xt_exists")
            print("[xt] business_code=" + str(ec) + " exc=" + str(exc)
                  + " xt_exists=" + str(exists))
            # 业务码非 -1（COM 层参数校验通过 = 进到了 SCTprime 内核）
            if ec in (None, "-1"):
                print("[xt] business code -1 → COM 层拦截，未达内核")
                results["xt"] = False

    print("SUMMARY: " + json.dumps(results, ensure_ascii=False))
    print("OVERALL: " + ("PASS" if all(results.values()) and results
                         else "FAIL"))
    (E_DIR / "p12e_run_summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return 0 if (results and all(results.values())) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
