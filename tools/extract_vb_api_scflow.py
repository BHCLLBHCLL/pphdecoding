#!/usr/bin/env python3
"""从 scFLOW 官方 VB 接口手册 HTML 提取 scFLOWpre/Kicker 类目录。

源：CradleCFD2025.2 ``Manuals/scFLOW/HTML/VB_Interface_eng``（MediaWiki
导出）。每个方法在 HTML 中为::

    <h3><span class="mw-headline" id="Name">Name</span></h3>
    <dl><dd>retval=doc.OpenProject(path, flag)</dd></dl>
    <dl><dd><table class="vbmethod"> ... </table></dd></dl>

表内行：``[Explanation]``（说明）、``[Argument]``（参数，每参数一行：
``(VARIANT) name`` / ``:`` / 描述）、``[Return Value]``（返回值）。

表内续行（首格为空）有三型，须分开处理（R30-3 实测）：

* **枚举取值行**（``"poly" / Polyhedral mesher``）——同一行可能塞多值；
* **Note 行**（``(Note) Refer to GetXxx ...``）——多为「取值见某 getter」的
  交叉引用，是取到词表的唯一线索；
* **参数续行**（``(BSTR)type / : / desc``）——才是真正的下一个参数。

输出 ``schemas/vb_api_catalog.json``：类 → 方法/属性 → 签名、说明、
参数表（``arguments[].values`` 带取值词表）、返回值。该目录是 typed COM 桥
（``scflowpre_api.py``）与 VBS 生成器共用的权威 API 面。

用法::

    python tools/extract_vb_api_scflow.py            # 全量提取
    python tools/extract_vb_api_scflow.py --list     # 仅类清单统计
"""

from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANUAL = Path(r"C:\Program Files\Cradle\CradleCFD2025.2\Manuals\scFLOW"
              r"\HTML\VB_Interface_eng")
OUT = ROOT / "schemas" / "vb_api_catalog.json"

PROGID = "scFLOWpre_Bx64net.Application.2025"

# scFLOWpre Preprocessor 类（含 150+ Cond* 子类）+ Kicker 三类。
# 不提取 Post/Solver/Monitor/scConverter/LFileView/SmartBlades（非本仓域）。
_FILE_PATTERNS = [
    ("Scf_vb_Preprocessor_*_Class.html", ""),
    ("Scf_vb_Preprocessor_*_class.html", ""),
    ("Scf_vb_Kicker_Application_class.html", "Kicker."),
    ("Cmn_vb_Kicker_ApplicationLaunchSetting_class.html", "Kicker."),
    ("Cmn_vb_Kicker_LicenseStatus_class.html", "Kicker."),
]
# 手册文件名中类名的正则捕获组
_NAME_RE = re.compile(r"^Scf_vb_Preprocessor_(.+?)_[Cc]lass(?:_Supplement)?\.html$"
                      r"|^(?:Scf|Cmn)_vb_Kicker_(.+?)_[Cc]lass\.html$")

_H2 = re.compile(r'<h2><span class="mw-headline"[^>]*>([^<]+)</span></h2>')
_H3 = re.compile(r'<h3><span class="mw-headline"[^>]*>([^<]+)</span></h3>')
_TAG = re.compile(r"<[^>]+>")
_TR = re.compile(r"<tr>(.*?)</tr>", re.S)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
# 手册两种表格并存：Utility 等类用 <table class="vbmethod">，Doc 等类用裸 <table>
_TABLE = re.compile(
    r'<dl><dd><table(?: class="vbmethod")?>(.*?)</table></dd></dl>', re.S)
