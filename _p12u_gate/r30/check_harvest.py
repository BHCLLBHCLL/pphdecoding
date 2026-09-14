import json, sys
sys.path.insert(0, ".")
sys.path.insert(0, "tools")
import console_utf8; console_utf8.enable()
from pph_parser import PphArchive
from schema_extract import extract_archive_schema
for name in ("box.pph", "p12c_cond_harvest_out.pph"):
    sc = extract_archive_schema(PphArchive.open(name))
    t = (sc.get("conditions") or {}).get("types") or {}
    cs = t.get("CondSource") or {}
    print(name, "| types:", len(t), "| CondSource count:", cs.get("count"),
          "regions:", cs.get("regions"), "samples:", cs.get("samples"))
cur = json.load(open("schemas/merged.json", encoding="utf-8"))["conditions"]["types"]["CondSource"]
print("merged.json CondSource:", {k: cur.get(k) for k in ("count", "regions", "samples")})
rep = json.load(open("p12h_registry_report.json", encoding="utf-8"))
print("frozen report keys:", sorted(rep.keys())[:12])
print("official_sample_projects:", rep.get("official_sample_projects"),
      "projects in merged:", len(json.load(open("schemas/merged.json", encoding="utf-8"))["projects"]))
