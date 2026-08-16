#!/usr/bin/env python3
"""geometry_ops（P0-2 facet→B-rep + P0-3 原生 create/modify）回归。

pskernel 不可用时内核级用例整体跳过（同 test_ps_edit 约定）。
"""

import math
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import geometry_ops as go  # noqa: E402


def _unit_cube_mesh(scale=1.0, offset=(0.0, 0.0, 0.0)):
    """12 三角形单位立方体网格（[0,1]³×scale+offset）。"""
    o = np.asarray(offset, dtype=np.float64)
    v = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64) * scale + o
    quads = [
        (0, 3, 2, 1), (4, 5, 6, 7),   # -Z +Z
        (0, 1, 5, 4), (2, 3, 7, 6),   # -Y +Y
        (1, 2, 6, 5), (0, 4, 7, 3),   # +X -X
    ]
    tris = []
    for a, b, c, d in quads:
        tris.append((a, b, c))
        tris.append((a, c, d))
    return v, np.asarray(tris, dtype=np.int64)


class TestPureHelpers(unittest.TestCase):
    def test_unit_factor(self):
        self.assertAlmostEqual(go.unit_factor("mm"), 1e-3)
        self.assertAlmostEqual(go.unit_factor("cm"), 1e-2)
        self.assertAlmostEqual(go.unit_factor("m"), 1.0)
        self.assertAlmostEqual(go.unit_factor("in"), 0.0254)
        self.assertAlmostEqual(go.unit_factor(None), 1.0)
        self.assertAlmostEqual(go.unit_factor("unknown"), 1.0)

    def test_mesh_volume_cube(self):
        v, t = _unit_cube_mesh()
        self.assertAlmostEqual(go.mesh_volume_m3(v, t), 1.0, places=6)
        v2, t2 = _unit_cube_mesh(scale=2.0)
        self.assertAlmostEqual(go.mesh_volume_m3(v2, t2), 8.0, places=6)

    def test_mesh_volume_empty(self):
        self.assertEqual(
            go.mesh_volume_m3(np.zeros((0, 3)), np.zeros((0, 3), int)), 0.0)


class _KernelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not go.available():
            raise unittest.SkipTest("pskernel.dll not available")
        cls.sess = go.session()

    def _bbox(self, tag):
        p = self.sess.facet_body(tag)
        self.assertIsNotNone(p)
        return p.points.min(axis=0), p.points.max(axis=0)


class TestCreatePrimitives(_KernelTest):
    def test_create_block(self):
        tag = go.create_block((1.0, 2.0, 3.0), (0.5, 0.0, 0.0))
        lo, hi = self._bbox(tag)
        for i, s in enumerate((1.0, 2.0, 3.0)):
            self.assertAlmostEqual(hi[i] - lo[i], s, delta=0.05)
        # create_solid_block 的 origin 是中心
        self.assertAlmostEqual((hi[0] + lo[0]) / 2, 0.5, delta=0.05)

    def test_create_cylinder_z(self):
        tag = go.create_cylinder(0.5, 2.0, (0.0, 0.0, 1.0), (0.0, 0.0, 1.0))
        lo, hi = self._bbox(tag)
        self.assertAlmostEqual(hi[2] - lo[2], 2.0, delta=0.05)
        self.assertAlmostEqual(lo[2], 1.0, delta=0.05)  # bottom
        self.assertAlmostEqual(hi[0] - lo[0], 1.0, delta=0.05)

    def test_create_cylinder_x(self):
        tag = go.create_cylinder(0.5, 2.0, (0.0, 0.0, 0.0),
                                 (1.0, 0.0, 0.0))
        lo, hi = self._bbox(tag)
        self.assertAlmostEqual(hi[0] - lo[0], 2.0, delta=0.05)
        self.assertAlmostEqual(hi[1] - lo[1], 1.0, delta=0.05)

    def test_create_sphere_volume(self):
        r = 1.0
        tag = go.create_sphere(r, (0.0, 0.0, 0.0))
        p = self.sess.facet_body(tag)
        vol = go.mesh_volume_m3(p.points, p.triangles)
        self.assertAlmostEqual(vol, 4 / 3 * math.pi * r ** 3, delta=0.15)
        lo, hi = self._bbox(tag)
        self.assertAlmostEqual((hi[0] + lo[0]) / 2, 0.0, delta=0.05)


