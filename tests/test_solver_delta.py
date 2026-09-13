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


def _synth_rep(**over):
    """合成 compare_fph 报告（字段默认：PRES 逐点全零、USTR 双侧空）。"""
    rep = {
        "a": "A.fph", "b": "B.fph", "a_size": 1, "b_size": 1,
        "only_a": [], "only_b": [], "ok": True,
        "fields": {
            "EC_Scalar:PRES": {"n_a": 100, "n_b": 100,
                               "pointwise": True, "delta_max": 0.0,
                               "delta_mean": 0.0, "delta_rel": 0.0},
            "FC_Scalar:USTR": {"n_a": 0, "n_b": 0,
                               "pointwise": False},
        },
    }
    rep.update(over)
    return rep


class TestGateFph(unittest.TestCase):
    def test_all_zero_passes_at_default_tol(self):
        gate = solver_delta.gate_fph(_synth_rep())
        self.assertTrue(gate["ok"])
        self.assertEqual(gate["n_fail"], 0)
        self.assertEqual(gate["n_empty_both"], 1)
        self.assertEqual(gate["fields"]["EC_Scalar:PRES"]["verdict"],
                         "PASS")
        self.assertEqual(
            gate["fields"]["FC_Scalar:USTR"]["note"],
            "empty on both sides")

    def test_nonzero_delta_fails_at_zero_tol(self):
        rep = _synth_rep()
        rep["fields"]["EC_Scalar:PRES"].update(delta_max=1e-6,
                                               delta_rel=1e-9)
        gate = solver_delta.gate_fph(rep)
        self.assertFalse(gate["ok"])
        self.assertEqual(gate["n_fail"], 1)
        self.assertEqual(gate["fields"]["EC_Scalar:PRES"]["verdict"],
                         "FAIL")
        self.assertIn("delta_max 1e-06 > tol_max 0", gate["fields"]
                      ["EC_Scalar:PRES"]["note"])

    def test_tol_boundary_exact_equality_passes(self):
        rep = _synth_rep()
        rep["fields"]["EC_Scalar:PRES"].update(delta_max=1e-6,
                                               delta_rel=1e-9)
        gate = solver_delta.gate_fph(rep, tol_max=1e-6, tol_rel=1e-9)
        self.assertTrue(gate["ok"])

    def test_rel_axis_independent(self):
        rep = _synth_rep()
        rep["fields"]["EC_Scalar:PRES"].update(delta_max=1e-6,
                                               delta_rel=1e-9)
        gate = solver_delta.gate_fph(rep, tol_max=1e-3)
        self.assertFalse(gate["ok"])
        self.assertIn("delta_rel 1e-09 > tol_rel 0",
                      gate["fields"]["EC_Scalar:PRES"]["note"])

    def test_max_axis_independent(self):
        rep = _synth_rep()
        rep["fields"]["EC_Scalar:PRES"].update(delta_max=1e-6,
                                               delta_rel=1e-9)
        gate = solver_delta.gate_fph(rep, tol_rel=1e-6)
        self.assertFalse(gate["ok"])
        self.assertIn("delta_max 1e-06 > tol_max 0",
                      gate["fields"]["EC_Scalar:PRES"]["note"])

    def test_shape_mismatch_fails(self):
        rep = _synth_rep()
        rep["fields"]["EC_Scalar:PRES"].update(pointwise=False)
        rep["fields"]["EC_Scalar:PRES"]["shape_mismatch"] = \
            [[344], [344, 3]]
        gate = solver_delta.gate_fph(rep)
        self.assertFalse(gate["ok"])
        self.assertEqual(gate["fields"]["EC_Scalar:PRES"]["verdict"],
                         "FAIL")
        self.assertIn("shape mismatch", gate["fields"]
                      ["EC_Scalar:PRES"]["note"])

    def test_n_mismatch_single_side_fails(self):
        rep = _synth_rep()
        rep["fields"]["FC_Scalar:USTR"].update(n_a=0, n_b=86180)
        gate = solver_delta.gate_fph(rep)
        self.assertFalse(gate["ok"])
        self.assertEqual(gate["n_fail"], 1)

    def test_only_a_fails_overall(self):
        gate = solver_delta.gate_fph(
            _synth_rep(only_a=["EC_Scalar:VORT"]))
        self.assertFalse(gate["ok"])
        self.assertEqual(gate["only_a"], ["EC_Scalar:VORT"])

    def test_broken_compare_rep_passthrough(self):
        gate = solver_delta.gate_fph(
            {"ok": False, "reason": "missing file"})
        self.assertFalse(gate["ok"])
        self.assertEqual(gate["reason"], "missing file")

    def test_self_compare_real_fph_field_verdicts_clean(self):
        # R11-3 后语义变化：H2O 那对 FPH 是**零流场**，自比虽然逐点相等，
        # gate 也会因 zero_field 判不通过（「都为零」不是等价证据）。
        # 这里改为断言「逐场判定干净」，零流场结论交给下面的断言。
        if not _has(FPH_A):
            self.skipTest(f"{FPH_A.name} missing")
        rep = solver_delta.compare_fph(FPH_A, FPH_A)
        gate = solver_delta.gate_fph(rep)
        self.assertEqual(gate["n_fail"], 0)
        self.assertTrue(rep.get("zero_field"),
                        "该对 FPH 应为零流场（R10-1 判据）")
        self.assertFalse(gate["ok"])
        self.assertIn("zero field", gate["reason"])

    def test_cross_run_real_fph_fails_default_gate(self):
        if not (_has(FPH_A) and _has(FPH_B)):
            self.skipTest("Sprint B FPH pair missing")
        rep = solver_delta.compare_fph(FPH_A, FPH_B)
        gate = solver_delta.gate_fph(rep)
        self.assertFalse(gate["ok"])
        self.assertGreaterEqual(gate["n_fail"], 1)


class TestMarkdownGate(unittest.TestCase):
    def test_gate_columns_rendered(self):
        rep = _synth_rep()
        gate = solver_delta.gate_fph(rep)
        md = solver_delta.delta_table_markdown(rep, gate=gate)
        self.assertIn("| gate |", md)
        self.assertIn("PASS (empty both)", md)
        self.assertIn("**Gate", md)
        self.assertIn("PASS**", md)

    def test_gate_fail_line(self):
        rep = _synth_rep()
        rep["fields"]["EC_Scalar:PRES"].update(delta_max=1.0,
                                               delta_rel=0.5)
        gate = solver_delta.gate_fph(rep)
        md = solver_delta.delta_table_markdown(rep, gate=gate)
        self.assertIn("FAIL**", md)

    def test_plain_output_unchanged(self):
        if not _has(FPH_A):
            self.skipTest(f"{FPH_A.name} missing")
        rep = solver_delta.compare_fph(FPH_A, FPH_A)
        md = solver_delta.delta_table_markdown(rep)
        self.assertIn("| EC_Scalar:PRES ", md)
        self.assertNotIn("| gate |", md)


if __name__ == "__main__":
    unittest.main()
