#!/usr/bin/env python3
"""gphstats.build_cells 单元重建与分类回归。

覆盖：单单元分类（hexa/tet/prism/pyramid/poly）、内部面共享的两单元重建、
真实 box 样例（936 hexa + 8 poly）。
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import gphstats  # noqa: E402

BOX_GPH = ROOT / "tests" / "box" / "meshinggroup1.gph"
BOUNDARY = 0xFFFFFFFF


class TestClassifyCell(unittest.TestCase):
    def test_hexahedron(self):
        self.assertEqual(gphstats.classify_cell([4, 4, 4, 4, 4, 4]),
                         gphstats.CELL_HEXAHEDRON)

    def test_tetrahedron(self):
        self.assertEqual(gphstats.classify_cell([3, 3, 3, 3]),
                         gphstats.CELL_TETRAHEDRON)

    def test_prism(self):
        self.assertEqual(gphstats.classify_cell([3, 3, 4, 4, 4]),
                         gphstats.CELL_PRISM)

    def test_pyramid(self):
        self.assertEqual(gphstats.classify_cell([3, 3, 3, 3, 4]),
                         gphstats.CELL_PYRAMID)

    def test_polyhedral(self):
        self.assertEqual(gphstats.classify_cell([4, 4, 4, 4, 4, 5]),
                         gphstats.CELL_POLYHEDRAL)


class TestBuildCells(unittest.TestCase):
    def test_single_isolated_hexa(self):
        owner = np.zeros(6, dtype=np.int64)
        neigh = np.full(6, BOUNDARY, dtype=np.int64)
        npe = np.full(6, 4, dtype=np.int64)
        cm = gphstats.build_cells(owner, neigh, npe)
        self.assertEqual(cm["n_cells"], 1)
        self.assertEqual(cm["type_histogram"], {"hexahedron": 1})
        self.assertEqual(cm["cell_face_counts"].tolist(), [6])

    def test_two_hexa_share_internal_face(self):
        # 两个六面体共用一个内部面：共 11 面；面 10 为内部面（owner=0, neigh=1）
        n = 11
        owner = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 0], dtype=np.int64)
        neigh = np.array([BOUNDARY] * 5 + [BOUNDARY] * 5 + [1],
                         dtype=np.int64)
        npe = np.full(n, 4, dtype=np.int64)
        cm = gphstats.build_cells(owner, neigh, npe)
        self.assertEqual(cm["n_cells"], 2)
        self.assertEqual(cm["type_histogram"], {"hexahedron": 2})
        self.assertEqual(cm["cell_face_counts"].tolist(), [6, 6])

    def test_box_hex_dominant(self):
        with gphstats.open_buffer(str(BOX_GPH)) as data:
            mesh = gphstats.parse_mesh(data)
            cells2 = gphstats.gph_cells(data)
        cm = gphstats.build_cells(mesh["owner"], mesh["neigh"], mesh["npe"])
        self.assertEqual(cm["n_cells"], 944)
        self.assertEqual(cm["type_histogram"],
                         {"hexahedron": 936, "polyhedral": 8})
        types = np.array(cm["cell_types"])
        self.assertTrue(np.all(
            cm["cell_face_counts"][types == "hexahedron"] == 6))
        # gph_cells 便捷入口与直接重建一致
        self.assertEqual(cells2["type_histogram"], cm["type_histogram"])


if __name__ == "__main__":
    unittest.main()