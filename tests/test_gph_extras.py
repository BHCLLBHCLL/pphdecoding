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


class TestPrismLayers(unittest.TestCase):
    BOUNDARY = 0xFFFFFFFF

    def test_two_prism_column(self):
        # 两个三棱柱共享一个内部面（face 4）→ 一列长 2
        owner = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1], dtype=np.int64)
        neigh = np.array([self.BOUNDARY] * 4 + [1] + [self.BOUNDARY] * 4,
                         dtype=np.int64)
        npe = np.array([3, 4, 4, 4, 3, 4, 4, 4, 3], dtype=np.int64)
        r = gphstats.prism_layers(owner, neigh, npe)
        self.assertEqual(r["n_prism"], 2)
        self.assertEqual(r["n_columns"], 1)
        self.assertEqual(r["column_lengths"], [2])
        self.assertEqual(r["length_histogram"], {2: 1})

    def test_no_prism(self):
        owner = np.zeros(6, dtype=np.int64)
        neigh = np.full(6, self.BOUNDARY, dtype=np.int64)
        npe = np.full(6, 4, dtype=np.int64)
        r = gphstats.prism_layers(owner, neigh, npe)
        self.assertEqual(r["n_prism"], 0)

    def test_box_no_prism(self):
        with gphstats.open_buffer(str(BOX_GPH)) as data:
            mesh = gphstats.parse_mesh(data)
        r = gphstats.prism_layers(mesh["owner"], mesh["neigh"], mesh["npe"])
        self.assertEqual(r["n_prism"], 0)


class TestByteExactSections(unittest.TestCase):
    """写端字节对齐：新节与原始 box 逐字节一致（含 40B 节头 + 20B 哨兵）。"""

    def _sec_bytes(self, name):
        with open(BOX_GPH, "rb") as f:
            data = f.read()
        s = gphstats._find_section(data, name)
        return bytes(data[s.start:s.end])

    def test_cvol_byte_exact(self):
        with gphstats.open_buffer(str(BOX_GPH)) as data:
            cvol = gphstats.cvol_ids(data)
        self.assertEqual(gphstats._cvol_section(cvol),
                         self._sec_bytes("LS_CvolIdOfElements"))

    def test_element_info_byte_exact(self):
        with gphstats.open_buffer(str(BOX_GPH)) as data:
            _, flags = gphstats.element_info(data)
        self.assertEqual(gphstats._element_info_section(flags),
                         self._sec_bytes("Element_InformationFlag"))

    def test_assemblies_byte_exact(self):
        with gphstats.open_buffer(str(BOX_GPH)) as data:
            xml = gphstats.assemblies_xml(data)
        self.assertEqual(gphstats._assemblies_section(xml),
                         self._sec_bytes("LS_Assemblies"))

    def test_comments_byte_exact(self):
        self.assertEqual(gphstats._comments_section("PolyHedra"),
                         self._sec_bytes("Comments"))

    def test_write_gph_volume_roundtrip_with_new_sections(self):
        with gphstats.open_buffer(str(BOX_GPH)) as data:
            mesh = gphstats.parse_mesh(data)
            cvol = gphstats.cvol_ids(data)
            ei = gphstats.element_info(data)
            xml = gphstats.assemblies_xml(data)
        faces = [
            mesh["conn"][mesh["face_offsets"][i]:mesh["face_offsets"][i + 1]].tolist()
            for i in range(mesh["n_faces"])
        ]
        p = ROOT / "_roundtrip2.gph"
        try:
            gphstats.write_gph_volume(
                p, mesh["vertices"], faces, mesh["owner"], mesh["neigh"],
                cvol=cvol, element_info=ei[1], assemblies=xml)
            with gphstats.open_buffer(str(p)) as raw:
                self.assertEqual(gphstats.element_info(raw)[1].tolist(),
                                 ei[1].tolist())
                self.assertEqual(gphstats.assemblies_xml(raw), xml)
        finally:
            p.unlink(missing_ok=True)


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
