#!/usr/bin/env python3
"""Create Non-Solid Part 对话框对齐 scFLOWpre。"""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QDialog, QDialogButtonBox

_APP = QApplication.instance() or QApplication(sys.argv)

import pphxml
from nav_panels import (
    NonSolidBody, NavDialogSession, _CoordSpecifiedPartDialog,
)


def _mini_xml() -> pphxml.MainXml:
    root = ET.fromstring("""<?xml version="1.0"?>
    <project>
      <parts>
        <part><name>Cuboid</name></part>
        <part><name>Cuboid[2]</name></part>
        <face_region_derived_sheets>
          <sheet><name>Sheet_open</name></sheet>
        </face_region_derived_sheets>
      </parts>
      <regions>
        <face><region><name>open</name></region></face>
      </regions>
    </project>""")
    return pphxml.MainXml(root)


class TestNonSolid(unittest.TestCase):
    def test_tabs(self):
        body = NonSolidBody()
        self.assertEqual(body.tabs.count(), 3)
        self.assertEqual(
            [body.tabs.tabText(i) for i in range(3)],
            ["Group Part", "Coordinates Specified Part",
             "Surface Region-Derived Sheet"])
        self.assertEqual(body.dialog_buttons, QDialogButtonBox.Close)

    def test_register_group(self):
        body = NonSolidBody()
        ctx = NavDialogSession().build_ctx(xml=_mini_xml())
        body.load(ctx)
        self.assertGreaterEqual(body._group["sel"].count(), 2)
        body._group["ed_name"].setText("G1")
        body._group["sel"].item(0).setSelected(True)
        body._group["sel"].item(1).setSelected(True)
        body._register_group()
        self.assertEqual(body._group["tree"].topLevelItemCount(), 1)
        self.assertEqual(ctx["session"]["non_solid"]["group_parts"][0]["name"],
                         "G1")

    def test_coord_dialog_and_session(self):
        body = NonSolidBody()
        ctx = NavDialogSession().build_ctx(xml=_mini_xml())
        body.load(ctx)

        def _fake_exec(self):
            self.ed_name.setText("CP1")
            self.sp_x.setValue(1)
            self.sp_y.setValue(2)
            self.sp_z.setValue(3)
            return QDialog.Accepted

        with mock.patch.object(_CoordSpecifiedPartDialog, "exec_", _fake_exec):
            body._new_coord_part()
        self.assertEqual(body._coord["tree"].topLevelItemCount(), 1)
        self.assertEqual(
            ctx["session"]["non_solid"]["coord_parts"][0]["name"], "CP1")

    def test_sheet_from_xml_and_register(self):
        body = NonSolidBody()
        ctx = NavDialogSession().build_ctx(xml=_mini_xml())
        body.load(ctx)
        self.assertGreaterEqual(body._sheet["tree"].topLevelItemCount(), 1)
        self.assertIn("open", [
            body._sheet["lst_reg"].item(i).text()
            for i in range(body._sheet["lst_reg"].count())])
        body._sheet["cb_target"].setCurrentIndex(0)
        body._sheet["ed_name"].setText("MySheet")
        body._register_sheet()
        names = [body._sheet["tree"].topLevelItem(i).text(0)
                 for i in range(body._sheet["tree"].topLevelItemCount())]
        self.assertIn("MySheet", names)

    def test_coord_creation_type_stack(self):
        body = NonSolidBody()
        body._coord["cb_type"].setCurrentIndex(2)
        self.assertEqual(body._coord["stack"].currentIndex(), 2)


if __name__ == "__main__":
    unittest.main()
