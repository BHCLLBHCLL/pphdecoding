#!/usr/bin/env python3
"""最小 MDL 写端（write_mdl）回归：LS_Faces/Csid/Frid/EdgeState 往返。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import mdl  # noqa: E402
import pph_vtk  # noqa: E402


def _unit_box_quads():
    pts = np.array(
        [[x, y, z]
         for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)],
        dtype=float)
    faces = [
        [0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1],
        [2, 3, 7, 6], [1, 5, 6, 2], [0, 2, 6, 4],
    ]
    return pts, faces


class TestWriteMdl(unittest.TestCase):
    def test_quad_roundtrip(self):
        pts, faces = _unit_box_quads()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "part.mdl"
            mdl.write_mdl(p, pts, faces)
            m = mdl.parse_mdl(str(p))
        self.assertEqual(m.n_vertices, 8)
        self.assertEqual(m.n_faces, 6)
        self.assertTrue(np.all(m.npe == 4))
        self.assertEqual(len(m.conn), 24)
        self.assertTrue(np.all(m.csid[0] == 0))
        self.assertTrue(np.all(m.csid[1] == 1))
        self.assertTrue(np.all(m.frid == 0))
        self.assertEqual(len(m.edge_state), 24)
        self.assertEqual(int(m.edge_state.sum()), 0)
        self.assertEqual(m.n_closed_volumes, 1)

    def test_triangle_roundtrip_and_render(self):
        pts, quads = _unit_box_quads()
        tris = []
        for q in quads:
            tris.append([q[0], q[1], q[2]])
            tris.append([q[0], q[2], q[3]])
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "tri.mdl"
            mdl.write_mdl(p, pts, tris)
            m = mdl.parse_mdl(str(p))
            self.assertEqual(m.n_faces, 12)
            self.assertTrue(np.all(m.npe == 3))
            pd = pph_vtk.mdl_mesh(m, "frid")
        self.assertEqual(pd.GetNumberOfCells(), 12)
        self.assertEqual(pd.GetNumberOfPoints(), 8)

    def test_ridge_edge_state_roundtrip(self):
        # ridge 标记 = LS_EdgeStateOfFaces(1) + LS_StateOfNodes(1)
        pts, faces = _unit_box_quads()  # 8 顶点，6 四边形面 = 24 半边
        edge_state = np.zeros(24, dtype=np.uint8)
        edge_state[0] = 1
        edge_state[5] = 1
        node_state = np.zeros(8, dtype=np.int64)
        node_state[3] = 1
        p = ROOT / "_test_ridge.mdl"
        try:
            mdl.write_mdl(p, pts, faces,
                          edge_state=edge_state, node_state=node_state)
            m = mdl.parse_mdl(str(p))
        finally:
            p.unlink(missing_ok=True)
        self.assertEqual(len(m.edge_state), 24)
        self.assertEqual(int((m.edge_state == 1).sum()), 2)
        self.assertEqual(int((m.node_state == 1).sum()), 1)
        self.assertEqual(m.edge_state.tolist()[0], 1)

    def test_pentagon_roundtrip(self):
        # n-gon（五边形面）：上下底各一个五边形 + 5 个四边形侧面
        ang = [2 * np.pi * i / 5 for i in range(5)]
        pts = np.array(
            [[np.cos(a), np.sin(a), 0.0] for a in ang] +
            [[np.cos(a), np.sin(a), 1.0] for a in ang], dtype=float)
        bottom = [0, 1, 2, 3, 4]
        top = [5, 6, 7, 8, 9]
        sides = [[i, (i + 1) % 5, (i + 1) % 5 + 5, i + 5] for i in range(5)]
        faces = [bottom, top] + sides
        p = ROOT / "_test_ngon.mdl"
        try:
            mdl.write_mdl(p, pts, faces)
            m = mdl.parse_mdl(str(p))
        finally:
            p.unlink(missing_ok=True)
        self.assertEqual(m.n_faces, 7)
        self.assertTrue(np.all(m.npe[[0, 1]] == 5))
        self.assertTrue(np.all(m.npe[2:] == 4))
        self.assertEqual(len(m.conn), 5 * 2 + 4 * 5)

    def test_deterministic_bytes(self):
        pts, faces = _unit_box_quads()
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "a.mdl"
            p2 = Path(td) / "b.mdl"
            mdl.write_mdl(p1, pts, faces)
            mdl.write_mdl(p2, pts, faces)
            self.assertEqual(p1.read_bytes(), p2.read_bytes())

    def test_custom_csid_frid_regions(self):
        pts, faces = _unit_box_quads()
        n = len(faces)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "part.mdl"
            mdl.write_mdl(
                p, pts, faces,
                csid=(np.full(n, 2, dtype=np.int64),
                      np.full(n, 3, dtype=np.int64)),
                frid=np.arange(n, dtype=np.int64),
                surface_regions=[("inlet", 0), ("outlet", 1)])
            m = mdl.parse_mdl(str(p))
        self.assertEqual(m.n_closed_volumes, 3)
        self.assertTrue(np.all(m.csid[0] == 2))
        self.assertTrue(np.all(m.csid[1] == 3))
        self.assertEqual(m.frid.tolist(), list(range(n)))
        self.assertEqual([(r.name, r.index) for r in m.surface_regions],
                         [("inlet", 0), ("outlet", 1)])

    def test_native_region_layout(self):
        """区域节对齐宿主布局：desc(type=1,255,1) 名称记录 + 20B 节尾。"""
        pts, faces = _unit_box_quads()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "part.mdl"
            mdl.write_mdl(
                p, pts, faces,
                surface_regions=[("open", 0), ("inlet", 1)],
                closed_volumes=["", "body1"],
                volume_regions=["FluidRegion"])
            raw = p.read_bytes()
            m = mdl.parse_mdl(str(p))
        name_rec = (b"\x00\x00\x00\x0c\x00\x00\x00\x01"
                    b"\x00\x00\x00\xff\x00\x00\x00\x01")
        # 2 面区域 + 2 闭体 + 1 体区域 = 5 条名称记录
        self.assertEqual(raw.count(name_rec), 5)
        self.assertIn(b"LS_MdlClosedVolumes", raw)
        self.assertIn(b"LS_MdlVolumeRegions", raw)
        self.assertEqual(m.closed_volumes, ["", "body1"])
        self.assertEqual(m.volume_regions, ["FluidRegion"])
        self.assertEqual([(r.name, r.index) for r in m.surface_regions],
                         [("open", 0), ("inlet", 1)])
        # 闭体 id 仍由 csid 数组推导；默认 csid(0,1) → 1 闭体，
        # closed_volumes 记录数 = N+1（含外部记录）
        self.assertEqual(m.n_closed_volumes, 1)

    def test_native_flow_writes_mdl_from_cad(self):
        src = (ROOT / "pph_gui.py").read_text(encoding="utf-8")
        self.assertIn("mdlmod.write_mdl", src)
        self.assertIn('part_name = "meshinggroup1_part.mdl"', src)
        self.assertIn("MDL(CAD生成)", src)


if __name__ == "__main__":
    unittest.main()
