#!/usr/bin/env python3
"""P12-H 向导收割机离线测试：归一化 diff / 归属判定 / 组合对账。"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pphxml  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "p12h_wizard_harvest", ROOT / "tools" / "_p12h_wizard_harvest.py")
h = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(h)


def _xml_zip(path: Path, xml_bytes: bytes, extra: dict | None = None):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("main.xml", xml_bytes)
        for name, data in (extra or {}).items():
            zf.writestr(name, data)


class TestNormMember(unittest.TestCase):
    def test_xml_species_stripped(self):
        raw = (
            b'<?xml version="1.0"?><scFLOWpre><analysis>'
            b"<date>2026/09/02</date><name>proj</name>"
            b"<species><value_obj>1</value_obj></species>"
            b"<species><value_obj>2</value_obj></species>"
            b"</analysis></scFLOWpre>")
        lines = h._norm_member("main.xml", raw)
        self.assertNotIn("species", "\n".join(lines))
        self.assertNotIn("date", "\n".join(lines))

    def test_xml_keeps_real_keys(self):
        raw = (b'<?xml version="1.0"?><scFLOWpre>'
               b"<ElectricCurrent>true</ElectricCurrent></scFLOWpre>")
        lines = h._norm_member("main.xml", raw)
        self.assertIn("ElectricCurrent", "\n".join(lines))

    def test_prp_date_stripped(self):
        raw = (b'<?xml version="1.0" encoding="utf-8"?>'
               b'<property version="5" date="2026/09/02">'
               b"<g>1</g></property>")
        lines = h._norm_member("main.prp", raw)
        self.assertNotIn("date=", "\n".join(lines))

    def test_binary_passthrough(self):
        lines = h._norm_member("meshinggroup1.gph", b"\x01\x02")
        self.assertEqual(lines, b"\x01\x02")


class TestCompareFamily(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(_tmpdir()))

    def _mk(self, name, xml, extra=None):
        p = self.tmp / name
        _xml_zip(p, xml, extra)
        return p

    def test_session_state(self):
        # 仅 Finish 噪声（species 重排 + snapshot 重写）→ 无变化成员
        base = self._mk(
            "b.pph",
            b"<s><species><v>1</v></species></s>",
            {"main.sctsnapshot": b"A", "main.prp":
             b'<property date="2026/09/02"/>',
             "main.js": b"j", "main.xenv": b"x"})
        out = self._mk(
            "o.pph",
            b"<s><species><v>2</v></species></s>",
            {"main.sctsnapshot": b"A" + b"B" * 182, "main.prp":
             b'<property date="2026/09/03"/>',
             "main.js": b"j", "main.xenv": b"x"})
        res = h.compare_family(h.member_map(base), h.member_map(out))
        self.assertEqual(res["changed"], [])
        self.assertFalse(res["added"])
        self.assertFalse(res["removed"])
        self.assertTrue(res["snapshot_changed"])

    def test_keys_detected(self):
        base = self._mk(
            "b2.pph", b"<s><Flow>false</Flow></s>",
            {"main.js": b"j"})
        out = self._mk(
            "o2.pph", b"<s><Flow>true</Flow></s>",
            {"main.js": b"j"})
        res = h.compare_family(h.member_map(base), h.member_map(out))
        self.assertIn("main.xml", res["changed"])

    def test_binary_change_flagged(self):
        base = self._mk("b3.pph", b"<s/>", {"m.gph": b"\x01"})
        out = self._mk("o3.pph", b"<s/>", {"m.gph": b"\x02"})
        res = h.compare_family(h.member_map(base), h.member_map(out))
        self.assertIn("m.gph", res["changed"])


class TestMergeAttribution(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(_tmpdir()))
        self._old_base, self._old_out = h.BASELINE, h.OUTDIR
        h.BASELINE = self.tmp / "base.pph"
        h.OUTDIR = self.tmp
        _xml_zip(h.BASELINE,
                 b"<s><Flow>false</Flow><Heat>false</Heat></s>",
                 {"main.js": b"j", "main.sctsnapshot": b"A"})

    def tearDown(self):
        h.BASELINE, h.OUTDIR = self._old_base, self._old_out

    def _out(self, name, xml):
        _xml_zip(self.tmp / name, xml,
                 {"main.js": b"j", "main.sctsnapshot": b"A" + b"Z" * 10})

    def test_session_state_no_out(self):
        h.FAMILIES = ["Flow"]
        rep = h.merge()
        self.assertEqual(rep["families"]["Flow"]["status"], "not_run")

    def test_session_state_with_noise_only(self):
        h.FAMILIES = ["Flow"]
        self._out("out_Flow.pph",
                  b"<s><Flow>false</Flow><Heat>false</Heat></s>")
        rep = h.merge()
        self.assertEqual(rep["families"]["Flow"]["verdict"],
                         "session_state")

    def test_keys_projected(self):
        h.FAMILIES = ["Flow"]
        self._out("out_Flow.pph",
                  b"<s><Flow>true</Flow><Heat>false</Heat></s>")
        rep = h.merge()
        self.assertEqual(rep["families"]["Flow"]["verdict"],
                         "keys_projected")

    def test_combo_attribution_vs_pre(self):
        h.FAMILIES = ["Boil/condensation"]
        tag = h._tag("Boil/condensation")
        # pre-only：Heat 勾选投影
        self._out(f"out_{tag}_pre.pph",
                  b"<s><Flow>false</Flow><Heat>true</Heat></s>")
        # combo：Heat + Boil 都勾，但 Boil 无键（同 pre）→ session_state
        self._out(f"out_{tag}.pph",
                  b"<s><Flow>false</Flow><Heat>true</Heat></s>")
        rep = h.merge()
        f = rep["families"]["Boil/condensation"]
        self.assertEqual(f["attribution"], "combo_vs_pre")
        self.assertEqual(f["verdict"], "session_state")
        self.assertEqual(f["target_contribution"], [])

    def test_combo_target_contribution(self):
        h.FAMILIES = ["Boil/condensation"]
        tag = h._tag("Boil/condensation")
        self._out(f"out_{tag}_pre.pph",
                  b"<s><Flow>false</Flow><Heat>true</Heat></s>")
        self._out(f"out_{tag}.pph",
                  b"<s><Flow>false</Flow><Heat>true</Heat>"
                  b"<Boil>true</Boil></s>")
        rep = h.merge()
        f = rep["families"]["Boil/condensation"]
        self.assertEqual(f["verdict"], "keys_projected")
        self.assertIn("main.xml", f["target_contribution"])


def _tmpdir():
    import tempfile
    return tempfile.TemporaryDirectory()


if __name__ == "__main__":
    unittest.main()
