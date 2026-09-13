#!/usr/bin/env python3
"""Create Parts 对话框对齐 scFLOWpre。"""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QDialogButtonBox

_APP = QApplication.instance() or QApplication(sys.argv)

from nav_panels import CreatePartsBody, NavDialogSession


class TestCreateParts(unittest.TestCase):
    def test_tabs_and_buttons(self):
        body = CreatePartsBody()
        self.assertEqual(body.tabs.count(), 4)
        self.assertEqual(
            [body.tabs.tabText(i) for i in range(4)],
            ["Cuboid", "Cylinder", "Sphere", "Rectangle"])
        self.assertEqual(
            body.dialog_buttons,
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.assertTrue(hasattr(body, "btn_preview"))
        self.assertIn("fluid", body.chk_fluid.text().lower())

    def test_cuboid_extend_min_max(self):
        body = CreatePartsBody()
        d = body._shapes["Cuboid"]
        self.assertFalse(d["min_side"]["x"].isEnabled())
        d["ext"].setChecked(True)
        self.assertTrue(d["min_side"]["x"].isEnabled())
        self.assertTrue(d["max_side"]["z"].isEnabled())

    def test_rectangle_disables_fluid_and_perp_size(self):
        body = CreatePartsBody()
        body.chk_fluid.setChecked(True)
        body.tabs.setCurrentIndex(3)  # Rectangle
        self.assertFalse(body.chk_fluid.isEnabled())
        self.assertFalse(body.chk_fluid.isChecked())
        d = body._shapes["Rectangle"]
        d["axis"].setCurrentText("Y axis")
        self.assertTrue(d["size"]["x"].isEnabled())
        self.assertFalse(d["size"]["y"].isEnabled())
        self.assertTrue(d["size"]["z"].isEnabled())

    def test_apply_session(self):
        body = CreatePartsBody()
        sess = NavDialogSession()
        ctx = sess.build_ctx()
        body.load(ctx)
        d = body._shapes["Cuboid"]
        d["name"].setText("BoxA")
        d["pos"]["x"].setValue(1.0)
        d["size"]["y"].setValue(2.0)
        d["ext"].setChecked(True)
        d["min_side"]["x"].setValue(0.1)
        d["max_side"]["z"].setValue(0.2)
        body.chk_fluid.setChecked(True)
        self.assertTrue(body.apply(ctx))
        data = ctx["session"]["create_parts"]
        self.assertEqual(data["shape"], "Cuboid")
        self.assertEqual(data["name"], "BoxA")
        self.assertTrue(data["fluid"])
        self.assertEqual(data["position"][0], 1.0)
        self.assertEqual(data["size"][1], 2.0)
        self.assertEqual(data["min_side"][0], 0.1)
        self.assertEqual(data["max_side"][2], 0.2)

    def test_calc_size_from_bounds(self):
        body = CreatePartsBody()
        body._ctx = {
            "groups_info": {
                "g": {"part": type("P", (), {
                    "xyz": __import__("numpy").array([
                        [0.0, 0.0, 0.0],
                        [2.0, 4.0, 6.0],
                    ])
                })()},
            },
        }
        body._calc_size("Cuboid")
        d = body._shapes["Cuboid"]
        self.assertEqual(d["pos"]["x"].value(), 0.0)
        self.assertEqual(d["size"]["x"].value(), 2.0)
        self.assertEqual(d["size"]["y"].value(), 4.0)
        self.assertEqual(d["size"]["z"].value(), 6.0)


if __name__ == "__main__":
    unittest.main()
