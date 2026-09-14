import json, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
d = json.loads(pathlib.Path("_p12u_gate/r35/corpus_diff_attr.json").read_text(encoding="utf-8"))
exact = [a for a in d.get("attributed", []) if a.get("exact_stem") and a["only_corpus"]]
loose = [a for a in d.get("attributed", []) if not a.get("exact_stem")]
print("精确同源且有差异:", len(exact), " 新增取值:", sum(len(a["only_corpus"]) for a in exact))
for a in exact:
    print("   ", a["member"], "<-", a["parent"], a["only_corpus"])
print("仅包含关系（提示，不入库）:", len(loose))
for a in loose:
    print("   ", a["parent"], "->", a["member"], "only_corpus=", a["only_corpus"][:4])
print()
for a in exact:
    cls, member, arg = a["member"].split(".")
    print("    (" + repr(cls) + ", " + repr(member) + ", " + repr(arg) + "): [")
    for v in a["only_corpus"]:
        print("        {\"value\": " + repr(v) + ", \"description\": \"（宿主语料："
              + a["parent"] + "）\", \"source\": \"host-corpus\"},")
    print("    ],")
