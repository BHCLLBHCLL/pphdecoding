#!/usr/bin/env python3
"""厂商材料与数据五库只读解析（P4-2）。

覆盖 Cradle 安装目录 ``Programs_x64`` 下：

==========================  =========================================
库文件                       内容
==========================  =========================================
``scFLOWpre.prp``            scFLOWpre 属性库（流体/固体，group/entry，
                             与 main.prp 同 schema，作为 GUI 兜底库）
``standard_property_ENG.xml`` STpre 标准物性（group[type]/entry）
``thermal_property_ENG.xml``  STpre 热物性（固体热传导/比热/密度）
``SCTpre.prp_struct``        结构金属材料（定长文本：弹性模量/泊松比/
                             密度/热膨胀/参考温度）
``heattransfer_ENG.xml``     换热系数预设（外壁/屋顶/室内地板等）
``solar_ENG.xml``            世界城市太阳位置（纬度/经度/标准子午线）
``SolarNEDO11.xml``          日本 NEDO 气象站点（MONSOLA-11/METPV-11）
``reaction_ENG.xml``         反应组分库（mole/类型/热化学表/元素组成）
==========================  =========================================

定位优先级：环境变量 ``SCFLOWPRE_PROGRAMS`` → 默认安装路径 →
``condition_tree.locate_definition()`` 推断。全部只读，不落盘。
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_PROGRAMS = Path(
    r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64")


def locate_programs() -> Optional[Path]:
    """定位 Programs_x64（env → 默认路径 → condition_tree 推断）。"""
    env = os.environ.get("SCFLOWPRE_PROGRAMS")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    if DEFAULT_PROGRAMS.is_dir():
        return DEFAULT_PROGRAMS
    try:
        from condition_tree import locate_definition
        found = locate_definition()
        if found is not None:
            cand = Path(found)
            for anc in cand.parents:
                if (anc / "scFLOWpre.prp").is_file():
                    return anc
    except Exception:  # noqa: BLE001
        pass
    return None


# ---------------------------------------------------------------------------
# 1) 属性库（scFLOWpre.prp / standard/thermal_property，group/entry 形态）
# ---------------------------------------------------------------------------

@dataclass
class MaterialEntry:
    name: str                      # 英文名 / key
    name_jpn: str = ""
    group: str = ""                # 所属组（如 gas(incompressible)）
    kind: str = ""                 # fluid / solid / metal / obstacle
    props: dict[str, str] = field(default_factory=dict)


def _parse_property_xml(data: bytes) -> list[MaterialEntry]:
    """``<property><group>(<key>|<type>+<name>)…<entry>`` 双方言解析。"""
    root = ET.fromstring(data.decode("utf-8", errors="replace"))
    out: list[MaterialEntry] = []
    for g in root.findall("group"):
        # scFLOWpre.prp：<key> + <name lang>; STpre：<type> + <name>
        gname = (g.findtext("key") or "").strip() \
            or (g.findtext("name") or "").strip() or "(group)"
        gtype = (g.findtext("type") or "").strip()
        for e in g.findall("entry"):
            key = (e.findtext("key") or "").strip()
            names = {n.get("lang"): (n.text or "").strip()
                     for n in e.findall("name")}
            name = key or names.get("eng") or names.get("jpn") \
                or (e.findtext("name") or "").strip()
            if not name:
                continue
            kind = (e.findtext("type") or "").strip() or gtype
            props: dict[str, str] = {}
            for ch in e:
                if ch.tag in ("key", "name", "type") or len(ch):
                    continue
                v = (ch.text or "").strip()
                if v:
                    props[ch.tag] = v
            out.append(MaterialEntry(
                name=name,
                name_jpn=names.get("jpn", ""),
                group=gname,
                kind=kind,
                props=props,
            ))
    return out


# ---------------------------------------------------------------------------
# 2) 结构金属库（SCTpre.prp_struct，定长文本）
# ---------------------------------------------------------------------------

@dataclass
class StructMetal:
    name: str
    category: str          # pure_metal / alloy ...
    model: str             # isotropic_elastic ...
    young: float = 0.0     # 弹性模量 [Pa]
    poisson: float = 0.0
    density: float = 0.0   # [kg/m3]
    thermal_exp: float = 0.0
    ref_temp: float = 20.0


def parse_prp_struct(text: str) -> list[StructMetal]:
    """四行一组：名称行 / 模型行 / 状态行 / 数值行。"""
    lines = [ln.rstrip() for ln in text.splitlines()]
    out: list[StructMetal] = []
    i = 0
    while i < len(lines) - 3:
        head = lines[i].strip()
        if not head or head.startswith("#"):
            i += 1
            continue
        parts = head.split(None, 1)
        if len(parts) != 2:
            i += 1
            continue
        name, category = parts[0], parts[1].strip()
        model = lines[i + 1].strip()
        status = lines[i + 2].strip()
        nums = lines[i + 3].split()
        if model and status and len(nums) >= 5:
            try:
                out.append(StructMetal(
                    name=name, category=category, model=model,
                    young=float(nums[0]), poisson=float(nums[1]),
                    density=float(nums[2]), thermal_exp=float(nums[3]),
                    ref_temp=float(nums[4]),
                ))
                i += 4
                continue
            except ValueError:
                pass
        i += 1
    return out


# ---------------------------------------------------------------------------
# 3) 换热系数预设（heattransfer_ENG.xml）
# ---------------------------------------------------------------------------

@dataclass
class HeatTransferPreset:
    type_id: int      # 1=垂直外壁 2=水平/地板 3=室内等
    name: str
    subname: str = ""
    values: list[float] = field(default_factory=list)  # W/m2K


_HT_TYPE_LABELS = {1: "Wall (vertical)", 2: "Floor / horizontal",
                   3: "Indoor", 4: "Other"}


def parse_heattransfer(data: bytes) -> list[HeatTransferPreset]:
    root = ET.fromstring(data.decode("utf-8", errors="replace"))
    out: list[HeatTransferPreset] = []
    for e in root.findall("entry"):
        try:
            tid = int((e.findtext("type") or "0").strip())
        except ValueError:
            tid = 0
        vals: list[float] = []
        for v in (e.findtext("value") or "").split(","):
            v = v.strip()
            try:
                vals.append(float(v))
            except ValueError:
                pass
        out.append(HeatTransferPreset(
            type_id=tid,
            name=(e.findtext("name") or "").strip(),
            subname=(e.findtext("subname") or "").strip(),
            values=vals,
        ))
    return out


# ---------------------------------------------------------------------------
# 4) 太阳位置 / NEDO 站点
# ---------------------------------------------------------------------------

@dataclass
class SolarLocation:
    name: str
    latitude: float = 0.0
    longitude: float = 0.0
    standard: float = 0.0    # 标准子午线 [deg]


@dataclass
class NedoSite:
    no: str
    category: str        # 都道府县（eng）
    category_jpn: str = ""
    name: str = ""       # eng
    name_jpn: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    standard: float = 135.0
    elevation: float = 0.0


def parse_solar_locations(data: bytes) -> list[SolarLocation]:
    root = ET.fromstring(data.decode("utf-8", errors="replace"))
    out = []
    for e in root.findall("./location/entry"):
        def _f(tag: str) -> float:
            try:
                return float((e.findtext(tag) or "0").strip() or 0)
            except ValueError:
                return 0.0
        name = (e.findtext("name") or "").strip()
        if name:
            out.append(SolarLocation(
                name=name, latitude=_f("latitude"),
                longitude=_f("longitude"), standard=_f("standard")))
    return out


def parse_nedo_sites(data: bytes) -> list[NedoSite]:
    root = ET.fromstring(data.decode("utf-8", errors="replace"))
    out: list[NedoSite] = []
    for cat in root.findall("category"):
        names = {n.get("lang"): (n.text or "").strip()
                 for n in cat.findall("name")}
        for s in cat.findall("site"):
            snames = {n.get("lang"): (n.text or "").strip()
                      for n in s.findall("name")}

            def _f(tag: str) -> float:
                try:
                    return float((s.findtext(tag) or "0").strip() or 0)
                except ValueError:
                    return 0.0
            out.append(NedoSite(
                no=s.get("no", ""),
                category=names.get("eng", ""),
                category_jpn=names.get("jpn", ""),
                name=snames.get("eng", ""),
                name_jpn=snames.get("jpn", ""),
                latitude=_f("latitude"), longitude=_f("longitude"),
                standard=_f("standard"), elevation=_f("elevation"),
            ))
    return out


# ---------------------------------------------------------------------------
# 5) 反应组分库（reaction_ENG.xml）
# ---------------------------------------------------------------------------

@dataclass
class ReactionSpecies:
    name: str
    mole: float = 0.0
    type: str = ""          # gas / liquid / solid
    unit: str = ""
    composition: dict[str, float] = field(default_factory=dict)


def parse_reaction_species(data: bytes) -> list[ReactionSpecies]:
    root = ET.fromstring(data.decode("utf-8", errors="replace"))
    out: list[ReactionSpecies] = []
    for e in root.findall("./material/entry"):
        name = (e.findtext("name") or "").strip()
        if not name:
            continue
        try:
            mole = float((e.findtext("mole") or "0").strip() or 0)
        except ValueError:
            mole = 0.0
        comp: dict[str, float] = {}
        for c in e.findall("./composition/component"):
            # 实测格式：<component no="1"> C,1 </component>（元素,个数）
            bits = (c.text or "").split(",")
            if len(bits) == 2:
                elem = bits[0].strip()
                try:
                    comp[elem] = float(bits[1])
                except ValueError:
                    pass
        out.append(ReactionSpecies(
            name=name, mole=mole,
            type=(e.findtext("type") or "").strip(),
            unit=(e.findtext("unit") or "").strip(),
            composition=comp,
        ))
    return out


# ---------------------------------------------------------------------------
# 汇总入口（懒加载 + 进程内缓存）
# ---------------------------------------------------------------------------

class MaterialLib:
    """五库只读访问（找不到安装目录时各访问器返回空表）。"""

    def __init__(self, programs: Optional[Path] = None):
        self.programs = programs or locate_programs()

    def _read(self, fname: str) -> Optional[bytes]:
        if self.programs is None:
            return None
        p = self.programs / fname
        return p.read_bytes() if p.is_file() else None

    def property_entries(self) -> list[MaterialEntry]:
        """scFLOWpre.prp + standard/thermal_property（合并去重，按名）。"""
        out: list[MaterialEntry] = []
        seen: set[str] = set()
        for fname in ("scFLOWpre.prp", "standard_property_ENG.xml",
                      "thermal_property_ENG.xml"):
            data = self._read(fname)
            if data is None:
                continue
            for m in _parse_property_xml(data):
                if m.name in seen:
                    continue
                seen.add(m.name)
                out.append(m)
        return out

    def fluids(self) -> list[MaterialEntry]:
        return [m for m in self.property_entries()
                if m.kind == "fluid"]

    def solids(self) -> list[MaterialEntry]:
        return [m for m in self.property_entries()
                if m.kind in ("solid", "heat_conduction", "solid_fluid")]

    def metals(self) -> list[StructMetal]:
        data = self._read("SCTpre.prp_struct")
        if data is None:
            return []
        return parse_prp_struct(
            data.decode("utf-8", errors="replace"))

    def heat_transfer_presets(self) -> list[HeatTransferPreset]:
        data = self._read("heattransfer_ENG.xml")
        return parse_heattransfer(data) if data else []

    def solar_locations(self) -> list[SolarLocation]:
        data = self._read("solar_ENG.xml")
        return parse_solar_locations(data) if data else []

    def nedo_sites(self) -> list[NedoSite]:
        data = self._read("SolarNEDO11.xml")
        return parse_nedo_sites(data) if data else []

    def reaction_species(self) -> list[ReactionSpecies]:
        data = self._read("reaction_ENG.xml")
        return parse_reaction_species(data) if data else []

    def summary(self) -> dict:
        return {
            "programs": str(self.programs) if self.programs else "",
            "fluids": len(self.fluids()),
            "solids": len(self.solids()),
            "metals": len(self.metals()),
            "heat_transfer_presets": len(self.heat_transfer_presets()),
            "solar_locations": len(self.solar_locations()),
            "nedo_sites": len(self.nedo_sites()),
            "reaction_species": len(self.reaction_species()),
        }


_LIB_CACHE: Optional[MaterialLib] = None


def material_lib_cached() -> Optional[MaterialLib]:
    """进程内共享实例（None = 未安装 Cradle）。"""
    global _LIB_CACHE
    if _LIB_CACHE is None:
        lib = MaterialLib()
        if lib.programs is None:
            return None
        _LIB_CACHE = lib
    return _LIB_CACHE


# ---------------------------------------------------------------------------
# 9) prp 写端（P12-C：P4-2 只读补齐，scFLOWpre.prp / main.prp 同方言）
# ---------------------------------------------------------------------------

@dataclass
class PrpEntry:
    key: str
    name_jpn: str = ""
    name_eng: str = ""
    kind: str = ""                       # <type>（fluid/solid/...）
    subtype: str = ""
    props: list[tuple[str, str]] = field(default_factory=list)  # 有序 (tag, value)

    def as_material_entry(self, group: str) -> MaterialEntry:
        return MaterialEntry(name=self.key or self.name_eng,
                             name_jpn=self.name_jpn, group=group,
                             kind=self.kind, props=dict(self.props))


@dataclass
class PrpGroup:
    key: str
    name_jpn: str = ""
    name_eng: str = ""
    entries: list[PrpEntry] = field(default_factory=list)


@dataclass
class PrpDocument:
    groups: list[PrpGroup] = field(default_factory=list)


def parse_prp_document(data: bytes) -> PrpDocument:
    """结构化解析 prp 方言（保留 entry key/双语名/type/subtype/有序属性）。"""
    root = ET.fromstring(data.decode("utf-8", errors="replace"))
    doc = PrpDocument()
    for g in root.findall("group"):
        grp = PrpGroup(
            key=(g.findtext("key") or "").strip(),
            name_jpn=next((n.text or "" for n in g.findall("name")
                           if n.get("lang") == "jpn"), ""),
            name_eng=next((n.text or "" for n in g.findall("name")
                           if n.get("lang") == "eng"), ""),
        )
        for e in g.findall("entry"):
            props: list[tuple[str, str]] = []
            for ch in e:
                if ch.tag in ("key", "name", "type", "subtype") or len(ch):
                    continue
                v = (ch.text or "").strip()
                if v:
                    props.append((ch.tag, v))
            grp.entries.append(PrpEntry(
                key=(e.findtext("key") or "").strip(),
                name_jpn=next((n.text or "" for n in e.findall("name")
                               if n.get("lang") == "jpn"), ""),
                name_eng=next((n.text or "" for n in e.findall("name")
                               if n.get("lang") == "eng"), ""),
                kind=(e.findtext("type") or "").strip(),
                subtype=(e.findtext("subtype") or "").strip(),
                props=props,
            ))
        doc.groups.append(grp)
    return doc


def write_prp_document(doc: PrpDocument, path: str | Path) -> Path:
    """按 scFLOWpre.prp 方言写出（UTF-8 BOM + CRLF + 制表缩进）。

    与厂商原始文件的差异（如实记录）：不含 ``<!-- date/time -->``
    注释头；其余可解析结构（组/条目/属性顺序）保持恒等。
    """
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        "<!-- Property Data Base -->",
        "<property>",
    ]
    for g in doc.groups:
        lines.append("\t<group>")
        if g.key:
            lines.append(f"\t\t<key>{g.key}</key>")
        if g.name_jpn:
            lines.append(f'\t\t<name lang="jpn">{g.name_jpn}</name>')
        if g.name_eng:
            lines.append(f'\t\t<name lang="eng">{g.name_eng}</name>')
        for e in g.entries:
            lines.append("\t\t\t<entry>")
            if e.key:
                lines.append(f"\t\t\t\t<key>{e.key}</key>")
            if e.name_jpn:
                lines.append(f'\t\t\t\t<name lang="jpn">{e.name_jpn}</name>')
            if e.name_eng:
                lines.append(f'\t\t\t\t<name lang="eng">{e.name_eng}</name>')
            if e.kind:
                lines.append(f"\t\t\t\t<type>{e.kind}</type>")
            if e.subtype:
                lines.append(f"\t\t\t\t<subtype>{e.subtype}</subtype>")
            for tag, v in e.props:
                lines.append(f"\t\t\t\t<{tag}>{v}</{tag}>")
            lines.append("\t\t\t</entry>")
        lines.append("\t</group>")
    lines.append("</property>")
    text = "\r\n".join(lines) + "\r\n"
    Path(path).write_bytes(text.encode("utf-8-sig"))
    return Path(path)


def parse_prp_document_from_file(path: str | Path) -> PrpDocument:
    return parse_prp_document(Path(path).read_bytes())


def write_prp_struct(metals: list[StructMetal], path: str | Path) -> Path:
    """SCTpre.prp_struct 定长文本写端（四行一组，%g 数值）。

    状态行实测厂商库恒为 ``complete``（parse 端不保留）；与厂商原始
    文件差异：数值格式化走 ``%g``（原文为定宽空格），解析级恒等
    （parse→write→parse 结果一致）。
    """
    lines = ['# prp_struct version="2.0" encoding="UTF-8"']
    for m in metals:
        lines += [
            # parse 端 name 已含括注（'copper(Cu)'），与 category 空格分隔
            f"{m.name} {m.category}",
            m.model,
            "complete",
            "%g %g %g %g %g" % (m.young, m.poisson, m.density,
                                m.thermal_exp, m.ref_temp),
        ]
    Path(path).write_bytes(("\n".join(lines) + "\n").encode("utf-8-sig"))
    return Path(path)
