import json, io, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ver = json.loads(Path("_p12u_gate/r47/name_verdicts.json").read_text(encoding="utf-8"))
print("kicker errors:", ver.get("kicker_errors"))
print("kicker args:", ver.get("kicker_args"))
d = json.loads(Path("schemas/host_member_availability.json").read_text(encoding="utf-8"))
print("kicker in classes:", [c for c in ("Kicker.Application","Kicker.ApplicationLaunchSetting","Kicker.LicenseStatus") if c in d["classes"]])
print("swept", d["coverage"]["classes_swept"])
