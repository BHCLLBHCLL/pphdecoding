import json, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
for name in ("_p12u_gate/r38/verdicts_closedvolume.json",):
    d = json.loads(pathlib.Path(name).read_text(encoding="utf-8"))
    print("==", name)
    print("   verdicts:", len(d["verdicts"]), d["tally"], "| unreachable:",
          len(d["pairs_unreachable"]))
    print("   obtained_via:", json.dumps(d.get("obtained_via"), ensure_ascii=False)[:400])
    print("   chain_errors:")
    for k, v in (d.get("chain_errors") or {}).items():
        print("      ", k, "::", str(v)[:140])
    print("   context_error:", d.get("context_error"))
    print("   classes unreachable:", sorted({p["class"] for p in d["pairs_unreachable"]}))
