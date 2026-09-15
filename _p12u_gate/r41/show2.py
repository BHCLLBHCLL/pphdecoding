import json, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
d = json.loads(pathlib.Path("_p12u_gate/r41/name_verdicts.json").read_text(encoding="utf-8"))
for v in d["verdicts"]:
    if v["verdict"] != "both":
        print(v["verdict"], "|", v["class"] + "." + v["heading"], "|",
              v["heading_state"], "|", v["signature_state"], "|",
              v.get("object_type"))
print("-- call_errors --")
for k, v in (d.get("call_errors") or {}).items():
    print("   ", k, "::", str(v)[:110])
