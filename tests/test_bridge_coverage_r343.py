#!/usr/bin/env python3
"""R34-3 回归：目录 ↔ typed 桥落差账 + 手册标题/签名名对账。

两件事：

1. **落差账**：17 个 typed 类覆盖目录 1760 个成员里的 372 个（21.1%）——
   `Conditions` 只有 1.2%（607 个成员里包装 7 个）。数字本身不是缺陷，但要**有账**；
2. **两条不变量**：
   * 包装方法必须能在目录里找到（自研便捷方法按命名规则排除）——否则就是调了
     手册外成员，需要像 `SetIntersectionDetectionDepth` 那样显式登记；
   * 手册 **h3 标题名 ≠ 签名名** 的条目必须把真名记进 `signature_name`
     （实测 41 处，如标题 `…WitouthMovingPart` vs 签名 `…WithoutMovingPart`）——
     包装类按签名写，不记就会在"目录里找不到"。
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

COV = ROOT / "tools" / "api_bridge_coverage.py"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
EVIDENCE = ROOT / "_p12u_gate" / "r34" / "bridge_coverage.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestCoverageAccount(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cov = _load("bridgecov_r343", COV)
        cls.data = cls.cov.report()

    def test_every_typed_class_has_a_row(self):
        self.assertEqual(self.data["classes"], len(
            __import__("automation.scflowpre_api", fromlist=["x"])
            .TYPED_CLASSES))

    def test_coverage_is_monotone(self):
        self.assertGreaterEqual(self.data["wrapped"], 370)
        self.assertGreaterEqual(self.data["coverage"], 0.2)
        self.assertLessEqual(self.data["catalog_members_in_typed_classes"],
                             self.data["catalog_members_total"])

    def test_wrapped_members_are_all_documented_or_declared(self):
        """包装方法必须可追溯到目录名（含签名名）；自研便捷方法已被排除。"""
        self.assertEqual(self.data["unknown_wrapped_members"], [])

    def test_conditions_is_the_biggest_gap(self):
        top = max(self.data["rows"], key=lambda r: r["catalog_members"])
        self.assertEqual(top["class"], "Conditions")
        self.assertGreater(top["catalog_members"], 500)


class TestHeadingSignatureMismatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.cov = _load("bridgecov_r343b", COV)

    def test_mismatches_are_recorded_in_catalog(self):
        mism = self.cov.heading_signature_mismatches(self.cat)
        self.assertGreaterEqual(len(mism), 40)
        for row in mism:
            entry = (self.cat["classes"][row["class"]]
                     [row["kind"]][row["heading"]])
            self.assertEqual(entry.get("signature_name"), row["signature"],
                             row["class"] + "." + row["heading"])
            self.assertNotEqual(row["heading"], row["signature"])

    def test_known_typo_case(self):
        entry = self.cat["classes"]["Doc"]["methods"][
            "CreateDiscontinuousMeshingGroupWitouthMovingPart"]
        self.assertEqual(entry.get("signature_name"),
                         "CreateDiscontinuousMeshingGroupWithoutMovingPart")

    def test_consistent_entries_have_no_signature_name(self):
        entry = self.cat["classes"]["MeshingGroupSetting"]["methods"][
            "ChangeMesher"]
        self.assertNotIn("signature_name", entry)


class TestEvidenceFile(unittest.TestCase):
    def test_coverage_never_shrinks(self):
        """R34 的证据是**当时的账**：R35-3 物化后覆盖只增不减（单调口径）。

        （原断言是"证据 == 实时"，R35-3 把包装从 372 提到 1759 后它必然失败 ——
        快照类断言一律改单调不变量，这是本仓的既定口径。）
        """
        if not EVIDENCE.is_file():
            raise unittest.SkipTest("coverage evidence missing")
        saved = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        live = _load("bridgecov_r343c", COV).report()
        self.assertGreaterEqual(live["wrapped"], saved["wrapped"])
        self.assertEqual(live["unknown_wrapped_members"], [])


if __name__ == "__main__":
    unittest.main()
