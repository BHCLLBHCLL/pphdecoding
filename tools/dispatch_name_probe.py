#!/usr/bin/env python3
"""R35-1：用 `IDispatch::GetIDsOfNames` 裁定「手册标题名 vs 签名名」。

背景：目录里 41 个方法的两处名字不一致（标题写 `…WitouthMovingPart`、签名写
`…WithoutMovingPart`；`SelectFace` vs `SetSelectFaces`…）。**两边都留着等于没裁定**，
而写错名字的那一侧调用必然失败。

离线路线已排除：scFLOWpre 的 COM 服务器**没有注册类型库**
（`HKCR\\CLSID\\{6FDA4768-…}\\TypeLib` 不存在；二进制里也 LoadTypeLib 不出来），
所以只能用运行时 `GetIDsOfNames` —— 它**只做名字解析、不调用任何方法**，零副作用。
顺带探测对象是否实现 `GetTypeInfo`（有则能整表导出真实成员名）。

用法::

    python tools/dispatch_name_probe.py --json _p12u_gate/r35/name_verdicts.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
sys.path.insert(0, str(ROOT))

import console_utf8  # noqa: E402

console_utf8.enable()

CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
PROGID = "scFLOWpre_Bx64net.Application.2025"
BOX = ROOT / "box.pph"

#: 可在单会话内取到实例的类 → 取实例的步骤名
TARGETS = ["Doc", "MeshingGroup", "MeshingGroupSetting", "Octree", "OctParam",
           "Conditions", "Env", "MDLWizard", "HybridParam"]


def mismatches() -> list:
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    out = []
    for cls, info in cat["classes"].items():
        for kind in ("methods", "properties"):
            for name, entry in (info.get(kind) or {}).items():
                sig = entry.get("signature_name")
                if sig and sig != name:
                    out.append({"class": cls, "heading": name,
                                "signature": sig, "kind": kind})
    return out


def _resolve(obj, name: str) -> str:
    """名字能否在该对象上解析（DISPID 命中 / UNKNOWNNAME / 其它错误）。

    R39-2：三条路依次试 —— `_oleobj_.GetIDsOfNames`（标准）→ 裸对象自带
    `GetIDsOfNames`（少数包装）→ `pythoncom` 直接按 IID 取 IDispatch。
    全部失败时把**对象类型**一并报出来（否则只能看到 AttributeError，无从判断）。
    """
    import pythoncom
    target = getattr(obj, "_oleobj_", None)
    if target is None:
        target = obj if hasattr(obj, "GetIDsOfNames") else None
    if target is not None:
        try:
            target.GetIDsOfNames(name)
            return "resolved"
        except Exception as exc:  # noqa: BLE001
            low = str(exc).lower()
            if "unknown" in low or "-2147352570" in low:
                return "unknown_name"
            if type(exc).__name__ != "AttributeError":
                return "error:" + type(exc).__name__
    try:
        disp = pythoncom.ObjectFromLresult if False else None  # noqa: F841
        ptr = getattr(obj, "_oleobj_", None)
        if ptr is not None:
            disp = ptr.QueryInterface(pythoncom.IID_IDispatch)
            disp.GetIDsOfNames(name)
            return "resolved"
    except Exception as exc:  # noqa: BLE001
        low = str(exc).lower()
        if "unknown" in low or "-2147352570" in low:
            return "unknown_name"
    return "error:AttributeError(" + type(obj).__name__ + ")"


def _has_type_info(obj) -> str:
    try:
        obj._oleobj_.GetTypeInfo()
        return "yes"
    except Exception as exc:  # noqa: BLE001
        return "no:" + type(exc).__name__


def _obtain(cls: str, conds, doc, mg):
    """尽力取一个该类的实例（R36-1）。

    手册在类级 `instance` 里给了配方，但形态各异；这里按"名字家族"逐个试：
    `Cond*` 走 `conditions.CreateCond*/QueryCond*ByName`，其余试 `Get*/GetPreset*`。
    取不到就如实记为「无实例」（不猜）。
    """
    short = cls[4:] if cls.startswith("Cond") else cls
    plan = []
    if conds is not None:
        plan += [(conds, "CreateCond" + short, (cls + "_r36",)),
                 (conds, "QueryCond" + short + "ByName", (cls + "_r36",)),
                 (conds, "Create" + short, (cls + "_r36",)),
                 (conds, "Get" + short, ())]
    for host in (doc, mg):
        if host is None:
            continue
        plan += [(host, "Get" + short, ()),
                 (host, "GetPreset" + short, ()),
                 (host, "Get" + short + "Default", ())]
    for host, name, args in plan:
        fn = getattr(host, name, None)
        if fn is None:
            continue
        try:
            obj = fn(*args) if args else fn()
        except Exception:  # noqa: BLE001
            continue
        if obj is not None:
            return obj, name
    return None, None


#: R45-1：手册配方/自动计划里的宿主变量名 → 本探针 ctx 键
_HOST_KEYS = {
    "doc": "Doc", "document": "Doc",
    "conditions": "Conditions", "conds": "Conditions",
    "meshgroup": "MeshingGroup", "mesh_group": "MeshingGroup", "mg": "MeshingGroup",
    "meshgroupsetting": "MeshingGroupSetting",
    "env": "Env", "app": "Application", "application": "Application",
    "util": "Utility", "utility": "Utility", "mdl": "MDL",
}

#: ctx 键 → 目录类名（键名与目录类名不一致时的别名，R45-1）
#:
#: **留空是有实测依据的**：R45 第一版把会话的 Application 对象别名成
#: Kicker.Application，结果那 9 个成员里 8 个 unknown_name —— 会话对象是目录里的
#: **Application** 类（23 成员），Kicker.Application 是 Kicker 启动器那个对象。
#: 别名只有在**验身**通过时才允许写进去（见 identity_ok）。
CTX_ALIASES: dict = {}

def arg_ladder(name: str) -> list:
    """自动计划的实参候选（R45-1）：1 参 → 3 参 → 2 参 → 0 参 → 布尔 → 字符串。

    多参创建器（CreateCondCoSim(name, apptype, interfacetype)）与零参 getter
    （Doc.GetProjectSetting 这类）都能在同一套阶梯里试到。
    """
    return [(name,), (name, 0, 0), (name, 0), (), (name, False),
            (name, "default")]


#: 目录成员表缓存：扩面要对 199 类各算一遍宿主成员，重复构建太慢
_MEMBER_CACHE: dict = {}


#: R44-2 / R45-2：空对象的**前置条件**提示表（这些类只有跑过对应流程才有实例）。
#:
#: 放在模块级是有意的：证据里只出现**当轮真的空**的类（R45 后 ClosedVolume/
#: Octree 已能取到，就不再列），但"这个类要先跑什么"是**知识**，不随一轮结果
#: 消失 —— 测试直接查这张表，产品面（`automation.scflowpre_api.object_hints`）
#: 查证据里的子集。
EMPTY_HINTS = {
    "ClosedVolume": "先跑 MDL/BAM 建模（闭空间由面区域生成）",
    "PropItem": "先注册材料/物性（或经闭空间的材料项取得）",
    "CondMapForStructure": "先建映射（scFLOW2Nastran）条件——宿主无创建接口",
    "MapCond": "先有映射流程（宿主无 GetAllMapCondNames 接口）",
    "CondBoussinesqBaseTemp": "条件向导创建——宿主无 CreateCondBoussinesqBaseTemp 接口",
    "CondCoSim": "先做 CoSim 设置（本机语料无该条件）",
    "CondCoSimRegion": "先有 CoSim 区域（由 CoSim 条件派生）",
    "Octree": "先建八叉树（网格组的 octree 步骤）",
}


def _catalog_members(cat: dict, cls: str) -> dict:
    key = (id(cat), cls)
    hit = _MEMBER_CACHE.get(key)
    if hit is not None:
        return hit
    info = cat["classes"].get(cls) or {}
    out: dict = {}
    for kind in ("methods", "properties"):
        out.update(info.get(kind) or {})
    _MEMBER_CACHE[key] = out
    return out


def _candidate_members(cls: str) -> list:
    """按类名猜构造/取用成员名（R45-1）。

    手册的取法各式各样（CreateCondDTSR / GetCondCavitation /
    QueryCondMultiphaseMaterial / GetPresetSurfParam / GetUtility…），
    所以按名字家族**穷举**，能不能调由宿主裁定。
    """
    full = cls.split(".")[-1]
    short = full[4:] if full.startswith("Cond") else full
    names: list = []
    for base in (full, short):
        names += ["Create" + base, "Create" + base + "Default", "Get" + base,
                  "Get" + base + "s", "Query" + base + "ByName",
                  "GetPreset" + base, "Query" + base, "Get" + base + "ByIndex",
                  "Query" + base + "ByIndex", "Get" + base + "Default"]
    seen: set = set()
    out: list = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _split_args(text: str) -> list:
    """按顶层逗号切参数（配方里的参数不含嵌套括号，够用）。"""
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return [t.strip() for t in out if t.strip()]


def recipe_plan(cat: dict, cls: str, held: dict):
    """类级 instance 配方 → (host_key, member, args, how)（R45-1）。

    手册给的取法形如 Set dtsr = conditions.CreateCondDTSR("name")。占位符
    只认能安全替换的几种（ProgID → 本机 ProgID、带引号字面量 → 生成名或
    @ 名、整数、布尔）；出现别的占位符就**放弃该配方**（不猜）。
    """
    inst = ((cat["classes"].get(cls) or {}).get("instance") or "").strip()
    # 手册里的引号有**印刷体**（“name”）也有 ASCII —— 先归一，否则配方参数
    # 会被当成「未知占位符」整条放弃（R45 实测 CreateCondDTSR 等一批）
    for fancy, plain in (("\u201c", '"'), ("\u201d", '"'),
                         ("\u2018", "'"), ("\u2019", "'")):
        inst = inst.replace(fancy, plain)
    m = re.match(r"^Set\s+\w+\s*=\s*(\w+)\.(\w+)\s*(?:\((.*)\))?$", inst, re.S)
    if not m:
        return None
    host_key = _HOST_KEYS.get(m.group(1).lower())
    if host_key is None or host_key not in held:
        return None
    member, raw = m.group(2), (m.group(3) or "").strip()
    args: list = []
    if raw:
        for tok in _split_args(raw):
            if tok == "ProgID":
                args.append(PROGID)
            elif re.fullmatch(r'"[^"]*"', tok):
                lit = tok.strip('"')
                args.append(lit if lit.startswith("@") else "R45" + cls.split(".")[-1])
            elif tok.lower() in ("true", "false"):
                args.append(tok.lower() == "true")
            elif re.fullmatch(r"-?\d+", tok):
                args.append(int(tok))
            else:
                return None      # 未知占位符（如 id / propname）→ 该配方不可自动执行
    return (host_key, member, tuple(args), "recipe:" + m.group(1) + "." + member)


#: 手册参数名前缀：'[in](BSTR)ProgID' → 'ProgID'
_ARG_PREFIX = re.compile(r"^\[[^\]]*\]\s*(?:\([^)]*\))?\s*")


def signature_args(entry: dict, name: str):
    """按手册**参数名**给一组实参（R45-1）；有认不出的参数就返回 None（不猜）。

    没有它，Kicker.Application.GetApplicationLaunchSetting(ProgID) 这类成员
    只会被阶梯喂上名字串 → 全失败（PROGID 是唯一能用的取值）。
    """
    args: list = []
    for a in entry.get("arguments") or []:
        # 手册参数名带前缀：'[in](BSTR)ProgID' —— 不剥前缀就永远认不出 ProgID
        key = _ARG_PREFIX.sub("", str(a.get("name") or "")).strip().lower()
        if key in ("", "none", "-"):
            continue
        vals = [v.get("value") for v in (a.get("values") or [])
                if v.get("value") is not None]
        if key == "progid":
            args.append(PROGID)
        elif "name" in key:
            args.append(name)
        elif vals:
            # R47-1：手册**词表**里的合法取值优先（CreateMultiYAxisTable(name,
            # type) 的 type 只认 'freq_absorp_coeff_table' 这类字符串 —— 喂 0
            # 必然被拒，喂词表首项就能过）
            args.append(vals[0])
        elif key in ("type", "index", "id", "num", "number", "key",
                     "definitiontype", "valuekey"):
            args.append(0)
        elif key.startswith(("b", "is", "flag", "does", "has")):
            args.append(False)
        else:
            return None
    return tuple(args)


def _class_stems(cls: str) -> list:
    """类名 → 手册里可能用来命名"取它"的成员的名字片段（R48-1）。

    手册的命名习惯（实测）：
    * 前缀缩写 @@IS???@@ → @@S???@@、@@IV???@@ → @@V???@@（ISFace 的取法是
      @Doc.GetSelectedSFaces@@、IVFace 是 @@Doc.GetSelectedVFaces@@）；
    * @@Cond<X>@@ 的取法常叫 @@GetCond<X>Condition@@（CondOutputPclFile →
      @@GetCondOutputPclFileCondition@@）；
    * 尾部 @@View/Param@@ 常被省掉（CrossSectionView → @@GetCrossSectionViewObj@@）。
    片段**按特异性排序**（长的在前），短于 4 个字母的一律不要（否则 "edge" 这种
    会命中一大片无关成员）。
    """
    full = cls.split(".")[-1]
    low = full.lower()
    out: list = [low]
    if low.startswith("cond") and len(low) > 6:
        out.append(low[4:])
    if low.startswith("is") and len(low) > 4:
        out.append("s" + low[2:])
    if low.startswith("iv") and len(low) > 4:
        out.append("v" + low[2:])
    for suffix in ("view", "param", "database", "info"):
        if low.endswith(suffix) and len(low) - len(suffix) >= 4:
            out.append(low[:-len(suffix)])
    seen: list = []
    for s in sorted(set(out), key=len, reverse=True):
        if len(s) >= 4 and s not in seen:
            seen.append(s)
    return seen


#: 片段命中里要排除的"元信息"字样（它们返回的是结构/标量，不是那个类的实例）
_STEM_NOISE = ("information", "count", "num", "flag", "color", "name")


def stem_candidates(cat: dict, cls: str, held: dict) -> list:
    """按**命名片段**找取法（R48-1）：手册没给实例配方、名字家族也猜不中的类。

    只在**已持有宿主**上找（调得到才算候选）；@@Get*/Query*@@ 优先，@@HitTest*/
    @@Set*/@@Select*@@ 靠后（前者是取用，后者多是动作）。
    """
    stems = _class_stems(cls)
    if not stems:
        return []
    out: list = []
    for host_key, host_cls in held.items():
        hmembers = _catalog_members(cat, host_cls)
        for name in sorted(hmembers):
            low = name.lower()
            rank = 2
            for i, stem in enumerate(stems):
                if stem in low:
                    rank = i
                    break
            else:
                continue
            if not low.startswith(("get", "query")):
                rank += 3          # 取用优先于动作
            elif any(bad in low for bad in _STEM_NOISE):
                continue           # 元信息取器（...Information/Count/Num/Flag…）
            elif any(low.endswith(stem + s) for stem in stems for s in ("", "s")):
                rank -= 1          # 名字**以片段收尾**的最像"取这个类"
            out.append({"rank": rank, "host": host_key, "member": name,
                        "args": signature_args(hmembers[name],
                                               "R48" + cls.split(".")[-1]),
                        "how": "stem:" + host_cls + "." + name})
    out.sort(key=lambda p: (p["rank"], p["how"]))
    return out[:6]


def auto_plans(cat: dict, cls: str, held: dict) -> list:
    """为一个目标类生成候选配方（离线纯函数，可单测）。

    held: {ctx 键: 目录类名}。三层优先级：
    ① 目录里**声明在已持有宿主上**的构造/取用成员（最可靠）；
    ② 类级 instance 配方（手册亲自给的取法）；
    ③ 宿主独有成员（手册是子集，R42 已证宿主有手册外成员）——只在条件/文档/
       网格组三个宿主上泛试，且放在最后。
    """
    plans: list = []
    cands = _candidate_members(cls)
    # ② 配方放最前：那是手册**亲自给的取法**（参数也是它给的，不用猜）；
    #    配方拿错对象由验身拦（CondOversetGap 那页写的就是 CreateCondSpray）
    rec = recipe_plan(cat, cls, held)
    if rec:
        plans.append({"host": rec[0], "member": rec[1], "args": rec[2],
                      "how": rec[3]})
    # ① 目录里声明在已持有宿主上的构造/取用成员（参数按阶梯退让）
    gen = "R45" + cls.split(".")[-1]
    for host_key, host_cls in held.items():
        hmembers = _catalog_members(cat, host_cls)
        for name in cands:
            if name in hmembers:
                plans.append({"host": host_key, "member": name,
                              "args": signature_args(hmembers[name], gen),
                              "how": "catalog:" + host_cls + "." + name})
    # ③ 命名片段（R48-1）—— 手册没给配方、名字家族也猜不中的类靠它
    plans += stem_candidates(cat, cls, held)
    for host_key in ("Conditions", "Doc", "MeshingGroup"):
        if host_key in held:
            for name in cands[:3]:
                plans.append({"host": host_key, "member": name, "args": None,
                              "how": "generic:" + host_key + "." + name})
    return plans


def sweep_class_verdict(states: dict, min_members: int = 4) -> str:
    """整类成员解析结果 → 'ok' / 'suspect' / 'empty'（R45-1 验身后置闸）。

    `suspect` = 未知过半（且成员数够多）⇒ 手上这个对象**多半不是这个类**：
    别名写错、配方给了别家对象、或对象过时。这类结论一律不记 ——
    假否证（把别人的成员写成"宿主未实现"）比"未普查"更有害。
    """
    if not states:
        return "empty"
    n_unk = sum(1 for s in states.values() if s == "unknown_name")
    if len(states) >= min_members and n_unk * 2 > len(states):
        return "suspect"
    return "ok"


#: 收获名字用的成员名（GetAll*Names 这类；值是名字数组）
_NAME_GETTERS = ("GetAllConditionNames", "GetAllTableNames",
                 "GetAllMultiYAxisTableNames", "GetAllMapCondNames",
                 "GetAllScriptNames", "GetAllRegionNames")


def harvest_names(cat: dict, ctx: dict, call) -> list:
    """收集**真实存在的对象名**，供 Query<X>ByName(name) 类配方使用（R47-1）。

    只开工程拿不到 Region/Table/SNode 这类对象，但它们的取法是
    Query<X>ByName(name) —— 名字从哪来？两条**实证**来源：
    ① 已持有对象的 GetName()（区域/条件都实现了它）；
    ② 宿主上的 GetAll*Names 取器（返回名字数组）。
    拿不到就空手（不猜名字）。
    """
    pool: list = []

    def _add(v):
        if isinstance(v, str) and v and v not in pool and len(pool) < 40:
            pool.append(v)

    for key, obj in list(ctx.items()):
        if obj is None or key in ("Doc", "Conditions", "MeshingGroup"):
            continue
        try:
            _add(str(call(obj, "GetName") or "").strip())
        except Exception:  # noqa: BLE001
            continue
    for key in ("Doc", "Conditions", "MeshingGroup"):
        obj = ctx.get(key)
        if obj is None:
            continue
        for member in _NAME_GETTERS:
            try:
                got = call(obj, member)
            except Exception:  # noqa: BLE001
                continue
            for item in (got if isinstance(got, (list, tuple)) else [got]):
                _add(str(_unwrap(item) or "").strip())
    # 手册配方里的 @名字 也是实证的名字（引号有印刷体，先归一 —— R47 实测：
    # 不归一只能收到 ASCII 引号那 4 个，@ALECancel 这类会漏）
    for cls in cat["classes"]:
        inst = ((cat["classes"].get(cls) or {}).get("instance") or "")
        for fancy, plain in (("\u201c", '"'), ("\u201d", '"'),
                             ("\u2018", "'"), ("\u2019", "'")):
            inst = inst.replace(fancy, plain)
        for lit in re.findall(r'"(@[^"]+)"', inst):
            _add(lit)
    return pool


KICKER_PROGID = "Kicker_Bx64.Application.2025"


def attach_kicker(ctx: dict, via: dict, result: dict, index: dict,
                  cat: dict, resolve=None) -> int:
    """把 Kicker 启动器对象接进来（R47-2），并派生它的两个类实例。

    Kicker.* 三个类此前终态是"本会话取不到"——但**Kicker 本机就在跑**（宿主就是
    它启动的）。这里附着（失败才 Dispatch），然后按手册取
    GetApplicationLaunchSetting(ProgID) / GetLicenseStatus()，**逐个验身**
    （identity_ok：类独有成员解析率 ≥ 半数）才收进 ctx。
    """
    import win32com.client as wc

    from automation import scflowpre_api as api
    resolve = resolve or _resolve
    made = 0
    kicker = None
    try:
        kicker = wc.GetActiveObject(KICKER_PROGID)
        how = "kicker:GetActiveObject"
    except Exception:  # noqa: BLE001
        try:
            kicker = wc.Dispatch(KICKER_PROGID)
            how = "kicker:Dispatch"
        except Exception as exc:  # noqa: BLE001
            result["kicker_error"] = type(exc).__name__ + ": " + str(exc)[:120]
            return 0
    raw = getattr(kicker, "_oleobj_", None) or kicker
    ctx["Kicker.Application"] = raw       # 普查用：PyIDispatch 就能 GetIDsOfNames
    via["Kicker.Application"] = how
    made += 1
    # **调用**必须走 win32com 的 CDispatch（_invoke 先 _FlagAsMethod 再 getattr）——
    # 拿 _oleobj_（PyIDispatch）去调会 AttributeError（R47 首轮实测）
    caller = api.ComObject(kicker)
    # GetApplicationLaunchSetting(ProgID) 的 ProgID **不是**我们连 scFLOWpre 用的那个
    # （R47 实测：传 scFLOWpre_Bx64net.Application.2025 → 宿主回 'Invalid ProgID
    # was specified.'）。故按"注册表里实际存在的 ProgID 形态"逐个试，成功的那个入证据。
    progids = (PROGID, "scFLOWpre_Bx64net.Application", "scFLOWpre_Bx64net",
               "scFLOWpre_Bx64net.Application.2023")
    plans = (("GetApplicationLaunchSetting", "Kicker.ApplicationLaunchSetting",
              progids),
             ("GetLicenseStatus", "Kicker.LicenseStatus", (None,)))
    for member, cls, arglist in plans:
        args = arglist if isinstance(arglist, tuple) else (arglist,)
        cand = None
        for arg in (args if args else (None,)):
            try:
                cand = _unwrap(caller.call(member) if arg is None
                               else caller.call(member, arg))
            except Exception as exc:  # noqa: BLE001
                result.setdefault("kicker_errors", {})[cls] = (
                    member + "(" + str(arg)[:40] + ") -> "
                    + type(exc).__name__ + ": " + str(exc)[:90])
                cand = None
                continue
            if cand is not None and cand is not False:
                result.setdefault("kicker_args", {})[cls] = str(arg)
                break
            cand = None
        if cand is None:
            result.setdefault("kicker_errors", {}).setdefault(
                cls, member + " -> 各 ProgID 都返回空")
            continue
        if cand is None or cand is False:
            result.setdefault("kicker_errors", {})[cls] = member + " -> 返回空"
            continue
        ok, detail = identity_ok(
            cand, distinctive_members(cat, cls, index))
        if not ok:
            result.setdefault("kicker_errors", {})[cls] = (
                member + " -> 验身不过 " + str(detail))
            continue
        ctx[cls] = cand
        via[cls] = "kicker:" + member
        made += 1
    return made


def prime_selection(ctx: dict, cat: dict) -> list:
    """先"全选"再取几何类（R49-1）。

    @@GetSelected<X>@@ 系列只在**有选中**时才给对象 —— @@ISFace@@/@@IVFace@@/@@ISEdge@@/
    @@IVEdge@@/@@ISVertex@@ 这几类在 R48 的实测里"取法都在、调用也成功，就是返回空"。
    这里在取实例之前把 Doc 上的 @@SetSelectAll*@@ 逐个打上（参数全给 True，
    因为这些 setter 的布尔参数是"选/不选"而不是可选行为）。
    """
    from automation import scflowpre_api as api
    doc = ctx.get("Doc")
    if doc is None:
        return [], {}
    caller = api.ComObject(doc)
    done: list = []
    errs: dict = {}
    for name, entry in (cat["classes"].get("Doc", {}).get("methods")
                        or {}).items():
        if not name.startswith("SetSelectAll"):
            continue
        argc = max(1, len(entry.get("arguments") or []))
        tries = [(True,) * argc]
        if argc > 1:
            # 可选尾参可省（手册口径"少不报"）—— 实测 SetSelectAllVFace 两参版
            # 在本机被拒，一参版才行
            tries.append((True,))
        for argsin in tries:
            try:
                caller.call(name, *argsin)
                done.append(name)
                errs.pop(name, None)
                break
            except Exception as exc:  # noqa: BLE001
                errs[name] = type(exc).__name__ + ": " + str(exc)[:80]
    return done, errs


def audit_identity_guard(cat: dict, ctx: dict, index: dict,
                         sample: int = 0, details: dict | None = None) -> dict:
    """量验身闸门的**误放率**（R49-2）：拿别家的对象去验，看会不会被放行。

    判据是"该类独有成员的解析率 ≥ 半数"。这条例很便宜，但**只有拦住过什么**
    的记录（identity_rejected），没有"会不会放错"的数。这里在真对象上做对照：
    * @@self_pass@@：对象对**自己**的类应当通过（放错=误杀真对象）；
    * @@false_accept@@：对象对**别的类**若不通过则拦对了（放行=误放）。
    """
    if sample <= 0:
        return {}
    # ① 自类通过率：**全部**已取得类（不只抽样）—— 不过就是误杀真对象
    all_cands = [c for c in sorted(ctx)
                 if c in cat["classes"]
                 and distinctive_members(cat, c, index)]
    self_total = self_pass = 0
    sample_sizes: dict = {}
    for cls in all_cands:
        obj = ctx.get(cls)
        if obj is None:
            continue
        smp = distinctive_members(cat, cls, index)
        ok, detail = identity_ok(obj, smp)
        self_total += 1
        self_pass += 1 if ok else 0
        key = str(detail.get("sample"))
        sample_sizes[key] = sample_sizes.get(key, 0) + 1
    # ② 跨类误放（抽样 × 3 家别类）
    cands = all_cands[:sample]
    trials = accepts = 0
    for cls in cands:
        obj = ctx.get(cls)
        if obj is None:
            continue
        for other in [c for c in cands if c != cls][:3]:
            trials += 1
            ok2, _ = identity_ok(obj, distinctive_members(cat, other, index))
            accepts += 1 if ok2 else 0
    # ③ 边界表（离线、确定性）：样本量 1..5 × 解析数 0..s 的判定形状
    boundary = [{"sample": s, "resolved": r, "accept": r * 2 >= s}
                for s in range(1, 6) for r in range(s + 1)]
    # ④ 被否样本的**稳健性**：离阈值多远（|2r − s| ≤ 1 ⇒ 差一点就翻案 = 判据脆）
    margins = []
    fragile = 0
    for key, detail in (details or {}).items():
        s = int(detail.get("sample") or 0)
        r = int(detail.get("resolved") or 0)
        if s <= 0:
            continue
        margin = 2 * r - s
        fragile += 1 if abs(margin) <= 1 else 0
        margins.append({"how": key, "sample": s, "resolved": r,
                        "margin": margin})
    return {"classes_sampled": len(cands), "self_total": self_total,
            "rejections": len(margins), "fragile_rejections": fragile,
            "rejection_margins": margins[:12],
            "self_pass": self_pass,
            "false_kill": self_total - self_pass,
            "distinctive_sample_sizes": sample_sizes,
            "cross_trials": trials, "false_accept": accepts,
            "false_accept_rate": (round(accepts / trials, 3) if trials else None),
            "boundary": boundary,
            "rule": "该类独有成员解析率 ≥ 半数即认作此类的对象"}


def member_name_index(cat: dict) -> dict:
    """成员名 → 出现在多少个类里（1 = 该类独有）。验身与无歧义判据共用。"""
    index: dict = {}
    for cls in cat["classes"]:
        for name in _catalog_members(cat, cls):
            index[name] = index.get(name, 0) + 1
    return index


def distinctive_members(cat: dict, cls: str, index: dict,
                        limit: int = 5) -> list:
    """该类**独有**的成员名（其它类都没有）——用来验「拿到的对象是不是这个类」。"""
    mine = _catalog_members(cat, cls)
    return [m for m in sorted(mine) if index.get(m, 0) == 1][:limit]


def identity_ok(obj, sample, resolve=None) -> tuple:
    """拿到的对象必须**像**这个类（R45-1 验身）。

    为什么必须验：手册配方未必对得上类（CondOversetGap 那页配方写的是
    CreateCondSpray）。拿错对象不会报错，但普查会把它**所有**独有成员判成
    「宿主未实现」—— 那是假否证，比没普查更糟。判据：独有成员**半数以上**能解析。
    """
    resolve = resolve or _resolve
    if not sample:
        return True, {"sample": 0, "resolved": 0, "unknown": 0, "errors": 0}
    states = [resolve(obj, m) for m in sample]
    detail = {"sample": len(sample),
              "resolved": sum(1 for s in states if s == "resolved"),
              "unknown": sum(1 for s in states if s == "unknown_name"),
              "errors": sum(1 for s in states if str(s).startswith("error:"))}
    ok = detail["resolved"] * 2 >= len(sample)
    return ok, detail


class _MdlUnavailable(RuntimeError):
    """MDL 对象不可得（R40-1：闭空间只能建在 MDL 之上）。"""


def _unwrap(obj, depth: int = 4):
    """递归拆 tuple/数组（取首元素，最多 `depth` 层）。

    win32com 对"多返回值"成员返回 tuple；实测 `conds.GetCondCoSim()` 还会**套一层**
    —— 只拆一层仍拿到 tuple，于是名字解析抛 AttributeError，
    被误判成"宿主不认"（R38/R39 两次踩到，都是假否证）。
    """
    while depth and isinstance(obj, (tuple, list)):
        if not obj:
            return None      # **空 tuple = "没拿到对象"**，不是"拿到了一个空容器"
        obj = obj[0]
        depth -= 1
    return obj


def _is_com(obj) -> bool:
    """是不是一个真正的 COM 对象（R48-1 补闸）。

    片段候选里混着**标量返回**的成员（`Doc.GetSFaceInformation` 这类给的是字符串/
    结构体），它们能过"非空"检查，却会在普查里对每个成员抛 AttributeError ——
    46 条 `error:*` 就是这么来的（整类不记的闸门只看 unknown_name，不看 error）。
    """
    return hasattr(obj, "_oleobj_") or hasattr(obj, "GetIDsOfNames")


def _first(obj):
    try:
        if hasattr(obj, "__getitem__") and len(obj):
            return _unwrap(obj[0]) if isinstance(obj[0], (tuple, list)) \
                else obj[0]
    except Exception:  # noqa: BLE001
        pass
    return None


def _chains(doc, conds, mg, obtained: dict, inter: dict,
            errors: dict) -> dict:
    """链式实例（R37-1）：手册类级 `instance` 给了配方，但形态各异，逐条实现。

    每条的失败都**不致命**：取不到就不进 ctx，最终如实记为「未裁定 + 原因」。
    """
    out: dict = {}

    def _try(cls, fn, how):
        try:
            obj = fn()
        except Exception as exc:  # noqa: BLE001
            errors[cls] = how + " -> " + type(exc).__name__ + ": " + str(exc)
            return
        if obj is not None:
            out[cls] = _unwrap(obj)     # R41：多返回值成员给的是 tuple，必须先拆
            obtained[cls] = how
        else:
            # **覆盖**而不是 setdefault：前面的尝试（如工程循环里的 MDL 检查）留下的
            # 原因会被后来的真实失败盖住 —— R41 实测：留着旧文本会得出错误结论
            errors[cls] = how + " -> 返回空（工程里没有该对象）"

    # 数组型 getter → 取第一个
    _try("ClosedVolume", lambda: _first(doc.GetClosedVolumes(False)),
         "chain:doc.GetClosedVolumes")
    _try("ClosedVolume", lambda: _first(doc.GetClosedVolumes(True)),
         "chain:doc.GetClosedVolumes(True)")
    # R38-1：闭空间其实是 **MDL** 侧的东西（doc.GetClosedVolumes 在只开工程时为空）
    calls = inter.setdefault("call_errors", {})

    def _call(host, name, *args):
        """统一走泛型 `call()`：**手册未必收录的成员**（如 CreateCondBoussinesqBaseTemp）
        只能这样试 —— 物化包装只覆盖目录里有的成员（R41）。

        "成员不存在"与"返回空"必须分清：前者是 `com_error`（宿主没有该接口），
        后者是"有接口但这台机器上没有对象"。故把异常记进 `call_errors`。
        """
        try:
            return _unwrap(host.call(name, *args))
        except Exception as exc:  # noqa: BLE001
            calls[name] = type(exc).__name__ + ": " + str(exc)[:90]
            return None

    def _make_mdl():
        """R41：拿到 MDL 的关键一步是 `MDLWizard.CreateMDL`（此前只在 R40 里 Begin 了向导）。"""
        diag = inter.setdefault("mdl_probe", {})
        try:
            mg.BeginMDLWizard()
            diag["begin"] = "ok"
        except Exception as exc:  # noqa: BLE001
            diag["begin"] = type(exc).__name__ + ": " + str(exc)
        wiz = _unwrap(mg.GetMDLWizard())
        diag["wizard"] = type(wiz).__name__ if wiz is not None else None
        if wiz is not None:
            got = _call(wiz, "CreateMDL")
            diag["CreateMDL"] = "None" if got is None else repr(got)[:40]
        mdl = mg.GetMDL()
        raw = getattr(mdl, "raw", None)
        diag["mdl_raw_is_none"] = raw is None
        return mdl if raw is not None else None

    def _mdl_cvol():
        mdl = mg.GetMDL()
        for getter, args in (("GetClosedVolumes", ()),
                             ("QueryClosedVolumeByIndex", (0,)),
                             ("GetStoredClosedVolumes", (False,))):
            try:
                res = (getattr(mdl, getter)(*args) if args
                       else getattr(mdl, getter)())
            except Exception:  # noqa: BLE001
                continue
            first = _first(res) if args == () else res
            if first is not None:
                return first
        return None

    _try("ClosedVolume", _mdl_cvol, "chain:mg.GetMDL().GetClosedVolumes")
    # R41：MDL 建立 → 闭空间 → **闭空间的材料项**就是 PropItem
    def _mdl_chain():
        mdl = _make_mdl()
        if mdl is None:
            return None
        for getter, args in (("GetClosedVolumes", ()),
                             ("QueryClosedVolumeByIndex", (0,))):
            res = _call(mdl, getter, *args)
            if res is not None:
                return res
        _call(mdl, "SelectAllFace", True)
        made = _call(mdl, "CreateClosedVolumeFromSelectedFace", "R41cvol")
        if made is not None:
            return made
        return _call(mdl, "QueryClosedVolumeByIndex", 0)

    _try("ClosedVolume", _mdl_chain, "chain:wizard.CreateMDL → mdl.GetClosedVolumes")

    def _cvol_propitem():
        cvol = out.get("ClosedVolume")
        if cvol is None:
            return None
        for getter in ("GetMaterial", "GetPhaseMaterial"):
            got = _call(cvol, getter)
            if got is not None:
                return got
        return None

    _try("PropItem", _cvol_propitem, "chain:ClosedVolume.GetMaterial")

    # R41：MapCond 有直建接口（Doc.CreateMapCond / QueryMapCondByName）
    def _mapcond_direct():
        for name, args in (("CreateMapCond", ()),
                           ("GetUnusedMapCondName", ("R41map",))):
            got = _call(doc, name, *args)
            if got is not None and name == "CreateMapCond":
                return got
        names = _call(doc, "GetAllMapCondNames")
        first = _first(names) if names is not None else None
        if first:
            return _call(doc, "QueryMapCondByName", first)
        return None

    _try("MapCond", _mapcond_direct, "chain:Doc.CreateMapCond")

    # R41：CondMapForStructure 的手册无创建器 —— 用泛型 call 试手册外成员
    def _cmap_direct():
        got = _call(conds, "CreateCondMapForStructure", "R41cms")
        if got is not None:
            return got
        return _call(conds, "QueryCondMapForStructureByName", "R41cms")

    _try("CondMapForStructure", _cmap_direct,
         "chain:conds.call(CreateCondMapForStructure)")

    # R41：CondBoussinesqBaseTemp 同样无创建器（手册只有 QueryByName）
    def _bouss_direct():
        got = _call(conds, "CreateCondBoussinesqBaseTemp", "R41bouss")
        if got is not None:
            return got
        return _call(conds, "QueryCondBoussinesqBaseTempByName", "R41bouss")

    _try("CondBoussinesqBaseTemp", _bouss_direct,
         "chain:conds.call(Create/QueryCondBoussinesqBaseTemp)")

    # R38-1：PropItem 也可以从多相条件的材料项拿
    def _propitem_cond():
        for maker, getter in (("GetCondMultiphaseHandling", "GetPrimaryMaterial"),
                              ("CreateCondMultiphaseHandling",
                               "GetPrimaryMaterial"),
                              ("GetCondMultiphaseMaterial", "GetPhaseMaterial")):
            try:
                cond = getattr(conds, maker)("R38mh")
            except Exception:  # noqa: BLE001
                continue
            try:
                obj = getattr(cond, getter)()
            except Exception:  # noqa: BLE001
                continue
            if obj is not None:
                return obj
        return None

    _try("PropItem", _propitem_cond,
         "chain:MultiphaseHandling.GetPrimaryMaterial")
    _try("SpecialRegion", lambda: _first(doc.GetSpecialRegions()),
         "chain:doc.GetSpecialRegions")
    # CondCoSim 需要 (name, apptype, interfacetype) 三个参数
    _try("CondCoSim", lambda: conds.CreateCondCoSim("R37cosim", 0, 0),
         "chain:conds.CreateCondCoSim(name,0,0)")
    # CondCoSimRegion：从 CoSim 条件拿区域，再 GetOwner()
    _cosim = out.get("CondCoSim")
    if _cosim is None:
        # R38-1：工程里可能已有 CoSim 条件（ldc 类算例），直接用现成的
        try:
            _cosim = _unwrap(conds.GetCondCoSim())
            if _cosim is not None:
                out["CondCoSim"] = _cosim
                obtained["CondCoSim"] = "chain:conds.GetCondCoSim"
        except Exception:  # noqa: BLE001
            _cosim = None

    def _cosim_region():
        reg = _first(_call(_cosim, "GetCoSimRegions"))
        if reg is None:
            return None
        return _call(reg, "GetOwner")

    if _cosim is not None:
        _try("CondCoSimRegion", _cosim_region, "chain:GetCoSimRegions()[0].GetOwner")
    else:
        errors["CondCoSimRegion"] = ("前置对象 CondCoSim 未取到（见其条目）——"
                                     "GetOwner() 需要 CoSim 区域实例")
    # MapCond：CondMapForStructure.GetValue(key)
    _cmap = inter.get("cmap")

    def _mapcond():
        for key in ("default", "1", "map", "value"):
            try:
                obj = _cmap.GetValue(key)
            except Exception:  # noqa: BLE001
                continue
            if obj is not None:
                return obj
        return None

    if _cmap is not None:
        _try("MapCond", _mapcond, "chain:CondMapForStructure.GetValue(key)")
    else:
        errors["MapCond"] = ("前置对象 CondMapForStructure 未取到 —— "
                             "MapCond 只能由它的 GetValue(key) 产出")
    # PropItem：CondInitial.GetPhaseMaterial（材料属性项）
    _condinitial = inter.get("condinitial")

    def _propitem():
        for getter in ("GetPhaseMaterial", "GetPrimaryMaterial"):
            try:
                obj = getattr(_condinitial, getter)()
            except Exception:  # noqa: BLE001
                continue
            if obj is not None:
                return obj
        return None

    if _condinitial is not None:
        _try("PropItem", _propitem, "chain:CondInitial.GetPhaseMaterial")
    else:
        errors["PropItem"] = ("前置对象 CondInitial 未取到；且工程未注册材料 —— "
                              "PropItem 经 CondInitial.GetPhaseMaterial 产出")
    # CondBoussinesqBaseTemp：先建同名条件，再按名查
    def _bouss():
        conds.CreateCondBoussinesqBaseTemp("R37bouss")
        return conds.QueryCondBoussinesqBaseTempByName("R37bouss")

    _try("CondBoussinesqBaseTemp", _bouss, "chain:Create+QueryByName")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="标题名 vs 签名名 实机裁定")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--project", type=Path, action="append", default=None,
                    help="用哪个工程建实例，可重复（R38-1：不同工程提供不同对象）")
    ap.add_argument("--sweep", action="store_true",
                    help="R42-1：对已取到实例的类做**成员可用性普查**"
                         "（GetIDsOfNames 逐个解析，零副作用）")
    ap.add_argument("--evidence-run", default="",
                    help="R50-2：本轮标签（轮次/日期）—— 写进证据，供逐条复验追溯")
    ap.add_argument("--guard-audit", type=int, default=0,
                    help="R49-2：抽样 N 个类量验身闸门的误放率（0=不量）")
    ap.add_argument("--auto-budget", type=float, default=300.0,
                    help="R45-1：自动配方扩面的时间预算（秒）；超时后如实记为未尝试")
    ap.add_argument("--with-mdl", action="store_true",
                    help="R40-1：走 MDL 流程造闭空间（选全部面 → 建闭空间）再裁定")
    ap.add_argument("--kicker", action="store_true",
                    help="R47-2：另取 Kicker 启动器对象，把 Kicker.* 三个类也普查")
    ap.add_argument("--keep-host", action="store_true")
    args = ap.parse_args(argv)
    pairs = mismatches()
    projects = args.project or [BOX]
    result = {"pairs": len(pairs), "targets": TARGETS, "verdicts": [],
              "object_probe": {}, "pairs_unreachable": [],
              "with_mdl": bool(args.with_mdl),
              "projects": [str(p) for p in projects]}
    import automation.host_boot as host_boot
    from automation import scflowpre_api as api
    t0 = time.time()
    pid = host_boot.cold_boot()
    print("[r35-1] cold boot pid=" + str(pid), flush=True)
    ctx: dict = {}
    # R43-2：普查状态按**优先级**累积（resolved > unknown_name > error）。
    # 多工程会话里，先取到的对象在 OpenProject 换工程后会变成空对象
    # （实测 Octree 的 28 个成员全报 AttributeError(NoneType)）——
    # 所以普查必须**逐工程**做，不能让旧工程的实例拖到最后再查。
    sweep_acc: dict = {}
    sweep_prio = {"resolved": 3, "unknown_name": 2}
    # 走仓内桥的附着逻辑：ROT 附着失败会自动回退 Dispatch（实测裸
    # GetActiveObject 会 MK_E_UNAVAILABLE = -2147221021）
    sess = api.ScFlowpreSession()
    ok = False
    for _ in range(6):
        if sess.connect():
            ok = True
            break
        time.sleep(5)
    if not ok:
        result["context_error"] = "session.connect 失败: " + str(api.last_error)
        print("[r35-1] " + str(result["context_error"]))
    def _empty(obj) -> bool:
        """对象是否**空壳**（ComObject 包了个 None / None 本身）。"""
        if obj is None:
            return True
        unwrapped = _unwrap(getattr(obj, "raw", obj))
        return unwrapped is None

    def _create_conds(conds) -> int:
        """R44-1：按目录里的 `CreateCond*` 批量建条件实例，供普查扩面。

        这条路子由条件收割工具验证过（一次会话 58/58 create err=0）；
        参数按"1 参 → 3 参 → 2 参"退让，多参创建器（如 `CreateCondCoSim(name, apptype,
        interfacetype)`）也能试到。
        """
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        methods = (cat["classes"].get("Conditions") or {}).get("methods") or {}
        made = 0
        for meth in sorted(methods):
            if not meth.startswith("CreateCond"):
                continue
            cls = "Cond" + meth[len("CreateCond"):]
            if cls not in cat["classes"] or ctx.get(cls) is not None:
                continue
            name = "R44" + cls
            for args in ((name,), (name, 0, 0), (name, 0)):
                try:
                    obj = conds.call(meth, *args)
                except Exception as exc:  # noqa: BLE001
                    (inter.setdefault("call_errors", {}))[meth] = (
                        type(exc).__name__ + ": " + str(exc)[:80])
                    continue
                cand = _unwrap(obj)
                if cand is not None and not _empty(cand):
                    ctx[cls] = cand
                    via[cls] = "CreateCond*:" + meth
                    made += 1
                    break
        return made

    def _raw(obj):
        """拆 typed 包装 + **拆 tuple/数组**。

        实测（R38-1）：`conds.GetCondCoSim()` / `GetCoSimRegions()` 这类返回的是
        tuple，直接拿去 `GetIDsOfNames` 会抛 AttributeError（'tuple' object has no
        attribute ...），于是把**能解析的名字误判成 neither** —— 假否证。
        """
        return _unwrap(getattr(obj, "raw", obj))

    cat_all = json.loads(CATALOG.read_text(encoding="utf-8"))
    _auto_state: dict = {}

    def _auto_expand() -> int:
        """R45-1：按自动配方扩面（逐工程累积，只补还没拿到的类）。

        配方来自两处：目录里**声明在已持有宿主上**的构造/取用成员，
        以及类级 instance 配方。三层保护：
        * 参数按阶梯退让（1 参 → 3 参 → 2 参 → 0 参），多参创建器也能试到；
        * **验身**（独有成员解析率 ≥ 半数）——拿错对象会把别人的成员判成
          「宿主未实现」，那是假否证（CondOversetGap 的配方写的是 CreateCondSpray）；
        * 总时间预算（--auto-budget），超时就停并如实记名，不让一次卡死毁掉整轮。
        """
        if "deadline" not in _auto_state:
            _auto_state["deadline"] = time.time() + args.auto_budget
        # R49-1：取实例前先"全选"（GetSelected* 只在有选中时给对象）
        sel, sel_err = prime_selection(ctx, cat_all)
        if sel:
            result["selection_primed"] = sorted(set(sel))
        if sel_err:
            result.setdefault("selection_prime_errors", {}).update(sel_err)
        held = {}
        for key, obj in list(ctx.items()):
            cls = CTX_ALIASES.get(key, key)
            if obj is not None and cls in cat_all["classes"]:
                held[key] = cls
        index = member_name_index(cat_all)
        # R47-1：真实对象名池（Query<X>ByName 类配方要用真名字）
        pool = harvest_names(cat_all, ctx,
                             lambda o, m: _unwrap(api.ComObject(o).call(m)))
        if pool:
            result["name_pool"] = pool
        rejected = set(result.get("identity_rejected") or [])
        empty_hits: dict = {}
        # **不并进 call_errors**：那里的错误被"手册标题裁定"与 dispatch_account 当
        # "宿主没有这个接口"的证据用，而自动配方会在**多个宿主**上试同一个名字
        # （CreateCondCoSim 在 Doc 上当然没有）—— 并进去会把 CondCoSim 这类
        # "接口有、对象还没造出来"的条目误判成 host-interface-absent。
        calls: dict = {}
        made = 0
        for cls in sorted(cat_all["classes"]):
            if cls in ctx or cls in rejected:
                continue
            if time.time() > _auto_state["deadline"]:
                result.setdefault("auto_timeouts", []).append(cls)
                continue
            name = "R45" + cls.split(".")[-1]
            ladders = arg_ladder(name)
            rejected_here: list = []
            for plan in auto_plans(cat_all, cls, held)[:12]:
                host_raw = ctx.get(plan["host"])
                if host_raw is None:
                    continue
                host = api.ComObject(host_raw)
                # 手册给的那组实参先试；不成再按阶梯退让（两边都不放弃）
                tries = ([plan["args"]] if plan["args"] is not None else []) + ladders
                if "ByName" in plan["member"] and pool:
                    # R47-1：*ByName 类取法先用**真名字**试（池里的是宿主上存在的
                    # 对象名；用生成的 "R45Xxx" 必然查不到）
                    tries = ([(n,) for n in pool[:8]]
                             + [(n, 0) for n in pool[:4]] + tries)
                for argsin in tries:
                    if argsin is None:
                        continue
                    try:
                        got = host.call(plan["member"], *argsin)
                    except Exception as exc:  # noqa: BLE001
                        calls[plan["host"] + "." + plan["member"]] = (
                            type(exc).__name__ + ": " + str(exc)[:80])
                        continue
                    cand = _raw(got) if got is not None else None
                    if cand is None or _empty(cand) or not _is_com(cand):
                        # 试过、但**返回空/标量**：这是 R46-1 归因的主要证据
                        # （"本机工程里没有这类对象"≠"宿主没这个接口"）
                        empty_hits.setdefault(cls, plan["how"])
                        continue
                    sample = distinctive_members(cat_all, cls, index)
                    ok, detail = identity_ok(cand, sample)
                    if not ok:
                        # 这条配方给的是**别的类**的对象 → 换下一条配方再试
                        # （不能一票否决：手册配方错不代表目录配方也错）
                        rejected_here.append(cls + " <- " + plan["how"])
                        result.setdefault("identity_detail", {})[
                            cls + " | " + plan["how"]] = detail
                        continue
                    ctx[cls] = cand
                    via[cls] = "auto:" + plan["how"]
                    result.setdefault("auto_obtained", {})[cls] = plan["how"]
                    made += 1
                    break
                if cls in ctx:
                    break
            if cls not in ctx and rejected_here:
                result.setdefault("identity_rejected", []).extend(rejected_here)
                rejected.add(cls)      # 本轮别再对这个类做同一批尝试
        if calls:
            result.setdefault("auto_call_errors", {}).update(calls)
        # 后来拿到了的类，不算"试过返回空"
        for done in list(empty_hits):
            if done in ctx:
                empty_hits.pop(done)
        if empty_hits:
            result.setdefault("auto_empty_targets", {}).update(empty_hits)
        return made

    doc = sess.doc                          # typed 包装：内部走 _FlagAsMethod
    wanted = sorted({p["class"] for p in pairs})
    via = result.setdefault("obtained_via", {})
    if args.kicker:
        # R47-2：Kicker.* 与工程无关，一次性取（在最前面，失败不影响后续）
        _idx = member_name_index(cat_all)
        try:
            n_k = attach_kicker(ctx, via, result, _idx, cat_all)
            print("[r47] Kicker 对象接入 " + str(n_k) + " 个类", flush=True)
        except Exception as exc:  # noqa: BLE001
            result["kicker_error"] = type(exc).__name__ + ": " + str(exc)[:120]
    errors = result.setdefault("chain_errors", {})
    # R38-1：**一个会话里轮换多个工程** —— 不同工程提供不同对象（闭空间/材料/CoSim），
    # 已取到的类不再重复取（ctx 只增不减），未取到的继续在下一个工程里试。
    for proj in projects:
        try:
            if doc is None:
                raise RuntimeError("no document")
            if "Doc" not in ctx:
                ctx["Doc"] = _raw(doc)
            if "Application" not in ctx:
                try:
                    ctx["Application"] = _raw(sess.app)   # R43-1：白捡一类
                except Exception:  # noqa: BLE001
                    pass
            # 顺序要紧：未打开工程时 GetConditions 抛 DISP_E_MEMBERNOTFOUND
            # （实测 -2147352573「找不到成员」），会把后面的实例全挡掉。
            # 另：**不要用裸 CDispatch 链式调用** —— win32com 会把未 flag 的方法
            # 当属性读（实测 QueryMeshingGroupByIndex(0) 抛 TypeError）。
            doc.OpenProject(str(proj))
            doc.WaitForWorker()
            print("[r38] 打开工程 " + Path(proj).name, flush=True)
            conds_typed = doc.GetConditions()   # typed：实例构建要走它的 call()
            ctx.setdefault("Conditions", _raw(conds_typed))
            inter: dict = {}   # COM 对象另放：evidence 必须可 JSON 序列化
            try:
                inter["cmap"] = conds_typed.CreateCondMapForStructure("R38map")
                via["CondMapForStructure"] = "CreateCondMapForStructure"
            except Exception as exc:  # noqa: BLE001
                errors["CondMapForStructure"] = (
                    "CreateCondMapForStructure -> " + type(exc).__name__
                    + ": " + str(exc))
            try:
                inter["condinitial"] = conds_typed.CreateCondInitial("R38init")
            except Exception:  # noqa: BLE001
                pass
            mg = doc.QueryMeshingGroupByIndex(0)
            ctx.setdefault("MeshingGroup", _raw(mg))
            ctx.setdefault("MeshingGroupSetting",
                           _raw(mg.GetMeshingGroupSetting()))
            if _empty(ctx.get("Octree")):
                # 空对象（工程里还没建八叉树）不要占位 —— 留着它，后面的工程
                # 才有机会提供一个真对象（R43：ldc 里 GetOctree() 是空壳，
                # 导致 Octree 的 28 个成员全部报 AttributeError(NoneType)）
                try:
                    cand = _raw(mg.GetOctree())
                    if not _empty(cand):
                        ctx["Octree"] = cand
                    else:
                        result.setdefault("empty_objects", []).append("Octree")
                except Exception:  # noqa: BLE001
                    pass
            for name, getter in (("OctParam", "GetOctParam"),
                                 ("Env", "GetEnv"),
                                 ("HybridParam", "GetPresetHybridParam")):
                if name in ctx:
                    continue
                try:
                    ctx[name] = _raw(getattr(doc, getter)())
                except Exception:  # noqa: BLE001
                    pass
            if "MDLWizard" not in ctx:
                try:
                    mg.BeginMDLWizard()
                    ctx["MDLWizard"] = _raw(mg.GetMDLWizard())
                except Exception:  # noqa: BLE001
                    pass
            if False and args.with_mdl and "ClosedVolume" not in ctx:   # R41：交给 _chains
                # R40-1：闭空间不是"打开工程就有"——它在 MDL 里由面区域生成。
                # 这里走最省事的一条：MDL 选全部面 → 由选中面建闭空间。
                try:
                    mdl = mg.GetMDL()
                    # 注意：拿到的是**包着空对象的 ComObject**，不是 None 本身 ——
                    # 于是 mdl is not None 成立，真正炸在 _invoke(None, ...)，
                    # 报错文本是 "'NoneType' object has no attribute ..."，
                    # 光看它会误以为是成员名写错（R40-1 实测）。必须看底层 raw。
                    if mdl is None or getattr(mdl, "raw", None) is None:
                        errors["ClosedVolume"] = (
                            "mg.GetMDL() 底层返回 None（ComObject 包了个空对象）："
                            "闭空间必须建立在 MDL 之上 —— 该工程尚未完成 MDL/BAM 建模流程")
                        raise _MdlUnavailable()
                    # 注意：MDL 不在 TYPED_CLASSES 里 → 没有物化包装，
                    # 必须走泛型 call()（R40-1 实测：getattr 直接 AttributeError）
                    steps = (("mdl.call(SelectAllFace, True)",
                              lambda: mdl.call("SelectAllFace", True)),
                             ("mdl.call(CreateClosedVolumeFromSelectedFace)",
                              lambda: mdl.call(
                                  "CreateClosedVolumeFromSelectedFace",
                                  "R40cvol")),
                             ("mdl.call(QueryClosedVolumeByIndex, 0)",
                              lambda: mdl.call("QueryClosedVolumeByIndex", 0)))
                    for step, fn in steps:
                        try:
                            res = _unwrap(fn())
                        except Exception as exc:  # noqa: BLE001
                            errors["ClosedVolume"] = (
                                step + " -> " + type(exc).__name__ + ": "
                                + str(exc))
                            continue
                        if res is not None and not isinstance(res, bool):
                            ctx["ClosedVolume"] = _raw(res)
                            via["ClosedVolume"] = "chain:" + step
                            errors.pop("ClosedVolume", None)
                            print("   + ClosedVolume <- " + step, flush=True)
                            break
                        errors["ClosedVolume"] = step + " -> 返回空/布尔"
                except _MdlUnavailable:
                    pass                      # 原因已写进 errors
                except Exception as exc:  # noqa: BLE001
                    errors["ClosedVolume"] = ("mdl 流程 -> "
                                              + type(exc).__name__ + ": "
                                              + str(exc))
            # R44-1：批量造条件实例（普查扩面的主力）
            if args.sweep:
                made = _create_conds(conds_typed)
                if made:
                    print("   + 批量条件实例 " + str(made) + " 个", flush=True)
            # R37-1：链式实例（数组型 getter / 多参数 Create / 二级 GetOwner）
            for cls, obj in _chains(doc, conds_typed, mg, via, inter,
                                    errors).items():
                if cls not in ctx:
                    ctx[cls] = _raw(obj)
                    print("   + " + cls + " <- chain", flush=True)
            # R36-1：名字家族试取（typed host：裸 CDispatch 会静默全失败）
            for cls in wanted:
                if ctx.get(cls) is not None:
                    continue
                obj, how = _obtain(cls, conds_typed, doc, mg)
                cand = _raw(obj) if obj is not None else None
                # 空壳（ComObject 包了个 None）**不能**收进 ctx：
                # 收下之后普查会对它的每个成员报 AttributeError(NoneType)，
                # 28 条噪声把真结论埋掉（R43 实测 Octree）
                if cand is None or _empty(cand):
                    # 空壳/空结果：**记下来**，否则这个类在普查里"消失"就没归因
                    result.setdefault("empty_objects", []).append(cls)
                    errors[cls] = (str(how) + " -> 空对象（工程里没有该对象）")
                else:
                    ctx[cls] = cand       # _raw 会拆 tuple（R38-1）
                    via[cls] = how
                    print("   + " + cls + " <- " + str(how), flush=True)
            # R45-1：自动配方扩面（三层优先级 + 验身 + 时间预算）
            if args.sweep:
                n_auto = _auto_expand()
                if n_auto:
                    print("   + 自动配方扩面 " + str(n_auto) + " 类", flush=True)
            result["mdl_probe"] = inter.get("mdl_probe") or {}
            # R43-2：**每个工程**都把当前 ctx 普查一遍，状态按优先级累积
            if args.sweep:
                empty_objs: list = result.setdefault("empty_objects", [])
                for cls, obj in list(ctx.items()):
                    if _empty(obj):
                        empty_objs.append(cls)
                        continue
                    # R45-1：ctx 键未必是目录类名（Application → Kicker.Application）。
                    # 普查必须记在**目录类名**上，否则同一类被记两次、别名键还会
                    # 造出一个目录里不存在的"类"（假覆盖）。
                    cat_cls = CTX_ALIASES.get(cls, cls)
                    if cat_cls not in cat_all["classes"]:
                        result.setdefault("swept_unmapped", []).append(cls)
                        continue
                    cinfo = cat_all["classes"].get(cat_cls) or {}
                    if not (cinfo.get("methods") or cinfo.get("properties")):
                        # 手册页**一个成员都没有**的类（CondALECancel / ParticleRegion…）：
                        # 对象拿到了也"没成员可查"。单列一桶 —— 混进 classes_swept 会把
                        # 覆盖率说虚，算"未普查"又不实（我们确实取到了它）。
                        result.setdefault("no_member_classes", []).append(cat_cls)
                        continue
                    states: dict = {}
                    for kind in ("methods", "properties"):
                        for mem, entry in (cinfo.get(kind) or {}).items():
                            # 属性键可能带类型后缀（`Visible(BOOL)`）——
                            # 宿主认的是括号前那段；不剥后缀会把**已实现**的属性
                            # 误判成"宿主未实现"（R43 实测 2 例）
                            disp = (entry.get("dispatch_name")
                                    or entry.get("signature_name")
                                    or mem.split("(", 1)[0])
                            st = _resolve(obj, disp)
                            # R45-1：手册标题名与签名名不一致时（R34-3 的 41 处），
                            # 只试派发名会把**能用的那个名字**判成"宿主未实现"
                            # （实测 ClosedVolume.SelectFace：签名名 SetSelectFaces
                            # 不认，标题名 SelectFace 认）。故派发名不通时再试成员键。
                            if st == "unknown_name" and disp != mem:
                                alt = _resolve(obj, mem.split("(", 1)[0])
                                if alt == "resolved":
                                    st = "resolved"
                                    result.setdefault(
                                        "resolved_via_member_key", []).append(
                                            cat_cls + "." + mem)
                            states[mem] = st
                    # R45-1 **验身后置闸**：拿错对象（别名写错、配方给的别家对象）
                    # 会把整类成员判成"宿主未实现" —— 那是假否证，比没普查更糟
                    # （实测：把会话 Application 当成 Kicker.Application，
                    # 9 个成员里 8 个 unknown_name）。整类未知过半就**整类不记**，
                    # 宁可停在"未普查"。
                    if sweep_class_verdict(states) == "suspect":
                        result.setdefault("swept_suspect", {})[cat_cls] = {
                            "total": len(states),
                            "unknown": sum(1 for s in states.values()
                                           if s == "unknown_name")}
                        # 取得路径**作废**：这个类没进普查，就别说"拿到了"
                        # （R47 实测：CondParticleCounter 的配方给的是别的条件对象，
                        # 验身否掉后仍留在 obtained_via/auto_obtained 里 → 自相矛盾）
                        via.pop(cls, None)
                        (result.get("auto_obtained") or {}).pop(cat_cls, None)
                        continue
                    for mem, st in states.items():
                        slot = sweep_acc.setdefault(cat_cls, {})
                        old = slot.get(mem)
                        if old is None or (sweep_prio.get(st, 0)
                                           > sweep_prio.get(old, 0)):
                            slot[mem] = st
            result.setdefault("call_errors", {}).update(
                inter.get("call_errors") or {})
            if all(ctx.get(c) is not None for c in wanted):
                break                      # 全拿到就不必再开工程
        except Exception as exc:  # noqa: BLE001
            result.setdefault("context_errors", []).append(
                Path(proj).name + ": " + type(exc).__name__ + ": " + str(exc))
            print("[r38] 工程 " + Path(proj).name + " 取实例失败: "
                  + type(exc).__name__ + ": " + str(exc), flush=True)
    # R46-2：**每个拿到实例的类都要能答"怎么拿到的"** —— 会话直取的核心对象
    # （Doc/Conditions/MeshingGroup…）此前没有 via 条目，覆盖率报表答不上来
    for _key in ctx:
        via.setdefault(_key, "session:会话/文档直取")
    # 没拿到实例、也没留下链式错误的类，补一条**兜底原因**（不许静默）
    for cls in wanted:
        if ctx.get(cls) is None:
            errors.setdefault(
                cls, "各工程的 Get*/Create*/Query* 都未产出实例（见 object_probe）")
    # R42-1 / R43-1：成员可用性普查（逐工程累积，见 sweep_acc）+ 覆盖率口径。
    if args.sweep:
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        classes_total = len(cat["classes"])
        members_total = sum(len(i.get("methods") or {})
                            + len(i.get("properties") or {})
                            for i in cat["classes"].values())
        per_class: dict = {}
        for cls, states in sorted(sweep_acc.items()):
            unknown = sorted(m for m, st in states.items()
                             if st == "unknown_name")
            errs = sorted(m for m, st in states.items()
                          if str(st).startswith("error:"))
            per_class[cls] = {"total": len(states),
                              "resolved": sum(1 for st in states.values()
                                               if st == "resolved"),
                              "unknown": unknown, "errors": errs}
        swept_members = sum(v["total"] for v in per_class.values())
        empty_set = set(result.get("empty_objects") or [])
        # 同一类可能在**早期工程**里是空的（box.pph 没建八叉树），在后面工程里
        # 取到了真对象 —— 已普查的类不许再算"取不到实例"，否则三桶会重叠
        # （R45 实测：ClosedVolume / Octree 同时在两个桶里，199 类数出 201）
        empty_set -= set(per_class)
        # 三桶互斥：已普查 / 试过但拿不到对象（empty_objects）/ 从未尝试（unswept）
        no_member = (set(result.get("no_member_classes") or [])
                     - set(per_class) - empty_set)
        # 四桶互斥：已普查 / 取不到实例 / 取到但手册无成员 / 从未尝试
        unswept = sorted(set(cat["classes"]) - set(per_class) - empty_set
                         - no_member)
        result["availability"] = {c: {"total": v["total"],
                                      "resolved": v["resolved"],
                                      "unknown": len(v["unknown"]),
                                      "errors": len(v["errors"])}
                                  for c, v in per_class.items()}
        sweep_path = ROOT / "schemas" / "host_member_availability.json"
        # R49-2：验身闸门误放率（真对象 × 别家的独有成员，抽样实测）
        if args.guard_audit:
            result["guard_audit"] = audit_identity_guard(
                cat, ctx, member_name_index(cat), args.guard_audit,
                result.get("identity_detail") or {})
            ga = result["guard_audit"]
            print("[r49] 验身闸门：自类通过 " + str(ga["self_pass"]) + "/"
                  + str(ga["self_total"]) + "（误杀 " + str(ga["false_kill"])
                  + "）；跨类 " + str(ga["cross_trials"]) + " 次里误放 "
                  + str(ga["false_accept"]) + "（"
                  + str(ga["false_accept_rate"]) + "）；被否 "
                  + str(ga.get("rejections")) + " 条中近阈（|2r−s|≤1）"
                  + str(ga.get("fragile_rejections")), flush=True)
        # R50-2：**可复验串** —— 任取一条 host_absent / recipe_unreliable，
        # 都能追到"哪一轮、哪个日志、哪些工程、什么时候"
        result["evidence_run"] = {
            "round": args.evidence_run or "（未标轮次）",
            "when": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "log": str(args.json or ""),
            "projects": [Path(p).name for p in projects],
            "probe": "tools/dispatch_name_probe.py --sweep",
            "progid": PROGID,
        }
        sweep_path.write_text(json.dumps({
            "source": "tools/dispatch_name_probe.py --sweep（GetIDsOfNames）",
            "evidence_run": result.get("evidence_run") or {},
            "note": ("state=unknown_name ⇒ 宿主**未实现**该成员；"
                     "error:* ⇒ 探针侧问题（对象为空/过时），**不得**当宿主否证；"
                     "未出现在本表的类 = **未普查**（不等于已实现）"),
            "coverage": {"classes_swept": len(per_class),
                         "empty_objects": sorted(empty_set),
                         "empty_hints": {c: EMPTY_HINTS.get(c, "（未登记前置条件）")
                                         for c in sorted(empty_set)},
                         "classes_total": classes_total,
                         "no_member_classes": sorted(no_member),
                         "members_swept": swept_members,
                         "members_total": members_total,
                         "unswept_classes": unswept,
                         # R45-1：扩面的**过程证据**（哪些类靠哪条配方拿到、
                         # 哪些被判"拿错对象"、哪些超时没试、哪些 ctx 键不是目录类）
                         "auto_obtained": dict(sorted(
                             (result.get("auto_obtained") or {}).items())),
                         "identity_rejected": sorted(
                             result.get("identity_rejected") or []),
                         "identity_detail": result.get("identity_detail") or {},
                         "auto_timeouts": sorted(
                             set(result.get("auto_timeouts") or [])),
                         # R46-2：**每个类的取得路径**（链条/条件批量/自动配方）
                         "obtained_via": {CTX_ALIASES.get(k, k): v
                                          for k, v in sorted(via.items())
                                          if CTX_ALIASES.get(k, k)
                                          in cat["classes"]},
                         # R46-1：试过取法但返回空的类（归因证据）
                         "auto_empty_targets": dict(sorted(
                             (result.get("auto_empty_targets") or {}).items())),
                         "swept_unmapped": sorted(
                             set(result.get("swept_unmapped") or [])),
                         # 验身后置闸否掉的类（整类未知过半 = 拿错对象）
                         "swept_suspect": result.get("swept_suspect") or {},
                         # 派发名不通、成员键名通（R34-3 的标题/签名对）
                         "resolved_via_member_key": sorted(
                             set(result.get("resolved_via_member_key") or [])),
                         # R49-1：取实例前打过"全选"的成员（几何类靠它才有对象）
                         "selection_primed": sorted(
                             set(result.get("selection_primed") or [])),
                         "selection_prime_errors": result.get(
                             "selection_prime_errors") or {},
                         # R49-2：验身闸门的误放率实测
                         "guard_audit": result.get("guard_audit") or {},
                         # R50-2：可复验串（逐条证据都能追到这一轮）
                         "evidence_run": result.get("evidence_run") or {}},
            "classes": {c: {"total": v["total"], "resolved": v["resolved"],
                            "unknown": v["unknown"],
                            "errors": v["errors"]}
                        for c, v in per_class.items()},
            "availability": {c: dict(states)
                             for c, states in sweep_acc.items()},
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        n_unknown = sum(len(v["unknown"]) for v in per_class.values())
        n_err = sum(len(v["errors"]) for v in per_class.values())
        print("[r43] 普查 " + str(len(per_class)) + "/" + str(classes_total)
              + " 类、" + str(swept_members) + "/" + str(members_total)
              + " 成员 → " + sweep_path.name + "；未实现 " + str(n_unknown)
              + "，探针侧错误 " + str(n_err)
              + "，自动配方 " + str(len(result.get("auto_obtained") or {}))
              + " 类（验身否 " + str(len(result.get("identity_rejected") or []))
              + "，超时 " + str(len(set(result.get("auto_timeouts") or [])))
              + "）", flush=True)
        for cls, v in sorted(per_class.items()):
            if v["unknown"] or v["errors"]:
                print("   " + cls + " unknown=" + str(len(v["unknown"]))
                      + " errors=" + str(len(v["errors"]))
                      + " " + json.dumps((v["unknown"] + v["errors"])[:6],
                                          ensure_ascii=False), flush=True)

    for name, obj in ctx.items():
        result["object_probe"][name] = _has_type_info(obj)
    by_class: dict = {}
    for p in pairs:
        by_class.setdefault(p["class"], []).append(p)
    for cls, items in sorted(by_class.items()):
        obj = ctx.get(cls)
        if obj is None:
            for p in items:
                result["pairs_unreachable"].append(
                    {"class": cls, "heading": p["heading"],
                     "signature": p["signature"], "reason": "无实例"})
            continue
        for p in items:
            v = {"class": cls, "heading": p["heading"],
                 "signature": p["signature"],
                 "heading_state": _resolve(obj, p["heading"]),
                 "signature_state": _resolve(obj, p["signature"])}
            if (v["heading_state"] == "resolved"
                    and v["signature_state"] != "resolved"):
                v["verdict"] = "heading"
            elif (v["signature_state"] == "resolved"
                    and v["heading_state"] != "resolved"):
                v["verdict"] = "signature"
            elif v["heading_state"] == v["signature_state"] == "resolved":
                v["verdict"] = "both"
            elif (str(v["heading_state"]).startswith("error:")
                  or str(v["signature_state"]).startswith("error:")):
                # 解析本身就报错（对象形态/取法问题）→ **不能**算"宿主不认"，
                # 否则就是探针侧缺陷造出的假否证（R38-1 实测：tuple 未拆包）
                v["verdict"] = "unknown"
            else:
                v["verdict"] = "neither"
            if v["verdict"] == "unknown":
                # 诊断：把对象形态记下来（"tuple 未拆包"这类假否证就是靠它定位的）
                v["object_type"] = type(obj).__name__
                v["object_repr"] = repr(obj)[:80]
            result["verdicts"].append(v)
    if not args.keep_host:
        result["killed_hosts"] = host_boot.kill_all_hosts()
    result["seconds"] = round(time.time() - t0, 1)
    tally: dict = {}
    for v in result["verdicts"]:
        tally[v["verdict"]] = tally.get(v["verdict"], 0) + 1
    result["tally"] = tally
    print("[r35-1] 裁定: " + json.dumps(tally) + " | 无实例 "
          + str(len(result["pairs_unreachable"])))
    for v in result["verdicts"]:
        print("   " + v["verdict"].ljust(9) + v["class"] + "." + v["heading"]
              + " / " + v["signature"])
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    # 紧凑裁定表：{类: {目录键: 宿主接受的名字}} —— typed 桥据此选派发名
    # （"both" 保留目录键，避免无谓漂移；"neither" 不入表）
    # 与既有裁定表**合并**（单调累积：某次运行取不到实例的类，保留上次结论）
    resolved: dict = {}
    prev_path = ROOT / "schemas" / "name_verdicts.json"
    if prev_path.is_file():
        try:
            prev = json.loads(prev_path.read_text(encoding="utf-8"))
            for k, v in (prev.get("resolved") or {}).items():
                resolved[k] = dict(v)
        except Exception:  # noqa: BLE001
            pass
    for v in result["verdicts"]:
        name = {"heading": v["heading"], "signature": v["signature"],
                "both": v["heading"]}.get(v["verdict"])
        if name:
            resolved.setdefault(v["class"], {})[v["heading"]] = name
    out = {
        "source": "tools/dispatch_name_probe.py（运行时 GetIDsOfNames，151 工程语料外）",
        "method": "IDispatch::GetIDsOfNames 只做名字解析、不调用方法",
        "note": "宿主不实现 GetTypeInfo 且未注册类型库；未裁定的对（需 Cond* 实例）不在此表",
        "resolved": resolved,
        "tally": result["tally"],
    }
    path = prev_path
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print("[r35-1] 已写 " + str(path) + "（" + str(len(resolved)) + " 类）")
    print("SUMMARY: " + json.dumps({"verdicts": len(result["verdicts"]),
                                    "tally": tally}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
