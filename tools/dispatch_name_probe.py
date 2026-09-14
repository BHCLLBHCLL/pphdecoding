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
    """名字能否在该对象上解析（DISPID 命中 / UNKNOWNNAME / 其它错误）。"""
    try:
        import pythoncom
        dispid = obj._oleobj_.GetIDsOfNames(name)
        return "resolved" if dispid is not None else "resolved"
    except Exception as exc:  # noqa: BLE001
        low = str(exc).lower()
        if "unknown" in low or "-2147352570" in low:
            return "unknown_name"
        return "error:" + type(exc).__name__


def _has_type_info(obj) -> str:
    try:
        obj._oleobj_.GetTypeInfo()
        return "yes"
    except Exception as exc:  # noqa: BLE001
        return "no:" + type(exc).__name__


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="标题名 vs 签名名 实机裁定")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--keep-host", action="store_true")
    args = ap.parse_args(argv)
    pairs = mismatches()
    result = {"pairs": len(pairs), "targets": TARGETS, "verdicts": [],
              "object_probe": {}, "pairs_unreachable": []}
    import automation.host_boot as host_boot
    from automation import scflowpre_api as api
    t0 = time.time()
    pid = host_boot.cold_boot()
    print("[r35-1] cold boot pid=" + str(pid), flush=True)
    ctx: dict = {}
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
    def _raw(obj):
        return getattr(obj, "raw", obj)

    try:
        doc = sess.doc                      # typed 包装：内部走 _FlagAsMethod 派发
        if doc is None:
            raise RuntimeError("no document")
        ctx["Doc"] = _raw(doc)
        # 顺序要紧：未打开工程时 GetConditions 抛 DISP_E_MEMBERNOTFOUND
        # （实测 -2147352573「找不到成员」），会把后面的实例全挡掉。
        # 另：**不要用裸 CDispatch 链式调用** —— win32com 会把未 flag 的方法
        # 当属性读，实测 QueryMeshingGroupByIndex(0) 抛
        # "TypeError: 'bool' object is not callable"（R35-1 第二次踩）。
        doc.OpenProject(str(BOX))          # typed 包装只收 path（flag 缺省 False）
        doc.WaitForWorker()
        ctx["Conditions"] = _raw(doc.GetConditions())
        mg = doc.QueryMeshingGroupByIndex(0)
        ctx["MeshingGroup"] = _raw(mg)
        ctx["MeshingGroupSetting"] = _raw(mg.GetMeshingGroupSetting())
        ctx["Octree"] = _raw(mg.GetOctree())
        for name, getter in (("OctParam", "GetOctParam"),
                             ("Env", "GetEnv"),
                             ("HybridParam", "GetPresetHybridParam")):
            try:
                ctx[name] = _raw(getattr(doc, getter)())
            except Exception:  # noqa: BLE001
                pass
        try:
            mg.BeginMDLWizard()
            ctx["MDLWizard"] = _raw(mg.GetMDLWizard())
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        result["context_error"] = type(exc).__name__ + ": " + str(exc)
        print("[r35-1] 取实例失败: " + str(result["context_error"]))
    for name, obj in ctx.items():
        result["object_probe"][name] = _has_type_info(obj)
        print("   " + name + " GetTypeInfo: " + result["object_probe"][name],
              flush=True)
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
            else:
                v["verdict"] = "neither"
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
    resolved: dict = {}
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
    path = ROOT / "schemas" / "name_verdicts.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print("[r35-1] 已写 " + str(path) + "（" + str(len(resolved)) + " 类）")
    print("SUMMARY: " + json.dumps({"verdicts": len(result["verdicts"]),
                                    "tally": tally}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
