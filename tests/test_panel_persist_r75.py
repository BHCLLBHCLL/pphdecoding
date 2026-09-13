#!/usr/bin/env python3
"""R7-5 回归：面板落盘收尾（_PartsControlFollowupBody → main.xenv）。

该面板唯一的用户态是「是否写出 scFLOWpre VBS」一个勾选；子类共用同一段、
按 _vbs_op 分键。审计口径：memory_only 降到 1（只剩对话框）。
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


class TestAuditAfterR75(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not AUDIT.is_file():
            raise unittest.SkipTest("audit tool missing")
        cls.audit = _load("panel_audit_r75", AUDIT)

    def test_only_the_dialog_remains_memory_only(self):
        data = self.audit.build()
        mem = sorted(p["panel"] for p in data["panels"]
                     if p["persistence"] == "memory_only")
        self.assertEqual(mem, ["CondTypeCatalogDialog"])
        self.assertGreaterEqual(data["counts"].get("persisted", 0), 16)

    def test_followup_body_is_persisted(self):
        by = {p["panel"]: p for p in self.audit.build()["panels"]}
        self.assertEqual(by["_PartsControlFollowupBody"]["persistence"],
                         "persisted:xenv")


class TestFollowupPersist(unittest.TestCase):
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

    def _body(self, op: str):
        cls = type("_T", (self.nav._PartsControlFollowupBody,),
                   {"_vbs_op": op, "title": "T-" + op})
        return cls()

    def test_checkbox_survives_reload_per_op(self):
        self._app()
        xenv = pphxml.XenvSettings()
        ctx = {"xenv": xenv, "session": {}}
        body = self._body("wrap")
        body.load(ctx)
        self.assertTrue(body.chk_write_vbs.isChecked())   # 默认 True
        body.chk_write_vbs.setChecked(False)
        self.assertTrue(body.apply(ctx))
        self.assertTrue(ctx["session"]["followup_persisted"])
        # 同 op 重新加载 → 读回 False
        ctx2 = {"xenv": xenv, "session": {}}
        body2 = self._body("wrap")
        body2.load(ctx2)
        self.assertFalse(body2.chk_write_vbs.isChecked())
        # 不同 op 不串键（各自独立）
        ctx3 = {"xenv": xenv, "session": {}}
        body3 = self._body("retry")
        body3.load(ctx3)
        self.assertTrue(body3.chk_write_vbs.isChecked())

    def test_pending_vbs_still_written_when_checked(self):
        self._app()
        xenv = pphxml.XenvSettings()
        ctx = {"xenv": xenv, "session": {}}
        body = self._body("wrap")
        body.load(ctx)
        body.apply(ctx)
        self.assertEqual(ctx["session"]["pending_vbs"]["op"], "wrap")

    def test_no_xenv_reports_not_persisted(self):
        self._app()
        ctx = {"session": {}}
        body = self._body("wrap")
        body.load(ctx)
        self.assertTrue(body.apply(ctx))
        self.assertFalse(ctx["session"]["followup_persisted"])


if __name__ == "__main__":
    unittest.main()
