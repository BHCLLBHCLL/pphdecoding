import json, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
cat = json.loads(pathlib.Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
print("== 属性样例（Doc 前 6）==")
props = cat["classes"]["Doc"].get("properties") or {}
for k, v in list(props.items())[:6]:
    print("   ", repr(k), "| signature:", str(v.get("signature"))[:60],
          "| return:", str(v.get("return"))[:60])
print("属性总数:", sum(len(i.get("properties") or {}) for i in cat["classes"].values()))
print()
print("== upwd 候选取值 ==")
cond = cat["classes"]["Conditions"]["methods"]
for m in ("GetUpwdParam", "GetUpwdOptionParamForEquation", "GetUpwdOptionParam"):
    e = cond.get(m) or {}
    for a in e.get("arguments") or []:
        vals = [x["value"] for x in (a.get("values") or [])]
        if vals:
            print("   ", m + "." + str(a.get("name")), len(vals), vals[:14])
print()
ev = json.loads(pathlib.Path("_p12u_gate/r35/corpus_diff_attr.json").read_text(encoding="utf-8"))
for link in ev.get("attributed", []):
    if link["parent"] == "upwd_param":
        print("upwd_param 语料取值:", sorted(link["corpus"]))
        print("   归因到:", link["member"], "| only_corpus:", link["only_corpus"])
print()
print("== 未裁定对的类 ==")
v = json.loads(pathlib.Path("_p12u_gate/r35/name_verdicts.json").read_text(encoding="utf-8"))
import collections
c = collections.Counter(p["class"] for p in v["pairs_unreachable"])
for k, n in c.most_common():
    print("   ", k, n)
