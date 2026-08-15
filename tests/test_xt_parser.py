#!/usr/bin/env python3
"""P3：完整 XT 解码器（schema 加载 + 文本/二进制解析）回归。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import parasolid  # noqa: E402

BOX = ROOT / "tests" / "box"
FIXTURE = BOX / "_block_bin.x_b"


class TestSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scflowpre_probe import programs_dir
        p = Path(programs_dir()) / "Schemas" / "sch_37102.sch_txt"
        if not p.exists():
            raise unittest.SkipTest("sch_37102 not installed")
        cls.sch = parasolid.load_schema(str(p))

    def test_node_count(self):
        self.assertGreater(len(self.sch), 200)

    def test_body_fields(self):
        nt = self.sch[12]
        self.assertEqual(nt.name, "BODY")
        self.assertEqual(len(nt.fields), 40)
        names = [f.name for f in nt.fields]
        for expect in ("lattice", "mesh", "polyline", "owner",
                       "boundary_lattice", "boundary_mesh",
                       "boundary_polyline", "mesh_offset_data",
                       "index_map_offset", "lowest_node_id", "child"):
            self.assertIn(expect, names)

    def test_lattice_node(self):
        self.assertEqual(self.sch[222].name, "LATTICE")
        self.assertEqual(len(self.sch[222].fields), 8)

    def test_mesh_polyline(self):
        self.assertEqual(self.sch[200].name, "POLYLINE")
        self.assertEqual(self.sch[201].name, "MESH")

    def test_field_type_table(self):
        self.assertEqual(parasolid.FIELD_TYPES["d"][0], "int")
        self.assertEqual(parasolid.FIELD_TYPES["f"][0], "double")
        self.assertEqual(parasolid.FIELD_TYPES["p"][0], "pointer")

    def test_node_classes(self):
        self.assertEqual(parasolid.NODE_CLASSES[1006], "SURFACE")
        self.assertEqual(parasolid.NODE_CLASSES[1040], "SURFACE_OWNER")
        self.assertEqual(parasolid.NODE_CLASSES[1005], "PART")


class TestParseTextXt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FIXTURE.exists():
            raise unittest.SkipTest("_block_bin.x_b fixture missing")

    def test_full_parse(self):
        m = parasolid.parse_text_xt(
            FIXTURE.read_text(encoding="ascii", errors="replace"))
        self.assertFalse(getattr(m, "parse_error", False))
        self.assertEqual(m.schema, "SCH_3701153_37102_13006")
        self.assertEqual(len(m.order), 87)
        # 立方体完整 B-rep 拓扑计数
        from collections import Counter
        counts = Counter(n.name for n in m.order)
        self.assertEqual(counts["BODY"], 1)
        self.assertEqual(counts["SHELL"], 2)
        self.assertEqual(counts["FACE"], 6)
        self.assertEqual(counts["LOOP"], 6)
        self.assertEqual(counts["EDGE"], 12)
        self.assertEqual(counts["VERTEX"], 8)
        self.assertEqual(counts["PLANE"], 6)
        self.assertEqual(counts["LINE"], 12)
        self.assertEqual(counts["POINT"], 8)
        self.assertEqual(counts["HALFEDGE"], 24)
        self.assertEqual(counts["REGION"], 2)

    def test_body_refs(self):
        m = parasolid.parse_text_xt(
            FIXTURE.read_text(encoding="ascii", errors="replace"))
        b = m.order[0]
        self.assertEqual(b.name, "BODY")
        self.assertEqual(b.index, 1)
        self.assertEqual(b.fields["highest_node_id"], 62)
        self.assertEqual(b.fields["shell"], 2)
        self.assertEqual(b.fields["edge"], 7)
        self.assertEqual(b.fields["vertex"], 8)
        self.assertEqual(b.fields["region"], 6)

    def test_point_coords(self):
        m = parasolid.parse_text_xt(
            FIXTURE.read_text(encoding="ascii", errors="replace"))
        pts = m.by_type(29)
        self.assertEqual(len(pts), 8)
        # create_solid_block((1,1,1))：x,y 在 +-0.5，z 在 {0,1}
        for p in pts:
            x, y, z = p.fields["pvec"]
            self.assertAlmostEqual(abs(x), 0.5, delta=1e-9)
            self.assertAlmostEqual(abs(y), 0.5, delta=1e-9)
            self.assertIn(z, (0.0, 1.0))


class TestParseBinaryXt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p = BOX / "_pk3.bin"
        if not p.exists():
            raise unittest.SkipTest("_pk3.bin fixture missing")
        cls.model = parasolid.parse_binary_xt(p.read_bytes())

    def test_header(self):
        self.assertEqual(self.model.schema, "SCH_3701153_37102_13006")
        self.assertEqual(self.model.version,
                         ": TRANSMIT FILE created by modeller version 3701153")
        self.assertEqual(self.model.max_node_types, 239)

    def test_nodes_parsed(self):
        self.assertGreaterEqual(len(self.model.order), 1)
        self.assertEqual(self.model.order[0].name, "BODY")


class TestOldApi(unittest.TestCase):
    def test_parse_text_entities_still_works(self):
        p = BOX / "box.x_t"
        if not p.exists():
            self.skipTest("box.x_t missing")
        r = parasolid.parse_text_entities(p.read_text(errors="replace"))
        self.assertEqual(r["header"]["FORMAT"], "text")
        self.assertIn(51, r["type_counts"])


if __name__ == "__main__":
    unittest.main()
