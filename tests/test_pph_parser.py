#!/usr/bin/env python3
"""pphdecoding 解析器健全性测试（对 tests/ 下的样例 pph）。

用法::

    python tests/test_pph_parser.py            # 全部测试
    python tests/test_pph_parser.py -v         # 详细输出
"""

import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import crdlfld  # noqa: E402
import mdl as mdl_mod  # noqa: E402
import oct as oct_mod  # noqa: E402
import pphxml  # noqa: E402
import sctsnapshot  # noqa: E402
from pph_parser import PphArchive  # noqa: E402

PPH = ROOT / "tests" / "laptop_thermal_steady_scaled_v3_fanonly_simple.pph"
EXTRACTED = ROOT / "tests" / "laptop_thermal_steady_scaled_v3_fanonly_simple"


class TestContainer(unittest.TestCase):
    def test_is_zip(self):
        self.assertTrue(zipfile.is_zipfile(PPH))

    def test_member_list(self):
        arch = PphArchive.open(str(PPH))
        names = [m.name for m in arch.members]
        self.assertEqual(names, [
            "main.js", "main.prp", "main.sctsnapshot", "main.xenv", "main.xml",
            "meshinggroup1.gph", "meshinggroup1.oct",
            "meshinggroup1_part.mdl", "meshinggroup1_ridge.mdl",
        ])

    def test_extract_roundtrip(self):
        arch = PphArchive.open(str(PPH))
        for m in arch.members:
            ref = EXTRACTED / m.name
            data = arch.read_member(m.name)
            self.assertEqual(len(data), m.size)
            self.assertEqual(data, ref.read_bytes(),
                             f"{m.name} 解包内容与参考目录不一致")


class TestTextMembers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arch = PphArchive.open(str(PPH))

    def test_main_js(self):
        js = pphxml.parse_main_js(self.arch.read_member("main.js"))
        self.assertIn("usr_input", js.functions())
        self.assertFalse(js.has_user_code())

    def test_main_prp(self):
        prp = pphxml.parse_prp(self.arch.read_member("main.prp"))
        self.assertEqual(len(prp.groups), 30)
        self.assertIn("gas(incompressible)", prp.group_names())

    def test_main_xenv(self):
        xenv = pphxml.parse_xenv(self.arch.read_member("main.xenv"))
        self.assertEqual(xenv.get("TYPE", "PROJECT_TYPE"), "scflow")
        self.assertEqual(xenv.get("UNIT", "MODEL_LENGTH_UNIT"), "m")

    def test_main_xml_indexed_tags(self):
        mx = pphxml.parse_main_xml(self.arch.read_member("main.xml"))
        self.assertEqual(mx.project_name,
                         "laptop_thermal_steady_scaled_v3_fanonly_simple")
        conds = mx.conditions()
        self.assertEqual(len(conds), 23)
        first = mx.condition_summary(conds[0])
        self.assertEqual(first["type"], "CondBoundaryFlowIO")
        # 索引标签还原
        self.assertEqual(pphxml.restore_index("SECTITEM__IDX3"), ("SECTITEM", 3))


class TestSnapshot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap = sctsnapshot.SctSnapshot.load(
            str(EXTRACTED / "main.sctsnapshot"))

    def test_top_level(self):
        tags = [r.tag for r in self.snap.records]
        self.assertEqual(tags, [
            "CADTHRUVERSION", "TREESTRUCT", "CADTHRUVERSION", "VIEWSTRUCT",
            "CADTHRUVERSION", "TOPASSYSTRUCT", "TOPASSYSTRUCT", "BSGSEX",
            "CADTHRUVERSION", "QUEUESTRUCT", "CADTHRUVERSION", "QUEUESTRUCT",
            "CADTHRUVERSION", "QUEUESTRUCT",
        ])
        self.assertEqual(self.snap.records[0].value, 8)
        self.assertEqual(self.snap.skipped_bytes, 0)

    def test_bodies_zip_headers(self):
        bodies = self.snap.bodies()
        self.assertEqual(len(bodies), 4)
        for b in bodies:
            z = b["zip"]
            self.assertGreater(z.uncompressed_size, 0)
            self.assertGreater(z.compressed_size, 0)
            self.assertEqual(len(z.raw), 28 + len(z.payload))

    def test_meshing_groups(self):
        groups = self.snap.meshing_groups()
        names = [g["name"] for g in groups]
        self.assertIn("MeshingGroup_1_Default", names)

    def test_face_groups(self):
        fgs = self.snap.face_groups()
        names = [g.get("name") for g in fgs]
        self.assertIn("open", names)


