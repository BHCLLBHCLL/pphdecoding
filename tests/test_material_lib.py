"""P4-2 材料五库测试：解析 / 兜底 / GUI 选择器。"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from material_lib import (HeatTransferPreset, MaterialLib, NedoSite,
                          parse_heattransfer, parse_nedo_sites,
                          parse_prp_struct, parse_reaction_species,
                          parse_solar_locations, _parse_property_xml)


def _installed() -> bool:
    from material_lib import locate_programs
    return locate_programs() is not None


HEATTRANSFER_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8" ?>
<heattransfer>
  <entry>
    <type> 1 </type>
    <name> Exterior wall </name>
    <value> 17.0, 23.0 </value>
  </entry>
  <entry>
    <type> 3 </type>
    <name> Indoor </name>
    <subname> Floor </subname>
    <value> -1, -1, -1 </value>
  </entry>
</heattransfer>
"""

PROPERTY_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8" ?>
<property>
  <group>
    <type> fluid </type>
    <name> gas(incompressible) </name>
    <entry>
      <name> air(test) </name>
      <density> 1.2 </density>
      <viscosity> 1.8e-05 </viscosity>
    </entry>
  </group>
</property>
"""

PRP_STRUCT_SAMPLE = """# prp_struct version="2.0"
copper(Cu) pure_metal
isotropic_elastic
complete
       1.29e+011           0.343            8960        1.7e-005              20
"""

SOLAR_SAMPLE = b"""<?xml version="1.0" ?>
<solar>
  <location>
    <entry>
      <name> Tokyo </name>
      <latitude> 35.68 </latitude>
      <longitude> 139.77 </longitude>
      <standard> 135.00 </standard>
    </entry>
  </location>
</solar>
"""

NEDO_SAMPLE_STR = """<?xml version="1.0" ?>
<solar_NEDO>
  <category>
    <name lang="eng"> Hokkaido </name>
    <name lang="jpn"> 北海道 </name>
    <site no="11001">
      <name lang="eng"> SOYAMISAKI </name>
      <name lang="jpn"> 宗谷岬 </name>
      <latitude> 45.52 </latitude>
      <longitude> 141.94 </longitude>
      <standard> 135 </standard>
      <elevation> 26 </elevation>
    </site>
  </category>
</solar_NEDO>
"""
NEDO_SAMPLE = NEDO_SAMPLE_STR.encode("utf-8")

REACTION_SAMPLE = b"""<?xml version="1.0" ?>
<reaction>
  <material>
    <entry>
      <name> CH4 </name>
      <mole>  1.0E-02 </mole>
      <type> gas </type>
      <unit> none </unit>
      <composition>
        <component no="1"> C,1 </component>
        <component no="2"> H,4 </component>
      </composition>
    </entry>
  </material>
