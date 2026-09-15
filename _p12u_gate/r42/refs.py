import json, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
cat = json.loads(pathlib.Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
absent = []
for cls, info in cat["classes"].items():
    for kind in ("methods", "properties"):
        for mem, e in (info.get(kind) or {}).items():
            if e.get("host_absent"):
                absent.append((cls, mem))
print("host_absent 成员:", len(absent))
for cls, mem in absent:
    print("   ", cls + "." + mem, "| ZWSP:" , "\u200b" in mem, "| repr:", repr(mem)[:60])
print()
roots = [("tools", "tools"), ("automation", "automation"), ("tests", "tests"), (".", ".")]
names = [m for _c, m in absent]
for label, sub in roots:
    base = pathlib.Path(sub)
    for p in sorted(base.glob("*.py")):
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in names:
            if m in src:
                print("REF", p.as_posix(), "->", m)
