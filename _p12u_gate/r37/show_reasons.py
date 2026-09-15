import json, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
d = json.loads(pathlib.Path("_p12u_gate/r37/name_verdicts.json").read_text(encoding="utf-8"))
print("verdicts:", len(d["verdicts"]), d["tally"], "| unreachable:", len(d["pairs_unreachable"]))
print("-- obtained_via --")
for k, v in (d.get("obtained_via") or {}).items():
    print("   ", k, "=", v)
print("-- chain_errors --")
for k, v in (d.get("chain_errors") or {}).items():
    print("   ", k, "::", str(v)[:150])
