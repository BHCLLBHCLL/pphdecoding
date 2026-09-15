import json, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
d = json.loads(pathlib.Path("schemas/host_member_availability.json").read_text(encoding="utf-8"))
cov = d["coverage"]
print("classes_swept:", cov["classes_swept"], "/", cov["classes_total"])
print("members_swept:", cov["members_swept"], "/", cov["members_total"])
print("empty_objects:", cov.get("empty_objects"))
print("unswept 数:", len(cov["unswept_classes"]))
tot_unknown = sum(len(v.get("unknown") or []) for v in d["classes"].values())
tot_err = sum(len(v.get("errors") or []) for v in d["classes"].values())
print("unknown:", tot_unknown, " errors:", tot_err)
print("未实现明细:")
for cls, v in sorted(d["classes"].items()):
    if v.get("unknown"):
        print("   ", cls, v["unknown"])
