#!/usr/bin/env python3
"""R3-2 回归：BC 去壳铺开（右键全字段入口 + 按名定位）。

R2-4 只给 flow BC 加了按钮；R3-2 把它泛化成：每个页面的条件列表挂右键
All fields (schema)... 菜单，并以**条件名**（不限类型）在 main.xml 里定位
元素。本文件钉住三件事：挂载幂等、任意页可挂、非条件节点不弹菜单。
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pphxml  # noqa: E402

MERGED = ROOT / "schemas" / "merged.json"

#: 持有 QApplication 引用（临时实例会被 GC，随后建控件即 abort）
_APPS: list = []


def _xml():
    box = ROOT / "box.pph"
    if not box.is_file():
        raise unittest.SkipTest("box.pph missing")
    from pph_parser import PphArchive
    arch = PphArchive.open(str(box))
    member = arch.by_role("project_xml")[0]
    return pphxml.parse_main_xml(arch.read_member(member.name))


class _Page:
    """最小页面替身：只带 _cond_list。"""

    def __init__(self, lst):
        self._cond_list = lst


class TestAnyNameLookup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import nav_panels
        except Exception:  # noqa: BLE001
            raise unittest.SkipTest("PyQt5 not available")
        cls.nav = nav_panels

    def test_find_by_name_ignores_type(self):
        xml = _xml()
        conds = xml.conditions()
        if not conds:
            self.skipTest("box.pph 无条件实体")
        el = conds[0]
        name = (el.findtext("name") or "").strip()
        if not name:
            self.skipTest("first condition unnamed")
        found = self.nav._find_condition_el_any(xml, name)
        self.assertIs(found, el)
        self.assertIsNone(
            self.nav._find_condition_el_any(xml, "no-such-cond"))
        self.assertIsNone(self.nav._find_condition_el_any(None, name))
        self.assertIsNone(self.nav._find_condition_el_any(xml, "  "))


class TestDeshellMenuHooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not MERGED.is_file():
            raise unittest.SkipTest("schemas/merged.json not generated")
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

    def _fake(self, lists):
        fake = type("FakeNav", (), {})()
        fake._pages = {("p" + str(i)): _Page(l)
                       for i, l in enumerate(lists)}
        fake._ctx = {"xml": _xml()}
        return fake

    def test_install_is_idempotent_and_covers_all_pages(self):
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QTreeWidget
        self._app()
        lists = [QTreeWidget(), QTreeWidget(), None]
        fake = self._fake(lists)
        self.nav.ConditionsBody._install_deshell_menus(fake)
        for lst in lists[:2]:
            self.assertEqual(lst.contextMenuPolicy(), Qt.CustomContextMenu)
        self.assertEqual(len(fake._deshell_hooked), 2)
        # 二次挂载不重复（否则一次右键弹多个菜单）
        self.nav.ConditionsBody._install_deshell_menus(fake)
        self.assertEqual(len(fake._deshell_hooked), 2)

    def test_non_condition_item_does_not_open_menu(self):
        from PyQt5.QtWidgets import QTreeWidget, QTreeWidgetItem
        self._app()
        lst = QTreeWidget()
        it = QTreeWidgetItem(["RegionThatIsNotACondition"])
        lst.addTopLevelItem(it)
        fake = self._fake([lst])
        calls = []
        fake._deshell_condition_el = lambda el: calls.append(el)
        pos = lst.visualItemRect(it).center()
        self.nav.ConditionsBody._deshell_menu(fake, lst, pos)
        self.assertEqual(calls, [])

    def test_fill_hooks_menus_and_entry_delegates(self):
        src = (ROOT / "nav_panels.py").read_text(encoding="utf-8")
        self.assertIn("self._install_deshell_menus()", src)
        self.assertIn("self._deshell_condition_el(el)", src)
        self.assertIn("All fields (schema)...", src)


if __name__ == "__main__":
    unittest.main()
