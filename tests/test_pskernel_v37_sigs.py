#!/usr/bin/env python3
"""pskernel_v37_sigs：V37 新增导出完整签名补全表回归。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pskernel_v37  # noqa: E402
import pskernel_v37_sigs as sigs  # noqa: E402


class TestSignatureTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not pskernel_v37.PSK37.exists():
            raise unittest.SkipTest("2025.2 pskernel.dll not installed")
        cls.d = sigs.build_v37_signatures()

    def test_all_covered(self):
        self.assertEqual(len(self.d), 104)
        for name, v in self.d.items():
            self.assertIsNotNone(v["proto"], f"{name} 缺签名")
            self.assertIn(v["confidence"], ("high", "med", "low"))
            self.assertIn("PK_ERROR_code_t", v["proto"])

    def test_high_confidence_getters(self):
        for name in ("PK_SESSION_ask_cellular_guise", "PK_FACE_ask_type",
                     "PK_REGION_ask_type", "PK_FRAME_ask_body",
                     "PK_LATTICE_ask_type", "PK_BODY_slice"):
            self.assertIn(name, self.d)
            self.assertEqual(self.d[name]["confidence"], "high")

    def test_r_f_convention(self):
        # _r_f = 基函数 + PK_FRUSTUM_t *frustrum
        proto = self.d["PK_BODY_slice_r_f"]["proto"]
        self.assertIn("PK_FRUSTUM_t *frustrum", proto)
        # 基函数名保留（_r_f 签名中函数名仍为基函数名）
        self.assertIn("PK_BODY_slice(", proto)

    def test_mark_2_base(self):
        # PK_MARK_create_r_f 基函数 = PK_MARK_create_2（命名去 _2）
        self.assertIn("PK_MARK_create_2(", self.d["PK_MARK_create_r_f"]["proto"])

    def test_dump_md(self):
        text = sigs.dump_signatures_md()
        self.assertIn("pskernel V37 新增导出签名补全表", text)
        self.assertIn("PK_BODY_slice", text)
        rows = [ln for ln in text.splitlines() if ln.startswith("| PK_")]
        self.assertEqual(len(rows), 104)


if __name__ == "__main__":
    unittest.main()
