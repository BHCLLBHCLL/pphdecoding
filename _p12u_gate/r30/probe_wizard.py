import json, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
new = json.loads(Path("p12h_registry_report.json").read_text(encoding="utf-8"))
import subprocess
old = json.loads(subprocess.run(["git", "show", "HEAD:p12h_registry_report.json"],
                                capture_output=True).stdout)
for k in sorted(set(old) | set(new)):
    if old.get(k) != new.get(k):
        if k in ("dispositions", "family_annotations"):
            a, b = old[k], new[k]
            diff = [x for x in set(a) | set(b) if a.get(x) != b.get(x)]
            print("KEY", k, "-> differing entries:", diff)
        else:
            print("KEY", k)
            print("   old:", json.dumps(old.get(k), ensure_ascii=False)[:200])
            print("   new:", json.dumps(new.get(k), ensure_ascii=False)[:200])
wiz = json.loads(Path("p12h_wizard_report.json").read_text(encoding="utf-8"))
fams = wiz.get("families") or {}
print("wizard report families:", len(fams))
print("verdict counter:", Counter(v.get("verdict", v.get("status", "?")) for v in fams.values()))
