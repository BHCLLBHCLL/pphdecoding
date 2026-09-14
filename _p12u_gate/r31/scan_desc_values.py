"""R31-2 依据：取值写在**参数描述**里的行型 —— 先量分布再定规则。"""
import re, sys, importlib.util, collections
sys.path.insert(0, ".")
sys.path.insert(0, "tools")
import console_utf8; console_utf8.enable()
spec = importlib.util.spec_from_file_location("ex", "tools/extract_vb_api_scflow.py")
ex = importlib.util.module_from_spec(spec); spec.loader.exec_module(ex)

files = []
for pat, _prefix in ex._FILE_PATTERNS:
    files.extend(sorted(ex.MANUAL.glob(pat)))
print("extracted files:", len(files))

QUOTE = '"\u201c\u201d'
tok = re.compile("[" + QUOTE + "]([^" + QUOTE + "]{1,40})[" + QUOTE + "]")
hits = []
for f in files:
    t = f.read_text(encoding="utf-8", errors="replace")
    for pos, name, block in ex._split_sections(t):
        tm = ex._TABLE.search(block)
        if not tm:
            continue
        mode = None
        for row in ex._TR.findall(tm.group(1)):
            cells = [ex._strip(c) for c in ex._TD.findall(row)]
            if not cells:
                continue
            head = cells[0]
            if "[Argument]" in head:
                mode = "arg"
            elif "[Return Value]" in head:
                mode = "ret"
            elif "[Explanation]" in head:
                mode = "expl"
            elif not head:
                continue
            if mode not in ("arg", "ret"):
                continue
            desc = cells[-1]
            toks = tok.findall(desc)
            if toks and not desc.strip().startswith(('"', "\u201c", "\u201d")):
                hits.append((f.name, name, mode, desc, toks))
print("描述内嵌引号取值的行:", len(hits))
kinds = collections.Counter()
for h in hits:
    d = h[3]
    if re.search(r"(?:mode|type|edition|method|option|flag)s?\b[^\"]*$", d.split('"')[0], re.I):
        kinds["有 label 前缀"] += 1
    else:
        kinds["其它"] += 1
print(kinds)
for h in hits[:18]:
    print("  ", h[0][:34], "|", h[1], "|", h[2], "|", h[3][:110])
