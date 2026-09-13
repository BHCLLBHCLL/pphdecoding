#!/usr/bin/env python3
"""R4-3 / R4-4 回归：面板存储审计 + xenv 落盘通道。

* R4-3：panel_store_audit.build() 的分类必须与代码事实一致（OptionNav /
  MeshParam / NonSolid 曾全是 memory_only）；
* R4-4：panel_xenv_get/set 语义 + OptionNavBody 经 main.xenv 往返持久。
"""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pphwriter  # noqa: E402
import pphxml  # noqa: E402
from pph_parser import PphArchive  # noqa: E402

BOX = ROOT / "box.pph"
AUDIT = ROOT / "tools" / "panel_store_audit.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _xenv_from(pph: Path):
    arch = PphArchive.open(str(pph))
    names = [m.name for m in arch.members if m.name == "main.xenv"]
    if not names:
        return None
    return pphxml.parse_xenv(arch.read_member(names[0]))


class TestPanelStoreAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not AUDIT.is_file():
            raise unittest.SkipTest("tools/panel_store_audit.py missing")
        cls.audit = _load("panel_audit_r4", AUDIT)

    def test_classifies_memory_only_panels(self):
        # R5-3 之后 MeshParam/NonSolid 已落盘，memory_only 只剩这 4 个
        data = self.audit.build()
        by = {p["panel"]: p for p in data["panels"]}
        mem = sorted(n for n, p in by.items()
                     if p["persistence"] == "memory_only")
        self.assertEqual(mem, ["CondTypeCatalogDialog", "CreatePartsBody",
                               "ExecuteBody", "_PartsControlFollowupBody"])
        self.assertGreaterEqual(len(data["panels"]), 30)

    def test_option_nav_is_persisted_after_r44(self):
        data = self.audit.build()
        by = {p["panel"]: p for p in data["panels"]}
        self.assertEqual(by["OptionNavBody"]["persistence"], "persisted:xenv")
        ev = [e for e in by["OptionNavBody"]["evidence"] if e["mode"] == "write"]
        self.assertTrue(ev)

    def test_block_boundaries_do_not_swallow_module_functions(self):
        data = self.audit.build()
        by = {p["panel"]: p for p in data["panels"]}
        opt = by["OptionNavBody"]
        # 曾因类块吞掉模块级函数（condition_registry_cached）而误判 persisted:xml
        self.assertNotIn("xml", opt["stores_written"])
        src = (ROOT / "nav_panels.py").read_text(encoding="utf-8").splitlines()
        anchor = 1 + next(i for i, ln in enumerate(src)
                          if ln.startswith("def condition_registry_cached"))
        self.assertGreaterEqual(anchor, opt["lines"][1])


class TestPanelXenvChannel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import nav_panels
        except Exception:  # noqa: BLE001
            raise unittest.SkipTest("PyQt5 not available")
        cls.nav = nav_panels

    def test_set_requires_xenv(self):
        ctx = {"session": {}}
        self.assertFalse(self.nav.panel_xenv_set(ctx, "S", {"k": "v"}))
        self.assertNotIn("xenv_dirty", ctx)
        self.assertEqual(self.nav.panel_xenv_get(ctx, "S", "k", "d"), "d")

    def test_set_writes_and_flags_dirty(self):
        xenv = pphxml.XenvSettings()
        ctx = {"xenv": xenv}
        self.assertTrue(self.nav.panel_xenv_set(ctx, "S", {"k": "v"}))
        self.assertTrue(ctx["xenv_dirty"])
        self.assertEqual(self.nav.panel_xenv_get(ctx, "S", "k"), "v")
        self.assertEqual(self.nav.panel_xenv_get(ctx, "S", "nope", "d"), "d")

    def test_bool_roundtrip(self):
        self.assertEqual(self.nav.panel_bool_str(True), "true")
        self.assertEqual(self.nav.panel_bool_str(False), "false")
        for text, expect in (("true", True), ("false", False), ("1", True),
                             ("", False), ("yes", True)):
            self.assertEqual(self.nav.panel_bool(text), expect, text)

    def test_option_nav_persists_through_container(self):
        if not BOX.is_file():
            self.skipTest("box.pph missing")
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(
            ["test", "-platform", "offscreen"])
        _APPS.append(app)
        section = self.nav.OptionNavBody.XENV_SECTION
        with tempfile.TemporaryDirectory() as td:
            xenv = _xenv_from(BOX)
            ctx = {"xenv": xenv, "session": {}}
            self.assertTrue(self.nav.panel_xenv_set(
                ctx, section,
                {"always_show_wizard": "true", "show_bam_item": "false"}))
            out = Path(td) / "with_xenv.pph"
            pphwriter.clone_pph(str(BOX), str(out),
                                {"main.xenv": pphxml.serialize_xenv(xenv)})
            back = _xenv_from(out)
            self.assertIsNotNone(back)
            self.assertEqual(back.get(section, "always_show_wizard"), "true")
            self.assertEqual(back.get(section, "show_bam_item"), "false")
            # 面板读端：xenv 优先，session 兜底
            dlg = self.nav.OptionNavBody()
            dlg.load({"xenv": back, "session": {}})
            self.assertTrue(dlg.chk_always.isChecked())
            self.assertFalse(dlg.chk_show_bam.isChecked())
            self.assertTrue(dlg.chk_show_mesher.isChecked())
            sess_only = {"xenv": None, "session":
                         {"option_nav": {"show_bam_item": False}}}
            dlg2 = self.nav.OptionNavBody()
            dlg2.load(sess_only)
            self.assertFalse(dlg2.chk_show_bam.isChecked())


_APPS: list = []


if __name__ == "__main__":
    unittest.main()
