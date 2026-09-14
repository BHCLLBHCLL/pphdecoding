import json, re, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
cat = json.loads(pathlib.Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
for needle in ("PropItem", "HybridParam", "OctParam", "ClosedVolume", "SpecialRegion"):
    print("==", needle)
    for cls, info in cat["classes"].items():
        for kind in ("methods", "properties"):
            for name, e in (info.get(kind) or {}).items():
                sig = str(e.get("signature") or "")
                ret = str((e.get("return") or {}).get("name") or "")
                if needle.lower() in (sig + " " + ret).lower():
                    print("   ", cls + "." + name, "|", sig[:80])
