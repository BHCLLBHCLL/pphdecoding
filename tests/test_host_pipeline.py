#!/usr/bin/env python3
"""Tests for automation.host_pipeline (COM registration + host VBS)."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import host_pipeline  # noqa: E402


class TestBuildAndParse(unittest.TestCase):
    def test_build_pipeline_vbs(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            result = td / "result.txt"
            vbs = host_pipeline.build_pipeline_vbs(
                result, set_name="Box", group_name="BoxGroup",
                output=td / "host.vbs")
            text = vbs.read_text(encoding="utf-8-sig")
            self.assertIn('CreateObject("pphdecoding.ScflowPipeline")', text)
            self.assertIn('CreateShapeGroupSet("Box")', text)
            self.assertIn('CreateShapeGroup(hSet, "BoxGroup")', text)
            self.assertIn("Pipe.LastError()", text)

    def test_parse_result_ok(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "result.txt"
            p.write_text(
                "context_ready=True\n"
                "set_handle=1|last_error=0\n"
                "group_handle=2|last_error=0\n"
                "mdl=True|last_error=0\n",
                encoding="utf-8")
            parsed = host_pipeline.parse_result(p)
        self.assertTrue(parsed["ok"])
        self.assertTrue(parsed["context_ready"])
        self.assertEqual(parsed["set_handle"], 1)
        self.assertEqual(parsed["group_handle"], 2)
        self.assertTrue(parsed["mdl"])

    def test_parse_result_create_failed(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "result.txt"
            p.write_text("error=create_failed\n", encoding="utf-8")
            parsed = host_pipeline.parse_result(p)
        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed["error"], "create_failed")

    def test_parse_result_missing(self):
        parsed = host_pipeline.parse_result(Path(r"C:\nonexistent\result.txt"))
        self.assertFalse(parsed["ok"])


class TestRegistration(unittest.TestCase):
    def test_register_com_writes_hkcu(self):
        with tempfile.TemporaryDirectory() as td:
            dll = Path(td) / "scflow_bridge.dll"
            dll.write_bytes(b"MZ")
            writes: list[tuple] = []
            with mock.patch.object(host_pipeline, "_write_reg_string",
                                   side_effect=lambda *a: writes.append(a)):
                result = host_pipeline.register_com(dll)
        self.assertTrue(result["registered"])
        self.assertEqual(result["progid"], host_pipeline.PROGID)
        self.assertGreaterEqual(len(writes), 5)
        paths = [w[1] for w in writes]
        self.assertTrue(any("InprocServer32" in p for p in paths))
        self.assertTrue(any(p.endswith("\\CLSID") for p in paths))

    def test_unregister_com_removes_hkcu(self):
        deletes: list[tuple] = []
        with mock.patch.object(host_pipeline, "_delete_reg_tree",
                               side_effect=lambda *a: deletes.append(a)):
            result = host_pipeline.unregister_com()
        self.assertFalse(result["registered"])
        self.assertGreaterEqual(len(deletes), 2)

    def test_run_in_host_manual(self):
        with tempfile.TemporaryDirectory() as td:
            vbs = Path(td) / "host.vbs"
            vbs.write_text("' test", encoding="utf-8")
            result = host_pipeline.run_in_host(vbs, backend="manual")
        self.assertEqual(result["backend"], "manual")
        self.assertIn("Execute VBScript", result["hint"])


if __name__ == "__main__":
    unittest.main()
