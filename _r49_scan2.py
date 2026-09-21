import json, subprocess, io, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
old = json.loads(subprocess.run(["git","show","HEAD:schemas/host_member_availability.json"],
                                capture_output=True, text=True, encoding="utf-8").stdout)
new = json.loads(Path("schemas/host_member_availability.json").read_text(encoding="utf-8"))
os_, ns = set(old["classes"]), set(new["classes"])
print("R48", len(os_), "-> R49", len(ns), "| NEW:", sorted(ns - os_), "| LOST:", sorted(os_ - ns))
for c in sorted(ns - os_):
    v = new["classes"][c]
    print("   %-16s total=%3d unknown=%s via=%s" % (c, v["total"], v["unknown"], new["coverage"]["obtained_via"].get(c)))
cov = new["coverage"]
print("buckets", cov["classes_swept"], len(cov["empty_objects"]), len(cov["no_member_classes"]), len(cov["unswept_classes"]),
      "sum", cov["classes_swept"]+len(cov["empty_objects"])+len(cov["no_member_classes"])+len(cov["unswept_classes"]))
oldunk = set(m for v in old["classes"].values() for m in (v["unknown"] or []))
newunk = set(m for v in new["classes"].values() for m in (v["unknown"] or []))
print("new absent names:", sorted(newunk - oldunk))
print("guard_audit:", cov.get("guard_audit"))
print("selection_primed:", len(cov.get("selection_primed") or []))
print("primed still unswept geometry:", [c for c in ("ISFace","IVFace","ISEdge","IVEdge","ISVertex") if c not in ns])
