#!/usr/bin/env python3
"""NativeBridge 加载器测试（未编译回退 + 已编译实机）。"""

import os
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

    def test_p11_calls_unknown_handle(self):
        """P11：handle 不在 _OBJECT_BUFFERS 时先校验，不触发 DLL 加载。"""
        native_bridge._OBJECT_BUFFERS.clear()
        r1 = native_bridge.create_facet_octree(12345, "oct")
        self.assertFalse(r1["ok"])
        self.assertEqual(r1["error_code"], native_bridge.SCF_ERR_ARG)
        r2 = native_bridge.execute_wrapping(12345)
        self.assertFalse(r2["ok"])
        self.assertEqual(r2["error_code"], native_bridge.SCF_ERR_ARG)
        r3 = native_bridge.create_mesh_octree(12345)
        self.assertFalse(r3["ok"])
        self.assertEqual(r3["error_code"], native_bridge.SCF_ERR_ARG)


class TestComDispatchSurface(unittest.TestCase):
    """P12-A：COM 桥（scflow_com.cpp）分发表完整性——每个业务方法须有
    dispid enum + 名称表条目 + Invoke case，防止新增 C ABI 后忘记接 COM
    分发（P12-A 前车之鉴：CreateMeshOctree/ConvertFacetToXT 有 C ABI 无
    dispid）。源码级守卫，不依赖宿主。"""

    CASES = (
        ("ContextReady", 1), ("CreateShapeGroupSet", 2),
        ("CreateShapeGroup", 3), ("CreateMDL", 4), ("ReleaseHandle", 5),
        ("LastError", 6), ("LastErrorMessage", 7), ("Status", 8),
        ("ContextReadyRaw", 9), ("LastExceptionCode", 10),
        ("CreateFacetOctree", 11), ("ExecuteWrapping", 12),
        ("CreateMeshOctree", 13), ("ConvertFacetToXT", 14),
    )

    def test_dispatch_table_complete(self):
        src = (ROOT / "native" / "scflow_com.cpp").read_text(
            encoding="utf-8")
        for name, dispid in self.CASES:
            self.assertIn(f"L\"{name}\"", src,
                          f"名称表缺 {name}")
            self.assertIn(f"kDisp{name} = {dispid},", src,
                          f"enum 缺 {name}={dispid}")
            self.assertIn(f"case kDisp{name}:", src,
                          f"Invoke case 缺 {name}")


@unittest.skipUnless(
    native_bridge.is_compiled()
    and os.environ.get("SCF_RUN_BRIDGE_TESTS") == "1",
    "需要 bridge 已编译且 SCF_RUN_BRIDGE_TESTS=1（实机调用加载厂商 "
    "DLL，与 Qt offscreen 同进程会访问冲突，不默认混入全量回归）")
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
