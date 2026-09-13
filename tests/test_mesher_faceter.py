#!/usr/bin/env python3
"""Mesher/Faceter Setting 对话框对齐 scFLOWpre。"""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QDialogButtonBox

_APP = QApplication.instance() or QApplication(sys.argv)

import pphxml
from nav_panels import MesherFaceterBody, NavDialogSession


class TestMesherFaceter(unittest.TestCase):
    def test_layout(self):
        body = MesherFaceterBody()
        self.assertEqual(
            body.dialog_buttons,
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.assertEqual(
            [body.tree.headerItem().text(i) for i in range(3)],
            ["Parameter", "Value", "Unit"])
        self.assertIn("mesher", body._editors)
        self.assertFalse(body.cb_unit.isEnabled())

    def test_visibility_poly_wizard_af(self):
        from nav_panels import _set_combo_data
        body = MesherFaceterBody()
        _set_combo_data(body.cb_mesher, "0")
        _set_combo_data(body.cb_surf, "0")
        _set_combo_data(body.cb_mdl, "1")
        _set_combo_data(body.cb_faceter, "true")
        _set_combo_data(body.cb_acc_type, "0")
        body._sync_visibility()
        self.assertFalse(body._items["surf"].isHidden())
        self.assertFalse(body._items["mdl"].isHidden())
        self.assertFalse(body._items["sb_ang"].isHidden())
        self.assertTrue(body._items["vx_dist"].isHidden())
        self.assertTrue(body._items["d_chord"].isHidden())

    def test_visibility_voxel(self):
        from nav_panels import _set_combo_data
        body = MesherFaceterBody()
        _set_combo_data(body.cb_mesher, "1")
        body._sync_visibility()
        self.assertTrue(body._items["surf"].isHidden())
        self.assertTrue(body._items["mdl"].isHidden())
        self.assertFalse(body._items["vx_dist"].isHidden())

    def test_load_apply_xenv(self):
        xenv = pphxml.XenvSettings()
        pphxml.set_xenv_value(xenv, "MESH", "MESHER", "0")
        pphxml.set_xenv_value(xenv, "MESH", "SURF_MESHER", "0")
        pphxml.set_xenv_value(xenv, "FACET", "MDL_METHOD", "1")
        pphxml.set_xenv_value(xenv, "FACET", "USE_FACETTER", "true")
        pphxml.set_xenv_value(xenv, "FACET", "FACET_ACCURACY_SPECIFY_TYPE", "0")
        pphxml.set_xenv_value(xenv, "FACET", "USE_ABSOLUTE_VALUE", "false")
        pphxml.set_xenv_value(xenv, "FACET", "USE_SIMPLE_SETTING", "true")
        pphxml.set_xenv_value(xenv, "FACET", "SOLID_BASE_MINIMUM_ANGLE", "10")
        pphxml.set_xenv_value(xenv, "FACET", "SOLID_BASE_LENGTH_FACTOR", "0.05")
        pphxml.set_xenv_value(
            xenv, "FACET", "SOLID_BASE_TINY_FACE_WIDTH_RATIO", "0.05")
        pphxml.set_xenv_value(xenv, "FACET", "SIMPLE_MAX_WIDTH", "5")
        pphxml.set_xenv_value(xenv, "FACET", "SIMPLE_CHORD_TOLERANCE", "1")
        pphxml.set_xenv_value(xenv, "FACET", "SIMPLE_MAX_ANGLE", "10")
        pphxml.set_xenv_value(xenv, "FACET", "SIMPLE_CHORD_TOLERANCE_ABS", "0")
        pphxml.set_xenv_value(xenv, "FACET", "SIMPLE_MAX_WIDTH_ABS", "0")
        pphxml.set_xenv_value(
            xenv, "FACET", "SOLID_BASE_LENGTH_FACTOR_FOR_OCTREE", "0.25")
        pphxml.set_xenv_value(
            xenv, "FACET", "SOLID_BASE_MINIMUM_ANGLE_FOR_OCTREE", "5")
        for k, v in (
            ("DETAIL_CHORD_TOLERANCE", "0"), ("DETAIL_CHORD_ANGLE", "10"),
            ("DETAIL_SURF_TOLERANCE", "0"), ("DETAIL_SURF_ANGLE", "10"),
            ("DETAIL_MAX_WIDTH", "0"),
        ):
            pphxml.set_xenv_value(xenv, "FACET", k, v)

        body = MesherFaceterBody()
        ctx = NavDialogSession().build_ctx(xenv=xenv, groups_info={"g1": {}})
        body.load(ctx)
        self.assertEqual(body.cb_mesher.currentData(), "0")
        self.assertEqual(body.cb_faceter.currentData(), "true")
        self.assertAlmostEqual(body.sp_sb_ang.value(), 10.0)
        self.assertAlmostEqual(body.sp_sb_tiny.value(), 5.0)
        body.sp_sb_ang.setValue(12)
        body.sp_width_sb.setValue(6)
        self.assertTrue(body.apply(ctx))
        self.assertEqual(xenv.get("FACET", "SOLID_BASE_MINIMUM_ANGLE"), "12")
        self.assertEqual(xenv.get("FACET", "SIMPLE_MAX_WIDTH"), "6")
        self.assertTrue(ctx["xenv_dirty"])


if __name__ == "__main__":
    unittest.main()
