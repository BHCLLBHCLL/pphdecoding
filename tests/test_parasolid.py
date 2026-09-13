"""3.1 Parasolid 传输流部分提取（schema / 字段名 / 实体类型）。"""

import os
import tempfile
import unittest
import zipfile

import parasolid
import sctsnapshot


def _load_snap(pph_path: str) -> sctsnapshot.SctSnapshot:
    with zipfile.ZipFile(pph_path) as z:
        raw = z.read("main.sctsnapshot")
    tmp = os.path.join(tempfile.gettempdir(), "snap_ps3.bin")
    with open(tmp, "wb") as f:
        f.write(raw)
    return sctsnapshot.SctSnapshot.load(tmp)


BOX_PPH = r"box.pph"
LAPTOP_PPH = r"tests\laptop_thermal_steady_scaled_v3_fanonly_simple.pph"


class TestParasolidExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.box = _load_snap(BOX_PPH).bodies()[0]["zip"].decompress_body()
        cls.laptop = _load_snap(LAPTOP_PPH)

    def test_header_and_schema(self):
        p = parasolid.parse_transmit(self.box.decrypt())
        self.assertEqual(p.version, 3701153)
        self.assertEqual(p.schema, "SCH_3701153_37102_13006")
        self.assertIn("TRANSMIT FILE created by modeller version",
                      p.header_line)

    def test_box_field_names(self):
        p = parasolid.parse_transmit(self.box.decrypt())
        names = p.field_names
        expected = [
            "lattice", "mesh", "polyline", "owner",
            "boundary_lattice", "boundary_mesh", "boundary_polyline",
            "index_map_offset", "index_mapR", "node_id_index_mapR",
            "schema_embedding_mapR", "child", "lowest_node_id",
            "mesh_offset_data", "list_type", "notransmit",
            "finger_index", "finger_block", "frame", "legal_owners",
        ]
        for name in expected:
            self.assertIn(name, names, name)
        self.assertEqual(len(p.fields), 22)

    def test_box_entities_and_sdl(self):
        p = parasolid.parse_transmit(self.box.decrypt())
        self.assertEqual(p.entities,
                         ["CADthru/PKEdge", "CADthru/PKFace",
                          "CADthru/PKVertex"])
        self.assertEqual(p.sdl_attributes,
                         ["SDL/TYSA_NAME", "SDL/TYSA_LAYER",
                          "SDL/TYSA_UNAME"])

    def test_all_bodies_parse(self):
        for b in self.laptop.bodies():
            p = parasolid.parse_transmit(b["zip"].decompress_body().decrypt())
            self.assertEqual(p.version, 3701153)
            self.assertEqual(p.schema, "SCH_3701153_37102_13006")
            self.assertEqual(len(p.fields), 22)
            self.assertTrue(p.entities)

    def test_field_scan_rejects_binary_noise(self):
        # 随机二进制不应产生字段
        import random

        rng = random.Random(42)
        junk = bytes(rng.randrange(256) for _ in range(8192))
        self.assertEqual(parasolid.scan_fields(junk), [])
        # 可打印文本中也不应误报（无 token+len 帧）
        text = (b"the quick brown fox jumps over the lazy dog" * 20)
        self.assertEqual(parasolid.scan_fields(text), [])

    def test_summary(self):
        p = parasolid.parse_transmit(self.box.decrypt())
        s = p.summary()
        self.assertIn("version=3701153", s)
        self.assertIn("lattice($CCCI)", s)
        self.assertIn("CADthru/PKEdge", s)


if __name__ == "__main__":
    unittest.main()
