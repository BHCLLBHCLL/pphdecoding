"""取值形状体检：文档里的取值应当是标识符样（无空格/逗号/句号结尾）。"""
import json, re, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
cat = json.loads(pathlib.Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
OK = re.compile(r"^[A-Za-z0-9_.:/\-]+$")
bad, total = [], 0
for cls, info in cat["classes"].items():
    for kind in ("methods", "properties"):
        for name, e in (info.get(kind) or {}).items():
            for a in (e.get("arguments") or []) + [e.get("return") or {}]:
                if not isinstance(a, dict):
                    continue
                for v in a.get("values") or []:
                    total += 1
                    if not OK.match(v["value"]):
                        bad.append((cls, name, v["value"][:50]))
print("取值总数:", total, "| 形状可疑:", len(bad))
for b in bad[:12]:
    print("  ", b)
