#!/usr/bin/env python3
"""GPH cvol/区域/Parts 写端回归：box 网格数据 round-trip。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import gphstats  # noqa: E402

BOX_GPH = ROOT / "tests" / "box" / "meshinggroup1.gph"


def _mesh_to_faces(mesh):
    off = mesh["face_offsets"]
    conn = mesh["conn"]
    return [conn[off[i]:off[i + 1]].tolist() for i in range(mesh["n_faces"])]


class TestSurfaceRegionNameWrite(unittest.TestCase):
    """LS_SurfaceRegions 名表写端：原地改名（宿主安全）+ 追加（格式级）。

    宿主行为矩阵见 REANALYSIS §6.2（追加触发宿主无界重建，禁用）；
    此处锁定字节级语义：改名后 parser 可见新名、面数组与节长不变。
    """

    def test_rename_in_place(self):
        with gphstats.open_buffer(str(BOX_GPH)) as data:
            srs_before = gphstats.surface_regions_summary(data)
            ids_before = gphstats.surface_region_face_ids(data)
            sec = gphstats._find_section(data, "LS_SurfaceRegions")
            sec_len = sec.end - sec.start
            new = gphstats.rename_surface_region(data, "open", "ope9")

        srs_after = gphstats.surface_regions_summary(new)
        ids_after = gphstats.surface_region_face_ids(new)
        sec2 = gphstats._find_section(new, "LS_SurfaceRegions")
        self.assertNotIn(("open", srs_before[0][1]), srs_after)
        self.assertIn("ope9", [n for n, _ in srs_after])
        self.assertEqual(len(new), len(data))          # 等长约束
        self.assertEqual(sec2.end - sec2.start, sec_len)
        np.testing.assert_array_equal(ids_after["ope9"], ids_before["open"])
        # 其余区域不受影响
        for name in [n for n, _ in srs_before if n != "open"]:
            np.testing.assert_array_equal(ids_after[name], ids_before[name])

    def test_append_grows_section(self):
        with gphstats.open_buffer(str(BOX_GPH)) as data:
            n_before = len(gphstats.surface_regions_summary(data))
            new = gphstats.append_surface_region(data, "@P5Append")
        srs = gphstats.surface_regions_summary(new)
        self.assertGreater(len(new), len(data))
        self.assertIn("@P5Append", [n for n, _ in srs])
        self.assertEqual(len(srs), n_before + 1)

    def test_rename_unknown_is_noop(self):
        with gphstats.open_buffer(str(BOX_GPH)) as data:
            new = gphstats.rename_surface_region(data, "__nope__", "x")
        self.assertEqual(bytes(new), bytes(data))


class TestGphWriteSections(unittest.TestCase):
    def test_box_roundtrip(self):
        with gphstats.open_buffer(str(BOX_GPH)) as data:
            mesh = gphstats.parse_mesh(data)
            cvol = gphstats.cvol_ids(data)
            srs = gphstats.surface_regions_summary(data)
            face_ids = gphstats.surface_region_face_ids(data)
            vr = gphstats.string_list(data, "LS_VolumeRegions")
            parts = gphstats.parts_summary(data, cvol)

        faces = _mesh_to_faces(mesh)
        regions = [(name, face_ids[name]) for name, _ in srs]
        p = ROOT / "_roundtrip.gph"
        try:
            gphstats.write_gph_volume(
                p, mesh["vertices"], faces, mesh["owner"], mesh["neigh"],
                cvol=cvol, volume_regions=vr,
                surface_regions=regions, parts=parts)
            with gphstats.open_buffer(str(p)) as raw:
                s = gphstats.summarize(raw)
                face_ids2 = gphstats.surface_region_face_ids(raw)
        finally:
            p.unlink(missing_ok=True)

        self.assertEqual(s["cvol_unique"], np.unique(cvol).tolist())
        self.assertEqual(s["volume_regions"], vr)
        self.assertEqual(s["surface_regions"], srs)
        # face ids 逐区域一致
        for name, _ in srs:
            self.assertTrue(np.array_equal(face_ids2[name], face_ids[name]))
        # parts 名称一致
        self.assertEqual([x[0] for x in s["parts"]], [x[0] for x in parts])
        # 网格拓扑一致（944 单元）
        self.assertEqual(s["links"]["n_cells"], 944)
        self.assertEqual(s["links"]["n_faces"], 3168)


if __name__ == "__main__":
    unittest.main()