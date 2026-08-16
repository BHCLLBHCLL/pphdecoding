#!/usr/bin/env python3
"""P1 条件体系回归：注册表元数据推断 + 通用表单 + XML 写回。

- 纯逻辑部分（field_meta/枚举/必填/写回 XML + registry 校验闭环）不依赖 Qt。
- GenericCondBody 表单交互部分需要 PyQt5（同 test_create_parts 约定，
  缺 PyQt5 时跳过）。
"""

import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from condition_registry import ConditionRegistry  # noqa: E402
from schema_extract import load_schema_json  # noqa: E402
import pphxml  # noqa: E402

MERGED = ROOT / "schemas" / "merged.json"


def _registry() -> ConditionRegistry:
    return ConditionRegistry.from_schemas(
        [(load_schema_json(MERGED), "merged")])


class TestFieldMetaInference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not MERGED.exists():
            raise unittest.SkipTest("schemas/merged.json not generated")
        cls.reg = _registry()

    def test_types_present(self):
        names = self.reg.type_names()
        for expect in ("CondBoundaryFlowIO", "CondBoundaryWallThermal"):
            self.assertIn(expect, names)
        self.assertGreaterEqual(len(names), 8)

    def test_field_meta_shape(self):
        t = self.reg.get("CondBoundaryFlowIO")
        meta = t.field_meta()
        self.assertTrue(meta)
        names = [m["name"] for m in meta]
        self.assertNotIn("type", names)
        self.assertNotIn("name", names)
        self.assertNotIn("regions", names)
        self.assertNotIn("regions.region", names)
        for m in meta:
            self.assertIn(m["kind"], ("int", "float", "bool", "string",
                                      "empty", "composite"))
            self.assertIsInstance(m["enum"], list)
            self.assertIn(m["required"], (True, False, None))

    def test_required_from_occurrence_counts(self):
        # 语料内每个类型的 type/name 都全额出现（children>0 的复合字段
        # 也全额出现）；这里验证计数驱动的 required 推断至少对某类型生效
        found_any_required = False
        for tname in self.reg.type_names():
            t = self.reg.get(tname)
            for m in t.field_meta():
                if m["required"] is True:
                    found_any_required = True
                    # 叶子 required 字段必有默认样本（复合/empty 无样本正常）
                    self.assertTrue(m["default"] or m["kind"] in (
                        "empty", "composite"))
        self.assertTrue(found_any_required)

    def test_enum_inference(self):
        t = self.reg.get("CondBoundaryFlowIO")
        meta = {m["name"]: m for m in t.field_meta()}
        # flow_io_type 样本为 token 形态 → 枚举
        m = meta.get("flow_io_type")
        if m is not None:
            self.assertTrue(m["enum"])
            self.assertIn(m["default"], m["enum"])
        # 数值型字段不做枚举误导：int 字段的枚举只含整数字符串
        for name, m in meta.items():
            if m["kind"] == "int" and m["enum"]:
                for v in m["enum"]:
                    int(v)

    def test_enum_rejects_free_text(self):
        from condition_registry import ConditionField
        f = ConditionField(name="name", kind="string",
                           samples=["my condition 1", "wall left"])
        self.assertEqual(f.enum_values, [])
        f2 = ConditionField(name="mode", kind="string",
                            samples=["laminar", "turbulence"])
        self.assertEqual(f2.enum_values, ["laminar", "turbulence"])


