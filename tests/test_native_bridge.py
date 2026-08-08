#!/usr/bin/env python3
"""NativeBridge 加载器测试（未编译回退 + 已编译实机）。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import native_bridge  # noqa: E402


class TestNativeBridgeFallback(unittest.TestCase):
    def test_not_compiled_fallback(self):
        orig_dll = native_bridge.BRIDGE_DLL
        orig_probe = native_bridge.scflowpre_probe.probe
        native_bridge.BRIDGE_DLL = Path(r"C:\nonexistent\bridge.dll")
        native_bridge.scflowpre_probe.probe = (
            lambda: {"installed": False})
        try:
            self.assertFalse(native_bridge.is_compiled())
            self.assertIsNone(native_bridge.load())
            st = native_bridge.status()
        finally:
            native_bridge.BRIDGE_DLL = orig_dll
            native_bridge.scflowpre_probe.probe = orig_probe
        self.assertFalse(st["bridge_compiled"])
        self.assertFalse(st["fallback"]["installed"])


@unittest.skipUnless(native_bridge.is_compiled(),
                     "native/out/scflow_bridge.dll 未编译")
class TestNativeBridgeReal(unittest.TestCase):
    def test_status(self):
        st = native_bridge.status()
        self.assertTrue(st["bridge_compiled"])
        self.assertGreaterEqual(st["loaded_modules"], 1)
        self.assertIn("programs_dir", st["status"])


if __name__ == "__main__":
    unittest.main()
