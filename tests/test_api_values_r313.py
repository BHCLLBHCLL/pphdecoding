#!/usr/bin/env python3
"""R31-3 回归：typed 桥暴露 API 取值词表（可查询 / 三态校验）。

R31-2 把 1738 条取值送进目录后，桥接层要能查、能校验；但**不能**当硬白名单 ——
手册有漏项（R30 实测 `GetVoxelOctRefineType` 手册只列 shape/speed，宿主还认
`octree`）。故 `check_api_value` 是**三态**：True / False / **None（无词表，不拦）**。
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pphxml  # noqa: E402
from automation import scflowpre_api as api  # noqa: E402


class TestVocabularyQueries(unittest.TestCase):
    def test_return_values(self):
        self.assertEqual(
            api.api_values("MeshingGroupSetting", "GetVoxelOctRefineType",
                           "return"),
            [{"value": "shape", "description": "Model shape-weighted"},
             {"value": "speed", "description": "Speed-weighted"}])

    def test_argument_values(self):
        self.assertEqual(
            api.api_value_set("MeshingGroupSetting", "ChangeMesher", "type"),
            {"poly", "oct"})

    def test_default_picks_first_argument_with_values(self):
        self.assertEqual(
            api.api_value_set("ClosedVolume", "SetConnectionType"),
            {"default", "connect", "disconnect"})

    def test_missing_member_or_values_yield_empty(self):
        self.assertEqual(api.api_values("NoSuchClass", "NoSuchMethod"), [])
        self.assertEqual(
            api.api_values("MeshingGroupSetting", "SetCompleteParallelFlag"),
            [])

    def test_catalog_is_cached(self):
        self.assertIs(api.load_catalog(), api.load_catalog())


class TestThreeStateCheck(unittest.TestCase):
    def test_true_false_none(self):
        self.assertIs(api.check_api_value("MeshingGroupSetting", "ChangeMesher",
                                          "poly", "type"), True)
        self.assertIs(api.check_api_value("MeshingGroupSetting", "ChangeMesher",
                                          "voxel", "type"), False)
        self.assertIsNone(api.check_api_value(
            "MeshingGroupSetting", "SetCompleteParallelFlag", "true", "bFlag"))


class TestMeasuredEncodingAgreesWithCatalog(unittest.TestCase):
    """面板用的实测编码表必须与目录口径对得上（只允许「手册缺项」的差集）。"""

    def test_documented_names_match_measured_table(self):
        documented = api.api_value_set("MeshingGroupSetting",
                                       "GetVoxelOctRefineType", "return")
        measured = set(pphxml.VOXEL_OCT_REFINE_TYPES)
        self.assertLessEqual(documented, measured)
        # 差集就是手册漏项：实机 getter 读回的宿主默认值
        self.assertEqual(measured - documented, {"octree"})

    def test_measured_codes_are_distinct_ints(self):
        codes = list(pphxml.VOXEL_OCT_REFINE_TYPES.values())
        self.assertEqual(len(codes), len(set(codes)))
        for c in codes:
            int(c)


if __name__ == "__main__":
    unittest.main()
