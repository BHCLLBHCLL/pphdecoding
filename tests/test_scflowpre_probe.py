#!/usr/bin/env python3
"""scFLOWpre 安装/API 探测测试（含真实安装跳过逻辑）。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scflowpre_probe as probe_mod  # noqa: E402


class TestFindInstall(unittest.TestCase):
    def test_missing_install(self, tmp_path=None):
        old = probe_mod.INSTALL_DIR_CANDIDATES
        probe_mod.INSTALL_DIR_CANDIDATES = [
            Path(r"C:\nonexistent_cradle_install")]
        try:
            self.assertIsNone(probe_mod.find_install())
        finally:
            probe_mod.INSTALL_DIR_CANDIDATES = old

    def test_fake_install(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            exe = root / "Programs_x64" / "scFLOWpre_Bx64net.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"MZfake")
            old = probe_mod.INSTALL_DIR_CANDIDATES
            probe_mod.INSTALL_DIR_CANDIDATES = [root]
            try:
                self.assertEqual(probe_mod.find_install(), root)
                self.assertEqual(probe_mod.find_program("scFLOWpre_Bx64net.exe"),
                                 exe)
                self.assertIsNone(probe_mod.find_program("missing.dll"))
            finally:
                probe_mod.INSTALL_DIR_CANDIDATES = old


class TestPeExports(unittest.TestCase):
    def test_not_pe(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.dll"
            p.write_bytes(b"not a pe")
            self.assertEqual(probe_mod.pe_exports(p), [])

    def test_real_install(self):
        root = probe_mod.find_install()
        if root is None:
            self.skipTest("本机未安装 scFLOWpre")
        dll = root / "Programs_x64" / "scFLOWpreCmd_Bx64net.dll"
        if not dll.is_file():
            self.skipTest("缺少 scFLOWpreCmd DLL")
        names = probe_mod.pe_exports(dll)
        self.assertGreater(len(names), 1000)
        self.assertTrue(any("CondBoundaryFlowIO" in n for n in names))


class TestProbe(unittest.TestCase):
    def test_probe_installed_shape(self):
        result = probe_mod.probe()
        self.assertIn("installed", result)
        if result["installed"]:
            self.assertIn("dll_export_counts", result)
            self.assertIn("scFLOWpreCmd_Bx64net.dll",
                          result["dll_export_counts"])


if __name__ == "__main__":
    unittest.main()
