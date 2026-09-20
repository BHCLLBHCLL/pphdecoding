import json, io, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
d = json.loads(Path("schemas/host_member_availability.json").read_text(encoding="utf-8"))
cov = d["coverage"]
ver = json.loads(Path("_p12u_gate/r47/name_verdicts.json").read_text(encoding="utf-8"))
for cls in ("CondParticleCounter", "Kicker.LicenseStatus", "Condition", "MultiYAxisTable"):
    print(cls, "| in classes:", cls in d["classes"], "| in empty:", cls in cov["empty_objects"],
          "| in no_member:", cls in (cov.get("no_member_classes") or []),
          "| in unswept:", cls in cov["unswept_classes"],
          "| via:", (cov.get("obtained_via") or {}).get(cls),
          "| auto:", (cov.get("auto_obtained") or {}).get(cls))
print("empty_objects:", cov["empty_objects"])
print("suspect:", cov.get("swept_suspect"))
print("verdict auto_obtained has CondParticleCounter:", "CondParticleCounter" in (ver.get("auto_obtained") or {}))
print("verdict empty_objects (set):", sorted(set(ver.get("empty_objects") or [])))