_SIGNATURE = re.compile(r"<dl><dd>([^<]*(?:<(?!/?dd)[^<]*)*)</dd></dl>")
_NOTE = re.compile(r"<dl><dd><b>\(Note\)</b>(.*?)</dd></dl>", re.S)
_ARG_CELL = re.compile(r"^\(([^)]+)\)\s*(.+)$")
#: 表头归一（R32-3 实测变体）：`[Return Value]` 4617 行 vs `[Return value]` **4280 行**
#: —— 旧实现只认大写 V，等于**静默丢掉近一半方法的返回值**（连同其取值词表）。
#: 另有 `[Arguments]`(50) / `[Return]`(50) / 拼写错 `[Argiment]` `[Resturn Value]`
#: `[Return Value]]` `[Explnation]` `[Explanetion]` `[xplanation]` 与日文 `[引数]`
#: `[戻り値]` `[戻り値/Return value]`；`[Description]` 只出现在类级表，方法块内为 0。
#: 签名里的真实成员名（h3 标题可能拼错：实测 41 处标题名 ≠ 签名名，如
#: `CreateDiscontinuousMeshingGroupWitouthMovingPart` 标题 vs `…WithoutMovingPart` 签名）。
#: 不一致时写进 `signature_name`，让调用侧能用**宿主真正认的**名字。
_SIG_MEMBER = re.compile(r"\.([A-Za-z_]\w*)\s*[\( ]")
_HEAD_EXPL = re.compile(r"xpl|説明", re.I)
_HEAD_ARG = re.compile(r"argu|argi|引数", re.I)
_HEAD_RET = re.compile(r"return|resturn|戻り値", re.I)


def _head_kind(head: str):
    """表头 → 'expl' / 'arg' / 'ret' / None（大小写、拼写、日文变体都归一）。"""
    if not head.startswith("["):
        return None
    if _HEAD_EXPL.search(head):
        return "expl"
    if _HEAD_ARG.search(head):
        return "arg"
    if _HEAD_RET.search(head):
        return "ret"
    return None
#: 取值格：手册用 "poly" 标注；全角引号 ”GVEL” 是手册笔误，一并接住。
#: 用字符类拼接而非转义串 —— 免掉 \s / \" 混写带来的 SyntaxWarning。
_QUOTES = "\"\u201c\u201d"
#: 取值格 → 「"value" [: 描述]」连续切分（同格多值时靠 finditer 逐个取，
#: 不能用 split —— split 会把匹配到的取值本身吃掉）
_ENUM_DESC = re.compile(
    "[" + _QUOTES + "]([^" + _QUOTES + "]+)[" + _QUOTES
    + "]\\s*:?\\s*([^" + _QUOTES + "]*)")
#: 描述内嵌取值（R31-2 实测 116 行）：第一个引号之前必须出现**类型标记**
#: （(string)/(BSTR)/(VARIANT)）或 label 词（mode/type/…），否则是散文
#: （如 `Use "cycle_interval" to get cycle interval`）——实测 118 行被此条挡住。
_DESC_PREFIX = re.compile(
    r"(?:\((?:BSTR|VARIANT|string)[^)]*\)"
    r"|\b(?:mode|type|edition|format|method|option|key|setting|flag)\b)"
    r"[\s\[:,，(]*(?:\[[^\]]*)?$", re.I)
#: R32-3 增补两条（把误拒的真词表捞回来，实测各带一批）：
#: ① 描述里**任何位置**先出现完整类型标记 —— 手册常把取值写在条件从句之后
#:    （`Direction of region (string) If coordinate definition type is plane
#:    "positive_side" …`）；`Color (string "0xAABBGGRR")` 这类格式提示的
#:    右括号在引号**之后**，因此不匹配。
_DESC_MARKER_ANY = re.compile(r"\((?:BSTR|VARIANT|string)[^)]*\)", re.I)
#: 格式提示（**不是**取值）：颜色串 `"0xAABBGGRR"` 之类。R32-3 第一版放宽后
#: 混进 63 条（`Doc.AddTemporaryDrawingObject*` 的颜色占位），故：格式提示一律剔除。
_FORMAT_HINT = re.compile(r"0x[0-9A-Fa-f]{4,}|AABBGGRR")
#: Note 段落是散文：`(Note) Failure occurs in the following cases: "not in part mode,"`
#: 这类引号串不是取值（R32-3 实测污染了 `Doc.SewSheets` 的返回值）。
_NOTE_PROSE = re.compile(r"\(Note\)", re.I)
#: ② 括号内逗号分隔的取值列表（`("none", "low", "medium", "high")`；
#: 手册还有全角括号/全角逗号变体：`（"summary", "detail", "solverComand"）`）。
_DESC_PAREN_LIST = re.compile(
    "[\\(（]\\s*[" + _QUOTES + "][^" + _QUOTES + "]+[" + _QUOTES
    + "]\\s*(?:[,，]\\s*[" + _QUOTES + "][^" + _QUOTES + "]+[" + _QUOTES
    + "]\\s*)+[,，)\\)）]")
