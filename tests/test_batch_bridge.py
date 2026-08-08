#!/usr/bin/env python3
"""批处理桥测试（构造命令 + dry-run 输出解析）。"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import automation.batch_bridge as batch  # noqa: E402


class TestBuildCommand(unittest.TestCase):
    def test_basic(self):
        cmd = batch.build_command("pre.bat", "case.cmb", 4)
        self.assertEqual(cmd.as_list(), ["pre.bat", "case.cmb", "4"])

    def test_license_and_extra(self):
        cmd = batch.build_command(
            "pre.bat", "case.cmb", 2,
            license_file=r"C:\lic\cradle.dat", extra=["-overwrite"])
        self.assertEqual(
            cmd.as_list(),
            ["pre.bat", "--license-file", r"C:\lic\cradle.dat",
             "case.cmb", "2", "-overwrite"])

    def test_as_shell(self):
        cmd = batch.build_command("pre.bat", "case.cmb", 1)
        self.assertIn("case.cmb", cmd.as_shell())


class TestFindCliBat(unittest.TestCase):
    def test_found(self):
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "scFLOWpreCLI_Bx64net.bat"
            fake.write_text("@echo off\n", encoding="ascii")
            orig = batch.scflowpre_probe.find_program
            batch.scflowpre_probe.find_program = (
                lambda name: fake if name == batch.CLI_BATS["pre"] else None)
            try:
                self.assertEqual(batch.find_cli_bat("pre"), fake)
                self.assertIsNone(batch.find_cli_bat("comb"))
            finally:
                batch.scflowpre_probe.find_program = orig

    def test_unknown_kind(self):
        with self.assertRaises(ValueError):
            batch.find_cli_bat("nope")


class TestInspect(unittest.TestCase):
    def test_dry_run(self):
        orig = batch._run_helper

        def fake_run(helper, command, bat, args):
            return ["mpirun -np 1 pre.exe case.cmb"]

        batch._run_helper = fake_run
        try:
            result = batch.inspect(
                Path("pre.bat"), ["case.cmb", "1"],
                helper=Path("helper.exe"))
        finally:
            batch._run_helper = orig
        self.assertTrue(result["available"])
        self.assertIn("mpirun", result["lines"][0])

    def test_missing_helper(self):
        orig = batch.scflowpre_probe.find_program
        batch.scflowpre_probe.find_program = lambda name: None
        try:
            result = batch.inspect(Path("pre.bat"), ["case.cmb", "1"])
        finally:
            batch.scflowpre_probe.find_program = orig
        self.assertFalse(result["available"])


class TestBatchBridge(unittest.TestCase):
    def test_plan_raises_without_bat(self):
        orig = batch.find_cli_bat
        batch.find_cli_bat = lambda kind: None
        try:
            bridge = batch.BatchBridge("pre")
            with self.assertRaises(FileNotFoundError):
                bridge.plan("case.cmb", 1)
        finally:
            batch.find_cli_bat = orig


if __name__ == "__main__":
    unittest.main()
