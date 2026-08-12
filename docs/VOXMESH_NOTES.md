# 自研 Voxel / Hex-dominant mesher（MVP）

> 状态：2026-08-13 实现第一版（`voxmesh.py` + `gphstats.write_gph_volume`）。
> 定位：DEV_PLAN §0.6 的自研旁路 —— 产物兼容 CRDL-FLD OCT/GPH，**算法不等价**
> scFLOWpre Voxel fitting mesher；官方质量/贴体仍由 AutomationBridge 驱动宿主。

## 1. 手册语义（scFLOW Voxel fitting mesher）

来自 `Pre_eng/Scf_pre_Condition-Mesh_Parameter-Voxel_Fitting_Mesher.html`：

- **BlockMesh**：八分单元归属判定（阈值、多 solid 包围的流体单元处理、
  part 间分离设置）；
- **Fitting**：`fit to parts surface`、特征复现方法（不用/用 model ridge/
  hybrid）、平滑迭代、拟合迭代、最大位移距离比、特征检测角、
  最近点位移许可角、内外位移平滑、误差位置松弛；
- **Surface Regions**：网格化后的面区域映射（远面跳过阈值）。

MVP 覆盖：BlockMesh 归属（inside/cut/outside）、rough poly 开关、
简化贴体（近表面角点投影，`max_fit_distance_ratio`）。

## 2. 开源/学术蓝本（在线检索要点）

| 来源 | 要点 | 在本实现中的对应 |
|------|------|------------------|
| cfMesh `cartesianMesh`（GPL） | 背景 octree → hex-dominant，级别跃迁为 polyhedra | 八叉树 + 切割带多面体 |
| OpenFOAM `snappyHexMesh` | castellation → snap → addLayers 三阶段 | castellation=八叉树细化；snap=可选贴体投影；layers 未做 |
| Hexotic（IMR18） | 平衡规则（相邻 ≤1 级）+ pairing 规则 → 对偶全 hex | 平衡/对偶列为后续项 |
| HybridOctree_Hex（CMU, JoCS 2024） | 自适应 all-hex + scaled Jacobian>0.5 | 质量优化路线参考 |
| AIAA 2020-1408 / Pointwise hex-core | 根 voxel → octree 尺寸场 → hex core（tet/pyramid/hex 过渡） | 过渡带 polyhedra 近似 |
| scFLOW 手册 Voxel 页 | BlockMesh + fitting + 面区域映射 | 参数面与流程对齐 |

## 3. 流水线（当前实现）

```text
MDL part / STL
  → 根立方盒（包围盒外扩 margin_ratio）
  → 均匀 octree（initial_depth/轴）→ 表面相交自适应细化（max_depth, max_cells）
  → 叶子分类：inside / cut / outside（AABB-三角形相交 + 射线法投票）
  → inside → hex；cut → rough hex 或 棱-面交点凸包 polyhedra（可选贴体投影）
  → 面装配（owner/neigh 去重 + Newell 外向法向）
  → 写 .oct（oct.write_oct）+ .gph（gphstats.write_gph_volume）
```

## 4. 参数映射

| 对话框/CLI | 对齐 xenv/手册 | 默认 |
|------------|----------------|------|
| `initial_depth` | 初分（根盒 2^depth/轴） | 2 |
| `max_depth` | 表面细化上限 | 4 |
| `max_cells` | `NUMBER_OF_INITIAL_DIVISION_WHEN_VOXEL_MESHING`（容量语义） | 500_000 |
| `rough_poly` | `USE_ROUGH_POLY_WHEN_VOXEL_MESHING` | True |
| `fit_to_surface` | `fit to parts surface`（简化版） | False |
| `max_fit_distance_ratio` | Maximum fitting distance ratio | 0.5 |

## 5. 使用

CLI：

```bat
python -m voxmesh box.pph -o out\box_vox --initial-depth 2 --max-depth 3 --rough
python -m voxmesh part.stl -o out\box_vox --initial-depth 2 --max-depth 3
```

GUI：`Execute → Voxel Fitting Mesh (Self Build)…`（需要 PPH 已有 OCT/GPH 成员
占位；写回为 `*.voxmesh.pph`，打开后即显示新网格）。

## 6. 已知限制与后续

- 八叉树未做 2:1 平衡与 pairing；级别跃迁处仍为“各叶子独立成单元”，
  相邻不同深度叶子会共享悬挂点（面装配按顶点集合去重，网格仍是合法
  多面体，但非 conforming hex 拓扑）。
- 面区域映射（frid/cvol 写回）、边界层、粗糙多面体质量平滑未做。
- 非水密面片的 inside/cut 判定退化为射线投票，可靠性依赖输入质量。
- 性能：`rough_poly=True` 快（秒级）；`rough_poly=False` 的凸包路径
  在 box 样例约 40s，后续可并行化/空间索引优化。
