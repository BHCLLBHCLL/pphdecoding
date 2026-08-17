#!/usr/bin/env python3
"""P7-1 条件 schema 扩源：样本嵌套条件深扫。

`pphxml.MainXml.all_conditions` 覆盖三类形态（直接子级 ``condition``
之外的嵌套条件）：嵌套 ``condition`` 元素、条件形容器（带
``<type>CondXxx</type>`` 子元素）、空 type 的目录可推断条件。
数据源 = 全部仓内 PPH 样本（权威 XML 键）。
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from condition_help_schema import apply_help_schema  # noqa: E402
from condition_registry import ConditionRegistry  # noqa: E402
from pphxml import parse_main_xml  # noqa: E402
from schema_extract import load_schema_json  # noqa: E402

SCHEMAS = ROOT / "schemas"

# 深扫净新的 8 类型（P7-1 实测于全部仓内样本）
NEW_SAMPLE_TYPES = (
    "CondParticleBoundaryDEM",
    "CondParticleSymmBoundaryDEM",
    "CondParticleSymmHeatBoundaryDEM",
    "CondOutputLFileElectricCurrent",
    "CondOutputLFilePassage",
    "CondOutputLFileYplus",
    "CondStedInfo",
    "CondMultiphaseMaterial",
)

CATALOG = {"CondStedInfo", "CondMultiphaseMaterial",
           "CondParticleSymmBoundaryDEM"}

_SYNTHETIC = b"""<?xml version="1.0" encoding="utf-8"?>
<scFLOWpre>
  <conditions>
    <condition>
      <type>CondBoundaryFlowIO</type><name>direct</name><velocity_x>0</velocity_x>
    </condition>
    <output_param>
      <lfile_yplus>
        <condition>
          <type>CondOutputLFileYplus</type><name>yplus</name>
          <output_timing><output_cycle_value>1</output_cycle_value></output_timing>
        </condition>
      </lfile_yplus>
    </output_param>
    <particle_dem>
      <symmetrical_particle_boundary>
        <type>CondParticleSymmBoundaryDEM</type><name>@Sym</name><regions/>
      </symmetrical_particle_boundary>
    </particle_dem>
    <info_sted>
      <sted_info>
        <condition><name>@Sted</name><eps>1e-05</eps><interval>1</interval></condition>
      </sted_info>
    </info_sted>
    <noise>
      <velocity_x><type>VELX</type><value>0</value></velocity_x>
      <fake_container><type>CondFakeNotInCatalog</type><name>fake</name></fake_container>
    </noise>
    <unknown_container>
      <condition><name>no-type-no-catalog-parent</name></condition>
    </unknown_container>
  </conditions>
</scFLOWpre>
"""


def _registry_pipeline() -> ConditionRegistry:
    """nav_panels.condition_registry_cached 同款管线（无 Qt 依赖）。"""
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
    apply_help_schema(reg)
    return reg


class TestAllConditionsDeepScan(unittest.TestCase):
    """合成 main.xml：三类形态全命中 + 假阳性全排除。"""

    @classmethod
    def setUpClass(cls):
        cls.mx = parse_main_xml(_SYNTHETIC)
        cls.found = {t for _, t in cls.mx.all_conditions(CATALOG)}

    def test_direct_condition_kept(self):
        self.assertIn("CondBoundaryFlowIO", self.found)

    def test_nested_condition_found(self):
        self.assertIn("CondOutputLFileYplus", self.found)

    def test_condition_shaped_container_found(self):
        self.assertIn("CondParticleSymmBoundaryDEM", self.found)

    def test_empty_type_inferred_from_parent(self):
        self.assertIn("CondStedInfo", self.found)

    def test_value_slot_not_condition(self):
        # <velocity_x><type>VELX</type> 是值槽，不是条件
        self.assertNotIn("VELX", self.found)

    def test_non_catalog_cond_container_rejected(self):
        self.assertNotIn("CondFakeNotInCatalog", self.found)

    def test_unknown_parent_not_inferred(self):
        # 空 type 且父容器推断名不在目录 → 不收录（宁缺毋滥）
        self.assertNotIn("<unknown>", self.found)
        names = [t for _, t in self.mx.all_conditions(CATALOG)]
        self.assertEqual(names.count("CondStedInfo"), 1)


class TestMergedSchemaDeepScan(unittest.TestCase):
    """重建后的 schemas/merged.json 含深扫净新类型（权威 XML 键源）。"""

    @classmethod
    def setUpClass(cls):
        data = json.loads((SCHEMAS / "merged.json").read_text(encoding="utf-8"))
        cls.types = data["conditions"]["types"]

    def test_new_sample_types_present(self):
        for t in NEW_SAMPLE_TYPES:
            self.assertIn(t, self.types, f"merged.json 缺深扫类型 {t}")
            self.assertGreater(len(self.types[t]["fields"]), 0)

    def test_particle_boundary_dem_rich_fields(self):
        # particle_dem/boundary/condition 全参数面（cohesion/rolling 等）
        fields = self.types["CondParticleBoundaryDEM"]["fields"]
        for probe in ("cohesion_constant", "rolling_stiffness_beta1",
                      "surface_energy", "plasticity_ratio"):
            self.assertIn(probe, fields)

    def test_radiation_upgraded_to_sample_keys(self):
        # P6-1 时仅 html 显示名键（4 字段）；深扫后为样本权威键
        fields = self.types["CondBoundaryRadiation"]["fields"]
        self.assertGreaterEqual(len(fields), 30)


class TestRegistryCoverage(unittest.TestCase):
    """GUI 同款管线：带字段类型 25 → ≥33（P7-1 补全 10）。"""

    @classmethod
    def setUpClass(cls):
        cls.reg = _registry_pipeline()
        cls.with_fields = {t for t in cls.reg.types
                           if cls.reg.types[t].fields}

    def test_coverage_at_least_33(self):
        self.assertGreaterEqual(len(self.with_fields), 33)

    def test_new_types_editable(self):
        for t in NEW_SAMPLE_TYPES:
            self.assertIn(t, self.with_fields, f"{t} 应带字段 schema")
            ct = self.reg.types[t]
            self.assertGreater(len(ct.fields), 0)

    def test_bare_default_types_have_name_regions(self):
        # Symm*DEM 是裸默认条件（仅 type/name/regions，无参数面）
        symm = self.reg.types["CondParticleSymmBoundaryDEM"].fields
        self.assertIn("name", symm)
        self.assertIn("regions", symm)

    def test_sample_fields_not_overwritten_by_help(self):
        # 样本权威键优先：CondBoundaryRadiation 字段应含样本键而非 html 键
        radiation = self.reg.types["CondBoundaryRadiation"].fields
        self.assertTrue(
            any("emissivity" in k for k in radiation),
            "CondBoundaryRadiation 应含样本权威键（emissivity_*）")


if __name__ == "__main__":
    unittest.main()
