#!/usr/bin/env python3
"""P12-K I5 delta 工具离线回归（真实 Sprint B 产物自对拍/交叉对拍）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import solver_delta  # noqa: E402

FPH_A = ROOT / "p12b_solve_e2e.fph"
FPH_B = ROOT / "p12b_dp50_e2e.fph"
FPH_C = ROOT / "scratch" / "solve_b" / "box_400.fph"


def _has(p: Path) -> bool:
    return p.is_file() and p.stat().st_size > 0


class TestCompareFph(unittest.TestCase):
    def test_self_delta_zero(self):
        if not _has(FPH_A):
            self.skipTest(f"{FPH_A.name} missing")
        rep = solver_delta.compare_fph(FPH_A, FPH_A)
        self.assertTrue(rep["ok"])
        self.assertTrue(rep["fields"])
        for name, e in rep["fields"].items():
            if e.get("pointwise"):
                self.assertEqual(e["delta_max"], 0.0, name)
                self.assertEqual(e["delta_mean"], 0.0, name)
                self.assertEqual(e["delta_rel"], 0.0, name)

    def test_cross_run_produces_deltas(self):
        if not (_has(FPH_A) and _has(FPH_B)):
            self.skipTest("Sprint B FPH pair missing")
        rep = solver_delta.compare_fph(FPH_A, FPH_B)
        self.assertTrue(rep["ok"])
        pw = [e for e in rep["fields"].values() if e.get("pointwise")]
        self.assertTrue(pw, "expected pointwise fields")
        self.assertTrue(any(e["delta_max"] > 0 for e in pw))

    def test_missing_file(self):
        rep = solver_delta.compare_fph("Z:/no/a.fph", "Z:/no/b.fph")
        self.assertFalse(rep["ok"])
        self.assertEqual(rep["reason"], "missing file")

    def test_not_fph_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "junk.fph"
            p.write_bytes(b"not an fph")
            rep = solver_delta.compare_fph(p, p)
        self.assertFalse(rep["ok"])
        self.assertIn("no fields parsed", rep["reason"])


class TestMarkdown(unittest.TestCase):
    def test_table_rendered(self):
        if not _has(FPH_A):
            self.skipTest(f"{FPH_A.name} missing")
        rep = solver_delta.compare_fph(FPH_A, FPH_A)
        md = solver_delta.delta_table_markdown(rep)
        self.assertIn("delta_max", md)
        self.assertIn("| EC_Scalar:PRES ", md)


class TestSphFingerprint(unittest.TestCase):
    def test_fingerprint(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.sph"
            p.write_bytes(b"abc")
            fp = solver_delta.sph_fingerprint(p)
            self.assertTrue(fp["exists"])
            self.assertEqual(fp["size"], 3)
            self.assertEqual(len(fp["md5"]), 32)
        self.assertFalse(solver_delta.sph_fingerprint(
            Path(td) / "gone.sph")["exists"])


if __name__ == "__main__":
    unittest.main()
