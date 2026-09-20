import json, io, sys, re
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
cat = json.loads(Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
# Utility.GetUnitCandidate / Table 的 yUnitType 相关
for cls, mem in (("Utility","GetUnitCandidate"), ("Table","GetYUnitCandidate"), ("Utility","ConvertValueWithUnit")):
    e = ((cat["classes"].get(cls) or {}).get("methods") or {}).get(mem)
    print(cls + "." + mem, "->", json.dumps(e, ensure_ascii=False)[:300] if e else "(未列)")
# 全目录里带 values 的"单位样"参数
unitish = {}
for c, info in cat["classes"].items():
    for kind in ("methods", "properties"):
        for m, e in (info.get(kind) or {}).items():
            for a in (e.get("arguments") or []):
                for v in (a.get("values") or []):
                    val = str(v.get("value"))
                    if re.search(r"(kg|m/s|Pa|K\b|W/|J/|N\b)", val) and len(val) < 12:
                        unitish.setdefault((a.get("name") or "").split(")")[-1], set()).add(val)
for k, vals in list(unitish.items())[:12]:
    print("arg", k, "->", sorted(vals)[:10])
print("unswept now:")
av = json.loads(Path("schemas/host_member_availability.json").read_text(encoding="utf-8"))
print(av["coverage"]["unswept_classes"])
