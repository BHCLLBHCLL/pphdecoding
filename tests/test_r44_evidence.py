#!/usr/bin/env python3
"""R44 证据回归：普查扩面到 `Cond*`（R44-1）/ 空对象前置提示（R44-2）。

* **扩面**：目录里有 **89 个 `CreateCond*`** 创建器（条件收割工具验证过的路子），
  一个会话里批量建实例 → 普查覆盖从 **17 类 → 84 类**（成员 1873 → 2793），
  又抓出 4 处"手册有、宿主无"（`CondInitial`/`CondPorousMedia`/`CondSource`），
  累计 **16 处**；
* **提示**：`empty_objects` 的 8 个类在证据里带 `empty_hints`（"先跑哪个流程"），
  口径从"未普查"细化为"**试过、但没有前置对象**"。
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

AVAIL = ROOT / "schemas" / "host_member_availability.json"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
GATE = ROOT / "tools" / "api_contract_check.py"
PROBE = ROOT / "tools" / "dispatch_name_probe.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestCoverageExpansion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not AVAIL.is_file():
            raise unittest.SkipTest("availability evidence missing")
        cls.data = json.loads(AVAIL.read_text(encoding="utf-8"))
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))

    def test_classes_swept_reaches_target(self):
        cov = self.data["coverage"]
        self.assertGreaterEqual(cov["classes_swept"], 60,
                                "R44-1 验收：覆盖类数 ≥60")
        self.assertGreaterEqual(cov["members_swept"], 2500)

    def test_buckets_still_partition(self):
        cov = self.data["coverage"]
        # R45 起多一桶：手册页零成员的类（取到了对象但没成员可查）
        self.assertEqual(cov["classes_swept"] + len(cov["empty_objects"])
                         + len(cov.get("no_member_classes") or [])
                         + len(cov["unswept_classes"]), cov["classes_total"])

    def test_new_absent_members_found(self):
        unknown = {c: v.get("unknown") or []
                   for c, v in self.data["classes"].items()}
        # 注意：要数**条目**（同名成员可能在多个类都未实现，如 GetPbmFuncType、
        # ImportCSV）—— 去重后的名字会少 3 个
        entries = [m for ms in unknown.values() for m in ms]
        flat = set(entries)
        self.assertGreaterEqual(len(entries), 16, "扩面后累计 ≥16 处未实现")
        for mem in ("IsEnableConditionForCalculation", "GetPbmFuncType",
                    "GetProjectonType\u200b" if False else "GetProjectonType"):
            self.assertIn(mem, flat)

    def test_no_probe_errors_after_expansion(self):
        errs = [m for v in self.data["classes"].values()
                for m in (v.get("errors") or [])]
        self.assertEqual(errs, [], "扩面不得引入探针侧错误")


class TestEmptyObjectHints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(AVAIL.read_text(encoding="utf-8"))

    def test_every_empty_object_has_a_hint(self):
        cov = self.data["coverage"]
        hints = cov.get("empty_hints") or {}
        self.assertEqual(set(hints), set(cov["empty_objects"]))
        for cls, hint in hints.items():
            self.assertTrue(hint, cls)
            self.assertNotIn("未登记", hint, cls + " 的前置条件未登记")

    def test_hints_are_actionable(self):
        # R45：证据里只列**当轮真的空**的类（ClosedVolume/Octree 已能取到），
        # 但"这个类要先跑什么"是知识 —— 查探针模块里的**知识表**
        probe = _load("probe_r44_hints", PROBE)
        table = probe.EMPTY_HINTS
        self.assertIn("MDL", table["ClosedVolume"])
        self.assertIn("材料", table["PropItem"])
        self.assertIn("八叉树", table["Octree"])
        for cls, hint in self.data["coverage"]["empty_hints"].items():
            self.assertEqual(hint, table[cls], cls)


class TestGateAfterR44(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gate = _load("gate_r44", GATE)

    def test_gate_passes_with_expanded_sweep(self):
        res = self.gate.check_host_absent()
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["probe_errors"], 0)
        self.assertEqual(res["reference_count"], 0)
        self.assertGreaterEqual(res["absent_members"], 10)


if __name__ == "__main__":
    unittest.main()
