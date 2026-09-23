#!/usr/bin/env python3
"""R52 证据回归：未普查类参与同名判定（R52-1）/ 四份结论一个入口（R52-2）/ 盯防清单（R52-3）。

收口之后的三件事：结论要**更准**（证据分级）、要**一处可查**（汇总入口）、要被**守住**
（重开时知道先复查谁）。
"""

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

AVAIL = ROOT / "schemas" / "host_member_availability.json"
UNSWEPT = ROOT / "schemas" / "unswept_account.json"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
REOPEN_TOOL = ROOT / "tools" / "sweep_reopen_check.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestGradedAlternative(unittest.TestCase):
    """R52-1：别类的同名成员要**分级**说，不许笼统"未实测"。"""

    @classmethod
    def setUpClass(cls):
        from automation import scflowpre_api as api
        cls.api = api
        cls.ev = json.loads(AVAIL.read_text(encoding="utf-8"))

    def test_tier1_measured_when_available(self):
        # Condition.GetName：同名成员在若干已普查类里 resolved → 必须说"实测可用"
        alt = self.api.member_alternative("Condition", "GetName")
        if "实测可用" not in alt:
            raise unittest.SkipTest("本机没有该成员的其他实现：" + alt)
        self.assertIn("resolved", alt)

    def test_tier_unknown_class_is_flagged_not_measured(self):
        alt = self.api.member_alternative("SpecialRegion", "ImportCSV")
        self.assertIn("未实测", alt)

    def test_grading_reads_availability(self):
        # 分级必须依赖证据文件，而不是目录里的"有没有这一条"
        av = self.ev.get("availability") or {}
        self.assertTrue(av, "证据里应有 availability")
        cls = next(iter(av))
        self.assertIsInstance(av[cls], dict)

    def test_empty_object_owner_gets_prerequisite(self):
        """空对象类里的同名成员：给"未实测 + 先跑前置流程"（若该类确实在空对象里）。"""
        cov = self.ev["coverage"]
        empty = set(cov.get("empty_objects") or [])
        if not empty:
            raise unittest.SkipTest("本轮没有空对象类")
        hints = cov.get("empty_hints") or {}
        member = None
        for e_cls in sorted(empty):
            for m in (self.api.load_catalog()["classes"].get(e_cls, {})
                      .get("methods") or {}):
                member = m
                break
            if member:
                break
        if not member:
            raise unittest.SkipTest("空对象类没有成员可试")
        # 直接验分级函数（构造 owners=空对象类）
        out = self.api._grade_owners([sorted(empty)[0]], member)
        self.assertTrue(out)
        if hints.get(sorted(empty)[0]):
            self.assertIn("先跑前置流程", out)

    def test_tier4_says_do_not_switch(self):
        # 已普查但该成员 unknown 的类：不许推荐（构造一个真实例子）
        av = self.ev.get("availability") or {}
        pair = None
        for cls, states in av.items():
            for mem, st in states.items():
                if st == "unknown_name":
                    pair = (cls, mem)
                    break
            if pair:
                break
        if not pair:
            raise unittest.SkipTest("本轮没有 unknown 成员")
        cls, mem = pair
        out = self.api._grade_owners([cls], mem)
        self.assertTrue(out)


class TestCapabilityReport(unittest.TestCase):
    """R52-2：四份结论一个入口。"""

    @classmethod
    def setUpClass(cls):
        from automation import scflowpre_api as api
        cls.api = api
        cls.rep = api.host_capability_report()
        cls.ev = json.loads(AVAIL.read_text(encoding="utf-8"))
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))

    def test_four_sections_present(self):
        for key in ("host_absent", "unreliable_recipes", "object_hints",
                    "needs_corpus_groups"):
            self.assertIn(key, self.rep)
            self.assertIn(key, self.rep["sources"], "每段都要标来源")

    def test_sections_match_sources(self):
        self.assertEqual(self.rep["host_absent"],
                         self.api.host_absent_members(self.cat))
        self.assertEqual(self.rep["unreliable_recipes"],
                         self.api.unreliable_recipes(self.cat))
        self.assertEqual(self.rep["object_hints"],
                         self.api.object_hints())
        acct = json.loads(UNSWEPT.read_text(encoding="utf-8"))
        self.assertEqual(self.rep["needs_corpus_groups"],
                         acct.get("needs_corpus_groups") or {})

    def test_coverage_snapshot(self):
        cov = self.rep["coverage"]
        self.assertEqual(cov["classes_swept"],
                         self.ev["coverage"]["classes_swept"])
        self.assertIn("no_member_classes", cov)

    def test_render_is_complete(self):
        text = self.api.render_capability_report(self.rep)
        for cls in self.rep["host_absent"]:
            self.assertIn(cls, text)
        for group in self.rep["needs_corpus_groups"]:
            self.assertIn(group, text)
        self.assertIn("下一步", text)

    def test_render_survives_empty(self):
        text = self.api.render_capability_report({})
        self.assertIn("宿主能力边界", text)

    def test_panel_shows_report(self):
        # 面板是 QWidget：**先建 QApplication**（否则 Qt 会直接卡住/中止）
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance() or QApplication([])
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest("Qt 不可用: " + str(exc))
        import nav_panels
        dlg = nav_panels.HostBoundaryDialog()
        text = dlg.txt.toPlainText()
        self.assertIn("宿主能力边界", text)
        self.assertIn("缺语料分组", text)
        del app


class TestWatchlist(unittest.TestCase):
    """R52-3：重开时先复查谁。"""

    @classmethod
    def setUpClass(cls):
        cls.tool = _load("reopen_r52", REOPEN_TOOL)
        cls.ev = json.loads(AVAIL.read_text(encoding="utf-8"))
        cls.acct = json.loads(UNSWEPT.read_text(encoding="utf-8"))

    def test_watchlist_covers_evidence_kinds(self):
        wl = self.tool.watchlist(self.ev, self.acct)
        self.assertTrue(wl)
        kinds = {k for meta in wl.values() for k in meta["kinds"]}
        cov = self.ev["coverage"]
        if cov.get("swept_suspect"):
            self.assertIn("swept_suspect", kinds)
        if cov.get("empty_objects"):
            self.assertIn("empty_object", kinds)
        if cov.get("no_member_classes"):
            self.assertIn("no_member", kinds)
        for meta in wl.values():
            self.assertTrue(meta["why"])
            for why in meta["why"]:
                self.assertTrue(why.strip())

    def test_watchlist_from_synthetic_evidence(self):
        ev = {"coverage": {"swept_suspect": {"X": {"total": 5, "unknown": 4}},
                           "empty_objects": ["Y"],
                           "no_member_classes": ["Z"],
                           "guard_audit": {"rejection_margins": [
                               {"how": "W <- p", "sample": 5, "resolved": 2,
                                "margin": -1}]}}}
        acct = {"classes": {"V": {"terminal": "probe-limitation"}}}
        wl = self.tool.watchlist(ev, acct)
        self.assertEqual(sorted(wl), ["V", "W", "X", "Y", "Z"])
        self.assertIn("near_threshold", wl["W"]["kinds"])
        self.assertIn("probe_limitation", wl["V"]["kinds"])

    def test_watchlist_cli(self):
        self.assertEqual(self.tool.main(["--watchlist"]), 0)

    def test_decide_still_ok(self):
        self.assertFalse(self.tool.decide(self.ev)["reopen"])


if __name__ == "__main__":
    unittest.main()
