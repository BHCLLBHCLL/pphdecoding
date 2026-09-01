#!/usr/bin/env python3
"""P12-E 实机编排生成器回归（离线，不触宿主）。"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "_p12e_e2e_run", ROOT / "tools" / "_p12e_e2e_run.py")
p12e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p12e)


class TestWrapReplay(unittest.TestCase):
    @unittest.skipUnless(p12e.WRAP_REC.is_file(),
                         "wrapping recording missing")
    def test_replay_transform(self):
        groups = p12e.build_wrap_groups()
        self.assertEqual([n for n, _ in groups], ["wrap"])
        actions = groups[0][1]
        self.assertGreater(len(actions), 3000)
        # On Error Goto 0 全部替换为 Resume Next（防模态卡死，P12-A 先例）
        self.assertNotIn("On Error Goto 0", [a.strip() for a in actions])
        self.assertIn("On Error Resume Next", [a.strip() for a in actions])
        # SaveProject 重定向到 P12-E 证据路径
        saves = [a for a in actions if a.strip().startswith("Doc_.SaveProject")]
        self.assertTrue(saves)
        for s in saves:
            self.assertIn(p12e.WRAP_OUT.as_posix(), s)
        # 锁定序列骨架（录制 :717-1095 实测）
        joined = [a.strip() for a in actions]
        self.assertIn("WrappingGroup_.CreateOctree", joined)
        self.assertIn("WrappingGroup_.ExecuteWrapping", joined)
        self.assertIn("Doc_.EndWrapping", joined)

    @unittest.skipUnless(p12e.WRAP_REC.is_file(),
                         "wrapping recording missing")
    def test_no_array_literals(self):
        # P12-A 钉死：Array() 整型字面量（VT_I2）会致原生端 AV
        groups = p12e.build_wrap_groups()
        for a in groups[0][1]:
            self.assertNotIn("= Array(", a)


class TestMeshFlow(unittest.TestCase):
    def test_actions(self):
        actions = p12e.build_mesh_groups()[0][1]
        joined = "\n".join(actions)
        self.assertIn("OpenProject", joined)
        self.assertIn(p12e.BAM_OUT.name, joined)
        self.assertIn("MG_.CreateMesh", joined)
        self.assertIn("Doc_.WaitForWorker", joined)
        self.assertIn("create_ret=", joined)
        self.assertIn(p12e.MESH_OUT.as_posix(), joined)


class TestGroupFlows(unittest.TestCase):
    def test_disc(self):
        joined = "\n".join(p12e.build_disc_groups()[0][1])
        self.assertIn("CreateDiscontinuousMeshingGroupWithMovingPart", joined)
        self.assertIn('SetPartsControl "Discontinuous", True', joined)
        self.assertIn(p12e.DISC_OUT.as_posix(), joined)

    def test_overset(self):
        joined = "\n".join(p12e.build_overset_groups()[0][1])
        self.assertIn(
            "CreateDiscontinuousMeshingGroupWithoutMovingPart", joined)
        self.assertIn(p12e.OVERSET_OUT.as_posix(), joined)

    def test_reopen(self):
        joined = "\n".join(p12e.build_reopen_groups()[0][1])
        self.assertIn(p12e.WRAP_OUT.as_posix(), joined)
        self.assertIn("MG_.GetOctree", joined)

    def test_xt(self):
        joined = "\n".join(p12e.build_xt_groups()[0][1])
        self.assertIn("ConvertFacetToXT", joined)
        self.assertIn(p12e.BAM_MDL.name, joined)
        self.assertIn("pipe_exc=", joined)
        # 2026-09-01 复测钉死：符号表惰性初始化前转换逐次 -1，
        # priming（ContextReady + Status）必须先于 ConvertFacetToXT。
        self.assertLess(joined.index("Pipe_.Status"),
                        joined.index("ConvertFacetToXT"))
        self.assertLess(joined.index("Pipe_.ContextReady"),
                        joined.index("ConvertFacetToXT"))
        # Status 多行只落长度（st_len），不直接进日志行流
        self.assertIn("st_len=", joined)
        self.assertNotIn("out_.WriteLine st_", joined)


class TestVerifyLog(unittest.TestCase):
    def test_all_zero(self):
        v = p12e.verify_log("start\ns001=0\ns002=0\nend")
        self.assertEqual(v["total"], 2)
        self.assertEqual(v["bad"], 0)
        self.assertTrue(v["has_end"])

    def test_bad_code_and_info(self):
        v = p12e.verify_log(
            "start\ns001=0\ns002=-2147023174\n"
            "xt_ec=202 err=0\nxt_exists=True err=0\npipe_exc=0 err=0\nend")
        self.assertEqual(v["bad"], 1)
        self.assertEqual(v["info"]["xt_ec"], "202")
        self.assertEqual(v["info"]["xt_exists"], "True")

    def test_alive_capture(self):
        v = p12e.verify_log("s001=0\nmg2_alive=True err=0\nend")
        self.assertEqual(v["alive"]["mg2"], "True")


if __name__ == "__main__":
    unittest.main()
