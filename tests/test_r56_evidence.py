#!/usr/bin/env python3
"""R56 证据回归：口径绑定实现（R56-1）/ 测试总账（R56-2）/ 多版本宿主判据（R56-3）。

收口之后要防的是**悄悄失效**：判据改了文档没改、判据删了测试还绿、宿主升级了没人知道。
本轮把这三件事都变成可查的。
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOC_TOOL = ROOT / "tools" / "host_coverage_doc.py"
GATE = ROOT / "tools" / "api_contract_check.py"
REOPEN = ROOT / "tools" / "sweep_reopen_check.py"
EXTRACT = ROOT / "tools" / "extract_vb_api_scflow.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestMethodBindings(unittest.TestCase):
    """R56-1：一页文档的每条口径都要绑到**还在**的实现符号。"""

    @classmethod
    def setUpClass(cls):
        cls.tool = _load("covdoc_r56", DOC_TOOL)

    def test_all_bindings_resolve(self):
        res = self.tool.verify_method_bindings()
        self.assertTrue(res["ok"], res["missing"])
        self.assertGreaterEqual(res["checked"], 5)

    def test_every_method_has_a_binding(self):
        for entry in self.tool.METHOD:
            self.assertEqual(len(entry), 2, entry)
            text, where = entry
            self.assertIn(":", where, where)
            self.assertTrue(text.strip())

    def test_doc_renders_bindings(self):
        text = (ROOT / "docs" / "HOST_API_COVERAGE.md").read_text(
            encoding="utf-8")
        for _text, where in self.tool.METHOD:
            self.assertIn(where, text, where)

    def test_broken_binding_is_detected(self):
        real = list(self.tool.METHOD)
        self.tool.METHOD.append(("假口径", "tools/dispatch_name_probe.py:NoSuchSymbol"))
        try:
            res = self.tool.verify_method_bindings()
        finally:
            self.tool.METHOD[:] = real
        self.assertFalse(res["ok"])
        self.assertTrue(any("NoSuchSymbol" in m for m in res["missing"]))

    def test_missing_file_is_detected(self):
        real = list(self.tool.METHOD)
        self.tool.METHOD.append(("假口径", "tools/___nope___.py:x"))
        try:
            res = self.tool.verify_method_bindings()
        finally:
            self.tool.METHOD[:] = real
        self.assertFalse(res["ok"])


class TestCriterionLedger(unittest.TestCase):
    """R56-2：判据 ↔ 测试双向覆盖（门第 11 项）。"""

    @classmethod
    def setUpClass(cls):
        cls.gate = _load("gate_r56", GATE)

    def test_no_orphan_criteria(self):
        res = self.gate.check_test_ledger()
        self.assertEqual(res["orphan_criteria"], [],
                         "有判据没被任何测试引用")
        self.assertTrue(res["ok"], res)

    def test_no_module_without_symbol(self):
        res = self.gate.check_test_ledger()
        self.assertEqual(res["modules_without_symbol"], [])
        self.assertGreaterEqual(res["test_modules"], 8)

    def test_gate_has_eleven_checks(self):
        names = [n for n, _ in self.gate.CHECKS]
        self.assertGreaterEqual(len(names), 11)
        self.assertIn("test_ledger", names)

    def test_orphan_detection_works(self):
        # 名字**拼接**出来：否则本文件自己就"引用"了它，孤儿检测会看不见
        # （总账扫的是所有 tests/*.py —— 这是它该有的行为）
        fake = "__never_" + "referenced_criterion__"
        real = dict(self.gate.CRITERION_CORE)
        self.gate.CRITERION_CORE[fake] = "假判据"
        try:
            res = self.gate.check_test_ledger()
        finally:
            self.gate.CRITERION_CORE.clear()
            self.gate.CRITERION_CORE.update(real)
        self.assertFalse(res["ok"])
        self.assertIn(fake, res["orphan_criteria"])

    # ---- 本轮由总账"抓出来"的四个缺口，补齐测试 ----
    def test_api_arg_values_three_state(self):
        from automation import scflowpre_api as api
        # 有词表的参数 → 非空；查不到的成员 → 空表（三态口径：无词表不算错）
        got = api.api_arg_values("MeshingGroupSetting", "ChangeMesher", "type")
        self.assertTrue(got, "有词表的参数应给出取值集")
        self.assertTrue(all("value" in v for v in got))
        self.assertEqual(api.api_arg_values("Doc", "NoSuchMember"), [])

    def test_apply_host_absent_marks_entries(self):
        ex = _load("extract_r56", EXTRACT)
        tmp = ROOT / "_r56_avail.json"
        tmp.write_text(json.dumps({
            "availability": {"Y": {"DeadMember": "unknown_name",
                                   "Alive": "resolved"}}},
            ensure_ascii=False), encoding="utf-8")
        real = ex.HOST_AVAILABILITY
        ex.HOST_AVAILABILITY = tmp
        try:
            cat = {"classes": {"Y": {"methods": {
                "DeadMember": {}, "Alive": {}}}}}
            n = ex._apply_host_absent(cat)
        finally:
            ex.HOST_AVAILABILITY = real
            tmp.unlink(missing_ok=True)
        self.assertEqual(n, 1)
        self.assertTrue(cat["classes"]["Y"]["methods"]["DeadMember"]["host_absent"])
        self.assertNotIn("host_absent", cat["classes"]["Y"]["methods"]["Alive"])


class TestVersionVerdict(unittest.TestCase):
    """R56-3：多版本宿主的四种情形分开说。"""

    @classmethod
    def setUpClass(cls):
        cls.tool = _load("reopen_r56", REOPEN)
        cls.R = "scFLOWpre_Bx64net.Application."

    def test_coarse_evidence_same_major(self):
        v = self.tool.version_verdict(self.R + "2025", [self.R + "2025"],
                                      ["2025.2"])
        self.assertFalse(v["reopen"])
        self.assertTrue(any("判不出来" in w for w in v["warnings"]))

    def test_fine_version_gone_is_reopen(self):
        v = self.tool.version_verdict(self.R + "2025.2", [self.R + "2025"],
                                      ["2025.3"])
        self.assertTrue(v["reopen"])
        self.assertTrue(any("2025.3" in r for r in v["reasons"]))

    def test_major_version_change_is_reopen(self):
        v = self.tool.version_verdict(self.R + "2025", [self.R + "2026"], [])
        self.assertTrue(v["reopen"])

    def test_newer_available_but_evidence_version_present(self):
        v = self.tool.version_verdict(self.R + "2025.2", [self.R + "2025"],
                                      ["2025.2", "2025.3"])
        self.assertFalse(v["reopen"])
        self.assertTrue(any("不必立刻重开" in w for w in v["warnings"]))

    def test_progid_parsing_takes_after_application(self):
        self.assertEqual(self.tool._progid_version(self.R + "2025.2"), "2025.2")
        self.assertEqual(self.tool._progid_version(self.R + "2025"), "2025")
        self.assertEqual(self.tool._progid_version("NoDots"), "NoDots")

    def test_reopen_check_still_clean(self):
        ev = json.loads((ROOT / "schemas" /
                         "host_member_availability.json").read_text(
                             encoding="utf-8"))
        res = self.tool.decide(ev)
        self.assertFalse(res["reopen"], res["reasons"])


if __name__ == "__main__":
    unittest.main()
