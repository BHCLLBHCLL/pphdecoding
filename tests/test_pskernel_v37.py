#!/usr/bin/env python3
"""pskernel_v37：V37 新增导出逆向补充回归（依赖 2025.2 pskernel）。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pskernel_v37 as v  # noqa: E402


class TestV37OnlyExports(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not v.PSK37.exists():
            raise unittest.SkipTest("2025.2 pskernel.dll not installed")

    def test_count(self):
        only = v.v37_only_exports()
        self.assertEqual(len(only), 104)

    def test_families(self):
        only = v.v37_only_exports()
        self.assertIn("PK_BODY_slice", only)
        self.assertIn("PK_LATTICE_create_by_core", only)
        self.assertIn("PK_FRAME_ask_body", only)
        # 2023（V34.1）没有这些导出
        p23 = Path("C:/Program Files/Cradle/CradleCFD2023/Programs_x64/"
                   "pskernel.dll")
        if p23.exists():
            import pskernel_abi as abi
            n23 = {e.name for e in abi.dump_exports(str(p23))}
            for name in ("PK_BODY_slice", "PK_LATTICE_create_by_core"):
                self.assertNotIn(name, n23)

    def test_classify(self):
        self.assertEqual(v.classify("PK_LATTICE_ask_type"), "LATTICE")
        self.assertEqual(v.classify("PK_FRAME_ask_body"), "FRAME")
        self.assertEqual(v.classify("PK_BODY_slice_r_f"), "BODY_slice")

    def test_base_name(self):
        self.assertEqual(v.base_name("PK_BODY_slice_r_f"), "PK_BODY_slice")
        self.assertEqual(v.base_name("PK_BODY_slice_cb_r_f"),
                         "PK_BODY_slice")
        self.assertEqual(v.base_name("PK_BODY_slice"), "PK_BODY_slice")


class TestInferenceCalibration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not v.PSK37.exists():
            raise unittest.SkipTest("2025.2 pskernel.dll not installed")
        cls.cal = v.calibrate()

    def test_exact_matches(self):
        # 文档化签名对拍：4 参数函数推断 = 4
        self.assertEqual(self.cal["PK_PART_transmit"]["got"], 4)
        self.assertEqual(self.cal["PK_PART_receive"]["got"], 4)
        for name, r in self.cal.items():
            self.assertGreaterEqual(r["got"], r["expected"] - 1,
                                    f"{name} argc 下界不符")


class TestSupplement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not v.PSK37.exists():
            raise unittest.SkipTest("2025.2 pskernel.dll not installed")
        cls.supp = v.supplement()

    def test_all_covered(self):
        self.assertEqual(len(self.supp), 104)
        for name, info in self.supp.items():
            self.assertIn("family", info)
            self.assertIn("argc", info)

    def test_slice_family(self):
        s = self.supp["PK_BODY_slice"]
        self.assertEqual(s["family"], "BODY_slice")
        self.assertEqual(s["argc"], 4)
        self.assertIn("2", s["byte_args"])   # 第 2 参数 = logical 字节

    def test_verified_table(self):
        self.assertIn("PK_SESSION_ask_cellular_guise", v.V37_VERIFIED)
        self.assertEqual(v.V37_VERIFIED["PK_SESSION_ask_cellular_guise"]
                         ["rc"], 0)


class TestSchemaDiff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p = Path("C:/Program Files/Cradle/CradleCFD2023/Programs_x64/"
                 "Schemas/sch_34101.sch_txt")
        if not p.exists():
            raise unittest.SkipTest("2023 Schemas not installed")
        cls.d = v.schema_diff()

    def test_new_types(self):
        self.assertIn(233, self.d["new_types"])
        self.assertEqual(self.d["new_types"][233], "IMPLICIT_SURF")
        self.assertIn(234, self.d["new_types"])
        self.assertIn(237, self.d["new_types"])   # PATTERN_AXIAL
        self.assertIn(238, self.d["new_types"])   # LATTICE_DATA_PATTERN


if __name__ == "__main__":
    unittest.main()
