import json, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
acc = json.loads(pathlib.Path("schemas/dispatch_account.json").read_text(encoding="utf-8"))
print("account evidence:", acc.get("evidence"))
row = [r for r in acc["rows"] if r["heading"] == "SelectFace"]
print("row reason:", row[0]["reason"] if row else None)
d = json.loads(pathlib.Path("_p12u_gate/r40/name_verdicts.json").read_text(encoding="utf-8"))
print("r40 ClosedVolume:", (d.get("chain_errors") or {}).get("ClosedVolume"))
import os
for p in sorted(pathlib.Path("_p12u_gate").glob("r*/name_verdicts.json")):
    print("   ", p, round(os.path.getmtime(p), 1))
