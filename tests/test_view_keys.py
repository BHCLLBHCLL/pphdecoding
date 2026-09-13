#!/usr/bin/env python3
"""Draw Window 视图快捷键：X/Y/Z(/Shift) + F Fit（对齐 cabdecoding）。"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt5.QtWidgets import QApplication, QWidget  # noqa: E402

import pph_gui  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)


class TestViewKeys(unittest.TestCase):
    def test_plane_view_camera(self):
        cases = [
            ("yz", False, (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            ("yz", True, (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            ("xz", False, (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            ("xz", True, (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
            ("xy", False, (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
            ("xy", True, (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
        ]
        for plane, negative, pos, up in cases:
            self.assertEqual(
                pph_gui.plane_view_camera(plane, negative=negative),
                (pos, up))

    def test_view_key_action(self):
        self.assertEqual(
            pph_gui.view_key_action("x"), ("plane", "yz", False))
        self.assertEqual(
            pph_gui.view_key_action("X", shift=True), ("plane", "yz", True))
        self.assertEqual(
            pph_gui.view_key_action("y"), ("plane", "xz", False))
        self.assertEqual(
            pph_gui.view_key_action("z"), ("plane", "xy", False))
        self.assertEqual(pph_gui.view_key_action("f"), ("fit",))
        self.assertIsNone(pph_gui.view_key_action("f", shift=True))
        self.assertIsNone(pph_gui.view_key_action("a"))

    def test_draw_shortcuts_installed(self):
        win = pph_gui.PphViewer()
        try:
            # 确保菜单动作已创建；用占位 widget 验证绑定
            if win.view3d.vtk_widget is None:
                win.view3d.vtk_widget = QWidget()
            win._install_draw_view_shortcuts()
            seqs = {
                a.shortcut().toString()
                for a in win.view3d.vtk_widget.actions()
                if not a.shortcut().isEmpty()
            }
            self.assertIn("X", seqs)
            self.assertIn("Y", seqs)
            self.assertIn("Z", seqs)
            self.assertIn("F", seqs)
            self.assertTrue(
                any("Shift" in s and s.endswith("X") for s in seqs))
            self.assertEqual(win._act_xy.shortcut().toString(), "Z")
            self.assertEqual(win._act_xz.shortcut().toString(), "Y")
            self.assertEqual(win._act_yz.shortcut().toString(), "X")
        finally:
            win.close()


if __name__ == "__main__":
    unittest.main()
