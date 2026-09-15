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
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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


def _unwrap(obj, depth: int = 4):
    """递归拆 tuple/数组（取首元素，最多 `depth` 层）。

    win32com 对"多返回值"成员返回 tuple；实测 `conds.GetCondCoSim()` 还会**套一层**
    —— 只拆一层仍拿到 tuple，于是名字解析抛 AttributeError，
    被误判成"宿主不认"（R38/R39 两次踩到，都是假否证）。
    """
    while depth and isinstance(obj, (tuple, list)) and obj:
        obj = obj[0]
        depth -= 1
    return obj


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
            out[cls] = obj
            obtained[cls] = how
        else:
            errors.setdefault(cls, how + " -> 返回空（工程里没有该对象）")

    # 数组型 getter → 取第一个
    _try("ClosedVolume", lambda: _first(doc.GetClosedVolumes(False)),
         "chain:doc.GetClosedVolumes")
    _try("ClosedVolume", lambda: _first(doc.GetClosedVolumes(True)),
         "chain:doc.GetClosedVolumes(True)")
    # R38-1：闭空间其实是 **MDL** 侧的东西（doc.GetClosedVolumes 在只开工程时为空）
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
        reg = _first(_cosim.GetCoSimRegions())
        if reg is None:
            return None
        return _unwrap(reg.GetOwner())

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
    ap.add_argument("--keep-host", action="store_true")
    args = ap.parse_args(argv)
    pairs = mismatches()
    projects = args.project or [BOX]
    result = {"pairs": len(pairs), "targets": TARGETS, "verdicts": [],
              "object_probe": {}, "pairs_unreachable": [],
              "projects": [str(p) for p in projects]}
    import automation.host_boot as host_boot
    from automation import scflowpre_api as api
    t0 = time.time()
    pid = host_boot.cold_boot()
    print("[r35-1] cold boot pid=" + str(pid), flush=True)
    ctx: dict = {}
    # 走仓内桥的附着逻辑：ROT 附着失败会自动回退 Dispatch（实测裸
    # GetActiveObject 会 MK_E_UNAVAILABLE = -2147221021）
    sess = api.ScFlowpreSession()
    verdicts_by_class: dict = {}
    ok = False
    for _ in range(6):
        if sess.connect():
            ok = True
            break
        time.sleep(5)
    if not ok:
        result["context_error"] = "session.connect 失败: " + str(api.last_error)
        print("[r35-1] " + str(result["context_error"]))
    def _raw(obj):
        """拆 typed 包装 + **拆 tuple/数组**。

        实测（R38-1）：`conds.GetCondCoSim()` / `GetCoSimRegions()` 这类返回的是
        tuple，直接拿去 `GetIDsOfNames` 会抛 AttributeError（'tuple' object has no
        attribute ...），于是把**能解析的名字误判成 neither** —— 假否证。
        """
        return _unwrap(getattr(obj, "raw", obj))

    doc = sess.doc                          # typed 包装：内部走 _FlagAsMethod
    wanted = sorted({p["class"] for p in pairs})
    via = result.setdefault("obtained_via", {})
    errors = result.setdefault("chain_errors", {})
    # R38-1：**一个会话里轮换多个工程** —— 不同工程提供不同对象（闭空间/材料/CoSim），
    # 已取到的类不再重复取（ctx 只增不减），未取到的继续在下一个工程里试。
    for proj in projects:
        try:
            if doc is None:
                raise RuntimeError("no document")
            if "Doc" not in ctx:
                ctx["Doc"] = _raw(doc)
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
            try:
                ctx.setdefault("Octree", _raw(mg.GetOctree()))
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
                if obj is not None:
                    ctx[cls] = _raw(obj)      # 必须走 _raw：它会拆 tuple（R38-1）
                    via[cls] = how
                    print("   + " + cls + " <- " + str(how), flush=True)
            if all(ctx.get(c) is not None for c in wanted):
                break                      # 全拿到就不必再开工程
        except Exception as exc:  # noqa: BLE001
            result.setdefault("context_errors", []).append(
                Path(proj).name + ": " + type(exc).__name__ + ": " + str(exc))
            print("[r38] 工程 " + Path(proj).name + " 取实例失败: "
                  + type(exc).__name__ + ": " + str(exc), flush=True)
    # 没拿到实例、也没留下链式错误的类，补一条**兜底原因**（不许静默）
    for cls in wanted:
        if ctx.get(cls) is None:
            errors.setdefault(
                cls, "各工程的 Get*/Create*/Query* 都未产出实例（见 object_probe）")
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
