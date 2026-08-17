#!/usr/bin/env python3
"""工程登记与 Save 覆盖收集（Wave A）。

把「空工程模板 / CAD 零件登记 / Save As 追加 ZIP 成员 / MDL 面区域名表」
从 GUI 抽成无 Qt 依赖的纯函数，便于 pytest 钉死：

* :func:`collect_save_overrides` — 源 ZIP 没有的成员与 dirty 成员写入 override
* :func:`add_xml_part` — ``meshinggroup/movinggroup/group/part`` 登记
* :func:`mdl_bytes_from_tess` / :func:`append_surface_region_bytes`
* :func:`cad_meshes_to_surface` — Import 剖分预览 → (points, tris)
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional
from xml.etree import ElementTree as ET

import numpy as np

import mdl
import pphxml

DEFAULT_SGS = "MeshingGroup_1"
DEFAULT_MDL_MEMBER = "meshinggroup1_part.mdl"


def collect_save_overrides(
        arch,
        member_bytes: dict[str, bytes],
        editor_overrides: Optional[dict[str, bytes]] = None,
        dirty: Optional[Iterable[str]] = None,
) -> dict[str, bytes]:
    """Save As / rewrite 用的成员覆盖表。

    包含：文本编辑器 overrides（优先）、``dirty`` 集合、以及
    ``member_bytes`` 里源归档 *没有* 的新成员（导入的 ``.x_t`` / 生成的
    ``.mdl`` ``.oct`` ``.gph``）。不扫描全部 GPH 做字节对比。
    """
    out = dict(editor_overrides or {})
    names: set[str] = set()
    if arch is not None:
        names = {m.name for m in arch.members}
    dirty_set = {str(n) for n in (dirty or ())}
    for name, data in (member_bytes or {}).items():
        if not name or data is None:
            continue
        if name in out:
            continue
        if name not in names or name in dirty_set:
            out[name] = data
    return out


def empty_project_members(*, name: str = "Untitled") -> dict[str, bytes]:
    """最小可解析空工程：main.xml / xenv / prp / js（含 movinggroup 槽）。"""
    now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<scFLOWpre>
  <version>5225.20302.20251223</version>
  <date>{now}</date>
  <project>
    <name>{name}</name>
    <showmode>1</showmode>
  </project>
  <parts>
    <meshinggroup>
      <phase>0</phase>
      <analysis_model_flag>false</analysis_model_flag>
      <sgs_name>{DEFAULT_SGS}</sgs_name>
      <meshonly>false</meshonly>
      <mesh_visible>true</mesh_visible>
      <visible>true</visible>
      <mesh_state>0</mesh_state>
      <org_name/>
      <movinggroup>
        <expand>true</expand>
        <visible>true</visible>
        <group>
          <name>{name}</name>
          <expand>true</expand>
          <expand_discontinuous>true</expand_discontinuous>
          <group_part>false</group_part>
          <cvols_for_octmesh/>
        </group>
      </movinggroup>
    </meshinggroup>
  </parts>
  <regions/>
  <conditions>
    <analysis_type>
      <Flow>true</Flow>
    </analysis_type>
    <basic_param>
      <steady>true</steady>
      <end_cycle>100</end_cycle>
    </basic_param>
  </conditions>
</scFLOWpre>
"""
    xenv = pphxml.XenvSettings()
    for sec, key, val in (
        ("TYPE", "PROJECT_TYPE", "scflow"),
        ("MESH", "MESHER", "0"),
        ("MESH", "SURF_MESHER", "0"),
        ("FACET", "MDL_METHOD", "1"),
        ("FACET", "USE_FACETTER", "true"),
        ("FACET", "PROJECT_SOLIDS", "true"),
        ("FACET", "PROJECT_SHEETS", "true"),
        ("FACET", "FACET_ACCURACY_SPECIFY_TYPE", "0"),
        ("FACET", "USE_ABSOLUTE_VALUE", "false"),
        ("FACET", "SIMPLE_CHORD_TOLERANCE", "1"),
        ("FACET", "SIMPLE_MAX_ANGLE", "10"),
        ("FACET", "SIMPLE_MAX_WIDTH", "5"),
        ("FACET", "SOLID_BASE_MINIMUM_ANGLE", "10"),
        ("FACET", "SOLID_BASE_LENGTH_FACTOR", "0.05"),
        ("FACET", "SOLID_BASE_TINY_FACE_WIDTH_RATIO", "0.05"),
    ):
        pphxml.set_xenv_value(xenv, sec, key, val)
    prp = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<prp version="1" date="">\n'
        "</prp>\n"
    )
    js = (
        "//@FormattedScript\n"
        "function usr_input(nlines)\n{\n\n}\n"
    )
    return {
        "main.xml": xml.encode("utf-8"),
        "main.xenv": pphxml.serialize_xenv(xenv),
        "main.prp": prp.encode("utf-8"),
        "main.js": js.encode("utf-8"),
    }


def ensure_meshinggroup(xml: pphxml.MainXml,
                        sgs_name: str = DEFAULT_SGS) -> ET.Element:
    parts = xml.section("parts")
    if parts is None:
        parts = ET.SubElement(xml.root, "parts")
    found = None
    for mg in parts.findall("meshinggroup"):
        if (mg.findtext("sgs_name") or "").strip() == sgs_name:
            found = mg
            break
        if found is None:
            found = mg
    if found is not None:
        return found
    mg = ET.SubElement(parts, "meshinggroup")
    ET.SubElement(mg, "phase").text = "0"
    ET.SubElement(mg, "sgs_name").text = sgs_name
    return mg


