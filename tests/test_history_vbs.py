#!/usr/bin/env python3
"""history.vbs 录制解析测试。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation.history_vbs import actions_to_hints, parse_history  # noqa: E402

SAMPLE = """
' scFLOWpre history
scFLOWpre.NewProject "case1"
Call scFLOWpre.ImportPartFile("C:\\cad\\part.x_t", 1)
scFLOWpre.SetOctreeParameter "facet_angle", 5
scFLOWpre.ExecuteWrapping _
  , True
scFLOWpre.Quit
Rem end
"""


class TestParseHistory(unittest.TestCase):
    def test_parse(self):
        actions = parse_history(SAMPLE)
        self.assertEqual(
            [a["command"] for a in actions],
            ["scFLOWpre.NewProject", "scFLOWpre.ImportPartFile",
             "scFLOWpre.SetOctreeParameter", "scFLOWpre.ExecuteWrapping",
             "scFLOWpre.Quit"])

    def test_args(self):
        actions = parse_history(SAMPLE)
        self.assertEqual(actions[0]["args"], ['"case1"'])
        self.assertEqual(actions[1]["args"],
                         ['"C:\\cad\\part.x_t"', "1"])
        self.assertEqual(actions[3]["args"], ["True"])

    def test_continuation_join(self):
        actions = parse_history(SAMPLE)
        self.assertEqual(len(actions), 5)

    def test_hints(self):
        hints = actions_to_hints(parse_history(SAMPLE))
        self.assertEqual(hints["scFLOWpre.Quit"]["count"], 1)
        self.assertIn("scFLOWpre.NewProject", hints)


if __name__ == "__main__":
    unittest.main()
