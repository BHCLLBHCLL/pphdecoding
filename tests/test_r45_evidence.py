#!/usr/bin/env python3
"""R45 证据回归：自动配方扩面（R45-1）/ 提示进产品面（R45-2）/ 普查常规入口（R45-3）。

* **扩面**：拿"目录里声明在已持有宿主上的 `Create*/Get*/Query*`" + "类级
  `instance` 配方"自动生成候选，参数按阶梯退让 → 覆盖 84 类 → ≥110 类；
  配**验身**（独有成员解析率 ≥ 半数）挡住"配方写的是别的类"（CondOversetGap
  那页给的 CreateCondSpray）；
* **产品面**：`automation.scflowpre_api.object_hints()` / `host_absent_members()`
  + `docs/NYI_INVENTORY.md` 的自动生成节（同一份证据，三种可查面）；
* **入口**：`tools/host_member_sweep.py` 一条命令复算覆盖率（`--report-only`
  不起宿主）。
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
SWEEP_TOOL = ROOT / "tools" / "host_member_sweep.py"
NYI_DOC = ROOT / "docs" / "NYI_INVENTORY.md"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestPlannerOffline(unittest.TestCase):
    """自动配方生成是**纯函数**：不起宿主就能验它给的路子对不对。"""

    @classmethod
    def setUpClass(cls):
        cls.probe = _load("probe_r45", PROBE)
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.held = {"Doc": "Doc", "Conditions": "Conditions",
                    "MeshingGroup": "MeshingGroup",
                    "Application": "Kicker.Application"}

    def test_recipe_parsed_from_manual_page(self):
        # 手册页实例行：Set dtsr = conditions.CreateCondDTSR("name")
        rec = self.probe.recipe_plan(self.cat, "CondDTSR", self.held)
        self.assertIsNotNone(rec, "印刷体引号不该让配方整条作废")
        self.assertEqual(rec[1], "CreateCondDTSR")
        self.assertEqual(rec[2], ("R45CondDTSR",))

    def test_recipe_keeps_at_name_argument(self):
        rec = self.probe.recipe_plan(self.cat, "CondALECancel", self.held)
        self.assertEqual(rec[1], "QueryConditionByName")
        self.assertEqual(rec[2], ("@ALECancel",))

    def test_recipe_substitutes_progid(self):
        rec = self.probe.recipe_plan(
            self.cat, "Kicker.ApplicationLaunchSetting", self.held)
        # 该类自身页无配方 → 由签名参数名推（GetApplicationLaunchSetting(ProgID)）
        plans = self.probe.auto_plans(
            self.cat, "Kicker.ApplicationLaunchSetting", self.held)
        self.assertIn("Application", [p["host"] for p in plans])
        self.assertTrue(any(p["member"] == "GetApplicationLaunchSetting"
                            and p["args"] == (self.probe.PROGID,)
                            for p in plans), [p["args"] for p in plans])
        self.assertIsNone(rec)   # 无实例行 → 不猜

    def test_recipe_refuses_unknown_placeholder(self):
        # Prep: SNode 的配方是 Set coord_part = snode.Get...LinkedToMesh(id)
        # snode 不在宿主别名表 → 放弃（不猜）；占位符 id 也不认
        self.assertIsNone(self.probe.recipe_plan(self.cat, "SNode", self.held))

    def test_plans_prefer_recipe_then_catalog(self):
        plans = self.probe.auto_plans(self.cat, "Table", self.held)
        self.assertEqual(plans[0]["how"].split(":")[0], "catalog")
        hows = [p["how"] for p in plans]
        self.assertTrue(any(h.startswith("catalog:Doc.") for h in hows))

    def test_identity_guard_catches_wrong_class(self):
        class Fake:
            def __init__(self, names):
                self.names = set(names)

        def resolve(obj, name):
            return "resolved" if name in obj.names else "unknown_name"

        ok, detail = self.probe.identity_ok(
            Fake(["a", "b", "c", "d", "e"]), ["a", "b", "c", "x", "y"], resolve)
        self.assertTrue(ok)
        self.assertEqual(detail["resolved"], 3)
        ok2, _ = self.probe.identity_ok(Fake(["a"]), ["a", "b", "c", "x", "y"],
                                        resolve)
        self.assertFalse(ok2, "别人家的对象必须被拦下（假否证的源头）")
        # 目录里没有独有成员的类（如 ParticleRegion 空页）→ 无从验身，放行
        ok3, d3 = self.probe.identity_ok(Fake([]), [], resolve)
        self.assertTrue(ok3)
        self.assertEqual(d3["sample"], 0)

    def test_distinctive_members_are_unique(self):
        index = self.probe.member_name_index(self.cat)
        sample = self.probe.distinctive_members(self.cat, "CondDTSR", index)
        self.assertTrue(sample)
        for name in sample:
            self.assertEqual(index[name], 1, name + " 不是该类独有")

    def test_sweep_class_verdict_blocks_wrong_object(self):
        # 实测事故：会话 Application 被别名成 Kicker.Application → 9 个成员里
        # 8 个 unknown_name。整类未知过半必须判 suspect（整类不记）
        bad = {"a": "unknown_name", "b": "unknown_name", "c": "unknown_name",
               "d": "resolved", "e": "unknown_name"}
        self.assertEqual(self.probe.sweep_class_verdict(bad), "suspect")
        good = {"a": "resolved", "b": "resolved", "c": "resolved",
                "d": "resolved", "e": "unknown_name"}
        self.assertEqual(self.probe.sweep_class_verdict(good), "ok")
        self.assertEqual(self.probe.sweep_class_verdict({}), "empty")
        # 成员太少就没法验身（ParticleRegion 这类空手册页）→ 不判 suspect
        self.assertEqual(
            self.probe.sweep_class_verdict({"a": "unknown_name"}), "ok")

    def test_arg_ladder_covers_multi_and_zero_arg(self):
        # 阶梯要同时覆盖多参创建器与零参 getter（顺序即优先级）
        ladder = self.probe.arg_ladder("R45X")
        self.assertEqual(ladder[0], ("R45X",))
        self.assertIn(("R45X", 0, 0), ladder)
        self.assertIn((), ladder)
        self.assertEqual(len(ladder), 6)

    def test_no_backticks_in_planner_names(self):
        # 防御：候选名必须是合法标识符（否则宿主调用必然抛 TypeError）
        for name in self.probe._candidate_members("CondCoSimRegionMarker"):
            self.assertTrue(name.isidentifier(), name)


class TestExpansionEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not AVAIL.is_file():
            raise unittest.SkipTest("availability evidence missing")
        cls.data = json.loads(AVAIL.read_text(encoding="utf-8"))
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))

    def test_coverage_reaches_r45_target(self):
        cov = self.data["coverage"]
        self.assertGreaterEqual(cov["classes_swept"], 110,
                                "R45-1 验收：覆盖类数 ≥110")
        self.assertGreaterEqual(cov["members_swept"], 3000)

    def test_buckets_still_partition(self):
        # 四桶互斥：已普查 / 取不到实例 / 取到但手册无成员 / 从未尝试
        cov = self.data["coverage"]
        self.assertEqual(cov["classes_swept"] + len(cov["empty_objects"])
                         + len(cov.get("no_member_classes") or [])
                         + len(cov["unswept_classes"]), cov["classes_total"])

    def test_swept_keys_are_catalog_classes(self):
        # ctx 键必须**原样**是目录类名：别名（Application → Kicker.Application）
        # 曾把 Kicker 启动器当成会话对象，凭假象刷出 8 条"宿主未实现"
        for cls in self.data["classes"]:
            self.assertIn(cls, self.cat["classes"], cls + " 不是目录类名")
        self.assertIn("Application", self.data["classes"],
                      "会话 Application 对象本身就是目录 Application 类")
        # R47：Kicker.* 改为**附着 Kicker 会话实测**取得 —— 可以进普查，但取得路径
        # 必须写明是 kicker:（否则就是拿会话对象冒充，正是 R45 修掉的那个假象）
        via = self.data["coverage"].get("obtained_via") or {}
        if "Kicker.Application" in self.data["classes"]:
            self.assertTrue(str(via.get("Kicker.Application", ""))
                            .startswith("kicker:"),
                            "Kicker.* 只能是实测取得")

    def test_suspect_classes_are_not_recorded(self):
        # 验身后置闸否掉的类：不得同时出现在普查结果里（宁可停在未普查）
        suspect = self.data["coverage"].get("swept_suspect") or {}
        for cls, detail in suspect.items():
            self.assertNotIn(cls, self.data["classes"], cls)
            self.assertGreater(detail["unknown"], detail["total"] / 2)

    def test_heading_name_fallback_did_not_mark_absent(self):
        # ClosedVolume.SelectFace：签名名 SetSelectFaces 不认、标题名认 →
        # 不许记成"宿主未实现"
        states = (self.data.get("availability") or {}).get("ClosedVolume") or {}
        self.assertEqual(states.get("SelectFace"), "resolved",
                         "派发名不通时要用成员键名再试一次")

    def test_auto_obtained_is_evidence_backed(self):
        cov = self.data["coverage"]
        auto = cov.get("auto_obtained") or {}
        self.assertTrue(auto, "本轮扩面必须留下配方来源")
        # 拿到对象的类必须落进"我们确实到过"的两个桶之一：有成员 → 普查；
        # 手册页零成员 → no_member（不算进覆盖率，但也不是"未普查"）
        reached = set(self.data["classes"]) | set(
            cov.get("no_member_classes") or [])
        for cls, how in auto.items():
            self.assertIn(cls, reached, cls + " 拿到了却没落桶")
            self.assertTrue(how, cls)
        # 验身否是**过程证据**：被否的类不得同时又进了普查
        for line in cov.get("identity_rejected") or []:
            cls = line.split(" <- ")[0]
            self.assertNotIn(cls, auto, cls + " 既被否又算取得，自相矛盾")

    def test_no_probe_errors_after_expansion(self):
        errs = [m for v in self.data["classes"].values()
                for m in (v.get("errors") or [])]
        self.assertEqual(errs, [], "扩面不得引入探针侧错误")

    def test_absent_entries_not_regressed(self):
        entries = [m for v in self.data["classes"].values()
                   for m in (v.get("unknown") or [])]
        self.assertGreaterEqual(len(entries), 16,
                                "扩面只允许把未实现成员记得更多")


class TestProductSurface(unittest.TestCase):
    """R45-2：提示与"宿主未实现"必须在**产品面**可查（API + 文档同源）。"""

    @classmethod
    def setUpClass(cls):
        from automation import scflowpre_api as api
        cls.api = api
        cls.data = json.loads(AVAIL.read_text(encoding="utf-8"))
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))

    def test_api_hints_match_evidence(self):
        hints = self.api.object_hints()
        self.assertEqual(hints, self.data["coverage"]["empty_hints"])
        # 提示表是**知识**（模块级 EMPTY_HINTS），证据里只列当轮真的空的类
        self.assertIn("PropItem", hints)
        self.assertIn("材料", hints["PropItem"])

    def test_api_host_absent_matches_catalog(self):
        absent = self.api.host_absent_members()
        n = sum(len(v) for v in absent.values())
        self.assertGreaterEqual(n, 16)
        got = {(c, m) for c, ms in absent.items() for m in ms}
        want = {(c, m) for c, info in self.cat["classes"].items()
                for kind in ("methods", "properties")
                for m, e in (info.get(kind) or {}).items()
                if e.get("host_absent")}
        self.assertEqual(got, want)

    def test_missing_evidence_does_not_crash(self):
        self.assertEqual(self.api.load_availability(
            ROOT / "schemas" / "___nope___.json"), {})
        self.assertEqual(self.api.object_hints(
            ROOT / "schemas" / "___nope___.json"), {})

    def test_nyi_doc_carries_host_boundary(self):
        text = NYI_DOC.read_text(encoding="utf-8")
        self.assertIn("宿主侧能力边界", text)
        self.assertIn("宿主未实现的成员", text)
        for cls, hint in self.data["coverage"]["empty_hints"].items():
            self.assertIn(cls, text)
            self.assertIn(hint, text)
        for cls, names in self.api.host_absent_members().items():
            self.assertIn(cls + " — " + " / ".join(names), text)


class TestSweepEntry(unittest.TestCase):
    """R45-3：一条命令复算覆盖率（--report-only 不起宿主）。"""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load("host_member_sweep", SWEEP_TOOL)
        cls.data = json.loads(AVAIL.read_text(encoding="utf-8"))

    def test_summarize_totals_match_evidence(self):
        s = self.mod.summarize(self.data)
        cov = self.data["coverage"]
        self.assertEqual(s["classes_swept"], cov["classes_swept"])
        self.assertEqual(s["members_swept"], cov["members_swept"])
        self.assertEqual(s["classes_swept"] + s["empty_objects"]
                         + s["no_member_classes"] + s["unswept_classes"],
                         s["classes_total"])

    def test_summarize_survives_empty_evidence(self):
        s = self.mod.summarize({})
        self.assertEqual(s["classes_swept"], 0)
        self.assertIn("0/0", self.mod.render(s))

    def test_report_only_exit_code(self):
        self.assertEqual(self.mod.main(["--report-only"]), 0)
        # 下限抬高到不可能达到的数 → 必须非零（普查掉下来就是回归）
        self.assertEqual(self.mod.main(["--report-only",
                                        "--min-classes", "100000"]), 1)


if __name__ == "__main__":
    unittest.main()
