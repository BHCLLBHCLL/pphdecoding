#!/usr/bin/env python3
"""Condition Wizard 对齐 scFLOWpre。"""

from __future__ import annotations

import os
import sys
import unittest
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

import pphxml
from nav_panels import ConditionsBody, NavDialogSession, _COND_WIZARD_LEAVES


def _mini_xml() -> pphxml.MainXml:
    root = ET.fromstring("""<?xml version="1.0"?>
    <scFLOWpre>
      <project><name>demo</name></project>
      <regions>
        <face><region><name>open</name></region></face>
        <fluid><region><name>FluidRegion</name></region></fluid>
      </regions>
      <conditions>
        <analysis_type>
          <Flow>true</Flow>
          <Heat>false</Heat>
          <Moving>true</Moving>
        </analysis_type>
        <basic_param>
          <steady>true</steady>
          <end_cycle>400</end_cycle>
          <default_temp>20</default_temp>
          <default_temp_unit>C</default_temp_unit>
          <gravity>false</gravity>
          <gravity_x>0</gravity_x>
          <gravity_y>0</gravity_y>
          <gravity_z>-9.8</gravity_z>
        </basic_param>
        <output_param>
          <fph_param>
            <fph_output_type>cycle_interval</fph_output_type>
            <fph_cycle_interval>100</fph_cycle_interval>
          </fph_param>
        </output_param>
        <file>
          <sph><filename>demo.sph</filename><output>false</output></sph>
          <gph><filename>demo.gph</filename><output>false</output></gph>
          <fph><filename>demo</filename><output>false</output></fph>
          <rph><filename>demo</filename><output>true</output></rph>
        </file>
        <condition>
          <type>CondBoundaryFlowIO</type>
          <name>Flux</name>
          <regions/>
        </condition>
        <condition>
          <type>CondBoundaryWallStress</type>
          <name>Wall1</name>
          <regions/>
        </condition>
        <condition>
          <type>CondSource</type>
          <name>Src1</name>
          <regions/>
        </condition>
        <analysis_control>
          <time_accuracy><order>0</order></time_accuracy>
          <loop>
            <nloop_default>true</nloop_default>
            <type>0</type>
            <const_value>1</const_value>
          </loop>
          <loop_min>
            <type>0</type>
            <const_value>1</const_value>
          </loop_min>
          <solv><type>speed</type></solv>
          <pcty>
            <bdefault>true</bdefault>
            <ipcty>3</ipcty>
          </pcty>
          <undr>
            <loop_undr_flag>false</loop_undr_flag>
            <undr_momentum>
              <type>0</type>
              <const_value>0.7</const_value>
            </undr_momentum>
          </undr>
          <sted><cycle_interval>1</cycle_interval></sted>
        </analysis_control>
      </conditions>
    </scFLOWpre>""")
    return pphxml.MainXml(root)


