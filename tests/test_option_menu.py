#!/usr/bin/env python3
"""Option(O) 菜单与对话框对齐 scFLOWpre。"""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QDialog

_APP = QApplication.instance() or QApplication(sys.argv)

import option_dialogs
from nav_panels import NavDialogSession
from pph_gui import NavigationWindow, PphViewer


class TestOptionDialogs(unittest.TestCase):
    def test_mouse_operation_dialog(self):
        dlg = option_dialogs.ChangeMouseOperationDialog(
            "CRADLE 3-Button Mode")
        self.assertEqual(dlg.windowTitle(), "Change Mouse Operation")
        self.assertGreaterEqual(dlg.cb_type.count(), 4)
        self.assertIn("Middle Button", dlg.lab_map.text())

    def test_unit_conversion_temp(self):
        dlg = option_dialogs.UnitConversionDialog()
        dlg.cb_cat.setCurrentText("Temperature")
        dlg.sp_in.setValue(25)
        dlg.cb_from.setCurrentText("C")
        dlg.cb_to.setCurrentText("F")
        dlg._recalc()
        self.assertAlmostEqual(float(dlg.ed_out.text()), 77.0, places=5)

    def test_unit_conversion_rpm(self):
        dlg = option_dialogs.UnitConversionDialog()
        dlg.sp_rpm.setValue(60)
        dlg.sp_deg.setValue(360)
        dlg._recalc_rpm()
        self.assertAlmostEqual(float(dlg.ed_sec.text()), 1.0, places=6)

    def test_environment_settings_navigation(self):
        ctx = NavDialogSession().build_ctx()
        dlg = option_dialogs.EnvironmentSettingsDialog(ctx)
        self.assertEqual(dlg.windowTitle(), "Environment Settings")
        self.assertTrue(dlg.chk_show_bam.isChecked())
        dlg.chk_always_wiz.setChecked(True)
        dlg.chk_enable_wrap.setChecked(True)
        self.assertTrue(dlg.apply(ctx))
        opt = ctx["session"]["option_nav"]
        self.assertTrue(opt["always_show_wizard"])
        self.assertTrue(opt["enable_wrapping"])

    def test_nav_hide_mesher(self):
        nav = NavigationWindow()
        keys = [
            nav.tree.topLevelItem(i).data(0, Qt.UserRole)
            for i in range(nav.tree.topLevelItemCount())
            if nav.tree.topLevelItem(i).data(0, Qt.UserRole)
        ]
        self.assertIn("mesher_faceter", keys)
        nav.set_show_mesher_item(False)
        keys = [
            nav.tree.topLevelItem(i).data(0, Qt.UserRole)
            for i in range(nav.tree.topLevelItemCount())
            if nav.tree.topLevelItem(i).data(0, Qt.UserRole)
        ]
        self.assertNotIn("mesher_faceter", keys)


class TestOptionMenuWiring(unittest.TestCase):
    def test_menu_structure(self):
        win = PphViewer()
        texts = []
        for act in win.menuBar().actions():
            if "Option" in act.text().replace("&", ""):
                m = act.menu()
                for a in m.actions():
                    if a.isSeparator():
                        texts.append("---")
                    elif a.menu() is not None:
                        texts.append(a.text() + ">")
                    else:
                        texts.append(a.text())
                break
        self.assertIn("1-Button Mode", texts)
        self.assertIn("2-Button Mode", texts)
        self.assertIn("3-Button Mode (CTRL)", texts)
        self.assertIn("3-Button Mode", texts)
        self.assertIn("Operation…", texts)
        self.assertIn("Unit Conversion…", texts)
        self.assertIn("Settings…", texts)
        self.assertIn("Change to Viewer Mode", texts)
        self.assertIn("Change Language>", texts)

    def test_mouse_mode_session(self):
        win = PphViewer()
        win._set_mouse_mode("1btn")
        self.assertEqual(
            win._nav_dialogs.session["option_mouse"]["mode"], "1btn")

    def test_viewer_mode_restricts_save_and_bam(self):
        win = PphViewer()
        win._toggle_viewer_mode(True)
        self.assertFalse(win._menu_acts["file_save"].isEnabled())
        self.assertFalse(win._menu_acts["exec_bam"].isEnabled())
        self.assertFalse(win._menu_acts["edit_create_parts"].isEnabled())
        win._toggle_viewer_mode(False)
        self.assertTrue(win._menu_acts["file_save"].isEnabled())
        self.assertTrue(win._menu_acts["exec_bam"].isEnabled())
        self.assertTrue(win._menu_acts["edit_create_parts"].isEnabled())


if __name__ == "__main__":
    unittest.main()
