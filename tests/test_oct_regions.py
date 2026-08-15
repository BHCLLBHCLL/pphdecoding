#!/usr/bin/env python3
"""oct 分区/区域对齐/单元链路（O1-O3）回归。"""

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


class TestOctRegions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = octmod.parse_oct(str(BOX_OCT))
        cls.snap = sctsnapshot.SctSnapshot.from_bytes(
            BOX_SNAP.read_bytes())

    def test_block_partition_unpartitioned(self):
        bp = self.model.block_partition()
        self.assertFalse(bp["partitioned"])
        self.assertEqual(bp["n_blocks"], 0)
        self.assertEqual(bp["n_octants"], self.model.n_octants)

    def test_region_map_aligns(self):
        rm = octmod.oct_region_map(self.snap, self.model)
        self.assertEqual(rm["n_leaves"], 1968)
        self.assertEqual(rm["n_active"], 883)
        lo, hi = rm["active_bbox"]
        # 活跃区域集中在 y∈[0,0.011] 上半精化板（DEV_PLAN 已钉死）
        self.assertAlmostEqual(lo[1], 0.0, delta=1e-6)
        self.assertAlmostEqual(hi[1], 0.011, delta=1e-6)

    def test_region_map_flags_aligned(self):
        rm = octmod.oct_region_map(self.snap, self.model)
        flags = rm["flags"]
        self.assertEqual(flags.size, self.model.n_octants)
        self.assertEqual(int(flags.sum()), 883)

    def test_cell_mask(self):
        lo, hi = octmod.oct_region_map(self.snap, self.model)["active_bbox"]
        centroids = np.array([
            [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2],
            [100.0, 100.0, 100.0],  # 远处，应排除
        ])
        mask = octmod.oct_cell_mask(self.model, self.snap, centroids)
        self.assertTrue(mask[0])
        self.assertFalse(mask[1])


if __name__ == "__main__":
    unittest.main()
