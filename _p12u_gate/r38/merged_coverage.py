import json, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
t = json.loads(pathlib.Path("schemas/name_verdicts.json").read_text(encoding="utf-8"))
res = t["resolved"]
print("classes:", len(res), "entries:", sum(len(v) for v in res.values()))
print("tally:", t.get("tally"))
cat = json.loads(pathlib.Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
n = 0
for cls, info in cat["classes"].items():
    for kind in ("methods", "properties"):
        for k, e in (info.get(kind) or {}).items():
            if e.get("dispatch_name"):
                n += 1
print("目录 dispatch_name 条数:", n)
d = json.loads(pathlib.Path("_p12u_gate/r38/name_verdicts.json").read_text(encoding="utf-8"))
had = {(v["class"], v["heading"]) for v in d["verdicts"]}
allp = {(p["class"], p["heading"]) for p in d["pairs_unreachable"]} | had
print("本次运行: 裁定", len(had), "未裁定", len(allp) - len(had))
