#!/usr/bin/env python3
"""Modify Parts 对话框对齐 scFLOWpre。"""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QDialogButtonBox

_APP = QApplication.instance() or QApplication(sys.argv)

from nav_panels import (
    ModifyPartsBody, NavDialogSession, _MODIFY_PARTS_TABS,
)


class TestModifyParts(unittest.TestCase):
    def test_tabs_match_manual(self):
        names = [t[0] for t in _MODIFY_PARTS_TABS]
        self.assertEqual(names[:5], [
            "Data Cleaning", "Edit Solid", "Edit Sheet",
            "Cross Section and Extraction", "Transform",
        ])
        self.assertIn("Turbo machinery", names)

    def test_dialog_layout(self):
        body = ModifyPartsBody()
        self.assertEqual(body.tabs.count(), len(_MODIFY_PARTS_TABS))
        self.assertEqual(
            body.dialog_buttons, QDialogButtonBox.Close)
        self.assertTrue(hasattr(body, "btn_exec"))
        self.assertTrue(hasattr(body, "chk_preview"))
        self.assertTrue(hasattr(body, "chk_overlay"))
        # Data Cleaning 首项
        self.assertEqual(
            body._lists[0].item(0).text(), "Remove Redundant Edges")
        self.assertIn("remove_redundant_edges", body._panels)

    def test_apply_and_execute_session(self):
        body = ModifyPartsBody()
        sess = NavDialogSession()
        ctx = sess.build_ctx()
        # fake parts via groups
        ctx["groups_info"] = {"PartA": {}, "PartB": {}}
        body.load(ctx)
        panel = body._panels["remove_redundant_edges"]
        self.assertGreaterEqual(panel.lst.count(), 2)
        panel.lst.item(0).setSelected(True)
        body.chk_preview.setChecked(True)
        self.assertTrue(body.apply(ctx))
        data = ctx["session"]["modify_parts"]
        self.assertEqual(data["op"], "remove_redundant_edges")
        self.assertTrue(data["preview"])
        # offscreen 下 QMessageBox 可能崩溃，只验证会话写入逻辑
        from unittest import mock
        with mock.patch("nav_panels.QMessageBox.information"):
            body._on_execute()
        self.assertTrue(
            ctx["session"]["modify_parts"].get("execute_requested"))

    def test_priority_up_down(self):
        body = ModifyPartsBody()
        panel = body._panels["remove_solid_overlap"]
        panel.set_parts(["A", "B", "C"])
        panel.lst.setCurrentRow(1)
        panel._move_sel(-1)
        self.assertEqual(panel.lst.item(0).text(), "B")
        self.assertEqual(panel.selected_parts(), ["B", "A", "C"])


if __name__ == "__main__":
    unittest.main()
