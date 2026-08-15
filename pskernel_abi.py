#!/usr/bin/env python3
"""pskernel Parasolid 接口全面解析（V34.1 / V37 pskernel.dll x q-solid V35 手册）。

Cradle scFLOWpre 内嵌 Parasolid 内核（pskernel.dll）的全部导出函数，对照网络
可获取的 Parasolid V35 手册（q-solid.com 托管的 Parasolid_Docs_V35/headers，
逐函数 HTML 页含完整 C 签名）做接口映射：

* dump_exports —— PE 导出表（名称/序号/RVA，内联解析器）；
* fetch_v35_page / fetch_v35_batch —— 下载并缓存手册页
  （缓存目录 tests/box/v35_pages，可离线复现）；
* parse_signature —— 从手册页文本解析 C 签名
  （返回类型 + 参数表 [(类型, 名, 注释)]，typedef/枚举页单独归类）；
* map_interface —— 导出 x 手册 -> 接口映射（含未文档化的内部函数）；
* compare_versions —— 多版本导出差异报告（2023=V34.1 子集 2025.2=V37）；
* gen_ctypes —— 由签名生成 ctypes 原型（供后续内核调用直接复用）。

版本结论（三通道确证）：CradleCFD2023 scFLOWpre 使用 Parasolid V34.1
（pskernel.dll FileVersion 34.01.153、Schemas 含 sch_34101、运行期 PKBody3
modeller version 3401153 / SCH_3401153_34101_13006），不是 V35；
CradleCFD2025.2 = V37（3701153 / SCH_37102）。V35 手册为最接近的公开文档，
V34.1 的导出集为其子集（1100/1204 个 PK_* 导出均可在 V35 手册中定位）。
"""

from __future__ import annotations

import concurrent.futures
import re
import struct
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

V35_BASE = "http://www.q-solid.com/Parasolid_Docs_V35/headers"
DEFAULT_CACHE = Path(__file__).resolve().parent / "tests" / "box" / "v35_pages"
_UA = {"User-Agent": "Mozilla/5.0 (compatible; pskernel-abi/1.0)"}


# ---- PE 导出表 ----------------------------------------------------

@dataclass
class Export:
    name: str
    ordinal: int
    rva: int


def dump_exports(path) -> list:
    """解析 PE 导出表（x64）。"""
    data = Path(path).read_bytes()
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    coff = pe_off + 4
    nsec = struct.unpack_from("<H", data, coff + 2)[0]
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    dd_off = opt + (112 if magic == 0x20B else 96)
    exp_rva, _ = struct.unpack_from("<2I", data, dd_off)
    if not exp_rva:
        return []
    sec_off = opt + opt_size
    sections = []
    for i in range(nsec):
        s = sec_off + i * 40
        vsize, vaddr, rawsize, rawaddr = struct.unpack_from("<4I", data, s + 8)
        sections.append((vaddr, vsize, rawaddr, rawsize))

    def rva2off(rva):
        for vaddr, vsize, rawaddr, rawsize in sections:
            if vaddr <= rva < vaddr + max(vsize, rawsize):
                return rawaddr + (rva - vaddr)
        return None

    eo = rva2off(exp_rva)
    vals = struct.unpack_from("<2I2H7I", data, eo)
    (flags, ts, vmaj, vmin, name_rva, base, nfunc, nname,
     addr_func, addr_name, addr_ord) = vals
    no = rva2off(addr_name)
    nf = rva2off(addr_func)
    oo = rva2off(addr_ord)
    out = []
    for i in range(nname):
        nr = struct.unpack_from("<I", data, no + i * 4)[0]
        noff = rva2off(nr)
        s = data[noff:data.find(b"\x00", noff)].decode(errors="replace")
        ord_ = struct.unpack_from("<H", data, oo + i * 2)[0]
        rva = struct.unpack_from("<I", data, nf + (ord_ - base) * 4)[0]
        out.append(Export(s, ord_, rva))
    return out


# ---- 手册页获取 ----------------------------------------------------

