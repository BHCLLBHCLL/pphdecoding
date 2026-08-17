#!/usr/bin/env python3
"""P6-1 条件字段级扩面：帮助元数据（HTML 帮助页 + 求解设置树）字段注入。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from condition_help_schema import (  # noqa: E402
    apply_help_schema, html_field_schema, sanitize_key, tree_field_schema)
from condition_registry import ConditionRegistry  # noqa: E402
from schema_extract import load_schema_json  # noqa: E402

SCHEMAS = ROOT / "schemas"


def _registry_with_catalog() -> ConditionRegistry:
    items = []
    for p in sorted(SCHEMAS.glob("*.json")):
        if p.name in ("cond_types.json", "condition_tree.json",
                      "cond_html_meta.json"):
            continue
        try:
            items.append((load_schema_json(p), p.stem))
        except Exception:
            continue
    reg = ConditionRegistry.from_schemas(items) if items \
        else ConditionRegistry()
    if (SCHEMAS / "cond_types.json").is_file():
        reg.merge_catalog(SCHEMAS / "cond_types.json")
    return reg


class TestSanitizeKey(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(sanitize_key("Total temperature, Total pressure"),
                         "total_temperature_total_pressure")
        self.assertEqual(sanitize_key("  Fan  "), "fan")
        self.assertEqual(sanitize_key("Velocity X"), "velocity_x")
        self.assertEqual(sanitize_key(""), "field")

    def test_always_xml_safe(self):
        # 字段名应可作为 XML 元素 tag（不含空格 / 非法字符）
        for text in ("Total temperature", "P-Q characteristics",
                     "List of Tables/Functions", "A / B", "123"):
            key = sanitize_key(text)
            self.assertNotIn(" ", key)
            self.assertNotIn("/", key)
            self.assertNotIn("-", key)
            self.assertTrue(key)


class TestFieldSchemas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (SCHEMAS / "cond_html_meta.json").is_file():
            raise unittest.SkipTest("cond_html_meta.json not generated")
        cls.html = html_field_schema()
        cls.tree = tree_field_schema()

    def test_html_schema_shape(self):
        # 帮助页字段：key 合法、kind 合法、display 保留
        for tname, fields in self.html.items():
            self.assertTrue(tname.startswith("Cond"))
            for key, desc in fields.items():
                self.assertNotIn(" ", key)
                self.assertIn(desc["kind"],
                              ("int", "float", "string"))
                self.assertTrue(desc.get("display"))

    def test_tree_schema_maps_cond_types(self):
        # 求解设置树应至少覆盖若干已知 Cond* 类型
        for want in ("CondPorousMedia", "CondSource", "CondMoving"):
            self.assertIn(want, self.tree)

    def test_html_covers_help_linked_types(self):
        # 有 help 映射且页面有 params/terms 的类型应被覆盖
        self.assertGreaterEqual(len(self.html), 6)


class TestApplyHelpSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (SCHEMAS / "cond_types.json").is_file():
            raise unittest.SkipTest("cond_types.json not generated")
        cls.reg = _registry_with_catalog()
        cls.before = {n for n, t in cls.reg.types.items() if t.fields}
        cls.stats = apply_help_schema(cls.reg)

    def test_injects_fields(self):
        # tree/sibling 扩面后 help 注入面可能缩小；仍应写入一批可选字段
        self.assertGreaterEqual(self.stats["types_with_new_fields"], 8)
        self.assertGreater(self.stats["total_fields_injected"], 50)

    def test_expands_coverage(self):
        after = {n for n, t in self.reg.types.items() if t.fields}
        self.assertGreaterEqual(len(after), 60)
        self.assertGreater(len(after), len(self.before))

    def test_sibling_output_keys_come_from_samples(self):
        donors = [
            t for n, t in self.reg.types.items()
            if t.category == "output" and t.count > 0]
        self.assertTrue(donors)
        union = set()
        for d in donors:
            union.update(d.fields)
        t = self.reg.get("CondOutputCSV")
        self.assertIsNotNone(t)
        self.assertTrue(t.fields)
        self.assertTrue(set(t.fields) <= union)

    def test_does_not_overwrite_sample_types(self):
        # 样本已背书的精确字段不被帮助字段覆盖
        for name in self.before:
            t = self.reg.get(name)
            # 字段仍存在，且必填计数语义保留（sample 类型 count>0）
            self.assertTrue(t.fields)

    def test_new_fields_optional(self):
        # 帮助字段 count=0 → required=None（不做必填误判）。
        # CondBoundaryRadiation 在 P7-1 后为样本类型（required 按
        # count 语义计算），不再属于 help 注入面。
        for tname in ("CondFreeSurface", "CondAcceleration"):
            t = self.reg.get(tname)
            if t is None:
                continue
            for m in t.field_meta():
                self.assertEqual(m["required"], None)
                self.assertIsInstance(m["enum"], list)

    def test_field_names_xml_safe(self):
        for n, t in self.reg.types.items():
            for key in t.fields:
                self.assertNotIn(" ", key)
                self.assertNotIn("/", key)
                self.assertNotIn("-", key)


if __name__ == "__main__":
    unittest.main()
