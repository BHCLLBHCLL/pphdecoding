import json, re, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
cat = json.loads(pathlib.Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
d = json.loads(pathlib.Path("_p12u_gate/r34/corpus_diff_auto.json").read_text(encoding="utf-8"))
cond = cat["classes"]["Conditions"]["methods"]
print("Conditions 成员数:", len(cond))
for stem in ("loop", "equa", "solv", "soli", "next", "upwd", "gradient",
             "fph", "heat", "moment", "move", "table", "outside", "contact",
             "face"):
    hits = [m for m in cond if stem in m.lower()]
    if hits:
        print("  " + stem + ":", hits[:6])
print()
print("仅重叠候选（前 25）:")
for link in d["overlap_only"][:25]:
    print("   " + link["parent"].ljust(30), "->", link["member"].ljust(46),
          "corpus=" + str(len(link["corpus"])), "only_corpus=" + str(link["only_corpus"][:4]))
