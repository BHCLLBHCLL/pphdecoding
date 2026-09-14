"""验证 R31-4 护栏非空转：拿**修复前**的已提交对（R8 快照 vs 当时的 merged.json）
跑同一段比较逻辑，应当报出不一致。"""
import json, re, subprocess, sys
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
EVID = re.compile(r"官方案例库实样 (\d+) 例")


def show(ref):
    return json.loads(subprocess.run(["git", "show", ref], capture_output=True,
                                     check=True).stdout)


def compare(report, merged):
    types = (merged.get("conditions") or {}).get("types") or {}
    bad = []
    for name, disp in report["dispositions"].items():
        m = EVID.search(disp.get("evidence") or "")
        if not m or name not in types:
            continue
        if int(m.group(1)) != types[name].get("count"):
            bad.append((name, int(m.group(1)), types[name].get("count")))
    return bad


rep_r8 = show("dd4e278:p12h_registry_report.json")   # R29 状态（修复前的提交对）
merged_pre = show("dd4e278:schemas/merged.json")
bad = compare(rep_r8, merged_pre)
print("修复前（R8 快照 vs 同提交的 merged.json）不一致:", len(bad), bad[:5])
rep_now = json.load(open("p12h_registry_report.json", encoding="utf-8"))
merged_now = json.load(open("schemas/merged.json", encoding="utf-8"))
print("修复后（当前工作树）不一致:", len(compare(rep_now, merged_now)))
