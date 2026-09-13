"""P2-1 回归：voxmesh 八叉树子序必须等于 .oct / 宿主约定 (x + 2y + 4z)。

背景（2026-09-13 审计 §6 P0）：`voxmesh._OctNode.split` 此前以 x 外层、z 内层
生成子表（slot = 4x+2y+z，z 最快），而 `.oct` / 快照 / `oct.parse_oct` 的约定是
**x 最快**（`slot = x + 2y + 4z`）。非对称树写出的前序位图会被解读成另一棵树
（实测 L-shape 127/155 叶子落错包围盒，且叶子集合本身不同）。原测试只断言叶子
**数量**，故 CI 全绿却掩盖了该缺陷。本文件按**叶子集合恒等**锁定。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import oct as octmod  # noqa: E402
import voxmesh  # noqa: E402


def _refine(root: "voxmesh._OctNode", index: int) -> None:
    root.split()
    root.children[index].split()


def _bitmap_and_leaves(root):
    bits: list[int] = []
    leaves: set = set()

    def walk(n) -> None:
        if n.children is None:
            bits.append(0)
            leaves.add((tuple(np.round(n.box_min, 6)),
                        tuple(np.round(n.box_max, 6))))
            return
        bits.append(1)
        for c in n.children:
            walk(c)

    walk(root)
    return bits, leaves


class TestOctChildOrder(unittest.TestCase):
    def test_child_index_is_x_plus_2y_plus_4z(self):
        """子表下标 == x + 2y + 4z（x 最快）。"""
        root = voxmesh._OctNode(np.zeros(3), 1.0, 0)
        root.split()
        self.assertEqual(len(root.children), 8)
        for idx, child in enumerate(root.children):
            x, y, z = idx & 1, (idx >> 1) & 1, (idx >> 2) & 1
            expect = np.array([x, y, z], dtype=float) * 0.5
            np.testing.assert_allclose(child.box_min, expect, atol=1e-12)

    def test_asymmetric_tree_roundtrip_leaf_set_identical(self):
        """非对称树写 .oct 再读回，叶子集合必须逐个恒等（三种细分位置）。"""
        for index in (1, 4, 7):
            with self.subTest(refined_child=index):
                root = voxmesh._OctNode(np.zeros(3), 1.0, 0)
                _refine(root, index)
                bits, ref_leaves = _bitmap_and_leaves(root)
                with tempfile.TemporaryDirectory() as td:
                    p = Path(td) / "t.oct"
                    octmod.write_oct(p, root.box_min, root.box_max,
                                     refinement=np.array(bits, dtype=np.uint8),
                                     unit="m")
                    m = octmod.parse_oct(p)
                parsed = set()
                for lo, hi, *_rest in m.iter_leaves():
                    parsed.add((tuple(np.round(np.asarray(lo, dtype=float), 6)),
                                tuple(np.round(np.asarray(hi, dtype=float), 6))))
                self.assertEqual(len(ref_leaves), len(parsed))
                self.assertEqual(ref_leaves, parsed)

    def test_deep_asymmetric_tree_roundtrip(self):
        """两层非对称细化（16 子块中挑一块再分）同样恒等。"""
        root = voxmesh._OctNode(np.zeros(3), 1.0, 0)
        root.split()
        root.children[2].split()          # x0 y1 z0
        root.children[2].children[5].split()
        bits, ref_leaves = _bitmap_and_leaves(root)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t2.oct"
            octmod.write_oct(p, root.box_min, root.box_max,
                             refinement=np.array(bits, dtype=np.uint8), unit="m")
            m = octmod.parse_oct(p)
        parsed = set()
        for lo, hi, *_rest in m.iter_leaves():
            parsed.add((tuple(np.round(np.asarray(lo, dtype=float), 6)),
                        tuple(np.round(np.asarray(hi, dtype=float), 6))))
        self.assertEqual(ref_leaves, parsed)


class TestContainerHeader(unittest.TestCase):
    """P2-3 回归：CRDL-FLD 容器头 = [I4=8][MAGIC][I4=8][I4][I4][I4]。"""

    def _header(self, path: Path) -> bytes:
        return path.read_bytes()[:28]

    def test_gph_oct_mdl_headers_match_native_layout(self):
        import gphstats
        import mdl

        expect_prefix = bytes.fromhex("00000008") + b"CRDL-FLD" + \
            bytes.fromhex("0000000800000004000000040000000400000020")
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            verts = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
                             dtype=float)
            faces = [np.array([0, 1, 2, 3])]
            g = td / "a.gph"
            gphstats.write_gph(g, verts, faces)
            o = td / "a.oct"
            octmod.write_oct(o, [0, 0, 0], [1, 1, 1], unit="m")
            m = td / "a.mdl"
            mdl.write_mdl(m, verts, faces)
            for p in (g, o, m):
                with self.subTest(name=p.name):
                    head = p.read_bytes()[:32]
                    self.assertEqual(head[:28], expect_prefix[:28])
                    self.assertEqual(head[28:32], bytes.fromhex("00000020"),
                                     "name-length I4(32) must follow the 4th "
                                     "header I4")


if __name__ == "__main__":
    unittest.main()
