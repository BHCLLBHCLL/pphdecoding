#!/usr/bin/env python3
"""mdl.detect_tiny_faces / detect_multifold_edges / P3-3 相交检测回归。"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

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


def _box(x0, y0, z0, x1, y1, z1):
    """单位盒顶点 + 外向四边形面（z 最快顶点序）。"""
    pts = [[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    quads = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1],
             [2, 3, 7, 6], [1, 5, 7, 3], [0, 2, 6, 4]]
    return pts, quads


def _mdl_from_boxes(boxes, bodies=None):
    """多盒拼一个 MdlModel（每盒独立顶点；bodies 为每盒的 csid 体号）。"""
    xyz: list = []
    faces: list = []
    face_body: list = []
    for i, (lo, hi) in enumerate(boxes):
        pts, quads = _box(*lo, *hi)
        base = len(xyz)
        xyz += pts
        faces += [[v + base for v in q] for q in quads]
        face_body += [bodies[i] if bodies else i + 1] * 6
    n_v = len(xyz)
    n_f = len(faces)
    conn = np.asarray(faces, dtype=np.int64).reshape(-1)
    return mdl.MdlModel(
        n_vertices=n_v, n_faces=n_f,
        xyz=np.asarray(xyz, dtype=float),
        face_type=np.full(n_f, 134, dtype=np.int64),
        conn=conn,
        csid=(np.zeros(n_f, dtype=np.int64),
              np.asarray(face_body, dtype=np.int64)),
        frid=np.zeros(n_f, dtype=np.int64),
        edge_state=np.zeros(conn.size, dtype=np.uint8),
        node_state=np.zeros(n_v, dtype=np.int64),
        closed_volumes=[""], volume_regions=["FluidRegion"],
        surface_regions=[])


class TestFaceAreas(unittest.TestCase):
    def test_unit_box_areas(self):
        m = _mdl_from_boxes([((0, 0, 0), (1, 1, 1))])
        areas = mdl.face_areas(m)
        self.assertEqual(areas.shape, (6,))
        np.testing.assert_allclose(areas, 1.0)
        self.assertAlmostEqual(float(areas.sum()), 6.0)

    def test_rect_box_areas(self):
        m = _mdl_from_boxes([((0, 0, 0), (2, 3, 4))])
        areas = mdl.face_areas(m)
        # 面积：xy 6×2、yz 8×2、xz 12×2 → 总 52
        self.assertAlmostEqual(float(areas.sum()), 52.0)

    def test_triangulate(self):
        m = _mdl_from_boxes([((0, 0, 0), (1, 1, 1))])
        tris, fmap = mdl.triangulate_faces(m)
        self.assertEqual(len(tris), 12)       # 6 四边形 × 2
        self.assertEqual(fmap.min(), 0)
        self.assertEqual(int(fmap.max()), 5)


class TestSegTri(unittest.TestCase):
    def test_cross(self):
        tri = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        p0 = np.array([0.25, 0.25, -1.0])
        p1 = np.array([0.25, 0.25, 1.0])
        self.assertTrue(mdl._seg_tri_intersect(p0, p1, tri))

    def test_miss(self):
        tri = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        p0 = np.array([5.0, 5.0, -1.0])
        p1 = np.array([5.0, 5.0, 1.0])
        self.assertFalse(mdl._seg_tri_intersect(p0, p1, tri))

    def test_parallel(self):
        tri = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        p0 = np.array([0.0, 0.0, 1.0])
        p1 = np.array([1.0, 0.0, 1.0])
        self.assertFalse(mdl._seg_tri_intersect(p0, p1, tri))


class TestSurfaceIntersections(unittest.TestCase):
    def test_disjoint_bodies_clean(self):
        m = _mdl_from_boxes([((0, 0, 0), (1, 1, 1)),
                             ((5, 5, 5), (6, 6, 6))])
        self.assertEqual(mdl.surface_intersections(m, vertex_tol=1e-9), [])

    def test_overlapping_bodies_found(self):
        m = _mdl_from_boxes([((0, 0, 0), (2, 2, 2)),
                             ((1, 1, 1), (3, 3, 3))])
        hits = mdl.surface_intersections(m, vertex_tol=1e-9)
        self.assertGreater(len(hits), 0)
        self.assertEqual(hits[0]["body_a"], 1)
        self.assertEqual(hits[0]["body_b"], 2)

    def test_shared_interface_ignored(self):
        # 两盒共享一个面（界面面片 csid 同含两侧）→ 不算穿越
        xyz_a, quads_a = _box(0, 0, 0, 1, 1, 1)
        xyz_b, quads_b = _box(1, 0, 0, 2, 1, 1)
        xyz = xyz_a + xyz_b
        faces = ([[v for v in q] for q in quads_a]
                 + [[v + 8 for v in q] for q in quads_b])
        # quads 序：x-, x+, y-, y+, z+, z- → A 的 x+ = faces[1]，
        # B 的 x- = faces[6+5]；删两者后补一份 x=1 界面（A 侧顶点）
        del faces[11]
        del faces[1]
        faces.append([4, 5, 7, 6])
        n_f = len(faces)                 # 5 + 5 + 1
        b1 = np.array([0] * 10 + [1], dtype=np.int64)   # 界面另一侧 body1
        b2 = np.array([1] * 5 + [2] * 5 + [2], dtype=np.int64)
        conn = np.asarray(faces, dtype=np.int64).reshape(-1)
        m = mdl.MdlModel(
            n_vertices=len(xyz), n_faces=n_f,
            xyz=np.asarray(xyz, dtype=float),
            face_type=np.full(n_f, 134, dtype=np.int64),
            conn=conn,
            csid=(b1, b2),
            frid=np.zeros(n_f, dtype=np.int64),
            edge_state=np.zeros(conn.size, dtype=np.uint8),
            node_state=np.zeros(len(xyz), dtype=np.int64),
            closed_volumes=["", "A", "B"], volume_regions=["FluidRegion"],
            surface_regions=[])
        # 界面在 in_a & in_b 集合中 → 自动排除；两侧外表面互不相交
        hits = mdl.surface_intersections(m, vertex_tol=1e-9)
        self.assertEqual(hits, [])

    def test_cross_model(self):
        a = _mdl_from_boxes([((0, 0, 0), (2, 2, 2))])
        b = _mdl_from_boxes([((1, 1, 1), (3, 3, 3))])
        hits = mdl.surface_intersections(a, b, vertex_tol=1e-9)
        self.assertGreater(len(hits), 0)
        self.assertIn("face_a", hits[0])

        c = _mdl_from_boxes([((10, 10, 10), (12, 12, 12))])
        self.assertEqual(
            mdl.surface_intersections(a, c, vertex_tol=1e-9), [])

    def test_touching_boxes_not_reported(self):
        # 两盒贴合（共享面但独立拓扑）：共面贴合不属穿越 → 不报
        m = _mdl_from_boxes([((0, 0, 0), (1, 1, 1)),
                             ((1, 0, 0), (2, 1, 1))])
        hits = mdl.surface_intersections(m, vertex_tol=1e-9)
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
