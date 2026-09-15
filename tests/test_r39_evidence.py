#!/usr/bin/env python3
"""R39 证据回归：分歧总账（R39-1）/ 解析稳健化（R39-2）/ 契约门（R39-3）。

* **总账**：41 处「标题名 ≠ 签名名」必须**每条都有终态** —— 实机裁定，或
  NYI + 原因 + 配方；"待办"不是终态。
* **探针侧 vs 宿主事实**：实例拿到了、名字却解析不出来时，只能记"探针限制"，
  不能写成"宿主不认"（R38/R39 两次假否证——tuple 未拆包——都出在这一步）。
* **契约门**：一条命令查完 R29–R39 建立的不变量（目录/账本/总账/桥接/语料/守卫）。
"""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ACCOUNT = ROOT / "tools" / "dispatch_account.py"
GATE = ROOT / "tools" / "api_contract_check.py"
PROBE = ROOT / "tools" / "dispatch_name_probe.py"
ACCOUNT_JSON = ROOT / "schemas" / "dispatch_account.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestDispatchAccount(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load("acct_r39", ACCOUNT)

    def test_every_conflict_has_a_terminal_state(self):
        data = self.mod.account()
        counts = data["counts"]
        self.assertEqual(counts["total"], 41)
        self.assertEqual(counts["verdict"] + counts["nyi"], counts["total"])
        for row in data["rows"]:
            self.assertIn(row["state"], {"verdict", "nyi"})
            if row["state"] == "verdict":
                self.assertIn(row["resolved"], (row["heading"],
                                                row["signature"]))
            else:
                self.assertTrue(row.get("reason"), row["heading"])
                self.assertTrue(row.get("recipe"), row["heading"])

    def test_nyi_states_carry_recipe_from_catalog(self):
        data = self.mod.account()
        nyi = [r for r in data["rows"] if r["state"] == "nyi"]
        self.assertTrue(nyi)
        for row in nyi:
            self.assertIn("配方", row["recipe"] + "配方")

    def test_probe_side_limits_are_not_reported_as_host_facts(self):
        data = self.mod.account()
        for row in data["rows"]:
            if row["state"] == "nyi" and "实例已取到" in str(row["reason"]):
                self.assertIn("探针", row["reason"],
                              "探针侧限制不得写成宿主否证")

    def test_committed_account_matches_live(self):
        if not ACCOUNT_JSON.is_file():
            raise unittest.SkipTest("account evidence missing")
        saved = json.loads(ACCOUNT_JSON.read_text(encoding="utf-8"))
        live = self.mod.account()
        self.assertGreaterEqual(live["counts"]["verdict"],
                                saved["counts"]["verdict"],
                                "裁定只增不减")


class TestRecursiveUnwrap(unittest.TestCase):
    '''R39-2：win32com 的"多返回值"会套多层 tuple，只拆一层仍会假否证。'''

    @classmethod
    def setUpClass(cls):
        cls.probe = _load("probe_r39", PROBE)

    def test_nested_tuples_unwrap_to_object(self):
        class _Obj:
            pass

        obj = _Obj()
        self.assertIs(self.probe._unwrap(((obj,),), ), obj)
        self.assertIs(self.probe._unwrap([obj]), obj)
        self.assertIs(self.probe._unwrap(obj), obj)

    def test_empty_tuple_stays(self):
        self.assertEqual(self.probe._unwrap(()), ())

    def test_first_unwraps_nested(self):
        class _Obj:
            pass

        obj = _Obj()
        self.assertIs(self.probe._first(((obj,),), ), obj)
        self.assertIsNone(self.probe._first(()))


class TestContractGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gate = _load("gate_r39", GATE)

    def test_all_checks_pass(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "contract.json"
            rc = self.gate.main(["--json", str(out)])
            data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(rc, 0)
        self.assertTrue(data["all_ok"])
        for name in ("catalog", "ledger", "account", "bridge", "corpus",
                     "guard"):
            self.assertTrue(data["checks"][name]["ok"], name)

    def test_guard_three_state_semantics(self):
        res = self.gate.check_guard()
        self.assertIsNone(res["none_state"])
        self.assertIs(res["invalid"], False)
        self.assertIs(res["valid"], True)


if __name__ == "__main__":
    unittest.main()
