import json, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
d = json.loads(pathlib.Path("_p12u_gate/r39/name_verdicts.json").read_text(encoding="utf-8"))
print("verdicts:", len(d["verdicts"]), d["tally"], "| unreachable:", len(d["pairs_unreachable"]))
for v in d["verdicts"]:
    if v["verdict"] not in ("both",):
        print("   ", v["verdict"], v["class"] + "." + v["heading"], "|",
              v["heading_state"], "|", v["signature_state"])
