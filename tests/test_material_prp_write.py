#!/usr/bin/env python3
"""材料五库 prp 写端 round-trip（P12-C C4）。

厂商库文件存在时对真实数据断言解析级恒等；不存在时用合成数据。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import material_lib  # noqa: E402


def _programs():
    return material_lib.locate_programs()


class TestPrpDocumentSynthetic(unittest.TestCase):
    def _doc(self):
        doc = material_lib.PrpDocument()
        g = material_lib.PrpGroup(key="gas(x)", name_jpn="気体",
                                  name_eng="gas(x)")
        g.entries.append(material_lib.PrpEntry(
            key="custom(1/20C)", name_jpn="カスタム", name_eng="custom(1/20C)",
            kind="fluid", subtype="gas",
            props=[("density", "1.2"), ("viscosity", "1.8e-05"),
                   ("capacity", "1007")]))
        doc.groups.append(g)
        return doc

    def test_write_parse_roundtrip(self):
        import tempfile
        doc = self._doc()
        with tempfile.TemporaryDirectory() as td:
            p = material_lib.write_prp_document(doc, Path(td) / "x.prp")
            back = material_lib.parse_prp_document(p.read_bytes())
        self.assertEqual(len(back.groups), 1)
        g = back.groups[0]
        self.assertEqual((g.key, g.name_jpn, g.name_eng),
                         ("gas(x)", "気体", "gas(x)"))
        self.assertEqual(len(g.entries), 1)
        e = g.entries[0]
        self.assertEqual(e.key, "custom(1/20C)")
        self.assertEqual((e.kind, e.subtype), ("fluid", "gas"))
        self.assertEqual(e.props, [("density", "1.2"),
                                   ("viscosity", "1.8e-05"),
                                   ("capacity", "1007")])

    def test_format_bom_crlf(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = material_lib.write_prp_document(self._doc(),
                                                Path(td) / "x.prp")
            raw = p.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"</property>\r\n", raw)

    def test_legacy_parser_reads_writer_output(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = material_lib.write_prp_document(self._doc(),
                                                Path(td) / "x.prp")
            entries = material_lib._parse_property_xml(p.read_bytes())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].name, "custom(1/20C)")
        self.assertEqual(entries[0].group, "gas(x)")
        self.assertEqual(entries[0].props["density"], "1.2")


@unittest.skipUnless(_programs() is not None, "Cradle not installed")
class TestPrpDocumentVendorRoundtrip(unittest.TestCase):
    VENDOR = ("scFLOWpre.prp", "standard_property_ENG.xml",
              "thermal_property_ENG.xml")

    def test_vendor_roundtrip_identity(self):
        import tempfile
        prog = _programs()
        for fname in self.VENDOR:
            data = (prog / fname).read_bytes()
            if b"<property>" not in data:
                continue
            doc = material_lib.parse_prp_document(data)
            with tempfile.TemporaryDirectory() as td:
                out = material_lib.write_prp_document(doc, Path(td) / "o.prp")
                back = material_lib.parse_prp_document(out.read_bytes())
            self.assertEqual(len(doc.groups), len(back.groups), fname)
            for gb, ga in zip(doc.groups, back.groups):
                self.assertEqual(gb.key, ga.key, fname)
                self.assertEqual((gb.name_jpn, gb.name_eng),
                                 (ga.name_jpn, ga.name_eng), fname)
                self.assertEqual(len(gb.entries), len(ga.entries), fname)
                for eb, ea in zip(gb.entries, ga.entries):
                    self.assertEqual((eb.key, eb.name_jpn, eb.name_eng),
                                     (ea.key, ea.name_jpn, ea.name_eng),
                                     fname)
                    self.assertEqual((eb.kind, eb.subtype),
                                     (ea.kind, ea.subtype), fname)
                    self.assertEqual(eb.props, ea.props, fname)

    def test_vendor_prp_struct_roundtrip(self):
        import tempfile
        prog = _programs()
        data = (prog / "SCTpre.prp_struct")
        if not data.is_file():
            self.skipTest("SCTpre.prp_struct missing")
        metals = material_lib.parse_prp_struct(
            data.read_text(encoding="utf-8-sig", errors="replace"))
        self.assertGreater(len(metals), 0)
        with tempfile.TemporaryDirectory() as td:
            out = material_lib.write_prp_struct(metals, Path(td) / "o.txt")
            back = material_lib.parse_prp_struct(
                out.read_text(encoding="utf-8-sig"))
        self.assertEqual([(m.name, m.category, m.model) for m in metals],
                         [(m.name, m.category, m.model) for m in back])
        for mb, ma in zip(metals, back):
            for f in ("young", "poisson", "density", "thermal_exp",
                      "ref_temp"):
                self.assertAlmostEqual(getattr(mb, f), getattr(ma, f),
                                       places=6)

    def test_main_prp_from_pph_roundtrip(self):
        import tempfile
        import zipfile
        pph = ROOT / "p12e_disc_e2e_out.pph"
        if not pph.is_file():
            self.skipTest("p12e artifact missing")
        with zipfile.ZipFile(pph) as zf:
            names = [n for n in zf.namelist()
                     if n.endswith(".prp")]
            if not names:
                self.skipTest("no main.prp member")
            data = zf.read(names[0])
            if b"<property>" not in data:
                self.skipTest("main.prp not property dialect")
            doc = material_lib.parse_prp_document(data)
            with tempfile.TemporaryDirectory() as td:
                out = material_lib.write_prp_document(doc, Path(td) / "o.prp")
                back = material_lib.parse_prp_document(out.read_bytes())
        self.assertEqual([(g.key, len(g.entries)) for g in doc.groups],
                         [(g.key, len(g.entries)) for g in back])


if __name__ == "__main__":
    unittest.main()
