import json, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
d = json.loads(pathlib.Path("_p12u_gate/r40/name_verdicts.json").read_text(encoding="utf-8"))
print("verdicts:", len(d["verdicts"]), d["tally"], "| unreachable:", len(d["pairs_unreachable"]))
print("ClosedVolume reason:", (d.get("chain_errors") or {}).get("ClosedVolume"))
print("obtained_via ClosedVolume:", (d.get("obtained_via") or {}).get("ClosedVolume"))
print("unreachable classes:", sorted({p["class"] for p in d["pairs_unreachable"]}))