#: 整数取值行：手册把 0/1/2 型枚举写成「0 Initial calculation 1 Restart…」
_NUM_DESC = re.compile(r"(\d+)\s*:?\s*([^\d]*?)(?=\s*\d+\s*:?\s|$)")
#: 漏闭合引号（手册 "IRBN）：取值取到首个空白，余下当描述
_ENUM_OPEN = re.compile(
    "[" + _QUOTES + "]([^\\s" + _QUOTES + "]+)\\s*(.*)$")
_NOTE_ROW = re.compile(r"\(Note\)\s*(.*)", re.S)
_NOTE_HREF = re.compile(r'href="#([A-Za-z_]\w+)"')


def _strip(s: str) -> str:
    s = _TAG.sub(" ", s)
    s = htmllib.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_method_block(body: str) -> dict:
    """解析一个 h3 方法块：签名 + vbmethod 表 + (Note)。"""
    entry: dict = {}
    m = _SIGNATURE.search(body)
    if m:
        entry["signature"] = _strip(m.group(1))
    nm = _NOTE.search(body)
    if nm:
        entry["note"] = _strip(nm.group(1))
    tm = _TABLE.search(body)
    if not tm:
        return entry
    mode = None
    for row in _TR.findall(tm.group(1)):
        cells = [_strip(c) for c in _TD.findall(row)]
        if not cells:
            continue
        head = cells[0]
        kind = _head_kind(head)
        if kind == "expl":
            mode = "expl"
            entry["explanation"] = " ".join(c for c in cells[1:] if c)
        elif kind == "arg":
            mode = "arg"
            if len(cells) >= 4:
                _push_arg(entry, cells[1], cells[3])
        elif kind == "ret":
            mode = "ret"
            if len(cells) >= 4:
                _push_arg(entry, cells[1], cells[3], ret=True)
        elif head.startswith("(Note)"):
            nm2 = _NOTE_ROW.match(head)
            if nm2:
                entry.setdefault("note", nm2.group(1).strip())
        elif mode in ("arg", "ret") and len(cells) >= 3 \
                and _ARG_CELL.match(head):
            # 无 [Argument] 表头的参数行：cells[0] 直接是 (TYPE) name
            _push_arg(entry, head, cells[-1], ret=(mode == "ret"))
        elif not head:
            _parse_continuation(entry, mode, cells, row)
    return entry


def _parse_continuation(entry: dict, mode, cells: list, row: str) -> None:
    """续行（首格为空）分三类：Note 行 / 枚举取值行 / 参数续行。

    手册实测分布（359 份 HTML）：取值行 836 行 4 格、634 行 3 格、12 行
    同格多值、7 行 5 格；Note 行 545 行。旧解析把取值行当成**新参数**
    （name 带引号、type 空）——全库 1205 条假参数、239 个方法受影响，
    正是 R29 只能靠猜取值词表（"octree"/"voxel" 全猜错）的原因。
    """
    first = next((c for c in cells if c), "")
    nm = _NOTE_ROW.match(first)
    if nm:
        entry.setdefault("note", nm.group(1).strip())
        href = _NOTE_HREF.search(row)
        if href:
            entry.setdefault("note_ref", href.group(1))
        return
    vals = _enum_values(cells[1]) if len(cells) > 1 else []
    if not vals and len(cells) > 1 and not any(cells[2:]) \
            and _NUM_DESC.match(cells[1].strip()):
        vals = _numeric_values(cells[1])
    if vals:
        tail = [c for c in cells[2:] if c]
        if tail:
            vals[-1]["description"] = tail[-1]
        _push_values(entry, mode, vals)
        return
    if mode == "arg" and len(cells) >= 3:
        # 参数续行：[空] [(VARIANT) name] [:] [desc]
        _push_arg(entry, cells[0] or cells[1], cells[-1])


