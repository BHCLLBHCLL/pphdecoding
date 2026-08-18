#!/usr/bin/env python3
"""Octree/GPH 例程黄金回归（vs D:\\training\\cradle 官方工程，盘上黄金）。

三档规模对拍（P8-1 黄金扩容）：

- interference：21k 叶子 / 28.5k cells（hex 97%，干涉真实几何）；
- tr03（Overset）：31.5k 叶子 / 63.9k cells（polyhedral 92%，旋转机械）；
- laptop_simplified：1.24M 叶子（division 位图满树不变量 + region
  后序流规模一致性；GPH 349MB 不在测试中整读）。

另含 ``gphstats._sections_cache`` id 复用脏缓存回归（P8-1 修复：
同进程先后解析两个 GPH，第二个曾返回 0 cells）。

例程库缺失时全部跳过（非本机黄金环境）。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import gphstats  # noqa: E402
import sctsnapshot  # noqa: E402
from gphstats import gph_cells, parse_mesh  # noqa: E402

CRADLE = Path(os.environ.get("PPH_CRADLE_ROOT", r"D:\training\cradle"))
_HAVE = CRADLE.is_dir()


def _snapshot(path: Path) -> sctsnapshot.SctSnapshot:
    with zipfile.ZipFile(path) as z:
        tmp = tempfile.NamedTemporaryFile(delete=False,
                                          suffix=".sctsnapshot")
        tmp.write(z.read("main.sctsnapshot"))
        tmp.close()
    return sctsnapshot.SctSnapshot.load(tmp.name)


def _octree_facts(path: Path) -> dict:
    snap = _snapshot(path)
    bits = snap.octree_division_bits()
    region = snap.octree_region()
    internal = int(bits.sum())
    n_octants = 1 + 8 * internal
    return {
        "n_octants": n_octants,
        "n_internal": internal,
        # 满八叉树不变量：n = 1 + 8 * n_internal；位图 unpack 后长度
        # 为 8*ceil(n/8)，尾部填充位 ∈ [0,7]（零位，非真实叶子）
        "full_tree": 0 <= int(bits.size) - n_octants <= 7,
        "n_active": region["n_active"] if region else 0,
        "region_padding": region["padding"] if region else -1,
    }


@unittest.skipUnless(_HAVE, f"cradle example root missing: {CRADLE}")
class TestInterferenceGolden(unittest.TestCase):
    """interference：中型真实几何（hex 主导）。"""

    @classmethod
    def setUpClass(cls):
        cls.cells = gph_cells(
            (CRADLE / "interference" / "interference.gph").read_bytes())
        cls.oct = _octree_facts(CRADLE / "interference" / "interference.pph")

    def test_octree_scale(self):
        self.assertTrue(self.oct["full_tree"])
        self.assertGreater(self.oct["n_active"], 20_000)
        self.assertLess(self.oct["n_active"], 22_000)

    def test_gph_cells_hex_dominant(self):
        hist = self.cells["type_histogram"]
        total = sum(hist.values())
        self.assertGreater(total, 28_000)
        self.assertLess(total, 29_000)
        self.assertGreater(hist.get("hexahedron", 0) / total, 0.95)


@unittest.skipUnless(_HAVE, f"cradle example root missing: {CRADLE}")
class TestTr03OversetGolden(unittest.TestCase):
    """tr03：旋转机械 + Overset（polyhedral 主导）。"""

    @classmethod
    def setUpClass(cls):
        cls.cells = gph_cells((CRADLE / "tr03" / "tr03" / "tr03.gph").read_bytes())
        cls.oct = _octree_facts(CRADLE / "tr03" / "tr03" / "tr03.pph")

    def test_octree_scale(self):
        self.assertTrue(self.oct["full_tree"])
        self.assertGreater(self.oct["n_active"], 30_000)
        self.assertLess(self.oct["n_active"], 33_000)

    def test_gph_cells_polyhedral_dominant(self):
        hist = self.cells["type_histogram"]
        total = sum(hist.values())
        self.assertGreater(total, 63_000)
        self.assertLess(total, 65_000)
        self.assertGreater(hist.get("polyhedral", 0) / total, 0.90)


@unittest.skipUnless(_HAVE, f"cradle example root missing: {CRADLE}")
class TestLaptopScale(unittest.TestCase):
    """laptop_simplified：1.24M 叶子规模（division/region 一致性，不整读 349MB GPH）。"""

    @classmethod
    def setUpClass(cls):
        cls.oct = _octree_facts(
            CRADLE / "laptop" / "laptop" / "laptop_simplified.pph")

    def test_division_full_tree_invariant_at_scale(self):
        # 满八叉树不变量在 1.4M+ octants 上成立（位图重放无孤儿节点）
        self.assertTrue(self.oct["full_tree"])
        self.assertGreater(self.oct["n_octants"], 1_300_000)

    def test_region_active_leaves_at_scale(self):
        # 激活叶子（region flag=1）≈ 1.24M，且不超过叶子总数
        n_leaves = self.oct["n_octants"] - self.oct["n_internal"]
        self.assertGreater(self.oct["n_active"], 1_200_000)
        self.assertLessEqual(self.oct["n_active"], n_leaves)


class TestGphCacheFingerprint(unittest.TestCase):
    """_sections_cache id 复用脏缓存回归（本地 GPH，无需例程库）。

    旧实现按 ``id(data)`` 键控且公开 API（``gph_cells(bytes)``）无
    清理路径：buffer A 被 GC 后 buffer B 复用同 id → 命中 A 的节表
    → B 解析出 0 cells。指纹守卫必须检测并重扫。
    """

    GPH = ROOT / "tests" / "box" / "meshinggroup1.gph"

    @classmethod
    def setUpClass(cls):
        cls.data = cls.GPH.read_bytes()
        cls.mesh = parse_mesh(cls.data)
        cls.n_cells_ref = int(cls.mesh["owner"].max()) + 1

    def test_stale_cache_entry_detected(self):
        # 毒化：在 data 的 id 下塞入「另一个 buffer 的节表 + 错误指纹」
        other = b"\x00" * 64 + self.data[64:128]  # 内容不同的同长 buffer
        stale_secs = gphstats._all_sections(other)
        gphstats._sections_cache[id(self.data)] = (
            stale_secs, gphstats._buffer_fingerprint(other))
        try:
            mesh = parse_mesh(self.data)
            self.assertEqual(int(mesh["owner"].max()) + 1,
                             self.n_cells_ref)
        finally:
            gphstats._sections_cache.pop(id(self.data), None)

    def test_same_content_cache_hit_is_safe(self):
        # 同内容不同对象：指纹相同 → 命中无害（scan_sections 是纯函数）
        twin = bytes(self.data)
        m1 = parse_mesh(self.data)
        m2 = parse_mesh(twin)
        self.assertEqual(m1["n_faces"], m2["n_faces"])


if __name__ == "__main__":
    unittest.main()
