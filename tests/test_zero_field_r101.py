#!/usr/bin/env python3
"""R10-1 回归：零流场判据（delta 报告不得把「都为零」当等价证据）。

审计 §5-O3 的问题：I5 的 b1/b2 delta 逐点相等、delta_max=0，但两个都是
零流场（VEL / PRES 均值均为 0）—— 假阳性。solver_delta 现在自带判据。
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import solver_delta  # noqa: E402


def _rep(fields):
    return {"fields": fields}


class TestZeroFieldReport(unittest.TestCase):
    def test_primary_all_zero_means_zero_field(self):
        rep = _rep({"FC_Scalar:PRES": {"a_mean": 0.0, "b_mean": 0.0},
                    "FC_Vector:VEL": {"a_mean": 0.0, "b_mean": 0.0},
                    "EC_Scalar:EVIS": {"a_mean": 0.0108, "b_mean": 0.0108}})
        got = solver_delta.zero_field_report(rep)
        self.assertTrue(got["zero_field"], "辅助量非零不得掩盖零流场")
        self.assertEqual(got["primary_nonzero"], [])
        self.assertEqual(got["auxiliary_nonzero_count"], 1)

    def test_any_nonzero_field_clears_flag(self):
        rep = _rep({"FC_Scalar:PRES": {"a_mean": 0.0, "b_mean": 0.0},
                    "FC_Vector:VEL": {"a_mean": 1.5, "b_mean": 0.0}})
        got = solver_delta.zero_field_report(rep)
        self.assertFalse(got["zero_field"])
        self.assertEqual(got["primary_nonzero"], ["FC_Vector:VEL"])

    def test_missing_means_are_tolerated(self):
        got = solver_delta.zero_field_report(_rep({"X": {}}))
        # 无主变量可判 → 不宣称零流场（保守）
        self.assertFalse(got["zero_field"])

    def test_i5_pair_is_flagged_zero_field(self):
        a = ROOT / "_p12k_i5" / "b1" / "box_b1_400.fph"
        b = ROOT / "_p12k_i5" / "b2" / "box_b2_400.fph"
        if not (a.is_file() and b.is_file()):
            self.skipTest("i5 fph artifacts missing")
        rep = solver_delta.compare_fph(a, b)
        if not rep.get("ok"):
            self.skipTest("fph parse unavailable: " + str(rep.get("reason")))
        self.assertTrue(rep["zero_field"], "I5 b1/b2 应被判为零流场")
        self.assertEqual(rep["primary_nonzero"], [])
        self.assertGreater(rep["auxiliary_nonzero_count"], 0)


class TestGateRejectsZeroField(unittest.TestCase):
    """R11-3：--gate 遇零流场必须 FAIL（否则「都为零」会被当成等价证据）。"""

    def _rep(self, vel_a, vel_b):
        return {"fields": {
            "FC_Vector:VEL": {"pointwise": True, "n_a": 4, "n_b": 4,
                               "delta_max": 0.0, "delta_rel": 0.0,
                               "a_mean": vel_a, "b_mean": vel_b},
        }, "only_a": [], "only_b": []}

    def test_zero_field_fails_gate(self):
        rep = self._rep(0.0, 0.0)
        rep.update(solver_delta.zero_field_report(rep))
        got = solver_delta.gate_fph(rep)
        self.assertFalse(got["ok"])
        self.assertTrue(got["zero_field"])
        self.assertIn("zero field", got["reason"])

    def test_nonzero_field_passes_gate(self):
        rep = self._rep(12.5, 12.5)
        rep.update(solver_delta.zero_field_report(rep))
        got = solver_delta.gate_fph(rep)
        self.assertTrue(got["ok"], got.get("reason"))
        self.assertFalse(got["zero_field"])

    def test_cli_gate_on_i5_pair_returns_nonzero(self):
        import subprocess
        a = ROOT / "_p12k_i5" / "b1" / "box_b1_400.fph"
        b = ROOT / "_p12k_i5" / "b2" / "box_b2_400.fph"
        if not (a.is_file() and b.is_file()):
            self.skipTest("i5 fph artifacts missing")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "solver_delta.py"), "--a", str(a),
             "--b", str(b), "--kind", "fph", "--gate"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace")
        if "no fields parsed" in (proc.stdout or ""):
            self.skipTest("fph parse unavailable")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("zero field", proc.stdout)


if __name__ == "__main__":
    unittest.main()
