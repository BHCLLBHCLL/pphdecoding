#!/usr/bin/env python3
"""自研 Voxel / Hex-dominant mesher 回归。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import gphstats  # noqa: E402
import oct as octmod  # noqa: E402
import voxmesh  # noqa: E402

BOX_PPH = ROOT / "box.pph"


def _unit_box_surface() -> tuple[np.ndarray, np.ndarray]:
    pts = np.array(
        [[x, y, z]
         for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)],
        dtype=float)
    faces = [
        [0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1],
        [2, 3, 7, 6], [1, 5, 7, 3], [0, 2, 6, 4],
    ]
    return voxmesh.surface_from_mesh(pts, faces)


class TestVoxMeshSynthetic(unittest.TestCase):
    def test_rough_poly_hex_mesh(self):
        points, tris = _unit_box_surface()
        params = voxmesh.VoxelMeshParams(
            initial_depth=2, max_depth=3, max_cells=100_000,
            rough_poly=True)
        res = voxmesh.build_mesh(points, tris, params)
        st = res.stats()
        self.assertGreater(st["n_cells"], 0)
        self.assertEqual(st["n_poly"], 0)
        self.assertEqual(st["n_hex"], st["n_cells"])
        self.assertEqual(st["n_cells"],
                         st["n_inside"] + st["n_cut"])
        if res.refinement.size:
            # 满八叉树：total = 8*internal + 1, leaves = 7*internal + 1
            internal = int(res.refinement.sum())
            self.assertEqual(8 * internal + 1,
                             int(res.refinement.size))
            self.assertEqual(7 * internal + 1,
                             int(res.stats()["n_leaves"]))

    def test_cut_cells_become_polyhedra(self):
        points, tris = _unit_box_surface()
        params = voxmesh.VoxelMeshParams(
            initial_depth=2, max_depth=3, max_cells=100_000,
            rough_poly=False)
        res = voxmesh.build_mesh(points, tris, params)
        st = res.stats()
        self.assertGreater(st["n_poly"], 0)
        self.assertLess(st["n_poly"], st["n_cells"])

    def test_roundtrip_oct_and_gph(self):
        points, tris = _unit_box_surface()
        with tempfile.TemporaryDirectory() as td:
            pre = Path(td) / "box"
            res = voxmesh.build_mesh(
                points, tris,
                voxmesh.VoxelMeshParams(initial_depth=2, max_depth=2))
            oct_p, gph_p = voxmesh.write_outputs(res, pre)
            om = octmod.parse_oct(oct_p)
            self.assertEqual(om.leaf_stats()["n_leaves"],
                             len(res.leaf_boxes))
            mesh = gphstats.parse_mesh(gph_p.read_bytes())
            self.assertEqual(mesh["n_faces"],
                             len(mesh["owner"]))
            self.assertEqual(int(mesh["owner"].max()) + 1,
                             len(res.cells))
            self.assertTrue(mesh["boundary_mask"].any())

    def test_deterministic(self):
        points, tris = _unit_box_surface()
        params = voxmesh.VoxelMeshParams(initial_depth=2, max_depth=3)
        r1 = voxmesh.build_mesh(points, tris, params)
        r2 = voxmesh.build_mesh(points, tris, params)
        self.assertEqual(r1.stats()["n_cells"], r2.stats()["n_cells"])
        self.assertEqual(r1.stats()["n_vertices"],
                         r2.stats()["n_vertices"])

    def test_build_octree_only_matches_build_mesh(self):
        points, tris = _unit_box_surface()
        params = voxmesh.VoxelMeshParams(initial_depth=2, max_depth=3)
        rmin, rmax, ref, leaves = voxmesh.build_octree(points, tris, params)
        res = voxmesh.build_mesh(points, tris, params)
        self.assertEqual(len(leaves), len(res.leaf_boxes))
        self.assertTrue(np.array_equal(ref, res.refinement))
        self.assertTrue(np.allclose(rmin, res.root_min))
        self.assertTrue(np.allclose(rmax, res.root_max))


class TestVoxMeshReal(unittest.TestCase):
    @unittest.skipUnless(BOX_PPH.is_file(), "box.pph not present")
    def test_build_from_box_mdl(self):
        import pph_parser
        arch = pph_parser.PphArchive.open(str(BOX_PPH))
        members = arch.by_role(pph_parser.ROLE_MDL_PART)
        self.assertTrue(members)
        with tempfile.TemporaryDirectory() as td:
            mdl_path = Path(td) / "part.mdl"
            mdl_path.write_bytes(arch.read_member(members[0].name))
            pre = Path(td) / "box_vox"
            res, oct_p, gph_p = voxmesh.build_from_mdl(
                mdl_path, pre,
                voxmesh.VoxelMeshParams(
                    initial_depth=2, max_depth=3, max_cells=300_000,
                    rough_poly=True))
            st = res.stats()
            self.assertGreater(st["n_cells"], 100)
            self.assertEqual(st["n_poly"], 0)
            mesh = gphstats.parse_mesh(gph_p.read_bytes())
            self.assertEqual(int(mesh["owner"].max()) + 1,
                             st["n_cells"])
            self.assertGreater(len(mesh["vertices"]), 100)

    @unittest.skipUnless(BOX_PPH.is_file(), "box.pph not present")
    def test_cli_smoke(self):
        with tempfile.TemporaryDirectory() as td:
            pre = Path(td) / "cli_vox"
            code = voxmesh.main([
                str(BOX_PPH), "-o", str(pre),
                "--initial-depth", "2", "--max-depth", "2", "--rough"])
            self.assertEqual(code, 0)
            self.assertTrue(Path(str(pre) + ".oct").is_file())
            self.assertTrue(Path(str(pre) + ".gph").is_file())


class TestGphVolumeWriter(unittest.TestCase):
    def test_two_hex_cells_share_face(self):
        # 两个并排 hex：cell0 x∈[0,1]，cell1 x∈[1,2]
        verts = []
        for x in (0.0, 1.0, 2.0):
            for y in (0.0, 1.0):
                for z in (0.0, 1.0):
                    verts.append([x, y, z])
        verts = np.asarray(verts, dtype=float)

        def hex_ids(x0: float) -> np.ndarray:
            base = int(x0 * 4)
            return np.array([
                base + 0, base + 1, base + 3, base + 2,
                base + 4, base + 5, base + 7, base + 6,
            ])

        c0 = hex_ids(0.0)
        c1 = hex_ids(1.0)
        cells = [c0, c1]
        face_map = {}
        for cid, ids in enumerate(cells):
            for f in voxmesh.HEX_FACES:
                key = frozenset(int(ids[v]) for v in f)
                if key not in face_map:
                    face_map[key] = [cid, -1, [int(ids[v]) for v in f]]
                elif face_map[key][1] == -1:
                    face_map[key][1] = cid
        faces = [r[2] for r in face_map.values()]
        owner = np.array([r[0] for r in face_map.values()], dtype=np.int32)
        neigh = np.array([r[1] for r in face_map.values()], dtype=np.int32)
        with tempfile.TemporaryDirectory() as td:
            p = gphstats.write_gph_volume(
                Path(td) / "two.gph", verts, faces, owner, neigh)
            mesh = gphstats.parse_mesh(p.read_bytes())
        self.assertEqual(int(mesh["owner"].max()) + 1, 2)
        self.assertEqual(int((mesh["neigh"] == 0xFFFFFFFF).sum()),
                         len(faces) - 1)  # 仅共享面非边界
        self.assertEqual(int((mesh["neigh"] < 0xFFFFFFFF).sum()), 1)
        self.assertEqual(int(mesh["boundary_mask"].sum()),
                         len(faces) - 1)


def _face_neighbor_depth_diffs(root_min: np.ndarray,
                                leaves) -> list[int]:
    """独立校验器：返回所有面邻叶子对（细侧深度 - 粗侧深度）的差值。

    对每个叶子按其深度量化到整格坐标，逐层向上查祖先格的 ±1 面移
    邻居；仅在叶子贴住祖先该侧面时才构成面邻（避开与平衡实现共用
    代码，避免"用被测代码验证自身"）。
    """
    by_depth: dict[int, dict[tuple, int]] = {}
    coords: list[tuple[tuple, int]] = []
    for i, (mn, mx, d) in enumerate(leaves):
        cell = float(mx[0] - mn[0])
        c = tuple(np.rint((np.asarray(mn) - np.asarray(root_min))
                          / cell).astype(np.int64))
        di = int(d)
        coords.append((c, di))
        by_depth.setdefault(di, {})[c] = i
    diffs: list[int] = []
    for (_mn, _mx, _d), (c, d) in zip(leaves, coords):
        for cd in range(d):
            shift = d - cd
            mask = (1 << shift) - 1
            base = tuple(int(v) >> shift for v in c)
            for axis in range(3):
                if (c[axis] & mask) == 0:        # 贴祖先 - 侧面
                    nb = list(base)
                    nb[axis] -= 1
                    if tuple(nb) in by_depth.get(cd, {}):
                        diffs.append(d - cd)
                if (c[axis] & mask) == mask:     # 贴祖先 + 侧面
                    nb = list(base)
                    nb[axis] += 1
                    if tuple(nb) in by_depth.get(cd, {}):
                        diffs.append(d - cd)
    return diffs


class TestVoxMesh2to1Balance(unittest.TestCase):
    def test_balanced_tree_respects_2to1(self):
        points, tris = _unit_box_surface()
        params = voxmesh.VoxelMeshParams(
            initial_depth=2, max_depth=5, max_cells=1_000_000,
            balance_2to1=True)
        root_min, _root_max, _ref, leaves = voxmesh.build_octree(
            points, tris, params)
        self.assertGreater(len(leaves), 500)     # 表面细化确实发生
        jumps = [d for d in _face_neighbor_depth_diffs(root_min, leaves)
                 if d > 1]
        self.assertEqual(jumps, [],
                         f"2:1 平衡被违反 {len(jumps)} 处")

    def test_unbalanced_tree_has_depth_jumps(self):
        points, tris = _unit_box_surface()
        params = voxmesh.VoxelMeshParams(
            initial_depth=2, max_depth=5, max_cells=1_000_000,
            balance_2to1=False)
        root_min, _root_max, _ref, leaves = voxmesh.build_octree(
            points, tris, params)
        diffs = _face_neighbor_depth_diffs(root_min, leaves)
        self.assertTrue(any(d >= 2 for d in diffs),
                        "关闭平衡后应存在深度差 ≥ 2 的面邻对")


class TestGuiWiring(unittest.TestCase):
    def test_execute_menu_and_dialog_wired(self):
        src = (ROOT / "pph_gui.py").read_text(encoding="utf-8")
        self.assertIn("Voxel Fitting Mesh (Self Build)", src)
        self.assertIn("def _build_voxel_mesh", src)
        self.assertIn("def _voxel_params_dialog", src)
        self.assertIn("voxmesh.build_from_mdl", src)

    def test_module_cli_args(self):
        src = (ROOT / "voxmesh.py").read_text(encoding="utf-8")
        self.assertIn("--initial-depth", src)
        self.assertIn("--max-depth", src)


if __name__ == "__main__":
    unittest.main()
