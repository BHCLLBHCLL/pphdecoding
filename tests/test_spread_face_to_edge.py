#!/usr/bin/env python3
"""Wave E：Spread Selected Face to Selected Edge 对偶邻接扩散。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mdl  # noqa: E402


def _quad_strip(n_faces: int = 4) -> mdl.MdlModel:
    """一行 n 个四边形：面 i 与 i+1 共享边 (i+1, i+1+n_faces+1)。"""
    n_verts = 2 * (n_faces + 1)
    xyz = np.array(
        [[float(i), 0.0, 0.0] for i in range(n_faces + 1)]
        + [[float(i), 1.0, 0.0] for i in range(n_faces + 1)],
        dtype=np.float64,
    )
    conn = []
    for i in range(n_faces):
        lo0, lo1 = i, i + 1
        hi0, hi1 = i + n_faces + 1, i + 1 + n_faces + 1
        conn.extend([lo0, lo1, hi1, hi0])
    conn = np.asarray(conn, dtype=np.int32)
    n = n_faces
    zeros = np.zeros(n, dtype=np.int32)
    return mdl.MdlModel(
        n_vertices=n_verts,
        n_faces=n,
        xyz=xyz,
        face_type=np.full(n, 134, dtype=np.int32),
        conn=conn,
        csid=(zeros.copy(), np.ones(n, dtype=np.int32)),
        frid=zeros.copy(),
        edge_state=np.ones(len(conn), dtype=np.uint8),
        node_state=np.zeros(n_verts, dtype=np.int32),
        closed_volumes=["", "body"],
        volume_regions=[],
        surface_regions=[],
    )


class TestSpreadFacesToSelectedEdge(unittest.TestCase):
    def test_stop_edge_cuts_strip(self):
        model = _quad_strip(4)
        # 面 1 与面 2 共享边 (2, 7)：下排顶点 0..4，上排 5..9
        stop = [(2, 7)]
        got = mdl.spread_faces_to_selected_edge(model, [0], stop)
        self.assertEqual(got, [0, 1])
        got_r = mdl.spread_faces_to_selected_edge(model, [3], stop)
        self.assertEqual(got_r, [2, 3])

    def test_no_stop_fills_component(self):
        model = _quad_strip(4)
        got = mdl.spread_faces_to_selected_edge(model, [1], [])
        self.assertEqual(got, [0, 1, 2, 3])

    def test_empty_seeds(self):
        model = _quad_strip(3)
        self.assertEqual(mdl.spread_faces_to_selected_edge(model, [], [(1, 5)]), [])

    def test_out_of_range_seeds_ignored(self):
        model = _quad_strip(2)
        self.assertEqual(mdl.spread_faces_to_selected_edge(model, [-1, 99], None), [])

    def test_gui_slot_wired(self):
        src = (ROOT / "pph_gui.py").read_text(encoding="utf-8")
        self.assertIn("def _spread_face_to_edge(self)", src)
        self.assertIn("self._spread_face_to_edge", src)
        self.assertIn("last_edge_pick", src)


if __name__ == "__main__":
    unittest.main()
