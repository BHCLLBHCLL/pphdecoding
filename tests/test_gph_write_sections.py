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