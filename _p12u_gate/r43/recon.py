import json, sys, collections, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
av = json.loads(pathlib.Path("schemas/host_member_availability.json").read_text(encoding="utf-8"))
states = collections.Counter()
errs = collections.defaultdict(list)
for cls, members in av["availability"].items():
    for mem, st in members.items():
        kinds = "resolved" if st == "resolved" else ("unknown_name" if st == "unknown_name" else "error")
        states[kinds] += 1
        if kinds == "error":
            errs[cls].append((mem, st))
print("成员状态:", dict(states))
print("受影响类:", len(errs))
for cls, items in errs.items():
    print("   ", cls, len(items), items[:3])
cat = json.loads(pathlib.Path("schemas/vb_api_catalog.json").read_text(encoding="utf-8"))
swept = set(av["availability"])
allc = set(cat["classes"])
swept_members = sum(len(m) for m in av["availability"].values())
all_members = sum(len(info.get("methods") or {}) + len(info.get("properties") or {})
                  for info in cat["classes"].values())
print()
print("类覆盖: %d / %d" % (len(swept), len(allc)))
print("成员覆盖: %d / %d" % (swept_members, all_members))
print("未普查类（前 12）:", sorted(allc - swept)[:12])
