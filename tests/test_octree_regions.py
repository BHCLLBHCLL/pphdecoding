#!/usr/bin/env python3
"""Octree Parameter「Size for regions」列表应对齐 main.xml 零件。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pphxml  # noqa: E402
from nav_panels import _collect_octree_regions  # noqa: E402
from pph_gui import _extract_part_tree_meta  # noqa: E402
from pph_parser import PphArchive  # noqa: E402

LAPTOP = ROOT / "tests" / "laptop_thermal_steady_scaled_v3_fanonly_simple.pph"


class TestOctreeRegions(unittest.TestCase):
    def test_laptop_matches_scflow_part_list(self):
        if not LAPTOP.is_file():
            self.skipTest("laptop sample pph missing")
        arch = PphArchive.open(str(LAPTOP))
        mx = pphxml.parse_main_xml(arch.read_member("main.xml"))
        meta, parts = _extract_part_tree_meta(mx)
        groups = {"meshinggroup1": {
            "xml_parts": parts.get("meshinggroup1") or []}}
        rows = _collect_octree_regions({
            "regions_meta": meta, "groups_info": groups})
        names = [r["name"] for r in rows]
        self.assertTrue(any("air(incompressible/20C)" in n for n in names))
        for part in ("air_domain", "case1", "rotation1", "impeller1"):
            self.assertIn(part, names)
            self.assertIn(f"Part surface (@{part})", names)
        self.assertIn("open", names)
        # 不得再写死单 Part 工程名
        self.assertNotIn("Part", names)
        self.assertNotIn("Part surface (@Part)", names)

    def test_empty_ctx_fallback(self):
        rows = _collect_octree_regions({})
        names = [r["name"] for r in rows]
        self.assertIn("Part surface (@Part)", names)


if __name__ == "__main__":
    unittest.main()
