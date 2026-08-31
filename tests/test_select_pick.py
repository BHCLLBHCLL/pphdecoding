#!/usr/bin/env python3
"""Select 拾取模式与菜单接线回归。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class TestSelectPickMode(unittest.TestCase):
    def test_set_pick_mode_values(self):
        # 避免拉起完整 Qt/VTK：只测 View3DTab 方法签名存在于源码
        src = (ROOT / "pph_gui.py").read_text(encoding="utf-8")
        self.assertIn("def set_pick_mode(self, mode: str)", src)
        self.assertIn("self._pick_mode", src)
        self.assertIn("_set_select_pick_mode", src)
        self.assertIn("_select_all_edges", src)
        self.assertIn("_select_all_ridges", src)

    def test_scan_no_longer_lists_wired_picks(self):
        from tools.scan_nyi_menus import _extract_nyi_from_source
        src = (ROOT / "pph_gui.py").read_text(encoding="utf-8")
        items = {label for _, label in _extract_nyi_from_source(src)}
        for label in (
            "Mouse Pick (Part)", "Mouse Pick (Face)",
            "Mouse Pick (Edge)", "Mouse Pick (Vertex)",
            "Select All Edges", "Select All Ridges",
            "Deselect All Edges", "Deselect All Vertices",
            "Deselect All Elements",
            "Rubber Circle (Select)", "Rubber Polygon (Select)",
            "Spread Selected Face to Selected Edge",
        ):
            self.assertNotIn(label, items, label)

    def test_remaining_nyi_keeps_product_boundary_items(self):
        from tools.scan_nyi_menus import _extract_nyi_from_source
        src = (ROOT / "pph_gui.py").read_text(encoding="utf-8")
        items = {label for _, label in _extract_nyi_from_source(src)}
        # P12-F：五项暂缓/重评估菜单已接宿主 typed 路线，不再 NYI
        for label in (
            "Create Actran Files…",
            "Define Facet Part…",
            "Create Non-Facet/Closed Volume Part…",
            "Create 2D Sub-mesh Meshing Unit…",
            "Fix Marked Element Shape",
        ):
            self.assertNotIn(label, items, label)
        self.assertIn("Restore Closed Volume Data…", items)
        self.assertEqual(items, {"Restore Closed Volume Data…"})


if __name__ == "__main__":
    unittest.main()
