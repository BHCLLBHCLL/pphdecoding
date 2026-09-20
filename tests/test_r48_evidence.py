#!/usr/bin/env python3
"""R48 证据回归：命名片段扩面（R48-1）/ 配方可信度入目录（R48-2）/ typed 直调前置拦截（R48-3）。

* **片段**：手册没给实例配方、名字家族也猜不中的类，靠**命名片段**找取法 ——
  实测命名习惯：`IS???→S???` / `IV???→V???`（`ISFace←Doc.GetSelectedSFaces`、
  `IVFace←Doc.GetSelectedVFaces`）、`Cond<X>→GetCond<X>Condition`、尾部
  `View/Param` 常省略；
* **配方可信度**：验身否掉的类在目录里标 `recipe_unreliable`（附证据），
  读目录的人不必照抄再撞一次墙；
* **前置拦截**：`ComObject.call` 与 VBS 生成**共用同一判据**
  （`scflowpre_api.unambiguous_host_absent()`）—— 宿主未实现的成员在调用前就报可读错误。
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

AVAIL = ROOT / "schemas" / "host_member_availability.json"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
PROBE = ROOT / "tools" / "dispatch_name_probe.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestStemCandidates(unittest.TestCase):
    """R48-1：片段要找得到手册里真实存在的取法名。"""

    @classmethod
    def setUpClass(cls):
        cls.probe = _load("probe_r48", PROBE)
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.held = {"Doc": "Doc", "Conditions": "Conditions",
                    "FaceRegion": "FaceRegion"}

    def test_is_iv_prefix_maps_to_s_v(self):
        self.assertIn("sface", self.probe._class_stems("ISFace"))
        self.assertIn("vface", self.probe._class_stems("IVFace"))
        self.assertIn("sedge", self.probe._class_stems("ISEdge"))

    def test_cond_suffix_and_view_stripping(self):
        self.assertIn("outputpclfile",
                      self.probe._class_stems("CondOutputPclFile"))
        self.assertIn("crosssection", self.probe._class_stems(
            "CrossSectionView"))

    def test_short_stems_refused(self):
        for stem in self.probe._class_stems("ISFace"):
            self.assertGreaterEqual(len(stem), 4)

    def test_candidates_hit_real_accessors(self):
        got = {p["how"] for p in self.probe.stem_candidates(
            self.cat, "IVFace", self.held)}
        self.assertIn("stem:Doc.GetSelectedVFaces", got)
        got2 = {p["how"] for p in self.probe.stem_candidates(
            self.cat, "CondOutputPclFile", self.held)}
        self.assertIn("stem:Conditions.GetCondOutputPclFileCondition", got2)

    def test_getters_rank_before_actions(self):
        plans = self.probe.stem_candidates(self.cat, "ISEdge", self.held)
        self.assertTrue(plans)
        self.assertTrue(plans[0]["member"].lower().startswith(
            ("get", "query")), plans[0])


class TestRecipeReliability(unittest.TestCase):
    """R48-2：验身否掉的取法要在目录里留痕。"""

    @classmethod
    def setUpClass(cls):
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.data = json.loads(AVAIL.read_text(encoding="utf-8"))

    def test_rejected_classes_are_marked(self):
        cov = self.data["coverage"]
        rejected = {str(x).partition(" <- ")[0]
                    for x in (cov.get("identity_rejected") or [])}
        rejected |= set(cov.get("swept_suspect") or {})
        marked = {c for c, i in self.cat["classes"].items()
                  if i.get("recipe_unreliable")}
        self.assertTrue(rejected, "本机应有验身否掉的取法")
        self.assertTrue(rejected.issubset(marked),
                        sorted(rejected - marked))

    def test_marks_carry_evidence(self):
        for cls, info in self.cat["classes"].items():
            if not info.get("recipe_unreliable"):
                continue
            ev = info.get("recipe_unreliable_evidence")
            self.assertTrue(ev, cls)
            self.assertTrue(all(str(x).strip() for x in ev), cls)


class TestTypedPrecheck(unittest.TestCase):
    """R48-3：typed 直调在**调用前**拦下宿主未实现的成员。"""

    @classmethod
    def setUpClass(cls):
        from automation import scflowpre_api as api
        cls.api = api

    def test_one_predicate_for_both_surfaces(self):
        from automation import vbs_bridge as bridge
        self.assertEqual(self.api.unambiguous_host_absent(),
                         bridge.host_absent_methods())

    def test_absent_set_is_unambiguous(self):
        absent = self.api.unambiguous_host_absent()
        self.assertIn("GetAllMapCondNames", absent)
        self.assertNotIn("ImportCSV", absent)

    def test_call_raises_readable_error(self):
        class Fake:
            def _FlagAsMethod(self, *_a):
                pass

        # 判据挂在**目录类名**上（typed 包装的 api_class），不是被包对象的属性
        obj = self.api.ComObject(Fake())
        obj.api_class = "Doc"
        with self.assertRaises(self.api.ApiValueError) as ctx:
            obj.call("GetAllMapCondNames")
        msg = str(ctx.exception)
        self.assertIn("宿主未实现", msg)
        self.assertIn("DISP_E_UNKNOWNNAME", msg)
        self.assertIn("host_absent", msg)

    def test_normal_member_not_blocked(self):
        class Fake:
            def GetProjectSetting(self):
                return "ok"

            def _FlagAsMethod(self, *_a):
                pass

        obj = self.api.ComObject(Fake())
        obj.api_class = "Doc"
        self.assertEqual(obj.call("GetProjectSetting"), "ok")


if __name__ == "__main__":
    unittest.main()
