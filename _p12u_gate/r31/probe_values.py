import sys
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
from automation import scflowpre_api as api
for cls, mem, arg in (
        ("ClosedVolume", "GetConnectionType", "return"),
        ("ClosedVolume", "SetConnectionType", "type"),
        ("Conditions", "GetRadiationVFRETimingParam", "return"),
        ("Doc", "GetDefaultSolidPartColor", "return"),
        ("Doc", "GetBkColor", "return"),
        ("Conditions", "GetFPHVariableOutput", "key"),
        ("Conditions", "GetFPHVariableOutput", "value"),
        ("MeshingGroupSetting", "ChangeSurfMesher", "type"),
):
    vals = api.api_values(cls, mem, arg)
    print(cls + "." + mem + "(" + str(arg) + ") ->", len(vals),
          [v["value"] for v in vals][:6])
cat = api.load_catalog()
print("classes:", len(cat["classes"]))
tot = sum(len(a.get("values") or [])
          for info in cat["classes"].values()
          for kind in ("methods", "properties")
          for e in (info.get(kind) or {}).values()
          for a in (e.get("arguments") or []) + [e.get("return") or {}]
          if isinstance(a, dict))
print("values total:", tot)
