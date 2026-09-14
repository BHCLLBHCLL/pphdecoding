"""R32-3：把描述内嵌取值规则**拒绝**的行逐行分类，找能安全捞回的真词表。"""
import re, sys, json, collections, importlib.util, pathlib
sys.path.insert(0, ".")
sys.path.insert(0, "tools")
import console_utf8; console_utf8.enable()
spec = importlib.util.spec_from_file_location("ex", "tools/extract_vb_api_scflow.py")
ex = importlib.util.module_from_spec(spec); spec.loader.exec_module(ex)

files = []
for pat, _p in ex._FILE_PATTERNS:
    files.extend(sorted(ex.MANUAL.glob(pat)))
QUOTE = '"\u201c\u201d'
tok = re.compile("[" + QUOTE + "]([^" + QUOTE + "]{1,40})[" + QUOTE + "]")
FORMAT = re.compile(r"0x[0-9A-Fa-f]|string\s*[\"'\u201c\u201d]|\(output|\(input")
NOTE = re.compile(r"\(Note\)")


def shape(desc: str, toks: list) -> str:
    if NOTE.search(desc):
        return "note"
    if FORMAT.search(desc):
        return "format-hint"
    if len(toks) >= 2:
        # 取值后是否跟「(描述)」或「大写开头描述」
        follow = re.findall("[" + QUOTE + "][^" + QUOTE + "]+[" + QUOTE
                            + "]\s*(\([^)]*\)|:?\s*[A-Z][^\""
                            + QUOTE + "]*)", desc)
        if len(follow) >= len(toks):
            return "maybe-enum"
        return "prose-with-2-tokens"
    return "single-token"


rows = []
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
            if not tok.findall(desc) or desc.strip()[:1] in QUOTE:
                continue
            joined = " ".join(c for c in cells if c)
            if ex._desc_values(joined):
                continue                      # 已接受
            rows.append({"file": f.name[:40], "method": name, "mode": mode,
                         "desc": desc, "tokens": tok.findall(desc),
                         "shape": shape(desc, tok.findall(desc))})
kinds = collections.Counter(r["shape"] for r in rows)
print("被拒行数:", len(rows), dict(kinds))
bundled = collections.Counter((r["shape"], r["method"]) for r in rows)
pathlib.Path("_p12u_gate/r32/rejected_rows.json").write_text(
    json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
print("--- maybe-enum 全部 ---")
for r in rows:
    if r["shape"] == "maybe-enum":
        print("  ", r["method"], "|", r["tokens"][:5], "|", r["desc"][:90])
print("--- prose-with-2-tokens（前 12）---")
n = 0
for r in rows:
    if r["shape"] == "prose-with-2-tokens" and n < 12:
        n += 1
        print("  ", r["method"], "|", r["tokens"][:4], "|", r["desc"][:90])