class TestConditions(unittest.TestCase):
    def test_wizard_layout(self):
        body = ConditionsBody()
        self.assertEqual(body.title, "Condition Wizard")
        self.assertEqual(body.dialog_buttons, 0)
        self.assertTrue(hasattr(body, "btn_finish"))
        self.assertTrue(hasattr(body, "btn_next"))
        self.assertEqual(len(_COND_WIZARD_LEAVES), body.stack.count())
        # 导航含 Analysis Conditions
        roots = [body.nav.topLevelItem(i).text(0)
                 for i in range(body.nav.topLevelItemCount())]
        self.assertIn("Analysis Conditions", roots)
        self.assertIn("Output Setting of Analysis Data", roots)

    def test_load_analysis_and_basic(self):
        body = ConditionsBody()
        ctx = NavDialogSession().build_ctx(xml=_mini_xml())
        body.load(ctx)
        self.assertTrue(body._atype_checks["Flow"].isChecked())
        self.assertFalse(body._atype_checks["Heat"].isChecked())
        self.assertTrue(body._atype_checks["Moving"].isChecked())
        self.assertTrue(body.rb_steady.isChecked())
        self.assertEqual(body.sp_last_cycle.value(), 400)
        # Flow BC：左树为区域，条件挂在子节点
        flow_page = body._pages["bc_flow"]
        self.assertGreaterEqual(flow_page._cond_list.topLevelItemCount(), 1)
        # New condition 示意图按钮
        self.assertTrue(hasattr(flow_page, "_flow_btns"))
        self.assertIn("io", flow_page._flow_btns)
        self.assertFalse(flow_page._flow_btns["io"][0].icon().isNull())
        self.assertEqual(flow_page._flow_btns["io"][0].iconSize().width(), 36)

    def test_apply_writes_xml(self):
        body = ConditionsBody()
        ctx = NavDialogSession().build_ctx(xml=_mini_xml())
        body.load(ctx)
        body._atype_checks["Heat"].setChecked(True)
        body.rb_trans.setChecked(True)
        body.sp_last_cycle.setValue(800)
        body.chk_gravity.setChecked(True)
        self.assertTrue(body.apply(ctx))
        self.assertTrue(ctx.get("xml_dirty"))
        cond = ctx["xml"].section("conditions")
        self.assertEqual(cond.findtext("analysis_type/Heat"), "true")
        self.assertEqual(cond.findtext("basic_param/steady"), "false")
        self.assertEqual(cond.findtext("basic_param/end_cycle"), "800")
        self.assertEqual(cond.findtext("basic_param/gravity"), "true")
        self.assertIn("wizard_page", ctx["session"]["conditions"])

    def test_next_back_navigation(self):
        body = ConditionsBody()
        body.load(NavDialogSession().build_ctx(xml=_mini_xml()))
        it = body._find_nav_item("analysis_type")
        body.nav.setCurrentItem(it)
        self.assertFalse(body.btn_back.isEnabled())
        body._go_next()
        self.assertEqual(body._current_key(), "basic_setting")
        body._go_back()
        self.assertEqual(body._current_key(), "analysis_type")

    def test_basic_cycle_transient_visibility(self):
        body = ConditionsBody()
        body.load(NavDialogSession().build_ctx(xml=_mini_xml()))
        # 稳态：仅 Last cycle
        self.assertTrue(body.rb_steady.isChecked())
        body._sync_basic_cycle()
        self.assertTrue(body._cycle_items["dt_type"].isHidden())
        self.assertTrue(body._cycle_items["time_step"].isHidden())
        self.assertFalse(body._cycle_items["last_cycle"].isHidden())

        # 瞬态 + Time step
        body.rb_trans.setChecked(True)
        body.cb_dt_type.setCurrentIndex(0)  # Time step
        body._sync_basic_cycle()
        self.assertFalse(body._cycle_items["dt_type"].isHidden())
        self.assertFalse(body._cycle_items["time_step"].isHidden())
        self.assertTrue(body._cycle_items["dt_init"].isHidden())
        self.assertTrue(body._cycle_items["courant"].isHidden())
        self.assertFalse(body._cycle_items["set_start"].isHidden())
        self.assertTrue(body._cycle_items["start_time"].isHidden())
        self.assertTrue(body._cycle_items["set_dt_limit"].isHidden())

        # Courant → 显示 Initial / Courant / dt limit
        body.cb_dt_type.setCurrentIndex(1)
        body._sync_basic_cycle()
        self.assertTrue(body._cycle_items["time_step"].isHidden())
        self.assertFalse(body._cycle_items["dt_init"].isHidden())
        self.assertFalse(body._cycle_items["courant"].isHidden())
        self.assertFalse(body._cycle_items["set_dt_limit"].isHidden())

        # Set start / skip → 展开子项
        body.cb_set_start.setCurrentIndex(1)
        body.cb_skip.setCurrentIndex(1)
        body._sync_basic_cycle()
        self.assertFalse(body._cycle_items["start_time"].isHidden())
        self.assertFalse(body._cycle_items["skip_duration"].isHidden())
        self.assertFalse(body._cycle_items["skip_time"].isHidden())

    def test_basic_transient_apply(self):
        body = ConditionsBody()
        ctx = NavDialogSession().build_ctx(xml=_mini_xml())
        body.load(ctx)
        body.rb_trans.setChecked(True)
        body.cb_dt_type.setCurrentIndex(1)  # Courant
        body.sp_courant.setValue(0.5)
        body.cb_set_stop.setCurrentIndex(1)
        body.sp_stop_time.setValue(12.5)
        self.assertTrue(body.apply(ctx))
        bp = ctx["xml"].section("conditions").find("basic_param")
        self.assertEqual(bp.findtext("steady"), "false")
        self.assertEqual(bp.findtext("type"), "1")
        self.assertEqual(
            bp.findtext("courant_num_val/const_value"), "0.5")
        self.assertEqual(bp.findtext("set_stop_time"), "true")
        self.assertEqual(
            bp.findtext("stop_time/const_value"), "12.5")

    def test_initial_condition_icons(self):
        from nav_panels import (
            _ic_new_condition_icon, _ic_region_icon, _IC_NEW_COND_BUTTONS,
        )
        body = ConditionsBody()
        page = body._pages["initial"]
        self.assertTrue(hasattr(page, "_ic_buttons"))
        self.assertEqual(len(page._ic_buttons), len(_IC_NEW_COND_BUTTONS))
        for btn in page._ic_buttons:
            self.assertFalse(btn.icon().isNull())
            self.assertEqual(btn.iconSize().width(), 36)
        # 区域图标
        for kind in ("whole", "volume", "special"):
            ic = _ic_region_icon(kind, 18)
            self.assertFalse(ic.isNull())
        for kind, _ in _IC_NEW_COND_BUTTONS:
            self.assertFalse(_ic_new_condition_icon(kind, 48).isNull())
        body.load(NavDialogSession().build_ctx(xml=_mini_xml()))
        lst = page._cond_list
        self.assertGreaterEqual(lst.topLevelItemCount(), 1)
        self.assertFalse(lst.topLevelItem(0).icon(0).isNull())
        self.assertEqual(lst.topLevelItem(0).text(0), "Whole region")

    def test_flow_boundary_right_panel(self):
        from nav_panels import _flow_bc_icon, _FLOW_BC_NEW_BUTTONS
        body = ConditionsBody()
        ctx = NavDialogSession().build_ctx(xml=_mini_xml())
        body.load(ctx)
        page = body._pages["bc_flow"]
        stack = page._flow_stack
        self.assertEqual(stack.currentIndex(), 0)
        # 门控按钮：默认 GT-SUITE / DEM / liquid film 禁用
        self.assertFalse(page._flow_btns["gtsuite"][0].isEnabled())
        self.assertFalse(page._flow_btns["dem"][0].isEnabled())
        body._atype_checks["GT-SUITE"].setChecked(True)
        self.assertTrue(page._flow_btns["gtsuite"][0].isEnabled())
        # 打开编辑页
        body._open_flow_bc_editor("io", "Inflow and outflow condition",
                                  new=True)
        self.assertEqual(stack.currentIndex(), 1)
        self.assertEqual(body.flow_edit_title.text(),
                         "Inflow and outflow condition")
        self.assertGreater(body.flow_param_tree.topLevelItemCount(), 0)
        # Set 写回
        body.ed_flow_name.setText("FluxNew")
        reg = page._cond_list.topLevelItem(0)
        reg.setSelected(True)
        body._set_flow_bc()
        self.assertEqual(stack.currentIndex(), 0)
        names = []
        for i in range(page._cond_list.topLevelItemCount()):
            p = page._cond_list.topLevelItem(i)
            for j in range(p.childCount()):
                names.append(p.child(j).text(0))
        self.assertIn("FluxNew", names)
        for kind, _lab, _gate in _FLOW_BC_NEW_BUTTONS:
            self.assertFalse(_flow_bc_icon(kind, 36).isNull())

    def test_wall_boundary_right_panel(self):
        from nav_panels import _wall_bc_icon, _WALL_BC_NEW_BUTTONS
        body = ConditionsBody()
        ctx = NavDialogSession().build_ctx(xml=_mini_xml())
        body.load(ctx)
        page = body._pages["bc_wall"]
        self.assertTrue(hasattr(page, "_wall_btns"))
        self.assertIn("stress", page._wall_btns)
        btn = page._wall_btns["stress"][0]
        self.assertFalse(btn.icon().isNull())
        self.assertEqual(btn.iconSize().width(), 36)
        self.assertEqual(
            btn.text(), "Wall shear stress condition")
        # Particle 门控
        self.assertFalse(page._wall_btns["particle"][0].isEnabled())
        body._atype_checks["ParticleTracking"].setChecked(True)
        self.assertTrue(page._wall_btns["particle"][0].isEnabled())
        # 左树含 Undefined Stress
        names = [
            page._cond_list.topLevelItem(i).text(0)
            for i in range(page._cond_list.topLevelItemCount())
        ]
        self.assertTrue(any("Undefined (Stress" in n for n in names))
        # 打开编辑
        body._open_wall_bc_editor(
            "stress", "Wall shear stress condition", new=True)
        self.assertEqual(page._wall_stack.currentIndex(), 1)
        self.assertGreater(body.wall_param_tree.topLevelItemCount(), 0)
        body.ed_wall_name.setText("WallA")
        page._cond_list.topLevelItem(0).setSelected(True)
        body._set_wall_bc()
        self.assertEqual(page._wall_stack.currentIndex(), 0)
        for kind, _lab, _gate in _WALL_BC_NEW_BUTTONS:
            self.assertFalse(_wall_bc_icon(kind, 36).isNull())

    def test_thermal_boundary_right_panel(self):
        from nav_panels import _thermal_bc_icon, _THERMAL_BC_NEW_BUTTONS
        body = ConditionsBody()
        ctx = NavDialogSession().build_ctx(xml=_mini_xml())
        body.load(ctx)
        page = body._pages["bc_thermal"]
        self.assertTrue(hasattr(page, "_thermal_btns"))
        self.assertIn("heat", page._thermal_btns)
        btn = page._thermal_btns["heat"][0]
        self.assertFalse(btn.icon().isNull())
        self.assertEqual(btn.iconSize().width(), 36)
        self.assertEqual(btn.text(), "Wall heat transfer condition")
        # 门控：Porous / Radiation / Solar 默认禁用
        self.assertFalse(page._thermal_btns["porous"][0].isEnabled())
        self.assertFalse(page._thermal_btns["radiation"][0].isEnabled())
        body._atype_checks["Radiation"].setChecked(True)
        self.assertTrue(page._thermal_btns["radiation"][0].isEnabled())
        names = [
            page._cond_list.topLevelItem(i).text(0)
            for i in range(page._cond_list.topLevelItemCount())
        ]
        self.assertTrue(any("Undefined (Thermal" in n for n in names))
        body._open_thermal_bc_editor(
            "heat", "Wall heat transfer condition", new=True)
        self.assertEqual(page._thermal_stack.currentIndex(), 1)
        self.assertGreater(body.thermal_param_tree.topLevelItemCount(), 0)
        body.ed_thermal_name.setText("HeatA")
        page._cond_list.topLevelItem(0).setSelected(True)
        body._set_thermal_bc()
        self.assertEqual(page._thermal_stack.currentIndex(), 0)
        for kind, _lab, _gate in _THERMAL_BC_NEW_BUTTONS:
            self.assertFalse(_thermal_bc_icon(kind, 36).isNull())

    def test_sym_boundary_right_panel(self):
        from nav_panels import _sym_bc_icon, _SYM_BC_NEW_BUTTONS
        body = ConditionsBody()
        ctx = NavDialogSession().build_ctx(xml=_mini_xml())
        body.load(ctx)
        page = body._pages["bc_sym"]
        self.assertTrue(hasattr(page, "_sym_btns"))
        self.assertIn("flow", page._sym_btns)
        btn = page._sym_btns["flow"][0]
        self.assertFalse(btn.icon().isNull())
        self.assertEqual(btn.iconSize().width(), 36)
        self.assertEqual(btn.text(), "Symmetrical boundary condition")
        self.assertFalse(page._sym_btns["particle"][0].isEnabled())
        body._atype_checks["ParticleTracking"].setChecked(True)
        self.assertTrue(page._sym_btns["particle"][0].isEnabled())
        names = [
            page._cond_list.topLevelItem(i).text(0)
            for i in range(page._cond_list.topLevelItemCount())
        ]
        self.assertTrue(any("Undefined (Particle" in n for n in names))
        # 选区域后 Apply
        page._cond_list.topLevelItem(0).setSelected(True)
        body._apply_sym_bc("flow", "Symmetrical boundary condition")
        child_names = []
        for i in range(page._cond_list.topLevelItemCount()):
            p = page._cond_list.topLevelItem(i)
            for j in range(p.childCount()):
                child_names.append(p.child(j).text(0))
        self.assertTrue(any(n.startswith("Symmetry") for n in child_names))
        for kind, _lab, _gate in _SYM_BC_NEW_BUTTONS:
            self.assertFalse(_sym_bc_icon(kind, 36).isNull())

    def test_periodic_boundary_right_panel(self):
        from nav_panels import _periodic_bc_icon
        body = ConditionsBody()
        ctx = NavDialogSession().build_ctx(xml=_mini_xml())
        body.load(ctx)
        page = body._pages["bc_periodic"]
        self.assertTrue(hasattr(page, "_cond_table"))
        self.assertEqual(page._cond_table.columnCount(), 3)
        self.assertFalse(_periodic_bc_icon(36).isNull())
        # 直接写入 session 并刷新列表
        ctx.setdefault("session", {}).setdefault("conditions", {})[
            "periodic_boundaries"] = [{
                "name": "Per1",
                "primary": "open",
                "secondary": "open",
                "rotation": "Do not consider",
                "translation": "Do not consider",
                "projection": "Plane",
                "pressure_diff": "0",
            }]
        body._fill_periodic_bc_list()
        self.assertEqual(page._cond_table.rowCount(), 1)
        self.assertEqual(page._cond_table.item(0, 0).text(), "Per1")
        self.assertFalse(page._cond_table.item(0, 0).icon().isNull())

    def test_source_condition_right_panel(self):
        from nav_panels import _source_bc_icon, _SOURCE_BC_NEW_BUTTONS
        body = ConditionsBody()
        ctx = NavDialogSession().build_ctx(xml=_mini_xml())
        body.load(ctx)
        page = body._pages["source"]
        self.assertTrue(hasattr(page, "_source_btns"))
        self.assertIn("source", page._source_btns)
        btn = page._source_btns["source"][0]
        self.assertFalse(btn.icon().isNull())
        self.assertEqual(btn.iconSize().width(), 36)
        self.assertEqual(btn.text(), "Source condition")
        # Mixed gas 门控 Mass source
        self.assertFalse(page._source_btns["mass_vol"][0].isEnabled())
        body._atype_checks["mixed_gas"].setChecked(True)
        self.assertTrue(page._source_btns["mass_vol"][0].isEnabled())
        self.assertGreaterEqual(page._cond_list.topLevelItemCount(), 1)
        body._open_source_bc_editor(
            "source", "Source condition", new=True)
        self.assertEqual(page._source_stack.currentIndex(), 1)
        self.assertGreater(body.source_param_tree.topLevelItemCount(), 0)
        body.ed_source_name.setText("SrcA")
        page._cond_list.topLevelItem(0).setSelected(True)
        body._set_source_bc()
        self.assertEqual(page._source_stack.currentIndex(), 0)
        for kind, _lab, _gate in _SOURCE_BC_NEW_BUTTONS:
            self.assertFalse(_source_bc_icon(kind, 36).isNull())

    def test_fixed_condition_right_panel(self):
        from nav_panels import _fixed_bc_icon
        body = ConditionsBody()
        ctx = NavDialogSession().build_ctx(xml=_mini_xml())
        body.load(ctx)
        page = body._pages["fixed"]
        self.assertTrue(hasattr(page, "_fixed_btn"))
        self.assertFalse(page._fixed_btn.icon().isNull())
        self.assertEqual(page._fixed_btn.iconSize().width(), 36)
        self.assertEqual(page._fixed_btn.text(), "Fixed condition")
        self.assertGreaterEqual(page._cond_list.topLevelItemCount(), 1)
        body._open_fixed_bc_editor(new=True)
        self.assertEqual(page._fixed_stack.currentIndex(), 1)
        self.assertEqual(body.fixed_param_tree.topLevelItemCount(), 2)
        body.ed_fixed_name.setText("FixA")
        page._cond_list.topLevelItem(0).setSelected(True)
        body._set_fixed_bc()
        self.assertEqual(page._fixed_stack.currentIndex(), 0)
        child_names = []
        for i in range(page._cond_list.topLevelItemCount()):
            p = page._cond_list.topLevelItem(i)
            for j in range(p.childCount()):
                child_names.append(p.child(j).text(0))
        self.assertIn("FixA", child_names)
        self.assertFalse(_fixed_bc_icon(36).isNull())

    def test_analysis_control_panel(self):
        from nav_panels import _ac_nav_icon, _AC_NAV_TREE
        body = ConditionsBody()
        ctx = NavDialogSession().build_ctx(xml=_mini_xml())
        body.load(ctx)
        page = body._pages["analysis_control"]
        self.assertTrue(hasattr(page, "_ac_nav"))
        nav = page._ac_nav
        labels = []
        for i in range(nav.topLevelItemCount()):
            it = nav.topLevelItem(i)
            labels.append(it.text(0))
            for j in range(it.childCount()):
                labels.append(it.child(j).text(0))
        self.assertIn("Batch Setting", labels)
        self.assertIn("Loop", labels)
        self.assertIn("Matrix Solvers", labels)
        self.assertIn("Under-Relaxation Coefficient", labels)
        self.assertIn("Avoidance of Divergence (Variable)", labels)
        self.assertIn("Accuracy of Convective Terms", labels)
        self.assertFalse(_ac_nav_icon("leaf", 16).isNull())
        # 子页布局：undr 表 + 侧栏；upwd 表；pcty 下拉；sted 双表
        self.assertEqual(body.ac_undr_tree.columnCount(), 3)
        self.assertGreaterEqual(body.ac_undr_tree.topLevelItemCount(), 10)
        self.assertIn("Value :", body.ac_undr_tree.topLevelItem(0).text(2))
        self.assertGreaterEqual(body.ac_upwd_tree.topLevelItemCount(), 5)
        self.assertGreaterEqual(body.ac_loopeq_tree.topLevelItemCount(), 5)
        self.assertGreaterEqual(body.ac_sted_param.topLevelItemCount(), 3)
        self.assertEqual(
            body.cb_ac_pcty.itemText(0), "Default (SIMPLEC method)")
        # 切换页面
        nav.setCurrentItem(body._ac_nav_items["loop"])
        self.assertIs(body._ac_stack.currentWidget(), body._ac_pages["loop"])
        self.assertTrue(body.chk_ac_loop_default.isChecked())
        nav.setCurrentItem(body._ac_nav_items["upwd"])
        self.assertIs(body._ac_stack.currentWidget(), body._ac_pages["upwd"])
        nav.setCurrentItem(body._ac_nav_items["solv"])
        self.assertTrue(body.rb_ac_solv_speed.isChecked())
        # Batch Apply Accuracy/Stability
        body.cb_ac_batch.setCurrentIndex(1)
        body._ac_apply_batch()
        self.assertTrue(body.rb_ac_time_2nd.isChecked())
        self.assertTrue(body.rb_ac_solv_acc.isChecked())
        self.assertEqual(body.sp_ac_loop_max.value(), 20)
        self.assertEqual(body.cb_ac_pcty.currentData(), "2")
        self.assertTrue(body.apply(ctx))
        ac = ctx["xml"].section("conditions").find("analysis_control")
        self.assertEqual(ac.findtext("solv/type"), "accuracy")
        self.assertEqual(ac.findtext("time_accuracy/order"), "1")
        self.assertEqual(ac.findtext("loop/const_value"), "20")
        self.assertEqual(ac.findtext("pcty/ipcty"), "2")
        self.assertEqual(len(_AC_NAV_TREE), 10)

    def test_output_and_file_optional_panels(self):
        from nav_panels import (
            _OUT_FIELD_NAV, _OUT_LIST_NAV, _OUT_OTHER_NAV,
            _OPTIONAL_NEW_BUTTONS, _optional_cond_icon, _file_type_icon,
        )
        body = ConditionsBody()
        ctx = NavDialogSession().build_ctx(xml=_mini_xml())
        body.load(ctx)
        # Field File 子导航
        fpage = body._pages["out_field"]
        self.assertTrue(hasattr(fpage, "_out_field_nav"))
        self.assertEqual(
            fpage._out_field_nav.topLevelItemCount(), len(_OUT_FIELD_NAV))
        self.assertEqual(
            body.cb_fph_type.itemText(0), "Last cycle")
        self.assertGreaterEqual(body.fph_var_tree.topLevelItemCount(), 5)
        # List / Other
        self.assertEqual(
            body._pages["out_list"]._out_list_nav.topLevelItemCount(),
            len(_OUT_LIST_NAV))
        self.assertEqual(
            body._pages["out_other"]._out_other_nav.topLevelItemCount(),
            len(_OUT_OTHER_NAV))
        body._out_other_nav_items["oth_restart"]
        body._pages["out_other"]._out_other_nav.setCurrentItem(
            body._out_other_nav_items["oth_restart"])
        self.assertIs(
            body._out_other_stack.currentWidget(),
            body._out_other_pages["oth_restart"])
        # File Name
        self.assertGreaterEqual(body.file_tree.topLevelItemCount(), 10)
        self.assertIn("sph", body._file_editors)
        self.assertFalse(_file_type_icon("fph", 16).isNull())
        body.ed_project.setText("proj")
        body._apply_project_to_files()
        self.assertEqual(body._file_editors["sph"].text(), "proj.sph")
        self.assertEqual(body._file_editors["fph"].text(), "proj")
        # Optional Conditions 示意图标按钮
        opage = body._pages["optional"]
        self.assertEqual(len(opage._opt_btns), len(_OPTIONAL_NEW_BUTTONS))
        for btn in opage._opt_btns:
            self.assertFalse(btn.icon().isNull())
            self.assertEqual(btn.iconSize().width(), 36)
        body._open_optional("table", "Table")
        self.assertEqual(opage._cond_list.topLevelItemCount(), 1)
        for kind, _lab in _OPTIONAL_NEW_BUTTONS:
            self.assertFalse(_optional_cond_icon(kind, 36).isNull())
        # apply 写 fph 类型
        body.cb_fph_type.setCurrentText("Every specified cycle")
        body.sp_fph_cycle.setValue(50)
        self.assertTrue(body.apply(ctx))
        fp = ctx["xml"].section("conditions").find(
            "output_param/fph_param")
        self.assertEqual(fp.findtext("fph_output_type"), "cycle_interval")
        self.assertEqual(fp.findtext("fph_cycle_interval"), "50")


if __name__ == "__main__":
    unittest.main()
