#!/usr/bin/env python3
"""官方 Org PPH 常见「仅 ridge、无 part」时的面片回退。"""

from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pph_parser  # noqa: E402


def _zip_pph(tmp: Path, names: list[str]) -> Path:
    path = tmp / "t.pph"
    with zipfile.ZipFile(path, "w") as z:
        for n in names:
            z.writestr(n, b"x")
    return path


class TestSurfaceMdlFallback(unittest.TestCase):
    def test_prefers_part_over_ridge(self):
        with tempfile.TemporaryDirectory() as td:
            p = _zip_pph(Path(td), [
                "main.xml",
                "meshinggroup1_part.mdl",
                "meshinggroup1_ridge.mdl",
                "meshinggroup1.gph",
            ])
            arch = pph_parser.PphArchive.open(str(p))
            names = [m.name for m in arch.surface_mdl_members()]
            self.assertEqual(names, ["meshinggroup1_part.mdl"])

    def test_ridge_when_no_part(self):
        with tempfile.TemporaryDirectory() as td:
            p = _zip_pph(Path(td), [
                "main.xml",
                "meshinggroup1_ridge.mdl",
                "meshinggroup1.gph",
            ])
            arch = pph_parser.PphArchive.open(str(p))
            self.assertFalse(arch.by_role(pph_parser.ROLE_MDL_PART))
            names = [m.name for m in arch.surface_mdl_members()]
            self.assertEqual(names, ["meshinggroup1_ridge.mdl"])

    def test_empty_when_no_mdl(self):
        with tempfile.TemporaryDirectory() as td:
            p = _zip_pph(Path(td), ["main.xml", "meshinggroup1.gph"])
            arch = pph_parser.PphArchive.open(str(p))
            self.assertEqual(arch.surface_mdl_members(), [])

    def test_group_surface_path(self):
        self.assertEqual(
            pph_parser.group_surface_path({"paths": {"ridge": "r.mdl"}}),
            "r.mdl")
        self.assertEqual(
            pph_parser.group_surface_path(
                {"paths": {"part": "p.mdl", "ridge": "r.mdl"}}),
            "p.mdl")
        self.assertIsNone(pph_parser.group_surface_path({"paths": {}}))


if __name__ == "__main__":
    unittest.main()
