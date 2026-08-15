#!/usr/bin/env python3
"""P2: CADthru 分面二进制 schema 字段表 + 数据区偏移回归。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import parasolid  # noqa: E402
import sctsnapshot  # noqa: E402

BOX_SNAP = ROOT / "tests" / "box" / "main.sctsnapshot"


def _decrypt_pkbody3() -> bytes:
    snap = sctsnapshot.SctSnapshot.from_bytes(BOX_SNAP.read_bytes())

    def walk(recs):
        for r in recs:
            if r.tag == "ZIPBODYBYTES":
                v = r.value
                zb = (v if isinstance(v, sctsnapshot.ZipBlob)
                      else sctsnapshot.ZipBlob.parse(bytes(v)))
                return zb.decompress_body().decrypt()
            if r.children:
                x = walk(r.children)
                if x:
                    return x
        return None

    plain = walk(snap.records)
    assert plain is not None
    return plain


class TestFieldDataOffsets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stream = parasolid.parse_transmit(_decrypt_pkbody3())

    def test_schema(self):
        self.assertEqual(self.stream.version, 3701153)
        self.assertEqual(self.stream.schema, "SCH_3701153_37102_13006")
        self.assertEqual(len(self.stream.fields), 22)

    def test_lattice_mesh_polyline_offsets(self):
        # 注：scan_fields 拾取的"数据区偏移"实为 BODY 编辑序列中 I/A 操作的
        # ptr_class 值（lattice=222 / mesh=1006 / polyline=1008），二进制
        # 解码后这些字段定义改由 model.edits 结构化提供。
        offs = parasolid.field_data_offsets(self.stream)
        self.assertEqual(offs["lattice"], 222)
        self.assertEqual(offs["mesh"], 1006)
        self.assertEqual(offs["polyline"], 1008)

    def test_boundary_aliases(self):
        offs = parasolid.field_data_offsets(self.stream)
        self.assertEqual(offs["boundary_lattice"], offs["lattice"])
        self.assertEqual(offs["boundary_mesh"], offs["mesh"])
        self.assertEqual(offs["boundary_polyline"], offs["polyline"])

    def test_token_alphabet(self):
        for k in ("I", "D", "A", "C", "$", "l", "u", "d"):
            self.assertIn(k, parasolid.TOKEN_ALPHABET)


class TestBinaryXtDecode(unittest.TestCase):
    """P2 二进制 XT 全量解码（A flag CADthru 流 + B flag kernel 产物）。"""

    @classmethod
    def setUpClass(cls):
        cls.plain = _decrypt_pkbody3()
        cls.model = parasolid.parse_binary_xt(cls.plain)

    def test_no_parse_error(self):
        self.assertFalse(getattr(self.model, "parse_error", True))
        self.assertEqual(len(self.model.order), 159)

    def test_header(self):
        self.assertEqual(self.model.schema, "SCH_3701153_37102_13006")
        self.assertEqual(self.model.binary_flag, "A")
        self.assertEqual(self.model.userfield_size, 0)

    def test_box_geometry_nodes(self):
        from collections import Counter
        counts = Counter(n.name for n in self.model.order)
        # box = 8 顶点 / 12 边 / 6 面 + 几何与属性
        self.assertEqual(counts["VERTEX"], 8)
        self.assertEqual(counts["EDGE"], 12)
        self.assertEqual(counts["FACE"], 6)
        self.assertEqual(counts["POINT"], 8)
        self.assertEqual(counts["LINE"], 12)
        self.assertEqual(counts["PLANE"], 6)
        self.assertEqual(counts["BODY"], 1)

    def test_sdl_attribute_values(self):
        # SDL/TYSA_NAME / LAYER / UNAME 的 ATT_DEF_ID 字符串值
        strings = set()
        for n in self.model.order:
            if n.name == "ATT_DEF_ID":
                s = "".join(n.fields.get("string", []))
                if s:
                    strings.add(s)
        self.assertIn("SDL/TYSA_NAME", strings)
        self.assertIn("SDL/TYSA_LAYER", strings)
        self.assertIn("SDL/TYSA_UNAME", strings)

    def test_edit_sequence_cadthru_fields(self):
        # BODY 编辑序列携带 CADthru 扩展字段定义（ptr_class 与旧字段表一致）
        edit = self.model.edits.get(12)
        self.assertEqual(edit["n"], 36)
        defs = {op[1]: op[2] for op in edit["ops"]
                if op[0] in ("I", "A") and len(op) > 1}
        self.assertEqual(defs["lattice"], 222)
        self.assertEqual(defs["mesh"], 1006)
        self.assertEqual(defs["polyline"], 1008)
        self.assertEqual(defs["owner"], 1040)
        self.assertEqual(defs["mesh_offset_data"], 206)

    def test_byte_exact_roundtrip(self):
        out = parasolid.encode_binary_xt(self.model)
        self.assertEqual(out, self.plain)


class TestKernelBinaryB(unittest.TestCase):
    """B flag（kernel PK_PART_transmit 二进制产物）：与文本对拍 + 字节级闭环。"""

    @classmethod
    def setUpClass(cls):
        try:
            import ps_facet2_nodes as psf
            if not psf.available():
                raise unittest.SkipTest("pskernel.dll not available")
        except Exception:
            raise unittest.SkipTest("pskernel.dll not available")
        import struct
        from ctypes import (POINTER, byref, c_int, c_void_p, memset,
                            c_char_p, Structure, sizeof, c_ubyte)

        class T4(Structure):
            _fields_ = [
                ("o_t_version", c_int), ("transmit_format", c_int),
                ("transmit_user_fields", c_ubyte), ("transmit_version", c_int),
                ("transmit_nmnl_geometry", c_ubyte),
                ("transmit_indexed_context", c_void_p),
                ("transmit_meshes", c_int)]

        sess = psf._get_session()
        body = sess.create_solid_block((1.0, 1.0, 1.0))
        arr = (c_int * 1)(int(body))
        pk = sess.pk
        pk.PK_PART_transmit.restype = c_int
        pk.PK_PART_transmit.argtypes = [
            c_int, POINTER(c_int), c_char_p, POINTER(T4)]
        outs = {}
        for fmt, tag in ((18220, "txt"), (18221, "bin")):
            opts = T4()
            memset(byref(opts), 0, sizeof(opts))
            opts.o_t_version = 4
            opts.transmit_format = fmt
            opts.transmit_meshes = 0x6612
            key = f"p2t_{tag}".encode()
            rc = pk.PK_PART_transmit(1, arr, key, byref(opts))
            self = None
            if rc != 0:
                raise unittest.SkipTest(f"PK_PART_transmit rc={rc}")
            outs[tag] = sess._transmit_output.get(f"p2t_{tag}", b"")
        cls.bin_data = outs["bin"]
        cls.text_model = parasolid.parse_text_xt(
            outs["txt"].decode("latin-1"))

    def test_parse_no_error(self):
        m = parasolid.parse_binary_xt(self.bin_data)
        self.assertFalse(getattr(m, "parse_error", True))
        self.assertEqual(len(m.order), len(self.text_model.order))

    def test_byte_exact_roundtrip(self):
        m = parasolid.parse_binary_xt(self.bin_data)
        self.assertEqual(parasolid.encode_binary_xt(m), self.bin_data)

    def test_graph_vs_text(self):
        m = parasolid.parse_binary_xt(self.bin_data)
        # 同体同序：按 node_id 对照字段值（二进制传输标签可与文本不同，
        # node_id 与连接关系不变）
        b_by_nid = {}
        for n in m.order:
            nid = n.fields.get("node_id")
            if nid is not None:
                b_by_nid[nid] = n
        n_checked = 0
        for tn in self.text_model.order:
            nid = tn.fields.get("node_id")
            b = b_by_nid.get(nid)
            if b is None:
                continue
            n_checked += 1
            self.assertEqual(b.type_id, tn.type_id)
            for k, tv in tn.fields.items():
                if k in ("node_id", "@varlen"):
                    continue
                bv = b.fields.get(k)
                if isinstance(tv, float):
                    if tv is None:
                        self.assertIsNone(bv, f"{nid}.{k}")
                    else:
                        self.assertAlmostEqual(bv, tv, places=6,
                                               msg=f"{nid}.{k}")
        self.assertGreater(n_checked, 50)

    def test_unset_sentinel_normalized(self):
        # tolerance 未设值（文本 '?'）：二进制哨兵 -3.14158e13 → None
        m = parasolid.parse_binary_xt(self.bin_data)
        unset = [n for n in m.order
                 if "tolerance" in n.fields and n.fields["tolerance"] is None]
        self.assertTrue(unset)
        for n in unset:
            self.assertIn(n.name, ("EDGE", "VERTEX", "FACE"))


if __name__ == "__main__":
    unittest.main()
