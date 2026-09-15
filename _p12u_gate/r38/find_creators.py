import json, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
cat = json.loads(pathlib.Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
cond = cat["classes"]["Conditions"]["methods"]
for stem in ("Map", "Boussinesq", "Multiphase", "CoSim"):
    hits = [m for m in cond if stem.lower() in m.lower() and m.startswith(("Create", "Get", "Query"))]
    print("Conditions." + stem, "->", hits[:8])
mdl = cat["classes"].get("MDL", {}).get("methods", {})
print()
print("MDL 成员数:", len(mdl))
for key in list(mdl):
    if any(s in key.lower() for s in ("closedvolume", "faceregion", "getface", "select")):
        print("   ", key, "|", str(mdl[key].get("signature"))[:80])
print()
print("== 谁产出 PropItem / 谁产出 CondMapForStructure ==")
for cls, info in cat["classes"].items():
    for kind in ("methods",):
        for name, e in (info.get(kind) or {}).items():
            sig = str(e.get("signature") or "")
            for needle in ("PropItem", "CondMapForStructure", "MapCond", "Boussinesq"):
                if needle.lower() in sig.lower():
                    print("   ", needle, "<-", cls + "." + name, "|", sig[:70])
                    break
