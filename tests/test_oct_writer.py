#!/usr/bin/env python3
"""oct.write_oct 最小八叉树写端回归。"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import oct  # noqa: E402


class TestOctWriter(unittest.TestCase):
    def test_roundtrip_single_leaf(self):
        with tempfile.TemporaryDirectory() as td:
            p = oct.write_oct(
                Path(td) / "leaf.oct",
                [0, 0, 0], [1, 1, 1])
            model = oct.parse_oct(str(p))
        self.assertEqual(model.n_octants, 1)
        self.assertEqual(model.n_leaves, 1)
        np.testing.assert_allclose(model.root_min, [0, 0, 0])
        np.testing.assert_allclose(model.root_max, [1, 1, 1])
        leaves = list(model.iter_leaves())
        self.assertEqual(len(leaves), 1)

    def test_roundtrip_uniform_subdivision(self):
        ref = np.array([1, 0, 0, 0, 0, 0, 0, 0, 0], dtype=np.uint8)
        with tempfile.TemporaryDirectory() as td:
            p = oct.write_oct(
                Path(td) / "sub.oct",
                [0, 0, 0], [2, 2, 2], refinement=ref)
            model = oct.parse_oct(str(p))
        self.assertEqual(model.n_octants, 9)
        self.assertEqual(model.n_internal, 1)
        self.assertEqual(model.n_leaves, 8)
        self.assertEqual(len(list(model.iter_leaves())), 8)


if __name__ == "__main__":
    unittest.main()
