#!/usr/bin/env python3
"""R46 证据回归：未普查类归因（R46-1）/ 取得路径进总账（R46-2）/ 宿主边界上面板（R46-3）。

* **归因**：`tools/unswept_account.py` 给"从未尝试"的类逐类终态 ——
  `needs-corpus` / `host-interface-absent` / `no-creation-path` /
  `call-rejected` / `foreign-app` / `probe-limitation`，理由必须来自证据
  （配方宿主、候选调用错误、返回空），**不许**编一个；
* **总账**：`coverage.obtained_via` 让覆盖率报表能答「这个类怎么拿到的」；
* **面板**：`nav_panels.py` 的条件目录新增 Host 列 + 「Host 边界…」对话框
  （数据 = `automation.scflowpre_api`，文本 = 纯函数 `render_host_boundary`）。
"""

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 面板测试要**离屏**跑（无显示器）；必须在 import PyQt5 之前设好
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

AVAIL = ROOT / "schemas" / "host_member_availability.json"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
UNSWEPT = ROOT / "schemas" / "unswept_account.json"
ACCOUNT_TOOL = ROOT / "tools" / "unswept_account.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestUnsweptAccount(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not AVAIL.is_file():
            raise unittest.SkipTest("availability evidence missing")
        cls.tool = _load("unswept_r46", ACCOUNT_TOOL)
        cls.data = json.loads(AVAIL.read_text(encoding="utf-8"))
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.acct = cls.tool.account()

    def test_every_unswept_class_has_a_terminal(self):
        unswept = set(self.data["coverage"]["unswept_classes"])
        rows = self.acct["classes"]
        self.assertEqual(set(rows), unswept, "未普查类必须逐类归因")
        for cls, r in rows.items():
            self.assertIn(r["terminal"], self.tool.TERMINALS, cls)
            self.assertTrue(r["reason"].strip(), cls)
            self.assertIn("evidence", r, cls)

    def test_counts_match_rows(self):
        c = self.acct["counts"]
        self.assertEqual(c["total"], len(self.acct["classes"]))
        for t in self.tool.TERMINALS:
            self.assertEqual(c[t], sum(1 for r in self.acct["classes"].values()
                                       if r["terminal"] == t), t)

    def test_committed_account_matches_live(self):
        if not UNSWEPT.is_file():
            raise unittest.SkipTest("unswept account not committed yet")
        saved = json.loads(UNSWEPT.read_text(encoding="utf-8"))
        self.assertEqual(saved["counts"], self.acct["counts"],
                         "入册的归因表必须与当场计算一致（跑完要 --json 再生）")

    def test_recipe_host_extraction(self):
        self.assertEqual(self.tool.recipe_host("SNode", self.cat), "snode")
        self.assertEqual(self.tool.recipe_host("Kicker.Application", self.cat),
                         "app")
        self.assertIsNone(self.tool.recipe_host("Table", self.cat))

    def test_declared_candidates_need_manual_backing(self):
        # Table：手册在 Doc 上声明了 CreateTable → 有「手册给的取法」
        self.assertTrue(self.tool.declared_candidates("Table", self.cat))
        # WrappingParam：手册没给任何创建/取用路径 → 只能记 no-creation-path
        self.assertEqual(self.tool.declared_candidates("WrappingParam",
                                                       self.cat), [])

    def test_classify_prefers_evidence(self):
        r = self.tool.classify("SNode", self.cat, {"_path": "x"})
        self.assertEqual(r["terminal"], "needs-corpus")
        self.assertIn("snode", r["reason"])
        # 别的应用对象
        r2 = self.tool.classify("Kicker.LicenseStatus", self.cat, {"_path": "x"})
        self.assertEqual(r2["terminal"], "foreign-app")
        # 手册声明的取法全部"未知名称" → 宿主没有这个接口
        r4 = self.tool.classify(
            "Table", self.cat,
            {"_path": "x",
             "auto_call_errors": {"Doc.CreateTable": "com_error: 未知名称。"}})
        self.assertEqual(r4["terminal"], "host-interface-absent")
        # 返回空 = 前置语料不在本机工程
        r3 = self.tool.classify(
            "Table", self.cat,
            {"_path": "x", "auto_empty_targets": {"Table": "catalog:Doc.CreateTable"}})
        self.assertEqual(r3["terminal"], "needs-corpus")
        self.assertIn("返回空", r3["reason"])

    def test_no_hand_waving_reason(self):
        """终态理由必须能追到证据（配方/候选/尝试/返回空），不许是「待办」。"""
        for cls, r in self.acct["classes"].items():
            blob = r["reason"]
            self.assertNotIn("待办", blob, cls)
            self.assertNotIn("TODO", blob, cls)
            if r["terminal"] == "probe-limitation":
                self.assertIn("没有结论", blob, cls)


