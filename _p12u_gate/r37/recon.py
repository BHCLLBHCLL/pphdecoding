import json, re, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
cat = json.loads(pathlib.Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
v = json.loads(pathlib.Path("_p12u_gate/r36/name_verdicts.json").read_text(encoding="utf-8"))
want = sorted({p["class"] for p in v["pairs_unreachable"]})
print("== 未裁定对的类 ==")
for cls in want:
    info = cat["classes"].get(cls) or {}
    print("--", cls)
    print("   instance:", str(info.get("instance"))[:110])
    print("   expl    :", str(info.get("explanation"))[:110])
print()
print("== 谁提供这些类的实例 ==")
for needle in ("PropDataBase", "ClosedVolume", "SpecialRegion", "CondCoSim"):
    hits = []
    for cls, info in cat["classes"].items():
        for kind in ("methods", "properties"):
            for name, e in (info.get(kind) or {}).items():
                sig = str(e.get("signature") or "")
                if needle.lower() in sig.lower() and name.lower().startswith(("get", "create", "query")):
                    hits.append(cls + "." + name + " :: " + sig[:70])
    print("--", needle, len(hits))
    for h in hits[:6]:
        print("    ", h)
print()
print("== 未裁定对明细 ==")
for p in v["pairs_unreachable"]:
    print("   ", p["class"] + "." + p["heading"], "/", p["signature"])
