#!/usr/bin/env python3
"""原生 BAM（native_bam）回归：闭体识别/多重边/匹配/微小面/修复/报告/写端。

步骤语义对齐 Analysis Model Wizard 录制序列
（``automation/pipeline_plan.BAM_WIZARD_ACTIONS``）。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import mdl  # noqa: E402
import native_bam  # noqa: E402
import pphxml  # noqa: E402


def _unit_box() -> tuple[np.ndarray, list]:
    """正确封闭的单位立方体（z 最快顶点序，四边形面）。"""
    pts = np.array(
        [[x, y, z]
         for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)],
        dtype=float)
    quads = [
        [0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1],
        [2, 3, 7, 6], [1, 5, 7, 3], [0, 2, 6, 4],
    ]
    return pts, quads


class TestCreateBoundary(unittest.TestCase):
    """CreateBoundary：定向 + 闭体识别 + csid。"""

    def test_single_closed_box(self):
        pts, quads = _unit_box()
        res = native_bam.build_analysis_model(pts, quads)
        rep = res.report
        self.assertEqual(rep.n_closed_volumes, 1)
        self.assertEqual(rep.n_sheet_components, 0)
        self.assertEqual(rep.n_open_edges, 0)
        self.assertTrue(rep.buildable)
        self.assertEqual(rep.rows, [])
        self.assertTrue(np.all(res.csid[0] == 0))
        self.assertTrue(np.all(res.csid[1] == 1))
        # 立方体 12 条尖边 / 8 个角点
        self.assertEqual(rep.n_ridge_edges, 12)
        self.assertEqual(int(res.edge_state.sum()), 24)
        self.assertEqual(int(res.node_state.sum()), 8)
        # 外向一致 → 符号体积为正
        self.assertAlmostEqual(
            float(native_bam._signed_volume(res.points, res.faces)), 1.0)

    def test_two_disjoint_boxes(self):
        pts, quads = _unit_box()
        pts2 = np.vstack([pts, pts + 3.0])
        quads2 = quads + [[v + 8 for v in f] for f in quads]
        res = native_bam.build_analysis_model(pts2, quads2)
        self.assertEqual(res.report.n_closed_volumes, 2)
        self.assertEqual(sorted(set(res.csid[1].tolist())), [1, 2])

    def test_open_sheet_not_buildable(self):
        pts, quads = _unit_box()
        res = native_bam.build_analysis_model(pts, quads[:-1])
        rep = res.report
        self.assertEqual(rep.n_closed_volumes, 0)
        self.assertEqual(rep.n_sheet_components, 1)
        self.assertEqual(rep.n_open_edges, 4)
        self.assertFalse(rep.buildable)
        levels = {r["level"] for r in rep.rows}
        self.assertIn(3, levels)  # Open edge 行

    def test_flipped_faces_get_reoriented(self):
        """全部面反向的闭盒 → 重定向后仍识别为 1 闭体且体积为正。"""
        pts, quads = _unit_box()
        flipped = [list(reversed(f)) for f in quads]
        res = native_bam.build_analysis_model(pts, flipped)
        self.assertEqual(res.report.n_closed_volumes, 1)
        self.assertAlmostEqual(
            float(native_bam._signed_volume(res.points, res.faces)), 1.0)

    def test_influence_config_recorded_in_report(self):
        """Influence 参数透传到报告（几何效应在宿主内核，原生记录配置）。"""
        pts, quads = _unit_box()
        res = native_bam.build_analysis_model(
            pts, quads,
            native_bam.BamParams(influence_enable=True,
                                 influence_targets=["case1", "impeller1"]))
        self.assertTrue(res.report.influence_enable)
        self.assertEqual(res.report.influence_targets,
                         ["case1", "impeller1"])
        self.assertIn("case1", "\n".join(res.report.summary_lines()))


class TestMultiEntityInfo(unittest.TestCase):
    """CreateMultiEntityInfo：多重边/多重面。"""

    def test_multifold_edge(self):
        # 三张四边形共边 (0,1) → 多重边
        pts = np.array([
            [0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0],
            [0, 0, 1], [1, 0, 1], [0, -1, 0], [1, -1, 0],
        ])
        faces = [[0, 1, 3, 2], [0, 1, 5, 4], [0, 1, 7, 6]]
        mf_edges, mf_faces = native_bam.detect_multifold(pts, faces)
        self.assertIn((0, 1), mf_edges)
        self.assertEqual(len(mf_edges[(0, 1)]), 3)
        self.assertEqual(mf_faces, 0)

    def test_multifold_face_duplicate(self):
        pts = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]])
        faces = [[0, 1, 2, 3], [0, 1, 2, 3]]
        mf_edges, mf_faces = native_bam.detect_multifold(pts, faces)
        self.assertEqual(mf_faces, 1)

    def test_multifold_edge_tolerant(self):
        # 三面共几何边但各持独立顶点副本（缝隙 eps）：精确拓扑抓不到，
        # 容差合并（P3-1）应识别为多重边
        eps = 1e-3
        pts = np.array([
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],       # face A
            [0, eps, 0], [1, eps, 0], [1, 2, 0], [0, 2, 0],   # face B
            [0, -eps, 0], [1, -eps, 0], [1, -2, 0], [0, -2, 0],
        ])
        faces = [[0, 1, 3, 2], [4, 5, 7, 6], [8, 9, 11, 10]]
        mf_edges, _ = native_bam.detect_multifold(pts, faces)
        self.assertEqual(len(mf_edges), 0)          # 精确：无共享边
        mf_edges, _ = native_bam.detect_multifold(
            pts, faces, tol_edge=0.01)
        self.assertEqual(len(mf_edges), 1)
        self.assertEqual(len(next(iter(mf_edges.values()))), 3)

    def test_multifold_face_tolerant(self):
        # 两几何重合面（独立顶点副本，z 向偏 eps）：容差合并识别重复
        eps = 1e-3
        base = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]])
        pts = np.vstack([base, base + [0.0, 0.0, eps]])
        faces = [[0, 1, 2, 3], [4, 5, 6, 7]]
        _, mf_faces = native_bam.detect_multifold(pts, faces)
        self.assertEqual(mf_faces, 0)               # 精确：顶点集不同
        _, mf_faces = native_bam.detect_multifold(
            pts, faces, tol_face=0.01)
        self.assertEqual(mf_faces, 1)

    def test_pipeline_tolerance_reports_multifold(self):
        # 主管线：缝隙多重边经 1/N 容差（N=100 → tol=diag/100）进报告
        eps = 1e-3
        pts = np.array([
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
            [0, eps, 0], [1, eps, 0], [1, 2, 0], [0, 2, 0],
            [0, -eps, 0], [1, -eps, 0], [1, -2, 0], [0, -2, 0],
        ])
        faces = [[0, 1, 3, 2], [4, 5, 7, 6], [8, 9, 11, 10]]
        strict = native_bam.build_analysis_model(
            pts, faces, native_bam.BamParams(
                tol_multifold_edge=1e6, tol_multifold_face=1e6))
        self.assertEqual(strict.report.n_multifold_edges, 0)
        loose = native_bam.build_analysis_model(
            pts, faces, native_bam.BamParams(
                tol_multifold_edge=100.0, tol_multifold_face=100.0))
        self.assertGreaterEqual(loose.report.n_multifold_edges, 1)
        types = {r["type"] for r in loose.report.rows}
        self.assertIn("Multi-fold edge", types)


class TestMatchingAndTiny(unittest.TestCase):
    """FindAFFaceMatching/SetFaceMatched + FindTinyFace/SetTinyFacesRemoved。"""

    def test_face_matching_merges_frid(self):
        p1 = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
                      dtype=float)
        p2 = p1 + np.array([0, 0, 0.0005])
        pts = np.vstack([p1, p2])
        faces = [[0, 1, 2, 3], [7, 6, 5, 4]]  # 法向相反
        frid = np.array([0, 2], dtype=np.int64)
        frid_out, pairs = native_bam.match_faces(pts, faces, frid, 0.01)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(frid_out.tolist(), [0, 0])

    def test_matching_respects_tol(self):
        p1 = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
                      dtype=float)
        p2 = p1 + np.array([0, 0, 0.5])
        pts = np.vstack([p1, p2])
        faces = [[0, 1, 2, 3], [7, 6, 5, 4]]
        _frid, pairs = native_bam.match_faces(
            pts, faces, np.zeros(2, dtype=np.int64), 0.01)
        self.assertEqual(pairs, [])

    def test_remove_tiny_faces(self):
        pts, quads = _unit_box()
        tiny = np.vstack([pts, [[0.5, 0.5, 0.5], [0.5005, 0.5, 0.5],
                                [0.5, 0.5005, 0.5]]])
        faces = quads + [[8, 9, 10]]
        res = native_bam.build_analysis_model(
            tiny, faces,
            native_bam.BamParams(remove_tiny=True, remove_tiny_tol=0.001))
        self.assertEqual(res.report.n_tiny_found, 1)
        self.assertEqual(res.report.n_tiny_removed, 1)
        self.assertEqual(len(res.faces), 6)
        self.assertEqual(res.report.n_closed_volumes, 1)

    def test_remove_tiny_disabled(self):
        pts, quads = _unit_box()
        tiny = np.vstack([pts, [[0.5, 0.5, 0.5], [0.5005, 0.5, 0.5],
                                [0.5, 0.5005, 0.5]]])
        faces = quads + [[8, 9, 10]]
        res = native_bam.build_analysis_model(
            tiny, faces,
            native_bam.BamParams(remove_tiny=False, remove_tiny_tol=0.001))
        self.assertEqual(res.report.n_tiny_removed, 0)
        self.assertEqual(len(res.faces), 7)
        # CheckMDLErrors 仍报告微小面
        self.assertTrue(any(r["type"] == "Tiny face"
                            for r in res.report.rows))


class TestRepair(unittest.TestCase):
    """RepairMDL：焊接 / 去重 / 去孤立点。"""

    def test_weld_and_dedup(self):
        pts, quads = _unit_box()
        dup_pts = np.vstack([pts, pts[0:1] + 1e-12])  # 顶点 8 ≈ 顶点 0
        faces = [f[:] for f in quads]
        faces[0] = [8, 1, 3, 2]
        faces.append(quads[1][:])  # 完全重复面
        res = native_bam.build_analysis_model(
            dup_pts, faces, native_bam.BamParams())
        self.assertEqual(res.report.n_closed_volumes, 1)
        self.assertEqual(len(res.faces), 6)
        self.assertEqual(len(res.points), 8)
        self.assertIn("duplicate_faces", res.report.repair_stats)

    def test_isolated_vertices_removed(self):
        pts, quads = _unit_box()
        far = np.vstack([pts, [[10.0, 10.0, 10.0]]])
        res = native_bam.build_analysis_model(far, quads)
        self.assertEqual(len(res.points), 8)
        self.assertEqual(
            res.report.repair_stats.get("isolated_vertices"), 1)


class TestWriteBamMdl(unittest.TestCase):
    """写端：原生布局 + parse_mdl 回读。"""

    def test_roundtrip_full_records(self):
        pts, quads = _unit_box()
        res = native_bam.build_analysis_model(pts, quads)
        with tempfile.TemporaryDirectory() as td:
            p = native_bam.write_bam_mdl(res, Path(td) / "part.mdl")
            raw = p.read_bytes()
            m = mdl.parse_mdl(str(p))
        self.assertEqual(m.n_closed_volumes, 1)
        self.assertEqual(m.closed_volumes, ["", ""])  # 外部 + 1 闭体
        self.assertEqual(m.volume_regions, ["FluidRegion"])
        self.assertEqual([(r.name, r.index) for r in m.surface_regions],
                         [("@PartSurface_Part", 0)])
        self.assertTrue(np.all(m.csid[0] == 0))
        self.assertTrue(np.all(m.csid[1] == 1))
        self.assertEqual(int(m.edge_state.sum()), 24)
        self.assertEqual(int(m.node_state.sum()), 8)
        # 原生名称记录 desc(type=1, 255, 1) + 节尾标记
        self.assertIn(b"\x00\x00\x00\x0c\x00\x00\x00\x01"
                      b"\x00\x00\x00\xff\x00\x00\x00\x01", raw)
        self.assertIn(b"FluidRegion", raw)

    def test_write_mdl_closed_volumes_param(self):
        pts, quads = _unit_box()
        n = len(quads)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "part.mdl"
            mdl.write_mdl(
                p, pts, quads,
                csid=(np.zeros(n, dtype=np.int64),
                      np.full(n, 2, dtype=np.int64)),
                closed_volumes=["", "outer", "inner"],
                volume_regions=["FluidRegion", "SolidRegion"])
            m = mdl.parse_mdl(str(p))
        self.assertEqual(m.closed_volumes, ["", "outer", "inner"])
        self.assertEqual(m.volume_regions, ["FluidRegion", "SolidRegion"])
        self.assertEqual(m.n_closed_volumes, 2)


class TestParamsFromSession(unittest.TestCase):
    def test_session_mapping(self):
        sess = {
            "project_solids": False,
            "use_facetter": True,
            "acc_type": "1",
            "match_tol": 0.01,
            "remove_tiny": False,
            "remove_tiny_tol": 0.005,
            "tiny_pct": 2.5,
            "tol_multifold_edge": "1e+05",
            "influence_enable": True,
            "influence_targets": ["case1"],
            "apply_face_matching": False,
            "repair": False,
        }
        p = native_bam.BamParams.from_session(sess)
        self.assertFalse(p.project_solids)
        self.assertEqual(p.acc_type, "1")
        self.assertAlmostEqual(p.match_tol, 0.01)
        self.assertFalse(p.remove_tiny)
        self.assertAlmostEqual(p.remove_tiny_tol, 0.005)
        self.assertAlmostEqual(p.tiny_pct, 2.5)
        self.assertAlmostEqual(p.tol_multifold_edge, 1e5)
        self.assertTrue(p.influence_enable)
        self.assertEqual(p.influence_targets, ["case1"])
        self.assertFalse(p.apply_face_matching)
        self.assertFalse(p.repair)

    def test_xenv_fallback(self):
        xenv = pphxml.XenvSettings()
        pphxml.set_xenv_value(xenv, "FACET", "USE_FACETTER", "false")
        pphxml.set_xenv_value(xenv, "FACET", "SOLID_BASE_MINIMUM_ANGLE", "15")
        pphxml.set_xenv_value(
            xenv, "FACET", "SOLID_BASE_TINY_FACE_WIDTH_RATIO", "0.02")
        p = native_bam.BamParams.from_session({}, xenv)
        self.assertFalse(p.use_facetter)
        self.assertAlmostEqual(p.sb_ang, 15.0)
        self.assertAlmostEqual(p.tiny_pct, 2.0)  # 0-1 → 百分数


class TestGuiWiring(unittest.TestCase):
    def test_native_pipeline_uses_native_bam(self):
        src = (ROOT / "pph_gui.py").read_text(encoding="utf-8")
        self.assertIn("native_bam.build_analysis_model", src)
        self.assertIn("native_bam.BamParams.from_session", src)
        self.assertIn("write_bam_mdl", src)
        self.assertIn("def _run_native_bam", src)
        self.assertIn("def _is_native_mdl", src)

    def test_wizard_actions_flag_session(self):
        src = (ROOT / "nav_panels.py").read_text(encoding="utf-8")
        self.assertIn('"Match": "apply_face_matching"', src)
        self.assertIn('"Remove tiny faces": "remove_tiny"', src)


if __name__ == "__main__":
    unittest.main()
