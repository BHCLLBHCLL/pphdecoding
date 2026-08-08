#!/usr/bin/env python3
"""Schema 抽取功能测试（box.pph）。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pph_parser import PphArchive  # noqa: E402
from schema_extract import (extract_archive_schema, extract_text_schema,  # noqa: E402
                            merge_schemas)

BOX_PPH = ROOT / "box.pph"


class TestExtractTextSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arch = PphArchive.open(str(BOX_PPH))
        cls.schema = extract_archive_schema(cls.arch)

    def test_project_meta(self):
        self.assertEqual(self.schema["project"]["name"], "box")
        self.assertIn("version", self.schema["project"])

    def test_conditions_present(self):
        cond = self.schema["conditions"]
        self.assertGreater(cond["count"], 0)
        self.assertIn("CondBoundaryFlowIO", cond["types"])

    def test_condition_fields(self):
        entry = self.schema["conditions"]["types"]["CondBoundaryFlowIO"]
        fields = entry["fields"]
        self.assertIn("flow_io_type", fields)
        self.assertEqual(fields["flow_io_type"]["kind"], "string")
        self.assertIn("pressure_value.const_value", fields)
        self.assertIn("regions", entry)

    def test_xenv_unit_section(self):
        unit = self.schema["xenv"]["sections"]["UNIT"]
        self.assertIn("MODEL_LENGTH_UNIT", unit)
        self.assertEqual(unit["MODEL_LENGTH_UNIT"]["values"]["m"], 1)

    def test_prp_groups(self):
        groups = self.schema["prp"]["groups"]
        self.assertGreaterEqual(len(groups), 10)
        self.assertIn("gas(incompressible)", groups)


class TestMergeSchemas(unittest.TestCase):
    def test_merge_two(self):
        arch = PphArchive.open(str(BOX_PPH))
        s1 = extract_archive_schema(arch)
        s2 = extract_archive_schema(arch)
        merged = merge_schemas([s1, s2])
        self.assertEqual(merged["projects"], ["box", "box"])
        t = merged["conditions"]["types"]["CondBoundaryFlowIO"]
        self.assertGreaterEqual(t["count"], 2)
        self.assertEqual(
            merged["xenv"]["sections"]["UNIT"]["MODEL_LENGTH_UNIT"]
            ["values"]["m"], 2)

    def test_extract_text_schema_roundtrip(self):
        data = {m.role: self._read(m) for m in
                PphArchive.open(str(BOX_PPH)).members}
        schema = extract_text_schema(
            data["project_xml"], data["environment"], data["property_db"])
        self.assertIn("conditions", schema)

    def _read(self, member):
        arch = PphArchive.open(str(BOX_PPH))
        return arch.read_member(member.name)


if __name__ == "__main__":
    unittest.main()
