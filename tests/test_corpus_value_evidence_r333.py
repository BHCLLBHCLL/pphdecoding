#!/usr/bin/env python3
"""R33 回归：手册笔误修正 + 语料补充 + 手册↔宿主词表对拍。

三路证据合起来回答「手册词表可不可信」：

1. **宿主自己写出的 XML**（151 个官方工程）——`<xxx_type><name>VALUE</name>`：
   `stability_type` 手册=语料（protectd1/protectd2），`stabilitygeom_type` 手册**漏**
   `elem_volume`（语料 5 条 vs 手册 4 条）→ 已按语料补充入库；
2. **手册笔误**：`"'protectd1"` / `"'orthogonality"`（引号内多一个单引号）与宿主
   `<name>protectd1</name>`（755 处）/ `<name>orthogonality</name>`（151 处）不符 →
   修正并保留 `manual_value` 以便回溯；
3. **实机 setter/getter 对拍**（单会话 8 档、120/120 err=0）：3 个字符串枚举方法的
   手册取值全被宿主接受，2 个臆造取值全被拒。
"""

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EX = ROOT / "tools" / "extract_vb_api_scflow.py"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
CORPUS_DIFF = ROOT / "_p12u_gate" / "r33" / "corpus_diff.json"
ENUM_PROBE = ROOT / "_p12u_gate" / "r33" / "enum_probe.json"
IDENT = re.compile(r"^[A-Za-z0-9_.:/\-]+$")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestValueEvidencePass(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ex = _load("ex_r333", EX)

    def test_typo_fixed_with_manual_value_kept(self):
        cat = {"classes": {"C": {"methods": {"M": {"arguments": [
            {"name": "param", "values": [{"value": "'protectd1",
                                          "description": "x"}]}]}}}}}
        stats = self.ex._apply_value_evidence(cat)
        val = cat["classes"]["C"]["methods"]["M"]["arguments"][0]["values"][0]
        self.assertEqual(stats["fixed"], 1)
        self.assertEqual(val["value"], "protectd1")
        self.assertEqual(val["manual_value"], "'protectd1")
        self.assertIn("main.xml", val["fix_evidence"])

    def test_addendum_mechanism_writes_with_source(self):
        orig = self.ex._VALUE_ADDENDA
        try:
            self.ex._VALUE_ADDENDA = {
                ("C", "M", "param"): [{"value": "new_val",
                                       "description": "d",
                                       "source": "host-corpus"}]}
            cat = {"classes": {"C": {"methods": {"M": {"arguments": [
                {"name": "param", "values": []}]}}}}}
            stats = self.ex._apply_value_evidence(cat)
        finally:
            self.ex._VALUE_ADDENDA = orig
        vals = cat["classes"]["C"]["methods"]["M"]["arguments"][0]["values"]
        self.assertEqual(stats["added"], 1)
        self.assertEqual(vals[0]["source"], "host-corpus")

    def test_addendum_is_idempotent(self):
        cat = {"classes": {"C": {"methods": {"M": {"arguments": [
            {"name": "param", "values": [{"value": "new_val"}]}]}}}}}
        orig = self.ex._VALUE_ADDENDA
        try:
            self.ex._VALUE_ADDENDA = {
                ("C", "M", "param"): [{"value": "new_val"}]}
            stats = self.ex._apply_value_evidence(cat)
        finally:
            self.ex._VALUE_ADDENDA = orig
        self.assertEqual(stats["added"], 0)


class TestCatalogAfterR333(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))

    def _slot(self, cls, member, arg):
        e = self.cat["classes"][cls]["methods"][member]
        for a in e.get("arguments") or []:
            if a.get("name") == arg:
                return a
        raise AssertionError(arg)

    def test_stability_params_corrected(self):
        vals = self._slot("Conditions", "GetPresetStabilityParam",
                          "param")["values"]
        self.assertEqual([v["value"] for v in vals],
                         ["protectd1", "protectd2"])
        self.assertEqual(vals[0]["manual_value"], "'protectd1")

    def test_orthogonality_corrected(self):
        vals = self._slot("Conditions", "GetPresetStabilityParamGeom",
                          "param")["values"]
        names = [v["value"] for v in vals]
        self.assertIn("orthogonality", names)
        fixed = [v for v in vals if v["value"] == "orthogonality"][0]
        self.assertEqual(fixed["manual_value"], "'orthogonality")

    def test_corpus_supplement_landed(self):
        vals = self._slot("Conditions", "GetPresetStabilityParamGeom",
                          "param")["values"]
        hit = [v for v in vals if v["value"] == "elem_volume"]
        self.assertTrue(hit, "语料补充的 elem_volume 必须在册")
        self.assertEqual(hit[0]["source"], "host-corpus")

    def test_every_value_is_identifier_like(self):
        bad = [(c, m, v["value"])
               for c, info in self.cat["classes"].items()
               for kind in ("methods", "properties")
               for m, e in (info.get(kind) or {}).items()
               for a in (e.get("arguments") or []) + [e.get("return") or {}]
               if isinstance(a, dict)
               for v in (a.get("values") or []) if not IDENT.match(v["value"])]
        self.assertEqual(bad, [], "取值必须是标识符样（手册笔误应已修正）")


class TestCorpusEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CORPUS_DIFF.is_file():
            raise unittest.SkipTest("corpus diff evidence missing")
        cls.data = json.loads(CORPUS_DIFF.read_text(encoding="utf-8"))

    def test_all_links_agree_with_catalog(self):
        self.assertGreaterEqual(len(self.data["links"]), 2)
        for link in self.data["links"]:
            self.assertEqual(link["only_corpus"], [],
                             link["parent"] + " 手册漏项未入库")
            self.assertTrue(link["agree"], link["parent"])

    def test_corpus_is_the_official_example_library(self):
        self.assertGreaterEqual(self.data["files"], 100)


class TestGapTerminalState(unittest.TestCase):
    """R33-4：写入口缺口必须有**终态**，不能停在「待办」。"""

    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads(
            (ROOT / "schemas" / "host_keys.json").read_text(encoding="utf-8"))

    def test_every_gap_has_terminal_status(self):
        gaps = set(self.ledger.get("known_gaps") or [])
        status = self.ledger.get("known_gap_status") or {}
        self.assertEqual(set(status), gaps, "缺口与终态表必须一一对应")
        for gid, info in status.items():
            self.assertTrue(info.get("terminal"), gid + " 没有终态")
            self.assertIn(info.get("status"),
                          {"no-panel-surface", "controls-added"}, gid)
            self.assertTrue(info.get("reason"))
            self.assertTrue(info.get("round"))
        self.assertEqual(gaps, {"FACET.INTERSECTION_DETECTION_DEPTH"})


class TestHostEnumProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ENUM_PROBE.is_file():
            raise unittest.SkipTest("enum probe evidence missing")
        cls.data = json.loads(ENUM_PROBE.read_text(encoding="utf-8"))

    def test_documented_values_accepted_bogus_rejected(self):
        bogus = {"polyhedral", "facet"}
        seen_ok = 0
        for row in self.data["per_case"]:
            ret = (row.get("set_ret") or {}).get("value")
            got = (row.get("get_val") or {}).get("value")
            if row["value"] in bogus:
                self.assertEqual(ret, "False",
                                 row["setter"] + " 对臆造取值应返回 False")
                continue
            self.assertEqual(ret, "True", row["setter"] + "=" + row["value"])
            self.assertEqual(got, row["value"], "getter 必须回读同值")
            seen_ok += 1
        self.assertGreaterEqual(seen_ok, 6)

    def test_single_session_clean(self):
        host = self.data["host"]
        self.assertIsNone(host.get("error"))
        self.assertEqual(host["err0"], host["total"])
        self.assertGreaterEqual(host["total"], 100)


if __name__ == "__main__":
    unittest.main()
