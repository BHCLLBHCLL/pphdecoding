#!/usr/bin/env python3
"""PipelinePlan / VBS 验收脚本测试。"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation.pipeline_plan import PipelinePlan  # noqa: E402
from automation.vbs_bridge import read_vbs_lines  # noqa: E402

BOX_PPH = ROOT / "box.pph"


class TestPipelinePlan(unittest.TestCase):
    def test_to_vbs_actions(self):
        plan = PipelinePlan(project_path=r"C:\case\case.pph",
                            steps=["prepare_parts", "build_analysis_model"])
        actions = plan.to_vbs_actions()
        self.assertEqual(actions[0], 'scFLOWpre.OpenProject "C:\\case\\case.pph"')
        self.assertIn("scFLOWpre.ReturnToPrepareParts", actions)
        self.assertIn("scFLOWpre.BuildAnalysisModel", actions)
        self.assertNotIn("scFLOWpre.Quit", actions)

    def test_custom_commands(self):
        plan = PipelinePlan(
            project_path="case.pph",
            steps=["build_analysis_model"],
            commands={"build_analysis_model": "scFLOWpre.BAM"})
        self.assertEqual(plan.to_vbs_actions(),
                         ['scFLOWpre.OpenProject "case.pph"', "scFLOWpre.BAM"])

    def test_unknown_step(self):
        plan = PipelinePlan(project_path="case.pph", steps=["nope"])
        with self.assertRaises(ValueError):
            plan.to_vbs_actions()

    def test_write_read(self):
        plan = PipelinePlan(project_path="case.pph",
                            steps=["generate_mesh"], include_quit=True)
        with tempfile.TemporaryDirectory() as td:
            p = plan.write_vbs(Path(td) / "plan.vbs")
            lines = read_vbs_lines(p)
        self.assertIn('scFLOWpre.OpenProject "case.pph"', lines)
        self.assertIn("scFLOWpre.GenerateMesh", lines)
        self.assertIn("scFLOWpre.Quit", lines)

    def test_verify_outputs(self):
        plan = PipelinePlan(project_path=str(BOX_PPH))
        result = plan.verify_outputs()
        self.assertGreaterEqual(result["role_counts"]["mdl"], 1)
        self.assertGreaterEqual(result["role_counts"]["oct"], 1)
        self.assertGreaterEqual(result["role_counts"]["gph"], 1)


if __name__ == "__main__":
    unittest.main()
