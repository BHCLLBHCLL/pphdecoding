#!/usr/bin/env python3
"""P12-M J1 生成器回归（离线，不触宿主）。

场景依据：I3（§20.7）+ 本轮容器勘验——ImportPatchAsCAD 换件丢存储
（cv2b 无 .his）→ 恢复腿 = 同几何 STL 再导入 + Wizard 最小核重建 +
.his 写回注入 + Store-and-Open 等价重开。"""
from __future__ import annotations

import importlib.util
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "_p12m_j1_run", ROOT / "tools" / "_p12m_j1_run.py")
j1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(j1)


class TestWizardCore(unittest.TestCase):
    def setUp(self):
        self.core = j1.WIZARD_CORE
        self.joined = "\n".join(self.core)

    def test_mirrors_recording_shape(self):
        # box_scflow_mdl.vbs :351-528 形态：单遍 Begin/End 配对
        self.assertEqual(self.core[0], "MeshingGroup_.BeginMDLWizard")
        self.assertEqual(self.core[-1], "MeshingGroup_.EndMDLWizard")
        self.assertEqual(
            self.joined.count("BeginMDLWizard"), 1)
        self.assertEqual(
            self.joined.count("EndMDLWizard"), 1)

    def test_single_entity_adaptation(self):
        # 换件场景单实体：CreateMultiEntityInfo ×6→×1
        self.assertEqual(
            self.joined.count("MDLWizard_.CreateMultiEntityInfo"), 1)

    def test_model_build_and_repair_chain(self):
        for call in ("MDLWizard_.CreateBoundary",
                     "MDLWizard_.CreateMDL",
                     "MDLWizard_.FindAFFaceMatching Param1_",
                     "MDLWizard_.SetFaceMatched",
                     "MDLWizard_.FindTinyFace Param1_",
                     "MDLWizard_.SetTinyFacesRemoved",
                     "MDLWizard_.RepairMDL",
                     "MDLWizard_.CheckMDLErrors"):
            self.assertIn(call, self.joined)

    def test_no_iif(self):
        # I2 纪律：IIf 两分支皆求值，禁用
        self.assertNotIn("IIf", self.joined)


class TestWizFlow(unittest.TestCase):
    def setUp(self):
        self.acts = j1.build_wiz_groups()[0][1]
        self.joined = "\n".join(self.acts)

    def test_base_and_same_geometry_reimport(self):
        self.assertIn('Doc_.OpenProject "' + j1.CV1B.as_posix()
                      + '", False', self.acts)
        self.assertIn('Set SN6_ = Doc_.ImportPatchAsCAD("'
                      + j1.PATCH2.as_posix() + '")', self.acts)

    def test_af_prelude_before_wizard(self):
        # P12-A 教训：FindAFFaceMatching 无 faceter 时 RPC_E_SERVERFAULT
        # → SetUseAFFacetter 必须先于 BeginMDLWizard 至少一次
        prelude = self.acts.index("Proj_.SetUseAFFacetter Param1_")
        begin = self.acts.index("MeshingGroup_.BeginMDLWizard")
        self.assertLess(prelude, begin)

    def test_meshinggroup_alias_before_core(self):
        # r3 教训：WIZARD_CORE 沿用录制变量名 MeshingGroup_，未赋值
        # 时全段 424 Object required 静默失败
        alias = self.acts.index("Set MeshingGroup_ = MGW_")
        self.assertLess(
            alias, self.acts.index("MeshingGroup_.BeginMDLWizard"))

    def test_embed_tail_before_save(self):
        # p12a/p12e 实证：模型状态经 main.sctsnapshot 内嵌需
        # CreateOctree + CreateMeshMonitor + WaitForWorker 后存盘
        save = self.acts.index('Doc_.SaveProject "'
                               + j1.WIZ_OUT.as_posix() + '"')
        octree = self.acts.index("MGO_.CreateOctree")
        monitor = self.acts.index("MGM_.CreateMeshMonitor")
        wait = self.acts.index("RetWW3_ = Doc_.WaitForWorker")
        self.assertLess(octree, save)
        self.assertLess(monitor, save)
        self.assertLess(wait, save)

    def test_store_probe_preset(self):
        # 换件后存储源预期为空（.his 被 API 换件丢弃）——探针在位
        self.assertIn("MDL2_.GetStoredClosedVolumes(False)", self.joined)
        self.assertIn("Av0_ = MDL2_.IsClosedVolumeRestorationAvailable",
                      self.joined)


class TestRestoreFlow(unittest.TestCase):
    def setUp(self):
        self.acts = j1.build_restore_groups()[0][1]
        self.joined = "\n".join(self.acts)

    def test_reopen_injected_container(self):
        self.assertIn('Doc_.OpenProject "' + j1.RESTORE_IN.as_posix()
                      + '", False', self.acts)

    def test_restore_chain_shape(self):
        self.assertIn("MD2_.GetStoredClosedVolumes(False)", self.joined)
        self.assertIn("Av1_ = MD2_.IsClosedVolumeRestorationAvailable",
                      self.joined)
        # catalog：候选查询返回 VARIANT 数组，Set 接收必 424（r6 教训）
        self.assertIn(
            "Cand_ = MD2_.GetRestorationCandidateOfClosedVolume("
            "LB0_, True)", self.acts)
        self.assertIn("If IsArray(Cand_) Then", self.joined)
        self.assertNotIn("Set Cand_", self.joined)

    def test_cvol_pairs_dim_set_construction(self):
        # Array() 整型字面量 VT_I2 AV 教训 → Dim+Set 对数组
        self.assertIn("Dim Pairs_(1)", self.acts)
        self.assertIn("Set Pairs_(0) = Dest_", self.acts)
        self.assertIn("Set Pairs_(1) = Src_", self.acts)
        # Array() 整型字面量教训只针对数组赋值——IsArray 守卫合法
        self.assertFalse(any("= Array(" in a for a in self.acts))
        self.assertNotIn("Pairs_ = Array", self.joined)

    def test_no_iif(self):
        self.assertNotIn("IIf", self.joined)


