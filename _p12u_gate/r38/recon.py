"""R38 依据：① 哪些官方工程有闭空间/材料/CoSim；② 手册里"可选参数"的标记形态。"""
import re, sys, collections, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
import official_examples
from pph_parser import PphArchive
root = official_examples.example_root()
markers = {"cvol": re.compile(r"closed_volume|closedvolume|<cvol", re.I),
           "material": re.compile(r"<material|propitem|material_name", re.I),
           "cosim": re.compile(r"cosim|co_simulation", re.I),
           "mapping": re.compile(r"map_cond|mapping", re.I)}
score = collections.defaultdict(dict)
for p in sorted(root.rglob("*.pph")):
    try:
        arch = PphArchive.open(str(p))
        xml = arch.read_member("main.xml").decode("utf-8", "replace")
        names = [m.name for m in arch.members]
    except Exception:
        continue
    for key, pat in markers.items():
        n = len(pat.findall(xml))
        if n:
            score[key][p.name] = n
    if any(n.startswith("main.prp") for n in names):
        score["prp"]["__" + p.name] = 1
for key in markers:
    top = sorted(score[key].items(), key=lambda kv: -kv[1])[:5]
    print(key, "->", top)
print("带 main.prp 的工程数:", len(score["prp"]))
print()
print("== 手册 optional 标记 ==")
man = pathlib.Path(r"C:\Program Files\Cradle\CradleCFD2025.2\Manuals\scFLOW\HTML\VB_Interface_eng")
pat = re.compile(r"optional", re.I)
n_files = n_hits = 0
samples = []
for f in sorted(man.glob("*.html")):
    t = f.read_text(encoding="utf-8", errors="replace")
    hits = pat.findall(t)
    if hits:
        n_files += 1
        n_hits += len(hits)
        if len(samples) < 4:
            i = t.lower().find("optional")
            seg = re.sub(r"<[^>]+>", " ", t[max(0, i - 180):i + 120])
            samples.append((f.name[:34], re.sub(r"\s+", " ", seg)))
print("含 optional 的手册文件:", n_files, " 命中:", n_hits)
for s in samples:
    print("   ", s[0], "|", s[1][:150])
