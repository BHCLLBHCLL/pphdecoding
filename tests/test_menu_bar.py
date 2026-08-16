#!/usr/bin/env python3
"""菜单栏对齐 scFLOWpre Menu Guide。"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QMessageBox

_APP = QApplication.instance() or QApplication(sys.argv)

from pph_gui import PphViewer


def _top_menus(win: PphViewer) -> list[str]:
    out = []
    for act in win.menuBar().actions():
        out.append(act.text().replace("&", ""))
    return out


def _menu_texts(win: PphViewer, name: str) -> list[str]:
    for act in win.menuBar().actions():
        if name in act.text().replace("&", ""):
            m = act.menu()
            texts = []
            for a in m.actions():
                if a.isSeparator():
                    texts.append("---")
                elif a.menu() is not None:
                    texts.append(a.text() + ">")
                else:
                    texts.append(a.text())
            return texts
    return []


class TestMenuBar(unittest.TestCase):
    def test_top_level_order(self):
        win = PphViewer()
        tops = _top_menus(win)
        self.assertEqual(
            tops,
            ["File(F)", "Edit(E)", "Select(S)", "View(V)",
             "Condition(C)", "Execute(X)", "Option(O)", "Help(H)"])

    def test_file_items(self):
        texts = _menu_texts(PphViewer(), "File")
        for need in (
            "New Project…", "Open…", "Save", "Save As…",
            "Open Project Folder", "Import…", "Export…",
            "Create Actran Files…", "Start Recording VBScript",
            "Stop Recording VBScript", "Execute VBScript…", "Exit",
        ):
            self.assertIn(need, texts)

    def test_edit_has_ridge_submenu(self):
        texts = _menu_texts(PphViewer(), "Edit")
        self.assertIn("Create Parts…", texts)
        self.assertIn("Modify Parts…", texts)
        self.assertIn("Register Region…", texts)
        self.assertIn("Ridge>", texts)

    def test_select_mouse_picks(self):
        texts = _menu_texts(PphViewer(), "Select")
        self.assertIn("Mouse Pick (Part)", texts)
        self.assertIn("Mouse Pick (Face)", texts)
        self.assertIn("Deselect All Faces", texts)
        self.assertIn("Element Quality Check…", texts)

    def test_select_by_list_file_wired(self):
        """P4-4：Select Elements by List File 已接线（不再是 NYI 灰显）。"""
        win = PphViewer()
        act = win._menu_acts["sel_by_list"]
        self.assertTrue(act.isEnabled())
        self.assertTrue(act.text().startswith("Select Elements by List File"))

    def test_view_rubber_submenus(self):
        texts = _menu_texts(PphViewer(), "View")
        self.assertIn("Part", texts)
        self.assertIn("Octree", texts)
        self.assertIn("Mesh", texts)
        self.assertIn("Rubber Box>", texts)
        self.assertIn("Cross Section View of Mesh", texts)

    def test_condition_and_execute(self):
        win = PphViewer()
        c = _menu_texts(win, "Condition")
        self.assertIn("Parts Control…", c)
        self.assertIn("Conditions…", c)
        self.assertIn("Mesher/Faceter Setting…", c)
        self.assertIn("Octree Parameter…", c)
        x = _menu_texts(win, "Execute")
        self.assertIn("Prepare Parts", x)
        self.assertIn("Build Analysis Model", x)
        self.assertIn("Generate Octree for Meshing", x)
        self.assertIn("Generate Mesh", x)
        self.assertIn("Execute Solver", x)

    def test_help_items(self):
        texts = _menu_texts(PphViewer(), "Help")
        self.assertEqual(
            [t for t in texts if t != "---"],
            ["Tutorial", "Reference", "About scFLOWpre"])

    def test_bam_locks_create_parts(self):
        win = PphViewer()
        self.assertTrue(win._prepare_parts_mode)
        self.assertTrue(win._menu_acts["edit_create_parts"].isEnabled())
        with patch.object(win, "_build_am_confirm_choice", return_value="ok"):
            win._confirm_build_analysis_model()
        self.assertFalse(win._prepare_parts_mode)
        self.assertFalse(win._menu_acts["edit_create_parts"].isEnabled())
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Ok):
            win._execute_prepare_parts()
        self.assertTrue(win._prepare_parts_mode)
        self.assertTrue(win._menu_acts["edit_create_parts"].isEnabled())


if __name__ == "__main__":
    unittest.main()
