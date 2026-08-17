#!/usr/bin/env python3
"""Parts Control 对话框 / Navigation 刷新 / SetPartsControl VBS。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from automation.pipeline_plan import build_execute_vbs, parts_control_actions
from nav_panels import BODY_CLASSES, NavDialogSession, PartsControlBody
from pph_gui import NavigationWindow


def _nav_keys(nav: NavigationWindow) -> list[str]:
    out: list[str] = []
    for i in range(nav.tree.topLevelItemCount()):
        item = nav.tree.topLevelItem(i)
        if item.childCount():          # 分组节点 → 收集子项 key
            for j in range(item.childCount()):
                out.append(item.child(j).data(0, Qt.UserRole))
        else:                          # 顶级 leaf（如 Begin Wrapping）
            out.append(item.data(0, Qt.UserRole))
    return out


class TestPartsControl(unittest.TestCase):
    def test_dialog_apply_session(self):
        body = PartsControlBody()
        sess = NavDialogSession()
        ctx = sess.build_ctx()
        body.load(ctx)
        body.chk_disc.setChecked(True)
        body.chk_wrap.setChecked(True)
        self.assertTrue(body.apply(ctx))
        pc = ctx["session"]["parts_control"]
        self.assertTrue(pc["discontinuous"])
        self.assertTrue(pc["wrapping"])
        self.assertFalse(pc["overset"])
        self.assertTrue(pc["nav_dirty"])

    def test_navigation_inserts_after_modify_parts(self):
        nav = NavigationWindow()
        keys0 = _nav_keys(nav)
        self.assertNotIn("specify_disc", keys0)
        self.assertNotIn("begin_wrap", keys0)

        nav.set_parts_control({
            "discontinuous": True, "overset": False, "wrapping": True})
        keys = _nav_keys(nav)
        self.assertIn("specify_disc", keys)
        self.assertIn("wrap_octree", keys)
        self.assertIn("begin_wrap", keys)
        self.assertNotIn("overset_mesh", keys)
        self.assertLess(keys.index("modify_parts"), keys.index("specify_disc"))
        self.assertLess(keys.index("specify_disc"), keys.index("mesher_faceter"))
        self.assertLess(keys.index("begin_wrap"), keys.index("execute"))

    def test_followup_bodies_registered(self):
        for key in ("specify_disc", "overset_mesh", "wrap_octree",
                    "wrap_param", "begin_wrap", "cancel_wrap",
                    "exec_wrap", "retry_wrap"):
            self.assertIn(key, BODY_CLASSES)

    def test_parts_control_vbs(self):
        pc = {"discontinuous": True, "overset": False, "wrapping": True}
        acts = parts_control_actions(pc)
        self.assertEqual(acts[0], "Set Conditions_ = Doc_.GetConditions")
        self.assertIn(
            'Conditions_.SetPartsControl "Discontinuous", True', acts)
        self.assertIn(
            'Conditions_.SetPartsControl "Overset", False', acts)
        self.assertIn(
            'Conditions_.SetPartsControl "Wrapping", True', acts)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "t.vbs"
            build_execute_vbs(
                "box.pph", {"bam": True, "oct": False, "mesh": False}, out,
                parts_control_sess=pc)
            raw = out.read_bytes()
            text = (raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff")
                    else raw.decode("utf-8"))
        self.assertIn(
            'Conditions_.SetPartsControl "Discontinuous", True', text)


    def test_parts_control_writes_xml_flags(self):
        import pphxml
        import project_persist
        xml = pphxml.parse_main_xml(
            project_persist.empty_project_members()["main.xml"])
        body = PartsControlBody()
        sess = NavDialogSession()
        ctx = sess.build_ctx(xml=xml)
        body.load(ctx)
        body.chk_disc.setChecked(True)
        body.chk_overset.setChecked(True)
        self.assertTrue(body.apply(ctx))
        self.assertTrue(ctx["xml_dirty"])
        pc = xml.section("conditions").find("parts_control")
        self.assertEqual(pc.findtext("Discontinuous"), "true")
        self.assertEqual(pc.findtext("overset"), "true")


    def test_open_cad_and_query_face_vbs(self):
        from automation.pipeline_plan import write_nav_vbs
        with tempfile.TemporaryDirectory() as td:
            cad = Path(td) / "part.step"
            cad.write_text("ISO", encoding="utf-8")
            out = Path(td) / "open.vbs"
            write_nav_vbs(
                "open_cad_file", "box.pph", out,
                draft={"path": str(cad)})
            text = out.read_bytes()
            decoded = (text.decode("utf-16") if text[:2] in (
                b"\xff\xfe", b"\xfe\xff") else text.decode("utf-8"))
            self.assertIn("Doc_.OpenCadFile", decoded)
            q = Path(td) / "q.vbs"
            write_nav_vbs(
                "query_face_region", "box.pph", q,
                draft={"name": "@PartSurface_Part"})
            qt = q.read_bytes()
            qd = (qt.decode("utf-16") if qt[:2] in (
                b"\xff\xfe", b"\xfe\xff") else qt.decode("utf-8"))
            self.assertIn(
                'Doc_.QueryFaceRegionByName("@PartSurface_Part")', qd)


if __name__ == "__main__":
    unittest.main()
