#!/usr/bin/env python3
"""R6-4 回归：面板落盘最后 2 页（Execute / CreateParts → main.xenv）。

这两个面板的用户态分别是「执行管线勾选项」与「Create Parts 表单草稿」；
本文件验证它们经 panel_json_set 落盘后，新实例 load 能原样读回。
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


class TestAuditAfterR64(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not AUDIT.is_file():
            raise unittest.SkipTest("audit tool missing")
        cls.audit = _load("panel_audit_r64", AUDIT)

    def test_last_two_panels_persisted(self):
        by = {p["panel"]: p for p in self.audit.build()["panels"]}
        for name in ("ExecuteBody", "CreatePartsBody"):
            self.assertEqual(by[name]["persistence"], "persisted:xenv", name)

    def test_only_dialog_and_followup_remain(self):
        data = self.audit.build()
        mem = sorted(n for n, p in
                     ((p["panel"], p) for p in data["panels"])
                     if p["persistence"] == "memory_only")
        self.assertEqual(mem, ["CondTypeCatalogDialog",
                               "_PartsControlFollowupBody"])


class TestExecutePersist(unittest.TestCase):
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

    def test_pipeline_flags_survive_reload(self):
        self._app()
        xenv = pphxml.XenvSettings()
        ctx = {"xenv": xenv, "session": {}, "groups_info": {}}
        body = self.nav.ExecuteBody()
        body.load(ctx)
        body.chk_wrap.setChecked(True)
        body.chk_mesh.setChecked(False)
        body.chk_files.setChecked(True)
        self.assertTrue(body.apply(ctx))
        self.assertTrue(ctx["session"]["execute_persisted"])
        ctx2 = {"xenv": xenv, "session": {}, "groups_info": {}}
        body2 = self.nav.ExecuteBody()
        body2.load(ctx2)
        self.assertTrue(body2.chk_wrap.isChecked())
        self.assertFalse(body2.chk_mesh.isChecked())
        self.assertTrue(body2.chk_files.isChecked())
        self.assertFalse(body2.chk_solver.isChecked())   # 强制不进管线

    def test_no_xenv_reports_not_persisted(self):
        self._app()
        ctx = {"session": {}, "groups_info": {}}
        body = self.nav.ExecuteBody()
        body.load(ctx)
        self.assertTrue(body.apply(ctx))
        self.assertFalse(ctx["session"]["execute_persisted"])


class TestCreatePartsDraftPersist(unittest.TestCase):
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

    def test_apply_writes_draft_to_xenv(self):
        self._app()
        xenv = pphxml.XenvSettings()
        ctx = {"xenv": xenv, "session": {}, "groups_info": {},
               "xml": None}
        body = self.nav.CreatePartsBody()
        body.load(ctx)
        self.assertTrue(body.apply(ctx))
        raw = xenv.get("PANEL_CREATE_PARTS", "draft", "")
        self.assertTrue(raw.startswith("{"))
        self.assertIn("shape", raw)
        # 同一份 xenv 重新加载（模拟重启）→ 草稿回到 session
        ctx2 = {"xenv": xenv, "session": {}, "groups_info": {},
                "xml": None}
        self.nav.CreatePartsBody().load(ctx2)
        self.assertIn("shape", ctx2["session"].get("create_parts", {}))

    def test_no_xenv_keeps_session_only(self):
        self._app()
        ctx = {"session": {}, "groups_info": {}, "xml": None}
        body = self.nav.CreatePartsBody()
        body.load(ctx)
        self.assertTrue(body.apply(ctx))
        self.assertFalse(ctx["session"]["create_parts_persisted"])
        self.assertIn("shape", ctx["session"]["create_parts"])


if __name__ == "__main__":
    unittest.main()
