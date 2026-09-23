#!/usr/bin/env python3
"""R53 证据回归：结论进自动文档（R53-1）/ 盯防清单带动作（R53-2）/ 收口结论进契约门（R53-3）。

收口之后要把结论**锁住**：文档自动生成（与产品面同源）、盯防清单可执行、契约门加第 8 项。
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
NYI_DOC = ROOT / "docs" / "NYI_INVENTORY.md"
GATE = ROOT / "tools" / "api_contract_check.py"
REOPEN_TOOL = ROOT / "tools" / "sweep_reopen_check.py"
SCAN_TOOL = ROOT / "tools" / "scan_nyi_menus.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestDocFromReport(unittest.TestCase):
    """R53-1：文档那一节必须**逐行**等于产品面的汇总。"""

    @classmethod
    def setUpClass(cls):
        from automation import scflowpre_api as api
        cls.api = api
        cls.text = NYI_DOC.read_text(encoding="utf-8")

    def test_four_sections_present(self):
        for key in ("宿主未实现的成员", "取法不可照抄", "取不到实例", "缺语料分组"):
            self.assertIn(key, self.text, key)

    def test_doc_matches_report_line_by_line(self):
        report = self.api.render_capability_report()
        i = self.text.find("宿主能力边界（")
        self.assertGreater(i, 0, "文档里应有能力汇总代码块")
        block = self.text[i:].split("```")[0].rstrip()
        # 逐行对账（文档里的块就是 report 的原文）
        self.assertEqual(block, report.rstrip())

    def test_absent_members_listed_with_next_step(self):
        for cls, names in self.api.host_absent_members().items():
            self.assertIn(cls + " — " + " / ".join(names), self.text)
        self.assertIn("下一步", self.text)

    def test_hints_listed(self):
        for cls, hint in self.api.object_hints().items():
            self.assertIn(cls, self.text)
            self.assertIn(hint, self.text)

    def test_generator_is_the_doc_source(self):
        # 文档由 scan_nyi_menus 生成，且它调的是产品面渲染（不是自己拼）
        src = SCAN_TOOL.read_text(encoding="utf-8")
        self.assertIn("render_capability_report", src)
        self.assertIn("host_capability_report", src)


class TestWatchlistActions(unittest.TestCase):
    """R53-2：每条盯防项都要有**可执行动作**。"""

    @classmethod
    def setUpClass(cls):
        cls.tool = _load("reopen_r53", REOPEN_TOOL)
        cls.ev = json.loads(AVAIL.read_text(encoding="utf-8"))
        cls.acct = json.loads(UNSWEPT.read_text(encoding="utf-8"))
        cls.wl = cls.tool.watchlist(cls.ev, cls.acct)

    def test_every_entry_has_actions(self):
        self.assertTrue(self.wl)
        for cls, meta in self.wl.items():
            self.assertTrue(meta.get("actions"), cls)
            for act in meta["actions"]:
                self.assertTrue(str(act).strip(), cls)
                self.assertNotIn("复查该类", act, cls + "：动作不能是占位话")

    def test_actions_cite_evidence(self):
        # 动作里要能看到证据（取法名/提示/样本数），不是"重新试试"
        joined = " ".join(a for m in self.wl.values() for a in m["actions"])
        self.assertTrue(any(k in joined for k in ("catalog:", "recipe:", "先跑",
                                                  "样本", "0 成员")), joined)

    def test_synthetic_action_kinds(self):
        ev = {"coverage": {
            "swept_suspect": {"X": {"total": 5, "unknown": 4}},
            "empty_objects": ["Y"], "empty_hints": {"Y": "先建八叉树"},
            "auto_empty_targets": {"Y": "catalog:Doc.GetY"},
            "no_member_classes": ["Z"],
            "guard_audit": {"rejection_margins": [
                {"how": "W <- stem:Doc.GetW", "sample": 4, "resolved": 2,
                 "margin": 0}]}}}
        acct = {"classes": {"V": {"terminal": "probe-limitation",
                                  "declared_candidates": ["catalog:Doc.GetV"],
                                  "evidence": "_p12u_gate/r50/x.json"}}}
        wl = self.tool.watchlist(ev, acct)
        self.assertIn("更大的独有成员样本", wl["X"]["actions"][0])
        self.assertIn("先建八叉树", " ".join(wl["Y"]["actions"]))
        self.assertIn("0 成员", " ".join(wl["Z"]["actions"]))
        self.assertIn("catalog:Doc.GetV", " ".join(wl["V"]["actions"]))
        self.assertIn("margin 0", " ".join(wl["W"]["actions"]))


class TestConvergenceGate(unittest.TestCase):
    """R53-3：契约门第 8 项。"""

    @classmethod
    def setUpClass(cls):
        cls.gate = _load("gate_r53", GATE)
        cls.ev = json.loads(AVAIL.read_text(encoding="utf-8"))

    def test_gate_has_eight_checks(self):
        names = [n for n, _ in self.gate.CHECKS]
        self.assertEqual(len(names), 8)
        self.assertIn("convergence", names)

    def test_convergence_passes_now(self):
        res = self.gate.check_sweep_convergence()
        self.assertTrue(res["ok"], res)
        self.assertTrue(res["coverage_ok"])
        self.assertTrue(res["terminals_ok"])
        self.assertTrue(res["reopen_ok"])
        self.assertEqual(res["unattributed"], [])
        self.assertEqual(res["missing_terminal"], [])

    def test_convergence_blocks_regression(self):
        """能挡住回落：拿**合成证据**跑判定（覆盖率掉线 / 未归因 / 有类缺终态）。"""
        import tempfile
        good = self.ev
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            # ① 覆盖率掉线
            bad = td / "avail_floor.json"
            bad.write_text(json.dumps({"coverage": dict(
                good["coverage"], classes_swept=3)}, ensure_ascii=False),
                encoding="utf-8")
            res = self.gate.check_sweep_convergence(
                bad, UNSWEPT, floor=155)
            self.assertFalse(res["ok"])
            self.assertFalse(res["coverage_ok"])
            # ② 未普查类与终态表对不上
            bad2 = td / "avail_unattr.json"
            bad2.write_text(json.dumps({"coverage": dict(
                good["coverage"],
                unswept_classes=list(good["coverage"]["unswept_classes"])
                + ["NotAClass"])}, ensure_ascii=False), encoding="utf-8")
            res2 = self.gate.check_sweep_convergence(bad2, UNSWEPT)
            self.assertFalse(res2["ok"])
            self.assertIn("NotAClass", res2["unattributed"])
            # ③ 有类缺终态
            bad3 = td / "unswept_missing.json"
            acct = json.loads(UNSWEPT.read_text(encoding="utf-8"))
            acct["classes"].pop(next(iter(acct["classes"])))
            bad3.write_text(json.dumps(acct, ensure_ascii=False),
                            encoding="utf-8")
            res3 = self.gate.check_sweep_convergence(AVAIL, bad3)
            self.assertFalse(res3["ok"])
            # 少了一行 → 那个类变成"未归因"（这就是缺终态的可拦截形态）
            self.assertTrue(res3["unattributed"] or res3["missing_terminal"])

    def test_reopen_still_clean(self):
        tool = _load("reopen_r53b", REOPEN_TOOL)
        self.assertFalse(tool.decide(self.ev)["reopen"])


if __name__ == "__main__":
    unittest.main()
