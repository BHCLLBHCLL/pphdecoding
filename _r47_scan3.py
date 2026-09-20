import json, io, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
cur = json.loads(Path("schemas/host_member_availability.json").read_text(encoding="utf-8"))
ver = json.loads(Path("_p12u_gate/r47/name_verdicts.json").read_text(encoding="utf-8"))
print("new classes vs R46 (146):", sorted(set(cur["classes"]) - set(ver.get("swept_before") or []))[:10])
print("obtained_via new (auto):", {k: v for k, v in (cur["coverage"]["obtained_via"] or {}).items() if k in ("MultiYAxisTable","Table","Value","Region","Condition","SNode","DiffusiveSpecies","BodyPattern","WrappingGroup")})
