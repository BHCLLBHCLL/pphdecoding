#!/usr/bin/env python3
"""条件注册表测试（box.pph）。"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pphxml  # noqa: E402
from condition_registry import ConditionRegistry  # noqa: E402
from pph_parser import PphArchive  # noqa: E402

BOX_PPH = ROOT / "box.pph"


class TestConditionRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arch = PphArchive.open(str(BOX_PPH))
        cls.reg = ConditionRegistry.from_archive(cls.arch, "box")

    def test_type_names(self):
        names = self.reg.type_names()
        self.assertIn("CondBoundaryFlowIO", names)
        self.assertIn("CondBoundaryWallThermal", names)

    def test_get_type(self):
        t = self.reg.get("CondBoundaryFlowIO")
        self.assertIsNotNone(t)
        self.assertGreaterEqual(t.count, 1)
        self.assertIn("open", t.regions)
        self.assertIn("flow_io_type", t.fields)

    def test_summary_counts(self):
        s = self.reg.summary()
        self.assertGreaterEqual(s["condition_type_count"], 5)
        self.assertGreaterEqual(s["condition_count"], 10)

    def test_json_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "registry.json"
            self.reg.save_json(path)
            loaded = ConditionRegistry.load_json(path)
        self.assertEqual(loaded.type_names(), self.reg.type_names())
        t1 = self.reg.get("CondBoundaryFlowIO")
        t2 = loaded.get("CondBoundaryFlowIO")
        self.assertEqual(t2.to_dict(), t1.to_dict())

    def test_validate_condition(self):
        xml = self.arch.read_member("main.xml")
        mx = pphxml.parse_main_xml(xml)
        cond = mx.conditions()[0]
        result = self.reg.validate_condition(cond)
        self.assertEqual(result["type"], "CondBoundaryFlowIO")
        self.assertEqual(result["issues"], [])


if __name__ == "__main__":
    unittest.main()
