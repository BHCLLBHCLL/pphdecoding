#!/usr/bin/env python3
"""P1: decode_brep 内核介导 B-rep 提取回归。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ps_facet2_nodes as psf  # noqa: E402

BOX_XT = ROOT / "tests" / "box" / "box.x_t"


class TestDecodeBrep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not psf.available():
            raise unittest.SkipTest("pskernel.dll not available")
        cls.brep = psf.decode_brep(BOX_XT.read_bytes())

    def test_topology_counts(self):
        self.assertEqual(len(self.brep["bodies"]), 5)
        self.assertEqual(len(self.brep["faces"]), 6)
        self.assertEqual(len(self.brep["edges"]), 16)
        self.assertEqual(len(self.brep["vertices"]), 16)

    def test_points_valid(self):
        pts = self.brep["points"]
        self.assertEqual(len(pts), len(self.brep["vertices"]))
        for p in pts:
            self.assertIsNotNone(p)
            self.assertEqual(len(p), 3)

    def test_face_surfaces_and_edge_curves(self):
        self.assertEqual(len(self.brep["face_surfaces"]), len(self.brep["faces"]))
        self.assertEqual(len(self.brep["edge_curves"]), len(self.brep["edges"]))
        self.assertTrue(all(s is not None for s in self.brep["face_surfaces"]))
        self.assertTrue(all(c is not None for c in self.brep["edge_curves"]))

    def test_classes(self):
        cls = self.brep["classes"]
        self.assertEqual(cls[self.brep["bodies"][0]], "body")
        self.assertEqual(cls[self.brep["faces"][0]], "face")
        self.assertEqual(cls[self.brep["edges"][0]], "edge")
        self.assertEqual(cls[self.brep["vertices"][0]], "vertex")
        self.assertEqual(cls[self.brep["face_surfaces"][0]], "surface")
        self.assertEqual(cls[self.brep["edge_curves"][0]], "curve")

    def test_extract_from_solid_block(self):
        sess = psf._get_session()
        body = sess.create_solid_block((1.0, 1.0, 1.0))
        brep = sess.extract_brep([body])
        self.assertEqual(len(brep["faces"]), 6)
        self.assertEqual(len(brep["edges"]), 12)
        self.assertEqual(len(brep["vertices"]), 8)

    def test_facet_crosscheck(self):
        # 对拍：B-rep 拓扑（PK_BODY_ask_*）↔ 分面（PK_TOPOL_facet_2），
        # 同一 box 实体：三角数 = 2×面数，分面角点数 = B-rep 顶点数。
        sess = psf._get_session()
        tags = sess.receive_xt(BOX_XT.read_bytes())
        solid = max(tags, key=lambda b: len(sess.body_faces(b) or []))
        n_faces = len(sess.body_faces(solid))
        verts = sess.body_vertices(solid)
        part = sess.facet2(solid)
        self.assertEqual(n_faces, 6)
        verts = [] if verts is None else list(verts)
        self.assertEqual(len(verts), 8)
        self.assertIsNotNone(part)
        self.assertEqual(len(part.triangles), 2 * n_faces)
        self.assertEqual(len(part.points), len(verts))


if __name__ == "__main__":
    unittest.main()
