import re, sys, collections
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
import official_examples
from pph_parser import PphArchive
root = official_examples.example_root()
marks = {"boussinesq": re.compile(r"boussinesq", re.I),
         "base_temperature": re.compile(r"base_temperature|basetemp", re.I),
         "map_cond": re.compile(r"map_cond|mapcond", re.I),
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
    print(k.ljust(16), sorted(hits[k], reverse=True)[:5])
