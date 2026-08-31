#!/usr/bin/env python3
"""P12-F 实机编排生成器回归（离线，不触宿主）。"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "_p12f_e2e_run", ROOT / "tools" / "_p12f_e2e_run.py")
p12f = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p12f)


class TestP12fFlows(unittest.TestCase):
    def test_flows_content(self):
        for which in p12f.FLOWS:
            groups = p12f.build_groups(which)
            name, actions = groups[0]
            self.assertEqual(name, which)
            text = p12f.logged_script(groups, Path("D:/log/l.log"), "t")
            joined = [a.strip() for a in text]
            self.assertIn('out_.WriteLine "start"', joined)
            self.assertIn('out_.WriteLine "end"', joined)
            self.assertTrue(any(a.startswith("Doc_.OpenProject")
                                for a in joined), which)
            # 每 flow 源工程独立（OpenProject 挂起配方）
            opens = [a for a in joined if a.startswith("Doc_.OpenProject")]
            self.assertEqual(len(opens), 1, which)
            self.assertIn("p12f_" + which + "_in.pph", opens[0])

    def test_flow_specific_apis(self):
        facet = [a for _, acts in p12f.build_groups("facet") for a in acts]
        self.assertIn("Set MG_ = Doc_.CreateMeshingGroup", facet)
        self.assertTrue(any(a.startswith("Doc_.ImportCADAsFacet ")
                            for a in facet))
        coord = [a for _, acts in p12f.build_groups("coord") for a in acts]
        self.assertIn(
            'Set CP_ = Doc_.CreateCoordinatesSpecifiedPart("'
            + p12f.COORD_NAME + '")', coord)
        submesh = [a for _, acts in p12f.build_groups("submesh")
                   for a in acts]
        self.assertIn(
            'Set SM_ = Doc_.CreateSubmeshMeshingGroup("'
            + p12f.SUBMESH_NAME + '")', submesh)
        fix = [a for _, acts in p12f.build_groups("fix") for a in acts]
        self.assertIn("fix_ret_ = MG_.FixMarkedElements", fix)
        self.assertTrue(any('out_.WriteLine "fix_ret=' in a for a in fix))
        actran = [a for _, acts in p12f.build_groups("actran")
                  for a in acts]
        self.assertTrue(any("CreateActranFilesMonitor" in a for a in actran))
        self.assertTrue(any('out_.WriteLine "actran_ret=' in a
                            for a in actran))

    def test_in_paths_copy_targets(self):
        for which in p12f.FLOWS:
            p = p12f.PATHS[which]
            self.assertTrue(p["in"].name.startswith("p12f_" + which + "_in"))
            self.assertTrue(p["out"].name.startswith(
                "p12f_" + which + "_out"))


class TestP12fVerifyLog(unittest.TestCase):
    def test_verify(self):
        text = ("start\n"
                "s001=0\n"
                "mg__alive=True err=0\n"
                "fix_ret=True err=0\n"
                "actran_ret=True err=0\n"
                "actran_files=4 err=0\n"
                "end\n")
        v = p12f.verify_log(text)
        self.assertEqual(v["total"], 5)
        self.assertEqual(v["err0"], 5)
        self.assertEqual(v["bad"], 0)
        self.assertTrue(v["has_end"])
        self.assertEqual(v["alive"], {"mg_": "True"})
        self.assertEqual(v["info"], {"fix_ret": "True",
                                     "actran_ret": "True",
                                     "actran_files": "4"})

    def test_verify_bad(self):
        v = p12f.verify_log("start\ns001=0\ns002=-5\njunk\nend\n")
        self.assertEqual(v["bad"], 1)
        self.assertTrue(v["problems"])


if __name__ == "__main__":
    unittest.main()
