#!/usr/bin/env python3
"""sctsnapshot 字节保留重序列化回归。

覆盖：字节恒等 round-trip（box + laptop）、改叶子值后写回再解析、
_encode_scalar / _decode_scalar 互逆。
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sctsnapshot  # noqa: E402

BOX_SNAP = ROOT / "tests" / "box" / "main.sctsnapshot"
LAPTOP_SNAP = (ROOT / "tests" /
               "laptop_thermal_steady_scaled_v3_fanonly_simple" /
               "main.sctsnapshot")


class TestSerializeByteIdentity(unittest.TestCase):
    def test_box(self):
        raw = BOX_SNAP.read_bytes()
        snap = sctsnapshot.SctSnapshot.load(str(BOX_SNAP))
        self.assertEqual(snap.serialize(raw), raw)

    def test_laptop(self):
        raw = LAPTOP_SNAP.read_bytes()
        snap = sctsnapshot.SctSnapshot.load(str(LAPTOP_SNAP))
        self.assertEqual(snap.serialize(raw), raw)

    def test_serialize_reads_file_when_no_data(self):
        raw = BOX_SNAP.read_bytes()
        snap = sctsnapshot.SctSnapshot.load(str(BOX_SNAP))
        self.assertEqual(snap.serialize(), raw)


class TestEncodeScalar(unittest.TestCase):
    def test_vwu_roundtrip(self):
        v = sctsnapshot.ValueWithUnit(1.5, 1)
        b = sctsnapshot._encode_scalar("LENGTHVWU", v)
        self.assertEqual(sctsnapshot._decode_scalar("LENGTHVWU", b).value, 1.5)

    def test_dpointu_roundtrip(self):
        p = sctsnapshot.DPointU((1.0, 2.0, 3.0), (1, 1, 1))
        b = sctsnapshot._encode_scalar("DPOINTU", p)
        self.assertEqual(sctsnapshot._decode_scalar("DPOINTU", b).xyz,
                         (1.0, 2.0, 3.0))

    def test_int_array_roundtrip(self):
        import numpy as np
        a = np.array([1, -2, 300, 0], dtype=np.int64)
        b = sctsnapshot._encode_scalar("INTARRAY", a)
        self.assertTrue(np.array_equal(
            sctsnapshot._decode_scalar("INTARRAY", b), a))


class TestModifyLeaf(unittest.TestCase):
    def test_modify_lengthvwu(self):
        raw = BOX_SNAP.read_bytes()
        snap = sctsnapshot.SctSnapshot.load(str(BOX_SNAP))
        rec = next(snap.find_all("LENGTHVWU"))
        rec.value = sctsnapshot.ValueWithUnit(100.0, rec.value.unit_type)
        out = snap.serialize(raw)
        snap2 = sctsnapshot.SctSnapshot.from_bytes(out)
        rec2 = next(snap2.find_all("LENGTHVWU"))
        self.assertEqual(rec2.value.value, 100.0)


if __name__ == "__main__":
    unittest.main()