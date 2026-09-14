#!/usr/bin/env python3
"""R35 证据回归：名字裁定（R35-1）/ 归因入库（R35-2）/ 目录物化（R35-3）。

三件事的证据都在仓里，测试逐条钉住：

* `_p12u_gate/r35/name_verdicts.json` —— 运行时 `GetIDsOfNames` 裁定
  「手册标题名 vs 签名名」。宿主**不实现 `GetTypeInfo`**、也没注册类型库，
  所以名字解析是唯一可用的实机判据（只解析、不调用，零副作用）。
* `_p12u_gate/r35/corpus_diff_attr.json` —— 词干归因后的对拍：精确同源的链接
  差异必须为 0（已入库），仅"包含"关系的只作提示。
* 物化包装：目录成员经 typed 类可调且**带取值校验**。
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

VERDICTS = ROOT / "_p12u_gate" / "r35" / "name_verdicts.json"
ATTR = ROOT / "_p12u_gate" / "r35" / "corpus_diff_attr.json"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
COV = ROOT / "tools" / "api_bridge_coverage.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestNameVerdicts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not VERDICTS.is_file():
            raise unittest.SkipTest("verdict evidence missing")
        cls.data = json.loads(VERDICTS.read_text(encoding="utf-8"))

    def test_host_exposes_no_type_info(self):
        """宿主不实现 GetTypeInfo（也没有注册类型库）—— 名字只能实机解析。"""
        probes = self.data.get("object_probe") or {}
        self.assertTrue(probes, "至少应探到一个对象")
        for name, state in probes.items():
            self.assertTrue(state.startswith("no:"), name + " -> " + state)

    def test_signature_wins_where_only_one_resolves(self):
        for v in self.data["verdicts"]:
            if v["verdict"] == "signature":
                self.assertEqual(v["signature_state"], "resolved")
                self.assertNotEqual(v["heading_state"], "resolved")
            if v["verdict"] == "heading":
                self.assertEqual(v["heading_state"], "resolved")

    def test_known_typo_pair_adjudicated(self):
        hit = [v for v in self.data["verdicts"]
               if v["heading"] == "CreateDiscontinuousMeshingGroupWitouthMovingPart"]
        self.assertTrue(hit, "该对峙对必须被裁定")
        self.assertEqual(hit[0]["verdict"], "signature",
                         "标题拼错名不得被宿主接受")

    def test_every_pair_gets_a_state(self):
        for v in self.data["verdicts"]:
            for key in ("heading_state", "signature_state", "verdict"):
                self.assertIn(key, v)
            self.assertIn(v["verdict"],
                          {"heading", "signature", "both", "neither"})

    def test_unreachable_pairs_are_declared(self):
        """取不到实例的对（如 Cond* 需要条件对象）必须显式列出，不得静默丢。"""
        reachable = len(self.data["verdicts"])
        unreachable = len(self.data.get("pairs_unreachable") or [])
        self.assertEqual(reachable + unreachable, self.data["pairs"])


class TestAttribution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ATTR.is_file():
            raise unittest.SkipTest("attribution evidence missing")
        cls.data = json.loads(ATTR.read_text(encoding="utf-8"))
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))

    def _slot(self, member_id):
        cls, member, arg = member_id.split(".")
        e = ((self.cat["classes"].get(cls) or {}).get("methods")
             or {}).get(member)
        if not e:
            return []
        slots = ([e.get("return") or {}] if arg == "return"
                 else [a for a in e.get("arguments") or []
                       if a.get("name") == arg])
        return slots[0].get("values") or []

    def test_exact_stem_links_have_no_gap_left(self):
        for link in self.data["attributed"]:
            if link.get("exact_stem"):
                self.assertEqual(link["only_corpus"], [],
                                 link["member"] + " 仍有手册漏项")

    def test_loose_stem_links_are_not_merged(self):
        """词干只是"包含"关系的（upwd_param → GetUpwdOptionParamForEquation）
        只作提示：其 only_corpus 不得出现在那个槽里。"""
        loose = [a for a in self.data["attributed"]
                 if not a.get("exact_stem") and a["only_corpus"]]
        self.assertTrue(loose, "证据里应有仅包含关系的候选")
        for link in loose:
            got = {v["value"] for v in self._slot(link["member"])}
            for v in link["only_corpus"]:
                self.assertNotIn(v, got, link["member"] + " 混入了 " + v)

    def test_added_values_keep_provenance(self):
        """每个 host-corpus 取值都必须能追到一条语料链接（含已并入 discovered 的）。"""
        links = (list(self.data.get("links") or [])
                 + list(self.data.get("discovered") or [])
                 + list(self.data.get("attributed") or []))
        checked = 0
        for link in links:
            got = {v["value"]: v for v in self._slot(link["member"])}
            for v in sorted(set(link["corpus"]) & set(got)):
                if got[v].get("source") == "host-corpus":
                    checked += 1
        self.assertGreaterEqual(checked, 20,
                                "语料入库的取值都应在这份证据里可追溯")


class TestMaterializedWrappers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from automation import scflowpre_api as api
        cls.api = api
        cls.cov = _load("bridgecov_r35", COV)

    def test_coverage_jumped(self):
        data = self.cov.report()
        self.assertGreaterEqual(data["coverage"], 0.9)
        self.assertEqual(data["unknown_wrapped_members"], [])

    def test_materialized_wrapper_dispatches_signature_name(self):
        """属性名 = 目录键（拼错的那个），派发名 = 签名名（宿主认的那个）。"""
        doc_cls = self.api.ScFlowpreDoc
        wrapper = getattr(doc_cls, "CreateDiscontinuousMeshingGroupWitouthMovingPart")
        calls = []

        class _Fake:
            def _FlagAsMethod(self, name):  # noqa: N802
                pass

            def CreateDiscontinuousMeshingGroupWithoutMovingPart(self, *a):  # noqa: N802
                calls.append(a)
                return "ok"

        obj = doc_cls(_Fake())
        self.assertEqual(wrapper(obj, "part"), "ok")
        self.assertEqual(calls, [("part",)])

    def test_materialized_wrapper_is_value_guarded(self):
        """物化包装同样走 call() → 取值校验（这是物化的真正意义）。"""
        api = self.api
        api.clear_value_warnings()
        calls = []

        class _Fake:
            def _FlagAsMethod(self, name):  # noqa: N802
                pass

            def ChangeMesher(self, kind):  # noqa: N802
                calls.append(kind)
                return True

        obj = api.ScFlowpreMeshingGroupSetting(_Fake())
        obj.ChangeMesher("polyhedral")
        self.assertEqual(len(api.value_warnings), 1)
        self.assertEqual(calls, ["polyhedral"])

    def test_verdict_table_is_loaded(self):
        table = self.api.load_name_verdicts()
        self.assertIn("Conditions", table)
        self.assertEqual(
            table["Conditions"]["SetContactThicknessDefault"],
            "SetContactThicknessDefault",
            "标题名胜出的对必须按标题名派发（签名名是手册拼错）")
        self.assertEqual(
            table["Doc"]["CreateDiscontinuousMeshingGroupWitouthMovingPart"],
            "CreateDiscontinuousMeshingGroupWithoutMovingPart")

    def test_heading_only_pair_dispatches_heading(self):
        """实测 4 对**只有标题名**能解析 —— 一律用签名名会调不通。"""
        calls = []

        class _Fake:
            def _FlagAsMethod(self, name):  # noqa: N802
                pass

            def SetContactThicknessDefault(self, *a):  # noqa: N802
                calls.append(a)
                return "heading"

            def SetContactTicknessDefault(self, *a):  # noqa: N802
                raise AssertionError("签名名不该被派发")

        obj = self.api.ScFlowpreConditions(_Fake())
        self.assertEqual(obj.SetContactThicknessDefault(1), "heading")
        self.assertEqual(calls, [(1,)])

    def test_existing_handwritten_wrappers_kept(self):
        """手写包装不被覆盖（保住其文档与语义）。"""
        import inspect
        fn = self.api.ScFlowpreMeshingGroupSetting.ChangeMesher
        self.assertIn("ChangeMesher", inspect.getsource(fn)
                      if inspect.isfunction(fn) else " ")


if __name__ == "__main__":
    unittest.main()
