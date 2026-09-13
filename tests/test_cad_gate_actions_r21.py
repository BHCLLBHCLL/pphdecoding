#!/usr/bin/env python3
"""R2-1 回归：CAD 端到端 gate 的三段动作生成器不变量。

这些断言把 R2-1 的诊断结论钉进代码，防止后续重构改回去：

* build 段**不得**再调用 CreateMesh（同会话恒 False + 留下 mesh error，
  证据 _p12u_gate/r2_1_probe.json 84/84 err=0）；
* mesh 段必须是录制配方（ChangeMesher / SetMDLMethod / AF facetter →
  MDL wizard → 流体区域登记 → 录制八叉树参数表 → CreateOctree →
  CreateMeshMonitor），并以 DoesMeshErrorExist 作为并行判据；
* reopen 段必须独立回读 DoesMeshExist。
"""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GATE = ROOT / "tools" / "cad_pipeline_gate.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("cad_gate_r21", str(GATE))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cad_gate_r21"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestGateActionInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GATE.is_file():
            raise unittest.SkipTest("tools/cad_pipeline_gate.py missing")
        cls.g = _load_gate()
        cls.out = ROOT / "_p12u_gate" / "_test_only.pph"

    def _joined(self, acts) -> str:
        return "\n".join(acts)

    def test_build_stage_has_no_create_mesh(self):
        acts = self.g.build_actions_full(self.g.XT, self.out)
        text = self._joined(acts)
        self.assertNotIn("CreateMeshMonitor", text)
        # Doc_.CreateMeshingGroup 是 "CreateMesh" 的子串，需排除
        self.assertFalse([a for a in acts
                          if "CreateMesh" in a
                          and "CreateMeshingGroup" not in a])
        self.assertIn("BuildAnalysisModel", text)
        self.assertIn("CreateOctree", text)
        self.assertIn("SaveProject", text)

    def test_mesh_wizard_recipe_order(self):
        acts = self.g.mesh_wizard_actions(self.g.XT, self.out)
        text = self._joined(acts)
        for token in ("ChangeMesher", "ChangeSurfMesher", "SetMDLMethod",
                      "SetUseAFFacetter", "BeginMDLWizard", "GetMDLWizard",
                      "EndMDLWizard", "CreateFluidRegion", "RegisterSPart",
                      "SetParams", "CreateOctree", "CreateMeshMonitor",
                      "WaitForWorker", "DoesMeshExist",
                      "DoesMeshErrorExist"):
            self.assertIn(token, text, token)
        # 录制顺序：网格器/MDL 方法 → AF facetter → 区域登记 → wizard →
        #           八叉树参数表 → CreateOctree → CreateMeshMonitor
        pos = [text.index(t) for t in (
            "ChangeMesher", "SetMDLMethod", "SetUseAFFacetter",
            "CreateFluidRegion", "BeginMDLWizard", "EndMDLWizard",
            "SetParams", "CreateOctree", "CreateMeshMonitor")]
        self.assertEqual(pos, sorted(pos), "配方顺序被改动")

    def test_mesh_stage_runs_on_utf16_channel(self):
        # wizard 在 ANSI 通道静默失败（GetMDLWizard 恒 Nothing）
        src = GATE.read_text(encoding="utf-8")
        self.assertIn("utf16=True", src)
        self.assertIn("_write_utf16_vbs", src)

    def test_reopen_stage_probes_mesh(self):
        acts = self.g.reopen_actions(self.out, self.out)
        text = self._joined(acts)
        self.assertIn("DoesMeshExist", text)
        self.assertIn("GetAllPartsBoundingBox", text)
        self.assertIn("mesh_exists=", text)

    def test_recorded_oct_param_table(self):
        pairs = self.g.OCT_PARAM_PAIRS
        self.assertEqual(len(pairs), 35)
        mapping = dict(pairs)
        for expect in ("TARGETNUMBER", "BASESIZE.MIN", "SECTITEM[0].NAME",
                       "SECTITEM[0].SIZE"):
            self.assertIn(expect, mapping)
        self.assertEqual(mapping["TARGETNUMBER"], "100000")
        self.assertEqual(mapping["SECTITEM[0].NAME"], "@PartSurface_Part")
        lines = self.g._recorded_oct_param_lines()
        self.assertEqual(lines[0], "Redim ArrayParam1_(69)")
        self.assertEqual(lines[1], 'ArrayParam1_(0) = "BALANCING"')
        self.assertEqual(lines[2], "ArrayParam1_(1) = 3")
        self.assertEqual(lines[-1],
                         "MG5_.SetOctCreateTypeWithSolidBaseOct Param1_")

    def test_stage_idle_limits_widened(self):
        # R3-1：mesh/reopen 段在同一条 VBS 行内长时间不写日志，必须放宽
        # 自愈惰性阈值（默认 420 s），否则被误判 hung 并杀宿主。
        src = GATE.read_text(encoding="utf-8")
        self.assertIn("idle_limit=1500.0", src)
        self.assertIn("idle_limit=900.0", src)
        self.assertIn("idle_limit=idle_limit", src)

    def test_utf8_stdout_wired(self):
        # R3-1：ANSI 控制台下 json.dumps(ensure_ascii=False) 的打印会崩，
        # 掩盖宿主崩溃的真实原因。harness 与 gate 都必须先切 UTF-8。
        src = GATE.read_text(encoding="utf-8")
        self.assertIn("p12e.utf8_stdout()", src)
        p12e_src = (ROOT / "tools" / "_p12e_e2e_run.py").read_text(
            encoding="utf-8")
        self.assertIn("def utf8_stdout()", p12e_src)
        self.assertIn("errors=\"replace\"", p12e_src)

    def test_vbs_lit_numeric_vs_string(self):
        self.assertEqual(self.g._vbs_lit("100000"), "100000")
        self.assertEqual(self.g._vbs_lit("0.00021875"), "0.00021875")
        self.assertEqual(self.g._vbs_lit("poly"), '"poly"')
        self.assertEqual(self.g._vbs_lit(""), '""')

    def test_fluid_region_block_targets_part(self):
        text = self._joined(self.g._fluid_region_lines())
        self.assertIn('QuerySNodeByName("Part")', text)
        self.assertIn("RegisterVPart", text)
        self.assertIn("SetSelectAllSPart", text)

    def test_mesh_mode_flag_defaults_to_wizard(self):
        src = GATE.read_text(encoding="utf-8")
        self.assertIn('choices=("wizard", "reopen")', src)
        self.assertIn('default="wizard"', src)


if __name__ == "__main__":
    unittest.main()
