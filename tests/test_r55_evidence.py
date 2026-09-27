#!/usr/bin/env python3
"""R55 证据回归：收口一页（R55-1）/ 补语料成本估计（R55-2）/ 同源面进自测（R55-3）。

收口之后的最后一层：**一页读完**、**排期看得出成本**、**同源面也进门**。
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

AVAIL = ROOT / "schemas" / "host_member_availability.json"
UNSWEPT = ROOT / "schemas" / "unswept_account.json"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
DOC = ROOT / "docs" / "HOST_API_COVERAGE.md"
DOC_TOOL = ROOT / "tools" / "host_coverage_doc.py"
GATE = ROOT / "tools" / "api_contract_check.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestOnePager(unittest.TestCase):
    """R55-1：一页文档与证据对账。"""

    @classmethod
    def setUpClass(cls):
        cls.tool = _load("covdoc_r55", DOC_TOOL)
        cls.ev = json.loads(AVAIL.read_text(encoding="utf-8"))
        cls.acct = json.loads(UNSWEPT.read_text(encoding="utf-8"))
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.text = DOC.read_text(encoding="utf-8")

    def test_doc_is_in_sync_with_evidence(self):
        self.assertEqual(self.tool.main(["--check"]), 0,
                         "一页文档必须与证据一致（改了证据就重生成）")

    def test_numbers_come_from_evidence(self):
        cov = self.ev["coverage"]
        self.assertIn(str(cov["classes_swept"]) + "/" + str(cov["classes_total"])
                      + " 类", self.text)
        self.assertIn(str(cov["members_swept"]) + "/"
                      + str(cov["members_total"]), self.text)
        absent = sum(1 for i in self.cat["classes"].values()
                     for k in ("methods", "properties")
                     for e in (i.get(k) or {}).values() if e.get("host_absent"))
        self.assertIn("宿主未实现 **" + str(absent) + " 条**", self.text)

    def test_buckets_partition_documented(self):
        cov = self.ev["coverage"]
        total = (cov["classes_swept"] + len(cov["empty_objects"])
                 + len(cov["no_member_classes"]) + len(cov["unswept_classes"]))
        self.assertEqual(total, cov["classes_total"])
        self.assertIn("| **合计** | **" + str(cov["classes_total"]) + "** |",
                      self.text)

    def test_terminals_and_groups_listed(self):
        counts = self.acct["counts"]
        for k in ("needs-corpus", "no-creation-path", "call-rejected"):
            self.assertIn("| `" + k + "` | " + str(counts[k]) + " |",
                          self.text)
        for g, info in self.acct["needs_corpus_plan"].items():
            self.assertIn(g, self.text)
            self.assertIn(str(info["expected_gain"]), self.text)

    def test_boundary_section_warns_against_extrapolation(self):
        self.assertIn("适用边界", self.text)
        self.assertIn("不许外推", self.text)
        self.assertIn("不替代", self.text.replace("**", ""))

    def test_build_is_pure(self):
        # 同一份输入 → 同一份输出（生成器不许带时间戳之类的噪声）
        a = self.tool.build(self.ev, self.acct, self.cat)
        b = self.tool.build(self.ev, self.acct, self.cat)
        self.assertEqual(a, b)


class TestCorpusCost(unittest.TestCase):
    """R55-2：成本档与"要什么算例"。"""

    @classmethod
    def setUpClass(cls):
        cls.acct = json.loads(UNSWEPT.read_text(encoding="utf-8"))
        cls.tool = _load("unswept_r55", ROOT / "tools" / "unswept_account.py")

    def test_every_group_has_tier_and_what(self):
        for g, info in self.acct["needs_corpus_plan"].items():
            self.assertIn(info.get("tier"), ("小", "中", "大", "未评估"), g)
            self.assertTrue(str(info.get("what") or "").strip(), g)

    def test_tiers_are_declared_in_tool(self):
        declared = {g for g, _ in self.tool.CORPUS_COST.items()}
        for g in self.acct["needs_corpus_plan"]:
            self.assertIn(g, declared | {"其他"}, g)

    def test_unknown_group_is_honest(self):
        out = self.tool.corpus_cost("不存在的组")
        self.assertEqual(out["tier"], "未评估")
        self.assertIn("未登记", out["what"])

    def test_cost_is_not_a_promise(self):
        # 成本档必须写明"要什么"，不许只给档位（排期要能据此安排）
        for g, info in self.acct["needs_corpus_plan"].items():
            self.assertGreaterEqual(len(str(info["what"])), 8, g)


class TestSurfaceChecks(unittest.TestCase):
    """R55-3：同源面（文档/面板）进契约门与自测。"""

    @classmethod
    def setUpClass(cls):
        cls.gate = _load("gate_r55", GATE)

    def test_gate_has_ten_checks(self):
        """门只许加不许减（R55 立 10 项、R56 加测试总账 1 项）。"""
        names = [n for n, _ in self.gate.CHECKS]
        self.assertGreaterEqual(len(names), 10)
        for key in ("doc_report", "panel_report", "test_ledger"):
            self.assertIn(key, names)

    def test_surface_checks_pass_now(self):
        for name in ("doc_report", "panel_report"):
            res = dict(self.gate.CHECKS)[name]()
            self.assertTrue(res.get("ok"), (name, res))

    def test_self_test_is_ten_of_ten(self):
        rc = self.gate.main(["--self-test"])
        self.assertEqual(rc, 0)

    def test_doc_counterexample_detected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.md"
            p.write_text("宿主能力边界（假）\n\n" + chr(96) * 3 + "text\nx\n"
                         + chr(96) * 3 + "\n", encoding="utf-8")
            res = self.gate.check_doc_matches_report(p)
        self.assertFalse(res["ok"])

    def test_panel_counterexample_detected(self):
        class Bad:
            @staticmethod
            def host_boundary_data():
                return {"absent": {}, "recipes": {}, "hints": {}}

            @staticmethod
            def render_host_boundary(_d):
                return "空"

        res = self.gate.check_panel_matches_report(Bad())
        self.assertFalse(res["ok"])


if __name__ == "__main__":
    unittest.main()
