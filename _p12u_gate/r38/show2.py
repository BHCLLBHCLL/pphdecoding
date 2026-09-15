import json, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
d = json.loads(pathlib.Path("_p12u_gate/r38/name_verdicts.json").read_text(encoding="utf-8"))
print("verdicts:", len(d["verdicts"]), d["tally"], "| unreachable:", len(d["pairs_unreachable"]))
print("projects:", [pathlib.Path(p).name for p in d.get("projects", [])])
print("-- neither --")
for v in d["verdicts"]:
    if v["verdict"] == "neither":
        print("   ", v)
print("-- obtained_via（新增） --")
for k, v in (d.get("obtained_via") or {}).items():
    print("   ", k, "=", str(v)[:80])
print("-- chain_errors --")
for k, v in (d.get("chain_errors") or {}).items():
    print("   ", k, "::", str(v)[:120])
print("-- context_errors --", d.get("context_errors"))
print("-- unreachable classes --", sorted({p["class"] for p in d["pairs_unreachable"]}))
