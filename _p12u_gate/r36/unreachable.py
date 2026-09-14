import json, collections, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
d = json.loads(pathlib.Path("_p12u_gate/r36/name_verdicts.json").read_text(encoding="utf-8"))
c = collections.Counter(p["class"] for p in d["pairs_unreachable"])
print("unreachable total:", sum(c.values()))
for k, v in c.most_common():
    print("   ", k, v)
print("verdicts:", len(d["verdicts"]), d["tally"])
print("obtained_via:", json.dumps(d.get("obtained_via"), ensure_ascii=False))
