#!/usr/bin/env python3
"""P12-I I4 生成器离线单测（无宿主）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "p12j_i4", str(ROOT / "tools" / "_p12j_i4_run.py"))
p12j = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p12j)


class TestBuildActranGroups(unittest.TestCase):
    def setUp(self):
        self.actions = dict(p12j.build_actran_groups())["actran"]

    def test_session_prefix(self):
        text = "\n".join(self.actions)
        self.assertIn("WaitForWorker", text)
        self.assertIn("OpenProject", text)
        self.assertLess(text.index("WaitForWorker"),
                        text.index("OpenProject"))
        self.assertIn("SetModeMesh", text)

    def test_analysis_control_and_param_probe(self):
        text = "\n".join(self.actions)
        self.assertIn("GetCondActranAnalysisControl", text)
        self.assertIn('GetParam("cfd_analysis_type"', text)
        self.assertIn("ctrl_g1=", text)

    def test_all_five_conditions(self):
        text = "\n".join(self.actions)
        for _var, method, name in p12j.ACTRAN_CONDS:
            self.assertIn(f"Conditions_.{method}", text)
            self.assertIn(name, text)

    def test_monitor_and_save_redirect(self):
        text = "\n".join(self.actions)
        self.assertIn("CreateActranFilesMonitor", text)
        self.assertIn(p12j.MON_DIR.as_posix(), text)
        self.assertIn("mon_ret=", text)
        self.assertIn("mon_files=", text)
        self.assertIn(f'SaveProject "{p12j.OUT_PPH.as_posix()}"', text)

    def test_no_array_literals(self):
        # VT_I2 AV 教训：VBS 里禁裸 Array() 整数字面量
        text = "\n".join(self.actions)
        self.assertNotIn("Array(", text)


class TestVerifyActranLog(unittest.TestCase):
    def test_clean_log(self):
        text = "\n".join([
            "start",
            "s001=0",
            "conditions__alive=True err=0",
            "mon_ret=True err=0",
            "mon_files=3 err=0",
            "ctrl_g1=True|transient err=0",
            "end",
        ])
        v = p12j.verify_actran_log(text)
        self.assertEqual(v["bad"], 0)
        self.assertTrue(v["has_end"])
        self.assertEqual(v["alive"], {"conditions_": "True"})
        self.assertEqual(v["info"], {"mon_ret": "True", "mon_files": "3",
                                     "ctrl_g1": "True|transient"})

    def test_bad_err_flagged(self):
        v = p12j.verify_actran_log("s001=0\ns002=424\nend")
        self.assertEqual(v["bad"], 1)
        self.assertIn("s002=424", v["problems"][0])

    def test_unparsed_flagged(self):
        v = p12j.verify_actran_log("garbage line\nend")
        # unparsed 行不入 total（P12-E verify_log 口径），证据在 problems
        self.assertEqual(v["total"], 0)
        self.assertIn("garbage line", v["problems"][0])


class TestCheckOutXml(unittest.TestCase):
    def test_missing_file(self):
        out = p12j.check_out_xml(Path("Z:/no/such.pph"))
        self.assertFalse(out["exists"])

    def test_keys_and_names(self, ):
        import tempfile
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.pph"
            with zipfile.ZipFile(p, "w") as zf:
                zf.writestr("main.xml",
                            "<a><actran_analysis_control/>"
                            "<actran_acoustic_analysis_name/>"
                            "P12JActranSource</a>")
            out = p12j.check_out_xml(p)
        self.assertIn("actran_analysis_control", out["keys"])
        self.assertIn("P12JActranSource", out["names"])


if __name__ == "__main__":
    unittest.main()