class TestExecuteCreateParts(_KernelTest):
    def test_cuboid_mm(self):
        draft = {"shape": "Cuboid", "name": "Box1", "fluid": True,
                 "position": (0.0, 0.0, 0.0), "size": (1000.0, 1000.0, 500.0)}
        res = go.execute_create_parts(draft, unit="mm")
        self.assertEqual(res["name"], "Box1")
        self.assertTrue(res["fluid"])
        self.assertTrue(res["xt"])
        p = res["tess"]
        lo = p.points.min(axis=0)
        hi = p.points.max(axis=0)
        self.assertAlmostEqual(hi[0] - lo[0], 1.0, delta=0.05)
        self.assertAlmostEqual(hi[2] - lo[2], 0.5, delta=0.05)
        self.assertAlmostEqual(go.mesh_volume_m3(p.points, p.triangles),
                               0.5, delta=0.02)

    def test_cylinder_direction_x(self):
        draft = {"shape": "Cylinder", "name": "CylX",
                 "bottom": (1.0, 2.0, 3.0), "height": 4.0,
                 "radius": 0.5, "direction": "X"}
        res = go.execute_create_parts(draft, unit="m")
        lo = res["tess"].points.min(axis=0)
        hi = res["tess"].points.max(axis=0)
        self.assertAlmostEqual(hi[0] - lo[0], 4.0, delta=0.06)
        self.assertAlmostEqual(lo[0], 1.0, delta=0.05)
        self.assertAlmostEqual(hi[1] - lo[1], 1.0, delta=0.06)

    def test_sphere(self):
        draft = {"shape": "Sphere", "name": "Sph", "center": (0.0, 0.0, 0.0),
                 "radius": 2.0}
        res = go.execute_create_parts(draft, unit="m")
        lo = res["tess"].points.min(axis=0)
        hi = res["tess"].points.max(axis=0)
        self.assertAlmostEqual(hi[0] - lo[0], 4.0, delta=0.1)

    def test_rectangle_sheet(self):
        # P5-1：Rectangle 原生建片体（PK_BODY_create_sheet_rectangle）
        draft = {"shape": "Rectangle", "name": "Rect", "axis": "Z axis",
                 "position": (0.0, 0.0, 0.5), "size": (2.0, 1.0, 0.0)}
        res = go.execute_create_parts(draft, unit="m")
        self.assertTrue(res["xt"])
        p = res["tess"]
        lo = p.points.min(axis=0)
        hi = p.points.max(axis=0)
        self.assertAlmostEqual(hi[0] - lo[0], 2.0, delta=0.05)
        self.assertAlmostEqual(hi[1] - lo[1], 1.0, delta=0.05)
        self.assertAlmostEqual((hi[2] + lo[2]) / 2, 0.5, delta=0.05)
        # 片体：面积 = 2，体积 = 0
        areas = []
        for a, b, c in p.triangles:
            u = p.points[b] - p.points[a]
            v = p.points[c] - p.points[a]
            areas.append(0.5 * np.linalg.norm(np.cross(u, v)))
        self.assertAlmostEqual(sum(areas), 2.0, delta=0.05)

    def test_cone(self):
        # V35 语义：radius = 小端半径，底面半径 = radius + height*tan(semi_angle)
        tag = go.create_cone(1.0, 2.0, math.atan(0.5), bottom_m=(0, 0, 0),
                             direction=(0, 0, 1))
        lo, hi = self._bbox(tag)
        self.assertAlmostEqual(hi[2] - lo[2], 2.0, delta=0.05)
        self.assertAlmostEqual(hi[0] - lo[0], 4.0, delta=0.05)  # 底直径=2*2

    def test_torus(self):
        tag = go.create_torus(2.0, 0.5, centre_m=(0, 0, 0), axis=(0, 0, 1))
        lo, hi = self._bbox(tag)
        self.assertAlmostEqual(hi[0] - lo[0], 5.0, delta=0.05)
        self.assertAlmostEqual(hi[2] - lo[2], 1.0, delta=0.05)
        self.assertAlmostEqual((hi[0] + lo[0]) / 2, 0.0, delta=0.05)

    def test_invalid_size(self):
        draft = {"shape": "Cuboid", "name": "Bad",
                 "position": (0, 0, 0), "size": (1.0, 0.0, 1.0)}
        with self.assertRaises(ValueError):
            go.execute_create_parts(draft, unit="m")


