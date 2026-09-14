import json, subprocess, sys
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
old = json.loads(subprocess.run(["git", "show", "HEAD:schemas/vb_api_catalog.json"],
                                capture_output=True, check=True).stdout)
new = json.loads(open("schemas/vb_api_catalog.json", encoding="utf-8").read())
for cls, mem in (("Conditions", "GetAnalysisType"), ("CondOutputLFileTurbo", "GetOutputTimingParam")):
    for tag, cat in (("OLD", old), ("NEW", new)):
        e = cat["classes"][cls]["methods"][mem]
        print(tag, cls + "." + mem)
        for a in e.get("arguments") or []:
            print("   arg", a.get("name"), "| values:", len(a.get("values") or []),
                  [v["value"] for v in (a.get("values") or [])][:4])
        r = e.get("return") or {}
        print("   ret", r.get("name"), "| values:", len(r.get("values") or []),
              [v["value"] for v in (r.get("values") or [])][:4])
        print("   entry-level values:", len(e.get("values") or []))
