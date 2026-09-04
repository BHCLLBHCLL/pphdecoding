#!/usr/bin/env python3
"""P12-K I5 双跑编排器离线回归（拷贝/报告装配/双腿汇总）。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import _p12k_i5_run as p12k  # noqa: E402

FPH_A = ROOT / "p12b_solve_e2e.fph"
FPH_B = ROOT / "p12b_dp50_e2e.fph"


def _has(p: Path) -> bool:
    return p.is_file() and p.stat().st_size > 0


class TestMakeWorkCopies(unittest.TestCase):
    def test_copies_and_names(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src.pph"
            src.write_bytes(b"pph-bytes")
            work = Path(td) / "work"
            copies = p12k.make_work_copies(src, work)
            for tag in ("b1", "b2"):
                self.assertIn(tag, copies)
                self.assertEqual(copies[tag]["case"], f"box_{tag}")
                self.assertTrue(
                    (work / tag / f"box_{tag}.pph").is_file())
        self.assertNotEqual(copies["b1"]["pph"], copies["b2"]["pph"])

    def test_missing_src_raises(self):
        with self.assertRaises(FileNotFoundError):
            p12k.make_work_copies(Path("Z:/no/exA36-3.pph"))


class TestScanAndPick(unittest.TestCase):
    def test_latest_fph_by_mtime(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "exA36_3_a1_100.fph").write_bytes(b"a")
            (d / "exA36_3_a1_200.fph").write_bytes(b"bb")
            os.utime(d / "exA36_3_a1_100.fph", (1000, 1000))
            os.utime(d / "exA36_3_a1_200.fph", (2000, 2000))
            got = p12k.latest_fph(d, "exA36_3_a1")
        self.assertEqual(got.name, "exA36_3_a1_200.fph")

    def test_latest_fph_none(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(p12k.latest_fph(Path(td), "zz"))

    def test_scan_fld_ifld_absent(self):
        with tempfile.TemporaryDirectory() as td:
            scan = p12k.scan_fld_ifld(Path(td))
        self.assertEqual(scan, {"fld": [], "ifld": []})


class TestRunOne(unittest.TestCase):
    def test_brief_structure_with_mocked_solve(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            pph = d / "box_b1.pph"
            pph.write_bytes(b"pph")
            (d / "box_b1_400.fph").write_bytes(b"fph")
            fake = {"ok": True,
                    "vbs_run": {"ok": True},
                    "wait": {"ok": True, "saw_solver": True,
                             "elapsed": 12.5},
                    "verify": {"ok": True, "strict_ok": True,
                               "key_fields": ["EC_Scalar:PRES"]}}
            with mock.patch("automation.solver_run.run_solve",
                            return_value=fake) as rs:
                brief = p12k.run_one("b1", {"dir": d, "pph": pph,
                                            "case": "box_b1"})
            self.assertEqual(rs.call_args.kwargs["case"], "box_b1")
        self.assertTrue(brief["ok"])
        self.assertTrue(brief["vbs_ok"])
        self.assertTrue(brief["verify_strict"])
        self.assertTrue(brief["fph"].endswith("box_b1_400.fph"))
        self.assertEqual(brief["fld_ifld"], {"fld": [], "ifld": []})

    def test_brief_failed_run(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            pph = d / "box_b1.pph"
            pph.write_bytes(b"pph")
            fake = {"ok": False, "reason": "VBS 提交失败"}
            with mock.patch("automation.solver_run.run_solve",
                            return_value=fake):
                brief = p12k.run_one("b1", {"dir": d, "pph": pph,
                                            "case": "box_b1"})
        self.assertFalse(brief["ok"])
        self.assertIsNone(brief["fph"])


class TestAssembleReport(unittest.TestCase):
    def _briefs(self, work: Path, ok: bool = True) -> dict:
        b1 = {"tag": "b1", "work": str(work / "b1"),
              "fph": str(FPH_A) if _has(FPH_A) else None,
              "fld_ifld": {"fld": [], "ifld": []}, "ok": ok}
        b2 = {"tag": "b2", "work": str(work / "b2"),
              "fph": str(FPH_B) if _has(FPH_B) else None,
              "fld_ifld": {"fld": [], "ifld": []}, "ok": ok}
        return {"b1": b1, "b2": b2}

    def test_report_written(self):
        if not (_has(FPH_A) and _has(FPH_B)):
            self.skipTest("Sprint B FPH pair missing")
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            summary = p12k.assemble_report(self._briefs(work), work)
            self.assertTrue((work / "delta_table.md").is_file())
            self.assertTrue((work / "delta_table.json").is_file())
            self.assertTrue((work / "i5_summary.json").is_file())
            md = (work / "delta_table.md").read_text(encoding="utf-8")
            self.assertIn("delta_max", md)
            js = json.loads((work / "i5_summary.json")
                            .read_text(encoding="utf-8"))
        self.assertTrue(summary["ok"])
        self.assertTrue(summary["fph_compare_ok"])
        self.assertGreater(summary["n_fields"], 0)
        self.assertIsNone(summary["fld_compare"])
        self.assertEqual(js, summary)

    def test_failed_run_marks_not_ok(self):
        with tempfile.TemporaryDirectory() as td:
            summary = p12k.assemble_report(
                self._briefs(Path(td), ok=False), Path(td))
        self.assertFalse(summary["ok"])

    def test_missing_fph_records_reason(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            briefs = self._briefs(work)
            briefs["b1"]["fph"] = None
            briefs["b2"]["fph"] = None
            summary = p12k.assemble_report(briefs, work)
        self.assertFalse(summary["ok"])
        self.assertFalse(summary["fph_compare_ok"])
        self.assertIn("missing", summary["fph_compare_reason"])


if __name__ == "__main__":
    unittest.main()