def _enum_values(cell: str) -> list:
    """取值格 → [{"value", "description"}]（同格多值也拆开）。"""
    text = cell.strip()
    if text and text[0] in _QUOTES and text.count(text[0]) % 2:
        # 漏闭合引号（Conditions.GetFPHVariableOutput 的 "IRBN）：取到首个空白
        m = _ENUM_OPEN.match(text)
        return ([{"value": m.group(1).strip(),
                  "description": m.group(2).strip()}] if m else [])
    return [{"value": m.group(1).strip(),
             "description": m.group(2).strip()}
            for m in _ENUM_DESC.finditer(text)]


def _clean_desc(s: str) -> str:
    """取值描述清理：去掉包裹括号/方括号与尾随逗号、冒号。"""
    out = (s or "").strip().strip("[]").strip().rstrip(",").strip()
    return out.strip("()").strip().rstrip(":").strip()


def _desc_values(text: str) -> list:
    """取值写在**参数描述**里的行型（R31-2）。

    手册有两种「描述即词表」写法：

      * `Type of connection (string)["default" (default), "connect" (connect)]`
      * `License mode "hpc" : HPC edition "lt" : LT edition`

    判定条件（实测标定，见 `_DESC_PREFIX`）：第一个引号之前必须出现类型标记或
    label 词；否则是散文（`Use "cycle_interval" to get cycle interval`），不得当词表。
    纯取值行（整格就是 `"poly"`）归 `_parse_continuation` 管，这里直接放行。
    """
    if not text.strip() or text.strip()[0] in _QUOTES:
        return []
    if _NOTE_PROSE.search(text):
        return []
    head = text.split('"')[0] if '"' in text else text
    found = list(_ENUM_DESC.finditer(text))
    # 放宽分支要求 ≥2 个取值：单个引号串多半是格式提示（`Color as "0xAABBGGRR"`）
    if not (_DESC_PREFIX.search(head)
            or (_DESC_MARKER_ANY.search(head) and len(found) >= 2)
            or _DESC_PAREN_LIST.search(text)):
        return []
    out = []
    for m in found:
        val, desc = m.group(1).strip(), _clean_desc(m.group(2))
        if _FORMAT_HINT.search(val + " " + desc):
            continue
        out.append({"value": val, "description": desc})
    return out


#: 手册**笔误**取值 → 宿主实测拼写（R33-1）。证据 = 宿主自己写出的 main.xml：
#: `<stability_type><name>protectd1</name>`（语料 151 工程 / 755 处命中）、
#: `<name>orthogonality</name>`（151 处）—— 手册把它们写成了 `"'protectd1"`
#: （引号内多一个单引号）。修正时保留 `manual_value`，便于回溯"手册原文如此"。
_VALUE_FIXES = {
    "'protectd1": ("protectd1", "宿主 main.xml <name>protectd1</name>，755 处"),
    "'orthogonality": ("orthogonality", "宿主 main.xml <name>orthogonality</name>，151 处"),
}

