#!/usr/bin/env python3
"""官方案例 Disc/Overset 工程结构对拍（案例库缺失则 skip）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import official_examples  # noqa: E402
import pph_parser  # noqa: E402
import pphxml  # noqa: E402
import project_persist  # noqa: E402


def _open_xml(pph: Path):
    arch = pph_parser.PphArchive.open(str(pph))
    xml_m = arch.by_role(pph_parser.ROLE_PROJECT_XML)
    if not xml_m:
        raise unittest.SkipTest(f"{pph.name}: no main.xml")
    mx = pphxml.parse_main_xml(arch.read_member(xml_m[0].name))
    return arch, mx


class TestReadPartsControlFlags(unittest.TestCase):
    def test_roundtrip(self):
        mx = pphxml.parse_main_xml(
            b'<?xml version="1.0"?><scFLOWpre><conditions/></scFLOWpre>')
        project_persist.set_parts_control_flags(
            mx, discontinuous=True, overset=False, wrapping=True)
        flags = project_persist.read_parts_control_flags(mx)
        self.assertTrue(flags["discontinuous"])
        self.assertFalse(flags["overset"])
        self.assertTrue(flags["wrapping"])


class TestOfficialDiscOverset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if official_examples.example_root() is None:
            raise unittest.SkipTest(
                f"set {official_examples.ENV_VAR} to the Cradle example library")
        cls.disc = official_examples.example_pph(official_examples.DISC_PPH)
        cls.overset = official_examples.example_pph(
            official_examples.OVERSET_PPH)
        if cls.disc is None or cls.overset is None:
            raise unittest.SkipTest("exA16-1 / exA25-1 PPH missing")

    def test_disc_single_group_ridge_only(self):
        arch, mx = _open_xml(self.disc)
        flags = project_persist.read_parts_control_flags(mx)
        self.assertTrue(flags["discontinuous"])
        self.assertFalse(flags["overset"])
        gph = arch.by_role(pph_parser.ROLE_GPH)
        self.assertEqual(len(gph), 1, [m.name for m in gph])
        self.assertFalse(arch.by_role(pph_parser.ROLE_MDL_PART))
        ridge = arch.by_role(pph_parser.ROLE_MDL_RIDGE)
        self.assertEqual(len(ridge), 1)
        self.assertEqual(
            [m.name for m in arch.surface_mdl_members()],
            [ridge[0].name])
        xml = arch.read_member(arch.by_role(pph_parser.ROLE_PROJECT_XML)[0].name)
        self.assertIn(b"CondDiscontinuous", xml)

    def test_overset_multi_meshing_groups(self):
        arch, mx = _open_xml(self.overset)
        flags = project_persist.read_parts_control_flags(mx)
        self.assertTrue(flags["overset"])
        gph = arch.by_role(pph_parser.ROLE_GPH)
        ridge = arch.by_role(pph_parser.ROLE_MDL_RIDGE)
        self.assertGreaterEqual(len(gph), 2, [m.name for m in gph])
        self.assertEqual(len(gph), len(ridge))
        self.assertFalse(arch.by_role(pph_parser.ROLE_MDL_PART))
        names = sorted(m.name for m in gph)
        self.assertTrue(any(n.startswith("meshinggroup") for n in names))


if __name__ == "__main__":
    unittest.main()
