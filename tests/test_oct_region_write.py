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
DISC_PPH = ROOT / "tests" / "box_disc.pph"


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


@unittest.skipUnless(DISC_PPH.is_file(), "box_disc.pph not present")
class TestDiscPphOctRegion(unittest.TestCase):
    """第二份真实几何：box_disc.pph 的 OCT + snapshot OCTREEREGION roundtrip。"""

    @classmethod
    def setUpClass(cls):
        import zipfile
        import tempfile
        cls._td = tempfile.TemporaryDirectory()
        td = Path(cls._td.name)
        with zipfile.ZipFile(DISC_PPH) as z:
            names = set(z.namelist())
            if "meshinggroup1.oct" not in names or "main.sctsnapshot" not in names:
                cls._td.cleanup()
                raise unittest.SkipTest("box_disc missing oct/snapshot")
            (td / "meshinggroup1.oct").write_bytes(z.read("meshinggroup1.oct"))
            (td / "main.sctsnapshot").write_bytes(z.read("main.sctsnapshot"))
        cls.model = octmod.parse_oct(str(td / "meshinggroup1.oct"))
        cls.snap = sctsnapshot.SctSnapshot.from_bytes(
            (td / "main.sctsnapshot").read_bytes())

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_disc_oct_has_leaves(self):
        self.assertGreater(self.model.n_leaves, 0)
        self.assertGreater(self.model.n_octants, 0)

    def test_disc_encode_region_postorder_roundtrip(self):
        flags_oct = self.snap.octree_region_as_oct_order(
            self.model.refinement)
        self.assertIsNotNone(flags_oct)
        post = sctsnapshot.encode_octree_region_postorder(
            self.model.refinement, flags_oct)
        reg = self.snap.octree_region(n_octants=self.model.n_octants)
        np.testing.assert_array_equal(post, reg["flags"])


class TestNativeLShapeOctree(unittest.TestCase):
    """非 box 几何：L 形表面 → 自研 octree 写出再读回。"""

    def test_write_read_l_shape_oct(self):
        import tempfile
        import voxmesh
        pts_a = np.array(
            [[x, y, z] for x in (0.0, 1.0) for y in (0.0, 1.0)
             for z in (0.0, 1.0)], dtype=float)
        pts_b = pts_a + np.array([1.0, 0.0, 0.0])
        faces = [
            [0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1],
            [2, 3, 7, 6], [1, 5, 7, 3], [0, 2, 6, 4],
        ]
        pts = np.vstack([pts_a, pts_b])
        faces2 = [[i + 8 for i in f] for f in faces]
        points, tris = voxmesh.surface_from_mesh(pts, faces + faces2)
        root_min, root_max, refinement, leaves = voxmesh.build_octree(
            points, tris,
            voxmesh.VoxelMeshParams(initial_depth=2, max_depth=3,
                                    max_cells=50_000))
        self.assertGreater(len(leaves), 0)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "l.oct"
            octmod.write_oct(path, root_min, root_max, refinement, date=20260817)
            m = octmod.parse_oct(str(path))
        self.assertEqual(m.n_octants, len(refinement))
        self.assertGreater(m.n_leaves, 0)


if __name__ == "__main__":
    unittest.main()
