#!/usr/bin/env python3
"""三向对齐扩样（冲刺 E · 域 5）：.oct 成员 ↔ 快照八叉树 ↔ GPH 网格。

O3 链路三表述同一八叉树，不变量：

1. **总量一致**：快照 division bits 的 octant 总数（``1+8*n_internal``）
   == ``.oct`` 成员 ``parse_oct`` 的 ``n_octants``（字节级两表述对拍）；
2. **层次自洽**：两侧满八叉树不变量 + ``n_active ≤ n_leaves ≤ n_octants``；
3. **网格落域**：GPH 单元数 > 0 且全部顶点落在 ``.oct`` 根域
   ``[root_min, root_max]`` 内（网格由八叉树活跃域生成）。

样本：本地 ``box.pph`` / ``p12a_octant_e2e_out.pph``（宿主 Refine 后
产物，P12-A e2e 证据）+ 盘上黄金 ``interference``（有 .oct 成员）与
``tr03``（无 .oct 成员 → 快照↔GPH 两向）。例程库缺失时相应跳过。
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import oct as octmod  # noqa: E402
import sctsnapshot  # noqa: E402
from gphstats import parse_mesh  # noqa: E402

CRADLE = Path(os.environ.get("PPH_CRADLE_ROOT", r"D:\training\cradle"))
EPS = 1e-6


def _member(pph: Path, name: str) -> bytes | None:
    with zipfile.ZipFile(pph) as z:
        if name not in z.namelist():
            return None
        return z.read(name)


def _snapshot_of(pph: Path) -> sctsnapshot.SctSnapshot:
    raw = _member(pph, "main.sctsnapshot")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sctsnapshot")
    tmp.write(raw)
    tmp.close()
    return sctsnapshot.SctSnapshot.load(tmp.name)


def _oct_model_of(pph: Path):
    raw = _member(pph, "meshinggroup1.oct")
    if raw is None:
        return None
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".oct")
    tmp.write(raw)
    tmp.close()
    return octmod.parse_oct(tmp.name)


def _gph_facts(pph: Path) -> dict:
    raw = _member(pph, "meshinggroup1.gph")
    mesh = parse_mesh(raw)
    verts = np.asarray(mesh["vertices"], dtype=float).reshape(-1, 3)
    return {"n_cells": int(mesh["owner"].max()) + 1,
            "n_verts": len(verts),
            "bbox_min": verts.min(axis=0),
            "bbox_max": verts.max(axis=0)}


class TriAlignmentCase:
    """单样本三向断言（成员缺失时退化为两向并记录）。"""

    def __init__(self, tester, pph: Path, has_oct_member: bool):
        self.t = tester
        self.pph = pph
        self.has_oct_member = has_oct_member

    def run(self):
        snap = _snapshot_of(self.pph)
        bits = snap.octree_division_bits()
        n_internal = int(bits.sum())
        n_octants_bits = 1 + 8 * n_internal
        region = snap.octree_region()
        n_active = int(region["n_active"]) if region else 0
        gph = _gph_facts(self.pph)

        # 快照侧满八叉树不变量（位图尾填充 ∈ [0,7]）
        self.t.assertTrue(0 <= int(bits.size) - n_octants_bits <= 7,
                          "snapshot full-tree invariant")

        om = _oct_model_of(self.pph) if self.has_oct_member else None
        if om is not None:
            # 1. 总量一致（两字节级表述）
            self.t.assertEqual(int(om.n_octants), n_octants_bits,
                               "oct member vs snapshot bits n_octants")
            # 2. 成员侧层次自洽
            self.t.assertEqual(int(om.n_leaves) + int(om.n_internal),
                               int(om.n_octants))
            self.t.assertLessEqual(n_active, int(om.n_leaves))
            root_min = np.asarray(om.root_min, dtype=float)
            root_max = np.asarray(om.root_max, dtype=float)
        else:
            # 无 .oct 成员：快照自洽 + 层次链（leaves = octants - internal
            # 不可验，退为 active ≤ octants）
            self.t.assertLessEqual(n_active, n_octants_bits)
            root_min = root_max = None

        # 3. 网格落域
        self.t.assertGreater(gph["n_cells"], 0)
        if root_min is not None:
            self.t.assertTrue(
                bool(np.all(gph["bbox_min"] >= root_min - EPS)),
                f"gph bbox_min {gph['bbox_min']} < oct root {root_min}")
            self.t.assertTrue(
                bool(np.all(gph["bbox_max"] <= root_max + EPS)),
                f"gph bbox_max {gph['bbox_max']} > oct root {root_max}")


class TestBoxTriAlignment(unittest.TestCase):
    """本地 box 工程（仓库根，含 .oct 成员）。"""

    def test_tri_alignment(self):
        TriAlignmentCase(self, ROOT / "box.pph", True).run()


@unittest.skipUnless((ROOT / "p12a_octant_e2e_out.pph").is_file(),
                     "P12-A octant e2e evidence missing")
class TestRefinedTriAlignment(unittest.TestCase):
    """宿主 Refine 后的八叉树（P12-A octant e2e 产物）三向仍自洽。"""

    def test_refined_tri_alignment(self):
        case = TriAlignmentCase(self, ROOT / "p12a_octant_e2e_out.pph", True)
        case.run()
        # Refine 使 octant 总量显著大于原 box（20105 → 94185，P12-A 实测）
        snap = _snapshot_of(ROOT / "p12a_octant_e2e_out.pph")
        self.assertGreater(1 + 8 * int(snap.octree_division_bits().sum()),
                           90_000)


@unittest.skipUnless((CRADLE / "interference" / "interference.pph").is_file(),
                     "cradle interference example missing")
class TestInterferenceTriAlignment(unittest.TestCase):
    def test_tri_alignment(self):
        TriAlignmentCase(
            self, CRADLE / "interference" / "interference.pph", True).run()


@unittest.skipUnless((CRADLE / "tr03" / "tr03" / "tr03.pph").is_file(),
                     "cradle tr03 example missing")
class TestTr03TwoWayAlignment(unittest.TestCase):
    """tr03 无 .oct 成员 → 快照↔GPH 两向。"""

    def test_two_way_alignment(self):
        TriAlignmentCase(self, CRADLE / "tr03" / "tr03" / "tr03.pph",
                         False).run()


if __name__ == "__main__":
    unittest.main()
