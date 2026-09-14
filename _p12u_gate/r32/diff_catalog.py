"""header 归一前后逐条对比：谁多了 return、谁少了 values。"""
import json, subprocess, sys
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
old = json.loads(subprocess.run(["git", "show", "HEAD:schemas/vb_api_catalog.json"],
                                capture_output=True, check=True).stdout)
new = json.loads(open("schemas/vb_api_catalog.json", encoding="utf-8").read())


def flat(cat):
    out = {}
    for cls, info in cat["classes"].items():
        for kind in ("methods", "properties"):
            for name, e in (info.get(kind) or {}).items():
                out[(cls, kind, name)] = e
    return out


o, n = flat(old), flat(new)
print("entries old/new:", len(o), len(n))
gained_ret = lost_ret = 0
gained_val = lost_val = 0
examples_lost = []
for k in set(o) | set(n):
    a, b = o.get(k, {}), n.get(k, {})
    if not a.get("return") and b.get("return"):
        gained_ret += 1
    if a.get("return") and not b.get("return"):
        lost_ret += 1

    def nvals(e):
        return sum(len(x.get("values") or [])
                   for x in (e.get("arguments") or []) + [e.get("return") or {}]
                   if isinstance(x, dict))
    va, vb = nvals(a), nvals(b)
    if vb > va:
        gained_val += 1
    if vb < va:
        lost_val += 1
        if len(examples_lost) < 8:
            examples_lost.append((k, va, vb, a.get("return"), b.get("return")))
print("新增 return:", gained_ret, " 丢失 return:", lost_ret)
print("values 增加条目:", gained_val, " 减少条目:", lost_val)
for k, va, vb, ra, rb in examples_lost:
    print("  LOST", k, va, "->", vb, "| ret_old=", str(ra)[:80], "| ret_new=", str(rb)[:80])
