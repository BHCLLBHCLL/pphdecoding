import importlib.util, json, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
spec = importlib.util.spec_from_file_location("ch", "tools/_p12c_cond_harvest.py")
rc = importlib.util.module_from_spec(spec); spec.loader.exec_module(rc)
td = Path(tempfile.mkdtemp())
tmp = td / "merged.json"
shutil.copyfile(rc.MERGED, tmp)
rc.REPORT = td / "report.json"
r1 = rc.merge(merged_path=tmp)
b1 = tmp.read_bytes()
r2 = rc.merge(merged_path=tmp)
b2 = tmp.read_bytes()
print("run1 to_add:", r1["to_add"])
print("run1 new_in_universe:", r1["new_in_universe"], "alias:", r1["alias_evidence"])
print("run2 to_add:", r2["to_add"])
print("idempotent:", b1 == b2)
print("repo merged.json untouched:", rc.MERGED.read_bytes() == Path("schemas/merged.json").read_bytes() or "CHANGED")
cur = json.load(open("schemas/merged.json", encoding="utf-8"))["conditions"]["types"]["CondSource"]["count"]
print("repo CondSource:", cur)
