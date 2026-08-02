#!/usr/bin/env python3
"""PPH 中 XML / 文本成员的解析。

* ``main.xml`` — scFLOWpre 项目定义。**注意**：scFLOW 使用带索引标签的
  XML 方言（``<SECTITEM[0]>``），标准 XML 解析器无法接受；本模块先做
  标签名净化（``TAG[N]`` → ``TAG__IDXN``，索引记录在 ``_index`` 属性）。
* ``main.prp`` — 材料/物性数据库（标准 XML：group/entry 层次）。
* ``main.xenv`` — 环境/单位/容差设置（标准 XML，UTF-8 BOM）。
* ``main.js`` — 用户子程序脚本（JavaScript，``//@FormattedScript`` 段）。

观测到的索引标签家族：``SECTITEM[N]``、``PRISMITEM[N]``、``SMOOTHITEM[N]``
（净化后 ``TAG__IDXN``，``serialize_main_xml`` 可还原）。

快照 ``LENGTHVWU``/``DPOINTU`` 中 ``unit_type`` 码到 xenv 单位的解析见
``UNIT_TYPE_TO_XENV_KEY`` / ``resolve_snapshot_unit``。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

_INDEXED_TAG = re.compile(r"<(/?)([A-Za-z_][\w.]*)\[(\d+)\](>|/>)")


def sanitize_scflow_xml(text: str) -> str:
    """把 scFLOW 的 ``<TAG[N]>`` 方言转换为合法 XML。

    ``<SECTITEM[0]>`` → ``<SECTITEM__IDX0>``；调用方可用
    ``restore_index(tag)`` 取回 ``(原名, 索引)``。闭合部分（``>`` 或 ``/>``）
    随标签整体替换，避免向元素文本注入多余 ``>``。
    """
    return _INDEXED_TAG.sub(r"<\g<1>\g<2>__IDX\g<3>\g<4>", text)


def restore_index(tag: str) -> tuple[str, Optional[int]]:
    """把净化后的标签名还原为 ``(原名, 索引或 None)``。"""
    m = re.match(r"^(.*?)__IDX(\d+)$", tag)
    if m:
        return m.group(1), int(m.group(2))
    return tag, None


_IDX_SAFE_TAG = re.compile(r"^([A-Za-z_][\w.]*)__IDX(\d+)$")


def serialize_main_xml(root: ET.Element) -> str:
    """把净化后的 ElementTree 写回 scFLOW 方言。

    ``TAG__IDXN`` → ``TAG[N]``，与 :func:`sanitize_scflow_xml` 互逆，
    支撑修改后的 main.xml 写回 .pph（见 pphwriter.py）。
    """
    text = ET.tostring(root, encoding="unicode")
    return re.sub(r"<(/?)([A-Za-z_][\w.]*)__IDX(\d+)(/?)([^>]*>)",
                  r"<\1\2[\3]\4\5", text)


# 快照 unit_type 码 → xenv 长度单位键（样例恒为 1 == MODEL_LENGTH_UNIT，
# 即 'm'）。其余码值需多单位制样例确认后补充。
UNIT_TYPE_TO_XENV_KEY: dict[int, str] = {1: "MODEL_LENGTH_UNIT"}


def resolve_snapshot_unit(unit_type: int,
                          xenv: "XenvSettings") -> Optional[str]:
    """把快照 ``LENGTHVWU``/``DPOINTU`` 的 ``unit_type`` 解析为 xenv 单位串。"""
    key = UNIT_TYPE_TO_XENV_KEY.get(unit_type)
    if key is None:
        return None
    return xenv.get("UNIT", key)


@dataclass
class XenvSettings:
    """main.xenv：Section/Key 层次设置。"""

    sections: dict[str, dict[str, str]] = field(default_factory=dict)

    def get(self, section: str, key: str, default: Optional[str] = None):
        return self.sections.get(section, {}).get(key, default)


def parse_xenv(data: bytes) -> XenvSettings:
    """解析 main.xenv（UTF-8 BOM 的 Section/Key XML）。"""
    text = data.decode("utf-8-sig")
    root = ET.fromstring(text)
    out = XenvSettings()
    for sec in root.iter("Section"):
        name = sec.get("name", "")
        for key in sec.iter("Key"):
            kname = key.get("name", "")
            # 去掉注释节点文本
            val = (key.text or "").strip()
            out.sections.setdefault(name, {})[kname] = val
    return out


def serialize_xenv(xenv: XenvSettings) -> bytes:
    """将 :class:`XenvSettings` 写回 main.xenv（UTF-8 BOM + CRLF）。

    注释节点不会保留；值与 Section/Key 层次与读端一致，可供 Save As 覆盖。
    """
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<Data type="env">',
    ]
    for sec_name, keys in xenv.sections.items():
        lines.append(f'    <Section name="{_xml_attr(sec_name)}">')
        for kname, val in keys.items():
            lines.append(f'        <Key name="{_xml_attr(kname)}">')
            lines.append(f"            {_xml_text(val)}")
            lines.append("        </Key>")
        lines.append("    </Section>")
    lines.append("</Data>")
    lines.append("")
    body = "\r\n".join(lines)
    return ("\ufeff" + body).encode("utf-8")


def _xml_attr(s: str) -> str:
    return (s.replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _xml_text(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def set_xenv_value(xenv: XenvSettings, section: str, key: str, value: str) -> None:
    """设置/新增 Section.Key。"""
    xenv.sections.setdefault(section, {})[key] = value


@dataclass
class PrpDatabase:
    """main.prp：材料物性库。"""

    version: str = ""
    date: str = ""
    groups: list[ET.Element] = field(default_factory=list)

    def group_names(self) -> list[str]:
        names = []
        for g in self.groups:
            k = g.findtext("key")
            names.append(k if k is not None else "")
        return names

    def entries(self, group: ET.Element) -> list[ET.Element]:
        return group.findall("entry")

    @staticmethod
    def entry_key(entry: ET.Element) -> str:
        return entry.findtext("key") or ""

    @staticmethod
    def entry_properties(entry: ET.Element) -> dict[str, str]:
        """提取 entry 下的简单 ``<tag>值</tag>`` 属性（跳过嵌套容器）。"""
        props: dict[str, str] = {}
        for ch in entry:
            if ch.tag in ("key", "name"):
                continue
            if len(ch) == 0:
                val = (ch.text or "").strip()
                if val:
                    props[ch.tag] = val
        return props


def parse_prp(data: bytes) -> PrpDatabase:
    """解析 main.prp 材料物性库。"""
    root = ET.fromstring(data.decode("utf-8"))
    out = PrpDatabase(version=root.get("version", ""), date=root.get("date", ""))
    out.groups = root.findall("group")
    return out


@dataclass
class MainXml:
    """main.xml：scFLOWpre 项目定义（已净化的 ElementTree）。"""

    root: ET.Element

    @property
    def version(self) -> str:
        return self.root.findtext("version", "")

    @property
    def project_name(self) -> str:
        return self.root.findtext("project/name", "")

    def section(self, name: str) -> Optional[ET.Element]:
        return self.root.find(name)

    def conditions(self) -> list[ET.Element]:
        cond = self.root.find("conditions")
        if cond is None:
            return []
        return cond.findall("condition")

    @staticmethod
    def condition_summary(cond: ET.Element) -> dict:
        out = {"type": cond.findtext("type", ""), "name": cond.findtext("name", "")}
        regions = cond.find("regions")
        if regions is not None:
            out["regions"] = [(restore_index(r.tag)[0], (r.text or "").strip())
                              for r in regions]
        return out


def parse_main_xml(data: bytes) -> MainXml:
    """解析 main.xml（自动净化索引标签方言）。"""
    text = data.decode("utf-8")
    root = ET.fromstring(sanitize_scflow_xml(text))
    return MainXml(root)


@dataclass
class JsScript:
    """main.js：用户子程序脚本。"""

    source: str

    def functions(self) -> list[str]:
        """脚本中定义的函数名列表。"""
        return re.findall(r"^\s*function\s+([A-Za-z_]\w*)\s*\(",
                          self.source, re.MULTILINE)

    def has_user_code(self) -> bool:
        """是否存在用户填入的实现（非空函数体）。"""
        for m in re.finditer(r"function\s+\w+\s*\([^)]*\)\s*\{(.*?)\}",
                             self.source, re.DOTALL):
            if m.group(1).strip():
                return True
        return False


def parse_main_js(data: bytes) -> JsScript:
    return JsScript(data.decode("utf-8", errors="replace"))
