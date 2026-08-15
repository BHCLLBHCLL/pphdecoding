#!/usr/bin/env python3
"""pskernel V37 新增导出（V35 手册未收录的 104 个 PK_*）逆向补充。

2025.2 的 pskernel = Parasolid V37.01.153（FileVersion + sch_37102 + 运行期
PKBody3 modeller version 3701153）。V35 手册（q-solid）为最接近的公开文档，
映射覆盖 1101/1204 个 PK_*；剩余 103 个为 V36/V37 新增（lattice/cellular
建模、FRAME、PARTITION/REGION 嵌入、TOPOL 连通性、BODY_slice 等）。

本模块用三层手段补全这些导出：

* 家族归类：按前缀/命名约定（base / _r_f / _cb_r_f 配对，FRAME/LATTICE/
  PARTITION/REGION/TOPOL 家族）+ V37 节点类型表（FRAME 等来自 sch_37102）；
* 反汇编参数推断：x64 入口前 ~40 条指令中 4 个寄存器参数（rcx/rdx/r8/r9）
  与栈参数（第 5 个起 [rsp+0x28]）的读取计数，字节读（dl/r8b）= logical/char，
  并对已文档化函数（PK_PART_transmit 等）先做校准；
* 经验调用验证：getter 类函数（PK_SESSION_ask_cellular_guise /
  PK_REGION_ask_type / PK_LATTICE_ask_type）在子进程中直接调用实测 rc。

已知限制（如实标注）：类型级签名（各指针的具体结构体）只能给出形态
（pointer/int/logical/byte），完整 o_t 结构布局仍需逐函数深挖或官方文档。
"""

from __future__ import annotations

import re
import struct
import subprocess
import sys
from pathlib import Path

import pskernel_abi as abi

PSK37 = Path("C:/Program Files/Cradle/CradleCFD2025.2/"
             "Programs_x64/pskernel.dll")

# 家族归类（V37-only 导出 → 家族名）
FAMILIES = {
    "FRAME": "PK_FRAME_",
    "LATTICE": "PK_LATTICE_",
    "PARTITION": "PK_PARTITION_",
    "REGION": "PK_REGION_",
    "TOPOL": "PK_TOPOL_",
    "BODY_slice": "PK_BODY_slice",
    "BODY_cellular": ("PK_BODY_is_cellular", "PK_BODY_is_disjoint",
                       "PK_BODY_make_patterned", "PK_BODY_enlarge",
                       "PK_BODY_create_implicit", "PK_BODY_ask_frames"),
    "FACE": "PK_FACE_",
    "ASSEMBLY": "PK_ASSEMBLY_",
    "GEOM": "PK_GEOM_",
    "LBALL": "PK_LBALL_",
    "MARK": "PK_MARK_",
    "SESSION": "PK_SESSION_",
    "TRANSF": "PK_TRANSF_",
}


def v37_only_exports(dll=PSK37) -> list[str]:
    """V37-only PK_* 导出（相对 2023 V34.1；2023 无同名者即 V36/V37 新增）。"""
    p23 = Path(r"C:\Program Files\Cradle\CradleCFD2023\Programs_x64\pskernel.dll")
    names37 = {e.name for e in abi.dump_exports(str(dll))}
    names34 = {e.name for e in abi.dump_exports(str(p23))} if Path(p23).exists() \
        else set()
    return sorted(x for x in names37 - names34 if x.startswith("PK_"))


def classify(name: str) -> str:
    for fam, pat in FAMILIES.items():
        if isinstance(pat, str) and name.startswith(pat):
            return fam
        if isinstance(pat, tuple) and name in pat:
            return fam
    return "other"


def base_name(name: str) -> str:
    """PK_XXX_r_f / PK_XXX_cb_r_f → PK_XXX（无基函数时返回原样）。"""
    if name.endswith("_cb_r_f"):
        return name[:-len("_cb_r_f")]
    if name.endswith("_r_f"):
        return name[:-len("_r_f")]
    return name


def _load_capstone():
    import capstone
    return capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)


def _exports_map(dll=PSK37) -> dict[str, int]:
    return {e.name: e.rva for e in abi.dump_exports(str(dll))}


def _rva2off(data, rva):
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    coff = pe_off + 4
    nsec = struct.unpack_from("<H", data, coff + 2)[0]
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    sec_off = opt + opt_size
    for i in range(nsec):
        s = sec_off + i * 40
        vsize, vaddr, rawsize, rawaddr = struct.unpack_from("<4I", data, s + 8)
        if vaddr <= rva < vaddr + max(vsize, rawsize):
            return rawaddr + (rva - vaddr)
    return None


