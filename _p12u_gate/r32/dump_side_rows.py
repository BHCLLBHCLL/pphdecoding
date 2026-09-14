import re, sys, importlib.util, pathlib
sys.path.insert(0, ".")
sys.path.insert(0, "tools")
import console_utf8; console_utf8.enable()
spec = importlib.util.spec_from_file_location("ex", "tools/extract_vb_api_scflow.py")
ex = importlib.util.module_from_spec(spec); spec.loader.exec_module(ex)
f = ex.MANUAL / "Scf_vb_Preprocessor_CrossSectionRegion_Class.html"
t = f.read_text(encoding="utf-8", errors="replace")
for pos, name, block in ex._split_sections(t):
    if name != "GetSide":
        continue
    tm = ex._TABLE.search(block)
    print("has table:", bool(tm))
    for row in ex._TR.findall(tm.group(1)):
        cells = [ex._strip(c) for c in ex._TD.findall(row)]
        print("  n=" + str(len(cells)), [c[:70] for c in cells])
    entry = ex._parse_method_block(block)
    print("PARSED:", json.dumps(entry, ensure_ascii=False)[:400] if False else entry)
