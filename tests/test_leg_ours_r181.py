#!/usr/bin/env python3
"""R18-1 回归：对照腿工具（solver_leg_ours）的离线不变量。"""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TOOL = ROOT / "tools" / "solver_leg_ours.py"


def _load():
    spec = importlib.util.spec_from_file_location("solver_leg_ours", str(TOOL))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["solver_leg_ours"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestLegOursTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TOOL.is_file():
            raise unittest.SkipTest("tools/solver_leg_ours.py missing")
        cls.tool = _load()

    def test_rewriters_cover_known_members(self):
        for name in ("meshinggroup1.gph", "meshinggroup1.oct",
                     "meshinggroup1_part.mdl"):
            self.assertIn(name, self.tool.REWRITERS)

    def test_default_case_is_the_official_50pa(self):
        self.assertIn("exA06-2_d_50.pph", str(self.tool.DEFAULT_BASE))

    def test_build_ours_uses_clone_pph_and_rewriter(self):
        src = TOOL.read_text(encoding="utf-8")
        self.assertIn("clone_pph", src)
        self.assertIn("_rewrite_gph", src)
        self.assertIn("gate_fph", src)
        self.assertIn("compare_fph", src)


if __name__ == "__main__":
    unittest.main()
