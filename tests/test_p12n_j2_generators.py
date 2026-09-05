#!/usr/bin/env python3
"""P12-N J2 生成器回归（离线，不触宿主）。

场景依据：I7（§20.11）真 CATPart 读链绿 + ImportCADAsFacet 干净
False（方法内部前置）；P12-D snode 配方 + J1 r4 WIZARD_CORE 全绿核
= ①产物级闭环配方；②facet 五变体前置矩阵。"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "_p12n_j2_run", ROOT / "tools" / "_p12n_j2_run.py")
j2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(j2)


class TestCatiaMdlChain(unittest.TestCase):
    def setUp(self):
        self.acts = j2.build_catia_mdl_groups(
            j2.CATIA_PART, j2.M1_OUT, j2.MDL1, "catia_mdl")[0][1]
        self.joined = "\n".join(self.acts)

    def test_open_cadfile_set_form_on_bare_host(self):
        # 裸宿主（无 OpenProject）+ 括号 Set 形式（retval-unreliable，
        # 验收走 Query 探针——P12-D/I7 同型）
        self.assertNotIn("OpenProject", self.joined)
        self.assertIn(
            f'Set SN_ = Doc_.OpenCadFile('
            f'"{j2.CATIA_PART.as_posix()}")', self.joined)
        self.assertIn('Set SN2_ = Doc_.QuerySNodeByName("Part")',
                      self.joined)

    def test_alias_before_wizard_core(self):
        # J1 r3 教训：复放段变量名 MeshingGroup_ 必须先绑定
        self.assertIn("Set MeshingGroup_ = MGW_", self.acts)
        alias = self.acts.index("Set MeshingGroup_ = MGW_")
        begin = self.acts.index("MeshingGroup_.BeginMDLWizard")
        self.assertLess(alias, begin)

    def test_af_prelude_before_begin(self):
        # P12-A 教训：无 faceter 时 FindAFFaceMatching RPC 崩溃
        pre = self.acts.index("Proj_.SetUseAFFacetter Param1_")
        begin = self.acts.index("MeshingGroup_.BeginMDLWizard")
        self.assertLess(pre, begin)

    def test_wizard_core_complete(self):
        self.assertIn("MDLWizard_.CreateMDL", self.joined)
        # J2 r1 教训（4/4 确定性）：EndMDLWizard 在真 CAD 几何上击杀
        # 脚本进程——流程去 EndMDLWizard，产物在 wizard 会话内收割
        self.assertNotIn("EndMDLWizard", self.joined)
        self.assertEqual(self.joined.count("BeginMDLWizard"), 1)

    def test_artifact_export_and_save(self):
        # 产物级闭环验收面：GetVMDL → Save(.mdl) → SaveProject
        self.assertIn("Set VMDL2_ = MGW_.GetVMDL", self.joined)
        self.assertIn(
            f'RetVx_ = VMDL2_.Save("{j2.MDL1.as_posix()}")',
            self.joined)
        self.assertIn(f'Doc_.SaveProject "{j2.M1_OUT.as_posix()}"',
                      self.joined)
        save = self.acts.index(
            f'Doc_.SaveProject "{j2.M1_OUT.as_posix()}"')
        vsave = self.acts.index(
            f'RetVx_ = VMDL2_.Save("{j2.MDL1.as_posix()}")')
        self.assertLess(vsave, save)

    def test_no_iif(self):
        self.assertNotIn("IIf", self.joined)


class TestCatiaMdl2Chain(unittest.TestCase):
    def setUp(self):
        self.acts = j2.build_catia_mdl_groups(
            j2.CATIA_PART2, j2.M2_OUT, j2.MDL2, "catia_mdl2")[0][1]
        self.joined = "\n".join(self.acts)

    def test_second_sample_wiring(self):
        self.assertIn(
            f'Set SN_ = Doc_.OpenCadFile('
            f'"{j2.CATIA_PART2.as_posix()}")', self.joined)
        self.assertIn(f'RetVx_ = VMDL2_.Save("{j2.MDL2.as_posix()}")',
                      self.joined)
        self.assertIn(f'Doc_.SaveProject "{j2.M2_OUT.as_posix()}"',
                      self.joined)


class TestFacetMatrix(unittest.TestCase):
    def _build(self, name):
        for cname, cad_key, af, empty in j2.FACET_CASES:
            if cname == name:
                out = None if empty else ROOT_HAND()
                src = None if empty else out
                return j2.build_facet_groups(
                    name, j2._cad(cad_key), out, src, af=af,
                    empty_doc=empty)[0][1]
        raise KeyError(name)

    def test_all_five_variants_registered(self):
        self.assertEqual(
            [c[0] for c in j2.FACET_CASES],
            ["f_stl", "f_stl_af", "f_xt_af", "f_catia_af",
             "f_catia_empty"])

    def test_import_line_shape(self):
        for cname, cad_key, af, empty in j2.FACET_CASES:
            acts = self._build(cname)
            joined = "\n".join(acts)
            self.assertIn(
                f'ret_ = Doc_.ImportCADAsFacet('
                f'"{j2._cad(cad_key).as_posix()}", MG_)', joined,
                cname)
            self.assertIn('f_ret=" & CStr(ret_)', joined, cname)
            # ret_ 普通赋值（非 Set）——ImportCADAsFacet 返回 VARIANT
            self.assertNotIn("Set ret_ =", joined, cname)

    def test_af_prelude_only_in_af_variants(self):
        for cname, cad_key, af, empty in j2.FACET_CASES:
            acts = self._build(cname)
            n = sum(1 for a in acts
                    if "SetUseAFFacetter" in a)
            self.assertEqual(n, 1 if af else 0, cname)

    def test_empty_doc_has_no_openproject_nor_save(self):
        acts = self._build("f_catia_empty")
        joined = "\n".join(acts)
        self.assertNotIn("OpenProject", joined)
        self.assertNotIn("SaveProject", joined)

    def test_project_variants_open_and_save(self):
        for cname in ("f_stl", "f_stl_af", "f_xt_af", "f_catia_af"):
            acts = self._build(cname)
            joined = "\n".join(acts)
            self.assertIn('Doc_.OpenProject "', joined, cname)
            self.assertIn('Doc_.SaveProject "', joined, cname)

    def test_wait_for_worker_after_import(self):
        for cname, *_ in j2.FACET_CASES:
            acts = self._build(cname)
            i_imp = next(i for i, a in enumerate(acts)
                         if "ImportCADAsFacet" in a)
            tail = acts[i_imp:i_imp + 4]
            self.assertTrue(
                any("WaitForWorker" in a for a in tail), cname)


class TestCadMatrix(unittest.TestCase):
    CASES = ("cm_xt", "cm_step", "cm_catia", "cm_catia2")

    def _build(self, name):
        cad = dict(j2.CADMATRIX_CASES)[name]
        groups = j2.build_cadmatrix_groups(cad, ROOT_HAND(), name)
        self.assertEqual(groups[0][0], name)
        return groups[0][1]

    def test_four_cases_registered(self):
        self.assertEqual([n for n, _ in j2.CADMATRIX_CASES],
                         list(self.CASES))

    def test_bare_host_set_form_open_cad_file(self):
        for name in self.CASES:
            acts = self._build(name)
            self.assertNotIn("OpenProject", "\n".join(acts), name)
            self.assertTrue(acts[3].startswith('Set SN_ = Doc_.OpenCadFile("'),
                            name)

    def test_stem_probe_and_name_independent_probes(self):
        for name, cad in j2.CADMATRIX_CASES:
            joined = "\n".join(self._build(name))
            self.assertIn('QuerySNodeByName("Part")', joined, name)
            self.assertIn(
                'QuerySNodeByName("' + cad.stem + '")', joined, name)
            self.assertEqual(joined.count("GetSParts(False, False, False)"),
                             2, name)
            self.assertIn("GetAllPartsBoundingBox BBox_, False", joined,
                          name)

    def test_two_round_probes_separated_by_pings(self):
        for name in self.CASES:
            acts = self._build(name)
            pings = [i for i, a in enumerate(acts) if "ping -n 6" in a]
            self.assertEqual(len(pings), 5, name)
            i_p1 = next(i for i, a in enumerate(acts)
                        if "GetSParts" in a)
            i_p2 = next(i for i, a in enumerate(acts)
                        if "Parts2_" in a)
            self.assertTrue(any(i_p1 < p < i_p2 for p in pings), name)

    def test_save_project_last(self):
        for name in self.CASES:
            acts = self._build(name)
            self.assertTrue(acts[-1].startswith('Doc_.SaveProject "'),
                            name)


def ROOT_HAND():
    return j2.N_DIR / "t_out.pph"


if __name__ == "__main__":
    unittest.main()
