"""候选规则校验：描述内嵌取值 —— 前缀须是类型标记或 label 词。"""
import re, sys, importlib.util
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
# 前缀 = 第一个引号之前的所有文本（跨单元格拼接，含类型标记）
PREFIX_OK = re.compile(
    r"(?:\((?:BSTR|VARIANT|string)[^)]*\)|\b(?:mode|type|edition|format|method|option|key|setting|flag)\b)"
    r"[\s\[:：,，(]*(?:\[[^\]]*)?$", re.I)
COMMA_LIST = re.compile(r"^\s*\(" + "[" + QUOTE + "][^" + QUOTE
                        + "]+[" + QUOTE + "]\s*(?:,\s*[" + QUOTE + "][^"
                        + QUOTE + "]+[" + QUOTE + "]\s*)+[,)]")

acc, rej = [], []
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
            pre = joined.split('"')[0] if '"' in joined else joined
            after = joined.split('"', 1)[1] if '"' in joined else ""
            ok = bool(PREFIX_OK.search(pre))
            if not ok and pre.rstrip().endswith("(") and "," in after:
                ok = bool(COMMA_LIST.match('"' + after))
            (acc if ok else rej).append((f.name, name, mode, desc))
print("接受:", len(acc), " 拒绝:", len(rej))
print("--- 接受样本 ---")
for h in acc[:10]:
    print("  OK ", h[1], "|", h[3][:100])
print("--- 拒绝样本 ---")
for h in rej[:14]:
    print("  NO ", h[1], "|", h[3][:100])
