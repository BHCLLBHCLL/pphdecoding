#!/usr/bin/env python3
"""R32-1 回归：实测宿主键账本（18 条）+ 面板写入口对账 + 单会话重核。

三件事各钉一条：

1. **账本自洽**：`schemas/host_keys.json` 每条都有 setter/轮次/证据，证据文件真实存在；
   轮次计数 4+3+2+3+5+1 = 18（**更正**文档旧口径「19」—— 旧口径把 R6-5 里被记为
   「未变化」的 `SetFacetUseAbsoluteValue` 也计成了键，见审计 §46.1）；
2. **账本 ↔ 代码一致**：每个 setter 在目录 `MeshingGroupSetting` 里真实存在；
   `tools/xenv_host_write_check.py` 的 `WRITES`/`WRITES_MORE` 必然是账本子集；
3. **账本 ↔ 实机一致**：`_p12u_gate/r32/keys_reverify.json` 是**单会话 18 档**重核
   （256/256 err=0）：每档的增量必须**恰好**是账本里那一把键（多一把少一把都算失败）。
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LEDGER_PATH = ROOT / "schemas" / "host_keys.json"
REVERIFY = ROOT / "_p12u_gate" / "r32" / "keys_reverify.json"
CHECK = ROOT / "tools" / "xenv_host_write_check.py"
COVERAGE = ROOT / "tools" / "host_key_coverage.py"
#: 轮次计数（R32-1 更正后的口径）
ROUND_COUNTS = {"R6-5": 4, "R10-3": 3, "R26": 2, "R27": 3, "R29": 5, "R30": 1}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestLedger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        cls.keys = cls.ledger["keys"]
        cls.ids = [e["section"] + "." + e["key"] for e in cls.keys]

    def test_ids_unique_and_wellformed(self):
        self.assertEqual(len(self.ids), len(set(self.ids)))
        for e in self.keys:
            self.assertTrue(e["section"] and e["key"] and e["setter"])
            self.assertTrue(e["round"].startswith("R"))

    def test_round_counts_account_for_all_keys(self):
        counts: dict = {}
        for e in self.keys:
            counts[e["round"]] = counts.get(e["round"], 0) + 1
        self.assertEqual(counts, ROUND_COUNTS)
        self.assertEqual(sum(ROUND_COUNTS.values()), len(self.keys))
        self.assertEqual(len(self.keys), 18)

    def test_evidence_files_exist(self):
        for e in self.keys:
            ev = e["evidence"]
            if ev.startswith("audit §"):
                continue
            self.assertTrue((ROOT / ev).is_file(), ev + " 证据文件不存在")

    def test_setters_exist_in_catalog(self):
        """账本里的 setter 必须**在手册里**存在 —— 除非在 ledger 显式声明为
        「宿主实有、手册全无」（R32-1 实测 SetIntersectionDetectionDepth 即此类：
        手册 199 类与全库 HTML 都没有该名字，但宿主 setter 返回 True 且落键）。"""
        cat = json.loads(
            (ROOT / "schemas" / "vb_api_catalog.json").read_text(
                encoding="utf-8"))
        methods = cat["classes"]["MeshingGroupSetting"]["methods"]
        undocumented = set(self.ledger.get("undocumented_setters") or [])
        for e in self.keys:
            if e["setter"] in undocumented:
                self.assertNotIn(e["setter"], methods,
                                 "已声明未入册的 setter 又出现在手册里 → 该声明该删")
                continue
            self.assertIn(e["setter"], methods, e["setter"])
        self.assertEqual(undocumented, {"SetIntersectionDetectionDepth"})

    def test_host_write_check_is_subset_of_ledger(self):
        chk = _load("xhw_r321", CHECK)
        ids = set(self.ids)
        for k, _v, _g, _l in chk.WRITES:
            self.assertIn(chk.SECTION + "." + k, ids)
        for s, k, _v, _g, _e, _l in chk.WRITES_MORE:
            self.assertIn(s + "." + k, ids)


class TestReverifyEvidence(unittest.TestCase):
    """单会话 18 档重核：每档增量必须恰好是账本里那一把键。"""

    @classmethod
    def setUpClass(cls):
        if not REVERIFY.is_file():
            raise unittest.SkipTest("reverify evidence missing")
        cls.data = json.loads(REVERIFY.read_text(encoding="utf-8"))
        cls.ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        cls.by_setter = {e["setter"]: e["section"] + "." + e["key"]
                         for e in cls.ledger["keys"]}

    def test_host_session_clean(self):
        host = self.data["host"]
        self.assertIsNone(host.get("error"))
        self.assertEqual(host["err0"], host["total"])
        self.assertGreaterEqual(host["total"], 200)

    def test_every_step_hits_exactly_its_key(self):
        seen = set()
        for row in self.data["per_case"]:
            setter = row["setter"]
            want = self.by_setter[setter]
            got = sorted(row.get("delta_vs_prev") or {})
            self.assertEqual(got, [want],
                             setter + " 的增量不是恰好的那一把键")
            seen.add(want)
        self.assertEqual(seen, set(self.by_setter.values()),
                         "账本里有键没被重核覆盖")

    def test_all_steps_single_host_session(self):
        self.assertEqual(len(self.data["per_case"]), 18)


class TestPanelCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import nav_panels  # noqa: F401
        except Exception:  # noqa: BLE001
            raise unittest.SkipTest("PyQt5 not available")
        cls.cov = _load("coverage_r321", COVERAGE)

    def test_gaps_equal_declared_gaps(self):
        data = self.cov.report(use_qt=True)
        self.assertEqual(data["ledger_duplicates"], [])
        self.assertEqual(data["gaps"], data["known_gaps"],
                         "缺口必须显式声明（新增缺口不许静默）")

    def test_coverage_is_majority_and_monotone(self):
        data = self.cov.report(use_qt=True)
        self.assertGreaterEqual(data["panel_written_count"], 17)
        self.assertGreaterEqual(data["host_readback_count"], 4)


if __name__ == "__main__":
    unittest.main()
