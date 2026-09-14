#!/usr/bin/env python3
"""R36 证据回归：Cond* 名字裁定补齐（R36-1）/ 仅包含关系归因（R36-2）/ 属性物化（R36-3）。

* 裁定表用**单调合并**：某次运行取不到实例的类保留上次结论，所以表只增不减；
* 实例构建必须走 **typed** 包装 —— 裸 `CDispatch` 的 `getattr` 会被 win32com 当属性读，
  本项前后踩了三次同一个坑，测试用假对象钉住"先 Create 再 Query"的次序；
* 属性物化的名字取目录键括号前那段（`Visible(BOOL)` → `Visible`）。
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import scflowpre_api as api  # noqa: E402

PROBE = ROOT / "tools" / "dispatch_name_probe.py"
VERDICTS = ROOT / "_p12u_gate" / "r36" / "name_verdicts.json"
ATTR = ROOT / "_p12u_gate" / "r36" / "corpus_diff_attr.json"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
TABLE = ROOT / "schemas" / "name_verdicts.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestVerdictsR36(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not VERDICTS.is_file():
            raise unittest.SkipTest("r36 verdict evidence missing")
        cls.data = json.loads(VERDICTS.read_text(encoding="utf-8"))

    def test_coverage_grew(self):
        self.assertGreaterEqual(len(self.data["verdicts"]), 30)
        self.assertEqual(self.data["pairs"], 41)
        self.assertEqual(len(self.data["verdicts"])
                         + len(self.data["pairs_unreachable"]), 41)

    def test_tally_consistent(self):
        tally: dict = {}
        for v in self.data["verdicts"]:
            tally[v["verdict"]] = tally.get(v["verdict"], 0) + 1
        self.assertEqual(tally, self.data["tally"])

    def test_each_verdict_has_a_resolving_name(self):
        for v in self.data["verdicts"]:
            if v["verdict"] == "heading":
                self.assertEqual(v["heading_state"], "resolved")
            elif v["verdict"] == "signature":
                self.assertEqual(v["signature_state"], "resolved")
            elif v["verdict"] == "both":
                self.assertEqual(v["heading_state"], "resolved")
                self.assertEqual(v["signature_state"], "resolved")

    def test_newly_obtained_classes(self):
        via = self.data.get("obtained_via") or {}
        self.assertGreaterEqual(len(via), 5)
        for cls in ("CondBladeShape", "CondBoundaryFlowIO", "OctParam"):
            self.assertIn(cls, via)

    def test_known_new_pairs(self):
        by = {(v["class"], v["heading"]): v for v in self.data["verdicts"]}
        self.assertEqual(by[("CondBladeShape", "EditChordLength")]["verdict"],
                         "heading")
        self.assertEqual(
            by[("CondOutputLFileTurbo",
                "ClearOutletBladeRegions")]["verdict"], "signature")


class TestVerdictTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = json.loads(TABLE.read_text(encoding="utf-8"))

    def test_table_merges_and_only_holds_resolving_names(self):
        """表里只放**宿主接受的名字**：目录键（heading/both）或签名名（signature）。"""
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        resolved = self.table["resolved"]
        self.assertGreaterEqual(len(resolved), 16)
        for cls, members in resolved.items():
            methods = cat["classes"][cls]["methods"]
            for key, name in members.items():
                allowed = {key, methods[key].get("signature_name")}
                self.assertIn(name, allowed, cls + "." + key)
        doc = resolved["Doc"]
        self.assertEqual(doc["CreateDiscontinuousMeshingGroupWitouthMovingPart"],
                         "CreateDiscontinuousMeshingGroupWithoutMovingPart")


class TestInstanceBuilder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.probe = _load("nameprobe_r36", PROBE)

    def test_create_wins_over_query(self):
        calls = []

        class _Host:
            def CreateCondFoo(self, name):
                calls.append("create")
                return "created"

            def QueryCondFooByName(self, name):
                calls.append("query")
                return "queried"

        obj, how = self.probe._obtain("CondFoo", _Host(), None, None)
        self.assertEqual((obj, how), ("created", "CreateCondFoo"))
        self.assertEqual(calls, ["create"])

    def test_query_used_when_create_missing(self):
        class _Host:
            def QueryCondFooByName(self, name):
                return "queried"

        obj, how = self.probe._obtain("CondFoo", _Host(), None, None)
        self.assertEqual((obj, how), ("queried", "QueryCondFooByName"))

    def test_returns_none_when_nothing_works(self):
        class _Host:
            def CreateCondFoo(self, name):
                raise RuntimeError("no")

        self.assertEqual(self.probe._obtain("CondFoo", _Host(), None, None),
                         (None, None))

    def test_non_cond_tries_getters(self):
        class _Doc:
            def GetWidget(self):
                return "widget"

        obj, how = self.probe._obtain("Widget", None, _Doc(), None)
        self.assertEqual((obj, how), ("widget", "GetWidget"))


class TestPropertiesR36(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        api.materialize_catalog_wrappers()
        api.materialize_catalog_properties()
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))

    def test_properties_materialized(self):
        prop = vars(api.ScFlowpreApplication).get("Visible")
        self.assertIsInstance(prop, property)

    def test_property_get_set_route_through_prop(self):
        class _Fake:
            Visible = True

        fake = _Fake()
        obj = api.ScFlowpreApplication(fake)
        self.assertTrue(obj.Visible)
        obj.Visible = False
        self.assertFalse(fake.Visible)

    def test_property_name_strips_type_suffix(self):
        keys = [k for info in self.cat["classes"].values()
                for k in (info.get("properties") or {})]
        self.assertTrue(any("(" in k for k in keys), "目录属性键带类型后缀")
        for k in keys:
            name = k.split("(", 1)[0]
            self.assertTrue(name.isidentifier(), k)


class TestUpwdAttribution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        if ATTR.is_file():
            cls.attr = json.loads(ATTR.read_text(encoding="utf-8"))
        else:
            cls.attr = None

    def test_values_landed_with_provenance(self):
        e = self.cat["classes"]["Conditions"]["methods"][
            "GetUpwdOptionParamForEquation"]
        slot = next(a for a in e["arguments"] if a.get("name") == "eq")
        vals = {v["value"]: v for v in slot["values"]}
        for want in ("eq_comb", "eq_dsol_cont", "eq_dsol_e", "eq_dsol_mom"):
            self.assertIn(want, vals)
            self.assertEqual(vals[want].get("source"), "host-corpus")

    def test_link_converged(self):
        if not self.attr:
            raise unittest.SkipTest("attribution evidence missing")
        hits = [a for a in self.attr["attributed"] if a["parent"] == "upwd_param"]
        for link in hits:
            self.assertEqual(link["only_corpus"], [])


if __name__ == "__main__":
    unittest.main()
