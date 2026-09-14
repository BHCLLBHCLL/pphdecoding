import json, sys, importlib.util
sys.path.insert(0, ".")
sys.path.insert(0, "tools")
import console_utf8; console_utf8.enable()
spec = importlib.util.spec_from_file_location("ex", "tools/extract_vb_api_scflow.py")
ex = importlib.util.module_from_spec(spec); spec.loader.exec_module(ex)
f = ex.MANUAL / "Scf_vb_Preprocessor_Conditions_Class.html"
t = f.read_text(encoding="utf-8", errors="replace")
for pos, name, block in ex._split_sections(t):
    if name != "GetAnalysisType":
        continue
    tm = ex._TABLE.search(block)
    for i, row in enumerate(ex._TR.findall(tm.group(1))):
        cells = [ex._strip(c) for c in ex._TD.findall(row)]
        if not cells:
            continue
        head = cells[0]
        print(i, "kind=", ex._head_kind(head), "| head=", repr(head[:24]),
              "| n=", len(cells), "| c1=", repr(cells[1][:26]) if len(cells) > 1 else "")
        if i > 4:
            break
    e = ex._parse_method_block(block)
    print("arg0:", json.dumps(e["arguments"][0], ensure_ascii=False)[:200] if e.get("arguments") else None)
    print("entry values:", len(e.get("values") or []))
