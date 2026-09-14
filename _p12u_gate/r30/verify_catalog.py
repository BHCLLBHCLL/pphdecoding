"""R30-3 验收：假参数清零 + 取值词表入库（可复算，不是快照）。"""
import json, pathlib, sys
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
cat = json.loads(pathlib.Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
classes = cat["classes"]
bogus = 0
n_values = 0
n_args_with_values = 0
n_entries_with_values = 0
n_notes = 0
n_refs = 0
for cls, info in classes.items():
    for kind in ("methods", "properties"):
        for name, entry in (info.get(kind) or {}).items():
            if not isinstance(entry, dict):
                continue
            if entry.get("note"):
                n_notes += 1
            if entry.get("note_ref"):
                n_refs += 1
            hit = False
            for a in (entry.get("arguments") or []) + [entry.get("return") or {}]:
                if not isinstance(a, dict):
                    continue
                if not a.get("type") and str(a.get("name", "")).startswith(('"', "\u201c", "\u201d")):
                    bogus += 1
                vals = a.get("values") or []
                if vals:
                    hit = True
                    n_args_with_values += 1
                    n_values += len(vals)
            if hit:
                n_entries_with_values += 1
            if entry.get("values"):
                n_values += len(entry["values"])
print("假参数（name 带引号、type 空）:", bogus)
print("带 values 的参数/返回值:", n_args_with_values)
print("取值总数:", n_values)
print("带 values 的条目:", n_entries_with_values)
print("note 条目:", n_notes, " 带 note_ref:", n_refs)

def show(cls, meth):
    e = (classes.get(cls, {}).get("methods") or {}).get(meth)
    if not e:
        print("MISSING", cls, meth); return
    print("---", cls + "." + meth)
    print("   note:", e.get("note"), "| ref:", e.get("note_ref"))
    for a in (e.get("arguments") or []):
        print("   arg", a.get("name"), a.get("type"), "desc=", (a.get("description") or "")[:40],
              "values=", [(v["value"], v["description"][:24]) for v in (a.get("values") or [])][:6])
    r = e.get("return") or {}
    print("   ret", r.get("name"), r.get("type"), "values=",
          [(v["value"], v["description"][:24]) for v in (r.get("values") or [])][:6])

show("MeshingGroupSetting", "SetVoxelOctRefineType")
show("MeshingGroupSetting", "GetVoxelOctRefineType")
show("MeshingGroupSetting", "ChangeMesher")
show("MeshingGroupSetting", "ChangeSurfMesher")
