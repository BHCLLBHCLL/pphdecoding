#!/usr/bin/env python3
"""OCT 八叉树文件解析（scFLOW ``*.oct``，CRDL-FLD 容器）。

节布局：

* ``Application`` / ``Dimension`` / ``Date`` / ``UnitOfCoordinates`` — 常规元数据。
* ``LS_CoordinateSystem`` — 坐标系 id（描述符链末值，观测为 0）。
* ``LS_OctLastGenYear`` — 最近一次八叉树生成的年份（0 = 未生成/未知）。
* ``LS_OctRootOctantMinMax`` — 根节点包围盒 ``R8[6]``
  ``(xmin, ymin, zmin, xmax, ymax, zmax)``。
* ``LS_OctOctantRefinement`` — ``U1[n_octants]``，**深度优先前序遍历**的
  八叉树结构位图：``1`` = 内部节点（被细分，其后紧跟 8 个子节点记录），
  ``0`` = 叶子。树是完整八叉树，因此 ``n = 1 + 8 * 内部节点数``。
* ``LS_OctOctantBlockID`` — ``I4[n_octants]``，与位图同序的块 id
  （本样例全为 -1，表示未使用）。

八叉树几何重建：从根包围盒出发，按前序位图递归二分；子节点顺序按
Morton/Z 序约定（bit0=x, bit1=y, bit2=z；低位为 min 半区）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional

import numpy as np

from crdlfld import CrdlFldFile, iter_data_blocks, iter_descriptors


@dataclass
class OctModel:
    """解析后的 OCT 八叉树。"""

    root_min: np.ndarray          # (3,) 根包围盒最小角
    root_max: np.ndarray          # (3,) 根包围盒最大角
    n_octants: int                # 位图长度（= 1 + 8*内部节点数）
    n_internal: int               # 内部（被细分）节点数
    n_leaves: int                 # 叶子节点数
    refinement: np.ndarray        # U1[n_octants] 前序位图
    block_id: np.ndarray          # I4[n_octants] 块 id（可能全 -1）
    unit: str = ""
    last_gen_year: int = 0

    def iter_leaves(self, max_leaves: Optional[int] = None
                    ) -> Iterator[tuple[tuple[float, float, float],
                                        tuple[float, float, float], int]]:
        """迭代叶子八分区，产出 ``(min_corner, max_corner, depth)``。

        子节点按 Z 序展开（bit0=x, bit1=y, bit2=z；bit=0 取低半区）。
        注意：单次遍历与 ``refinement`` 同长度，复杂度 O(n_octants)。
        """
        ref = self.refinement
        count = 0
        # 显式栈迭代，避免大深度递归
        stack: list[tuple[float, float, float, float, float, float, int, int]] = []
        x0, y0, z0 = (float(v) for v in self.root_min)
        x1, y1, z1 = (float(v) for v in self.root_max)
        pos = 0
        stack.append((x0, y0, z0, x1, y1, z1, 0, -1))
        while stack:
            ax, ay, az, bx, by, bz, depth, _ = stack.pop()
            r = int(ref[pos])
            pos += 1
            if r == 0:
                yield (ax, ay, az), (bx, by, bz), depth
                count += 1
                if max_leaves is not None and count >= max_leaves:
                    return
                continue
            cx, cy, cz = (ax + bx) / 2.0, (ay + by) / 2.0, (az + bz) / 2.0
            # 子节点 0..7 依次入栈（栈反向，故先压 7）
            for i in range(7, -1, -1):
                nax = cx if i & 1 else ax
                nay = cy if i & 2 else ay
                naz = cz if i & 4 else az
                nbx = bx if i & 1 else cx
                nby = by if i & 2 else cy
                nbz = bz if i & 4 else cz
                stack.append((nax, nay, naz, nbx, nby, nbz, depth + 1, i))

    def leaf_stats(self) -> dict:
        """叶子深度直方图与尺寸统计。"""
        from collections import Counter

        depths: Counter[int] = Counter()
        n = 0
        for _, _, d in self.iter_leaves():
            depths[d] += 1
            n += 1
        return {"n_leaves": n, "depth_histogram": dict(sorted(depths.items()))}


def parse_oct(filepath: str) -> OctModel:
    """解析 OCT 文件，返回 :class:`OctModel`。"""
    with CrdlFldFile.load(filepath) as f:
        data = f.data

        # ── 根包围盒 ─────────────────────────────────────────────────
        root_min = np.zeros(3)
        root_max = np.zeros(3)
        sec = f.get_section("LS_OctRootOctantMinMax")
        if sec:
            for b in iter_data_blocks(data, sec):
                if b.byte_count == 48:
                    vals = b.as_f8(data)
                    root_min = vals[:3]
                    root_max = vals[3:]
                    break

        # ── 位图 ─────────────────────────────────────────────────────
        refinement = np.empty(0, dtype=np.uint8)
        n_octants = 0
        sec = f.get_section("LS_OctOctantRefinement")
        if sec:
            counts = [d.dim0 for d in iter_descriptors(data, sec) if d.dim0 > 1]
            if counts:
                n_octants = counts[0]
            for b in iter_data_blocks(data, sec):
                refinement = b.as_u1(data)
                break
            if n_octants and len(refinement) != n_octants:
                refinement = refinement[:n_octants]
        n_octants = len(refinement)
        n_internal = int(np.count_nonzero(refinement)) if n_octants else 0
        n_leaves = n_octants - n_internal
        if n_octants and (n_octants - 1) % 8 != 0:
            raise ValueError(
                f"{filepath}: 八叉树节点数 {n_octants} 不满足 n = 1 + 8k")
        if n_octants and (n_octants - 1) // 8 != n_internal:
            raise ValueError(
                f"{filepath}: 内部节点数 {n_internal} 与位图长度不一致"
                f"（期望 {(n_octants - 1) // 8}）")

        # ── 块 id ────────────────────────────────────────────────────
        block_id = np.empty(0, dtype=np.int64)
        sec = f.get_section("LS_OctOctantBlockID")
        if sec:
            for b in iter_data_blocks(data, sec):
                if b.byte_count % 4 == 0:
                    block_id = b.as_i4(data)
                    break

        # ── 单位与生成年份 ───────────────────────────────────────────
        unit = ""
        sec = f.get_section("UnitOfCoordinates")
        if sec:
            for b in iter_data_blocks(data, sec):
                raw = bytes(data[b.offset : b.offset + b.byte_count])
                if all(x == 0 or 32 <= x < 127 for x in raw):
                    s = raw.decode("ascii", errors="replace").strip("\x00").rstrip()
                    if s:
                        unit = s
                        break
        last_gen_year = 0
        sec = f.get_section("LS_OctLastGenYear")
        if sec:
            vals = [d.dim0 for d in iter_descriptors(data, sec)]
            if vals:
                last_gen_year = vals[-1]

        return OctModel(
            root_min=root_min, root_max=root_max,
            n_octants=n_octants, n_internal=n_internal, n_leaves=n_leaves,
            refinement=refinement, block_id=block_id,
            unit=unit, last_gen_year=last_gen_year,
        )