#: 宿主语料**补充**的取值（手册未列）。键 = (类, 成员, 参数名或 "return")，
#: 条目形如 `{"value", "description", "source": "host-corpus"}`。
#:
#: **当前为空**：R33-3 拿 151 个宿主工程语料对拍 stability 家族，手册与语料
#: **完全一致**（`protectd1`/`protectd2`，各 151 处 `<name>` + 302 处元素标签），
#: 没有漏项 —— 机制保留备用（单测用合成条目验证它真的会写入）。
_VALUE_ADDENDA: dict = {
    ("Conditions", "GetPresetStabilityParamGeom", "param"): [
        {"value": "elem_volume",
         "description": "（宿主语料：stabilitygeom_type）",
         "source": "host-corpus"}],
    # ↓ R34-1：`--auto` 对拍（151 工程）发现的**名字同源**漏项，共 12 条。
    # 只收「容器名 ↔ 成员名同源」的链接；仅取值重叠的链接只作提示、不入库
    # （实测 loop_eq_param / equa_start_param 都会"匹配"到 GetUpwdParam）。
    ("CondBoundaryElectric", "GetBoundaryType", "return"): [
        {"value": "battery", "description": "（宿主语料：boundary_type）",
         "source": "host-corpus"},
        {"value": "clear", "description": "（宿主语料：boundary_type）",
         "source": "host-corpus"},
        {"value": "infinite_elements",
         "description": "（宿主语料：boundary_type）",
         "source": "host-corpus"}],
    ("ClosedVolume", "GetConnectionType", "return"): [
        {"value": "not_connect",
         "description": "（宿主语料：connection_type；手册另有 disconnect）",
         "source": "host-corpus"}],
    ("CondBoundaryWallThermal", "GetContactType", "return"): [
        {"value": "glue", "description": "（宿主语料：contact_type）",
         "source": "host-corpus"}],
    ("CondParticleGeneration", "GetConversionType", "return"): [
        {"value": "none", "description": "（宿主语料：conversion_type）",
         "source": "host-corpus"}],
    ("Conditions", "GetNextParam", "key"): [
        {"value": "CAVI", "description": "（宿主语料：next_param）",
         "source": "host-corpus"},
        {"value": "CMBV", "description": "（宿主语料：next_param）",
         "source": "host-corpus"},
        {"value": "CONC_VAPOR", "description": "（宿主语料：next_param）",
         "source": "host-corpus"}],
    ("CondBoundaryWallThermal", "GetOutsideType", "return"): [
        {"value": "saturated_humidity",
         "description": "（宿主语料：outside_type）",
         "source": "host-corpus"}],
    ("CondDiscontinuous", "GetProjectionType", "return"): [
        {"value": "surface", "description": "（宿主语料：projection_type）",
         "source": "host-corpus"}],
    # R36-2：`upwd_param` 容器（仅"包含"关系）经**取值词汇唯一性**归因 ——
    # 语料 12 条全是 `eq_*` 形状，而全库只有 `GetUpwdOptionParamForEquation.eq`
    # 是 `eq_*` 词汇（`GetUpwdParam.key` 是 MOM/ENERGY 大写码），故认定为同一族。
    ("Conditions", "GetUpwdOptionParamForEquation", "eq"): [
        {"value": "eq_comb", "description": "（宿主语料：upwd_param）",
         "source": "host-corpus"},
        {"value": "eq_dsol_cont", "description": "（宿主语料：upwd_param）",
         "source": "host-corpus"},
        {"value": "eq_dsol_e", "description": "（宿主语料：upwd_param）",
         "source": "host-corpus"},
        {"value": "eq_dsol_mom", "description": "（宿主语料：upwd_param）",
         "source": "host-corpus"}],
    ("Conditions", "GetSolvParam", "key"): [
        {"value": "eq_comb", "description": "（宿主语料：solv_param）",
         "source": "host-corpus"}],
    # ↓ R35-2：由「仅取值重叠」候选按**词干同源**归因后补入（`--attribute`）。
    # 词干只是"包含"关系的不入库（如 upwd_param → GetUpwdOptionParamForEquation）。
    ("CondInitial", "GetRegionType", "return"): [
        {"value": "all", "description": "（宿主语料：region_type）",
         "source": "host-corpus"},
        {"value": "point_group", "description": "（宿主语料：region_type）",
         "source": "host-corpus"},
        {"value": "region", "description": "（宿主语料：region_type）",
         "source": "host-corpus"},
        {"value": "surface_region", "description": "（宿主语料：region_type）",
         "source": "host-corpus"}],
    ("CondBoundaryDiffusiveSpecies", "GetTransferType", "return"): [
        {"value": "adiabatic", "description": "（宿主语料：transfer_type）",
         "source": "host-corpus"},
        {"value": "no_resistance", "description": "（宿主语料：transfer_type）",
         "source": "host-corpus"},
        {"value": "transfer", "description": "（宿主语料：transfer_type）",
         "source": "host-corpus"}],
    ("CondInitial", "GetVariableType", "return"): [
        {"value": "fuel", "description": "（宿主语料：variable_type）",
         "source": "host-corpus"},
        {"value": "fvf", "description": "（宿主语料：variable_type）",
         "source": "host-corpus"},
        {"value": "oxid", "description": "（宿主语料：variable_type）",
         "source": "host-corpus"},
        {"value": "pbnd", "description": "（宿主语料：variable_type）",
         "source": "host-corpus"},
        {"value": "reaction_incomp_species",
         "description": "（宿主语料：variable_type）",
         "source": "host-corpus"},
        {"value": "specify_value", "description": "（宿主语料：variable_type）",
         "source": "host-corpus"},
        {"value": "vapor", "description": "（宿主语料：variable_type）",
         "source": "host-corpus"},
        {"value": "velocity_poisson",
         "description": "（宿主语料：variable_type）",
         "source": "host-corpus"},
        {"value": "vos", "description": "（宿主语料：variable_type）",
         "source": "host-corpus"}],
}


