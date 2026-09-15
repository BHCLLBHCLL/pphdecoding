#!/usr/bin/env python3
"""R37 证据回归：链式实例裁定（R37-1）/ VBS 名字纠错（R37-2）/ 参数个数校验（R37-3）。

* 裁定表是**单调合并**的（取不到实例的类保留上次结论），所以"覆盖数只增不减"；
  未覆盖的类必须给出**确切原因**（链式 getter 抛错 / 返回空 / 需要更长的链）；
* VBS 生成通道按裁定表纠名：4 处「只有签名名能解析」的对，用目录键发出去必然失败；
* 参数个数按手册签名判（`(path, flag)` → 2；`SetX flag` → 1；`GetParam(key value)` → 2）。
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import scflowpre_api as api  # noqa: E402
from automation import vbs_bridge as vb  # noqa: E402

PROBE = ROOT / "tools" / "dispatch_name_probe.py"
VERDICTS = ROOT / "_p12u_gate" / "r37" / "name_verdicts.json"
TABLE = ROOT / "schemas" / "name_verdicts.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestChainVerdicts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not VERDICTS.is_file():
            raise unittest.SkipTest("r37 verdict evidence missing")
        cls.data = json.loads(VERDICTS.read_text(encoding="utf-8"))

    def test_coverage_grew_and_accounts_for_all_pairs(self):
        n = len(self.data["verdicts"])
        self.assertGreaterEqual(n, 32)
        self.assertEqual(n + len(self.data["pairs_unreachable"]),
                         self.data["pairs"])

    def test_chain_obtained_special_region(self):
        via = self.data.get("obtained_via") or {}
        self.assertIn("SpecialRegion", via)
        self.assertTrue(str(via["SpecialRegion"]).startswith("chain:"))

    def test_uncovered_classes_have_concrete_reasons(self):
        """R37-1 的验收：未覆盖要么补上，要么**给出确切原因**。"""
        errors = self.data.get("chain_errors") or {}
        classes = sorted({p["class"] for p in self.data["pairs_unreachable"]})
        self.assertTrue(classes)
        for cls in classes:
            self.assertIn(cls, errors, cls + " 未给原因")
            reason = str(errors[cls])
            self.assertGreater(len(reason), 20, reason)
            # 两种形态都算"确切原因"：链式调用报错（"-> 异常/返回空"）
            # 或前置对象缺失（"前置对象 X 未取到"）
            self.assertTrue("->" in reason or "前置" in reason, reason)

    def test_tally_consistent(self):
        tally: dict = {}
        for v in self.data["verdicts"]:
            tally[v["verdict"]] = tally.get(v["verdict"], 0) + 1
        self.assertEqual(tally, self.data["tally"])


class TestVbsNameCorrection(unittest.TestCase):
    def setUp(self):
        vb.clear_value_warnings()

    def test_corrections_come_from_verdict_table(self):
        fixes = vb.name_corrections()
        self.assertIn("CreateDiscontinuousMeshingGroupWitouthMovingPart", fixes)
        self.assertEqual(
            fixes["CreateDiscontinuousMeshingGroupWitouthMovingPart"],
            "CreateDiscontinuousMeshingGroupWithoutMovingPart")

    def test_vbs_with_typo_name_warns(self):
        acts = ['Doc_.CreateDiscontinuousMeshingGroupWitouthMovingPart "g"']
        got = vb.validate_actions(acts)
        self.assertTrue(any("应改用" in w for w in got), got)

    def test_vbs_with_correct_name_is_clean(self):
        acts = ['Doc_.CreateDiscontinuousMeshingGroupWithoutMovingPart "g"']
        self.assertEqual(vb.validate_actions(acts), [])

    def test_strict_mode_blocks_typo_name(self):
        with self.assertRaises(api.ApiValueError):
            vb.build_vbs(
                ['Doc_.CreateDiscontinuousMeshingGroupWitouthMovingPart "g"'],
                strict_values=True)


class TestArity(unittest.TestCase):
    def test_parse_shapes(self):
        self.assertEqual(api.signature_arity("retval=doc.OpenProject(path, flag)"), 2)
        self.assertEqual(api.signature_arity("meshset.SetTinyFaceRelativeFlag flag"), 1)
        self.assertEqual(api.signature_arity("array=condcosim.GetParam(key value)"), 2)
        self.assertEqual(api.signature_arity("retval=meshset.GetMesher()"), 0)
        self.assertIsNone(api.signature_arity(None))

    def _fake(self, calls):
        """假 COM 对象：`*args` 泛收 —— 参数个数校验是要在**派发前**告警，
        不该由替身抛 TypeError 来"实现"。"""
        class _Fake:
            def _FlagAsMethod(self, name):  # noqa: N802
                pass

            def ChangeMesher(self, *args):  # noqa: N802
                calls.append(args)
                return True

        return _Fake()

    def test_wrong_arity_warns_but_dispatches(self):
        api.clear_value_warnings()
        calls = []
        obj = api.ScFlowpreMeshingGroupSetting(self._fake(calls))
        obj.call("ChangeMesher", "poly", "extra")
        self.assertTrue(any("参数个数" in w for w in api.value_warnings),
                        api.value_warnings)
        self.assertEqual(calls, [("poly", "extra")])   # 默认照常派发

    def test_wrong_arity_blocks_in_strict(self):
        api.clear_value_warnings()
        calls = []
        obj = api.ScFlowpreMeshingGroupSetting(self._fake(calls))
        obj.strict_values = True
        with self.assertRaises(api.ApiValueError):
            obj.call("ChangeMesher", "poly", "extra")
        self.assertEqual(calls, [])

    def test_right_arity_is_silent(self):
        api.clear_value_warnings()
        calls = []
        obj = api.ScFlowpreMeshingGroupSetting(self._fake(calls))
        obj.call("ChangeMesher", "poly")
        self.assertEqual(api.value_warnings, [])
        self.assertEqual(calls, [("poly",)])


if __name__ == "__main__":
    unittest.main()
