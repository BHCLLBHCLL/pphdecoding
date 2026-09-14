import json, re, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
cat = json.loads(pathlib.Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
n_ret = n_entries = n_args = n_vals = 0
fmt = re.compile(r"0x[0-9A-Fa-f]{4,}|AABBGGRR")
susp = 0
for cls, info in cat["classes"].items():
    for kind in ("methods", "properties"):
        for name, e in (info.get(kind) or {}).items():
            n_entries += 1
            if e.get("return"):
                n_ret += 1
            n_args += len(e.get("arguments") or [])
            for a in (e.get("arguments") or []) + [e.get("return") or {}]:
                if not isinstance(a, dict):
                    continue
                for v in a.get("values") or []:
                    n_vals += 1
                    if fmt.search(v["value"] + " " + (v.get("description") or "")):
                        susp += 1
print("entries:", n_entries, "有 return:", n_ret, "arguments:", n_args)
print("values:", n_vals, "格式提示混入:", susp)