def _apply_value_evidence(catalog: dict) -> dict:
    """笔误修正 + 语料补充（R33-1）。返回统计，供 CLI 打印。"""
    fixed = added = 0
    for info in catalog["classes"].values():
        for kind in ("methods", "properties"):
            for name, entry in (info.get(kind) or {}).items():
                slots = list(entry.get("arguments") or []) + [
                    entry.get("return") or {}]
                for slot in slots:
                    if not isinstance(slot, dict):
                        continue
                    for v in slot.get("values") or []:
                        hit = _VALUE_FIXES.get(v.get("value"))
                        if hit:
                            v["manual_value"] = v["value"]
                            v["value"], v["fix_evidence"] = hit
                            fixed += 1
    for (cls, member, arg), extra in _VALUE_ADDENDA.items():
        entry = ((catalog["classes"].get(cls) or {})
                 .get("methods", {}).get(member))
        if not entry:
            continue
        slots = [entry.get("return") or {}] if arg == "return" else [
            a for a in (entry.get("arguments") or []) if a.get("name") == arg]
        for slot in slots:
            vals = slot.setdefault("values", [])
            have = {v["value"] for v in vals}
            for v in extra:
                if v["value"] not in have:
                    vals.append(dict(v))
                    added += 1
    return {"fixed": fixed, "added": added}


def _numeric_values(cell: str) -> list:
    """整数取值格 → [{"value", "description"}]（同格多值也拆开）。"""
    return [{"value": m.group(1), "description": m.group(2).strip()}
            for m in _NUM_DESC.finditer(cell.strip())]


def _push_values(entry: dict, mode, vals: list) -> None:
    """枚举行挂到最近的参数/返回值上（无宿主行则挂条目级）。"""
    target = entry.get("return") if mode == "ret" else None
    if target is None and entry.get("arguments"):
        target = entry["arguments"][-1]
    (target if isinstance(target, dict) else entry).setdefault(
        "values", []).extend(vals)


def _push_arg(entry: dict, name_cell: str, desc: str, ret: bool = False) -> None:
    name_cell = (name_cell or "").strip()
    if not name_cell:
        return
    am = _ARG_CELL.match(name_cell)
    item = {
        "type": am.group(1) if am else "",
        "name": (am.group(2) if am else name_cell).strip(),
        "description": (desc or "").strip(),
    }
    vals = _desc_values(name_cell + " " + (desc or ""))
    if vals:
        item["values"] = vals
    if ret:
        entry["return"] = item
    else:
        entry.setdefault("arguments", []).append(item)


