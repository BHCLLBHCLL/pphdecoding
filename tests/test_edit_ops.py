#!/usr/bin/env python3
"""宿主编辑操作 VBS（Ridge / Octant）生成与 GUI 接线回归。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation.edit_ops import (  # noqa: E402
    octant_actions,
    octant_op_label,
    ridge_actions,
    write_octant_vbs,
    write_ridge_vbs,
)
from automation.vbs_bridge import read_vbs_lines  # noqa: E402

FAKE = ROOT / "box.pph"


class TestRidgeVbs(unittest.TestCase):
    def test_recalc_with_angle(self):
        actions = ridge_actions(FAKE, "recalc", angle=30.0)
        text = "\n".join(actions)
        self.assertIn("Set VMDL_ = MeshingGroup_.GetVMDL", text)
        self.assertIn("VMDL_.RecalcRidge 30", text)
        self.assertNotIn("TODO", text)

    def test_recalc_from_project_setting(self):
        actions = ridge_actions(FAKE, "recalc")
        self.assertIn("VMDL_.RecalcRidgeFromProjectSetting", actions)

    def test_set_ridge_selects_all_by_default(self):
        actions = ridge_actions(FAKE, "set")
        text = "\n".join(actions)
        self.assertIn("VMDL_.SetSelectAllEdges(False)", text)
        self.assertIn("VMDL_.SetSelectAllEdges(True)", text)
        self.assertIn("VMDL_.SetSelectedEdgeToRidge", text)

    def test_unset_ridge_with_edge_numbers(self):
        actions = ridge_actions(FAKE, "unset", edge_numbers=[2, 5])
        text = "\n".join(actions)
        self.assertIn("VMDL_.GetEdge(2)", text)
        self.assertIn("VEdge_.SetSelect(True, False)", text)
        self.assertIn("VMDL_.SetSelectedEdgeToNonRidge", text)
        self.assertNotIn("SetSelectAllEdges(True)", text)


class TestOctantVbs(unittest.TestCase):
    def test_refine_merge_show(self):
        for op, call in (
            ("refine", "Octree_.Refine"),
            ("merge", "Octree_.Merge"),
            ("show_by_face", "Octree_.ShowOctBySelectedFace"),
            ("show_by_edge", "Octree_.ShowOctBySelectedEdge"),
        ):
            with self.subTest(op=op):
                actions = octant_actions(FAKE, op)
                text = "\n".join(actions)
                self.assertIn("Set Octree_ = MeshingGroup_.GetOctree", text)
                self.assertIn(call, text)
                self.assertNotIn("TODO", text)

    def test_refine_rec_level_range(self):
        actions = octant_actions(FAKE, "refine_rec", level=2, range_=3)
        self.assertIn("Octree_.RefineByLevel 2, 3", actions)

    def test_refine_num(self):
        actions = octant_actions(FAKE, "refine_num", level=1, num=4)
        self.assertIn("Octree_.RefineByNumber 1, 4", actions)

    def test_refine_curv_arrays(self):
        # P12-A：VBS 整型字面量（如 -1000）在 Array() 中是 VT_I2，原生端
        # 按 double 读数组会 AV——生成器必须产出恒带小数点的 Double 字面量。
        actions = octant_actions(
            FAKE, "refine_curv",
            rmin=[0.0, 0.1, 0.2], rmax=[0.1, 0.2, 0.3], lowerlimit=30.0)
        text = "\n".join(actions)
        self.assertIn("rmin_ = Array(0.0, 0.1, 0.2)", text)
        self.assertIn("rmax_ = Array(0.1, 0.2, 0.3)", text)
        self.assertIn("Octree_.RefineFromCurvature rmin_, rmax_, 30.0", text)

    def test_separation_not_supported(self):
        self.assertIsNone(octant_op_label("refine_sep"))
        with self.assertRaises(ValueError):
            octant_actions(FAKE, "refine_sep")

    def test_requires_level_for_refine_rec(self):
        with self.assertRaises(ValueError):
            octant_actions(FAKE, "refine_rec", level=1)


class TestWriteVbs(unittest.TestCase):
    def test_write_ridge_vbs_with_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ridge.vbs"
            marker = Path(tmp) / "ridge.done"
            write_ridge_vbs(FAKE, "recalc", out, angle=45.0, marker=marker)
            lines = read_vbs_lines(out)
            self.assertTrue(any("RecalcRidge 45" in ln for ln in lines))
            self.assertTrue(any(marker.name in ln for ln in lines))

    def test_write_octant_vbs_utf16(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "oct.vbs"
            write_octant_vbs(FAKE, "show_by_face", out)
            raw = out.read_bytes()
            self.assertTrue(raw.startswith(b"\xff\xfe"))
            lines = read_vbs_lines(out)
            self.assertTrue(any("ShowOctBySelectedFace" in ln
                                for ln in lines))

    def test_host_edit_vbs_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "edit.vbs"
            write_octant_vbs(FAKE, "show_all", out)
            lines = read_vbs_lines(out)
            self.assertIn("Set Doc_ = App_.GetDocument", lines)
            self.assertIn("Doc_.OpenProject", lines[3])
            self.assertIn("Octree_.ShowAll", lines)


class TestGuiWiring(unittest.TestCase):
    def test_rubber_select_real_handlers(self):
        src = (ROOT / "pph_gui.py").read_text(encoding="utf-8")
        for needle in (
            "def _rubber_select(self, kind: str = \"box\")",
            "def _rubber_select_cells",
            "def _rubber_apply_region",
            "def _toggle_rubber_select",
            "class _RubberPolygonOverlay",
            "vtkHardwareSelector",
            "QRubberBand",
        ):
            self.assertIn(needle, src, needle)

    def test_ridge_no_longer_todo(self):
        src = (ROOT / "pph_gui.py").read_text(encoding="utf-8")
        self.assertNotIn("RecalcRidge API 待录制锁定", src)
        self.assertIn("VMDL_.RecalcRidge / RecalcRidgeFromProjectSetting",
                      src)


if __name__ == "__main__":
    unittest.main()