def _ensure_group(mg: ET.Element, group_name: str) -> ET.Element:
    mv = mg.find("movinggroup")
    if mv is None:
        mv = ET.SubElement(mg, "movinggroup")
        ET.SubElement(mv, "expand").text = "true"
        ET.SubElement(mv, "visible").text = "true"
    grp = mv.find("group")
    if grp is None:
        grp = ET.SubElement(mv, "group")
        ET.SubElement(grp, "name").text = group_name
        ET.SubElement(grp, "expand").text = "true"
        ET.SubElement(grp, "expand_discontinuous").text = "true"
        ET.SubElement(grp, "group_part").text = "false"
        ET.SubElement(grp, "cvols_for_octmesh")
    elif not (grp.findtext("name") or "").strip():
        el = grp.find("name")
        if el is None:
            el = ET.SubElement(grp, "name")
        el.text = group_name
    return grp


def add_xml_part(xml: pphxml.MainXml, name: str, *,
                 group_name: Optional[str] = None,
                 sgs_name: str = DEFAULT_SGS) -> ET.Element:
    """在 ``meshinggroup/movinggroup/group`` 下追加 ``<part>``。

    结构对齐 box.pph（``parts → meshinggroup → movinggroup → group → part``）。
    同名 part 已存在则返回现有节点。
    """
    name = (name or "").strip() or "Part"
    mg = ensure_meshinggroup(xml, sgs_name)
    grp = _ensure_group(mg, group_name or name)
    for pt in grp.findall("part"):
        if (pt.findtext("name") or "").strip() == name:
            return pt
    pt = ET.SubElement(grp, "part")
    ET.SubElement(pt, "name").text = name
    ET.SubElement(pt, "expand").text = "false"
    ET.SubElement(pt, "expand_discontinuous").text = "false"
    ET.SubElement(pt, "group_part").text = "false"
    ET.SubElement(pt, "cvols_for_octmesh")
    ET.SubElement(pt, "visible").text = "true"
    ET.SubElement(pt, "attribute").text = "solid"
    return pt


def xml_part_names(xml: pphxml.MainXml) -> list[str]:
    names: list[str] = []
    parts = xml.section("parts")
    if parts is None:
        return names
    for pt in parts.iter("part"):
        n = (pt.findtext("name") or "").strip()
        if n and n not in names:
            names.append(n)
    return names


def cad_meshes_to_surface(meshes) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """Import 剖分预览（TessPart 或 ImportedBody）→ (points, tris)。"""
    pts_list: list[np.ndarray] = []
    tris_list: list[np.ndarray] = []
    base = 0
    for item in meshes or []:
        tess = getattr(item, "tess", item)
        pts = getattr(tess, "points", None)
        tris = getattr(tess, "triangles", None)
        if pts is None or tris is None:
            continue
        pts = np.asarray(pts, dtype=float).reshape(-1, 3)
        tris = np.asarray(tris, dtype=np.int64).reshape(-1, 3)
        if pts.size == 0 or tris.size == 0:
            continue
        pts_list.append(pts)
        tris_list.append(tris + base)
        base += len(pts)
    if not pts_list:
        return None
    return np.vstack(pts_list), np.vstack(tris_list)


def mdl_bytes_from_tess(points, faces, *,
                        app: str = "pphdecoding",
                        surface_regions=None) -> bytes:
    """剖分三角面 → 最小 ``*_part.mdl`` 字节。"""
    regions = list(surface_regions) if surface_regions is not None else None
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "part.mdl"
        mdl.write_mdl(p, points, faces, app=app, surface_regions=regions)
        return p.read_bytes()


def append_surface_region_bytes(mdl_bytes: bytes, name: str, *,
                                index: Optional[int] = None) -> bytes:
    """在 MDL 名表追加一条面区域（Register Region → 宿主 QueryFaceRegionByName）。"""
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "in.mdl"
        dst = Path(td) / "out.mdl"
        src.write_bytes(mdl_bytes)
        mdl.add_surface_region(src, name, index=index, output=dst)
        return dst.read_bytes()


def default_part_surface_region(part_name: str) -> str:
    """宿主默认面区域名 ``@PartSurface_<Part>``。"""
    n = (part_name or "Part").strip() or "Part"
    if n.startswith("@PartSurface_"):
        return n
    return f"@PartSurface_{n}"


def set_parts_control_flags(xml: pphxml.MainXml, *,
                            discontinuous: bool = False,
                            overset: bool = False,
                            wrapping: bool = False) -> ET.Element:
    """写入 ``conditions/parts_control``（对齐 box_disc：Discontinuous/overset/Wrapping）。"""
    cond = xml.section("conditions")
    if cond is None:
        cond = ET.SubElement(xml.root, "conditions")
    pc = cond.find("parts_control")
    if pc is None:
        pc = ET.SubElement(cond, "parts_control")
    for tag, val in (
        ("Discontinuous", discontinuous),
        ("overset", overset),
        ("Wrapping", wrapping),
    ):
        el = pc.find(tag)
        if el is None:
            el = ET.SubElement(pc, tag)
        el.text = "true" if val else "false"
    return pc


def read_parts_control_flags(xml: pphxml.MainXml) -> dict[str, bool]:
    """读取 ``conditions/parts_control`` 三开关（缺省 False）。"""
    cond = xml.section("conditions")
    pc = None if cond is None else cond.find("parts_control")
    def _flag(tag: str) -> bool:
        if pc is None:
            return False
        el = pc.find(tag)
        return (el is not None and (el.text or "").strip().lower() == "true")
    return {
        "discontinuous": _flag("Discontinuous"),
        "overset": _flag("overset"),
        "wrapping": _flag("Wrapping"),
    }
