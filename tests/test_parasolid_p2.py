#!/usr/bin/env python3
"""P2: CADthru 分面二进制 schema 字段表 + 数据区偏移回归。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import parasolid  # noqa: E402
import sctsnapshot  # noqa: E402

BOX_SNAP = ROOT / "tests" / "box" / "main.sctsnapshot"


def _decrypt_pkbody3() -> bytes:
    snap = sctsnapshot.SctSnapshot.from_bytes(BOX_SNAP.read_bytes())

    def walk(recs):
        for r in recs:
            if r.tag == "ZIPBODYBYTES":
                v = r.value
                zb = (v if isinstance(v, sctsnapshot.ZipBlob)
                      else sctsnapshot.ZipBlob.parse(bytes(v)))
                return zb.decompress_body().decrypt()
            if r.children:
                x = walk(r.children)
                if x:
                    return x
        return None

    plain = walk(snap.records)
    assert plain is not None
    return plain


class TestFieldDataOffsets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stream = parasolid.parse_transmit(_decrypt_pkbody3())

    def test_schema(self):
        self.assertEqual(self.stream.version, 3701153)
        self.assertEqual(self.stream.schema, "SCH_3701153_37102_13006")
        self.assertEqual(len(self.stream.fields), 22)

    def test_lattice_mesh_polyline_offsets(self):
        offs = parasolid.field_data_offsets(self.stream)
        self.assertEqual(offs["lattice"], 222)
        self.assertEqual(offs["mesh"], 1006)
        self.assertEqual(offs["polyline"], 1008)

    def test_boundary_aliases(self):
        offs = parasolid.field_data_offsets(self.stream)
        self.assertEqual(offs["boundary_lattice"], offs["lattice"])
        self.assertEqual(offs["boundary_mesh"], offs["mesh"])
        self.assertEqual(offs["boundary_polyline"], offs["polyline"])

    def test_token_alphabet(self):
        for k in ("I", "D", "A", "C", "$", "l", "u", "d"):
            self.assertIn(k, parasolid.TOKEN_ALPHABET)


if __name__ == "__main__":
    unittest.main()
