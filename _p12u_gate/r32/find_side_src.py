import re, sys, importlib.util, pathlib
sys.path.insert(0, ".")
sys.path.insert(0, "tools")
import console_utf8; console_utf8.enable()
spec = importlib.util.spec_from_file_location("ex", "tools/extract_vb_api_scflow.py")
ex = importlib.util.module_from_spec(spec); spec.loader.exec_module(ex)
files = []
for pat, _p in ex._FILE_PATTERNS:
    files.extend(sorted(ex.MANUAL.glob(pat)))
hit = None
for f in files:
    t = f.read_text(encoding="utf-8", errors="replace")
    if "positive_side" in t and "Direction of region" in t:
        hit = f
        break
print("file:", hit.name if hit else None)
if hit:
    m = ex._NAME_RE.match(hit.name)
    print("_NAME_RE match:", bool(m), m.groups() if m else None)
    print("in class_files():", hit in [p for _n, p in ex.class_files()])
    t = hit.read_text(encoding="utf-8", errors="replace")
    i = t.find("GetSide")
    print(re.sub(r"\s+", " ", t[i:i + 500])[:400])
