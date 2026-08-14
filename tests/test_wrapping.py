#!/usr/bin/env python3
"""Wrapping（从 x_t 曲面）API / 原生流程回归。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation.history_vbs import decode_vbs, parse_history_file  # noqa: E402
from automation.pipeline_plan import (  # noqa: E402
    LOCKED_COMMANDS,
    build_execute_vbs,
    steps_from_execute_plan,
    wrapping_actions,
)

WRAP_VBS = ROOT / "box_scflow_wrapping.vbs"


class TestWrappingLocked(unittest.TestCase):
    @unittest.skipUnless(WRAP_VBS.is_file(), "box_scflow_wrapping.vbs missing")
    def test_recording_sequence_locked(self):
        cmds = {a["command"] for a in parse_history_file(str(WRAP_VBS))}
        for cmd in (
            "Doc_.BeginWrapping",
            "Doc_.CreateWrappingGroup",
            "WrappingGroup_.CreateOctree",
            "WrappingGroup_.ExecuteWrapping",
            "Octree_.UpdateGroups",
            "Doc_.EndWrapping",
            "WrappingParam_.SetMethod",
            "WrappingParam_.SetOutsideType",
        ):
            self.assertIn(cmd, cmds, cmd)
        template = LOCKED_COMMANDS["begin_wrapping"]
        for cmd in (
            "Doc_.BeginWrapping",
            "WrappingGroup_.CreateOctree",
            "WrappingGroup_.ExecuteWrapping",
            "Doc_.EndWrapping",
        ):
            self.assertIn(cmd, template)
        self.assertNotIn("TODO", template)

    def test_steps_from_execute_plan(self):
        self.assertEqual(steps_from_execute_plan({"wrapping": True}),
                         ["begin_wrapping"])
        self.assertEqual(
            steps_from_execute_plan({"wrapping": True, "oct": True}),
            ["begin_wrapping", "generate_octree", "set_mode_octree"])
        self.assertEqual(
            steps_from_execute_plan({"bam": True, "oct": True,
                                     "mesh": True}),
            ["build_analysis_model",
             "generate_octree", "set_mode_octree",
             "generate_mesh", "set_mode_mesh"])

    def test_wrapping_actions_standalone(self):
        for op in ("begin_wrap", "exec_wrap", "retry_wrap",
                   "cancel_wrap", "wrap_octree", "wrap_param"):
            actions = wrapping_actions(op, r"D:\case\box.x_t")
            self.assertIn("Set Doc_ = App_.GetDocument", actions)
            self.assertIn('Doc_.OpenProject "D:/case/box.x_t", False',
                          actions)
        begin = "\n".join(wrapping_actions("begin_wrap", r"D:\case\box.x_t"))
        self.assertIn("Doc_.BeginWrapping", begin)
        self.assertIn("WrappingGroup_.ExecuteWrapping", begin)
        self.assertIn("Doc_.EndWrapping", begin)
        self.assertNotIn("TODO", begin)
        cancel = "\n".join(wrapping_actions("cancel_wrap", r"D:\case\box.x_t"))
        self.assertIn("Doc_.CancelWrapping", cancel)

    def test_build_execute_vbs_wrapping_order(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "wrap.vbs"
            build_execute_vbs(
                r"D:\case\box.x_t",
                {"wrapping": True, "oct": True, "mesh": True},
                out)
            text = decode_vbs(out.read_bytes())
            self.assertLess(text.index("Doc_.BeginWrapping"),
                            text.index("Doc_.EndWrapping"))
            self.assertLess(text.index("Doc_.EndWrapping"),
                            text.index("MeshingGroup_.CreateOctree"))
            self.assertLess(text.index("MeshingGroup_.CreateOctree"),
                            text.index("MeshingGroup_.CreateMeshMonitor"))
            self.assertNotIn("TODO", text)


class TestWrappingGuiWiring(unittest.TestCase):
    def test_execute_dialog_has_wrapping(self):
        src = (ROOT / "nav_panels.py").read_text(encoding="utf-8")
        self.assertIn("Wrapping (from CAD)", src)
        self.assertIn("self.chk_wrap", src)
        self.assertIn('"wrapping": self.chk_wrap.isChecked()', src)

    def test_native_flow_writes_wrap_mdl(self):
        src = (ROOT / "pph_gui.py").read_text(encoding="utf-8")
        self.assertIn("def _native_wrap_member_name", src)
        self.assertIn("meshinggroup1_wrap.mdl", src)
        self.assertIn("Wrapping(CAD→MDL)", src)


if __name__ == "__main__":
    unittest.main()
