#!/usr/bin/env python3
"""Register Region 对话框对齐 scFLOWpre。"""

from __future__ import annotations

import os
import sys
import unittest
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QDialogButtonBox

_APP = QApplication.instance() or QApplication(sys.argv)

import pphxml
from nav_panels import RegisterRegionBody, NavDialogSession


def _mini_xml() -> pphxml.MainXml:
    root = ET.fromstring("""<?xml version="1.0"?>
    <project>
      <parts><part><name>Cuboid</name></part>
            <part><name>Cuboid[2]</name></part></parts>
      <regions>
        <fluid><region>
          <name>FluidRegion</name>
          <property>air</property>
          <spart>Cuboid</spart>
        </region></fluid>
        <volume/>
        <face>
          <region>
            <name>open</name>
            <face_region_type>faces</face_region_type>
            <sface_num><num index="0">6</num></sface_num>
          </region>
        </face>
        <numerical/>
        <special_face/>
      </regions>
    </project>""")
    return pphxml.MainXml(root)


class TestRegisterRegion(unittest.TestCase):
    def test_tabs(self):
        body = RegisterRegionBody()
        self.assertEqual(body.tabs.count(), 5)
        self.assertEqual(
            [body.tabs.tabText(i) for i in range(5)],
            ["Surface Region", "Part Interface Region", "Volume Region",
             "Fluid Region", "Reference Point"])
        self.assertEqual(body.dialog_buttons, QDialogButtonBox.Close)

    def test_load_face_and_fluid(self):
        body = RegisterRegionBody()
        ctx = NavDialogSession().build_ctx(xml=_mini_xml())
        body.load(ctx)
        self.assertEqual(body._surf["tree"].topLevelItemCount(), 1)
        self.assertEqual(body._surf["tree"].topLevelItem(0).text(0), "open")
        self.assertEqual(body._surf["tree"].topLevelItem(0).text(2), "6")
        self.assertEqual(body._fluid["tree"].topLevelItemCount(), 1)
        self.assertEqual(
            body._fluid["tree"].topLevelItem(0).text(0), "FluidRegion")
        self.assertGreaterEqual(body._vol["lst_parts"].count(), 2)

    def test_register_surface(self):
        body = RegisterRegionBody()
        xml = _mini_xml()
        ctx = NavDialogSession().build_ctx(xml=xml)
        body.load(ctx)
        body._surf["ed_name"].setText("face_new")
        body._register_surface()
        self.assertTrue(ctx.get("xml_dirty"))
        names = [r.findtext("name") for r in xml.section("regions")
                 .find("face").findall("region")]
        self.assertIn("face_new", names)
        self.assertEqual(body._surf["tree"].topLevelItemCount(), 2)
        pending = ctx["session"].get("mdl_regions_pending") or []
        self.assertTrue(pending)
        self.assertEqual(pending[-1]["name"], "face_new")

    def test_register_refpoint(self):
        body = RegisterRegionBody()
        ctx = NavDialogSession().build_ctx()
        body.load(ctx)
        body._ref["ed_name"].setText("P1")
        body._ref["sp_x"].setValue(1)
        body._ref["sp_y"].setValue(2)
        body._ref["sp_z"].setValue(3)
        body._register_refpoint()
        pts = ctx["session"]["ref_points"]
        self.assertEqual(len(pts), 1)
        self.assertEqual(pts[0]["name"], "P1")
        self.assertEqual(pts[0]["xyz"], (1.0, 2.0, 3.0))

    def test_surface_target_stack(self):
        body = RegisterRegionBody()
        body._surf["cb_target"].setCurrentIndex(5)  # cross section
        self.assertEqual(body._surf["stack"].currentIndex(), 5)
        body._surf["cb_target"].setCurrentIndex(0)
        self.assertEqual(body._surf["stack"].currentIndex(), 0)


if __name__ == "__main__":
    unittest.main()
