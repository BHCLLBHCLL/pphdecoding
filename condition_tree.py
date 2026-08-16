#!/usr/bin/env python3
"""scFLOWpre 求解设置条件树解析（P4-0）。

数据源是 Cradle 安装目录 ``MonitorServices\\Optimization\\definition\\
scflow_main.xml`` —— 厂商优化框架（MonitorServices/Optimization）的
变量抽取定义，实质是求解设置树的权威 schema::

    definition > target(conditions)           # 树根（Analysis Conditions）
      > target × N                            # section（55 个）
          category         BASIC_SETTING / SOURCE_CONDITION / ...
          name             XML 元素名（basic_param / condition）
          display_name     英/日显示名（distinguished_name/eng/jpn）
          property*        区分键（type / name / source_type）
          variable*        可抽取变量
              condition*   依赖条件（keys 路径 + value）
              name         变量名（main.xml 键）
              real         值子键（如 const_value）
              unit         单位子键（如 unit）
              integer      整型值子键（少数）
              display_name 英/日显示名

解析产物落盘 ``schemas/condition_tree.json``，供求解设置详细页与
:mod:`nav_panels` 的通用渲染引擎使用；本模块不依赖 Qt。
"""

from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

# 本仓 bundled JSON（解析产物，供无安装环境使用）
BUNDLED_JSON = Path(__file__).resolve().parent / "schemas" / "condition_tree.json"

# 安装目录定位候选（版本号降序取最新）
_PROGRAM_GLOBS = [
    r"C:\Program Files\Cradle\CradleCFD*\Programs_x64",
    r"D:\Program Files\Cradle\CradleCFD*\Programs_x64",
]
DEF_REL = r"MonitorServices\Optimization\definition\scflow_main.xml"


def locate_definition() -> Optional[Path]:
    """定位 scflow_main.xml（环境变量 SCFLOWPRE_PROGRAMS 优先）。"""
    env = os.environ.get("SCFLOWPRE_PROGRAMS")
    cands: list[str] = []
    if env:
        cands.append(os.path.join(env, DEF_REL))
    for pat in _PROGRAM_GLOBS:
        for d in sorted(glob.glob(pat), reverse=True):
            cands.append(os.path.join(d, DEF_REL))
    for c in cands:
        if os.path.isfile(c):
            return Path(c)
    return None


def _tri(el: ET.Element, tag: str) -> Optional[dict]:
    """读 display_name/category 的三语结构（dn/eng/jpn）。"""
    node = el.find(tag)
    if node is None:
        return None
    out = {}
    for k in ("distinguished_name", "eng", "jpn"):
        v = node.findtext(k)
        if v:
            out["dn" if k == "distinguished_name" else k] = v.strip()
    return out or None


def _txt(el: ET.Element, tag: str) -> Optional[str]:
    v = el.findtext(tag)
    return v.strip() if v else None


