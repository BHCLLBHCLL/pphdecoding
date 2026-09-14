import sys
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
from automation import scflowpre_api as api
cat = api.load_catalog()
for cls, mem, arg in (("ClosedVolume", "GetSide", "return"),
                      ("Doc", "GetProductType", "return"),
                      ("Doc", "GetLaunchProgram", "return"),
                      ("Doc", "GetProjectTypeConversionMessages", "return"),
                      ("Doc", "GetBkColor", "return"),
                      ("Doc", "AddTemporaryDrawingObjectPoint", None)):
    e = (cat["classes"].get(cls, {}).get("methods") or {}).get(mem)
    if not e:
        print(cls + "." + mem, "MISSING"); continue
    for a in (e.get("arguments") or []) + [e.get("return") or {}]:
        vals = a.get("values") or []
        print(cls + "." + mem + "(" + str(a.get("name")) + ") desc=" +
              repr(a.get("description"))[:70], "values=", [v["value"] for v in vals][:6])
