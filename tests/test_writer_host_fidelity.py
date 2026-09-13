"""写端宿主保真回归：MDL / OCT / GPH 往返必须**逐字节等于宿主产物**。

背景（2026-09-13 P2 验收）：三个网格写端此前与宿主布局存在多处偏差
（容器头缺第 4 个 I4、节头缺尾随 I4(32)、节体缺哨兵、数组描述符未逐块交错、
Application/Encoding 描述符维序、区域记录缺 desc(1,255,1)、区域节尾哨兵末字段
误为 0、EdgeState 描述符 type 误为 4 …）。逐项修正后，对 `tests/box` 下的
**宿主原生产物**做解析→写出往返，差异收敛到 **0**（Date 参数从源文件读出后
完全一致）。本文件锁定该保真度——任何写端布局回退都会立刻变红。
"""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gphstats  # noqa: E402
import mdl  # noqa: E402
import oct as octmod  # noqa: E402

GPH = ROOT / "tests" / "box" / "meshinggroup1.gph"
MDL = ROOT / "tests" / "box" / "meshinggroup1_part.mdl"
OCT = ROOT / "tests" / "box" / "meshinggroup1.oct"


def _date_of(data: bytes) -> int:
    """从 CRDL-FLD 的 Date 节读取 I4 值（写出时回填，保证往返零差异）。"""
    name = b"Date" + b" " * 28
    i = data.find(name)
    if i < 4:
        return 20260812
    body = i + 36                      # 40 字节节头之后
    # body = desc(4,1,1) + desc(4,date,4)；值在第二个描述符的第 3 个字段
    return struct.unpack_from(">i", data, body + 16 + 8)[0]


class TestWriterHostFidelity(unittest.TestCase):
    @unittest.skipUnless(GPH.is_file(), "golden gph missing")
    def test_gph_roundtrip_byte_exact(self):
        raw = GPH.read_bytes()
        mesh = gphstats.parse_mesh(raw)
        fo = np.asarray(mesh["face_offsets"])
        faces = [np.asarray(mesh["conn"][fo[i]:fo[i + 1]])
                 for i in range(len(fo) - 1)]
        cvol = gphstats.cvol_ids(raw)
        info = gphstats.element_info(raw)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "rt.gph"
            gphstats.write_gph_volume(
                out, mesh["vertices"], faces, mesh["owner"], mesh["neigh"],
                app="SCTpre", date=_date_of(raw), cvol=cvol,
                surface_regions=[(n, ids) for n, ids in
                                 gphstats.surface_region_face_ids(raw).items()] or None,
                volume_regions=gphstats.volume_region_names(raw) or None,
                parts=gphstats.parts_summary(raw, cvol) or None,
                assemblies=gphstats.assemblies_xml(raw),
                element_info=(info[1] if info else None))
            got = out.read_bytes()
        self.assertEqual(len(got), len(raw),
                         "GPH 长度必须与宿主一致")
        self.assertEqual(got, raw, "GPH 往返必须逐字节等于宿主产物")

    @unittest.skipUnless(MDL.is_file(), "golden mdl missing")
    def test_mdl_roundtrip_byte_exact(self):
        raw = MDL.read_bytes()
        m = mdl.parse_mdl(MDL)
        faces = [m.face_nodes(i) for i in range(m.n_faces)]
        b1, b2 = m.csid_sides
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "rt.mdl"
            mdl.write_mdl(out, m.xyz, faces, csid=(b1, b2), frid=m.frid,
                          edge_state=m.edge_state, node_state=m.node_state,
                          date=_date_of(raw),
                          surface_regions=[(r.name, r.index)
                                           for r in (m.surface_regions or [])] or None,
                          closed_volumes=getattr(m, "closed_volumes", None),
                          volume_regions=getattr(m, "volume_regions", None))
            got = out.read_bytes()
        self.assertEqual(len(got), len(raw), "MDL 长度必须与宿主一致")
        self.assertEqual(got, raw, "MDL 往返必须逐字节等于宿主产物")

    @unittest.skipUnless(OCT.is_file(), "golden oct missing")
    def test_oct_roundtrip_byte_exact(self):
        raw = OCT.read_bytes()
        m = octmod.parse_oct(OCT)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "rt.oct"
            octmod.write_oct(out, m.root_min, m.root_max,
                             refinement=m.refinement, block_id=m.block_id,
                             unit=m.unit or "m", date=_date_of(raw))
            got = out.read_bytes()
        self.assertEqual(len(got), len(raw), "OCT 长度必须与宿主一致")
        self.assertEqual(got, raw, "OCT 往返必须逐字节等于宿主产物")


if __name__ == "__main__":
    unittest.main()
