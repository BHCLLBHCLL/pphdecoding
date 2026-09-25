#!/usr/bin/env python3
"""R54 证据回归：契约门自测总账（R54-1）/ 缺语料收益估计（R54-2）/ 复验提醒落点（R54-3）。

收口的最后一环：门要能**自证挡得住**，排期要能**看出优先级**，复验要**自动出声**。
"""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

UNSWEPT = ROOT / "schemas" / "unswept_account.json"
GATE = ROOT / "tools" / "api_contract_check.py"
RUNNER = ROOT / "run_all_tests.py"
REOPEN = ROOT / "tools" / "sweep_reopen_check.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestGateSelfTest(unittest.TestCase):
    """R54-1：8 项各有合成反例，且**全部被挡住**。"""

    @classmethod
    def setUpClass(cls):
        cls.gate = _load("gate_r54", GATE)

    def test_every_check_has_a_counterexample(self):
        with tempfile.TemporaryDirectory() as td:
            cases = self.gate._self_test_cases(Path(td))
        names = [n for n, _ in self.gate.CHECKS]
        self.assertEqual(sorted(cases), sorted(names),
                         "8 项每项都要有反例")

    def test_self_test_all_blocked(self):
        rc = self.gate.main(["--self-test"])
        self.assertEqual(rc, 0, "有反例没被挡住 —— 那项门是摆设")

    def test_counterexamples_really_fail(self):
        # 逐项跑反例：每项都必须 ok=False（不是靠 self_test 的汇总口径）
        with tempfile.TemporaryDirectory() as td:
            cases = self.gate._self_test_cases(Path(td))
            for name, fn in self.gate.CHECKS:
                res = cases[name]()
                self.assertFalse(res.get("ok"), name + " 反例竟然通过了")

    def test_patches_are_restored(self):
        # 自测会临时替换模块级名字：跑完必须还原，否则后面全乱
        before = (self.gate.ROOT, self.gate.CATALOG, self.gate._load)
        self.gate.main(["--self-test"])
        after = (self.gate.ROOT, self.gate.CATALOG, self.gate._load)
        self.assertEqual(before, after)


class TestCorpusPlan(unittest.TestCase):
    """R54-2：缺语料分组带"补上后能多覆盖几类"。"""

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(UNSWEPT.read_text(encoding="utf-8"))

    def test_plan_covers_every_group(self):
        groups = self.data.get("needs_corpus_groups") or {}
        plan = self.data.get("needs_corpus_plan") or {}
        self.assertTrue(groups)
        self.assertEqual(sorted(plan), sorted(groups))

    def test_estimates_partition_group(self):
        plan = self.data["needs_corpus_plan"]
        for g, info in plan.items():
            self.assertEqual(sorted(info["classes"]),
                             sorted(self.data["needs_corpus_groups"][g]), g)
            self.assertEqual(info["expected_gain"] + len(info["no_path"]),
                             len(info["classes"]), g)
            for cls in info["no_path"]:
                self.assertIn(cls, info["classes"], g)

    def test_gain_is_evidence_based(self):
        # 有取法的类必须进 expected_gain（例：粒子组的条件类都有配方/候选）
        plan = self.data["needs_corpus_plan"]
        self.assertGreaterEqual(plan["粒子/DEM"]["expected_gain"], 4)
        total = sum(v["expected_gain"] for v in plan.values())
        self.assertGreaterEqual(total, 15)

    def test_no_path_classes_flagged(self):
        plan = self.data["needs_corpus_plan"]
        flagged = [c for v in plan.values() for c in v["no_path"]]
        # 标出来的必须确实没有取法（配方的取法文本是空的，或候选是空的）
        rows = self.data["classes"]
        for cls in flagged:
            self.assertFalse(rows[cls].get("declared_candidates"), cls)
            self.assertFalse((rows[cls].get("recipe") or "").startswith("Set "),
                             cls)


class TestReopenNotice(unittest.TestCase):
    """R54-3：复验提醒接进回归入口，异常才出声。"""

    @classmethod
    def setUpClass(cls):
        cls.runner = _load("runner_r54", RUNNER)

    def test_silent_when_healthy(self):
        self.assertEqual(self.runner.reopen_notice(), "")

    def test_speaks_up_on_reopen(self):
        class Fake:
            returncode = 1
            stdout = ("[reopen] 结论：**建议重开普查**\n"
                      "  ★ 硬理由：宿主版本变了\n").encode("utf-8")
            stderr = b""

        orig = self.runner.subprocess.run
        self.runner.subprocess.run = lambda *a, **k: Fake()
        try:
            note = self.runner.reopen_notice()
        finally:
            self.runner.subprocess.run = orig
        self.assertIn("建议重开", note)
        self.assertIn("宿主版本变了", note)

    def test_runner_calls_it(self):
        src = RUNNER.read_text(encoding="utf-8")
        self.assertIn("reopen_notice()", src)
        self.assertIn("sweep_reopen_check.py", src)

    def test_tool_rc_semantics(self):
        tool = _load("reopen_r54", REOPEN)
        self.assertEqual(tool.main([]), 0)
        self.assertEqual(tool.main(["--floor", "100000"]), 1)


if __name__ == "__main__":
    unittest.main()
