#!/usr/bin/env python3
"""P12-D 实机编排生成器回归（离线，不触宿主）。"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "_p12d_e2e_run", ROOT / "tools" / "_p12d_e2e_run.py")
p12d = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p12d)


class TestRegionFlows(unittest.TestCase):
    def test_region_actions(self):
        actions = p12d.build_region_groups()[0][1]
        self.assertEqual([n for n, _ in p12d.build_region_groups()],
                         ["region"])
        joined = "\n".join(actions)
        self.assertIn('Doc_.CreateFaceRegion("' + p12d.REGION_NAME + '")',
                      joined)
        self.assertIn('Doc_.QueryFaceRegionByName("'
                      + p12d.REGION_NAME + '")', joined)
        # 负面对照（预期 Nothing，仅记录不作 gate）
        self.assertIn('Doc_.QueryFaceRegionByName("'
                      + p12d.REGION_ABSENT + '")', joined)
        self.assertIn(p12d.BOX.name, joined)
        self.assertIn(p12d.REGION_OUT.as_posix(), joined)

    def test_region_reopen_actions(self):
        actions = p12d.build_region_reopen_groups()[0][1]
        joined = "\n".join(actions)
        self.assertIn(p12d.REGION_OUT.as_posix(), joined)
        self.assertIn('Doc_.QueryFaceRegionByName("'
                      + p12d.REGION_NAME + '")', joined)

    def test_no_array_literals(self):
        # P12-A 钉死：Array() 整型字面量（VT_I2）会致原生端 AV
        for build in (p12d.build_region_groups,
                      p12d.build_region_reopen_groups,
                      p12d.build_facet_groups):
            for a in build()[0][1]:
                self.assertNotIn("= Array(", a)


class TestSnodeReplay(unittest.TestCase):
    @unittest.skipUnless(p12d.MDL_REC.is_file(), "BAM recording missing")
    def test_replay_transform(self):
        groups = p12d.build_snode_groups()
        self.assertEqual([n for n, _ in groups], ["snode"])
        actions = groups[0][1]
        self.assertGreater(len(actions), 2600)
        stripped = [a.strip() for a in actions]
        # On Error Goto 0 全部替换为 Resume Next（防模态卡死）
        self.assertNotIn("On Error Goto 0", stripped)
        self.assertIn("On Error Resume Next", stripped)
        # SNode 注入紧跟 OpenCadFile：CreateGroupPart 前探针 + 录制
        # 自身验证过的 QuerySNodeByName("Part") 路线（闸门键 SN2_）
        i_cad = stripped.index("Doc_.OpenCadFile Param1_")
        self.assertIn('Set GP_ = Doc_.CreateGroupPart("'
                      + p12d.REGION_NAME + 'Group")', stripped)
        self.assertIn('Set SN2_ = Doc_.QuerySNodeByName("Part")', stripped)
        self.assertGreater(stripped.index('Set SN2_ = '
                                          'Doc_.QuerySNodeByName("Part")'),
                           i_cad)
        # AFFaceter 前置于首个 BeginMDLWizard（P12-A 崩溃先例）
        i_wiz = stripped.index("MeshingGroup_.BeginMDLWizard")
        self.assertLess(stripped.index("Proj_.SetUseAFFacetter Param1_"),
                        i_wiz)
        self.assertIn(stripped[i_wiz], "MeshingGroup_.BeginMDLWizard")
        # CreateMDL 返回值捕获（void 方法实测记录，info 仅存档）
        i_mdl = stripped.index("RetMdl_ = MDLWizard_.CreateMDL")
        self.assertNotIn("MDLWizard_.CreateMDL", stripped)
        self.assertIn('out_.WriteLine "create_mdl=" & CStr(RetMdl_) '
                      '& " err=" & CStr(Err.Number)', stripped)
        # 后探针（wizard 完成后的文档上下文）在捕获之后
        self.assertIn('Set GP2_ = Doc_.CreateGroupPart("'
                      + p12d.REGION_NAME + 'Group2")', stripped)
        self.assertGreater(stripped.index('Set GP2_ = Doc_.CreateGroupPart("'
                                          + p12d.REGION_NAME + 'Group2")'),
                           i_mdl)
        # SaveProject 重定向 + VMDL.Save 显式导出（P12-A 权威路径）
        saves = [a for a in stripped if a.startswith("Doc_.SaveProject")]
        self.assertEqual(saves,
                         ['Doc_.SaveProject "' + p12d.SNODE_OUT.as_posix()
                          + '"'])
        self.assertIn('RetVx_ = VMDLx_.Save("'
                      + p12d.SNODE_MDL.as_posix() + '")', stripped)

    @unittest.skipUnless(p12d.MDL_REC.is_file(), "BAM recording missing")
    def test_no_array_literals(self):
        for a in p12d.build_snode_groups()[0][1]:
            self.assertNotIn("= Array(", a)


class TestFacetFlow(unittest.TestCase):
    def test_actions(self):
        actions = p12d.build_facet_groups()[0][1]
        joined = "\n".join(actions)
        self.assertIn(p12d.BOX.name, joined)
        self.assertIn("Set MG4_ = Doc_.CreateMeshingGroup", joined)
        self.assertIn('Doc_.ImportCADAsFacet "' + p12d.XT.as_posix()
                      + '", MG4_', joined)
        self.assertIn(p12d.FACET_OUT.as_posix(), joined)


class TestPatchFlow(unittest.TestCase):
    @unittest.skipUnless(p12d.PATCH_STL.is_file(), "STL sample missing")
    def test_actions(self):
        actions = p12d.build_patch_groups()[0][1]
        joined = "\n".join(actions)
        self.assertIn(p12d.BOX.name, joined)
        self.assertIn('Set SN5_ = Doc_.ImportPatchAsCAD "'
                      + p12d.PATCH_STL.as_posix() + '"', joined)
        self.assertIn(p12d.PATCH_OUT.as_posix(), joined)
        # P12-A 钉死：Array() 整型字面量（VT_I2）会致原生端 AV
        for a in actions:
            self.assertNotIn("= Array(", a)


class TestVerifyLog(unittest.TestCase):
    def test_zero_errors(self):
        text = ("start\ns001=0\napp__alive=True err=0\n"
                "create_mdl=True err=0\nend\n")
        v = p12d.verify_log(text)
        self.assertEqual(v["bad"], 0)
        self.assertEqual(v["total"], 3)
        self.assertTrue(v["has_end"])
        self.assertEqual(v["info"], {"create_mdl": "True"})
        self.assertEqual(v["alive"], {"app_": "True"})

    def test_bad_and_unparsed(self):
        text = "start\ns001=5\ns002=0\ngarbage line\nend\n"
        v = p12d.verify_log(text)
        self.assertEqual(v["bad"], 1)
        self.assertEqual(v["problems"][0], "s001=5")
        self.assertTrue(any("unparsed" in p for p in v["problems"]))


if __name__ == "__main__":
    unittest.main()
