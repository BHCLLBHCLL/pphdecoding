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
        native_bridge._INITIALIZED_LIB = None
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
            native_bridge._INITIALIZED_LIB = None
        self.assertFalse(st["bridge_compiled"])
        self.assertFalse(st["fallback"]["installed"])

    def test_pipeline_status_fallback(self):
        orig_dll = native_bridge.BRIDGE_DLL
        native_bridge._INITIALIZED_LIB = None
        native_bridge.BRIDGE_DLL = Path(r"C:\nonexistent\bridge.dll")
        try:
            st = native_bridge.pipeline_status()
        finally:
            native_bridge.BRIDGE_DLL = orig_dll
            native_bridge._INITIALIZED_LIB = None
        self.assertFalse(st["bridge_compiled"])
        self.assertFalse(any(st["symbols"].values()))

    def test_expand_zip_requires_bridge(self):
        orig_dll = native_bridge.BRIDGE_DLL
        native_bridge._INITIALIZED_LIB = None
        native_bridge.BRIDGE_DLL = Path(r"C:\nonexistent\bridge.dll")
        try:
            with self.assertRaises(RuntimeError):
                native_bridge.expand_zip("a.zip", "out")
        finally:
            native_bridge.BRIDGE_DLL = orig_dll
            native_bridge._INITIALIZED_LIB = None

    def test_pipeline_calls_require_bridge(self):
        orig_dll = native_bridge.BRIDGE_DLL
        native_bridge._INITIALIZED_LIB = None
        native_bridge.BRIDGE_DLL = Path(r"C:\nonexistent\bridge.dll")
        try:
            with self.assertRaises(RuntimeError):
                native_bridge.pipeline_context_ready()
            with self.assertRaises(RuntimeError):
                native_bridge.create_shape_group_set("Probe")
        finally:
            native_bridge.BRIDGE_DLL = orig_dll
            native_bridge._INITIALIZED_LIB = None


@unittest.skipUnless(native_bridge.is_compiled(),
                     "native/out/scflow_bridge.dll 未编译")
class TestNativeBridgeReal(unittest.TestCase):
    def test_status(self):
        st = native_bridge.status()
        self.assertTrue(st["bridge_compiled"])
        self.assertGreaterEqual(st["loaded_modules"], 1)
        self.assertIn("programs_dir", st["status"])

    def test_pipeline_status(self):
        st = native_bridge.pipeline_status()
        self.assertTrue(st["bridge_compiled"])
        self.assertGreaterEqual(len(st["symbols"]), 9)
        self.assertTrue(all(st["symbols"].values()))

    def test_pipeline_context_and_create_set(self):
        ctx = native_bridge.pipeline_context_ready()
        self.assertIn("ready", ctx)
        result = native_bridge.create_shape_group_set("Probe")
        if result.get("ok"):
            self.assertGreater(result["ptr"], 0)
            group = native_bridge.create_shape_group(
                result["handle"], "ProbeGroup")
            self.assertTrue(group["ok"])
            mdl = native_bridge.create_mdl(group["handle"])
            self.assertTrue(mdl["ok"])
            native_bridge.release(group["handle"])
            native_bridge.release(result["handle"])
        else:
            self.assertIn(result["error_code"], (
                native_bridge.SCF_ERR_CONTEXT_NOT_READY,
                native_bridge.SCF_ERR_EXCEPTION,
                native_bridge.SCF_ERR_SYMBOL,
                native_bridge.SCF_ERR_NULL_OBJECT))
            self.assertIn("message", result)


if __name__ == "__main__":
    unittest.main()