class TestObtainedVia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not AVAIL.is_file():
            raise unittest.SkipTest("availability evidence missing")
        cls.data = json.loads(AVAIL.read_text(encoding="utf-8"))

    def test_every_swept_class_has_a_path(self):
        cov = self.data["coverage"]
        via = cov.get("obtained_via") or {}
        self.assertTrue(via, "R46-2：取得路径必须进总账")
        # 已普查 + 手册无成员的类都必须有路径（后者也拿到了对象）
        want = set(self.data["classes"]) | set(
            cov.get("no_member_classes") or [])
        self.assertTrue(want.issubset(set(via)),
                        sorted(want - set(via)))
        for cls, how in via.items():
            self.assertTrue(str(how).strip(), cls)

    def test_paths_name_a_real_api(self):
        """取得路径必须是**真调用**：链条/自动配方/条件批量/会话，或目录里的成员名。"""
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        members = {m for info in cat["classes"].values()
                   for kind in ("methods", "properties")
                   for m in (info.get(kind) or {})}
        prefixes = ("chain:", "auto:", "CreateCond*:", "alias:", "session:")
        for cls, how in (self.data["coverage"]["obtained_via"] or {}).items():
            how = str(how)
            if how.startswith(prefixes):
                continue
            self.assertIn(how, members,
                          cls + " 的取得路径既不是已知来源，也不是目录成员名："
                          + how)


class TestPanelBoundary(unittest.TestCase):
    """R46-3：宿主边界要在**面板**可查（离屏 Qt）。"""

    @classmethod
    def setUpClass(cls):
        try:
            import nav_panels
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest("nav_panels 不可导入: " + str(exc))
        cls.np = nav_panels

    def test_render_is_pure_and_complete(self):
        data = {"absent": {"CondSource": ["IsEnableConditionForCalculation"]},
                "hints": {"Octree": "先建八叉树（网格组的 octree 步骤）"}}
        text = self.np.render_host_boundary(data)
        self.assertIn("Octree", text)
        self.assertIn("八叉树", text)
        self.assertIn("CondSource", text)
        self.assertIn("IsEnableConditionForCalculation", text)
        # 缺证据时也要给一句可读的话，不是崩或空
        empty = self.np.render_host_boundary({})
        self.assertIn("没有宿主未实现成员的证据", empty)

    def test_boundary_data_matches_product_api(self):
        from automation import scflowpre_api as api
        data = self.np.host_boundary_data()
        self.assertEqual(data["absent"], api.host_absent_members())
        self.assertEqual(data["hints"], api.object_hints())
        self.assertTrue(data["absent"], "本机应有 host_absent 证据")

    def test_host_absent_for_known_class(self):
        self.assertIn("IsEnableConditionForCalculation",
                      self.np.host_absent_for("CondSource"))
        self.assertEqual(self.np.host_absent_for("___nope___"), [])

    def test_dialog_builds_offscreen(self):
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance() or QApplication([])
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest("Qt 不可用: " + str(exc))
        dlg = self.np.HostBoundaryDialog({"absent": {"CondSource": ["X"]},
                                          "hints": {"Octree": "先建八叉树"}})
        self.assertIn("Octree", dlg.txt.toPlainText())
        self.assertIn("CondSource", dlg.txt.toPlainText())
        dlg2 = self.np.CondTypeCatalogDialog({}, None)
        headers = [dlg2.lst.headerItem().text(i)
                   for i in range(dlg2.lst.columnCount())]
        self.assertIn("Host", headers)
        self.assertTrue(hasattr(dlg2, "btn_host"), "要有 Host 边界… 入口")
        del app


if __name__ == "__main__":
    unittest.main()
