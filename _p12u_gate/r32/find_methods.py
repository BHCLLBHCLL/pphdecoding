import sys
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
from automation import scflowpre_api as api
cat = api.load_catalog()
want = ("GetSide", "GetProductType", "GetLaunchProgram", "GetBkColor",
        "GetProjectTypeConversionValidationMessages")
for cls, info in cat["classes"].items():
    for kind in ("methods", "properties"):
        for name, e in (info.get(kind) or {}).items():
            if name in want:
                vals = []
                for a in (e.get("arguments") or []) + [e.get("return") or {}]:
                    vals += [v["value"] for v in (a.get("values") or [])]
                print(cls + "." + name, "values=", vals[:6])
