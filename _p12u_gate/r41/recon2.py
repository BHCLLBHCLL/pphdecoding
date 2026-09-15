import re, sys, json, collections, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
C = json.loads(pathlib.Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
print("== Conditions 里 Create*Map* / *MapCond* ==")
cond = C["classes"]["Conditions"]["methods"]
for k in sorted(cond):
    if ("map" in k.lower()) or ("boussinesq" in k.lower()):
        print("   ", k, "|", str(cond[k].get("signature"))[:70])
print()
print("== 谁产出 CondMapForStructure / MapCond / PropItem（按签名文本）==")
for needle in ("condmapforstructure", "mapcond", "propitem"):
    print("--", needle)
    n = 0
    for cls, info in C["classes"].items():
        for kind in ("methods", "properties"):
            for name, e in (info.get(kind) or {}).items():
                sig = str(e.get("signature") or "")
                if needle in sig.lower():
                    print("     ", (cls + "." + name).ljust(50), "|", sig[:66])
                    n += 1
                    if n > 6:
                        break
            if n > 6:
                break
    print()
print("== MDLWizard 成员 ==")
for k, e in sorted((C["classes"].get("MDLWizard", {}).get("methods") or {}).items()):
    print("   ", k, "|", str(e.get("signature"))[:60])
print()
print("== 语料线索 ==")
import official_examples
from pph_parser import PphArchive
root = official_examples.example_root()
marks = {"boussinesq": re.compile(r"boussinesq", re.I),
         "map_cond": re.compile(r"map_cond|mapcond|mapping", re.I),
         "cosim_region": re.compile(r"cosim_region|cosimregion", re.I)}
hits = collections.defaultdict(list)
for p in sorted(root.rglob("*.pph")):
    try:
        t = PphArchive.open(str(p)).read_member("main.xml").decode("utf-8", "replace")
    except Exception:
        continue
    for k, pat in marks.items():
        n = len(pat.findall(t))
        if n:
            hits[k].append((n, p.name))
for k in marks:
    print("   ", k.ljust(14), sorted(hits[k], reverse=True)[:5])
