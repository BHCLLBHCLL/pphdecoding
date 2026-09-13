#!/usr/bin/env python3
"""voxmesh 面区域映射（P2-2：frid 传参 → LS_SurfaceRegions）回归。

验证：

- 三区盒面（inlet=z- / outlet=z+ / wall=四周）粗糙 hex 网格的边界面
  按最近输入三角形正确归属区域；
- 内部面不归属任何区域；
- 写出 GPH 含 LS_SurfaceRegions 且可被 gphstats 读回（名字 + 面数 +
  0-based 面号，区域覆盖全部边界面）；
- MDL 路径：write_mdl 带 frid + surface_regions → build_from_mdl 全链
  路自动携带区域（无需显式传参）。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import gphstats  # noqa: E402
import mdl as mdlmod  # noqa: E402
import voxmesh  # noqa: E402

# 盒角序（x 外层 / y 中层 / z 内层，同 test_voxmesh 的 _unit_box_surface）
_CORNERS = np.array(
    [[x, y, z]
     for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)],
    dtype=float)
# (quad 顶点环, 区域 id)：0-3 四侧壁 wall(2)，4 顶面 outlet(1)，5 底面 inlet(0)
# 角点序 x 外层/y 中层/z 内层：1=(−,−,+)…6=(+,+,−)，顶面须 [1,5,7,3]
# （test_voxmesh 旧 helper 的 [1,5,6,2] 含 z=− 角点，是斜穿扭面）
_QUADS = [
    ([0, 1, 3, 2], 2), ([4, 6, 7, 5], 2),
    ([0, 4, 5, 1], 2), ([2, 3, 7, 6], 2),
    ([1, 5, 7, 3], 1), ([0, 2, 6, 4], 0),
]
_REGION_NAMES = ["inlet", "outlet", "wall"]


def _region_box_surface() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """三区盒面 → (points, tris, tri_region)（四边形拆分同 surface_from_mesh）。"""
    tris: list[list[int]] = []
    tri_region: list[int] = []
    for quad, rid in _QUADS:
        q = np.asarray(quad, dtype=np.int64)
        tris.append(q[[0, 1, 2]])
        tri_region.append(rid)
        tris.append(q[[0, 2, 3]])
        tri_region.append(rid)
    return (_CORNERS,
            np.asarray(tris, dtype=np.int64),
            np.asarray(tri_region, dtype=np.int64))


class TestRegionMapping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pts, tris, tri_region = _region_box_surface()
        cls.params = voxmesh.VoxelMeshParams(
            initial_depth=2, max_depth=3, max_cells=100_000, rough_poly=True)
        cls.res = voxmesh.build_mesh(
            pts, tris, cls.params,
            tri_region=tri_region, region_names=_REGION_NAMES)

    def test_all_boundary_faces_mapped(self):
        """粗糙阶梯边界 100% 归属区域（内部单元不触根盒，边界全贴体）。"""
        res = self.res
        self.assertEqual(res.face_region.size, len(res.faces))
        neigh = np.asarray(res.face_neigh)
        boundary = neigh < 0
        self.assertTrue(boundary.any())
        self.assertTrue(np.all(res.face_region[boundary] >= 0),
                        "存在未归属区域的边界面")
        self.assertTrue(np.all(res.face_region[~boundary] == -1),
                        "内部面不应归属区域")

    def test_region_by_position(self):
        """inlet 面 z ≈ -0.5、outlet 面 z ≈ +0.5、wall 面在四侧。"""
        res = self.res
        for fi, fids in enumerate(res.faces):
            rid = int(res.face_region[fi])
            if rid < 0:
                continue
            cz = float(res.vertices[np.asarray(fids)][:, 2].mean())
            if rid == 0:
                self.assertLess(cz, -0.45)
            elif rid == 1:
                self.assertGreater(cz, 0.45)
            else:
                self.assertGreater(-abs(cz), -0.45)  # |cz| < 0.45

    def test_stats_surface_regions(self):
        st = self.res.stats()
        self.assertEqual(st["n_boundary_faces"],
                         int(np.count_nonzero(np.asarray(
                             self.res.face_neigh) < 0)))
        regions = st["surface_regions"]
        self.assertEqual(set(regions), {"inlet", "outlet", "wall"})
        self.assertTrue(all(n > 0 for n in regions.values()))

    def test_gph_roundtrip(self):
        """LS_SurfaceRegions 写出 → gphstats 读回（名字/面数/面号一致）。"""
        with tempfile.TemporaryDirectory() as td:
            oct_p, gph_p = voxmesh.write_outputs(
                self.res, Path(td) / "regions")
            data = gph_p.read_bytes()
            summary = dict(gphstats.surface_regions_summary(data))
            self.assertEqual(set(summary), {"inlet", "outlet", "wall"})
            face_ids = gphstats.surface_region_face_ids(data)
            neigh = np.asarray(self.res.face_neigh)
            all_ids = np.concatenate(list(face_ids.values()))
            # 区域面号 ↔ 边界面完全覆盖且不重复
            self.assertEqual(len(all_ids), int(np.count_nonzero(neigh < 0)))
            self.assertEqual(len(np.unique(all_ids)), len(all_ids))
            # 每区域面数与内存 face_region 一致
            for name, ids in face_ids.items():
                rid = _REGION_NAMES.index(name)
                self.assertEqual(
                    len(ids), int(np.count_nonzero(
                        self.res.face_region == rid)))
            # 面号指向的确实是边界面
            self.assertTrue(np.all(neigh[all_ids] < 0))


class TestMdlRegionPath(unittest.TestCase):
    def test_mdl_roundtrip_regions(self):
        """write_mdl(frid+regions) → build_from_mdl 自动携带区域进 GPH。"""
        pts, tris, tri_region = _region_box_surface()
        # write_mdl 以四边形面 + frid 写（每 quad 一条 frid）
        faces = [np.asarray(q, dtype=np.int64) for q, _ in _QUADS]
        frid = [rid for _, rid in _QUADS]
        regions = [(name, i) for i, name in enumerate(_REGION_NAMES)]
        with tempfile.TemporaryDirectory() as td:
            mdl_path = Path(td) / "box_part.mdl"
            mdlmod.write_mdl(mdl_path, pts, faces, frid=frid,
                             surface_regions=regions)
            model = mdlmod.parse_mdl(str(mdl_path))
            self.assertEqual(
                {r.name: int(r.index) for r in model.surface_regions},
                {"inlet": 0, "outlet": 1, "wall": 2})
            params = voxmesh.VoxelMeshParams(
                initial_depth=2, max_depth=3, max_cells=100_000,
                rough_poly=True)
            res, _oct_p, gph_p = voxmesh.build_from_mdl(
                mdl_path, Path(td) / "out", params)
            self.assertEqual(res.region_names, _REGION_NAMES)
            neigh = np.asarray(res.face_neigh)
            self.assertTrue(np.all(res.face_region[neigh < 0] >= 0))
            summary = dict(gphstats.surface_regions_summary(
                gph_p.read_bytes()))
            self.assertEqual(set(summary), {"inlet", "outlet", "wall"})


if __name__ == "__main__":
    unittest.main()
