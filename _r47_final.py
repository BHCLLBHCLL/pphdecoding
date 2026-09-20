import json, io, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
d = json.loads(Path("schemas/host_member_availability.json").read_text(encoding="utf-8"))
cov = d["coverage"]
ver = json.loads(Path("_p12u_gate/r47/name_verdicts.json").read_text(encoding="utf-8"))
print("swept", cov["classes_swept"], "members", cov["members_swept"], "empty", len(cov["empty_objects"]), "no_member", len(cov["no_member_classes"]), "unswept", len(cov["unswept_classes"]))
print("suspect", cov.get("swept_suspect"), "| auto", len(cov.get("auto_obtained") or {}), "| via", len(cov.get("obtained_via") or {}))
print("kicker via", {k:v for k,v in cov["obtained_via"].items() if k.startswith("Kicker")})
print("kicker args", ver.get("kicker_args"), "| errors", list((ver.get("kicker_errors") or {}).keys()))
entries = [m for v in d["classes"].values() for m in (v["unknown"] or [])]
print("absent entries", len(entries), "unique", len(set(entries)), "errors", sum(len(v["errors"] or []) for v in d["classes"].values()))
acct = json.loads(Path("schemas/unswept_account.json").read_text(encoding="utf-8"))
print("unswept account", acct["counts"])
print("name pool size", len(ver.get("name_pool") or []))