def infer_arg_usage(dll=PSK37, name: str = None, rva: int = None,
                    max_insns: int = 60) -> dict:
    """入口参数使用推断：{argc, byte_args, ptr_args, stack_args}。

    规则（x64 入口、首个 call 前的保存段，已对文档化函数校准）：

    * 4 个寄存器参数 = rcx/rdx/r8/r9 家族，取各槽位**首次被读**（保存/比较），
      后续内部复用不再计入；
    * 栈参数：入口 [rsp+0x28/0x30/...] 直接读，或 rbp 帧下
      [rbp+0xY] 经 prologue 帧偏移换算回入口 rsp（Y-frame_off 映射）；
    * 字节读（dl/r8b/cl 家族）= logical/char 形参。
    """
    data = Path(str(dll)).read_bytes()
    if rva is None:
        rva = _exports_map(dll)[name]
    fo = _rva2off(data, rva)
    md = _load_capstone()
    slots = {"1": ("rcx", "ecx", "cx", "cl"), "2": ("rdx", "edx", "dx", "dl"),
             "3": ("r8", "r8d", "r8w", "r8b"), "4": ("r9", "r9d", "r9w", "r9b")}
    slot_seen = set()
    stack_seen = set()
    byte_seen = set()
    frame_off = 0
    rsp_moved = False
    n = 0
    for insn in md.disasm(data[fo:fo + 0x400], rva):
        n += 1
        if n > max_insns:
            break
        ops = insn.op_str
        m = insn.mnemonic
        if m == "call":
            break
        if m == "sub" and "rsp" in ops:
            rsp_moved = True
        # prologue 帧偏移：lea rbp, [rsp - 0xX] / [rax - 0xX]
        if m == "lea" and "rbp" in ops and "- 0x" in ops:
            mm = re.search(r"- 0x([0-9a-f]+)", ops)
            if mm:
                frame_off = int(mm.group(1), 16)
        # 寄存器参数首读（参数寄存器 = 源侧；cmp/test 两侧皆可）
        src = ops.split(",")[1].strip() if "," in ops else ops
        if m in ("cmp", "test"):
            src = ops
        for slot, regs in slots.items():
            if slot in slot_seen:
                continue
            if m in ("mov", "movzx", "movsxd", "test", "cmp", "add", "lea",
                     "and", "or", "xor") and any(r in src for r in regs):
                slot_seen.add(slot)
                if m in ("movzx", "mov") and any(
                        r in src for r in ("dl", "r8b", "cl")):
                    byte_seen.add(slot)
        # 栈参数直接读（rsp 未变的前几条）——只算"读"（内存操作数在源侧）
        mem_src = None
        if m in ("mov", "movzx", "movsxd", "lea") and "," in ops:
            mem_src = ops.split(",")[1].strip()
        elif m in ("cmp", "test") and "," in ops:
            mem_src = ops.split(",")[0].strip()
        if mem_src and not rsp_moved and \
                (mem_src.startswith("[rsp") or mem_src.startswith("[rax")):
            for off, idx in ((0x28, 5), (0x30, 6), (0x38, 7), (0x40, 8),
                             (0x48, 9), (0x50, 10), (0x58, 11), (0x60, 12)):
                if re.search(r"\+ 0x%x\]" % off, mem_src) or \
                        re.search(r"\+ %d\]" % off, mem_src):
                    stack_seen.add(idx)
        # rbp 帧下的栈参数：[rbp + 0xY] 源读，Y-frame_off = 入口 rsp 偏移
        mm = re.search(r"\[rbp \+ 0x([0-9a-f]+)\]", mem_src or "")
        if mm and frame_off:
            incoming = int(mm.group(1), 16) - frame_off
            if 0x28 <= incoming <= 0x60:
                stack_seen.add((incoming - 0x28) // 8 + 5)
    argc = 0
    if "1" in slot_seen:
        argc = 1
    if "2" in slot_seen:
        argc = 2
    if "3" in slot_seen:
        argc = 3
    if "4" in slot_seen:
        argc = 4
    if stack_seen:
        argc = max(argc, max(stack_seen))
    return {"argc": argc, "byte_args": sorted(byte_seen),
            "ptr_args": [], "stack_args": sorted(stack_seen),
            "reg_args": sorted(slot_seen)}


def calibrate(dll=PSK37) -> dict:
    """用已文档化签名校准推断器（V35 手册的 argc 对拍）。"""
    known = {
        "PK_PART_transmit": 4,
        "PK_ENTITY_ask_class": 2,
        "PK_VERTEX_ask_point": 2,
        "PK_BODY_ask_faces": 2,
        "PK_SESSION_start": 1,
        "PK_PART_receive": 4,
    }
    out = {}
    for name, expect in known.items():
        rva = _exports_map(dll)[name]
        got = infer_arg_usage(dll, rva=rva)
        out[name] = {"expected": expect, "got": got["argc"],
                     "ok": got["argc"] >= expect}
    return out


def supplement(dll=PSK37, cache_dir=None) -> dict[str, dict]:
    """V37-only 导出的补充接口信息：家族 + 基名配对 + 推断参数。

    返回 {name: {family, base, r_f, argc, byte_args, stack_args, note}}。
    """
    only = v37_only_exports(dll)
    usage = {}
    rvas = _exports_map(dll)
    for name in only:
        usage[name] = infer_arg_usage(dll, rva=rvas[name])
    out = {}
    for name in only:
        fam = classify(name)
        base = base_name(name)
        note = ""
        if name.endswith("_cb_r_f"):
            note = "callback 变体（基函数 + 回调函数指针 + 上下文，栈参数多 2）"
        elif name.endswith("_r_f") and base in only:
            note = "reentrant/frustrum 变体（基函数参数 + PK_FRUSTUM_t *）"
        out[name] = {
            "family": fam,
            "base": base,
            "r_f": name.endswith("_r_f"),
            "cb": name.endswith("_cb_r_f"),
            **usage[name],
            "note": note,
        }
    return out


def report_supplement(supp: dict) -> str:
    from collections import Counter
    fams = Counter(v["family"] for v in supp.values())
    r_f = sum(1 for v in supp.values() if v["r_f"])
    cb = sum(1 for v in supp.values() if v["cb"])
    lines = [f"V37 新增导出补充：{len(supp)} 个",
             f"家族分布：{dict(fams.most_common())}",
             f"_r_f 变体 {r_f} / _cb_r_f 变体 {cb}",
             f"经验验证 {len(V37_VERIFIED)} 个："
             + ", ".join(f"{k}(rc={v['rc']})" for k, v in
                         V37_VERIFIED.items()),
             "参数推断（argc 为反汇编上界；ask 家族约定 = 实体 + 输出指针）："]
    for name, v in sorted(supp.items()):
        lines.append(f"  {name:32s} {v['family']:12s} argc={v['argc']}"
                     f" byte={v['byte_args'] or '-'}"
                     f" stack={v['stack_args'] or '-'} {v['note']}")
    return "\n".join(lines)


# ── 经验调用验证（子进程隔离，崩溃安全；结论见 V37_VERIFIED）───────

# 实测结论（2025.2 pskernel，ps_facet2_nodes 会话，默认 modeling guise）：
# * PK_SESSION_ask_cellular_guise(PK_LOGICAL_t *)：rc=0，guise=27110(0x69E6)，
#   签名 1 个输出指针参数确认；
# * PK_FACE_ask_type / PK_REGION_ask_type / PK_REGION_ask_lattices：以标准
#   ask 家族签名（实体, *out / 实体, *n, *arr）调用**不崩溃**，rc=5022
#   （o_t_version/guise 门禁——cellular 家族函数需 PK_SESSION_start 的
#   cellular guise，默认会话被拒）。签名形态与 ask 家族约定一致，待
#   cellular-guise 会话下复核。
V37_VERIFIED = {
    "PK_SESSION_ask_cellular_guise": {
        "signature": "PK_ERROR_code_t PK_SESSION_ask_cellular_guise("
                     "PK_LOGICAL_t *guise)",
        "rc": 0, "note": "默认会话实测 rc=0，guise=27110(0x69E6)",
    },
    "PK_FACE_ask_type": {
        "signature": "PK_ERROR_code_t PK_FACE_ask_type("
                     "PK_FACE_t face, PK_FACE_type_t *type)",
        "rc": 5022, "note": "ask 家族签名；5022=guise 门禁（cellular 会话待复核）",
    },
    "PK_REGION_ask_type": {
        "signature": "PK_ERROR_code_t PK_REGION_ask_type("
                     "PK_REGION_t region, PK_REGION_type_t *type)",
        "rc": 5022, "note": "同上",
    },
    "PK_REGION_ask_lattices": {
        "signature": "PK_ERROR_code_t PK_REGION_ask_lattices("
                     "PK_REGION_t region, int *n_lattices, "
                     "PK_LATTICE_t **lattices)",
        "rc": 5022, "note": "同上",
    },
}


def schema_diff() -> dict:
    """sch_34101（V34.1）vs sch_37102（V37）节点类型演进。"""
    import parasolid
    s34 = parasolid.load_schema(
        r"C:\Program Files\Cradle\CradleCFD2023\Programs_x64\Schemas\sch_34101.sch_txt")
    s37 = parasolid.load_schema(
        r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\Schemas\sch_37102.sch_txt")
    new = {t: s37[t].name for t in sorted(set(s37) - set(s34))}
    changed = {}
    for t in sorted(set(s37) & set(s34)):
        f34 = [(f.name, f.type, f.n_elts) for f in s34[t].fields]
        f37 = [(f.name, f.type, f.n_elts) for f in s37[t].fields]
        if f34 != f37:
            changed[t] = s37[t].name
    return {"new_types": new, "changed_types": changed}
