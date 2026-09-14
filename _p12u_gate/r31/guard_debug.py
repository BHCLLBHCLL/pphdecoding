import json, re, subprocess, sys
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
EVID = re.compile(r"官方案例库实样 (\d+) 例")
for ref in ("51a63bf", "92dc828", "f559d3c", "dd4e278"):
    rep = json.loads(subprocess.run(["git", "show", ref + ":p12h_registry_report.json"], capture_output=True, check=True).stdout)
    mg = json.loads(subprocess.run(["git", "show", ref + ":schemas/merged.json"], capture_output=True, check=True).stdout)
    types = mg["conditions"]["types"]
    row = []
    for name in ("CondSource", "CondPorousMedia", "CondSourceMass"):
        m = EVID.search(rep["dispositions"].get(name, {}).get("evidence") or "")
        row.append((name, int(m.group(1)) if m else None, types.get(name, {}).get("count")))
    print(ref, row, "| report generated:", rep.get("generated"))
