#!/usr/bin/env python3
"""Build Analysis Model：导航可见性 + 确认框 + Detailed Wizard。"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QDialog

_APP = QApplication.instance() or QApplication(sys.argv)

import pphxml
from nav_panels import (
    AnalysisModelWizardBody, BODY_CLASSES, DIALOG_KEYS, NavParamDialog,
)
from pph_gui import NavigationWindow, PphViewer


class TestBuildAmNavigation(unittest.TestCase):
    def test_dialog_registration(self):
        self.assertNotIn("build_am", DIALOG_KEYS)
        self.assertNotIn("build_am", BODY_CLASSES)
        self.assertIn("build_am_detailed", DIALOG_KEYS)
        self.assertIs(BODY_CLASSES["build_am_detailed"], AnalysisModelWizardBody)

    def test_nav_hidden_for_voxel(self):
        nav = NavigationWindow()
        keys = [
            nav.tree.topLevelItem(i).data(0, Qt.UserRole)
            for i in range(nav.tree.topLevelItemCount())
            if nav.tree.topLevelItem(i).data(0, Qt.UserRole)
        ]
        self.assertIn("build_am", keys)

        nav.set_polyhedral_mesher(False)
        keys = [
            nav.tree.topLevelItem(i).data(0, Qt.UserRole)
            for i in range(nav.tree.topLevelItemCount())
            if nav.tree.topLevelItem(i).data(0, Qt.UserRole)
        ]
        self.assertNotIn("build_am", keys)
        self.assertIn("mesher_faceter", keys)

        nav.set_polyhedral_mesher(True)
        keys = [
            nav.tree.topLevelItem(i).data(0, Qt.UserRole)
            for i in range(nav.tree.topLevelItemCount())
            if nav.tree.topLevelItem(i).data(0, Qt.UserRole)
        ]
        self.assertIn("build_am", keys)

    def test_sync_from_xenv_mesher(self):
        win = PphViewer()
        xenv = pphxml.XenvSettings()
        pphxml.set_xenv_value(xenv, "MESH", "MESHER", "1")
        win._xenv = xenv
        win._sync_nav_mesher()
        self.assertFalse(win.navigation._polyhedral_mesher)

        pphxml.set_xenv_value(xenv, "MESH", "MESHER", "0")
        win._nav_dialogs.session.pop("mesher_faceter", None)
        win._sync_nav_mesher()
        self.assertTrue(win.navigation._polyhedral_mesher)

    def test_navigate_build_am_calls_show(self):
        """build_am 不在 PANEL_CLASSES，_on_navigate 须单独处理。"""
        win = PphViewer()
        win.arch = object()
        win.navigation.set_polyhedral_mesher(True)
        with patch.object(win, "_show_condition") as sc:
            win._on_navigate("build_am")
            sc.assert_called_once_with("build_am")

    def test_confirm_ok(self):
        win = PphViewer()
        with patch.object(win, "_build_am_confirm_choice", return_value="ok"):
            win._confirm_build_analysis_model()
        self.assertTrue(
            win._nav_dialogs.session.get("build_am", {}).get("build_requested"))

    def test_confirm_cancel(self):
        win = PphViewer()
        win._nav_dialogs.session["build_am"] = {}
        with patch.object(win, "_build_am_confirm_choice", return_value="cancel"):
            win._confirm_build_analysis_model()
        self.assertFalse(
            win._nav_dialogs.session.get("build_am", {}).get("build_requested"))

    def test_confirm_detailed_opens_wizard(self):
        win = PphViewer()
        win.arch = object()  # 通过“已打开工程”检查
        win.navigation.set_polyhedral_mesher(True)
        opened = []

        def _fake_open(key, ctx, parent=None):
            opened.append(key)
            body = AnalysisModelWizardBody()
            dlg = NavParamDialog(key, body, ctx, parent)
            # 立即关掉，避免阻塞
            dlg.show()
            dlg.reject()
            return dlg

        with patch.object(win, "_build_am_confirm_choice", return_value="detailed"):
            with patch.object(win._nav_dialogs, "open", side_effect=_fake_open):
                with patch.object(QDialog, "exec_", return_value=QDialog.Rejected):
                    win._confirm_build_analysis_model()
        self.assertEqual(opened, ["build_am_detailed"])

    def test_wizard_body_layout(self):
        body = AnalysisModelWizardBody()
        self.assertEqual(body.title, "Analysis Model Wizard")
        self.assertEqual(body.dialog_buttons, 0)
        self.assertEqual(body.nav.count(), 8)
        self.assertTrue(hasattr(body, "chk_use_af"))


if __name__ == "__main__":
    unittest.main()
