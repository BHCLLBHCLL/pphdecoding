"""3.2 语义钉死：CsidOfFaces 双侧闭体、OCTREEREGION 交叉验证、PKBody3 尾标/pad。"""

import os
import struct
import tempfile
import unittest
import zipfile
import zlib

import numpy as np

import mdl
import oct
import sctsnapshot


BOX_SNAP = r"tests\box\main.sctsnapshot"
BOX_OCT = r"tests\box\meshinggroup1.oct"
BOX_PART = r"tests\box\meshinggroup1_part.mdl"
LAPTOP_PPH = r"tests\laptop_thermal_steady_scaled_v3_fanonly_simple.pph"
LAPTOP_OCT = r"tests\laptop_thermal_steady_scaled_v3_fanonly_simple\meshinggroup1.oct"
LAPTOP_PART = r"tests\laptop_thermal_steady_scaled_v3_fanonly_simple\meshinggroup1_part.mdl"
LAPTOP_RIDGE = r"tests\laptop_thermal_steady_scaled_v3_fanonly_simple\meshinggroup1_ridge.mdl"

# 注意：根目录 box.pph 已于 2026-08-13 提交（0336d7d）刷新为内部八叉树
# 20105 节点的新样本，而 tests/box/ 下的 .oct/.mdl 仍是原 2249 节点保存。
# OCTREEREGION 交叉验证必须用同一保存的三件套，故 box 侧固定取
# tests/box/main.sctsnapshot（与 .oct/.mdl 同源）。


def _load_snap(path: str) -> sctsnapshot.SctSnapshot:
    """支持 .pph（zip 容器）与裸 main.sctsnapshot 两种输入。"""
    if path.lower().endswith(".pph"):
        with zipfile.ZipFile(path) as z:
            raw = z.read("main.sctsnapshot")
        tmp = os.path.join(tempfile.gettempdir(), "snap_semantics.bin")
        with open(tmp, "wb") as f:
            f.write(raw)
        return sctsnapshot.SctSnapshot.load(tmp)
    return sctsnapshot.SctSnapshot.load(path)


class TestCsidOfFacesDualSide(unittest.TestCase):
    """``LS_CsidOfFaces`` = (volA, volB)，0=外部，b2 = frid+1。"""

    def test_box_part_single_closed_body(self):
        m = mdl.parse_mdl(BOX_PART)
        b1, b2 = m.csid
        self.assertEqual(int(b1.min()), 0)
        self.assertEqual(int(b1.max()), 0)
        self.assertEqual(int(b2.min()), 1)
        self.assertEqual(int(b2.max()), 1)
        self.assertEqual(m.n_closed_volumes, 1)
        # LS_MdlClosedVolumes 记录数 = 闭体数 + 1（索引 0 = 外部）
        self.assertEqual(len(m.closed_volumes), 2)

    def test_laptop_part_b2_equals_frid_plus_one(self):
        m = mdl.parse_mdl(LAPTOP_PART)
        b1, b2 = m.csid
        self.assertEqual(int(b1.max()), 0)  # part 面全为边界面
        self.assertEqual(set(np.unique(b2).tolist()), {1, 2, 3, 4})
        self.assertEqual(m.n_closed_volumes, 4)
        self.assertEqual(len(m.closed_volumes), 5)
        # frid × b2 精确一一对应：frid+1 = b2
        cross = {}
        for f, b in zip(m.frid, b2):
            cross[(int(f), int(b))] = cross.get((int(f), int(b)), 0) + 1
        self.assertEqual(set(cross), {(0, 1), (1, 2), (2, 3), (3, 4)})

    def test_laptop_ridge_interface_faces(self):
        m = mdl.parse_mdl(LAPTOP_RIDGE)
        b1, b2 = m.csid
        # 体间界面：两侧均非零（body2/body1 界面 (2,1) 有 412,644 面）
        interface = (b1 > 0) & (b2 > 0)
        self.assertGreater(int(interface.sum()), 400_000)
        pairs, counts = np.unique(np.column_stack([b1, b2]), axis=0,
                                  return_counts=True)
        pair_map = {tuple(map(int, p)): int(c) for p, c in zip(pairs, counts)}
        self.assertEqual(pair_map[(2, 1)], 412644)
        self.assertEqual(set(pair_map), {(0, 1), (0, 2), (2, 1)})
        self.assertEqual(m.n_closed_volumes, 2)
        self.assertEqual(len(m.closed_volumes), 3)


class TestOctreeRegionSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.box_snap = _load_snap(BOX_SNAP)
        cls.box_oct = oct.parse_oct(BOX_OCT)
        cls.laptop_snap = _load_snap(LAPTOP_PPH)
        cls.laptop_oct = oct.parse_oct(LAPTOP_OCT)

    def test_box_restrict_regions_all_empty(self):
        self.assertEqual(self.box_snap.octree_restrict_regions(), [])

    def test_laptop_restrict_region_indices_match_mdl(self):
        regions = self.laptop_snap.octree_restrict_regions()
        self.assertEqual(
            [(r["name"], r["index"], r["kind"]) for r in regions],
            [("open", 0, 0), ("case1", 1, 2),
             ("rotation1", 2, 2), ("impeller1", 3, 2)])
        m = mdl.parse_mdl(LAPTOP_PART)
        mdl_idx = {r.name: r.index for r in m.surface_regions}
        for r in regions:
            self.assertEqual(r["index"], mdl_idx[r["name"]])
            # csid 侧：b2 = region index + 1
            self.assertIn(r["index"] + 1, np.unique(m.csid[1]))

    def test_box_region_flags_all_leaves_in_deepest_levels(self):
        ref = self.box_oct.refinement
        flags = self.box_snap.octree_region_as_oct_order(ref)
        self.assertEqual(len(flags), len(ref))
        # flag=1 全部是叶子
        self.assertEqual(int(((flags == 1) & (ref == 1)).sum()), 0)
        leaves = list(self.box_oct.iter_leaves())
        leaf_flags = flags[ref == 0]
        depth_flag = {}
        for (_, _, d), fl in zip(leaves, leaf_flags):
            depth_flag[int(d)] = depth_flag.get(int(d), 0) + int(fl)
        # 只有最深两层被标记
        self.assertEqual({d: c for d, c in depth_flag.items() if c},
                         {4: 64, 5: 819})
        flagged = np.array([
            [mn[0], mn[1], mn[2], mx[0], mx[1], mx[2], d]
            for (mn, mx, d), fl in zip(leaves, leaf_flags) if fl])
        # 全部位于根包围盒 y 上半区（精化板）
        self.assertGreaterEqual(flagged[:, 1].min(), 0.0)
        self.assertEqual(flagged.shape[0], 883)

    def test_laptop_region_flags_all_leaves_in_rotor_column(self):
        ref = self.laptop_oct.refinement
        flags = self.laptop_snap.octree_region_as_oct_order(ref)
        self.assertEqual(int(((flags == 1) & (ref == 1)).sum()), 0)
        self.assertEqual(int(flags.sum()), 3445907)
        leaves = self.laptop_oct.iter_leaves()
        flagged_min = np.full(3, np.inf)
        flagged_max = np.full(3, -np.inf)
        flagged = 0
        for (mn, mx, _), fl in zip(leaves, flags[ref == 0]):
            if fl:
                flagged += 1
                flagged_min = np.minimum(flagged_min, np.array(mn))
                flagged_max = np.maximum(flagged_max, np.array(mx))
        self.assertEqual(flagged, 3445907)
        # 转子薄柱（与 OCTREERESTRRGN rotation1/impeller1 对应）
        self.assertTrue(-54.5 < flagged_min[0] < -54.4)
        self.assertTrue(-51.8 < flagged_max[0] < -51.7)
        self.assertTrue(4.9 < flagged_min[1] < 5.0)
        self.assertTrue(5.4 < flagged_max[1] < 5.5)
        self.assertTrue(-0.3 < flagged_min[2] < -0.2)
        self.assertTrue(0.2 < flagged_max[2] < 0.3)


class TestPKBody3TrailerPad(unittest.TestCase):
    """PKBody3 "尾标" 0x17DA2940 实为 E(0^8) 的低 32 位（零填充块密文）。"""

    @classmethod
    def setUpClass(cls):
        cls.box_snap = _load_snap(BOX_SNAP)
        cls.laptop_snap = _load_snap(LAPTOP_PPH)

    def test_trailer_is_zero_padding_block_artifact(self):
        bodies = [self.box_snap.bodies()[0]["zip"].decompress_body()]
        bodies += [b["zip"].decompress_body()
                   for b in self.laptop_snap.bodies()]
        with_trailer = [b for b in bodies if b.checksum is not None]
        # 带"尾标"的体 = 逻辑长度非 8 倍数（存在零填充块）
        self.assertEqual([b.logical_size % 8 for b in with_trailer],
                         [3, 4, 4])
        # 两个 8 倍数长度的体无"尾标"
        without = [b for b in bodies if b.checksum is None]
        self.assertEqual(sorted(b.logical_size for b in without), [3040, 7824])
        # 每个带"尾标"的体，最后一个密文块 == 固定密钥下的 E(0^8)
        import blowfish_le
        e0 = blowfish_le.encrypt_ecb(b"\x00" * 8)
        for b in with_trailer:
            self.assertEqual(b.data[-8:], e0)
        # box 的 pad 是零填充块密文碎片（0xB1 = E(0) 第 3 字节）
        box_body = bodies[0]
        self.assertEqual(box_body.pad, e0[3:4])

    def test_trailer_not_content_checksum(self):
        import blowfish_le

        body = self.box_snap.bodies()[0]["zip"].decompress_body()
        mark = sctsnapshot.PKBODY3_TRAILER_MARK
        self.assertNotEqual(zlib.crc32(body.data) & 0xFFFFFFFF, mark)
        self.assertNotEqual(zlib.adler32(body.data) & 0xFFFFFFFF, mark)
        # 尾标是固定密钥下 E(0) 的低 32 位，与明文内容无关
        self.assertEqual(blowfish_le.encrypt_ecb(b"\x00" * 8)[-4:],
                         struct.pack("<I", mark))


if __name__ == "__main__":
    unittest.main()
