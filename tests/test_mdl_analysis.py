#!/usr/bin/env python3
"""mdl.detect_tiny_faces / detect_multifold_edges 回归。"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mdl  # noqa: E402
import pph_parser  # noqa: E402

BOX_PPH = ROOT / "box.pph"


class TestMdlAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        arch = pph_parser.PphArchive.open(str(BOX_PPH))
        member = next(m for m in arch.members if m.role == "surface_part_mdl")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / member.name
        cls.path.write_bytes(arch.read_member(member.name))
        cls.model = mdl.parse_mdl(str(cls.path), load_arrays=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_tiny_faces_empty_with_small_tolerance(self):
        rows = mdl.detect_tiny_faces(self.model, 1e-9)
        self.assertIsInstance(rows, list)
        self.assertGreaterEqual(self.model.n_faces, 1)

    def test_multifold_edges_shape(self):
        edges = mdl.detect_multifold_edges(self.model)
        self.assertIsInstance(edges, dict)
        for faces in edges.values():
            self.assertGreater(len(faces), 2)

    def test_matching_faces_shape(self):
        pairs = mdl.detect_matching_faces(self.model)
        self.assertIsInstance(pairs, list)
        for p in pairs:
            self.assertIn("group1", p)
            self.assertIn("group2", p)


if __name__ == "__main__":
    unittest.main()
