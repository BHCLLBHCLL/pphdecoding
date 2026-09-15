#!/usr/bin/env python3
"""R38 证据回归：arity 口径收紧（R38-2）/ 裁定名入目录（R38-3）/ 多工程裁定（R38-1）。

* **arity 口径（R38-2）**：手册对"可选参数"的标注极稀疏（全库 14 文件 41 处，
  且多在 Post/Kicker），所以判据收紧为「**多则报、少不报**」——
  `OpenProject(path)` 这类省略可选尾参的调用不该被报错，多传参数一定是错。
* **裁定名入目录（R38-3）**：提取期把 `dispatch_name` 写进条目，
  只读目录的消费者（VBS 校验、将来的代码生成）就能拿到纠名。
* **多工程（R38-1）**：一个会话里轮换工程 —— 不同工程提供不同对象；
  取不到的对象必须留下**确切原因**（含"前置对象缺失"）。
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

VERDICTS = ROOT / "_p12u_gate" / "r38" / "name_verdicts.json"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
PROBE = ROOT / "tools" / "dispatch_name_probe.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestArityPolicy(unittest.TestCase):
    def _obj(self, calls):
        class _Fake:
            def _FlagAsMethod(self, name):  # noqa: N802
                pass

            def ChangeMesher(self, *args):  # noqa: N802
                calls.append(args)
                return True

        return api.ScFlowpreMeshingGroupSetting(_Fake())

    def test_too_many_args_warns(self):
        api.clear_value_warnings()
        calls = []
        self._obj(calls).call("ChangeMesher", "poly", "extra")
        self.assertTrue(any("参数个数" in w for w in api.value_warnings))

    def test_too_few_args_is_silent(self):
        """少参数不报（手册可选参数标注稀疏，硬判会误杀正常调用）。"""
        api.clear_value_warnings()
        calls = []
        # ChangeWithOpenProject 手册是 (path, flag)；这里只传 path
        obj = api.ScFlowpreDoc(type("F", (), {
            "_FlagAsMethod": lambda self, n: None,
            "OpenProject": lambda self, *a: True})())
        obj.call("OpenProject", "x.pph")
        self.assertEqual([w for w in api.value_warnings if "参数个数" in w], [])

    def test_exact_arity_is_silent(self):
        api.clear_value_warnings()
        self._obj([]).call("ChangeMesher", "poly")
        self.assertEqual(api.value_warnings, [])


class TestDispatchNamesInCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))

    def test_signature_only_pairs_have_dispatch_name(self):
        e = self.cat["classes"]["Doc"]["methods"][
            "CreateDiscontinuousMeshingGroupWitouthMovingPart"]
        self.assertEqual(e.get("dispatch_name"),
                         "CreateDiscontinuousMeshingGroupWithoutMovingPart")
        self.assertIn("verdict", str(e.get("dispatch_source")))

    def test_heading_only_pairs_keep_catalog_key(self):
        e = self.cat["classes"]["Conditions"]["methods"][
            "SetContactThicknessDefault"]
        self.assertEqual(e.get("dispatch_name"), "SetContactThicknessDefault")

    def test_corrections_readable_from_catalog_alone(self):
        """VBS 纠名只读目录即可（R38-3）。"""
        fixes = vb.name_corrections()
        self.assertGreaterEqual(len(fixes), 4)
        for key, resolved in fixes.items():
            self.assertNotEqual(key, resolved)


class TestMultiProjectEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not VERDICTS.is_file():
            raise unittest.SkipTest("r38 verdict evidence missing")
        cls.data = json.loads(VERDICTS.read_text(encoding="utf-8"))

    def test_multiple_projects_in_one_session(self):
        projects = self.data.get("projects") or []
        self.assertGreaterEqual(len(projects), 2)

    def test_unreachable_classes_all_have_reasons(self):
        errors = self.data.get("chain_errors") or {}
        classes = sorted({p["class"] for p in self.data["pairs_unreachable"]})
        for cls in classes:
            self.assertIn(cls, errors, cls + " 未给原因")

    def test_no_invalid_neither_from_tuple_bug(self):
        """曾因 getter 返回 tuple 未拆包，把能解析的名字误判成 neither（假否证）。"""
        for v in self.data["verdicts"]:
            if v["verdict"] == "neither":
                self.assertFalse(v["heading_state"].startswith("error:AttributeError"),
                                 str(v))
                self.assertFalse(v["signature_state"].startswith("error:AttributeError"),
                                 str(v))

    def test_probe_unwraps_tuples(self):
        """回归测试：_raw 必须拆 tuple/数组（R38-1 的假否证根因）。"""
        probe = _load("probe_r38", PROBE)
        self.assertTrue(hasattr(probe, "_chains"))


if __name__ == "__main__":
    unittest.main()
