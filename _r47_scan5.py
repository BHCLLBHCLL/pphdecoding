import json, io, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
d = json.loads(Path("schemas/host_member_availability.json").read_text(encoding="utf-8"))
cov = d["coverage"]
ver = json.loads(Path("_p12u_gate/r47/name_verdicts.json").read_text(encoding="utf-8"))
print("swept", cov["classes_swept"], "members", cov["members_swept"], "| empty", len(cov["empty_objects"]), "no_member", len(cov["no_member_classes"]), "unswept", len(cov["unswept_classes"]))
print("sum", cov["classes_swept"]+len(cov["empty_objects"])+len(cov["no_member_classes"])+len(cov["unswept_classes"]))
print("kicker classes:", {c: d["classes"][c]["unknown"] for c in ("Kicker.Application","Kicker.ApplicationLaunchSetting","Kicker.LicenseStatus") if c in d["classes"]})
print("kicker errors:", ver.get("kicker_errors"))
print("kicker via:", {k:v for k,v in cov["obtained_via"].items() if k.startswith("Kicker")})
print("new wins:", {k: cov["obtained_via"][k] for k in ("MultiYAxisTable","Condition","Table","Value","Region") if k in cov["obtained_via"]})
print("unswept:", cov["unswept_classes"])
