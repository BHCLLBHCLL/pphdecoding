#!/usr/bin/env python3
"""R5-3 回归：面板落盘再切 2 页（MeshParam / NonSolid → main.xenv）。

R4-4 打通了 panel_xenv_set 通道；本文件验证 JSON 变体（panel_json_set/get）
与两个 memory_only 面板的「改 → 存（xenv）→ 新实例 load → 值回来」。
"""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pphxml  # noqa: E402

AUDIT = ROOT / "tools" / "panel_store_audit.py"
_APPS: list = []


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestAuditAfterR53(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not AUDIT.is_file():
            raise unittest.SkipTest("audit tool missing")
        cls.audit = _load("panel_audit_r53", AUDIT)

    def test_two_more_panels_are_persisted(self):
        by = {p["panel"]: p for p in self.audit.build()["panels"]}
        for name in ("MeshParamBody", "NonSolidBody"):
            self.assertEqual(by[name]["persistence"], "persisted:xenv", name)

    def test_memory_only_shrunk(self):
        # R5-3 时 6→4；此后只减不增（精确计数由最新一轮测试负责）
        data = self.audit.build()
        self.assertLessEqual(data["counts"].get("memory_only"), 4)
        self.assertGreaterEqual(data["counts"].get("persisted", 0), 15)


class TestJsonChannel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import nav_panels
        except Exception:  # noqa: BLE001
            raise unittest.SkipTest("PyQt5 not available")
        cls.nav = nav_panels

    def test_json_roundtrip(self):
        xenv = pphxml.XenvSettings()
        ctx = {"xenv": xenv}
        state = {"prism_n": 2, "nested": {"a": [1, 2]}, "assign": "Wrapping"}
        self.assertTrue(self.nav.panel_json_set(ctx, "S", {"state": state}))
        self.assertEqual(
            self.nav.panel_json_get(ctx, "S", "state", None), state)
        # 坏 JSON 不得抛，回落到默认值
        self.nav.panel_xenv_set(ctx, "S", {"bad": "{not json"})
        self.assertEqual(self.nav.panel_json_get(ctx, "S", "bad", "d"), "d")
        self.assertEqual(self.nav.panel_json_get(ctx, "S", "missing", "d"), "d")
        self.assertFalse(self.nav.panel_json_set({"session": {}}, "S", {"s": 1}))


class TestMeshParamPersist(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import nav_panels
        except Exception:  # noqa: BLE001
            raise unittest.SkipTest("PyQt5 not available")
        cls.nav = nav_panels

    def _app(self):
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(
            ["test", "-platform", "offscreen"])
        if not _APPS:
            _APPS.append(app)
        return _APPS[0]

    def test_values_survive_reload(self):
        self._app()
        xenv = pphxml.XenvSettings()
        ctx = {"xenv": xenv, "session": {}, "groups_info": {}}
        body = self.nav.MeshParamBody()
        body.load(ctx)
        body.sp_prism_t.setValue(3.5)
        body.sp_prism_n.setValue(4)
        body.rb_wrap.setChecked(True)
        body.rb_detail.setChecked(True)
        self.assertTrue(body.apply(ctx))
        self.assertTrue(ctx["session"]["mesh_param_persisted"])
        # 新实例 + 只带 xenv（模拟重启）→ 值必须回来
        ctx2 = {"xenv": xenv, "session": {}, "groups_info": {}}
        body2 = self.nav.MeshParamBody()
        body2.load(ctx2)
        self.assertAlmostEqual(body2.sp_prism_t.value(), 3.5, places=6)
        self.assertEqual(body2.sp_prism_n.value(), 4)
        self.assertTrue(body2.rb_wrap.isChecked())
        self.assertTrue(body2.rb_detail.isChecked())

    def test_no_xenv_reports_not_persisted(self):
        self._app()
        ctx = {"session": {}, "groups_info": {}}
        body = self.nav.MeshParamBody()
        body.load(ctx)
        self.assertTrue(body.apply(ctx))
        self.assertFalse(ctx["session"]["mesh_param_persisted"])


class TestNonSolidPersist(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import nav_panels
        except Exception:  # noqa: BLE001
            raise unittest.SkipTest("PyQt5 not available")
        cls.nav = nav_panels

    def _app(self):
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(
            ["test", "-platform", "offscreen"])
        if not _APPS:
            _APPS.append(app)
        return _APPS[0]

    def test_registered_lists_survive_reload(self):
        self._app()
        xenv = pphxml.XenvSettings()
        ctx = {"xenv": xenv, "session": {}, "groups_info": {}}
        body = self.nav.NonSolidBody()
        body.load(ctx)
        sess = body._sess()
        sess["group_parts"] = [{"name": "grp1", "parts": ["Part"]}]
        sess["sheet_parts"] = [{"name": "sheet1", "nfaces": 12}]
        self.assertTrue(body.apply(ctx))
        self.assertTrue(
            ctx["session"]["non_solid"]["non_solid_persisted"])
        ctx2 = {"xenv": xenv, "session": {}, "groups_info": {}}
        body2 = self.nav.NonSolidBody()
        body2.load(ctx2)
        self.assertEqual(body2._sess()["group_parts"],
                         [{"name": "grp1", "parts": ["Part"]}])
        self.assertEqual(body2._sess()["sheet_parts"],
                         [{"name": "sheet1", "nfaces": 12}])


if __name__ == "__main__":
    unittest.main()
