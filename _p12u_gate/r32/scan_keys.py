"""R32-1 依据：从文档里把所有 `SECTION.KEY` 形式的宿主键抓出来，分类计数。"""
import re, sys, collections, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
docs = ["docs/CODE_STATE_AUDIT_20260906.md", "docs/ROUNDS.md",
        "docs/NEXT_PRIORITIES_20260913.md"]
SEC = ("FACET", "OCT_MESH", "MESH", "MESH_COMMON", "COND", "SOLVER")
pat = re.compile(r"\b(" + "|".join(SEC) + r")\.[A-Z][A-Z0-9_]{3,}\b")
seen = collections.defaultdict(set)
for d in docs:
    t = pathlib.Path(d).read_text(encoding="utf-8", errors="replace")
    for m in pat.finditer(t):
        seen[m.group(0)].add(pathlib.Path(d).name)
for k in sorted(seen):
    print(k.ljust(48), ",".join(sorted(seen[k])))
print("distinct:", len(seen))
