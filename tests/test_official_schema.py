#!/usr/bin/env python3
"""官方精选 PPH 并入 merged.json 的 Cond* 精确键。"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schema_extract import extend_merged_schema  # noqa: E402
from pphxml import parse_main_xml, serialize_main_xml  # noqa: E402

MERGED = ROOT / "schemas" / "merged.json"

# 官方案例库实测出现、且本仓 box/laptop 样本原先没有的类型
OFFICIAL_NEW_TYPES = (
    "CondInitial",
    "CondFan",
    "CondPorousMedia",
    "CondDiscontinuous",
    "CondPeriodicBoundary",
    "CondBatteryModel",
)


class TestExtendMergedSchema(unittest.TestCase):
    def test_does_not_overwrite_existing_kind(self):
        base = {
            "projects": ["box"],
            "conditions": {
                "count": 1,
                "types": {
                    "CondFan": {
                        "count": 1,
                        "regions": ["r"],
                        "fields": {
                            "name": {
                                "kind": "string",
                                "indexed": False,
                                "children": 0,
                                "samples": ["old"],
                                "count": 1,
                            },
                        },
                    },
                },
            },
        }
        extra = {
            "projects": ["exA13-1"],
            "conditions": {
                "count": 1,
                "types": {
                    "CondFan": {
                        "count": 1,
                        "regions": ["fan"],
                        "fields": {
                            "name": {
                                "kind": "int",
                                "indexed": False,
                                "children": 0,
                                "samples": ["new"],
                                "count": 1,
                            },
                            "pq_table": {
                                "kind": "composite",
                                "indexed": False,
                                "children": 1,
                                "samples": [],
                                "count": 1,
                            },
                        },
                    },
                },
            },
        }
        out = extend_merged_schema(base, extra)
        fan = out["conditions"]["types"]["CondFan"]
        self.assertEqual(fan["fields"]["name"]["kind"], "string")
        self.assertIn("old", fan["fields"]["name"]["samples"])
        self.assertIn("pq_table", fan["fields"])
        self.assertIn("exA13-1", out["projects"])


class TestDigitXmlTags(unittest.TestCase):
    def test_leading_digit_tag_roundtrip(self):
        raw = (
            b'<?xml version="1.0"?><scFLOWpre>'
            b"<1D_spatial_div_neg_electrode_domain>10"
            b"</1D_spatial_div_neg_electrode_domain>"
            b"</scFLOWpre>"
        )
        mx = parse_main_xml(raw)
        text = serialize_main_xml(mx.root)
        self.assertIn("1D_spatial_div_neg_electrode_domain", text)
        self.assertNotIn("_D1D", text)


class TestMergedOfficialTypes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not MERGED.is_file():
            raise unittest.SkipTest("schemas/merged.json missing")
        cls.data = json.loads(MERGED.read_text(encoding="utf-8"))
        cls.types = (cls.data.get("conditions") or {}).get("types") or {}
        cls.with_fields = {k for k, v in cls.types.items() if v.get("fields")}

    def test_raw_types_with_fields_cover_official(self):
        self.assertGreaterEqual(len(self.with_fields), 40)
        for t in OFFICIAL_NEW_TYPES:
            self.assertIn(t, self.with_fields, t)
            self.assertGreaterEqual(len(self.types[t]["fields"]), 5, t)


if __name__ == "__main__":
    unittest.main()
