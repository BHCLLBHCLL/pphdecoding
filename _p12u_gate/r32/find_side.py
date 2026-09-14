import json, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
cat = json.loads(pathlib.Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
hits = []
for cls, info in cat["classes"].items():
    for kind in ("methods", "properties"):
        for name, e in (info.get(kind) or {}).items():
            for a in (e.get("arguments") or []) + [e.get("return") or {}]:
                if not isinstance(a, dict):
                    continue
                for v in a.get("values") or []:
                    if v["value"] in ("positive_side", "negative_side", "inside", "outside"):
                        hits.append((cls, name, v["value"]))
print("side 词表命中:", len(hits))
for h in hits[:10]:
    print("  ", h)