def _split_sections(text: str):
    """yield (section_mode, name, block) —— 按 h2(Method/Property)/h3 切分。"""
    marks: list[tuple[int, str, str]] = []  # (pos, kind, text)
    for m in _H2.finditer(text):
        marks.append((m.start(), "h2", m.group(1).strip()))
    for m in _H3.finditer(text):
        marks.append((m.start(), "h3", m.group(1).strip()))
    marks.sort()
    mode = None
    for i, (pos, kind, label) in enumerate(marks):
        if kind == "h2":
            if label in ("Method", "Property"):
                mode = label.lower()
            continue
        if mode is None:
            continue  # Method 区之前的内容（类概述等）
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        yield mode, label, text[pos:end]


_CLASS_EXPL = re.compile(r"<h1>([^<]+) Class</h1>.*?<table>(.*?)</table>",
                         re.S)
_INSTANCE = re.compile(r"Set (\w+)\s*=\s*(\w+)\.(\w+)\(([^)]*)\)")


def _class_info(text: str) -> dict:
    """类级信息：说明、实例获取示例、Condition 基类继承推断。"""
    info: dict = {}
    m = _CLASS_EXPL.search(text)
    if m:
        rows = _TR.findall(m.group(2))
        for row in rows:
            cells = [_strip(c) for c in _TD.findall(row)]
            if cells and "[Explanation]" in cells[0] and len(cells) > 1:
                info["explanation"] = cells[1]
                if "methods of Condition class can be used" in cells[1]:
                    info["inherits"] = "Condition"
                break
    inst = _INSTANCE.search(text)
    if inst:
        info["instance"] = f"Set {inst.group(1)} = {inst.group(2)}.{inst.group(3)}({inst.group(4)})"
    return info


def extract_class(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    out: dict = {"file": path.name}
    out.update(_class_info(text))
    out["methods"] = {}
    out["properties"] = {}
    for mode, name, block in _split_sections(text):
        entry = _parse_method_block(block)
        sig = _SIG_MEMBER.search(entry.get("signature") or "")
        if sig and sig.group(1) != name:
            entry["signature_name"] = sig.group(1)
        target = out["methods"] if mode == "method" else out["properties"]
        target[name] = entry
    if not out["properties"]:
        del out["properties"]
    return out


def class_files() -> list[tuple[str, Path]]:
    """[(类名, 文件)]，按手册文件名规约排序。"""
    seen: dict[str, Path] = {}
    for pattern, prefix in _FILE_PATTERNS:
        for path in sorted(MANUAL.glob(pattern)):
            m = _NAME_RE.match(path.name)
            if not m:
                continue
            name = prefix + (m.group(1) or m.group(2))
            seen.setdefault(name, path)
    return sorted(seen.items())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", action="store_true",
                    help="仅打印类清单与统计，不写 JSON")
    args = ap.parse_args(argv)

    if not MANUAL.is_dir():
        print(f"manual not found: {MANUAL}", file=sys.stderr)
        return 2
    files = class_files()
    if not files:
        print("no class file matched", file=sys.stderr)
        return 2

    catalog = {
        "source": "CradleCFD2025.2 Manuals scFLOW HTML VB_Interface_eng",
        "progid": PROGID,
        "extracted": date.today().isoformat(),
        "classes": {},
    }
    total = 0
    for name, path in files:
        info = extract_class(path)
        catalog["classes"][name] = info
        total += len(info["methods"]) + len(info.get("properties", {}))
        if args.list:
            print(f"{name:42s} methods={len(info['methods']):4d} "
                  f"props={len(info.get('properties', {})):3d}  {path.name}")

    ev = _apply_value_evidence(catalog)

    if args.list:
        print(f"== {len(files)} classes, {total} members "
              f"(笔误修正 {ev['fixed']}、语料补充 {ev['added']})")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    n_cond = sum(1 for n in catalog["classes"] if n.startswith("Cond"))
    print(f"wrote {OUT}")
    print(f"classes={len(catalog['classes'])} "
          f"(Cond*={n_cond}) members={total} "
          f"fixes={ev['fixed']} addenda={ev['added']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
