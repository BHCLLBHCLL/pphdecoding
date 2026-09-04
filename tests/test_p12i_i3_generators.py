#!/usr/bin/env python3
"""P12-I I3 生成器回归（离线，不触宿主）。

场景依据：宿主帮助页 Scf_pre_Edit-Restore_Closed_Volume_Data.html
（2025.2）——菜单仅限「patch 已导入 + 另一 patch 再导入时选
[Store and Open]」；r2 基座 = r1 产物 cv1_out（2025.2 宿主自存，
patch① 导入史 + 闭体积存储史继承），cvrestore 执行再导入腿。
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "_p12i_i3_run", ROOT / "tools" / "_p12i_i3_run.py")
i3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(i3)


class TestCvstoreFlow(unittest.TestCase):
    def setUp(self):
        self.acts = i3.build_cvstore_groups()[0][1]
        self.joined = "\n".join(self.acts)

    def test_base_is_r1_artifact_no_reimport(self):
        # 基座 = 2025.2 宿主自存的 r1 产物（patch① 导入史 + 存储史
        # 继承；box.pph 的 2023.2 CAB Confirm 弹窗由此根除）
        self.assertIn('Doc_.OpenProject "' + i3.CV1_OUT.as_posix()
                      + '", False', self.acts)
        self.assertNotIn("ImportPatchAsCAD", self.joined)

    def test_recognize_and_store(self):
        self.assertIn("MG_.RecognizeClosedVolume False", self.acts)
        self.assertIn("Set MDL_ = MG_.GetMDL", self.acts)
        self.assertIn("Av0_ = MDL_.IsClosedVolumeRestorationAvailable",
                      self.acts)
        self.assertIn("SRet_ = MDL_.StoreClosedVolumes()", self.acts)
        self.assertIn("MDL_.GetStoredClosedVolumes(False)", self.joined)

    def test_save_redirect(self):
        saves = [a for a in self.acts
                 if a.strip().startswith("Doc_.SaveProject")]
        self.assertEqual(saves,
                         ['Doc_.SaveProject "'
                          + i3.CV1B_OUT.as_posix() + '"'])


class TestCvrestoreFlow(unittest.TestCase):
    def setUp(self):
        self.acts = i3.build_cvrestore_groups()[0][1]
        self.joined = "\n".join(self.acts)

    def test_reimport_then_store_and_open(self):
        # 帮助前置②：另一 patch 再导入 + [Store and Open]（Save+Open 等价）
        self.assertIn('Set SN6_ = Doc_.ImportPatchAsCAD("', self.joined)
        self.assertIn(i3.PATCH2.as_posix(), self.joined)
        self.assertIn('Doc_.SaveProject "' + i3.CV2B_OUT.as_posix() + '"',
                      self.acts)
        self.assertIn('Doc_.OpenProject "'
                      + i3.CV2B_OUT.as_posix() + '", False', self.acts)
        # 再导入必须先于 Store-and-Open 重开
        self.assertLess(self.joined.index("ImportPatchAsCAD"),
                        self.joined.index("Doc_.OpenProject"))

    def test_reimport_rebuilds_mdl(self):
        # r2 钉死：ImportPatchAsCAD = 组内换件（<mdl> 重置、成员落盘
        # 滞后）——导入后须 WaitForWorker + RecognizeClosedVolume
        # 重建 MDL，重开后同（cvstore 的 GetMDL 成功相关性实证）
        self.assertIn("RetWW2_ = Doc_.WaitForWorker", self.acts)
        self.assertIn("MG1_.RecognizeClosedVolume False", self.acts)
        self.assertIn("Set MD1_ = MG1_.GetMDL", self.acts)
        self.assertLess(self.acts.index("MG1_.RecognizeClosedVolume False"),
                        self.acts.index('Doc_.SaveProject "'
                                        + i3.CV2B_OUT.as_posix() + '"'))
        self.assertLess(self.acts.index("MG2_.RecognizeClosedVolume False"),
                        self.acts.index("Set MD2_ = MG2_.GetMDL"))

    def test_reopen_lag_requery(self):
        # I2 reopen 教训：MDL 成员恢复滞后 → ping 退避 + 单行重查
        self.assertIn("If MD2_ Is Nothing Then Set MD2_ = MG2_.GetMDL",
                      self.acts)
        self.assertGreaterEqual(
            self.joined.count("cmd /c ping -n 6 127.0.0.1 > nul"), 5)

    def test_restoration_probes_and_pairs(self):
        self.assertIn("Av1_ = MD2_.IsClosedVolumeRestorationAvailable",
                      self.acts)
        self.assertIn("MD2_.GetRestorationCandidateOfClosedVolume(LB0_, True)",
                      self.joined)
        # CVolPairs 构造：Dim+Set（禁 Array() 整型字面量，VT_I2 AV 教训）
        self.assertIn("Dim Pairs_(1)", self.acts)
        self.assertIn("Set Pairs_(0) = Dest_", self.acts)
        self.assertIn("Set Pairs_(1) = Src_", self.acts)
        self.assertIn("RRet_ = MD2_.RestoreClosedVolumes(True, Pairs_)",
                      self.acts)
        self.assertNotIn("= Array(", self.joined)
        self.assertIn("restore_ret=", self.joined)


class TestComposition(unittest.TestCase):
    def test_logged_script_wraps_and_ansi_encodable(self):
        for groups, title in (
                (i3.build_cvstore_groups(), "i3 cvstore"),
                (i3.build_cvrestore_groups(), "i3 cvrestore"),):
            lines = i3.p12e.logged_script(groups, i3.CVSTORE_LOG, title)
            self.assertEqual(lines[1], "On Error Resume Next")
            self.assertEqual(lines[-2], "out_.WriteLine \"end\"")
            s_lines = [x for x in lines if x.startswith("out_.WriteLine \"s")]
            self.assertGreater(len(s_lines), 10)
            text = "\r\n".join(lines)
            text.encode("mbcs")  # ANSI 通道可编码（P12-E 实测钉死）

    def test_verify_log_accepts_guard_lines(self):
        sample = ("start\ns001=0\ncvs_ub=3 err=0\ncvs_ub=NA err=0\n"
                  "av1=True err=0\nrestore_ret=True err=0\nend")
        v = i3.p12e.verify_log(sample)
        self.assertEqual(v["bad"], 0)
        self.assertTrue(v["has_end"])


class TestBusinessState(unittest.TestCase):
    def test_states(self):
        self.assertEqual(i3.business_state(
            {"av1": "True", "restore_ret": "True"}), 1)
        self.assertEqual(i3.business_state(
            {"av1": "True", "restore_ret": "False"}), 0)
        self.assertEqual(i3.business_state({"av1": "False"}), -1)
        self.assertEqual(i3.business_state({}), -1)

    def test_business_info_parse(self):
        text = ("start\ns001=0\nav0=False err=0\nstore_ret=True err=0\n"
                "av1=True err=0\nrestore_ret=True err=0\nend")
        info = i3.business_info(text)
        self.assertEqual(info["av0"], "False")
        self.assertEqual(info["store_ret"], "True")
        self.assertEqual(info["restore_ret"], "True")
        # sNNN 行不进 info
        self.assertNotIn("s001", info)


if __name__ == "__main__":
    unittest.main()
