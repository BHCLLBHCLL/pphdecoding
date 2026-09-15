"""R41 侦察：9 条 NYI 的产出者与语料线索（先离线，再决定实机怎么跑）。"""
import re, sys, collections, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
cat = pathlib.Path("schemas/vb_api_catalog.json")
import json
C = json.loads(cat.read_text(encoding="utf-8"))

NEEDLES = {
    "MDL 建立": ("createmdl", "beginmdl", "savemdl", "makemdl", "executemdl",
                 "getmdl"),
    "CondMapForStructure": ("mapforstructure", "condmap", "mapping"),
    "Boussinesq": ("boussinesq",),
    "PropDataBase/PropItem": ("propdatabase", "getpropitem", "phasematerial",
                              "primarymaterial", "material"),
    "CoSimRegion": ("cosimregion", "getowner", "cosim"),
    "ClosedVolume": ("closedvolume", "cvol"),
}
for label, needles in NEEDLES.items():
    print("==", label)
    seen = 0
    for cls, info in C["classes"].items():
        for kind in ("methods", "properties"):
            for name, e in (info.get(kind) or {}).items():
                sig = str(e.get("signature") or "")
                low = (name + " " + sig).lower()
                if any(n in low for n in needles):
                    if name.startswith(("Get", "Create", "Query", "Set", "begin")) or True:
                        print("   ", (cls + "." + name).ljust(52), "|", sig[:66])
                        seen += 1
                        if seen > 14:
                            break
            if seen > 14:
                break
        if seen > 14:
            break
    print()
print("== 语料线索（哪些工程含这些条件/对象）==")
import official_examples
from pph_parser import PphArchive
root = official_examples.example_root()
marks = {"boussinesq": re.compile(r"boussinesq", re.I),
         "map_cond": re.compile(r"map_cond|mapping|mapcond", re.I),
         "cosim_region": re.compile(r"cosim_region|cosimregion", re.I),
         "material": re.compile(r"<material_name|propitem", re.I),
         "cvol": re.compile(r"closed_volume|closedvolume", re.I)}
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
    top = sorted(hits[k], reverse=True)[:4]
    print("   ", k.ljust(14), top)
