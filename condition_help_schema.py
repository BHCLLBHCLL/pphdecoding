#!/usr/bin/env python3
"""从帮助元数据（HTML 帮助页 + 求解设置树）为 Cond* 类型补全字段 schema。

P6-1 的核心模块：把「样本驱动」的字段 schema 升级为「样本 + 帮助元数据」
双驱动。数据源（均在本仓 ``schemas/`` 下，非样本、非目录）：

* ``cond_types.json``    —— 165 个 Cond* 类型目录，含 ``help``（HTML 帮助页
  映射，由 :mod:`tools.html_cond_extract` 交叉核对回填）；
* ``cond_html_meta.json`` —— 184 页帮助解析，含每页 ``terms``（字段概念）
  与 ``params``（带取值样本的字段表）；
* ``condition_tree.json`` —— 厂商 ``scflow_main.xml`` 的求解设置树，含
  section → Cond* 类型映射（``display_variants.type=Cond*``）与字段变量
  （``name``/``display``/``value_key``）。

字段名规范：帮助页只有显示名（无 XML 键），此处把显示名/术语规范化为
合法 XML 键（snake_case），使通用条件表单可编辑；样本类型（已有精确字段
的 10 类）**不覆盖**，保持 XML round-trip 精确性。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
SCHEMAS = ROOT / "schemas"

# 字段名规范化：仅保留字母数字，其余转下划线（去首尾下划线）
_NON_KEY = re.compile(r"[^A-Za-z0-9]+")


def sanitize_key(text: str) -> str:
    """显示名/术语 → 合法 XML 键（小写 snake_case）；空输入回退 ``field``。"""
    s = _NON_KEY.sub("_", (text or "").strip())
    s = s.strip("_").lower()
    return s or "field"


def _kind_of_values(values: list[str]) -> str:
    """按取值样本推断字段类型（与 schema_extract 口径一致）。"""
    vals = [v for v in values if v]
    if not vals:
        return "string"
    if all(re.fullmatch(r"[+-]?\d+", v) for v in vals):
        return "int"
    if all(_is_number(v) for v in vals):
        return "float"
    return "string"


def _is_number(v: str) -> bool:
    try:
        float(v)
        return True
    except ValueError:
        return False


def load_json(name: str) -> Optional[dict]:
    p = SCHEMAS / name
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# ── 来源 A：HTML 帮助页（显示名 + 取值样本） ───────────────────────────

def html_field_schema() -> dict[str, dict[str, dict]]:
    """``{Cond*: {字段键: field_desc}}``，来自帮助页 terms + params。

    字段键为显示名 sanitize 后的合法 XML 键；``samples`` 取 params 的
    取值（供枚举推断）；``display`` 保留原始显示名。
    """
    ct = load_json("cond_types.json") or {}
    types = ct.get("types", {})
    hm = load_json("cond_html_meta.json") or {}
    pages = {p["file"]: p for p in hm.get("pages", [])}

    out: dict[str, dict[str, dict]] = {}
    for tname, meta in types.items():
        help_file = meta.get("help")
        if not help_file or help_file not in pages:
            continue
        page = pages[help_file]
        fields: dict[str, dict] = {}
        # params（带取值）优先，其次 terms（纯概念）
        for p in page.get("params", []):
            name = (p.get("name") or "").strip()
            if not name:
                continue
            key = sanitize_key(name)
            vals = [v for v in p.get("values", []) if v]
            fields[key] = {
                "kind": _kind_of_values(vals),
                "samples": vals[:5],
                "display": name,
                "source": "html",
            }
        for term in page.get("terms", []):
            key = sanitize_key(term)
            if key in fields:
                continue
            fields[key] = {
                "kind": "string",
                "samples": [],
                "display": term,
                "source": "html",
            }
        if fields:
            out[tname] = fields
    return out


# ── 来源 B：求解设置树（XML 键 + 显示名） ──────────────────────────────

def _section_cond_types(section: dict) -> list[str]:
    """section → Cond* 类型（display_variants 里 type=Cond*）。"""
    out: list[str] = []
    for var in section.get("display_variants", []):
        cd = var.get("condition") or {}
        keys, val = cd.get("keys") or [], cd.get("value") or ""
        if "type" in keys and str(val).startswith("Cond") and val not in out:
            out.append(val)
    return out


def tree_field_schema() -> dict[str, dict[str, dict]]:
    """``{Cond*: {字段键: field_desc}}``，来自 scflow_main.xml 求解设置树。

    字段键优先取 ``variable.dn``（distinguished name，如 VELX）——它在
    main.xml 里即 XML 键；缺失时用 ``variable.name`` 或 display 规范化。
    """
    ct = load_json("condition_tree.json") or {}
    out: dict[str, dict[str, dict]] = {}
    sections = [s for c in ct.get("categories", [])
                for s in c.get("sections", [])]
    for sec in sections:
        if sec.get("xml_name") != "condition":
            continue
        types = _section_cond_types(sec)
        if not types:
            continue
        fields: dict[str, dict] = {}
        for v in sec.get("variables", []):
            key = v.get("dn") or v.get("name")
            if not key or key in ("value_Value",):
                # value_Value 是通用值容器，重复出现，改用 display 区分
                key = sanitize_key(v.get("display") or "")
            else:
                key = sanitize_key(key)
            if not key or key in fields:
                continue
            kind = "int" if v.get("integer_key") else (
                "float" if v.get("value_key") else "string")
            fields[key] = {
                "kind": kind,
                "samples": [],
                "display": v.get("display") or key,
                "source": "tree",
            }
        for t in types:
            out.setdefault(t, {}).update(fields)
    return out


# ── 注入 ──────────────────────────────────────────────────────────────

def apply_help_schema(reg, html: Optional[dict] = None,
                      tree: Optional[dict] = None) -> dict:
    """把帮助元数据字段注入注册表，返回统计。

    只注入**尚无字段**的类型（样本已背书的精确字段不覆盖）。
    """
    from condition_registry import ConditionField

    html = html_field_schema() if html is None else html
    tree = tree_field_schema() if tree is None else tree
    merged: dict[str, dict[str, dict]] = {}
    for src in (tree, html):
        for tname, fields in src.items():
            m = merged.setdefault(tname, {})
            for k, d in fields.items():
                m.setdefault(k, d)

    added = 0
    total_fields = 0
    for tname, fields in merged.items():
        t = reg.types.get(tname)
        if t is None:
            continue
        if t.fields:
            continue  # 样本类型不覆盖
        for key, desc in fields.items():
            t.fields[key] = ConditionField(
                name=key,
                kind=desc.get("kind", "string"),
                indexed=False,
                children=0,
                samples=list(desc.get("samples", [])),
                count=0,  # required=None：帮助字段不做必填判定
            )
            total_fields += 1
        added += 1
    return {"types_with_new_fields": added, "total_fields_injected": total_fields}
