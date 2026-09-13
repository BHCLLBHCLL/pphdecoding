#!/usr/bin/env python3
"""R2-4 回归：条件编辑器去壳（schema 全字段入口 + 原地重写）。

- 纯逻辑：``_condition_to_initial`` / ``_flatten_cond`` /
  ``_find_condition_el`` 与 ``write_condition_to_xml(replace_el=...)``
  的"原地重写、不新增、不留旧字段"语义；
- Qt：``GenericCondBody(initial=...)`` 的 name/fields 预填与 Edit 标题。
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pphxml  # noqa: E402
from condition_registry import ConditionRegistry  # noqa: E402
from schema_extract import load_schema_json  # noqa: E402

MERGED = ROOT / "schemas" / "merged.json"


def _registry() -> ConditionRegistry:
    return ConditionRegistry.from_schemas(
        [(load_schema_json(MERGED), "merged")])


def _ctx_with_xml() -> dict:
    box = ROOT / "box.pph"
    if not box.is_file():
        raise unittest.SkipTest("box.pph missing")
    from pph_parser import PphArchive
    arch = PphArchive.open(str(box))
    member = arch.by_role("project_xml")[0]
    return {"xml": pphxml.parse_main_xml(arch.read_member(member.name))}


class _StubType:
    """无注册表条目时的最小 ctype（只用 ``fields`` 决定区域子标签）。"""

    fields: list = []


def _ctype_for(typ: str):
    t = _registry().get(typ)
    return t if t is not None else _StubType()


class TestDeshellHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not MERGED.is_file():
            raise unittest.SkipTest("schemas/merged.json not generated")
        try:
            import nav_panels
        except Exception:  # noqa: BLE001
            raise unittest.SkipTest("PyQt5 not available")
        cls.nav = nav_panels

    def _first(self):
        ctx = _ctx_with_xml()
        conds = ctx["xml"].conditions()
        if not conds:
            self.skipTest("box.pph 无条件实体")
        return ctx, conds, conds[0]

    def test_initial_roundtrip_and_lookup(self):
        ctx, _conds, el = self._first()
        init = self.nav._condition_to_initial(el)
        self.assertEqual(init["name"], (el.findtext("name") or "").strip())
        regs = el.find("regions")
        if regs is not None:
            self.assertEqual(
                init["regions"],
                [(c.text or "").strip() for c in list(regs)
                 if (c.text or "").strip()])
        typ = el.findtext("type") or ""
        found = self.nav._find_condition_el(ctx["xml"], typ, init["name"])
        self.assertIs(found, el)
        # 结构父节点的叶子都进了路径表（无文本的父节点不进）
        for path in init["fields"]:
            self.assertNotIn(path, ("type", "name", "regions"))

    def test_replace_el_rewrites_in_place(self):
        ctx, conds, el = self._first()
        before = len(conds)
        typ = el.findtext("type") or ""
        init = self.nav._condition_to_initial(el)
        data = {"type": typ, "name": "R24Replace",
                "regions": ["r24_region"], "fields": {"r24_only": "1"}}
        self.assertTrue(self.nav.write_condition_to_xml(
            ctx, _ctype_for(typ), data, replace_el=el))
        self.assertEqual(len(ctx["xml"].conditions()), before)
        self.assertIs(
            self.nav._find_condition_el(ctx["xml"], typ, "R24Replace"), el)
        regs = el.find("regions")
        self.assertIsNotNone(regs)
        self.assertEqual([(c.text or "") for c in list(regs)],
                         ["r24_region"])
        self.assertEqual(el.findtext("r24_only"), "1")
        # 原地重写语义：旧字段必须已被清空
        for path in init["fields"]:
            if path == "r24_only":
                continue
            node = el
            for seg in path.split("."):
                node = node.find(seg) if node is not None else None
            self.assertIsNone(node, "stale field survived: " + path)

    def test_create_still_appends(self):
        ctx, conds, _el = self._first()
        before = len(conds)
        typ = "CondBoundaryFlowIO"
        data = {"type": typ, "name": "R24New", "regions": [],
                "fields": {"a": "b"}}
        self.assertTrue(self.nav.write_condition_to_xml(
            ctx, _ctype_for(typ), data))
        conds2 = ctx["xml"].conditions()
        self.assertEqual(len(conds2), before + 1)
        self.assertEqual(conds2[-1].findtext("name"), "R24New")


class TestGenericCondBodyPrefill(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not MERGED.is_file():
            raise unittest.SkipTest("schemas/merged.json not generated")
        try:
            import nav_panels
        except Exception:  # noqa: BLE001
            raise unittest.SkipTest("PyQt5 not available")
        cls.nav = nav_panels

    def test_prefill_name_and_field(self):
        from PyQt5.QtWidgets import QApplication, QComboBox, QLineEdit
        # 必须持有引用：临时 QApplication 会被 GC，随后建控件即 abort
        app = QApplication.instance() or QApplication(
            ["test", "-platform", "offscreen"])
        type(self)._app = app
        reg = _registry()
        t = reg.get("CondBoundaryFlowIO")
        if t is None:
            self.skipTest("CondBoundaryFlowIO not in corpus")
        ctx = _ctx_with_xml()
        path = ""
        for m in t.field_meta():
            if m["kind"] in ("int", "float", "string", "bool") \
                    and m["default"]:
                path = m["name"]
                break
        if not path:
            self.skipTest("no sample default field")
        dlg = self.nav.GenericCondBody(
            "CondBoundaryFlowIO", t, ctx,
            initial={"name": "R24Edit", "regions": [],
                     "fields": {path: "4242"}})
        self.assertEqual(dlg.ed_name.text(), "R24Edit")
        self.assertTrue(dlg.windowTitle().startswith("Edit"))
        self.assertEqual(dlg._value(path, {}), "4242")
        res = dlg.result_cond()
        self.assertEqual(res["fields"].get(path), "4242")
        # 未预填的字段仍带样本默认（预填只覆盖给定路径）
        self.assertGreaterEqual(len(res["fields"]), 1)


if __name__ == "__main__":
    unittest.main()
