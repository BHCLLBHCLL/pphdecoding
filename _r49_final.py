import json, io, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
d = json.loads(Path("schemas/host_member_availability.json").read_text(encoding="utf-8"))
cov = d["coverage"]
print("swept", cov["classes_swept"], "members", cov["members_swept"], "| empty", len(cov["empty_objects"]), "no_member", len(cov["no_member_classes"]), "unswept", len(cov["unswept_classes"]))
print("primed", len(cov.get("selection_primed") or []), "| prime errors", cov.get("selection_prime_errors"))
print("guard_audit", cov.get("guard_audit"))
print("absent entries", len([m for v in d["classes"].values() for m in (v["unknown"] or [])]), "| errors", sum(len(v["errors"] or []) for v in d["classes"].values()))
cat = json.loads(Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
print("recipe_unreliable classes", sorted(c for c, i in cat["classes"].items() if i.get("recipe_unreliable")))