def _clean_text(html: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    for a, b in (("&gt;", ">"), ("&lt;", "<"), ("&amp;", "&"),
                 ("&nbsp;", " "), ("&quot;", '"'), ("&#39;", "'")):
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip()


def fetch_v35_page(name: str, cache_dir=None, timeout: int = 60):
    """下载 V35 手册页（pk_<name>.html）并缓存；返回净化文本。

    404/网络失败返回 None；缓存命中直接返回（离线可复现）。
    """
    cache_dir = Path(cache_dir or DEFAULT_CACHE)
    cache_dir.mkdir(parents=True, exist_ok=True)
    slug = name[3:] if name.upper().startswith("PK_") else name
    page = cache_dir / ("pk_" + slug.lower() + ".txt")
    if page.exists():
        return page.read_text(encoding="utf-8", errors="replace") or None
    url = V35_BASE + "/pk_" + slug.lower() + ".html"
    try:
        req = urllib.request.Request(url, headers=_UA)
        html = (urllib.request.urlopen(req, timeout=timeout).read()
                .decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            page.write_text("", encoding="utf-8")   # 缓存 404
        return None
    except Exception:
        return None
    text = _clean_text(html)
    page.write_text(text, encoding="utf-8")
    return text


def fetch_v35_batch(names, cache_dir=None, workers: int = 16) -> dict:
    """批量下载手册页（线程池）；返回 name -> 文本。"""
    out: dict = {}

    def work(name):
        return name, fetch_v35_page(name, cache_dir)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for name, text in ex.map(work, names):
            out[name] = text
    return out


# ---- 签名解析 ------------------------------------------------------

def parse_signature(text: str):
    """从手册页文本解析 C 签名。

    返回 {"kind": "function", "name", "return_type",
    "params": [(type, name, comment)]}；typedef/枚举页返回
    {"kind": "typedef"/"enum", "raw"}。
    """
    if not text:
        return None
    i = text.find("(")
    j = -1
    if i >= 0:
        # 签名结束 = ")" 后跟正文引导语（参数注释内可含括号，如 "(>= 0)"）
        end_m = re.search(r"\)\s+(This function|Specific Errors|"
                          r"Generated on|Use this function)", text[i:])
        if end_m:
            j = i + end_m.start()
        else:
            j = text.find(")", i + 1)
    if i >= 0 and j > i:
        head = text[:i].strip()
        body = text[i + 1:j]
        # 页面标题重复函数名（NAME RET NAME (）；取括号前最后两词 = 返回类型+名
        parts = head.split()
        if len(parts) < 2:
            return {"kind": "function", "name": head, "return_type": "",
                    "params": [], "raw": text[:200]}
        name = parts[-1]
        ret = parts[-2]
        params = []
        # 去掉 "( --- received arguments --- " 引导语（前后各一个 ---）
        m0 = re.match(r"\s*---[^-]*---\s*(.*)", body)
        if m0:
            body = m0.group(1)
        type_kw = ("const", "unsigned", "signed", "short", "long", "int",
                   "char", "double", "float", "void", "size_t", "struct",
                   "enum")

        def type_like(tok: str) -> bool:
            core = tok.lstrip("*")
            if core in type_kw:
                return True
            if not re.fullmatch(r"[A-Za-z_]\w*", core):
                return False
            return core[0].isupper() or "_" in core

        if body.strip():
            for chunk in body.split(","):
                chunk = chunk.strip()
                m = re.search(r"---", chunk)
                rest = chunk[m.end():].strip() if m else chunk
                # 输出参数节："--- comment --- returned arguments --- TYPE NAME"
                if "returned arguments" in rest:
                    rest = rest.split("returned arguments")[-1].strip() \
                        .lstrip("---").strip()
                # 名字之后的尾随注释（"--- its point ..."）与类型+名字分离
                trailing = ""
                if "---" in rest:
                    typ_part, _, trailing = rest.partition("---")
                    rest = typ_part.strip()
                    trailing = trailing.strip()
                toks = rest.split()
                if not toks:
                    continue
                name_tok = toks[-1]
                pname = name_tok.lstrip("*")
                # 类型 = 名字前符合 C 类型外观的连续 token（含 *const 等限定）
                k = len(toks) - 2
                type_toks = []
                while k >= 0:
                    t = toks[k]
                    if t.startswith("*") or type_like(t):
                        type_toks.insert(0, t)
                        k -= 1
                    else:
                        break
                ptype = " ".join(type_toks)
                if name_tok.startswith("*") and ptype and not ptype.endswith("*"):
                    ptype = (ptype + " *").strip()
                comment = " ".join(toks[:k + 1]).strip()
                if trailing:
                    comment = (comment + " " + trailing).strip()
                if not ptype and pname and not comment:
                    # 无类型的纯注释段：并入上一参数注释
                    if params:
                        last = params[-1]
                        params[-1] = (last[0], last[1],
                                      (last[2] + " " + rest).strip())
                    continue
                if not ptype:
                    # "--- transmit options" 类尾随注释段
                    if params:
                        last = params[-1]
                        params[-1] = (last[0], last[1],
                                      (last[2] + " " + pname).strip())
                    continue
                params.append((ptype, pname, comment))
        return {"kind": "function", "name": name, "return_type": ret,
                "params": params, "raw": text[:400]}
    if re.search(r"\btypedef\b", text):
        return {"kind": "typedef",
                "name": text.split()[1] if len(text.split()) > 1 else "",
                "raw": text[:400]}
    if re.search(r"\benum\b", text):
        return {"kind": "enum",
                "name": text.split()[1] if len(text.split()) > 1 else "",
                "raw": text[:400]}
    return None


# ---- 接口映射 ------------------------------------------------------

@dataclass
class InterfaceEntry:
    name: str
    rva: int = 0
    kind: str = "undocumented"     # function / typedef / enum / undocumented
    return_type: str = ""
    params: list = field(default_factory=list)
    doc: str = ""


def map_interface(dll_path, cache_dir=None, workers: int = 16,
                  progress=None) -> dict:
    """导出函数 x V35 手册 -> 接口映射。progress(name, i, n) 可选回调。"""
    exports = dump_exports(dll_path)
    names = [e.name for e in exports if e.name.startswith("PK_")]
    texts = fetch_v35_batch(names, cache_dir, workers)
    out: dict = {}
    total = len(names)
    for i, name in enumerate(names):
        if progress:
            progress(name, i, total)
        text = texts.get(name)
        sig = parse_signature(text) if text else None
        e = next(x for x in exports if x.name == name)
        if sig and sig.get("kind") == "function":
            out[name] = InterfaceEntry(name, e.rva, "function",
                                       sig["return_type"], sig["params"],
                                       (text or "")[:300])
        elif sig:
            out[name] = InterfaceEntry(name, e.rva, sig["kind"], "", [],
                                       (text or "")[:300])
        else:
            out[name] = InterfaceEntry(name, e.rva, "undocumented", "", [], "")
    for e in exports:
        if e.name not in out:
            out[e.name] = InterfaceEntry(e.name, e.rva, "undocumented")
    return out


def compare_versions(paths: dict) -> dict:
    """多版本导出差异：{tag: path} -> 集合差报告。"""
    sets = {tag: {e.name for e in dump_exports(p)}
            for tag, p in paths.items()}
    rows = []
    for name in sorted(set().union(*sets.values())):
        present = [tag for tag in sets if name in sets[tag]]
        if len(present) < len(sets):
            rows.append((name, present))
    others = {t: set().union(*(v for k, v in sets.items() if k != t))
              for t in sets}
    return {"counts": {t: len(s) for t, s in sets.items()},
            "differences": rows,
            "only": {t: sorted(sets[t] - others[t]) for t in sets}}


def gen_ctypes(mapping: dict, include_names=None) -> str:
    """由签名生成 ctypes 原型骨架（基本类型映射，结构体/指针 -> c_void_p）。"""
    simple = {
        "PK_ERROR_code_t": "c_int", "PK_LOGICAL_t": "c_int",
        "PK_VECTOR1_t": "c_double", "PK_LENGTH1_t": "c_double",
        "PK_ANGLE1_t": "c_double",
        "int": "c_int", "unsigned": "c_uint", "short": "c_short",
        "double": "c_double", "char": "c_char", "size_t": "c_size_t",
    }

    def map_type(t: str) -> str:
        t = t.strip()
        if t in simple:
            return simple[t]
        return "c_void_p"

    names = list(include_names) if include_names else sorted(mapping)
    lines = ["# ctypes 原型（pskernel_abi.gen_ctypes 生成，结构体布局见 V35 手册）",
             "from ctypes import (c_int, c_uint, c_short, c_double, c_char,",
             "                    c_void_p, POINTER, c_size_t)", ""]
    for name in names:
        e = mapping.get(name)
        if not e or e.kind != "function" or not e.params:
            continue
        ret = map_type(e.return_type)
        args = [map_type(t) for t, _, _ in e.params] or ["c_void_p"]
        proto = e.return_type + " " + name + "(" + ", ".join(
            (t + " " + n) if n else t for t, n, _ in e.params) + ")"
        lines.append("# " + proto)
        lines.append("pk." + name + ".restype = " + ret)
        lines.append("pk." + name + ".argtypes = [" + ", ".join(args) + "]")
        lines.append("")
    return "\n".join(lines)


def report(mapping: dict, version: str) -> str:
    """接口映射摘要报告（含 PK_* 文档覆盖率）。"""
    from collections import Counter
    kinds = Counter(e.kind for e in mapping.values())
    funcs = [e for e in mapping.values() if e.kind == "function"]
    pk_total = sum(1 for n in mapping if n.startswith("PK_"))
    pk_mapped = sum(1 for n in mapping
                    if n.startswith("PK_") and mapping[n].kind == "function")
    n_params = Counter(len(e.params) for e in funcs)
    n_ret = Counter(e.return_type for e in funcs)
    undoc = sorted(e.name for e in mapping.values()
                   if e.kind == "undocumented")
    lines = [f"pskernel {version} 接口映射",
             f"导出总数 {len(mapping)}：{dict(kinds)}",
             f"PK_* 文档覆盖 {pk_mapped}/{pk_total}",
             f"函数 {len(funcs)}（参数个数分布 {dict(sorted(n_params.items()))}）",
             f"返回类型 top: {n_ret.most_common(8)}",
             f"未文档化导出 {len(undoc)} 个：{', '.join(undoc[:40])}"
             + ("..." if len(undoc) > 40 else "")]
    return "\n".join(lines)
