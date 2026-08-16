#!/usr/bin/env python3
"""Octree OCTREEREGION 写端 roundtrip 回归。

补齐 Octree 域「表面接线、深层缺验证」的短板：``OCTREEREGION`` 后序写端
（:func:`sctsnapshot.encode_octree_region_postorder` 与
:meth:`SctSnapshot.update_octree_region`）在 P3-2 已实现但无测试锁定，
本文件验证「前序 → 后序 → 前序」严格互逆与「写回 → 重读」一致。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import oct as octmod  # noqa: E402
import sctsnapshot  # noqa: E402

BOX_OCT = ROOT / "tests" / "box" / "meshinggroup1.oct"
BOX_SNAP = ROOT / "tests" / "box" / "main.sctsnapshot"


class TestEncodeRegionPostorder(unittest.TestCase):
    """前序 → 后序写端与后序 → 前序读端严格互逆（纯逻辑，无 LZMS）。"""

    @classmethod
    def setUpClass(cls):
        if not (BOX_OCT.is_file() and BOX_SNAP.is_file()):
            raise unittest.SkipTest("box oct/snapshot not present")
        cls.model = octmod.parse_oct(str(BOX_OCT))
        cls.snap = sctsnapshot.SctSnapshot.from_bytes(BOX_SNAP.read_bytes())

    def test_encode_region_postorder_is_inverse_of_decode(self):
        flags_oct = self.snap.octree_region_as_oct_order(
            self.model.refinement)
        self.assertIsNotNone(flags_oct)
        post = sctsnapshot.encode_octree_region_postorder(
            self.model.refinement, flags_oct)
        reg = self.snap.octree_region(n_octants=self.model.n_octants)
        # 编码回后序后应与快照原始后序字节一致
        np.testing.assert_array_equal(post, reg["flags"])

    def test_encode_rejects_length_mismatch(self):
        with self.assertRaises(ValueError):
            sctsnapshot.encode_octree_region_postorder(
                self.model.refinement, np.zeros(1, dtype=np.uint8))


class TestUpdateOctreeRegion(unittest.TestCase):
    """写回 ZIPOCTREE 后重读一致（需 Windows cabinet.dll LZMS）。"""

    @classmethod
    def setUpClass(cls):
        if not sctsnapshot.lzms_available():
            raise unittest.SkipTest("LZMS (cabinet.dll) unavailable")
        if not (BOX_OCT.is_file() and BOX_SNAP.is_file()):
            raise unittest.SkipTest("box oct/snapshot not present")
        cls.model = octmod.parse_oct(str(BOX_OCT))
        cls.snap = sctsnapshot.SctSnapshot.from_bytes(BOX_SNAP.read_bytes())

    def test_update_octree_region_roundtrip(self):
        original = BOX_SNAP.read_bytes()
        flags_oct = self.snap.octree_region_as_oct_order(
            self.model.refinement).copy()
        flags_oct[0] ^= 1  # 翻转首 octant 区域标志
        self.assertTrue(self.snap.update_octree_region(flags_oct))
        new_bytes = self.snap.serialize(original_data=original)
        snap2 = sctsnapshot.SctSnapshot.from_bytes(new_bytes)
        flags2 = snap2.octree_region_as_oct_order(self.model.refinement)
        np.testing.assert_array_equal(flags2, flags_oct)


if __name__ == "__main__":
    unittest.main()
