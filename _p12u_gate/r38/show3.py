import json, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
d = json.loads(pathlib.Path("_p12u_gate/r38/name_verdicts.json").read_text(encoding="utf-8"))
print("verdicts:", len(d["verdicts"]), d["tally"], "| unreachable:", len(d["pairs_unreachable"]))
for v in d["verdicts"]:
    if v["verdict"] in ("neither",):
        print("   neither:", v)
print("-- errors --")
for k, v in (d.get("chain_errors") or {}).items():
    print("   ", k, "::", str(v)[:130])
print("-- unreachable classes --", sorted({p["class"] for p in d["pairs_unreachable"]}))
