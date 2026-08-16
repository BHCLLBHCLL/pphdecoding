#!/usr/bin/env python3
"""VBScript 桥测试（纯函数 + 模拟执行后端）。"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation.vbs_bridge import (VbsBridge, build_vbs, read_vbs_lines,  # noqa: E402
                                   write_vbs_file)


class TestVbsBuild(unittest.TestCase):
    def test_build_vbs(self):
        text = build_vbs(['scFLOWpre.OpenProject "box.pph"',
                          "scFLOWpre.ExecuteWrapping"])
        self.assertIn("OpenProject", text)
        self.assertIn("ExecuteWrapping", text)
        self.assertTrue(text.endswith("\r\n"))

    def test_write_read_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p = write_vbs_file(
                ['scFLOWpre.OpenProject "box.pph"',
                 "scFLOWpre.ExportMesh _",
                 '  "mesh.gph"'],
                Path(td) / "run.vbs")
            lines = read_vbs_lines(p)
        self.assertEqual(
            lines,
            ['scFLOWpre.OpenProject "box.pph"',
             'scFLOWpre.ExportMesh "mesh.gph"'])

    def test_read_ignores_comments(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "run.vbs"
            p.write_text("' comment\nRem another\nscFLOWpre.Quit\n",
                         encoding="utf-8-sig")
            self.assertEqual(read_vbs_lines(p), ["scFLOWpre.Quit"])


class TestVbsBridge(unittest.TestCase):
    def test_launch_command_default_and_custom(self):
        bridge = VbsBridge(install_dir=str(Path("C:/cradle")), _exe_cache=None)
        bridge._exe_cache = Path(r"C:\cradle\Programs_x64\scFLOWpre_Bx64net.exe")
        self.assertEqual(
            bridge.launch_command("run.vbs"),
            [r"C:\cradle\Programs_x64\scFLOWpre_Bx64net.exe",
             "-vbs", "run.vbs"])
        self.assertEqual(
            bridge.launch_command("run.vbs", script_args=["/script", "run.vbs"]),
            [r"C:\cradle\Programs_x64\scFLOWpre_Bx64net.exe",
             "/script", "run.vbs"])

    def test_execute_manual(self):
        with tempfile.TemporaryDirectory() as td:
            p = write_vbs_file(["scFLOWpre.Quit"], Path(td) / "run.vbs")
            bridge = VbsBridge()
            result = bridge.execute(p, backend="manual")
        self.assertEqual(result["backend"], "manual")
        self.assertIn("Execute VBScript", result["hint"])

    def test_execute_cli_verified_absent(self):
        # 2026-08-17 实机确认 scFLOWpre 无 -vbs 开关，cli 后端返回显式
        # unsupported 且绝不拉起宿主（不再静默 subprocess.run）。
        with tempfile.TemporaryDirectory() as td:
            p = write_vbs_file(["scFLOWpre.Quit"], Path(td) / "run.vbs")
            bridge = VbsBridge()
            bridge._exe_cache = Path("scFLOWpre.exe")
            result = bridge.execute(p, backend="cli")
        self.assertEqual(result["backend"], "cli")
        self.assertTrue(result["verified_absent"])
        self.assertFalse(result["ok"])

    def test_execute_gui_hooks(self):
        import sys
        import types

        class FakeApp:
            def __init__(self, *a, **k):
                pass

            @staticmethod
            def start(*a, **k):
                return FakeApp()

            def window(self, **k):
                return FakeWindow()

        class FakeWindow:
            def wait(self, *a, **k):
                return None

            def menu_select(self, *a, **k):
                return None

            def child_window(self, **k):
                return FakeChild()

        class FakeChild:
            def set_edit_text(self, *a, **k):
                return None

            def click(self, *a, **k):
                return None

        fake_py = types.ModuleType("pywinauto")
        fake_app = types.ModuleType("pywinauto.application")
        fake_app.Application = FakeApp
        fake_py.application = fake_app
        saved = {}
        for name, mod in (("pywinauto", fake_py),
                          ("pywinauto.application", fake_app)):
            saved[name] = sys.modules.get(name)
            sys.modules[name] = mod
        try:
            with tempfile.TemporaryDirectory() as td:
                p = write_vbs_file(["scFLOWpre.Quit"], Path(td) / "run.vbs")
                bridge = VbsBridge()
                bridge._exe_cache = Path("scFLOWpre.exe")
                result = bridge._execute_gui(p, hooks={})
        finally:
            for name, mod in saved.items():
                if mod is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = mod
        self.assertEqual(result["backend"], "gui")
        self.assertEqual(result["status"], "submitted")


if __name__ == "__main__":
    unittest.main()
