import re, sys, importlib.util
sys.path.insert(0, ".")
sys.path.insert(0, "tools")
import console_utf8; console_utf8.enable()
spec = importlib.util.spec_from_file_location("ex", "tools/extract_vb_api_scflow.py")
ex = importlib.util.module_from_spec(spec); spec.loader.exec_module(ex)
f = ex.MANUAL / "Scf_vb_Preprocessor_Conditions_Class.html"
t = f.read_text(encoding="utf-8", errors="replace")
for pos, name, block in ex._split_sections(t):
    if name not in ("GetPresetStabilityParam", "GetPresetStabilityParamGeom"):
        continue
    tm = ex._TABLE.search(block)
    print("==", name)
    for i, row in enumerate(ex._TR.findall(tm.group(1))[:6]):
        cells = [ex._strip(c) for c in ex._TD.findall(row)]
        print("  ", i, [c[:70] for c in cells])
