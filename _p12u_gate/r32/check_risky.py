import json, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
cat = json.loads(pathlib.Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
for cls, mem in (("Doc", "SewSheets"), ("Conditions", "GetRadiationVFRETimingParam")):
    e = (cat["classes"].get(cls, {}).get("methods") or {}).get(mem)
    if not e:
        print(cls + "." + mem, "MISSING"); continue
    print("==", cls + "." + mem)
    for a in (e.get("arguments") or []) + [e.get("return") or {}]:
        if a.get("values"):
            print("   ", a.get("name"), "->", [(v["value"], v["description"][:40])
                                               for v in a["values"]][:5])
