import json, io, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
d = json.loads(Path("schemas/host_member_availability.json").read_text(encoding="utf-8"))
cov = d["coverage"]
print("swept", cov["classes_swept"], "/", cov["classes_total"], "members", cov["members_swept"], "/", cov["members_total"])
print("empty", len(cov["empty_objects"]), "no_member", len(cov.get("no_member_classes") or []), "unswept", len(cov["unswept_classes"]))
print("sum", cov["classes_swept"]+len(cov["empty_objects"])+len(cov.get("no_member_classes") or [])+len(cov["unswept_classes"]))
print("kicker in classes:", [c for c in ("Kicker.Application","Kicker.ApplicationLaunchSetting","Kicker.LicenseStatus") if c in d["classes"]])
print("kicker via:", {k: v for k, v in (cov.get("obtained_via") or {}).items() if k.startswith("Kicker")})
print("kicker errors:", (json.loads(Path("_p12u_gate/r47/name_verdicts.json").read_text(encoding="utf-8")).get("kicker_errors")))
print("name_pool:", (json.loads(Path("_p12u_gate/r47/name_verdicts.json").read_text(encoding="utf-8")).get("name_pool") or [])[:10])
