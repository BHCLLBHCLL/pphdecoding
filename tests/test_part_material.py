#!/usr/bin/env python3
"""Part Material / Material 对话框对齐 scFLOWpre。"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QDialogButtonBox

_APP = QApplication.instance() or QApplication(sys.argv)

import pphxml
from nav_panels import PartMaterialBody, NavDialogSession, _ui_attribute_from_property


def _mini_xml() -> pphxml.MainXml:
    root = ET.fromstring("""<?xml version="1.0"?>
    <scFLOWpre>
      <parts>
        <meshinggroup>
          <movinggroup>
            <part>
              <name>Solid1</name>
              <attribute>solid</attribute>
              <property>air(incompressible/20C)</property>
            </part>
            <part>
              <name>Solid2</name>
              <attribute>solid</attribute>
              <property>@Obstacle</property>
            </part>
          </movinggroup>
        </meshinggroup>
        <face_region_derived_sheets>
          <part>
            <name>Sheet1</name>
            <sheettype>heat_conduction_panel</sheettype>
            <property>iron(Fe)(300K)</property>
            <thickness_val>
              <const_value>0.001</const_value>
              <unit>m</unit>
            </thickness_val>
          </part>
        </face_region_derived_sheets>
      </parts>
    </scFLOWpre>""")
    return pphxml.MainXml(root)


def _mini_prp() -> pphxml.PrpDatabase:
    root = ET.fromstring("""<?xml version="1.0"?>
    <property version="1">
      <group>
        <key>gas(incompressible)</key>
        <entry>
          <key>air(incompressible/20C)</key>
          <name>air</name>
          <type>fluid</type>
        </entry>
      </group>
      <group>
        <key>pure_metal</key>
        <entry>
          <key>iron(Fe)(300K)</key>
          <name>iron</name>
          <type>solid</type>
        </entry>
        <entry>
          <key>copper(Cu)(300K)</key>
          <name>copper</name>
          <type>solid</type>
        </entry>
      </group>
    </property>""")
    return pphxml.PrpDatabase(
        version=root.get("version", ""),
        groups=root.findall("group"),
    )


class TestPartMaterial(unittest.TestCase):
    def test_dialog_layout(self):
        body = PartMaterialBody()
        self.assertEqual(body.title, "Material")
        self.assertEqual(body.dialog_buttons, QDialogButtonBox.Ok)
        self.assertEqual(body.tabs.count(), 2)
        self.assertEqual(
            [body.tabs.tabText(i) for i in range(2)],
            ["Part", "Sheet Part"])
        self.assertTrue(hasattr(body, "btn_options"))
        headers = [body._part_tab["tree"].headerItem().text(i)
                   for i in range(4)]
        self.assertEqual(
            headers, ["#", "Part Name", "Attribute", "Material"])
        sh = [body._sheet_tab["tree"].headerItem().text(i)
              for i in range(5)]
        self.assertEqual(
            sh, ["#", "Part Name", "Attribute", "Thickness", "Material"])

    def test_load_and_apply_material(self):
        body = PartMaterialBody()
        sess = NavDialogSession()
        ctx = sess.build_ctx(xml=_mini_xml(), prp=_mini_prp())
        body.load(ctx)
        self.assertEqual(body._part_tab["tree"].topLevelItemCount(), 2)
        self.assertEqual(body._sheet_tab["tree"].topLevelItemCount(), 1)
        # Solid2 is Obstacle
        row1 = body._part_tab["tree"].topLevelItem(1)
        # sorting may reorder — find by name
        names = {}
        for i in range(body._part_tab["tree"].topLevelItemCount()):
            it = body._part_tab["tree"].topLevelItem(i)
            names[it.text(1)] = it
        self.assertEqual(names["Solid2"].text(2), "Obstacle")
        self.assertEqual(names["Solid1"].text(2), "Fluid")

        # Apply copper (solid) to Solid2
        body._set_part_attr_radios("Solid")
        body._rebuild_mat_tree("part")
        # expand & select copper
        mat_tree = body._part_tab["mat_tree"]
        self.assertGreater(mat_tree.topLevelItemCount(), 0)
        g = mat_tree.topLevelItem(0)
        g.setExpanded(True)
        copper = None
        for i in range(g.childCount()):
            if "copper" in g.child(i).text(0):
                copper = g.child(i)
                break
        self.assertIsNotNone(copper)
        mat_tree.setCurrentItem(copper)
        names["Solid2"].setSelected(True)
        body._apply_selection("part")
        self.assertEqual(names["Solid2"].text(2), "Solid")
        self.assertIn("copper", names["Solid2"].text(3))
        # xml writeback
        xml = ctx["xml"]
        props = {
            pt.findtext("name"): pt.findtext("property")
            for pt in xml.section("parts").iter("part")
            if pt.findtext("name")
        }
        self.assertEqual(props["Solid2"], "copper(Cu)(300K)")
        self.assertTrue(ctx.get("xml_dirty"))
        self.assertTrue(body.apply(ctx))
        self.assertIn("parts", ctx["session"]["part_material"])

    def test_ui_attribute_helper(self):
        prp = _mini_prp()
        self.assertEqual(
            _ui_attribute_from_property("@Obstacle", prp), "Obstacle")
        self.assertEqual(
            _ui_attribute_from_property("air(incompressible/20C)", prp),
            "Fluid")
        self.assertEqual(
            _ui_attribute_from_property("iron(Fe)(300K)", prp), "Solid")

    def test_sample_box_prp_groups(self):
        prp_path = Path(__file__).resolve().parent / "box" / "main.prp"
        if not prp_path.is_file():
            self.skipTest("box/main.prp missing")
        prp = pphxml.parse_prp(prp_path.read_bytes())
        body = PartMaterialBody()
        ctx = NavDialogSession().build_ctx(prp=prp, xml=_mini_xml())
        body.load(ctx)
        body._set_part_attr_radios("Solid")
        body._rebuild_mat_tree("part")
        names = [
            body._part_tab["mat_tree"].topLevelItem(i).text(0)
            for i in range(body._part_tab["mat_tree"].topLevelItemCount())
        ]
        self.assertIn("pure_metal", names)
        self.assertNotIn("gas(incompressible)", names)


if __name__ == "__main__":
    unittest.main()
