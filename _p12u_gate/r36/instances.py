import json, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
cat = json.loads(pathlib.Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
v = json.loads(pathlib.Path("_p12u_gate/r35/name_verdicts.json").read_text(encoding="utf-8"))
classes = []
for p in v["pairs_unreachable"]:
    if p["class"] not in classes:
        classes.append(p["class"])
for cls in classes:
    info = cat["classes"].get(cls) or {}
    print(cls.ljust(34), "| instance:", str(info.get("instance"))[:90])
print()
print("== 属性分布 ==")
for cls, info in cat["classes"].items():
    props = info.get("properties") or {}
    if props:
        print("   ", cls, len(props), list(props)[:4])
