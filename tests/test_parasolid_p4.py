#!/usr/bin/env python3
"""P4: encode 闭环（encode_brep 内核编码 + encode_facet_mesh 未实现标注）。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import parasolid  # noqa: E402
import ps_facet2_nodes as psf  # noqa: E402

BOX_XT = ROOT / "tests" / "box" / "box.x_t"


class TestEncodeBrep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not psf.available():
            raise unittest.SkipTest("pskernel.dll not available")

    def test_decode_encode_roundtrip(self):
        brep = psf.decode_brep(BOX_XT.read_bytes())
        self.assertTrue(brep["bodies"])
        # 编码首个体 → 文本 x_t → 再 receive（可再解析）
        xt = parasolid.encode_brep(brep["bodies"])
        self.assertIn(b"TRANSMIT FILE", xt)
        sess = psf._get_session()
        rebodies = sess.receive_xt(xt)
        self.assertTrue(rebodies)
        self.assertEqual(sess._ask_class(rebodies[0]), 5006)  # body

    def test_encode_facet_mesh_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            parasolid.encode_facet_mesh({})


if __name__ == "__main__":
    unittest.main()
