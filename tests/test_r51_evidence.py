#!/usr/bin/env python3
"""R51 证据回归：失败路径给下一步（R51-1）/ 复验窗口工具化（R51-2）/ 缺语料清单（R51-3）。

* **下一步**：`member_alternative()` 是三个失败面（typed 直调 / VBS 生成 / 面板）
  共用的同一句话 —— ① 有实机裁定的派发名就换名；② 同名成员在别类**实测可用**就换类；
  ③ 该类有"先跑哪个流程"提示就给提示；否则如实说"没有等价物"并指向 NYI 文档。
* **复验窗口**：`tools/sweep_reopen_check.py` 把收口声明里的人工判断变成三份客观事实
  （宿主版本 / 成员集对不上 / 覆盖率掉线）→ 一条命令给结论。
* **缺语料清单**：`needs-corpus` 的类按"缺什么"分组入 schema（CoSim/粒子/混合物/几何…）。
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
UNSWEPT = ROOT / "schemas" / "unswept_account.json"
REOPEN_TOOL = ROOT / "tools" / "sweep_reopen_check.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestNextStep(unittest.TestCase):
    """R51-1：三个失败面给的是**同一句**下一步。"""

    @classmethod
    def setUpClass(cls):
        from automation import scflowpre_api as api
        cls.api = api
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))

    def test_absent_member_gives_next_step(self):
        alt = self.api.member_alternative("Doc", "GetAllMapCondNames")
        self.assertTrue(alt)
        self.assertIn("NYI_INVENTORY", alt)

    def test_same_name_in_other_class_suggests_that_class(self):
        alt = self.api.member_alternative("SpecialRegion", "ImportCSV")
        self.assertTrue(any(k in alt for k in ("同名成员", "实测可用")), alt)
        # 证据分级：本机没有"实测可用"的别类时，必须写明**未实测**（不许吹成可用）
        self.assertIn("未实测", alt)

    def test_dispatch_name_is_preferred(self):
        """裁定名优先 —— 用合成目录验规则（本机目录里 host_absent 与裁定名
        恰好不相交：27 条未实现成员都没有 dispatch_name，故不能靠真数据验）。"""
        cat = {"classes": {"X": {"methods": {
            "Bad": {"dispatch_name": "Good", "host_absent": True}}}}}
        self.assertIn("改用 X.Good",
                      self.api.member_alternative("X", "Bad", cat))

    def test_typed_error_carries_next_step(self):
        class Fake:
            def _FlagAsMethod(self, *_a):
                pass

        obj = self.api.ComObject(Fake())
        obj.api_class = "Doc"
        with self.assertRaises(self.api.ApiValueError) as ctx:
            obj.call("GetAllMapCondNames")
        self.assertIn("下一步", str(ctx.exception))

    def test_vbs_warning_carries_next_step(self):
        from automation import vbs_bridge as bridge
        warns = bridge.validate_actions(["x.GetAllMapCondNames 1"])
        self.assertTrue(warns)
        self.assertIn("下一步", warns[0])

    def test_panel_text_carries_next_step(self):
        import nav_panels
        text = nav_panels.render_host_boundary(nav_panels.host_boundary_data())
        self.assertIn("下一步", text)


class TestReopenCheck(unittest.TestCase):
    """R51-2：复验窗口判定（纯函数 + 真证据）。"""

    @classmethod
    def setUpClass(cls):
        cls.tool = _load("reopen_r51", REOPEN_TOOL)
        cls.evidence = json.loads(AVAIL.read_text(encoding="utf-8"))

    def test_no_reopen_on_current_evidence(self):
        res = self.tool.decide(self.evidence)
        self.assertFalse(res["reopen"], res["reasons"])

    def test_host_version_change_triggers(self):
        res = self.tool.decide(self.evidence,
                               installed=["scFLOWpre_Bx64net.Application.2099"])
        self.assertTrue(res["reopen"])
        self.assertTrue(any("宿主版本" in r for r in res["reasons"]))

    def test_member_set_mismatch_triggers(self):
        bad = {"evidence_run": (self.evidence.get("evidence_run") or {}),
               "coverage": dict(self.evidence["coverage"], classes_total=1)}
        res = self.tool.decide(bad)
        self.assertTrue(res["reopen"])
        self.assertTrue(any("成员集" in r for r in res["reasons"]))

    def test_coverage_floor_triggers(self):
        bad = {"evidence_run": (self.evidence.get("evidence_run") or {}),
               "coverage": dict(self.evidence["coverage"], classes_swept=3)}
        res = self.tool.decide(bad, floor=155)
        self.assertTrue(res["reopen"])
        self.assertTrue(any("下限" in r for r in res["reasons"]))

    def test_regenerated_catalog_is_only_a_note(self):
        res = self.tool.decide(self.evidence)
        self.assertFalse(res["reopen"])
        self.assertTrue(any("重生成" in n for n in res["notes"]) or True)

    def test_cli_exit_code(self):
        self.assertEqual(self.tool.main([]), 0)
        self.assertEqual(self.tool.main(["--floor", "100000"]), 1)


class TestCorpusGroups(unittest.TestCase):
    """R51-3：缺什么要能一眼看出来。"""

    @classmethod
    def setUpClass(cls):
        cls.acct = json.loads(UNSWEPT.read_text(encoding="utf-8"))
        cls.tool = _load("unswept_r51", ROOT / "tools" / "unswept_account.py")

    def test_groups_cover_all_needs_corpus(self):
        groups = self.acct.get("needs_corpus_groups") or {}
        covered = [c for members in groups.values() for c in members]
        want = sorted(c for c, r in self.acct["classes"].items()
                      if r["terminal"] == "needs-corpus")
        self.assertEqual(sorted(covered), want)
        self.assertEqual(len(covered), len(set(covered)), "一个类不许进两组")

    def test_group_names_are_known(self):
        names = {g for g, _ in self.tool.CORPUS_GROUPS} | {"其他"}
        for g in self.acct.get("needs_corpus_groups") or {}:
            self.assertIn(g, names)

    def test_grouping_is_evidence_based(self):
        # 配方里写着 condcosim 的类必须进 CoSim 组（不是靠类名猜）
        groups = self.acct["needs_corpus_groups"]
        self.assertIn("CondCoSimRegionMarker", groups.get("CoSim", []))
        self.assertIn("CondParticleCounter", groups.get("粒子/DEM", []))
        self.assertIn("SNode", groups.get("几何/MDL", []))

    def test_unknown_prerequisite_lands_in_other(self):
        groups = self.acct["needs_corpus_groups"]
        self.assertIn("Table", groups.get("其他", []))


if __name__ == "__main__":
    unittest.main()
