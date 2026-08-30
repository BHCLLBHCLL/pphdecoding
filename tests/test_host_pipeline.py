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
from automation.history_vbs import decode_vbs  # noqa: E402


class TestBuildAndParse(unittest.TestCase):
    def test_build_pipeline_vbs(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            result = td / "result.txt"
            vbs = host_pipeline.build_pipeline_vbs(
                result, set_name="Box", group_name="BoxGroup",
                project_path=r"D:\training\cradle\box\box.pph",
                output=td / "host.vbs")
            text = decode_vbs(vbs.read_bytes())
            self.assertIn('Doc_.OpenProject "D:\\training\\cradle\\box\\box.pph", False', text)
            self.assertIn('CreateObject("pphdecoding.ScflowPipeline")', text)
            self.assertIn('CreateShapeGroupSet("Box")', text)
            # P10-1：句柄须 CLng() 转 Long，否则 VBScript Integer/VT_I2
            # 传回 COM 时 V_I4 读错 → SCF_ERR_ARG
            self.assertIn('CreateShapeGroup(CLng(hSet), "BoxGroup")', text)
            self.assertIn('CreateMDL(CLng(hGroup))', text)
            self.assertIn("Pipe.LastError()", text)

    def test_build_pipeline_vbs_deep(self):
        """P11：deep=True 追加 CreateFacetOctree / ExecuteWrapping 段。"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            result = td / "result.txt"
            vbs = host_pipeline.build_pipeline_vbs(
                result, set_name="Box", group_name="BoxGroup", deep=True,
                output=td / "deep.vbs")
            text = decode_vbs(vbs.read_bytes())
            self.assertIn('CreateFacetOctree(CLng(hGroup2), "BoxGroupOct")',
                          text)
            self.assertIn('ExecuteWrapping(CLng(hGroup2))', text)
            self.assertIn("facet_oct_handle=", text)
            self.assertIn("wrapping_ec=", text)
            self.assertIn("last_exception_code=", text)
            # P12-A：CreateMeshOctree（未知句柄→COM 层 SCF_ERR_ARG）+
            # ConvertFacetToXT（C ABI 全链）。
            self.assertIn("CreateMeshOctree(CLng(999901))", text)
            self.assertIn("mesh_oct_handle=", text)
            self.assertIn("ConvertFacetToXT(", text)
            self.assertIn("xt_ec=", text)
            self.assertIn("_p12_no_such.facet", text)
            # P11：深管线段须新建独立 set（主段已 ReleaseHandle hSet），
            # 否则 CreateShapeGroup 查不到句柄 → 深管线被 `If hGroup2 > 0`
            # 跳过（实机复现：facet_oct_handle/wrapping_ec 全部缺失）。
            self.assertIn('hSet2 = Pipe.CreateShapeGroupSet("BoxDeep")', text)
            self.assertIn('CreateShapeGroup(CLng(hSet2), "BoxGroupDeep")',
                          text)

    def test_build_pipeline_vbs_no_deep_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            result = td / "result.txt"
            vbs = host_pipeline.build_pipeline_vbs(
                result, set_name="Box", group_name="BoxGroup",
                output=td / "plain.vbs")
            text = decode_vbs(vbs.read_bytes())
            self.assertNotIn("CreateFacetOctree", text)
            self.assertNotIn("ExecuteWrapping", text)
            self.assertNotIn("CreateMeshOctree", text)
            self.assertNotIn("ConvertFacetToXT", text)

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

    def test_run_vbs_if_ready_skips_without_gui(self):
        with tempfile.TemporaryDirectory() as td:
            vbs = Path(td) / "host.vbs"
            vbs.write_text("' test", encoding="utf-8")
            fake = {
                "gui_ready": False,
                "hint": "no visible frame",
                "installed": True,
                "kicker_launcher": None,
                "running_pids": [],
                "any_visible": False,
            }
            with mock.patch.object(host_pipeline, "host_status",
                                   return_value=fake):
                result = host_pipeline.run_vbs_if_ready(vbs)
        self.assertTrue(result["skipped"])
        self.assertFalse(result["attempted"])
        self.assertFalse(result["ok"])

    def test_run_vbs_if_ready_calls_gui_when_ready(self):
        with tempfile.TemporaryDirectory() as td:
            vbs = Path(td) / "host.vbs"
            vbs.write_text("' test", encoding="utf-8")
            fake = {
                "gui_ready": True,
                "hint": "ok",
                "installed": True,
                "kicker_launcher": "Kicker",
                "running_pids": [1],
                "any_visible": True,
            }
            with mock.patch.object(host_pipeline, "host_status",
                                   return_value=fake):
                with mock.patch.object(
                        host_pipeline, "run_in_host",
                        return_value={"backend": "gui", "ok": True}):
                    result = host_pipeline.run_vbs_if_ready(vbs)
        self.assertTrue(result["attempted"])
        self.assertFalse(result["skipped"])
        self.assertTrue(result["ok"])

    def test_run_in_host_com_backend(self):
        with tempfile.TemporaryDirectory() as td:
            vbs = Path(td) / "host.vbs"
            vbs.write_text("' test", encoding="utf-8")
            with mock.patch.object(
                    host_pipeline, "_run_com_vbs",
                    return_value={"backend": "com", "ok": True,
                                  "script": str(vbs)}):
                result = host_pipeline.run_in_host(vbs, backend="com")
        self.assertEqual(result["backend"], "com")
        self.assertTrue(result["ok"])

    def test_run_in_host_rot_backend(self):
        """P10-2：rot 后端经 _run_rot_vbs 附着 Kicker 实例执行。"""
        with tempfile.TemporaryDirectory() as td:
            vbs = Path(td) / "host.vbs"
            vbs.write_text("' test", encoding="utf-8")
            with mock.patch.object(
                    host_pipeline, "_run_rot_vbs",
                    return_value={"backend": "rot", "ok": True,
                                  "owned": False, "script": str(vbs)}):
                result = host_pipeline.run_in_host(vbs, backend="rot")
        self.assertEqual(result["backend"], "rot")
        self.assertTrue(result["ok"])
        self.assertFalse(result["owned"])

    def test_run_rot_vbs_attach_first(self):
        """rot 后端不真连 COM：ScFlowpreSession 附着优先（owned=False）。"""
        fake_session = mock.MagicMock()
        fake_session.connect.return_value = True
        fake_session.owned = False
        fake_session.execute_vbs_file.return_value = True
        with tempfile.TemporaryDirectory() as td:
            vbs = Path(td) / "host.vbs"
            vbs.write_text("' test", encoding="utf-8")
            with mock.patch(
                    "automation.scflowpre_api.ScFlowpreSession",
                    return_value=fake_session):
                result = host_pipeline._run_rot_vbs(vbs, timeout=5.0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "rot")
        self.assertFalse(result["owned"])
        fake_session.connect.assert_called_once()
        fake_session.execute_vbs_file.assert_called_once_with(vbs)
        fake_session.close.assert_called_once()

    def test_run_rot_vbs_connect_failure(self):
        fake_session = mock.MagicMock()
        fake_session.connect.return_value = False
        import automation.scflowpre_api as api_mod
        with tempfile.TemporaryDirectory() as td:
            vbs = Path(td) / "host.vbs"
            vbs.write_text("' test", encoding="utf-8")
            with mock.patch.object(api_mod, "last_error", "no host"), \
                 mock.patch("automation.scflowpre_api.ScFlowpreSession",
                            return_value=fake_session):
                result = host_pipeline._run_rot_vbs(vbs, timeout=5.0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["backend"], "rot")
        self.assertIn("no host", result["error"])
        fake_session.execute_vbs_file.assert_not_called()

    def test_run_com_vbs_flags_methods(self):
        """晚绑定须 FlagAsMethod，禁止属性赋值。"""
        flagged: list = []

        class _Disp:
            def _FlagAsMethod(self, *names):
                flagged.extend(names)

            def ExecuteVBSWithFile(self, path):
                return True

            def ExecuteVBS(self, code):
                raise AssertionError("should not fallback")

        with tempfile.TemporaryDirectory() as td:
            vbs = Path(td) / "host.vbs"
            vbs.write_bytes(("' noop\r\n").encode("utf-16"))
            with mock.patch("pythoncom.CoInitialize"), \
                    mock.patch("pythoncom.CoUninitialize"), \
                    mock.patch("win32com.client.Dispatch",
                               return_value=_Disp()):
                result = host_pipeline._run_com_vbs(vbs, timeout=5.0)
        self.assertIn("ExecuteVBSWithFile", flagged)
        self.assertIn("ExecuteVBS", flagged)
        self.assertTrue(result["ok"])
        self.assertEqual(result.get("method"), "ExecuteVBSWithFile")

    def test_run_in_host_unknown_backend(self):
        with tempfile.TemporaryDirectory() as td:
            vbs = Path(td) / "host.vbs"
            vbs.write_text("' test", encoding="utf-8")
            with self.assertRaises(ValueError):
                host_pipeline.run_in_host(vbs, backend="nope")

    def test_locate_scflowpre(self):
        fake_root = Path(r"C:\Program Files\Cradle\CradleCFD2025.2")
        with mock.patch.object(host_pipeline.scflowpre_probe,
                               "find_install",
                               return_value=fake_root), \
             mock.patch.object(
                 host_pipeline.scflowpre_probe, "probe_com_progpids",
                 return_value={
                     "scFLOWpre_Bx64net.Application.2025": True,
                     "scConverter_Sx64net.Application.2025": True,
                     "STpre_Bx64net.Application.2025": False,
                 }) as probe_pids:
            info = host_pipeline.locate_scflowpre()
        self.assertTrue(info["installed"])
        self.assertEqual(info["install_dir"], str(fake_root))
        self.assertTrue(info["programs_dir"].endswith("Programs_x64"))
        # P4-3：关联 ProgID（scConverter / STpre 等）随探测结果返回
        probe_pids.assert_called_once()
        self.assertNotIn("scFLOWpre_Bx64net.Application.2025",
                         info["related_progpids"])
        self.assertTrue(info["related_progpids"]
                        ["scConverter_Sx64net.Application.2025"])
        self.assertFalse(info["related_progpids"]
                         ["STpre_Bx64net.Application.2025"])


class TestBackendConvergence(unittest.TestCase):
    """P12-A 后端收敛：rot 唯一权威通道，gui/manual/com 仅诊断。"""

    def test_authoritative_backend_constant(self):
        self.assertEqual(host_pipeline.AUTHORITATIVE_BACKEND, "rot")

    def test_resolve_backend_default_is_rot(self):
        self.assertEqual(host_pipeline.resolve_backend(), "rot")
        self.assertEqual(host_pipeline.resolve_backend(None), "rot")
        # 显式诊断通道按原样放行
        self.assertEqual(host_pipeline.resolve_backend("manual"), "manual")
        self.assertEqual(host_pipeline.resolve_backend("gui"), "gui")
        self.assertEqual(host_pipeline.resolve_backend("com"), "com")
        self.assertEqual(host_pipeline.resolve_backend("rot"), "rot")

    def test_resolve_backend_rejects_unknown(self):
        with self.assertRaises(ValueError):
            host_pipeline.resolve_backend("bogus")

    def test_run_in_host_default_routes_rot(self):
        """未指定 backend → rot（权威），不再默认 manual。"""
        with tempfile.TemporaryDirectory() as td:
            vbs = Path(td) / "host.vbs"
            vbs.write_text("' test", encoding="utf-8")
            with mock.patch.object(
                    host_pipeline, "_run_rot_vbs",
                    return_value={"backend": "rot", "ok": True,
                                  "script": str(vbs)}) as rot:
                result = host_pipeline.run_in_host(vbs)
        self.assertEqual(result["backend"], "rot")
        self.assertTrue(result["ok"])
        rot.assert_called_once()

    def test_run_vbs_authoritative_routes_rot(self):
        """GUI Execute 权威入口：rot，无 com 回退。"""
        with tempfile.TemporaryDirectory() as td:
            vbs = Path(td) / "host.vbs"
            vbs.write_text("' test", encoding="utf-8")
            with mock.patch.object(
                    host_pipeline, "_run_rot_vbs",
                    return_value={"backend": "rot", "ok": True,
                                  "script": str(vbs)}) as rot, \
                 mock.patch.object(
                    host_pipeline, "_run_com_vbs") as com:
                result = host_pipeline.run_vbs_authoritative(vbs)
        self.assertEqual(result["backend"], "rot")
        self.assertTrue(result["ok"])
        rot.assert_called_once()
        com.assert_not_called()

    def test_gui_uses_authoritative_channel(self):
        """pph_gui 的两处执行调用点必须走 run_vbs_authoritative。

        P12-A 验收「测试锁定路由」：GUI 不再直接指定 com 后端。
        """
        src = Path("pph_gui.py").read_text(encoding="utf-8")
        self.assertNotIn('run_in_host(path, backend="com")', src)
        self.assertNotIn('run_in_host(vbs, backend="com")', src)
        self.assertIn("host_pipeline.run_vbs_authoritative(path)", src)
        self.assertIn("host_pipeline.run_vbs_authoritative(vbs)", src)


class TestBackendConvergence(unittest.TestCase):
    """P12-A 后端收敛：rot 唯一权威通道，gui/manual/com 仅诊断。"""

    def test_authoritative_backend_constant(self):
        self.assertEqual(host_pipeline.AUTHORITATIVE_BACKEND, "rot")

    def test_resolve_backend_default_is_rot(self):
        self.assertEqual(host_pipeline.resolve_backend(), "rot")
        self.assertEqual(host_pipeline.resolve_backend(None), "rot")
        # 显式诊断通道按原样放行
        self.assertEqual(host_pipeline.resolve_backend("manual"), "manual")
        self.assertEqual(host_pipeline.resolve_backend("gui"), "gui")
        self.assertEqual(host_pipeline.resolve_backend("com"), "com")
        self.assertEqual(host_pipeline.resolve_backend("rot"), "rot")

    def test_resolve_backend_rejects_unknown(self):
        with self.assertRaises(ValueError):
            host_pipeline.resolve_backend("bogus")

    def test_run_in_host_default_routes_rot(self):
        """未指定 backend → rot（权威），不再默认 manual。"""
        with tempfile.TemporaryDirectory() as td:
            vbs = Path(td) / "host.vbs"
            vbs.write_text("' test", encoding="utf-8")
            with mock.patch.object(
                    host_pipeline, "_run_rot_vbs",
                    return_value={"backend": "rot", "ok": True,
                                  "script": str(vbs)}) as rot:
                result = host_pipeline.run_in_host(vbs)
        self.assertEqual(result["backend"], "rot")
        self.assertTrue(result["ok"])
        rot.assert_called_once()

    def test_run_vbs_authoritative_routes_rot(self):
        """GUI Execute 权威入口：rot，无 com 回退。"""
        with tempfile.TemporaryDirectory() as td:
            vbs = Path(td) / "host.vbs"
            vbs.write_text("' test", encoding="utf-8")
            with mock.patch.object(
                    host_pipeline, "_run_rot_vbs",
                    return_value={"backend": "rot", "ok": True,
                                  "script": str(vbs)}) as rot, \
                 mock.patch.object(
                    host_pipeline, "_run_com_vbs") as com:
                result = host_pipeline.run_vbs_authoritative(vbs)
        self.assertEqual(result["backend"], "rot")
        self.assertTrue(result["ok"])
        rot.assert_called_once()
        com.assert_not_called()

    def test_gui_uses_authoritative_channel(self):
        """pph_gui 的两处执行调用点必须走 run_vbs_authoritative。

        P12-A 验收「测试锁定路由」：GUI 不再直接指定 com 后端。
        """
        src = Path("pph_gui.py").read_text(encoding="utf-8")
        self.assertNotIn('run_in_host(path, backend="com")', src)
        self.assertNotIn('run_in_host(vbs, backend="com")', src)
        self.assertIn("host_pipeline.run_vbs_authoritative(path)", src)
        self.assertIn("host_pipeline.run_vbs_authoritative(vbs)", src)


class TestBackendConvergence(unittest.TestCase):
    """P12-A 后端收敛：rot 唯一权威通道，gui/manual/com 仅诊断。"""

    def test_authoritative_backend_constant(self):
        self.assertEqual(host_pipeline.AUTHORITATIVE_BACKEND, "rot")

    def test_resolve_backend_default_is_rot(self):
        self.assertEqual(host_pipeline.resolve_backend(), "rot")
        self.assertEqual(host_pipeline.resolve_backend(None), "rot")
        # 显式诊断通道按原样放行
        self.assertEqual(host_pipeline.resolve_backend("manual"), "manual")
        self.assertEqual(host_pipeline.resolve_backend("gui"), "gui")
        self.assertEqual(host_pipeline.resolve_backend("com"), "com")
        self.assertEqual(host_pipeline.resolve_backend("rot"), "rot")

    def test_resolve_backend_rejects_unknown(self):
        with self.assertRaises(ValueError):
            host_pipeline.resolve_backend("bogus")

    def test_run_in_host_default_routes_rot(self):
        """未指定 backend → rot（权威），不再默认 manual。"""
        with tempfile.TemporaryDirectory() as td:
            vbs = Path(td) / "host.vbs"
            vbs.write_text("' test", encoding="utf-8")
            with mock.patch.object(
                    host_pipeline, "_run_rot_vbs",
                    return_value={"backend": "rot", "ok": True,
                                  "script": str(vbs)}) as rot:
                result = host_pipeline.run_in_host(vbs)
        self.assertEqual(result["backend"], "rot")
        self.assertTrue(result["ok"])
        rot.assert_called_once()

    def test_run_vbs_authoritative_routes_rot(self):
        """GUI Execute 权威入口：rot，无 com 回退。"""
        with tempfile.TemporaryDirectory() as td:
            vbs = Path(td) / "host.vbs"
            vbs.write_text("' test", encoding="utf-8")
            with mock.patch.object(
                    host_pipeline, "_run_rot_vbs",
                    return_value={"backend": "rot", "ok": True,
                                  "script": str(vbs)}) as rot, \
                 mock.patch.object(
                    host_pipeline, "_run_com_vbs") as com:
                result = host_pipeline.run_vbs_authoritative(vbs)
        self.assertEqual(result["backend"], "rot")
        self.assertTrue(result["ok"])
        rot.assert_called_once()
        com.assert_not_called()

    def test_gui_uses_authoritative_channel(self):
        """pph_gui 的两处执行调用点必须走 run_vbs_authoritative。

        P12-A 验收「测试锁定路由」：GUI 不再直接指定 com 后端。
        """
        src = Path("pph_gui.py").read_text(encoding="utf-8")
        self.assertNotIn('run_in_host(path, backend="com")', src)
        self.assertNotIn('run_in_host(vbs, backend="com")', src)
        self.assertIn("host_pipeline.run_vbs_authoritative(path)", src)
        self.assertIn("host_pipeline.run_vbs_authoritative(vbs)", src)


class TestBackendConvergence(unittest.TestCase):
    """P12-A 后端收敛：rot 唯一权威通道，gui/manual/com 仅诊断。"""

    def test_authoritative_backend_constant(self):
        self.assertEqual(host_pipeline.AUTHORITATIVE_BACKEND, "rot")

    def test_resolve_backend_default_is_rot(self):
        self.assertEqual(host_pipeline.resolve_backend(), "rot")
        self.assertEqual(host_pipeline.resolve_backend(None), "rot")
        # 显式诊断通道按原样放行
        self.assertEqual(host_pipeline.resolve_backend("manual"), "manual")
        self.assertEqual(host_pipeline.resolve_backend("gui"), "gui")
        self.assertEqual(host_pipeline.resolve_backend("com"), "com")
        self.assertEqual(host_pipeline.resolve_backend("rot"), "rot")

    def test_resolve_backend_rejects_unknown(self):
        with self.assertRaises(ValueError):
            host_pipeline.resolve_backend("bogus")

    def test_run_in_host_default_routes_rot(self):
        """未指定 backend → rot（权威），不再默认 manual。"""
        with tempfile.TemporaryDirectory() as td:
            vbs = Path(td) / "host.vbs"
            vbs.write_text("' test", encoding="utf-8")
            with mock.patch.object(
                    host_pipeline, "_run_rot_vbs",
                    return_value={"backend": "rot", "ok": True,
                                  "script": str(vbs)}) as rot:
                result = host_pipeline.run_in_host(vbs)
        self.assertEqual(result["backend"], "rot")
        self.assertTrue(result["ok"])
        rot.assert_called_once()

    def test_run_vbs_authoritative_routes_rot(self):
        """GUI Execute 权威入口：rot，无 com 回退。"""
        with tempfile.TemporaryDirectory() as td:
            vbs = Path(td) / "host.vbs"
            vbs.write_text("' test", encoding="utf-8")
            with mock.patch.object(
                    host_pipeline, "_run_rot_vbs",
                    return_value={"backend": "rot", "ok": True,
                                  "script": str(vbs)}) as rot, \
                 mock.patch.object(
                    host_pipeline, "_run_com_vbs") as com:
                result = host_pipeline.run_vbs_authoritative(vbs)
        self.assertEqual(result["backend"], "rot")
        self.assertTrue(result["ok"])
        rot.assert_called_once()
        com.assert_not_called()

    def test_gui_uses_authoritative_channel(self):
        """pph_gui 的两处执行调用点必须走 run_vbs_authoritative。

        P12-A 验收「测试锁定路由」：GUI 不再直接指定 com 后端。
        """
        src = Path("pph_gui.py").read_text(encoding="utf-8")
        self.assertNotIn('run_in_host(path, backend="com")', src)
        self.assertNotIn('run_in_host(vbs, backend="com")', src)
        self.assertIn("host_pipeline.run_vbs_authoritative(path)", src)
        self.assertIn("host_pipeline.run_vbs_authoritative(vbs)", src)


class TestHostStatus(unittest.TestCase):
    """P6-5 宿主交互环境收敛：host_status 诊断口。"""

    def _fake_program(self, name):
        base = Path(r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64")
        return base / name

    def test_host_status_visible_instance(self):
        exe = self._fake_program("scFLOWpre_Bx64net.exe")
        kicker = self._fake_program("Kicker_Bx64.exe")
        with mock.patch.object(host_pipeline.scflowpre_probe, "find_program",
                               side_effect=lambda n: {exe.name: exe,
                                                      kicker.name: kicker}[n]), \
             mock.patch.object(host_pipeline, "_find_scflow_process",
                               return_value=[21240, 22468]), \
             mock.patch.object(host_pipeline, "_instance_window_info",
                               side_effect=[
                                   {"pid": 21240, "visible": False,
                                    "window_title": "", "window_handle": None},
                                   {"pid": 22468, "visible": True,
                                    "window_title": "scFLOWpre",
                                    "window_handle": 123},
                               ]):
            status = host_pipeline.host_status()
        self.assertTrue(status["installed"])
        self.assertEqual(status["kicker_launcher"], str(kicker))
        self.assertEqual(status["running_pids"], [21240, 22468])
        self.assertTrue(status["any_visible"])
        self.assertTrue(status["gui_ready"])
        self.assertIn("gui 后端可自动驱动", status["hint"])

    def test_host_status_no_visible_instance(self):
        exe = self._fake_program("scFLOWpre_Bx64net.exe")
        kicker = self._fake_program("Kicker_Bx64.exe")
        with mock.patch.object(host_pipeline.scflowpre_probe, "find_program",
                               side_effect=lambda n: {exe.name: exe,
                                                      kicker.name: kicker}[n]), \
             mock.patch.object(host_pipeline, "_find_scflow_process",
                               return_value=[21240]), \
             mock.patch.object(host_pipeline, "_instance_window_info",
                               return_value={"pid": 21240, "visible": False,
                                             "window_title": "",
                                             "window_handle": None}):
            status = host_pipeline.host_status()
        self.assertFalse(status["any_visible"])
        self.assertFalse(status["gui_ready"])
        self.assertIn("Kicker_Bx64.exe", status["hint"])

    def test_host_status_not_running(self):
        exe = self._fake_program("scFLOWpre_Bx64net.exe")
        kicker = self._fake_program("Kicker_Bx64.exe")
        with mock.patch.object(host_pipeline.scflowpre_probe, "find_program",
                               side_effect=lambda n: {exe.name: exe,
                                                      kicker.name: kicker}[n]), \
             mock.patch.object(host_pipeline, "_find_scflow_process",
                               return_value=[]):
            status = host_pipeline.host_status()
        self.assertFalse(status["any_visible"])
        self.assertIn("Kicker_Bx64.exe", status["hint"])
        self.assertEqual(status["instances"], [])

    def test_instance_window_info_matches_frame(self):
        class _W:
            process_id = 42
            class_name = "Afx:00007FF683D10000:0"
            name = "scFLOWpre"
            handle = 12345
            visible = True

        class _Other:
            process_id = 43
            class_name = "#32770"
            name = "dialog"
            handle = 999
            visible = False

        with mock.patch("pywinauto.findwindows.find_elements",
                        return_value=[_Other(), _W()]):
            info = host_pipeline._instance_window_info(42)
        self.assertTrue(info["visible"])
        self.assertEqual(info["window_handle"], 12345)
        self.assertEqual(info["window_title"], "scFLOWpre")

    def test_instance_window_info_no_frame(self):
        class _W:
            process_id = 42
            class_name = "#32770"
            name = "dialog"
            handle = 999
            visible = True

        with mock.patch("pywinauto.findwindows.find_elements",
                        return_value=[_W()]):
            info = host_pipeline._instance_window_info(42)
        self.assertFalse(info["visible"])
        self.assertIsNone(info["window_handle"])


if __name__ == "__main__":
    unittest.main()
