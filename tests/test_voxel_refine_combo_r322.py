#!/usr/bin/env python3
"""R32-2 回归：枚举下拉框由**目录词表**驱动（可写白名单 = 实测编码表）。

两层各司其职（见审计 §46.2）：

* 实测编码表 `pphxml.VOXEL_OCT_REFINE_TYPES` 决定**谁能被写出去**；
* 目录词表 `GetVoxelOctRefineType` 决定**标签**（手册口径）。

于是「目录新增有码的取值」会自动出现在控件里；「目录有值但没实测码」不会
（写不出去，列出来只会让用户选到无效项）。
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pphxml  # noqa: E402
from automation import scflowpre_api as api  # noqa: E402


class TestItemsFromCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import nav_panels
        except Exception:  # noqa: BLE001
            raise unittest.SkipTest("PyQt5 not available")
        cls.nav = nav_panels

    @staticmethod
    def _by_data(items):
        """(标签, 数据) 列表 → {数据: 标签}。"""
        return {data: label for label, data in items}

    def test_labels_come_from_catalog(self):
        items = self._by_data(self.nav._voxel_refine_items())
        self.assertEqual(items["speed"], "Speed-weighted")
        self.assertEqual(items["shape"], "Model shape-weighted")
        # 目录漏项（宿主默认 octree）用回落标签
        self.assertEqual(items["octree"], "Octree (host default)")

    def test_every_item_is_writable(self):
        for label, data in self.nav._voxel_refine_items():
            self.assertTrue(label)
            self.assertIsNotNone(pphxml.voxel_oct_refine_code(data), data)

    def test_catalog_label_change_shows_up(self):
        """改目录描述 → 控件标签跟着变（不是写死字符串）。"""
        orig = api.api_values
        try:
            api.api_values = lambda *a, **k: [
                {"value": "speed", "description": "SPEED (from catalog)"},
                {"value": "shape", "description": "SHAPE (from catalog)"}]
            items = self._by_data(self.nav._voxel_refine_items())
        finally:
            api.api_values = orig
        self.assertEqual(items["speed"], "SPEED (from catalog)")
        self.assertEqual(items["shape"], "SHAPE (from catalog)")

    def test_new_documented_value_with_code_appears(self):
        """目录新增取值 + 有实测码 → 自动进控件。"""
        orig_api, orig_tab = api.api_values, dict(
            pphxml.VOXEL_OCT_REFINE_TYPES)
        try:
            api.api_values = lambda *a, **k: [
                {"value": "auto", "description": "Automatic (new)"}]
            pphxml.VOXEL_OCT_REFINE_TYPES["auto"] = "4"
            items = self._by_data(self.nav._voxel_refine_items())
        finally:
            api.api_values = orig_api
            pphxml.VOXEL_OCT_REFINE_TYPES.clear()
            pphxml.VOXEL_OCT_REFINE_TYPES.update(orig_tab)
        self.assertEqual(items.get("auto"), "Automatic (new)")

    def test_documented_value_without_code_is_excluded(self):
        """目录有值但没实测码 → 不进控件（写不出去）。"""
        orig = api.api_values
        try:
            api.api_values = lambda *a, **k: [
                {"value": "mystery", "description": "Not writable"}]
            datas = [d for _l, d in self.nav._voxel_refine_items()]
        finally:
            api.api_values = orig
        self.assertNotIn("mystery", datas)

    def test_catalog_absence_does_not_break_gui(self):
        orig = api.api_values
        try:
            def boom(*a, **k):
                raise RuntimeError("catalog missing")
            api.api_values = boom
            items = self.nav._voxel_refine_items()
        finally:
            api.api_values = orig
        self.assertEqual(len(items), len(pphxml.VOXEL_OCT_REFINE_TYPES))


if __name__ == "__main__":
    unittest.main()