class TestWriteConditionXml(unittest.TestCase):
    """写回闭环：构造表单数据 → write_condition_to_xml → registry 校验。

    write_condition_to_xml 在 nav_panels 内（模块级导入 PyQt5），
    无 PyQt5 时跳过。
    """

    @classmethod
    def setUpClass(cls):
        if not MERGED.exists():
            raise unittest.SkipTest("schemas/merged.json not generated")
        cls.reg = _registry()
        try:
            import nav_panels  # noqa: F401
        except Exception:
            raise unittest.SkipTest("PyQt5 not available")
        cls.nav = __import__("nav_panels")

    def _ctx_with_xml(self) -> dict:
        box = ROOT / "box.pph"
        if not box.exists():
            self.skipTest("box.pph missing")
        from pph_parser import PphArchive
        arch = PphArchive.open(str(box))
        member = arch.by_role("project_xml")[0]
        xml = pphxml.parse_main_xml(arch.read_member(member.name))
        return {"xml": xml}

    def test_write_and_validate_flow_io(self):
        t = self.reg.get("CondBoundaryFlowIO")
        meta = {m["name"]: m for m in t.field_meta()}
        fields = {}
        for name, m in meta.items():
            # required 叶子：有样本默认取默认；kind=empty（语料中为
            # 空元素形态）写空元素；composite 父节点不写文本（其子
            # 路径写入时自动创建）
            if m["required"] and (m["default"] or m["kind"] == "empty"):
                fields[name] = m["default"]
        data = {"type": "CondBoundaryFlowIO", "name": "UnitTestFlow",
                "regions": ["open"], "fields": fields}
        ctx = self._ctx_with_xml()
        xml = ctx["xml"]
        n_before = len(xml.conditions())
        self.assertTrue(self.nav.write_condition_to_xml(ctx, t, data))
        self.assertTrue(ctx.get("xml_dirty"))
        conds = xml.conditions()
        self.assertEqual(len(conds), n_before + 1)
        el = conds[-1]
        self.assertEqual(el.findtext("type"), "CondBoundaryFlowIO")
        self.assertEqual(el.findtext("name"), "UnitTestFlow")
        regs = el.find("regions")
        self.assertIsNotNone(regs)
        self.assertEqual([r.text for r in regs], ["open"])
        # 写回元素通过 registry 校验（无未知字段 / 类型不匹配 / 缺失必填）
        report = self.reg.validate_condition(el)
        self.assertEqual(
            report["issues"],
            [i for i in report["issues"] if "missing required" not in i
             and "unknown field" not in i
             and "type mismatch" not in i])

    def test_write_without_xml_returns_false(self):
        t = self.reg.get("CondBoundaryFlowIO")
        data = {"type": "CondBoundaryFlowIO", "name": "X",
                "regions": [], "fields": {}}
        self.assertFalse(
            self.nav.write_condition_to_xml({"xml": None}, t, data))

    def test_nested_composite_paths(self):
        t = self.reg.get("CondBoundaryWallThermal")
        meta = t.field_meta()
        nested = [m for m in meta if "." in m["name"]]
        data = {"type": t.name, "name": "NestedTest", "regions": [],
                "fields": {m["name"]: m["default"] for m in nested
                           if m["default"]}}
        ctx = self._ctx_with_xml()
        if not data["fields"]:
            self.skipTest("no nested samples in corpus")
        self.assertTrue(self.nav.write_condition_to_xml(ctx, t, data))
        el = ctx["xml"].conditions()[-1]
        for path in data["fields"]:
            node = el
            ok = True
            for seg in path.split("."):
                node = node.find(seg) if node is not None else None
                if node is None:
                    ok = False
                    break
            self.assertTrue(ok, f"path {path} not written")


class TestGenericCondBodyForm(unittest.TestCase):
    """GenericCondBody 表单构建（需要 PyQt5 + offscreen）。"""

    @classmethod
    def setUpClass(cls):
        if not MERGED.exists():
            raise unittest.SkipTest("schemas/merged.json not generated")
        try:
            import nav_panels
        except Exception:
            raise unittest.SkipTest("PyQt5 not available")
        cls.nav = nav_panels

    def _ctx(self) -> dict:
        box = ROOT / "box.pph"
        if not box.exists():
            self.skipTest("box.pph missing")
        from pph_parser import PphArchive
        arch = PphArchive.open(str(box))
        member = arch.by_role("project_xml")[0]
        xml = pphxml.parse_main_xml(arch.read_member(member.name))
        return {"xml": xml, "groups_info": {}}

    def test_form_build_and_result(self):
        from PyQt5.QtWidgets import QApplication, QComboBox, QLineEdit
        app = QApplication.instance() or QApplication(
            ["test", "-platform", "offscreen"])
        reg = _registry()
        t = reg.get("CondBoundaryFlowIO")
        dlg = self.nav.GenericCondBody("CondBoundaryFlowIO", t,
                                       self._ctx())
        # 默认值填充：至少一个字段 widget 带样本默认
        defaults = 0
        for m in dlg._meta:
            w = dlg._widgets.get(m["name"])
            if w is None:
                continue
            if isinstance(w, QLineEdit) and w.text():
                defaults += 1
            elif isinstance(w, QComboBox) and w.currentText():
                defaults += 1
        self.assertGreater(defaults, 0)
        # 校验：名字为空 → 有错误
        errs = dlg._validate()
        self.assertTrue(any("Name" in e for e in errs))
        # 填名字 + 必填默认已在 → 校验通过（int/float 默认来自样本，合法）
        dlg.ed_name.setText("FormTest")
        errs = dlg._validate()
        self.assertFalse(
            [e for e in errs if "required" in e.lower() or "Required" in e])
        # 结果结构
        dlg.lst_regions.item(0).setSelected(True)
        res = dlg.result_cond()
        self.assertEqual(res["type"], "CondBoundaryFlowIO")
        self.assertEqual(res["name"], "FormTest")
        self.assertTrue(res["fields"])
        # 区域列表来自 box.xml 的 regions
        self.assertTrue(dlg.lst_regions.count() >= 1)

    def test_registry_cached(self):
        reg1 = self.nav.condition_registry_cached()
        self.assertTrue(self.nav.condition_registry_cached() is reg1)
        self.assertIsNotNone(reg1)
        self.assertIn("CondBoundaryFlowIO", reg1.type_names())


if __name__ == "__main__":
    unittest.main()
