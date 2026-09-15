#!/usr/bin/env python3
"""R41 证据回归：9 条 NYI 的推进入手（宿主能力 vs 对象前置）。

这一轮把「9 条 NYI」从"取不到实例"推进到**机制级结论**：

* 3 个类的创建/查询接口在宿主上**根本不存在**（`DISP_E_UNKNOWNNAME`）——
  手册没列、宿主也没实现（反向漏项的又一例）；
* 其余受**对象前置**阻塞：闭空间要 MDL（`wizard.CreateMDL` 调过仍是空）、
  PropItem 要材料、CoSim 区域要有 CoSim 条件（本机语料无此条件）。

同时修掉三个探针缺陷（都是"假否证"同族）：

1. `errors.setdefault` 让**旧的失败文本**盖住新结论（必须先覆盖）；
2. `_try` 存实例时**没拆 tuple** → 后续 `host.call` 报 'tuple' object has no attribute；
3. **空 tuple 被当成对象**（`GetCondCoSim()` 返回 `()` 表示"没有该条件"）→ 必须先判空。
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROBE = ROOT / "tools" / "dispatch_name_probe.py"
ACCOUNT = ROOT / "tools" / "dispatch_account.py"
EVIDENCE = ROOT / "_p12u_gate" / "r41" / "name_verdicts.json"
ACCOUNT_JSON = ROOT / "schemas" / "dispatch_account.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestUnwrapSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.probe = _load("probe_r41", PROBE)

    def test_empty_tuple_means_nothing(self):
        """空 tuple = "没拿到对象"（`GetCondCoSim()` 无 CoSim 条件时返回 ()）。"""
        self.assertIsNone(self.probe._unwrap(()))
        self.assertIsNone(self.probe._unwrap([]))

    def test_nested_tuples_still_unwrap(self):
        class _Obj:
            pass

        obj = _Obj()
        self.assertIs(self.probe._unwrap((((obj,),),)), obj)

    def test_plain_object_passthrough(self):
        class _Obj:
            pass

        obj = _Obj()
        self.assertIs(self.probe._unwrap(obj), obj)


class TestR41Evidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EVIDENCE.is_file():
            raise unittest.SkipTest("r41 evidence missing")
        cls.data = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_unknown_verdicts_are_gone(self):
        self.assertEqual([v for v in self.data["verdicts"]
                          if v["verdict"] == "unknown"], [])
        self.assertEqual([v for v in self.data["verdicts"]
                          if v["verdict"] == "neither"], [])

    def test_host_interface_absence_is_recorded(self):
        calls = self.data.get("call_errors") or {}
        for name in ("CreateCondMapForStructure",
                     "QueryCondMapForStructureByName",
                     "CreateCondBoussinesqBaseTemp",
                     "GetAllMapCondNames"):
            self.assertIn(name, calls, name)
            self.assertIn("未知名称", calls[name], name)

    def test_mdl_probe_diagnostics(self):
        probe = self.data.get("mdl_probe") or {}
        self.assertEqual(probe.get("begin"), "ok")
        self.assertTrue(probe.get("wizard"))
        self.assertTrue(probe.get("mdl_raw_is_none"),
                        "R41 结论：CreateMDL 之后 GetMDL() 仍为空")

    def test_pairs_still_accounted(self):
        self.assertEqual(len(self.data["verdicts"])
                         + len(self.data["pairs_unreachable"]),
                         self.data["pairs"])


class TestAccountAfterR41(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load("acct_r41", ACCOUNT)

    def test_host_absent_classes_are_marked(self):
        data = self.mod.account()
        by_cls = {r["class"]: r for r in data["rows"] if r["state"] == "nyi"}
        for cls in ("CondBoussinesqBaseTemp", "CondMapForStructure", "MapCond"):
            self.assertIn(cls, by_cls)
            self.assertTrue(by_cls[cls].get("host_interface_absent"),
                            cls + " 应带宿主无接口证据")
            self.assertIn("DISP_E_UNKNOWNNAME", by_cls[cls]["reason"])

    def test_totals_unchanged_and_complete(self):
        data = self.mod.account()
        self.assertEqual(data["counts"]["total"], 41)
        self.assertEqual(data["counts"]["verdict"]
                         + data["counts"]["nyi"], 41)

    def test_committed_account_has_same_verdict_count(self):
        if not ACCOUNT_JSON.is_file():
            raise unittest.SkipTest("account json missing")
        saved = json.loads(ACCOUNT_JSON.read_text(encoding="utf-8"))
        live = self.mod.account()
        self.assertGreaterEqual(live["counts"]["verdict"],
                                saved["counts"]["verdict"])


if __name__ == "__main__":
    unittest.main()
