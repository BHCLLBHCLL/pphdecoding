"""P4-0 条件树（condition_tree）解析与 main.xml 绑定测试。

数据源：schemas/condition_tree.json（由安装目录 scflow_main.xml 解析
产物 bundling）；绑定测试用 box.pph 的 main.xml（经 pphxml 容错解析）。
"""

import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import condition_tree  # noqa: E402
import pphxml  # noqa: E402


def _box_cond_root():
    raw = zipfile.ZipFile("box.pph").read("main.xml")
    xml = pphxml.parse_main_xml(raw)
    return xml.section("conditions")


class TestConditionTreeParse(unittest.TestCase):
    """bundled JSON 的结构与规模。"""

    @classmethod
    def setUpClass(cls):
        cls.tree = condition_tree.load_condition_tree()
        if cls.tree is None:
            raise unittest.SkipTest("condition_tree.json not bundled")

    def test_summary_counts(self):
        s = condition_tree.summary(self.tree)
        self.assertEqual(s["categories"], 9)
        self.assertEqual(s["sections"], 10)
        self.assertEqual(s["variables"], 349)
        self.assertGreater(s["conditions"], 700)

    def test_categories_present(self):
        engs = {c["eng"] for c in self.tree["categories"]}
        for want in ("Basic Setting", "Source Condition",
                     "Inflow and Outflow Condition",
                     "Moving Condition", "Porous Media Condition"):
            self.assertIn(want, engs)

    def test_two_segment_paths(self):
        paths = [v["name"] for _, _, v in
                 condition_tree.iter_variables(self.tree)
                 if "/" in v["name"]]
        self.assertEqual(len(paths), 39)
        self.assertTrue(any(p.startswith("volume_param/") for p in paths))

    def test_section_cond_types(self):
        src = next(s for c in self.tree["categories"]
                   if c["eng"] == "Source Condition"
                   for s in c["sections"])
        types = condition_tree.section_cond_types(src)
        for want in ("CondAcceleration", "CondSource", "CondPorousMedia",
                     "CondSourceMass", "CondFacePressureDrop"):
            self.assertIn(want, types)


class TestConditionTreeBinding(unittest.TestCase):
    """read/write/active 绑定（box.pph main.xml）。"""

    @classmethod
    def setUpClass(cls):
        cls.cond_root = _box_cond_root()
        if cls.cond_root is None:
            raise unittest.SkipTest("box.pph main.xml unavailable")
        cls.tree = condition_tree.load_condition_tree()
        cls.cats = {c["eng"]: c for c in cls.tree["categories"]}

    def test_basic_param_read_write(self):
        sec = self.cats["Basic Setting"]["sections"][0]
        insts = condition_tree.section_instances(self.cond_root, sec)
        self.assertEqual(len(insts), 1)
        bp = insts[0]
        v = next(v for v in sec["variables"]
                 if v["name"] == "const_time_step_val")
        self.assertTrue(condition_tree.variable_active(bp, v))
        old = condition_tree.read_variable(bp, v)
        self.assertIsNotNone(old)
        self.assertTrue(condition_tree.write_variable(bp, v, "3.25"))
        self.assertEqual(condition_tree.read_variable(bp, v), "3.25")
        condition_tree.write_variable(bp, v, old)
        self.assertEqual(condition_tree.read_variable(bp, v), old)

    def test_write_same_value_no_change(self):
        sec = self.cats["Basic Setting"]["sections"][0]
        bp = condition_tree.section_instances(self.cond_root, sec)[0]
        v = next(v for v in sec["variables"]
                 if v["name"] == "const_time_step_val")
        cur = condition_tree.read_variable(bp, v)
        self.assertFalse(condition_tree.write_variable(bp, v, cur))

    def test_write_creates_missing_path(self):
        sec = self.cats["Basic Setting"]["sections"][0]
        bp = condition_tree.section_instances(self.cond_root, sec)[0]
        v = {"name": "courant_num_val", "path": ["courant_num_val"],
             "value_key": "const_value", "unit_key": "unit",
             "conditions": [], "display": None}
        bp.remove(bp.find("courant_num_val"))
        self.assertIsNone(condition_tree.read_variable(bp, v))
        self.assertTrue(condition_tree.write_variable(bp, v, "0.85"))
        self.assertEqual(condition_tree.read_variable(bp, v), "0.85")
        self.assertIsNotNone(bp.find("courant_num_val/unit"))

    def test_flow_io_dependency_semantics(self):
        io_sec = self.cats["Inflow and Outflow Condition"]["sections"][0]
        insts = [c for c in self.cond_root.findall("condition")
                 if (c.findtext("type") or "") == "CondBoundaryFlowIO"]
        self.assertTrue(insts)
        inst = insts[0]
        v = next(v for v in io_sec["variables"]
                 if v["name"] == "velocity_vertical_value")
        active = condition_tree.variable_active(inst, v)
        flow_io = inst.findtext("flow_io_type")
        self.assertEqual(active, flow_io == "normal_velocity")
        readable = sum(1 for v in io_sec["variables"]
                       if condition_tree.read_variable(inst, v) is not None)
        self.assertGreater(readable, 40)


class TestSolverSettingsDialog(unittest.TestCase):
    """GUI 冒烟（offscreen）。"""

    @classmethod
    def setUpClass(cls):
        try:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from PyQt5.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest("PyQt5 unavailable")
        cls.app = QApplication.instance() or QApplication(
            [sys.argv[0], "-platform=offscreen"])
        import nav_panels
        cls.nav = nav_panels

    def _ctx(self):
        raw = zipfile.ZipFile("box.pph").read("main.xml")
        xml = pphxml.parse_main_xml(raw)
        return self.nav.NavDialogSession().build_ctx(xml=xml)

    def test_dialog_render_and_writeback(self):
        tree = condition_tree.load_condition_tree()
        if tree is None:
            self.skipTest("condition_tree.json not bundled")
        ctx = self._ctx()
        dlg = self.nav.SolverSettingsDialog(ctx)
        self.assertEqual(len(dlg._sections), 10)
        rows = list(dlg._rows)
        self.assertTrue(rows)
        self.assertTrue(all(el is not None for el, _, _, _ in rows))
        for el, v, ed, old in rows:
            if v["name"] == "const_time_step_val":
                ed.setText("7.5")
        dlg._on_ok()
        self.assertTrue(ctx["xml_dirty"])
        bp = ctx["xml"].section("conditions").find("basic_param")
        self.assertEqual(bp.find("const_time_step_val/const_value").text,
                         "7.5")
        dlg.deleteLater()


if __name__ == "__main__":
    unittest.main()
