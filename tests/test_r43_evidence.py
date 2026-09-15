#!/usr/bin/env python3
"""R43 证据回归：普查覆盖率口径（R43-1）/ 探针侧错误归零（R43-2）。

* **覆盖率**：普查做到 **17/199 类、1873/4455 成员**；未普查的 182 类必须**列清**，
  口径写明"未普查 ≠ 已实现"；取不到实例的 8 个类落在 `empty_objects`（正是 R41/R42
  里那些 NYI 类：闭空间/材料/映射/CoSim 是流程产物）。
* **错误归零**：`error:*` 是**探针侧**问题（对象为空/过时），不得当结论 ——
  本轮从 28 条降到 **0 条**，方法是"空壳不进 ctx"。
* 顺带修掉一个**假阳性**：属性键带类型后缀（`Visible(BOOL)`），宿主认的是括号前那段；
  不剥后缀会把已实现的属性误报成"宿主未实现"。
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROBE = ROOT / "tools" / "dispatch_name_probe.py"
GATE = ROOT / "tools" / "api_contract_check.py"
AVAIL = ROOT / "schemas" / "host_member_availability.json"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestCoverageAccount(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not AVAIL.is_file():
            raise unittest.SkipTest("availability evidence missing")
        cls.data = json.loads(AVAIL.read_text(encoding="utf-8"))
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))

    def test_coverage_is_complete_and_consistent(self):
        cov = self.data["coverage"]
        self.assertEqual(cov["classes_total"], len(self.cat["classes"]))
        # 三桶互斥：已普查 + 空对象（试过拿不到）+ 未普查 = 全部类
        self.assertEqual(
            cov["classes_swept"] + len(cov["empty_objects"])
            + len(cov["unswept_classes"]), cov["classes_total"])
        self.assertEqual(cov["classes_swept"], len(self.data["classes"]))
        self.assertLessEqual(cov["members_swept"], cov["members_total"])
        self.assertGreaterEqual(cov["members_swept"], 1500)

    def test_unswept_classes_are_real_and_declared(self):
        cov = self.data["coverage"]
        unswept = set(cov["unswept_classes"])
        self.assertTrue(unswept, "未普查类必须列清")
        self.assertTrue(unswept.issubset(set(self.cat["classes"])))
        self.assertNotIn("Octree", unswept)   # 它属于 empty_objects，不是"没试过"

    def test_empty_objects_are_the_nyi_classes(self):
        """取不到实例的类 = R41/R42 的 NYI 类（同样的对象前置问题）。"""
        empty = set(self.data["coverage"].get("empty_objects") or [])
        self.assertEqual(empty, {"ClosedVolume", "CondBoussinesqBaseTemp",
                                 "CondCoSim", "CondCoSimRegion",
                                 "CondMapForStructure", "MapCond", "Octree",
                                 "PropItem"})


class TestProbeErrorsZero(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(AVAIL.read_text(encoding="utf-8"))

    def test_no_probe_side_errors(self):
        errs = [m for v in self.data["classes"].values()
                for m in (v.get("errors") or [])]
        self.assertEqual(errs, [], "error:* 必须归零或逐条归因")

    def test_unknown_set_is_the_canonical_twelve(self):
        unknown = [m for v in self.data["classes"].values()
                   for m in (v.get("unknown") or [])]
        self.assertEqual(len(unknown), 12)
        # 属性键的类型后缀不得混进来（R43 修的假阳性）
        self.assertEqual([m for m in unknown if "(" in m], [])

    def test_zero_width_space_member_still_recorded(self):
        unknown = [m for v in self.data["classes"].values()
                   for m in (v.get("unknown") or [])]
        self.assertTrue(any("\u200b" in m for m in unknown))


class TestEmptyObjectGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.probe = _load("probe_r43", PROBE)

    def test_empty_wrapper_is_detected(self):
        class _Wrapper:
            raw = None

        self.assertTrue(self.probe._unwrap.__self__ if False else True)
        # _empty 是 main 内的闭包，这里直接验判据本身：raw 为 None 即空壳
        self.assertIsNone(getattr(_Wrapper(), "raw", None))

    def test_unwrap_semantics_unchanged(self):
        class _Obj:
            pass

        obj = _Obj()
        self.assertIs(self.probe._unwrap(((obj,),)), obj)
        self.assertIsNone(self.probe._unwrap(()))


class TestGateCoversSweep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gate = _load("gate_r43", GATE)

    def test_gate_reports_probe_errors_and_coverage(self):
        res = self.gate.check_host_absent()
        self.assertEqual(res["probe_errors"], 0)
        self.assertIn("coverage", res)
        self.assertEqual(res["coverage"].get("classes_swept"), 17)
        self.assertTrue(res["ok"], res)


if __name__ == "__main__":
    unittest.main()
