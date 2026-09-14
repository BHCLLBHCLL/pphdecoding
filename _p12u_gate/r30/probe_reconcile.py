import importlib.util, json, sys
from pathlib import Path
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
spec = importlib.util.spec_from_file_location("rc", "tools/_p12h_reconcile.py")
rc = importlib.util.module_from_spec(spec); spec.loader.exec_module(rc)
inputs = rc.load_inputs()
disp, problems = rc.attribute(inputs)
frozen = json.loads(Path("p12h_registry_report.json").read_text(encoding="utf-8"))["dispositions"]
print("problems:", problems[:3], "n_disp:", len(disp), "n_frozen:", len(frozen))
diffs = [k for k in set(disp) | set(frozen) if disp.get(k) != frozen.get(k)]
print("differing keys:", len(diffs), diffs[:10])
for k in diffs[:4]:
    a = (disp.get(k) or {}).get("evidence", "")
    b = (frozen.get(k) or {}).get("evidence", "")
    print("==", k, "| kind:", (disp.get(k) or {}).get("kind"), (frozen.get(k) or {}).get("kind"))
    print("   recompute:", a[:120])
    print("   frozen   :", b[:120])
counts = rc.sample_counts(inputs["merged"])
import re
for k in diffs[:6]:
    m = re.search(r"实样 (\d+) 例", (disp.get(k) or {}).get("evidence", ""))
    m2 = re.search(r"实样 (\d+) 例", (frozen.get(k) or {}).get("evidence", ""))
    print("   ", k, "merged count:", counts.get(k), "recompute n:", m and m.group(1), "frozen n:", m2 and m2.group(1))