def parse_condition_tree(path: str | os.PathLike | None = None) -> dict:
    """解析 scflow_main.xml → 条件树 dict（category→section→variable）。"""
    if path is None:
        found = locate_definition()
        if found is None:
            raise FileNotFoundError(
                "scflow_main.xml not found; set SCFLOWPRE_PROGRAMS or "
                "bundle schemas/condition_tree.json")
        path = found
    root = ET.parse(path).getroot()
    top = root.find("target")
    if top is None or (top.findtext("name") or "").strip() != "conditions":
        raise ValueError(f"unexpected definition root in {path}")

    categories: dict[str, dict] = {}
    order: list[str] = []
    for sec in top.findall("target"):
        cat = _tri(sec, "category") or {"eng": "(uncategorized)"}
        key = cat.get("dn") or cat.get("eng") or "?"
        catnode = categories.get(key)
        if catnode is None:
            catnode = {"eng": cat.get("eng", key),
                       "jpn": cat.get("jpn"), "dn": cat.get("dn"),
                       "sections": []}
            categories[key] = catnode
            order.append(key)
        variables = []
        for v in sec.findall("variable"):
            conds = []
            for c in v.findall("condition"):
                conds.append({
                    "keys": [k.strip() for k in
                             (k.text or "").split("/") if k.strip()]
                    if len(c.findall("key")) == 1 and "/" in (c.findtext("key") or "")
                    else [(k.text or "").strip() for k in c.findall("key")],
                    "value": (c.findtext("value") or "").strip(),
                })
            # 39 个变量有两段 <name>（嵌套元素路径，如 face_param/
            # flow_rate_value）——保留全路径
            names = [(n.text or "").strip() for n in v.findall("name")]
            names = [n for n in names if n]
            variables.append({
                "name": "/".join(names),
                "path": names,
                "display": (_tri(v, "display_name") or {}).get("eng"),
                "display_jpn": (_tri(v, "display_name") or {}).get("jpn"),
                "dn": (_tri(v, "display_name") or {}).get("dn"),
                "value_key": _txt(v, "real"),
                "unit_key": _txt(v, "unit"),
                "integer_key": _txt(v, "integer"),
                "conditions": conds,
            })
        # 7 个 section 的 display_name 按区分键有多个变体（display_name
        # 内嵌 condition）；首个无条件者为主标题
        main_dn: Optional[dict] = None
        variants: list[dict] = []
        for dn_el in sec.findall("display_name"):
            tri = {"dn": None, "eng": None, "jpn": None}
            for k in ("distinguished_name", "eng", "jpn"):
                t = dn_el.findtext(k)
                if t:
                    tri["dn" if k == "distinguished_name" else k] = t.strip()
            cond = dn_el.find("condition")
            if cond is None and main_dn is None:
                main_dn = tri
            else:
                variants.append({
                    "eng": tri.get("eng"),
                    "jpn": tri.get("jpn"),
                    "condition": {
                        "keys": [(k.text or "").strip()
                                 for k in cond.findall("key")],
                        "value": (cond.findtext("value") or "").strip(),
                    } if cond is not None else None,
                })
        catnode["sections"].append({
            "eng": (main_dn or {}).get("eng") or _txt(sec, "name") or "(section)",
            "jpn": (main_dn or {}).get("jpn"),
            "dn": (main_dn or {}).get("dn"),
            "display_variants": variants,
            "xml_name": _txt(sec, "name"),
            "properties": [p.strip() for p in
                           (p.text or "" for p in sec.findall("property")) if p.strip()],
            "variables": variables,
        })
    return {
        "source": Path(path).name,
        "root": _tri(top, "display_name") or {"eng": "Analysis Conditions"},
        "categories": [categories[k] for k in order],
    }


def summary(tree: dict) -> dict:
    """树规模统计（类别/section/变量/依赖条件数）。"""
    nsec = nvar = ncond = 0
    for cat in tree.get("categories", []):
        nsec += len(cat.get("sections", []))
        for sec in cat["sections"]:
            nvar += len(sec.get("variables", []))
            ncond += sum(len(v.get("conditions", []))
                         for v in sec.get("variables", []))
    return {"categories": len(tree.get("categories", [])),
            "sections": nsec, "variables": nvar, "conditions": ncond}


def iter_variables(tree: dict):
    """展平迭代 (category, section, variable)。"""
    for cat in tree.get("categories", []):
        for sec in cat.get("sections", []):
            for v in sec.get("variables", []):
                yield cat, sec, v


