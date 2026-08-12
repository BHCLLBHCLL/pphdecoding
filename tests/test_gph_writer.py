#!/usr/bin/env python3
"""gphstats.write_gph 最小六面体 GPH 写端回归。"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import gphstats  # noqa: E402


class TestGphWriter(unittest.TestCase):
    def test_roundtrip_hexahedron(self):
        verts = np.array([
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
            [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
        ], dtype=float)
        faces = [
            [0, 1, 2, 3], [5, 4, 7, 6],
            [0, 4, 5, 1], [2, 3, 7, 6],
            [1, 5, 6, 2], [0, 3, 7, 4],
        ]
        with tempfile.TemporaryDirectory() as td:
            p = gphstats.write_gph(
                Path(td) / "hex.gph", verts, faces)
            mesh = gphstats.parse_mesh(p.read_bytes())
        self.assertEqual(mesh["n_faces"], 6)
        self.assertEqual(len(mesh["vertices"]), 8)
        self.assertTrue(np.all(mesh["npe"] == 4))
        self.assertEqual(len(mesh["conn"]), 24)
        self.assertTrue(np.all(mesh["boundary_mask"]))


if __name__ == "__main__":
    unittest.main()
