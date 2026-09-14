import re, sys, importlib.util
sys.path.insert(0, ".")
sys.path.insert(0, "tools")
import console_utf8; console_utf8.enable()
spec = importlib.util.spec_from_file_location("ex", "tools/extract_vb_api_scflow.py")
ex = importlib.util.module_from_spec(spec); spec.loader.exec_module(ex)
files = []
for pat, _p in ex._FILE_PATTERNS:
    files.extend(sorted(ex.MANUAL.glob(pat)))
n = 0
for f in files:
    t = f.read_text(encoding="utf-8", errors="replace")
    for pos, name, block in ex._split_sections(t):
        tm = ex._TABLE.search(block)
        if not tm:
            continue
        rows = ex._TR.findall(tm.group(1))
        for row in rows:
            cells = [ex._strip(c) for c in ex._TD.findall(row)]
            if cells and cells[0].startswith("[Description]"):
                n += 1
                if n <= 4:
                    print(f.name[:40], "|", name, "|", [c[:60] for c in cells])
print("total [Description] in method blocks:", n)
