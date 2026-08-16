#!/usr/bin/env python3
"""sctsnapshot 字节保留重序列化回归。

覆盖：字节恒等 round-trip（box + laptop）、改叶子值后写回再解析、
_encode_scalar / _decode_scalar 互逆、OCTREEREGION 后序写端（P3-2）。
"""

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

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


class TestOctreeRegionWrite(unittest.TestCase):
    """P3-2：OCTREEREGION 后序写端（encode + LZMS 压缩 + 写回）。"""

    def test_encode_simple_tree(self):
        # 根内部 + 8 叶：后序 = 叶(槽0..7)在前、根最后
        ref = np.array([1, 0, 0, 0, 0, 0, 0, 0, 0], dtype=np.uint8)
        flags = np.array([9, 1, 2, 3, 4, 5, 6, 7, 8], dtype=np.uint8)
        post = sctsnapshot.encode_octree_region_postorder(ref, flags)
        np.testing.assert_array_equal(post, [1, 2, 3, 4, 5, 6, 7, 8, 9])

    def test_encode_two_level(self):
        # 根内部；槽0子内部（其8叶=位2..9）；槽1..7叶=位10..16
        ref = np.zeros(17, dtype=np.uint8)
        ref[0] = ref[1] = 1
        flags = np.arange(17, dtype=np.uint8)
        post = sctsnapshot.encode_octree_region_postorder(ref, flags)
        expect = [2, 3, 4, 5, 6, 7, 8, 9, 1,
                  10, 11, 12, 13, 14, 15, 16, 0]
        np.testing.assert_array_equal(post, expect)

    def test_encode_pad_and_validation(self):
        ref = np.array([1] + [0] * 8, dtype=np.uint8)
        flags = np.zeros(9, dtype=np.uint8)
        post = sctsnapshot.encode_octree_region_postorder(
            ref, flags, pad_to=12)
        self.assertEqual(len(post), 12)
        self.assertEqual(int(post[8:].sum()), 0)  # 尾部零填充
        with self.assertRaises(ValueError):
            sctsnapshot.encode_octree_region_postorder(ref, flags[:5])
        with self.assertRaises(ValueError):
            sctsnapshot.encode_octree_region_postorder(ref, flags, pad_to=5)

    def test_encode_roundtrip_box(self):
        snap = sctsnapshot.SctSnapshot.load(str(BOX_SNAP))
        ref = snap.octree_refinement()
        self.assertIsNotNone(ref)
        reg = snap.octree_region(n_octants=len(ref))
        flags = snap.octree_region_as_oct_order(ref)
        post = sctsnapshot.encode_octree_region_postorder(
            ref, flags, pad_to=reg["raw_size"])
        raw = np.frombuffer(snap._octree_bytearray("OCTREEREGION"),
                            dtype=np.uint8)
        self.assertEqual(len(post), len(raw))
        np.testing.assert_array_equal(post, raw)

    def test_encode_roundtrip_laptop(self):
        snap = sctsnapshot.SctSnapshot.load(str(LAPTOP_SNAP))
        ref = snap.octree_refinement()
        self.assertIsNotNone(ref)
        reg = snap.octree_region(n_octants=len(ref))
        flags = snap.octree_region_as_oct_order(ref)
        post = sctsnapshot.encode_octree_region_postorder(
            ref, flags, pad_to=reg["raw_size"])
        raw = np.frombuffer(snap._octree_bytearray("OCTREEREGION"),
                            dtype=np.uint8)
        self.assertEqual(len(post), len(raw))
        np.testing.assert_array_equal(post, raw)

    @unittest.skipIf(sys.platform != "win32",
                     "LZMS 压缩写端需 Windows cabinet.dll")
    def test_lzms_compress_roundtrip(self):
        data = (b"The quick brown fox jumps over the lazy dog. " * 500)
        self.assertEqual(
            sctsnapshot.lzms_decompress(sctsnapshot.lzms_compress(data)),
            data)
        # 压缩流首部与宿主格式同构（magic + 头 24B）
        comp = sctsnapshot.lzms_compress(data)
        self.assertEqual(struct.unpack("<I", comp[:4])[0],
                         sctsnapshot.ZIP_MAGIC)

    @unittest.skipIf(sys.platform != "win32",
                     "LZMS 压缩写端需 Windows cabinet.dll")
    def test_update_octree_region_roundtrip_box(self):
        raw = BOX_SNAP.read_bytes()
        snap = sctsnapshot.SctSnapshot.load(str(BOX_SNAP))
        ref = snap.octree_refinement()
        flags0 = snap.octree_region_as_oct_order(ref)
        self.assertIsNotNone(flags0)
        flags1 = flags0.copy()
        flags1[:128] = 1          # 前 128 个前序节点全部激活
        self.assertTrue(snap.update_octree_region(flags1, ref))
        out = snap.serialize(raw)
        snap2 = sctsnapshot.SctSnapshot.from_bytes(out)
        flags2 = snap2.octree_region_as_oct_order(ref)
        self.assertIsNotNone(flags2)
        np.testing.assert_array_equal(flags2, flags1)
        # 其余记录未破坏：首个 LENGTHVWU 仍可解析
        vwu = next(snap2.find_all("LENGTHVWU"))
        self.assertIsInstance(vwu.value, sctsnapshot.ValueWithUnit)


if __name__ == "__main__":
    unittest.main()