def write_json(tree: dict, path: str | os.PathLike = BUNDLED_JSON) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(tree, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    return p


# ── main.xml 绑定（纯逻辑，无 Qt） ────────────────────────────────────

def _find_path(el: ET.Element, path: list[str]) -> Optional[ET.Element]:
    """沿子元素路径查找（缺失返回 None）。"""
    cur = el
    for seg in path:
        if cur is None:
            return None
        cur = cur.find(seg)
    return cur


def _ensure_path(el: ET.Element, path: list[str]) -> ET.Element:
    """沿子元素路径查找，缺失则逐级创建。"""
    cur = el
    for seg in path:
        nxt = cur.find(seg)
        if nxt is None:
            nxt = ET.SubElement(cur, seg)
        cur = nxt
    return cur


def section_cond_types(section: dict) -> list[str]:
    """section 覆盖的 Cond* 类型（来自 display_variants 的 type= 值）。"""
    out: list[str] = []
    for var in section.get("display_variants", []):
        cd = var.get("condition") or {}
        keys, val = cd.get("keys") or [], cd.get("value") or ""
        if "type" in keys and val.startswith("Cond") and val not in out:
            out.append(val)
    return out


def section_instances(cond_root: ET.Element, section: dict) -> list[ET.Element]:
    """定位 section 对应的 main.xml 元素实例列表。

    ``xml_name=basic_param`` → conditions/basic_param（单实例）；
    ``xml_name=condition`` → 所有 type 命中 display_variants 的
    ``<condition>`` 元素。
    """
    if cond_root is None:
        return []
    if section.get("xml_name") != "condition":
        el = cond_root.find(section.get("xml_name") or "")
        return [el] if el is not None else []
    types = section_cond_types(section)
    return [c for c in cond_root.findall("condition")
            if (c.findtext("type") or "").strip() in types]


def variable_active(el: ET.Element, variable: dict) -> bool:
    """变量依赖是否在当前实例上成立（conditions keys 路径 == value）。"""
    for cd in variable.get("conditions", []):
        keys, want = cd.get("keys") or [], cd.get("value") or ""
        target = _find_path(el, keys) if keys else None
        got = (target.text or "").strip() if target is not None else None
        if got != want:
            return False
    return True


def read_variable(el: ET.Element, variable: dict) -> Optional[str]:
    """从实例元素读变量当前值（value_key/integer_key 子键或元素文本）。"""
    if el is None:
        return None
    path = variable.get("path") or []
    if not path:
        return None
    target = _find_path(el, path)
    if target is None:
        return None
    vkey = variable.get("value_key") or variable.get("integer_key")
    if vkey:
        holder = target.find(vkey)
        return (holder.text or "").strip() if holder is not None else None
    return (target.text or "").strip() if target.text else None


def write_variable(el: ET.Element, variable: dict, value: str) -> bool:
    """把值写回实例元素（按需创建路径与值/单位子键）。返回是否改动。"""
    if el is None or not value:
        return False
    path = variable.get("path") or []
    if not path:
        return False
    target = _ensure_path(el, path)
    vkey = variable.get("value_key") or variable.get("integer_key")
    if vkey:
        holder = target.find(vkey)
        if holder is None:
            holder = ET.SubElement(target, vkey)
        ukey = variable.get("unit_key")
        if ukey and target.find(ukey) is None:
            ET.SubElement(target, ukey)
    else:
        holder = target
    old = (holder.text or "").strip() if holder.text else ""
    if old == value:
        return False
    holder.text = value
    return True


def load_condition_tree(path: str | os.PathLike | None = None) -> Optional[dict]:
    """加载条件树：优先显式路径 → bundled JSON → 现场解析安装目录。"""
    if path is not None:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    if BUNDLED_JSON.is_file():
        return json.loads(BUNDLED_JSON.read_text(encoding="utf-8"))
    try:
        return parse_condition_tree()
    except FileNotFoundError:
        return None


def main(argv: list[str] | None = None) -> int:
    tree = parse_condition_tree()
    out = write_json(tree)
    s = summary(tree)
    print(f"condition tree -> {out}")
    print(f"categories={s['categories']} sections={s['sections']} "
          f"variables={s['variables']} conditions={s['conditions']}")
    for cat in tree["categories"]:
        nv = sum(len(sec["variables"]) for sec in cat["sections"])
        print(f"  {cat['eng']}: {len(cat['sections'])} sections, {nv} vars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
