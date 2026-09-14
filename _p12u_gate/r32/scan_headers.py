"""R32-3 追加发现：表头大小写变体统计。"""
import re, sys, collections, importlib.util
sys.path.insert(0, ".")
sys.path.insert(0, "tools")
import console_utf8; console_utf8.enable()
spec = importlib.util.spec_from_file_location("ex", "tools/extract_vb_api_scflow.py")
ex = importlib.util.module_from_spec(spec); spec.loader.exec_module(ex)
files = []
for pat, _p in ex._FILE_PATTERNS:
    files.extend(sorted(ex.MANUAL.glob(pat)))
heads = collections.Counter()
for f in files:
    t = f.read_text(encoding="utf-8", errors="replace")
    for row in ex._TR.findall(t):
        cells = [ex._strip(c) for c in ex._TD.findall(row)]
        if cells and cells[0].startswith("["):
            heads[cells[0][:40]] += 1
for h, n in heads.most_common(20):
    print(str(n).rjust(6), h)
