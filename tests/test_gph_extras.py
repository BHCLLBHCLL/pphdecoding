#!/usr/bin/env python3
"""gphstats 未解码节（Element_InformationFlag / LS_Assemblies）与写端字节对齐回归。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import gphstats  # noqa: E402
import crdlfld  # noqa: E402

BOX_GPH = ROOT / "tests" / "box" / "meshinggroup1.gph"


def _minimal_gph(sections: list[bytes]) -> bytes:
    """构造最小 CRDL-FLD 文件：文件头 + 若干节 + OverlapEnd。"""
    hdr = (b"\x00\x00\x00\x08" + crdlfld.MAGIC +
           b"\x00\x00\x00\x08\x00\x00\x00\x04\x00\x00\x00\x04")
    end = (b"\x00\x00\x00\x20" + b"OverlapEnd".ljust(32, b" "))
    return hdr + b"".join(sections) + end


class TestAssemblies(unittest.TestCase):
    def test_box_decode(self):
        with gphstats.open_buffer(str(BOX_GPH)) as data:
            xml = gphstats.assemblies_xml(data)
        self.assertTrue(xml.startswith('<?xml version="1.0"'))
        self.assertIn('<assembly name="box"', xml)
        self.assertIn('<part name="Part"/>', xml)

    def test_write_readback(self):
        xml = '<?xml version="1.0" encoding="utf-8"?>\n<root><a/></root>'
        buf = _minimal_gph([gphstats._assemblies_section(xml)])
        self.assertEqual(gphstats.assemblies_xml(buf), xml)


class TestElementInfo(unittest.TestCase):
    def test_box_decode(self):
        with gphstats.open_buffer(str(BOX_GPH)) as data:
            ei = gphstats.element_info(data)
        self.assertIsNotNone(ei)
        flag_types, flags = ei
        self.assertEqual(flag_types, 31)
        self.assertEqual(flags.size, 944)
        self.assertTrue(np.all(flags == 9))

    def test_write_readback(self):
        with gphstats.open_buffer(str(BOX_GPH)) as data:
            _, flags = gphstats.element_info(data)
        buf = _minimal_gph([gphstats._element_info_section(flags)])
        flag_types2, flags2 = gphstats.element_info(buf)
        self.assertEqual(flag_types2, 31)
        self.assertTrue(np.array_equal(flags2, flags))


if __name__ == "__main__":
    unittest.main()
