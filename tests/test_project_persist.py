#!/usr/bin/env python3
"""Wave A：Save 追加成员 / XT 零件登记 / MDL 面区域 / CAD 剖分回退。"""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import mdl
import pph_parser
import pphwriter
import pphxml
import project_persist as pp

BOX_MDL = Path(__file__).resolve().parents[1] / "tests" / "box" / "meshinggroup1_part.mdl"


class _FakeArch:
    def __init__(self, names):
        self.members = [SimpleNamespace(name=n) for n in names]


def test_collect_save_overrides_appends_new_members():
    arch = _FakeArch(["main.xml", "main.xenv"])
    members = {
        "main.xml": b"<old/>",
        "box.x_t": b"XTDATA",
        "meshinggroup1_part.mdl": b"MDL",
    }
    out = pp.collect_save_overrides(
        arch, members, editor_overrides={"main.xml": b"<new/>"})
    assert out["main.xml"] == b"<new/>"
    assert out["box.x_t"] == b"XTDATA"
    assert out["meshinggroup1_part.mdl"] == b"MDL"
    assert "main.xenv" not in out


def test_collect_save_overrides_dirty_existing():
    arch = _FakeArch(["main.xml", "meshinggroup1.gph"])
    members = {
        "main.xml": b"A",
        "meshinggroup1.gph": b"GPH-NEW",
    }
    out = pp.collect_save_overrides(
        arch, members, dirty=["meshinggroup1.gph"])
    assert out["meshinggroup1.gph"] == b"GPH-NEW"
    assert "main.xml" not in out


def test_clone_empty_project_appends_oct_gph_xt():
    members = pp.empty_project_members()
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "empty.pph")
        dst = os.path.join(td, "out.pph")
        with zipfile.ZipFile(src, "w") as zf:
            for name, data in members.items():
                zf.writestr(name, data)
        pphwriter.clone_pph(src, dst, {
            "box.x_t": b"XT",
            "meshinggroup1.oct": b"OCT",
            "meshinggroup1.gph": b"GPH",
        })
        arch = pph_parser.PphArchive.open(dst)
        names = {m.name for m in arch.members}
        assert names >= {
            "main.xml", "main.xenv", "main.prp", "main.js",
            "box.x_t", "meshinggroup1.oct", "meshinggroup1.gph",
        }
        assert arch.read_member("box.x_t") == b"XT"


def test_empty_project_has_movinggroup_slot():
    members = pp.empty_project_members(name="Untitled")
    xml = pphxml.parse_main_xml(members["main.xml"])
    mg = xml.section("parts").find("meshinggroup")
    assert mg is not None
    assert mg.findtext("sgs_name") == "MeshingGroup_1"
    grp = mg.find("movinggroup").find("group")
    assert grp.findtext("name") == "Untitled"
    assert grp.find("part") is None


def test_add_xml_part_registers_under_movinggroup():
    xml = pphxml.parse_main_xml(pp.empty_project_members()["main.xml"])
    pt = pp.add_xml_part(xml, "BoxBody")
    assert pt.findtext("name") == "BoxBody"
    assert pt.findtext("attribute") == "solid"
    assert "BoxBody" in pp.xml_part_names(xml)
    again = pp.add_xml_part(xml, "BoxBody")
    assert again is pt
    names = [p.findtext("name") for p in
             xml.section("parts").find("meshinggroup")
             .find("movinggroup").find("group").findall("part")]
    assert names == ["BoxBody"]


def test_save_empty_plus_xt_and_part_xml():
    members = pp.empty_project_members()
    xml = pphxml.parse_main_xml(members["main.xml"])
    pp.add_xml_part(xml, "Part")
    members["main.xml"] = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        + pphxml.serialize_main_xml(xml.root)
    ).encode("utf-8")
    members["box.x_t"] = b"fake-xt"
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "empty.pph")
        dst = os.path.join(td, "saved.pph")
        with zipfile.ZipFile(src, "w") as zf:
            for name, data in members.items():
                if name in ("box.x_t",):
                    continue
                zf.writestr(name, data)
        arch = pph_parser.PphArchive.open(src)
        overrides = pp.collect_save_overrides(
            arch,
            {**{n: arch.read_member(n) for n in
                ("main.xml", "main.xenv", "main.prp", "main.js")},
             "main.xml": members["main.xml"],
             "box.x_t": members["box.x_t"]},
            dirty=["main.xml"],
        )
        pphwriter.clone_pph(src, dst, overrides)
        saved = pph_parser.PphArchive.open(dst)
        assert "box.x_t" in {m.name for m in saved.members}
        mx = pphxml.parse_main_xml(saved.read_member("main.xml"))
        assert "Part" in pp.xml_part_names(mx)


def test_cad_meshes_to_surface_concat_and_offset():
    t1 = SimpleNamespace(
        points=np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0]]),
        triangles=np.array([[0, 1, 2]]),
    )
    t2 = SimpleNamespace(
        tess=SimpleNamespace(
            points=np.array([[2.0, 0, 0], [3, 0, 0], [2, 1, 0]]),
            triangles=np.array([[0, 1, 2]]),
        ),
    )
    pts, tris = pp.cad_meshes_to_surface([t1, t2])
    assert pts.shape == (6, 3)
    assert tris.tolist() == [[0, 1, 2], [3, 4, 5]]
    assert pp.cad_meshes_to_surface([]) is None


def test_mdl_bytes_from_tess_and_region_append():
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
         [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]],
        dtype=float)
    quads = [
        [0, 3, 2, 1], [4, 5, 6, 7],
        [0, 1, 5, 4], [2, 3, 7, 6],
        [1, 2, 6, 5], [0, 4, 7, 3],
    ]
    faces = []
    for a, b, c, d in quads:
        faces.append([a, b, c])
        faces.append([a, c, d])
    raw = pp.mdl_bytes_from_tess(
        pts, faces, surface_regions=[("@PartSurface_Part", 0)])
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "a.mdl"
        p.write_bytes(raw)
        m = mdl.parse_mdl(str(p))
        assert m.n_faces == 12
        assert "@PartSurface_Part" in [r.name for r in m.surface_regions]
        raw2 = pp.append_surface_region_bytes(raw, "face_inlet")
        p.write_bytes(raw2)
        m2 = mdl.parse_mdl(str(p))
        names2 = [r.name for r in m2.surface_regions]
        assert "face_inlet" in names2
        assert "@PartSurface_Part" in names2


@pytest.mark.skipif(not BOX_MDL.is_file(), reason="box MDL missing")
def test_append_region_on_box_mdl():
    raw = BOX_MDL.read_bytes()
    out = pp.append_surface_region_bytes(raw, "@WaveATestRegion")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "box.mdl"
        p.write_bytes(out)
        m = mdl.parse_mdl(str(p))
    assert "@WaveATestRegion" in [r.name for r in m.surface_regions]


def test_default_part_surface_region():
    assert pp.default_part_surface_region("Part") == "@PartSurface_Part"
    assert pp.default_part_surface_region("@PartSurface_X") == "@PartSurface_X"


def test_set_parts_control_flags():
    xml = pphxml.parse_main_xml(pp.empty_project_members()["main.xml"])
    pc = pp.set_parts_control_flags(
        xml, discontinuous=True, overset=False, wrapping=True)
    assert pc.findtext("Discontinuous") == "true"
    assert pc.findtext("overset") == "false"
    assert pc.findtext("Wrapping") == "true"
    cond = xml.section("conditions").find("parts_control")
    assert cond is pc