class TestBusinessState(unittest.TestCase):
    def test_three_states(self):
        self.assertEqual(j1.business_state(
            {"av1": "True", "restore_ret": "True"}), 1)
        self.assertEqual(j1.business_state(
            {"av1": "True", "restore_ret": "False"}), 0)
        self.assertEqual(j1.business_state({"av1": "False"}), -1)
        self.assertEqual(j1.business_state({}), -1)


class TestStlAndInject(unittest.TestCase):
    def test_patch2_cube_shape(self):
        # part.mdl 流形分析：闭体积 = [0,0.01]³ 全立方体（无腔体），
        # patch② 用 12 三角同区域立方体绕开 60k 三角病态导入
        out = j1.build_patch2_cube(
            out=j1.M_DIR / "_test_cube.stl")
        data = out.read_bytes()
        self.assertEqual(len(data), 84 + 50 * 12)
        n = struct.unpack("<I", data[80:84])[0]
        self.assertEqual(n, 12)
        tris = np.frombuffer(
            data[84:],
            dtype=np.dtype([("n", "<3f4"), ("v", "<3,3f4"), ("a", "<u2")]))
        v = tris["v"].astype(float).reshape(-1, 3)
        self.assertTrue(np.allclose(v.min(0), 0.0))
        self.assertTrue(np.allclose(v.max(0), 0.01))
        vn = tris["n"].astype(float)
        axes = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0],
                         [0, 0, 1], [0, 0, -1]], float)
        cluster = (vn @ axes.T).argmax(1)
        self.assertEqual(np.bincount(cluster).tolist(), [2] * 6)
        self.assertAlmostEqual(
            float(np.abs((vn @ axes.T).max(1)).min()), 1.0, places=6)

    def test_stl_layout_synthetic(self):
        # 纯组装函数：4 面小模型（不依赖宿主产物）
        tri = [[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]],
               [[0., 0., 0.], [0., 1., 0.], [0., 0., 1.]]]
        data = j1.stl_bytes(tri)
        self.assertEqual(len(data), 84 + 50 * 2)
        n = struct.unpack("<I", data[80:84])[0]
        self.assertEqual(n, 2)
        v0 = struct.unpack("<3f", data[84 + 12:84 + 24])
        self.assertAlmostEqual(v0[0], 0.0, places=6)

    def test_inject_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src.pph"
            dst = Path(td) / "dst.pph"
            out = Path(td) / "out.pph"
            payload = b"# his version=\"2.0\"\r\nSAMPLE\r\n"
            with zipfile.ZipFile(src, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("main.xml",
                           "<mdl><storedclosedvolumes><closedvolume>"
                           "<name>ClosedVolume1</name><onlystored>false"
                           "</onlystored></closedvolume>"
                           "</storedclosedvolumes></mdl>")
                z.writestr(j1.HIS_MEMBER, payload)
            with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("main.xml",
                           "<mdl><storedclosedvolumes/></mdl>")
                z.writestr("main.sctsnapshot", b"SNAP")
            j1.inject_his(src_pph=src, dst_pph=dst, out=out)
            with zipfile.ZipFile(out) as z:
                self.assertEqual(z.read(j1.HIS_MEMBER), payload)
                self.assertEqual(z.read("main.sctsnapshot"), b"SNAP")
                xml = z.read("main.xml").decode()
                self.assertIn("<name>ClosedVolume1</name>", xml)
                self.assertNotIn("<storedclosedvolumes/>", xml)

    def test_inject_rejects_unpopulated_source(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src.pph"
            dst = Path(td) / "dst.pph"
            with zipfile.ZipFile(src, "w") as z:
                z.writestr("main.xml", "<mdl><storedclosedvolumes/></mdl>")
                z.writestr(j1.HIS_MEMBER, b"A")
            with zipfile.ZipFile(dst, "w") as z:
                z.writestr("main.xml", "<mdl/>")
            with self.assertRaises(SystemExit):
                j1.inject_his(src_pph=src, dst_pph=dst,
                              out=Path(td) / "o.pph")

    def test_inject_rejects_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src.pph"
            dst = Path(td) / "dst.pph"
            with zipfile.ZipFile(src, "w") as z:
                z.writestr("main.xml",
                           "<mdl><storedclosedvolumes><closedvolume/>"
                           "</storedclosedvolumes></mdl>")
                z.writestr(j1.HIS_MEMBER, b"A")
            with zipfile.ZipFile(dst, "w") as z:
                z.writestr("main.xml", "<mdl/>")
                z.writestr(j1.HIS_MEMBER, b"B")
            with self.assertRaises(SystemExit):
                j1.inject_his(src_pph=src, dst_pph=dst,
                              out=Path(td) / "o.pph")


if __name__ == "__main__":
    unittest.main()
