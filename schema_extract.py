#!/usr/bin/env python3
"""从 PPH 项目中抽取机器可读的 Schema（条件 / 环境键 / 物性组）。

阶段 0/1 的关键前置：把 ``main.xml`` 中的条件树、``main.xenv`` 的
Section/Key、``main.prp`` 的物性组转成 JSON 注册表，供通用条件编辑器、
单位换算与黄金语料对比使用。
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, Optional

import pphxml
from pph_parser import PphArchive


def _kind_of(text: str) -> str:
    """按文本形态推断字段类型。"""
    if text == "":
        return "empty"
    if text.lower() in ("true", "false"):
        return "bool"
    if re.fullmatch(r"[+-]?\d+", text):
        return "int"
    try:
        float(text)
        return "float"
    except ValueError:
        return "string"


def condition_fields(cond: ET.Element, prefix: str = "") -> dict[str, dict]:
    """递归收集条件的叶子字段。

    返回 ``{"字段路径": {"kind", "sample", "indexed", "children"}}``，
    复合节点本身也登记（``children>0``），便于编辑器按层级重建表单。
    """
    fields: dict[str, dict] = {}
    for child in cond:
        tag, idx = pphxml.restore_index(child.tag)
        name = tag if not prefix else f"{prefix}.{tag}"
        text = (child.text or "").strip()
        kids = list(child)
        if not kids:
            fields[name] = {
                "kind": _kind_of(text),
                "sample": text,
                "indexed": idx is not None,
                "children": 0,
            }
        else:
            fields[name] = {
                "kind": "composite",
                "sample": "",
                "indexed": idx is not None,
                "children": len(kids),
            }
            fields.update(condition_fields(child, name))
    return fields


def _append_sample(field: dict, sample: str, limit: int = 5) -> None:
    samples = field.setdefault("samples", [])
    if sample and sample not in samples:
        samples.append(sample)
        del samples[limit:]


def extract_text_schema(xml_data: bytes,
                        xenv_data: bytes,
                        prp_data: bytes) -> dict:
    """从三个文本成员构建单项目 schema。"""
    mx = pphxml.parse_main_xml(xml_data)
    xenv = pphxml.parse_xenv(xenv_data)
    prp = pphxml.parse_prp(prp_data)

    cond_types: dict[str, dict] = {}
    for cond in mx.conditions():
        summary = mx.condition_summary(cond)
        tname = summary.get("type") or "<unknown>"
        entry = cond_types.setdefault(tname, {
            "count": 0,
            "regions": [],
            "fields": {},
        })
        entry["count"] += 1
        for r in summary.get("regions", []):
            rname = r[1] if isinstance(r, tuple) else str(r)
            if rname and rname not in entry["regions"]:
                entry["regions"].append(rname)
        for fname, fdesc in condition_fields(cond).items():
            target = entry["fields"].setdefault(fname, {
                "kind": fdesc["kind"],
                "indexed": fdesc["indexed"],
                "children": fdesc["children"],
                "samples": [],
            })
            if target["kind"] == fdesc["kind"]:
                _append_sample(target, fdesc["sample"])

    xenv_sections: dict[str, dict] = {}
    for sec_name, keys in xenv.sections.items():
        sec = xenv_sections.setdefault(sec_name, {})
        for kname, val in keys.items():
            entry = sec.setdefault(kname, {"values": {}})
            entry["values"][val] = entry["values"].get(val, 0) + 1

    prp_groups: dict[str, dict] = {}
    for group in prp.groups:
        gkey = group.findtext("key") or ""
        gname = group.findtext("name") or gkey
        entry = prp_groups.setdefault(gkey, {"name": gname, "entries": {}})
        for e in prp.entries(group):
            ekey = prp.entry_key(e)
            eentry = entry["entries"].setdefault(ekey, {
                "props": {},
                "count": 0,
            })
            eentry["count"] += 1
            for pk, pv in prp.entry_properties(e).items():
                if pk not in eentry["props"]:
                    eentry["props"][pk] = pv

    return {
        "project": {
            "name": mx.project_name,
            "version": mx.version,
        },
        "conditions": {
            "count": len(mx.conditions()),
            "types": cond_types,
        },
        "xenv": {"sections": xenv_sections},
        "prp": {"groups": prp_groups},
    }


def extract_archive_schema(arch: PphArchive) -> dict:
    """从 PPH 归档直接抽取。"""
    def _read(role: str) -> Optional[bytes]:
        members = arch.by_role(role)
        if not members:
            return None
        return arch.read_member(members[0].name)

    xml_data = _read("project_xml")
    xenv_data = _read("environment")
    prp_data = _read("property_db")
    if xml_data is None or xenv_data is None or prp_data is None:
        raise ValueError("PPH 缺少 main.xml / main.xenv / main.prp 成员")
    return extract_text_schema(xml_data, xenv_data, prp_data)


def merge_schemas(schemas: Iterable[dict]) -> dict:
    """合并多个项目 schema，字段样本去重保留前若干项。"""
    out: dict = {
        "projects": [],
        "conditions": {"count": 0, "types": {}},
        "xenv": {"sections": {}},
        "prp": {"groups": {}},
    }
    for schema in schemas:
        proj = schema.get("project", {})
        out["projects"].append(proj.get("name", ""))
        cond = schema.get("conditions", {})
        out["conditions"]["count"] += cond.get("count", 0)
        for tname, tentry in cond.get("types", {}).items():
            target = out["conditions"]["types"].setdefault(tname, {
                "count": 0,
                "regions": [],
                "fields": {},
            })
            target["count"] += tentry.get("count", 0)
            for r in tentry.get("regions", []):
                if r not in target["regions"]:
                    target["regions"].append(r)
            for fname, fdesc in tentry.get("fields", {}).items():
                tf = target["fields"].setdefault(fname, {
                    "kind": fdesc.get("kind", "string"),
                    "indexed": bool(fdesc.get("indexed")),
                    "children": int(fdesc.get("children", 0)),
                    "samples": [],
                })
                for s in fdesc.get("samples", []):
                    _append_sample(tf, s)
        for sec_name, keys in schema.get("xenv", {}).get("sections", {}).items():
            tsec = out["xenv"]["sections"].setdefault(sec_name, {})
            for kname, kentry in keys.items():
                tk = tsec.setdefault(kname, {"values": {}})
                for val, n in kentry.get("values", {}).items():
                    tk["values"][val] = tk["values"].get(val, 0) + n
        for gkey, gentry in schema.get("prp", {}).get("groups", {}).items():
            tg = out["prp"]["groups"].setdefault(
                gkey, {"name": gentry.get("name", gkey), "entries": {}})
            for ekey, eentry in gentry.get("entries", {}).items():
                te = tg["entries"].setdefault(ekey, {"props": {}, "count": 0})
                te["count"] += eentry.get("count", 0)
                for pk, pv in eentry.get("props", {}).items():
                    te["props"].setdefault(pk, pv)
    return out


def write_schema_json(schema: dict, path: str | Path) -> Path:
    """把 schema 写成 UTF-8 JSON（保留可读缩进）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schema, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


def load_schema_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