</reaction>
"""


class TestParsers(unittest.TestCase):
    """纯函数解析器（内置样本，不依赖安装）。"""

    def test_parse_property_xml(self):
        ms = _parse_property_xml(PROPERTY_SAMPLE)
        self.assertEqual(len(ms), 1)
        self.assertEqual(ms[0].name, "air(test)")
        self.assertEqual(ms[0].kind, "fluid")
        self.assertEqual(ms[0].props["density"], "1.2")

    def test_parse_prp_struct(self):
        metals = parse_prp_struct(PRP_STRUCT_SAMPLE)
        self.assertEqual(len(metals), 1)
        m = metals[0]
        self.assertEqual(m.name, "copper(Cu)")
        self.assertEqual(m.category, "pure_metal")
        self.assertAlmostEqual(m.young, 1.29e11)
        self.assertAlmostEqual(m.poisson, 0.343)
        self.assertAlmostEqual(m.density, 8960)

    def test_parse_heattransfer(self):
        ps = parse_heattransfer(HEATTRANSFER_SAMPLE)
        self.assertEqual(len(ps), 2)
        self.assertEqual(ps[0].name, "Exterior wall")
        self.assertEqual(ps[0].values, [17.0, 23.0])
        self.assertEqual(ps[1].subname, "Floor")
        self.assertEqual(len(ps[1].values), 3)

    def test_parse_solar_locations(self):
        locs = parse_solar_locations(SOLAR_SAMPLE)
        self.assertEqual(len(locs), 1)
        self.assertEqual(locs[0].name, "Tokyo")
        self.assertAlmostEqual(locs[0].latitude, 35.68)
        self.assertAlmostEqual(locs[0].standard, 135.0)

    def test_parse_nedo_sites(self):
        sites = parse_nedo_sites(NEDO_SAMPLE)
        self.assertEqual(len(sites), 1)
        s = sites[0]
        self.assertEqual(s.no, "11001")
        self.assertEqual(s.category, "Hokkaido")
        self.assertEqual(s.name_jpn, "宗谷岬")
        self.assertAlmostEqual(s.longitude, 141.94)

    def test_parse_reaction_species(self):
        sp = parse_reaction_species(REACTION_SAMPLE)
        self.assertEqual(len(sp), 1)
        self.assertEqual(sp[0].name, "CH4")
        self.assertAlmostEqual(sp[0].mole, 1.0e-2)
        self.assertEqual(sp[0].composition, {"C": 1.0, "H": 4.0})


@unittest.skipUnless(_installed(), "Cradle Programs_x64 not installed")
class TestInstalledLibraries(unittest.TestCase):
    """安装目录五库规模与关键字段。"""

    @classmethod
    def setUpClass(cls):
        cls.lib = MaterialLib()

    def test_property_scale(self):
        entries = self.lib.property_entries()
        self.assertGreaterEqual(len(self.lib.fluids()), 100)
        self.assertGreaterEqual(len(self.lib.solids()), 100)
        air = [m for m in entries
               if m.name == "air(incompressible/20C)"]
        self.assertTrue(air)
        self.assertEqual(air[0].props.get("density"), "1.206")

    def test_metals(self):
        metals = self.lib.metals()
        self.assertGreaterEqual(len(metals), 10)
        names = {m.name for m in metals}
        self.assertIn("copper(Cu)", names)
        self.assertIn("iron(Fe)", names)

    def test_heat_presets(self):
        ps = self.lib.heat_transfer_presets()
        self.assertGreaterEqual(len(ps), 15)
        self.assertTrue(any(p.name == "Exterior wall" for p in ps))

    def test_solar_and_nedo(self):
        self.assertGreaterEqual(len(self.lib.solar_locations()), 5)
        sites = self.lib.nedo_sites()
        self.assertGreaterEqual(len(sites), 800)
        self.assertTrue(any(s.name == "SOYAMISAKI" for s in sites))

    def test_reaction_species(self):
        sp = self.lib.reaction_species()
        self.assertGreaterEqual(len(sp), 10)
        names = {x.name for x in sp}
        self.assertIn("CH4", names)

    def test_summary(self):
        s = self.lib.summary()
        for key in ("fluids", "solids", "metals", "heat_transfer_presets",
                    "solar_locations", "nedo_sites", "reaction_species"):
            self.assertGreater(s[key], 0)


def _gui_available() -> bool:
    try:
        from PyQt5.QtWidgets import QApplication  # noqa: F401
    except Exception:
        return False
    return bool(os.environ.get("QT_QPA_PLATFORM") == "offscreen")


@unittest.skipUnless(_gui_available() and _installed(),
                     "Qt offscreen / Cradle unavailable")
class TestMaterialGui(unittest.TestCase):
    """P4-2 GUI：安装库兜底 + 预设/站点选择器。"""

    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_install_prp_fallback(self):
        import nav_panels as np_
        np_._INSTALL_PRP_CACHE = None
        try:
            db = np_.install_prp_fallback()
            self.assertIsNotNone(db)
            groups = db.group_names()
            self.assertTrue(any("gas" in g for g in groups))
            total = sum(len(db.entries(g)) for g in db.groups)
            self.assertGreaterEqual(total, 250)
        finally:
            np_._INSTALL_PRP_CACHE = None

    def test_part_material_tree_fallback(self):
        import nav_panels as np_
        np_._INSTALL_PRP_CACHE = None
        try:
            body = np_.PartMaterialBody()
            body._ctx = {}   # 无项目 prp → 兜底
            body._part_tab["rb_fluid"].setChecked(True)
            tree: object = body._part_tab["mat_tree"]
            n = sum(tree.topLevelItem(i).childCount()
                    for i in range(tree.topLevelItemCount()))
            self.assertGreaterEqual(n, 50)   # 流体 ≥50 可选
        finally:
            np_._INSTALL_PRP_CACHE = None

    def test_preset_dialog(self):
        import nav_panels as np_
        dlg = np_.HeatTransferPresetDialog()
        try:
            self.assertGreaterEqual(dlg.lst.topLevelItemCount(), 15)
            it = dlg.lst.topLevelItem(0)
            dlg._pick(it)
            self.assertIsNotNone(dlg.preset)
        finally:
            dlg.deleteLater()

    def test_solar_site_dialog(self):
        import nav_panels as np_
        dlg = np_.SolarSiteDialog()
        try:
            self.assertGreaterEqual(
                dlg.lst_world.topLevelItemCount(), 5)
            self.assertGreaterEqual(
                dlg.lst_nedo.topLevelItemCount(), 30)  # 都道府县分组
            # 找一个 NEDO 子站点选择
            top = dlg.lst_nedo.topLevelItem(0)
            if top.childCount():
                dlg._pick(top.child(0))
                self.assertIsNotNone(dlg.site)
        finally:
            dlg.deleteLater()


if __name__ == "__main__":
    unittest.main()