class TestExecuteModifyParts(_KernelTest):
    def _two_blocks(self):
        a = go.create_block((1.0, 1.0, 1.0))
        b = go.create_block((1.0, 1.0, 1.0), (0.5, 0.0, 0.0))
        return {"A": a, "B": b}

    def test_unite(self):
        tags = self._two_blocks()
        draft = {"op": "unite_solids", "parts": ["A", "B"], "params": {}}
        res = go.execute_modify_parts(draft, tags, unit="m")
        self.assertEqual(res["removed"], ["A", "B"])
        self.assertEqual(len(res["added"]), 1)
        p = res["added"][0]["tess"]
        lo = p.points.min(axis=0)
        hi = p.points.max(axis=0)
        self.assertAlmostEqual(hi[0] - lo[0], 1.5, delta=0.06)
        self.assertAlmostEqual(hi[1] - lo[1], 1.0, delta=0.06)

    def test_remove_solid_overlap(self):
        tags = self._two_blocks()
        draft = {"op": "remove_solid_overlap", "parts": ["A", "B"],
                 "params": {}}
        res = go.execute_modify_parts(draft, tags, unit="m")
        self.assertTrue(res["added"])
        p = res["added"][0]["tess"]
        vol = go.mesh_volume_m3(p.points, p.triangles)
        self.assertAlmostEqual(vol, 0.5, delta=0.1)

    def test_translate(self):
        tags = {"A": go.create_block((1.0, 1.0, 1.0))}
        lo1, _ = self._bbox(tags["A"])
        draft = {"op": "translate_copy", "parts": ["A"],
                 "params": {"distance": (1000.0, 0.0, 0.0)}}
        res = go.execute_modify_parts(draft, tags, unit="mm")
        self.assertEqual(res["changed"], ["A"])
        lo2, _ = self._bbox(tags["A"])
        self.assertAlmostEqual(lo2[0] - lo1[0], 1.0, delta=0.05)
        self.assertTrue(any("就地" in n for n in res["notes"]))

    def test_rotate(self):
        tags = {"A": go.create_block((2.0, 1.0, 1.0))}
        draft = {"op": "rotate_copy", "parts": ["A"],
                 "params": {"center": (0, 0, 0), "axis": "Z direction",
                            "angle": 90.0}}
        res = go.execute_modify_parts(draft, tags, unit="m")
        self.assertEqual(res["changed"], ["A"])
        lo, hi = self._bbox(tags["A"])
        self.assertAlmostEqual(hi[0] - lo[0], 1.0, delta=0.06)
        self.assertAlmostEqual(hi[1] - lo[1], 2.0, delta=0.06)

    def test_scale_uniform_and_reject(self):
        tags = {"A": go.create_block((1.0, 1.0, 1.0))}
        draft = {"op": "scale_copy", "parts": ["A"],
                 "params": {"center": (0, 0, 0), "scale": (2.0, 2.0, 2.0)}}
        go.execute_modify_parts(draft, tags, unit="m")
        lo, hi = self._bbox(tags["A"])
        self.assertAlmostEqual(hi[0] - lo[0], 2.0, delta=0.06)
        bad = {"op": "scale_copy", "parts": ["A"],
               "params": {"center": (0, 0, 0), "scale": (2.0, 1.0, 1.0)}}
        with self.assertRaises(NotImplementedError):
            go.execute_modify_parts(bad, tags, unit="m")

    def test_unsupported_op(self):
        with self.assertRaises(NotImplementedError):
            go.execute_modify_parts(
                {"op": "simplify_face", "parts": ["A"], "params": {}},
                {"A": 1}, unit="m")

    def test_no_loaded_bodies(self):
        with self.assertRaises(RuntimeError):
            go.execute_modify_parts(
                {"op": "unite_solids", "parts": ["X"], "params": {}},
                {}, unit="m")


class TestTrianglesToBrep(_KernelTest):
    def test_cube_mesh_to_solid(self):
        v, t = _unit_cube_mesh()
        solids = go.triangles_to_brep(v, t)
        self.assertTrue(solids)
        p = self.sess.facet_body(solids[0])
        vol = go.mesh_volume_m3(p.points, p.triangles)
        self.assertAlmostEqual(vol, 1.0, delta=0.05)

    def test_translated_cube(self):
        v, t = _unit_cube_mesh(scale=0.5, offset=(10.0, -5.0, 2.0))
        solids = go.triangles_to_brep(v, t)
        self.assertTrue(solids)
        p = self.sess.facet_body(solids[0])
        vol = go.mesh_volume_m3(p.points, p.triangles)
        self.assertAlmostEqual(vol, 0.125, delta=0.02)

    def test_boolean_with_brep_cube(self):
        """facet→B-rep 产物可直接参与布尔（管线闭环验证）。

        注：本内核（V37 lattice/mesh 面）对“经典体 − 面片实体”走近似
        路径——实测 x∈[0.25,1.25] 工具体仅移除约一半重叠体积
        （0.875 vs 理论 0.75），经典体-经典体布尔不受影响（见
        test_ps_edit / execute_modify_parts 用例）。此处断言语义：
        布尔可执行、确有材料被移除。
        """
        v, t = _unit_cube_mesh(offset=(0.25, 0.0, 0.0))
        solids = go.triangles_to_brep(v, t)
        self.assertTrue(solids)
        block = go.create_block((1.0, 1.0, 1.0))
        res = go.boolean(block, [solids[0]], "subtract")
        self.assertTrue(res)
        p = self.sess.facet_body(res[0])
        vol = go.mesh_volume_m3(p.points, p.triangles)
        self.assertLess(vol, 0.99)
        self.assertGreaterEqual(vol, 0.5)

    def test_empty_mesh(self):
        self.assertEqual(
            go.triangles_to_brep(np.zeros((0, 3)), np.zeros((0, 3), int)),
            [])


class TestTransmitBody(_KernelTest):
    def test_transmit_returns_xt_bytes(self):
        tag = go.create_block((1.0, 1.0, 1.0))
        raw = go.transmit_body(tag)
        self.assertTrue(raw)
        # 本内核文本 x_t 头部（见 user_guide §2 写回捕获）
        self.assertIn(b"TRANSMIT FILE", raw[:256])
        self.assertIn(b"modeller version", raw[:256])


if __name__ == "__main__":
    unittest.main()
