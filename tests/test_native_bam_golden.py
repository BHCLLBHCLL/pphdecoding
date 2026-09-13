"""P2-2 回归：native_bam 与宿主黄金件的一致性（容差默认 + ridge 节点规则）。

背景（2026-09-13 审计）：`native_bam.BamParams.remove_tiny_tol` 默认 1e-3 是
**绝对**长度，对 0.01 m 的黄金 box 会把 60,492 个面全部判为微小面并删光；
且 ridge 特征点规则用 `>=2`，宿主实为 `>=3`（节点数约 10 倍）。
两处已按实测修正，本文件以**宿主参考值**锁定。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mdl  # noqa: E402
import native_bam  # noqa: E402

GOLDEN_BOX = ROOT / "tests" / "box" / "meshinggroup1_part.mdl"

#: 宿主 box 参考值（tests/box/meshinggroup1_part.mdl → 宿主 BAM 结果）
HOST_FACES = 60492
HOST_RIDGE_EDGES = 852
HOST_FEATURE_NODES = 8


def _load_golden():
    m = mdl.parse_mdl(GOLDEN_BOX)
    pts = np.asarray(m.xyz, dtype=float)
    fo = np.asarray(m.face_offsets)
    faces = [np.asarray(m.conn[fo[i]:fo[i + 1]]) for i in range(m.n_faces)]
    return m, pts, faces


@unittest.skipUnless(GOLDEN_BOX.is_file(), "golden box mdl missing")
class TestNativeBamGolden(unittest.TestCase):
    def test_default_tiny_tolerance_keeps_all_faces(self):
        """默认容差（= 录制向导 1e-05）不得删除黄金 box 的任何面。"""
        self.assertEqual(native_bam.BamParams().remove_tiny_tol, 1e-5,
                         "默认容差必须等于录制向导的 FindTinyFace 1e-05")
        m, pts, faces = _load_golden()
        self.assertEqual(len(faces), HOST_FACES)
        _p, kept, _f, found, removed = native_bam.remove_tiny_faces(
            pts.copy(), list(faces), np.asarray(m.frid),
            native_bam.BamParams().remove_tiny_tol)
        self.assertEqual(found, 0, "默认容差下不应识别出微小面")
        self.assertEqual(removed, 0)
        self.assertEqual(len(kept), HOST_FACES)

    def test_ridge_edges_and_feature_nodes_match_host(self):
        """ridge 边数 = 852、特征点（>=3 尖边交汇）= 8，与宿主逐值相等。"""
        _m, pts, faces = _load_golden()
        _edge_state, node_flag, n_ridge = native_bam.detect_ridges(
            pts, faces, native_bam.BamParams().ridge_angle_deg)
        self.assertEqual(n_ridge, HOST_RIDGE_EDGES)
        self.assertEqual(int(np.sum(node_flag)), HOST_FEATURE_NODES)

    def test_old_absolute_tolerance_would_wipe_model(self):
        """把关：显式 1e-3（旧默认）确实会删光 —— 防止默认值被改回去。"""
        m, pts, faces = _load_golden()
        _p, kept, _f, found, removed = native_bam.remove_tiny_faces(
            pts.copy(), list(faces), np.asarray(m.frid), 1e-3)
        self.assertEqual(removed, HOST_FACES)
        self.assertEqual(len(kept), 0)


if __name__ == "__main__":
    unittest.main()
