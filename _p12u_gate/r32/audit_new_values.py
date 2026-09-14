"""审查 R32-3 新捞回的取值是否混入格式提示/散文。"""
import json, re, sys
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
from automation import scflowpre_api as api
cat = api.load_catalog()
suspicious = []
total = 0
for cls, info in cat["classes"].items():
    for kind in ("methods", "properties"):
        for name, e in (info.get(kind) or {}).items():
            for a in (e.get("arguments") or []) + [e.get("return") or {}]:
                if not isinstance(a, dict):
                    continue
                for v in a.get("values") or []:
                    total += 1
                    val, desc = v["value"], v.get("description") or ""
                    if (val.startswith("0x") or re.search(r"0x[0-9A-Fa-f]{4,}", val + desc)
                            or "output, string" in desc or "input, string" in desc
                            or "AABBGGRR" in val + desc):
                        suspicious.append((cls, name, val, desc[:60]))
print("取值总数:", total)
print("可疑（格式提示类）:", len(suspicious))
for s in suspicious[:10]:
    print("  ", s)
