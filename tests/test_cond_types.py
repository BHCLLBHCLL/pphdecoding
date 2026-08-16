"""P4-1 条件类型目录测试：二进制提取 / HTML 元数据 / 注册表合并 / GUI 目录。"""
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCHEMAS = ROOT / "schemas"
COND_JSON = SCHEMAS / "cond_types.json"
META_JSON = SCHEMAS / "cond_html_meta.json"


def _gui_available() -> bool:
    try:
        from PyQt5.QtWidgets import QApplication  # noqa: F401
    except Exception:
        return False
    return bool(os.environ.get("QT_QPA_PLATFORM") == "offscreen")


class TestCondTypesJson(unittest.TestCase):
    """schemas/cond_types.json（scFLOWpre 二进制扫描产物）。"""

    @classmethod
    def setUpClass(cls):
        if not COND_JSON.is_file():
            raise unittest.SkipTest("cond_types.json not generated")
        cls.data = json.loads(COND_JSON.read_text(encoding="utf-8"))
        cls.types = cls.data["types"]

    def test_scale_and_categories(self):
        self.assertGreaterEqual(len(self.types), 150)
        cats = {t["category"] for t in self.types.values()}
        for want in ("bc_flow", "bc_wall", "bc_thermal", "source",
                     "particle", "output", "cosim"):
            self.assertIn(want, cats)

    def test_key_types_present_with_display(self):
        for name in ("CondBoundaryFlowIO", "CondBoundaryWallThermal",
                     "CondBoundaryRadiation", "CondBoundarySolarRadiation",
                     "CondHumidity", "CondParticleBoundaryDEM",
                     "CondPorousMedia", "CondSource"):
            self.assertIn(name, self.types)
            self.assertTrue(self.types[name]["display"])

    def test_sample_backed_marked(self):
        sampled = [t for t in self.types.values() if t.get("sample")]
        self.assertGreaterEqual(len(sampled), 5)

    def test_aliases(self):
        self.assertEqual(self.data["aliases"]["Electric"],
                         "CondBoundaryElectric")
        self.assertEqual(self.data["aliases"]["Reaction"], "CondReaction")

    def test_no_impl_variants(self):
        for name in self.types:
            self.assertFalse(name.endswith("Impl"))
            self.assertFalse(name.endswith("_"))


class TestHtmlMeta(unittest.TestCase):
    """schemas/cond_html_meta.json（184 页解析 + 交叉核对）。"""

    @classmethod
    def setUpClass(cls):
        if not META_JSON.is_file():
            raise unittest.SkipTest("cond_html_meta.json not generated")
        cls.data = json.loads(META_JSON.read_text(encoding="utf-8"))

    def test_all_pages_parsed(self):
        self.assertEqual(len(self.data["pages"]), 184)

    def test_page_structure(self):
        by_file = {p["file"]: p for p in self.data["pages"]}
        rad = by_file["radiation_bc.html"]
        self.assertEqual(rad["title"], "Radiation")
        names = [p["name"] for p in rad["params"]]
        self.assertIn("Emissivity", names)

    def test_manual_links_validated(self):
        rep = self.data["crosscheck"]
        self.assertEqual(len(rep["manual_issues"]), 0)
        self.assertGreaterEqual(len(rep["manual_matched"]), 20)
        # help 链接应已回填 cond_types.json
        cj = json.loads(COND_JSON.read_text(encoding="utf-8"))
        helped = [t for t in cj["types"].values() if t.get("help")]
        self.assertGreaterEqual(len(helped), 20)


class TestRegistryMerge(unittest.TestCase):
    """condition_registry.merge_catalog 合并行为。"""

    @classmethod
    def setUpClass(cls):
        from condition_registry import ConditionRegistry
        reg = ConditionRegistry()
        reg.merge_catalog(COND_JSON)
        cls.reg = reg

    def test_merge_scale(self):
        self.assertGreaterEqual(len(self.reg.types), 150)

    def test_by_category(self):
        flow = self.reg.by_category(["bc_flow"])
        self.assertIn("CondBoundaryFlowIO", flow)
        thermal = self.reg.by_category(
            ["bc_thermal", "radiation", "solar", "humidity"])
        for want in ("CondBoundaryWallThermal", "CondBoundaryRadiation",
                     "CondBoundarySolarRadiation", "CondHumidity"):
            self.assertIn(want, thermal)

    def test_alias_resolution(self):
        self.assertEqual(self.reg.resolve_alias("Electric"),
                         "CondBoundaryElectric")
        self.assertEqual(self.reg.resolve_alias("CondMoving"),
                         "CondMoving")

    def test_metadata_backfilled(self):
        t = self.reg.get("CondBoundaryFlowIO")
        self.assertEqual(t.category, "bc_flow")
        self.assertEqual(t.display, "Inflow and outflow condition")
        self.assertEqual(t.help_file, "Flux_Inout.html")
        self.assertGreater(t.sample_count, 0)

    def test_roundtrip_dict(self):
        from condition_registry import ConditionType
        t = self.reg.get("CondPorousMedia")
        d = t.to_dict()
        t2 = ConditionType.from_dict("CondPorousMedia", d)
        self.assertEqual(t2.category, "porous")
        self.assertEqual(t2.display, t.display)
        self.assertEqual(t2.help_file, t.help_file)


@unittest.skipUnless(_gui_available(), "Qt offscreen unavailable")
class TestCatalogGui(unittest.TestCase):
    """CondTypeCatalogDialog 离屏冒烟。"""

    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _dialog(self, cats=None):
        import nav_panels as np_
        ctx = {"session": {}}
        return np_.CondTypeCatalogDialog(ctx, cats)

    def test_catalog_lists_all(self):
        dlg = self._dialog()
        try:
            self.assertGreaterEqual(dlg.lst.topLevelItemCount(), 150)
        finally:
            dlg.deleteLater()

    def test_catalog_page_filter(self):
        dlg = self._dialog(["bc_flow"])
        try:
            reg_types = {dlg.lst.topLevelItem(i).data(0, 0x0100)
                         for i in range(dlg.lst.topLevelItemCount())}
            self.assertIn("CondBoundaryFlowIO", reg_types)
            self.assertNotIn("CondBoundaryWallStress", reg_types)
        finally:
            dlg.deleteLater()

    def test_registry_cached_merges_catalog(self):
        import nav_panels as np_
        np_._COND_REGISTRY_CACHE = None
        try:
            reg = np_.condition_registry_cached()
            self.assertIsNotNone(reg)
            self.assertGreaterEqual(len(reg.types), 150)
        finally:
            np_._COND_REGISTRY_CACHE = None


if __name__ == "__main__":
    unittest.main()
