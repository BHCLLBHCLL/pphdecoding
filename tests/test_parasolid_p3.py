#!/usr/bin/env python3
"""P3: 文本 x_t 离线解析（头/实体类型码/回引）+ V37 class 枚举回归。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import parasolid  # noqa: E402

BOX_XT = ROOT / "tests" / "box" / "box.x_t"


class TestParseTextEntities(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = parasolid.parse_text_entities(
            BOX_XT.read_text(errors="replace"))

    def test_header(self):
        self.assertEqual(self.r["header"]["FORMAT"], "text")
        self.assertEqual(self.r["header"]["GUISE"], "transmit")
        self.assertEqual(self.r["header"]["KEY"], "__PSolid__")

    def test_type_codes(self):
        tc = self.r["type_counts"]
        # T51 = transmit 容器；T2..T6 = 5 类实体（每类定义一次）
        self.assertEqual(tc.get(51), 1)
        self.assertEqual(tc.get(2), 1)
        self.assertEqual(tc.get(6), 1)

    def test_backrefs(self):
        self.assertEqual(self.r["n_refs"], 38)

    def test_sdl(self):
        self.assertIn("SDL/TYSA_COLOUR", self.r["sdl_attributes"])
        self.assertIn("SDL/TYSA_LAYER", self.r["sdl_attributes"])


class TestClassNames(unittest.TestCase):
    def test_v37_enum(self):
        self.assertEqual(parasolid.PK_CLASS_NAMES[5006], "body")
        self.assertEqual(parasolid.PK_CLASS_NAMES[5004], "face")
        self.assertEqual(parasolid.PK_CLASS_NAMES[5002], "edge")
        self.assertEqual(parasolid.PK_CLASS_NAMES[5001], "vertex")
        self.assertEqual(parasolid.PK_CLASS_NAMES[4001], "surface")
        self.assertEqual(parasolid.PK_CLASS_NAMES[3001], "curve")
        self.assertEqual(parasolid.PK_CLASS_NAMES[2501], "point")


if __name__ == "__main__":
    unittest.main()
