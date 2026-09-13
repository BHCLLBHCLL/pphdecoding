#!/usr/bin/env python3
"""Import Part File 对话框对齐 scFLOWpre。"""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QDialogButtonBox

_APP = QApplication.instance() or QApplication(sys.argv)

import pphxml
from nav_panels import ImportPartBody, NavDialogSession, NavParamDialog


class TestImportPart(unittest.TestCase):
    def test_file_types_include_xt_and_categories(self):
        body = ImportPartBody()
        texts = [body.cb_type.itemText(i) for i in range(body.cb_type.count())]
        self.assertTrue(any("XT Files" in t for t in texts))
        self.assertTrue(any("Part data (CAD)" in t for t in texts))
        self.assertTrue(any("GPH Files" in t for t in texts))
        self.assertTrue(any("PRP Files" in t for t in texts))
        # 默认 XT
        self.assertIn("XT", body.cb_type.currentText())

    def test_dialog_buttons_open_cancel(self):
        self.assertEqual(
            ImportPartBody.dialog_buttons,
            QDialogButtonBox.Open | QDialogButtonBox.Cancel)
        sess = NavDialogSession()
        ctx = sess.build_ctx()
        dlg = NavParamDialog("import_part", ImportPartBody(), ctx)
        bbox = dlg.findChild(QDialogButtonBox)
        self.assertIsNotNone(bbox.button(QDialogButtonBox.Open))
        self.assertIsNotNone(bbox.button(QDialogButtonBox.Cancel))
        self.assertIsNone(bbox.button(QDialogButtonBox.Apply))

    def test_apply_writes_cad_xenv(self):
        xenv = pphxml.XenvSettings()
        pphxml.set_xenv_value(xenv, "CAD", "CAD_Import_TYPE", "0")
        pphxml.set_xenv_value(xenv, "CAD", "CAD_LIBRARY", "1")
        pphxml.set_xenv_value(xenv, "CAD", "USE_STEP_ASSISTANT", "true")
        pphxml.set_xenv_value(xenv, "CAD", "DELETE_COLORED_CAD_FACE", "true")
        pphxml.set_xenv_value(xenv, "CAD", "IGNORE_CAD_FACE_NAME", "true")
        pphxml.set_xenv_value(xenv, "CAD", "SELECT_DKCT_VERSION", "false")
        pphxml.set_xenv_value(xenv, "CAD", "DKCT_VERSION", "2025")
        pphxml.set_xenv_value(xenv, "CAD", "USE_ANCESTRAL_NAME", "false")
        pphxml.set_xenv_value(xenv, "CAD", "SEPARATE_DUPLICATE_SOLID", "false")

        body = ImportPartBody()
        sess = NavDialogSession()
        ctx = sess.build_ctx(xenv=xenv)
        body.load(ctx)
        self.assertTrue(body.rb_solid.isChecked())
        self.assertTrue(body.rb_lib_dk.isChecked())
        self.assertFalse(body.chk_use_lib_step.isChecked())

        body.rb_facet.setChecked(True)
        body.chk_use_lib_step.setChecked(True)
        body.chk_dk_ver.setChecked(True)
        body.sp_dk_ver.setValue(2021)
        body.ed_path.setText(r"D:\cad\demo.x_t")
        self.assertTrue(body.apply(ctx))

        self.assertEqual(xenv.get("CAD", "CAD_Import_TYPE"), "1")
        self.assertEqual(xenv.get("CAD", "USE_STEP_ASSISTANT"), "false")
        self.assertEqual(xenv.get("CAD", "SELECT_DKCT_VERSION"), "true")
        self.assertEqual(xenv.get("CAD", "DKCT_VERSION"), "2021")
        self.assertTrue(ctx["xenv_dirty"])
        ip = ctx["session"]["import_part"]
        self.assertEqual(ip["path"], r"D:\cad\demo.x_t")
        self.assertTrue(ip["open_requested"])


if __name__ == "__main__":
    unittest.main()
