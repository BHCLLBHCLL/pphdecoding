#!/usr/bin/env python3
"""R15-1 回归：宿主路径必须绝对（两次踩坑的断言化）。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import host_paths  # noqa: E402

GATE = ROOT / "tools" / "cad_pipeline_gate.py"
CONV = ROOT / "tools" / "cadthru_convert.py"


class TestRequireAbs(unittest.TestCase):
    def test_absolute_passes_relative_raises(self):
        ok = ROOT / "box.pph"
        self.assertEqual(host_paths.require_abs(ok), ok)
        with self.assertRaises(host_paths.RelativeHostPath):
            host_paths.require_abs("box.pph")
        with self.assertRaises(host_paths.RelativeHostPath):
            host_paths.abs_str("_p12u_gate/x.x_t", what="cad")

    def test_abs_str_is_posix(self):
        s = host_paths.abs_str(ROOT / "tests" / "box" / "box.x_t")
        self.assertTrue(Path(s).is_absolute())
        self.assertNotIn(chr(92), s)


class TestCallSitesUseIt(unittest.TestCase):
    def test_gate_asserts_absolute(self):
        src = GATE.read_text(encoding="utf-8")
        self.assertIn("host_paths.require_abs", src)
        self.assertIn("from automation import host_paths", src)

    def test_cadthru_converter_resolves_paths(self):
        src = CONV.read_text(encoding="utf-8")
        self.assertIn(".resolve()", src)
        self.assertIn("必须绝对路径", src)


if __name__ == "__main__":
    unittest.main()
