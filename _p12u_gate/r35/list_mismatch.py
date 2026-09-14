import importlib.util, json, sys, collections, pathlib
sys.path.insert(0, ".")
sys.path.insert(0, "tools")
import console_utf8; console_utf8.enable()
spec = importlib.util.spec_from_file_location("cov", "tools/api_bridge_coverage.py")
cov = importlib.util.module_from_spec(spec); spec.loader.exec_module(cov)
cat = json.loads(pathlib.Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
mism = cov.heading_signature_mismatches(cat)
print("总数:", len(mism))
c = collections.Counter(m["class"] for m in mism)
for cls, n in c.most_common():
    print("  ", cls, n)
pathlib.Path("_p12u_gate/r35/mismatch.json").write_text(
    json.dumps(mism, ensure_ascii=False, indent=1), encoding="utf-8")
