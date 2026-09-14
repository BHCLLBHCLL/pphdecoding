#!/usr/bin/env python3
"""R34-1 回归：语料对拍扩面 —— **名字同源**门 + 自动发现链接 + 入库溯源。

R33-3 只覆盖 2 个容器。R34-1 把语料里的取值容器全扫出来（333 种）并按
「取值集交叉」自动找链接；但**交叉只能找候选** —— 实测 `loop_eq_param` 与
`equa_start_param` 都会"匹配"到 `Conditions.GetUpwdParam`。故入库门槛
多加一条：容器名与成员名必须同源（`connection_type` ↔ `GetConnectionType`）。
仅取值重叠的链接只作提示，绝不入库。
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DIFF = ROOT / "tools" / "api_value_corpus_diff.py"
EVIDENCE = ROOT / "_p12u_gate" / "r34" / "corpus_diff_auto.json"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestNameGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = _load("corpus_r341", DIFF)

    def test_same_root_names_match(self):
        for parent, member in (("connection_type", "GetConnectionType"),
                               ("boundary_type", "GetBoundaryType"),
                               ("stability_type", "GetStabilityType"),
                               ("contact_type", "SetContactType")):
            self.assertTrue(self.d._name_matches(parent, member),
                            parent + " ↔ " + member)

    def test_value_overlap_alone_is_not_enough(self):
        for parent, member in (("loop_eq_param", "GetUpwdParam"),
                               ("equa_start_param", "GetUpwdParam"),
                               ("fourier_transform_freq_type", "GetVOFType")):
            self.assertFalse(self.d._name_matches(parent, member),
                             parent + " ↔ " + member + " 不得算同源")

    def test_discovery_splits_actionable_and_overlap_only(self):
        """同源 → 可入库；仅取值重叠（换个名字）→ 只提示。"""
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        real = [v["value"] for v in
                cat["classes"]["Conditions"]["methods"]["GetUpwdParam"]
                ["arguments"][0]["values"]][:3]
        self.assertGreaterEqual(len(real), 2)
        # 用一个**确定不在册**的取值验证 only_corpus 口径（not_connect 已在 R34-1
        # 经同源链接入库 → 拿它当反例会随目录演进而失效）
        assert "brand_new_value" not in {v["value"] for v in
                                         cat["classes"]["ClosedVolume"]
                                         ["methods"]["GetConnectionType"]
                                         ["return"]["values"]}
        scan = {"files": 1, "errors": 0, "per_container": {
            "connection_type": {"default": 5, "connect": 4,
                                "brand_new_value": 3},
            "eq_param_bucket": {v: 4 for v in real}}}
        actionable, overlap_only = self.d.discover_links(scan)
        self.assertEqual([a["parent"] for a in actionable],
                         ["connection_type"])
        self.assertEqual([o["parent"] for o in overlap_only],
                         ["eq_param_bucket"])
        self.assertIn("brand_new_value", actionable[0]["only_corpus"])
        self.assertFalse(overlap_only[0]["name_matched"])


class TestAutoEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EVIDENCE.is_file():
            raise unittest.SkipTest("auto corpus evidence missing")
        cls.data = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_corpus_is_official_library(self):
        self.assertGreaterEqual(self.data["files"], 100)
        self.assertEqual(self.data["errors"], 0)

    def test_no_actionable_link_has_a_manual_gap_left(self):
        self.assertGreaterEqual(len(self.data["discovered"]), 30)
        gaps = {d["parent"]: d["only_corpus"] for d in self.data["discovered"]
                if d["only_corpus"]}
        self.assertEqual(gaps, {}, "名字同源链接不得再有手册漏项")
        for link in self.data["discovered"]:
            self.assertTrue(link["name_matched"], link["parent"])

    def test_overlap_only_links_are_reported_not_merged(self):
        """仅重叠链接的 only_corpus 值**不得**被并进它"匹配"到的那个成员。

        （值本身可能因为别处合法来源而在目录里 —— 例如 `CAVI` 经
        `GetNextParam` 的同源链接入库 —— 所以断言要精确到"那个槽"。）
        """
        self.assertGreaterEqual(len(self.data["overlap_only"]), 10)
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))

        def slot_values(member_id):
            cls, member, arg = member_id.split(".")
            e = ((cat["classes"].get(cls) or {}).get("methods")
                 or {}).get(member)
            if not e:
                return set()
            slots = ([e.get("return") or {}] if arg == "return"
                     else [a for a in e.get("arguments") or []
                           if a.get("name") == arg])
            return {v["value"] for s in slots
                    for v in (s.get("values") or [])}

        checked = 0
        for link in self.data["overlap_only"]:
            if not link["only_corpus"]:
                continue
            merged = slot_values(link["member"])
            for v in link["only_corpus"]:
                checked += 1
                self.assertNotIn(v, merged, link["member"] + " 混入了 " + v)
        self.assertGreater(checked, 0, "证据里应有非空 only_corpus 的仅重叠链接")


class TestCorpusAdditions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))

    def _values(self, cls, member, arg):
        e = self.cat["classes"][cls]["methods"][member]
        slots = ([e["return"]] if arg == "return"
                 else [a for a in e.get("arguments") or []
                       if a.get("name") == arg])
        return slots[0].get("values") or []

    def test_additions_carry_provenance(self):
        pairs = (("CondBoundaryElectric", "GetBoundaryType", "return",
                  ["battery", "clear", "infinite_elements"]),
                 ("ClosedVolume", "GetConnectionType", "return",
                  ["not_connect"]),
                 ("CondBoundaryWallThermal", "GetContactType", "return",
                  ["glue"]),
                 ("CondParticleGeneration", "GetConversionType", "return",
                  ["none"]),
                 ("Conditions", "GetNextParam", "key",
                  ["CAVI", "CMBV", "CONC_VAPOR"]),
                 ("Conditions", "GetSolvParam", "key", ["eq_comb"]),
                 ("CondDiscontinuous", "GetProjectionType", "return",
                  ["surface"]),
                 ("CondBoundaryWallThermal", "GetOutsideType", "return",
                  ["saturated_humidity"]))
        n = 0
        for cls, member, arg, wanted in pairs:
            got = {v["value"]: v for v in self._values(cls, member, arg)}
            for w in wanted:
                self.assertIn(w, got, cls + "." + member + "." + arg)
                self.assertEqual(got[w].get("source"), "host-corpus", w)
                n += 1
        self.assertGreaterEqual(n, 12)


if __name__ == "__main__":
    unittest.main()
