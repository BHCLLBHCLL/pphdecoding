import json, subprocess, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
old = json.loads(subprocess.run(["git", "show", "HEAD:schemas/host_member_availability.json"],
                                capture_output=True, text=True, encoding="utf-8").stdout)
import pathlib
new = json.loads(pathlib.Path("schemas/host_member_availability.json").read_text(encoding="utf-8"))
os_, ns = set(old["classes"]), set(new["classes"])
print("R46 swept", len(os_), "-> R47 swept", len(ns))
print("NEW:", sorted(ns - os_))
print("LOST:", sorted(os_ - ns))
print("unswept R46", len(old["coverage"]["unswept_classes"]), "-> R47", len(new["coverage"]["unswept_classes"]))
print("unswept gained:", sorted(set(new["coverage"]["unswept_classes"]) - set(old["coverage"]["unswept_classes"])))
print("unswept lost:", sorted(set(old["coverage"]["unswept_classes"]) - set(new["coverage"]["unswept_classes"])))