@unittest.skipUnless(sctsnapshot.lzms_available(), "需要 Windows cabinet.dll LZMS")
class TestLzmsZipBlobs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap = sctsnapshot.SctSnapshot.load(
            str(EXTRACTED / "main.sctsnapshot"))
        cls.oct = oct_mod.parse_oct(str(EXTRACTED / "meshinggroup1.oct"))

    def test_body_pkbody3(self):
        bodies = self.snap.decompress_bodies()
        self.assertEqual(len(bodies), 4)
        expect = [
            (17604, True),   # 非 8 倍数 → 零填充块 → "尾标"出现
            (116572, True),
            (7824, False),   # 8 倍数 → 无零填充块
            (3040, False),
        ]
        prefixes = []
        for b, (sz, has_ck) in zip(bodies, expect):
            self.assertEqual(b["pkbody3"].logical_size, sz)
            self.assertEqual(len(b["pkbody3"].data), (sz + 7) // 8 * 8)
            self.assertEqual(b["pkbody3"].checksum is not None, has_ck)
            self.assertEqual(len(b["zip"].decompress()), b["zip"].uncompressed_size)
            prefixes.append(b["pkbody3"].schema_prefix)
        # 四个体共享 400 字节 schema 前缀
        self.assertTrue(all(p == prefixes[0] for p in prefixes))
        self.assertEqual(len(prefixes[0]), sctsnapshot.PKBODY3_SCHEMA_PREFIX_LEN)

    def test_body_pkbody3_decrypt(self):
        """Blowfish-LE 解密 → Parasolid 二进制传输流（含 SCH schema）。"""
        bodies = self.snap.decompress_bodies()
        for b in bodies:
            pt = b["pkbody3"].decrypt()
            self.assertEqual(len(pt), b["pkbody3"].logical_size)
            self.assertIn(b"TRANSMIT FILE created by modeller version", pt[:64])
            self.assertIn(b"SCH_3701153", pt[:128])
        # 加解密互逆：物理密文（ceil8）全块可还原
        from blowfish_le import decrypt_ecb, encrypt_ecb
        ct = bodies[0]["pkbody3"].data
        self.assertEqual(encrypt_ecb(decrypt_ecb(ct)), ct)
        pt0 = bodies[0]["pkbody3"].decrypt()
        pad8 = pt0 + b"\x00" * ((-len(pt0)) % 8)
        self.assertEqual(decrypt_ecb(encrypt_ecb(pad8))[: len(pt0)], pt0)

    def test_octree_mdl_body_laptop(self):
        m = self.snap.octree_mdl_body()
        self.assertIsNotNone(m)
        self.assertEqual((m.n_vertices, m.n_fins, m.n_facets), (410, 1216, 808))
        self.assertEqual(m.facets.shape, (808, 9))
        self.assertEqual(len(m.vertices), 410)

    def test_faceting_rules(self):
        recs = self.snap.decompress_faceting_rules()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].tag, "FACETINGRULES")
        self.assertGreater(len(recs[0].children), 10)

    def test_octree_equals_oct_member(self):
        crdl = self.snap.octree_crdlfld_bytes()
        self.assertIsNotNone(crdl)
        oct_path = EXTRACTED / "meshinggroup1.oct"
        self.assertEqual(crdl, oct_path.read_bytes())
        tags = [r.tag for r in self.snap.decompress_octree(max_depth=2)]
        self.assertIn("OCTREEBODY", tags)
        self.assertIn("OCTREEDIVISION", tags)
        self.assertIn("OCTREEREGION", tags)

    def test_octree_division_region(self):
        import numpy as np
        div = self.snap.octree_division()
        self.assertIsNotNone(div)
        # 满八叉树: ceil(n/8) == n_internal+1
        self.assertEqual(len(div), self.oct.n_internal + 1)
        self.assertEqual(len(div), (self.oct.n_octants + 7) // 8)

        # DLL 写入端: 前序 + 子序 (1,3,2,0,5,7,6,4) + LSB 打包
        # 重放应与 OCTREEDIVISION 字节级一致
        ref = self.oct.refinement
        n = len(ref)
        children = [None] * n
        stack = []
        if ref[0]:
            children[0] = [-1] * 8
            stack.append([0, 0])
        for pos in range(1, n):
            parent, slot = stack[-1]
            children[parent][slot] = pos
            stack[-1][1] = slot + 1
            if stack[-1][1] == 8:
                stack.pop()
            if ref[pos]:
                children[pos] = [-1] * 8
                stack.append([pos, 0])
        bits = []
        perm = list(sctsnapshot.SctSnapshot.OCTREE_DIVISION_CHILD_ORDER)

        def dfs(i):
            if children[i] is None:
                bits.append(0)
                return
            bits.append(1)
            for p in perm:
                dfs(children[i][p])

        dfs(0)
        packed = np.packbits(np.array(bits, dtype=np.uint8), bitorder="little")
        self.assertTrue(np.array_equal(packed, div))

        reg = self.snap.octree_region(n_octants=self.oct.n_octants)
        self.assertIsNotNone(reg)
        flags = reg["flags"]
        self.assertEqual(reg["order"], "postorder")
        self.assertEqual(len(flags), self.oct.n_octants)
        self.assertEqual(set(np.unique(flags).tolist()), {0, 1})
        self.assertGreater(reg["padding"], 0)
        pad_bytes = self.snap._octree_bytearray("OCTREEREGION")[self.oct.n_octants:]
        self.assertTrue(np.all(np.frombuffer(pad_bytes, dtype=np.uint8) == 0))

        # 后序→前序重映射: 与 refinement 同下标; box 上 flag=1 全为叶子
        flags_oct = self.snap.octree_region_as_oct_order(ref)
        self.assertEqual(len(flags_oct), n)
        self.assertEqual(int(flags_oct.sum()), int(flags.sum()))
        self.assertTrue(((flags_oct == 1) & (ref == 1)).sum() == 0)


class TestValueUnits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap = sctsnapshot.SctSnapshot.load(
            str(EXTRACTED / "main.sctsnapshot"))

    def test_mesh_tolerances_are_f64(self):
        for tag in ("MESH_CHORDTOL", "MESH_CHORDANG",
                    "MESH_SURFTOL", "MESH_SURFANG"):
            recs = list(self.snap.find_all(tag))
            self.assertEqual(len(recs), 1)
            self.assertIsInstance(recs[0].value, float)
            self.assertEqual(recs[0].value, 0.0)

    def test_lengthvwu(self):
        recs = list(self.snap.find_all("LENGTHVWU"))
        self.assertGreaterEqual(len(recs), 1)
        typed = [r.value for r in recs
                 if isinstance(r.value, sctsnapshot.ValueWithUnit)]
        self.assertEqual(len(typed), len(recs))
        # 至少有一处可读的非零长度
        self.assertTrue(any(abs(v.value) > 1e-6 for v in typed))
        self.assertTrue(all(v.unit_type == 1 for v in typed))

    def test_dpointu(self):
        recs = list(self.snap.find_all("DPOINTU"))
        self.assertGreaterEqual(len(recs), 1)
        for r in recs:
            self.assertIsInstance(r.value, sctsnapshot.DPointU)
            self.assertEqual(r.value.unit_types, (1, 1, 1))
        # 至少一处坐标非全垃圾（本例第三点约 (0.0062, -0.001, 0.0205)）
        sens = [r.value for r in recs
                if all(abs(c) < 1e3 for c in r.value.xyz)
                and any(abs(c) > 1e-6 for c in r.value.xyz)]
        self.assertGreaterEqual(len(sens), 1)


class TestOctree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = oct_mod.parse_oct(str(EXTRACTED / "meshinggroup1.oct"))

    def test_counts(self):
        m = self.model
        self.assertEqual(m.n_octants, 3_960_249)
        self.assertEqual(m.n_internal, 495_031)
        self.assertEqual(m.n_leaves, 3_465_218)
        # 完整八叉树不变量：n = 1 + 8 * 内部节点数
        self.assertEqual((m.n_octants - 1) % 8, 0)
        self.assertEqual((m.n_octants - 1) // 8, m.n_internal)

    def test_root_box(self):
        mn, mx = self.model.root_min, self.model.root_max
        self.assertAlmostEqual(mn[0], -59.335999, places=5)
        self.assertAlmostEqual(mx[2], 86.036001, places=5)

    def test_leaves_cover_root(self):
        leaves = list(self.model.iter_leaves(max_leaves=2000))
        # 第一个叶子从根包围盒最小角开始
        mn, _, _ = leaves[0]
        for a, b in zip(mn, self.model.root_min):
            self.assertAlmostEqual(a, b, places=6)

    def test_block_ids(self):
        self.assertTrue((self.model.block_id == -1).all())


class TestMdl(unittest.TestCase):
    def test_part_mdl(self):
        m = mdl_mod.parse_mdl(str(EXTRACTED / "meshinggroup1_part.mdl"))
        self.assertEqual(m.n_vertices, 21889)
        self.assertEqual(m.n_faces, 43766)
        # 全三角面片：conn == 3 * n_faces
        self.assertEqual(len(m.conn), 3 * m.n_faces)
        self.assertEqual(int(m.face_offsets[-1]), len(m.conn))
        self.assertEqual(len(m.edge_state), len(m.conn))
        import numpy as np
        self.assertEqual(set(np.unique(m.face_type).tolist()), {133})
        self.assertLess(int(m.conn.max()), m.n_vertices)
        self.assertIn("FluidRegion", m.volume_regions)
        names = [r.name for r in m.surface_regions]
        self.assertIn("impeller1", names)

    def test_ridge_mdl(self):
        m = mdl_mod.parse_mdl(str(EXTRACTED / "meshinggroup1_ridge.mdl"))
        self.assertEqual(m.n_vertices, 792506)
        self.assertEqual(m.n_faces, 810057)
        import numpy as np
        types = dict(zip(*[x.tolist() for x in np.unique(
            m.face_type, return_counts=True)]))
        self.assertEqual(types, {133: 35114, 134: 774943})
        self.assertEqual(int(m.face_offsets[-1]), len(m.conn))


class TestGph(unittest.TestCase):
    def test_sections(self):
        with crdlfld.CrdlFldFile.load(str(EXTRACTED / "meshinggroup1.gph")) as f:
            names = [s.name for s in f.sections]
            for expect in ("LS_CvolIdOfElements", "LS_Links", "LS_Nodes",
                           "LS_SurfaceRegions", "LS_VolumeRegions", "LS_Parts",
                           "LS_Assemblies"):
                self.assertIn(expect, names)
            meta = f.metadata()
            self.assertEqual(meta.get("Application"), "SCTpre")


BOX = ROOT / "tests" / "box"


@unittest.skipUnless(
    sctsnapshot.lzms_available() and (BOX / "main.sctsnapshot").exists(),
    "需要 Windows LZMS 与 tests/box")
class TestBoxPph(unittest.TestCase):
    """0.01³ 立方体 + open 边界的最小样例。"""

    @classmethod
    def setUpClass(cls):
        cls.snap = sctsnapshot.SctSnapshot.load(str(BOX / "main.sctsnapshot"))
        cls.oct = oct_mod.parse_oct(str(BOX / "meshinggroup1.oct"))

    def test_single_body_pkbody3_pad_trailer(self):
        bodies = self.snap.decompress_bodies()
        self.assertEqual(len(bodies), 1)
        b = bodies[0]["pkbody3"]
        self.assertEqual(b.logical_size, 7643)
        self.assertEqual(len(b.data), 7648)  # ceil8 物理密文
        self.assertEqual(b.checksum, sctsnapshot.PKBODY3_TRAILER_MARK)
        self.assertEqual(b.pad, b"\xb1")  # 零填充块密文碎片，非独立字段
        # schema 前缀与 laptop 样例一致
        lap = sctsnapshot.SctSnapshot.load(str(EXTRACTED / "main.sctsnapshot"))
        self.assertEqual(b.schema_prefix,
                         lap.decompress_bodies()[0]["pkbody3"].schema_prefix)

    def test_octree_mdl_body_cube(self):
        m = self.snap.octree_mdl_body()
        self.assertIsNotNone(m)
        self.assertEqual((m.n_vertices, m.n_fins, m.n_facets), (8, 19, 12))
        self.assertAlmostEqual(float(m.bbox_min[0]), 0.0, places=6)
        self.assertAlmostEqual(float(m.bbox_max[0]), 0.01, places=5)
        names = [g["name"] for g in m.face_groups]
        self.assertIn("open", names)
        # 12 个三角面 = 立方体 6 面 × 2
        self.assertEqual(len(m.facets), 12)
        self.assertTrue((m.facet_flags == 1).all())
        self.assertTrue((m.fin_flags == 1).all())

    def test_csid_single_closed_volume(self):
        import numpy as np
        m = mdl_mod.parse_mdl(str(BOX / "meshinggroup1_part.mdl"))
        b1, b2 = m.csid
        self.assertTrue((b1 == 0).all())
        self.assertTrue((b2 == 1).all())
        self.assertEqual(set(np.unique(m.frid).tolist()), {0})

    def test_octree_scale(self):
        self.assertEqual(self.oct.n_octants, 2249)
        self.assertEqual(self.oct.n_internal, 281)
        div = self.snap.octree_division()
        self.assertEqual(len(div), 282)
        reg = self.snap.octree_region(n_octants=self.oct.n_octants)
        self.assertEqual(len(reg["flags"]), 2249)
        self.assertGreater(reg["padding"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
