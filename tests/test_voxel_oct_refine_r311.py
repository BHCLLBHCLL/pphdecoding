#!/usr/bin/env python3
"""R31-1 回归：把 R30 实测的 `VOXEL_OCT_REFINE_TYPE` 接进面板写回。

背景：R29/R30 把 `OCT_MESH` 段 6 条键全部单变量定谳，但 `MesherFaceterBody`
只写其中 5 条 —— 第 6 条（R30 才定谳的 `VOXEL_OCT_REFINE_TYPE`）没有回流到面板。
本条还带来一个**编码翻译**：API/面板说字符串枚举（`speed`/`shape`/`octree`），
而 main.xenv 落整数码（1/2/3）——映射表来自 R30 单变量逐档实测（审计 §44.1）。
"""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pphxml  # noqa: E402

_APPS: list = []


def _app():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(
        ["test", "-platform", "offscreen"])
    if not _APPS:
        _APPS.append(app)
    return _APPS[0]


class TestEncodingTable(unittest.TestCase):
    """编码表就是实机实测值 —— 写死是**有意**的（防口径漂移）。"""

    def test_measured_codes(self):
        self.assertEqual(pphxml.voxel_oct_refine_code("speed"), "1")
        self.assertEqual(pphxml.voxel_oct_refine_code("shape"), "2")
        self.assertEqual(pphxml.voxel_oct_refine_code("octree"), "3")

    def test_roundtrip_both_ways(self):
        for name in ("speed", "shape", "octree"):
            code = pphxml.voxel_oct_refine_code(name)
            self.assertEqual(pphxml.voxel_oct_refine_name(code), name)

    def test_name_lookup_is_case_insensitive(self):
        self.assertEqual(pphxml.voxel_oct_refine_code("Shape"), "2")
        self.assertEqual(pphxml.voxel_oct_refine_code(" OCTREE "), "3")

    def test_unknown_values_are_rejected(self):
        """宿主实测：大小写错/数值档一律 False —— 面板不得落未知值。"""
        for bad in ("voxel", "oct", "0", "9", "", None):
            self.assertIsNone(pphxml.voxel_oct_refine_code(bad), repr(bad))
        self.assertIsNone(pphxml.voxel_oct_refine_name("9"))
        self.assertIsNone(pphxml.voxel_oct_refine_name(None))


class TestPanelWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import nav_panels
        except Exception:  # noqa: BLE001
            raise unittest.SkipTest("PyQt5 not available")
        cls.nav = nav_panels

    def _body(self, code: str):
        _app()
        xenv = pphxml.XenvSettings()
        if code is not None:
            pphxml.set_xenv_value(xenv, "OCT_MESH", "VOXEL_OCT_REFINE_TYPE",
                                  code)
        ctx = {"xenv": xenv, "session": {}, "xml": None}
        body = self.nav.MesherFaceterBody()
        body.load(ctx)
        return body, ctx, xenv

    def test_row_exists_and_is_voxel_scoped(self):
        body, _ctx, _x = self._body("3")
        self.assertIn("oct_refine", body._items)

    def test_load_translates_code_to_enum_name(self):
        body, _ctx, _x = self._body("1")
        self.assertEqual(body.cb_vx_refine.currentData(), "speed")
        body2, _ctx2, _x2 = self._body("2")
        self.assertEqual(body2.cb_vx_refine.currentData(), "shape")

    def test_unknown_code_falls_back_to_host_default(self):
        body, _ctx, _x = self._body("9")
        self.assertEqual(body.cb_vx_refine.currentData(), "octree")

    def test_apply_writes_measured_code(self):
        body, ctx, xenv = self._body("3")
        body.cb_vx_refine.setCurrentIndex(
            body.cb_vx_refine.findData("shape"))
        self.assertTrue(body.apply(ctx))
        self.assertEqual(xenv.get("OCT_MESH", "VOXEL_OCT_REFINE_TYPE"), "2")

    def test_apply_roundtrip_through_reload(self):
        body, ctx, xenv = self._body("1")
        body.cb_vx_refine.setCurrentIndex(
            body.cb_vx_refine.findData("speed"))
        body.apply(ctx)
        re_ctx = {"xenv": xenv, "session": {}, "xml": None}
        again = self.nav.MesherFaceterBody()
        again.load(re_ctx)
        self.assertEqual(again.cb_vx_refine.currentData(), "speed")
        self.assertEqual(xenv.get("OCT_MESH", "VOXEL_OCT_REFINE_TYPE"), "1")


class TestOCTMeshCoverage(unittest.TestCase):
    """面板必须写全 R30 定谳的 OCT_MESH 6 键（单调不变量：只增不减）。"""

    KEYS = ("FACET_ANGLE", "FACET_LENGTH_FACTOR", "FACET_MAX_WIDTH_FACTOR",
            "FACET_SPECIFY_EACH_REGION", "COMPLETE_PARALLEL",
            "VOXEL_OCT_REFINE_TYPE")

    @classmethod
    def setUpClass(cls):
        try:
            import nav_panels
        except Exception:  # noqa: BLE001
            raise unittest.SkipTest("PyQt5 not available")
        cls.nav = nav_panels

    def test_all_measured_oct_keys_written(self):
        _app()
        xenv = pphxml.XenvSettings()
        ctx = {"xenv": xenv, "session": {}, "xml": None}
        body = self.nav.MesherFaceterBody()
        body.load(ctx)
        body.apply(ctx)
        for key in self.KEYS:
            self.assertIsNotNone(xenv.get("OCT_MESH", key),
                                 "OCT_MESH." + key + " 未被面板写出")


if __name__ == "__main__":
    unittest.main()
