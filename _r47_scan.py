import json, io, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
cat = json.loads(Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
targets = {"SNode": [("Doc","QuerySNodeByName"),("Doc","GetSNodes"),("Doc","CreateSNode")],
           "Table": [("Doc","CreateTable"),("Doc","QueryTableByName")],
           "Value": [("Conditions","GetValue"),("Doc","GetValue")],
           "Region": [("Doc","QueryRegionByName"),("Doc","GetRegions")],
           "DiffusiveSpecies": [("Doc","QueryDiffusiveSpecies")],
           "MultiYAxisTable": [("Doc","CreateMultiYAxisTable")],
           "BodyPattern": [("Doc","GetBodyPatterns"),("Doc","QueryBodyPatternByIndex")],
           "WrappingGroup": [("Doc","CreateWrappingGroup"),("Doc","QueryWrappingGroupByIndex")]}
for cls, mems in targets.items():
    for host, m in mems:
        e = ((cat["classes"].get(host) or {}).get("methods") or {}).get(m)
        if not e:
            print("%-20s %s.%s : (手册未列)" % (cls, host, m))
            continue
        args = e.get("arguments") or []
        desc = []
        for a in args:
            vals = [v.get("value") for v in (a.get("values") or [])][:6]
            desc.append("%s%s" % (a.get("name"), ("=" + str(vals)) if vals else ""))
        print("%-20s %s.%s :: %s | args: %s" % (cls, host, m, (e.get("signature") or "")[:60], "; ".join(desc)[:120]))
