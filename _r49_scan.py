import json, io, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
cat = json.loads(Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
av = json.loads(Path("schemas/host_member_availability.json").read_text(encoding="utf-8"))
doc = cat["classes"]["Doc"]["methods"]
sel = sorted(m for m in doc if m.startswith("SetSelectAll"))
print("Doc.SetSelectAll*:", sel)
for m in ("SetSelectAllVFace","SetSelectAllSFace","SetSelectAllVEdge","SetSelectAllSEdge","SetSelectAllSVertex"):
    e = doc.get(m) or {}
    print("  %-22s %s | state=%s" % (m, (e.get("signature") or "")[:60], (av["availability"].get("Doc") or {}).get(m)))
print()
print("unswept now:", av["coverage"]["unswept_classes"])
