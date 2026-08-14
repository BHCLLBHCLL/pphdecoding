# 自研原生多面体 mesher —— clipped Voronoi / Delaunay 对偶

> 状态：2026-08-14 第二版（`polymesh.py`）：新增 **Lloyd 平滑**、
> **近壁层**、**VoroCrust 式特征保形**（镜像加权 seed）。
> 定位：DEV_PLAN §0.5 的自研旁路 —— 产物兼容 CRDL-FLD GPH，**算法不等价**
> scFLOW/Cradle；官方 polyhedral 仍由 AutomationBridge 驱动宿主。

## 1. 学术/开源参照

| 来源 | 要点 | 本实现对应 |
|------|------|------------|
| cfMesh《An Inside-Out Method For Arbitrary Polyhedra》(2014) | 八叉树模板 → tet → **tet 对偶 = polyhedra** | Delaunay 对偶（Voronoi 胞元） |
| VoroCrust（ACM TOG, Sandia） | conforming Voronoi、无裁剪、保尖角：**每球一对镜像 seed（c±r·n）**，尖边放棱心球，权 w=r² | `feature_preserve`：表面 seed 镜像对（in 出单元 / out ghost 塑形）+ 尖边棱心 4-seed 球；**加权以球半径随特征距离缩放近似**（邻尖边减半） |
| NASA LAVA Voronoi mesher（AIAA 2024-4306） | seed → **近壁分层** → **Lloyd 平滑** → cell clipping | `n_wall_layers` 法向分层 seed；`lloyd_iterations` 自由 seed 迭代移至胞元质心 |
| meshless_voronoi / OpenTissue | 凸多面体半空间裁剪工程实现 | `_Poly.clip`（Sutherland–Hodgman 3D） |

## 2. 算法

```text
MDL/STL 面片
  → 根盒（包围盒外扩 margin_ratio）
  → seed 生成（_generate_seeds）：
      表面点抽样（surface_stride）
        ├─ feature_preserve：VoroCrust 镜像对 p±δ·n_in（δ=球半径，近尖边减半）
        └─ 否则裸表面点
      尖边棱心球（二面角>feature_angle_deg：c±δ·n0、c±δ·n1 共 4 seed）
      近壁层（n_wall_layers × 沿内法向，d_i=t1·(g^i−1)/(g−1)，碰撞剔除）
      内部格点（divisions/轴，射线法过滤 inside，可选确定性抖动）
  → Lloyd 平滑（lloyd_iterations：自由 seed=内部+层，移至胞元质心×阻尼；
      边界 seed 全程冻结保贴体；目标出域放弃移动）
  → 联合 Delaunay（scipy）→ vertex_neighbor_vertices
  → 每个 emit seed：根盒 ∩ 邻居垂直平分半空间 = 有界 Voronoi 胞元
      （ghost seed 只塑形不出单元）
  → 表面相关胞元：按表面三角形平面裁剪（保留含最近内部种子一侧）
  → 凸多面体面表（顶点+面，n-gon）→ 全局顶点注册
  → owner/neigh 面装配（每单元至少拥有一个面，外向法向）
  → 写 .gph（gphstats.write_gph_volume）
```

关键实现点：

- `_Poly` 维护“顶点 + 面表”，半空间裁剪用 3D Sutherland–Hodgman，
  每次裁剪后压实顶点表并去重面（避免退化边/重复面）；
- 表面种子胞元未裁剪时大部分体积在域外，裁剪平面按**最近内部种子**
  定向（保留内侧），避免按胞元质心定向导致裁反；
- 内/外镜像 seed 对之间的 Voronoi 面恰好过表面点 p 且 ⊥ n——
  边界贴合不依赖裁剪（VoroCrust conforming 的核心）；尖边处
  c−δ·n0 与 c−δ·n1 的面平分二面角，网格边界在棱处精确转折；
- 面装配后翻转“仅作 neigh”的单元的一条共享面，保证
  `owner.max()+1 == n_cells`（GPH 统计口径）；
- Lloyd 仅移动内部/层 seed（顶点均质心 × damping，出域放弃），
  边界 seed 冻结——保角与平滑解耦；`interior_jitter` 为确定性
  （固定 rng 种子）测试扰动。

## 3. 参数

| 参数 | 含义 | 默认 |
|------|------|------|
| `divisions` | 根盒内部格点每轴划分数（seed 密度） | 12 |
| `surface_stride` | 表面点抽样步长（1=全部） | 8 |
| `clip_to_surface` | 表面 seed 胞元按表面平面裁剪 | True |
| `max_clip_planes` | 每胞元裁剪平面数上限 | 64 |
| `max_cells` | 单元上限 | 200_000 |
| `lloyd_iterations` / `lloyd_damping` | Lloyd 迭代次数 / 阻尼 | 0 / 0.5 |
| `interior_jitter` | 内部格点确定性抖动（×间距） | 0.0 |
| `n_wall_layers` | 近壁层数 | 0 |
| `first_layer_ratio` / `layer_growth` | 首层厚（×间距）/ 增长比 | 0.25 / 1.4 |
| `feature_preserve` | VoroCrust 镜像 seed 对 + 尖边球 | False |
| `feature_angle_deg` | 尖边二面角阈值 | 30.0 |
| `feature_radius_ratio` | seed 球半径（×间距） | 0.5 |

## 4. 使用

```bat
python -m polymesh box.pph -o out\poly_vox --divisions 8 --surface-stride 16
python -m polymesh part.stl -o out\poly_vox --divisions 10 --surface-stride 4
python -m polymesh box.pph -o out\poly_rough --no-clip   # 不贴体（纯 Voronoi）
python -m polymesh box.pph -o out\poly_feat --preserve-features --lloyd 2 --layers 2
```

GUI：`Execute → Polyhedral Mesh (Self Build)…`（参数对话框含 Lloyd/
近壁层/特征保形；写回为 `*.polymesh.pph`）。原生 Execute（API 关闭）
Polyhedral 默认：`lloyd_iterations=2, feature_preserve=True`。

## 5. 实测（单位立方体，divisions=6 / stride=1）

| 配置 | 单元 | 备注 |
|------|------|------|
| base | 128 | 总体积 1.053 |
| feature_preserve | 152 | ghost=32（8 顶点+24 棱 ghost），尖边 12，总体积 1.028（更接近真值） |
| n_wall_layers=2 | 139 | 层 seed 12（碰撞剔除后），总体积 1.058 |
| jitter 0.4 + Lloyd×5(0.5) | 188 | 体积变异系数 0.352 → 0.313（内部规则化；边界 seed 冻结故边界不规则度保留） |

## 6. 已知限制与后续

- Lloyd 质心用胞元顶点均值（非体积质心），高阻尼（→1.0）下可能振荡，
  默认 damping=0.5 稳定；边界 seed 冻结 → 边界单元不规则度不由 Lloyd 改善；
- 近壁层碰撞检测用表面质心 KD 距离（上界代理），薄间隙处可能欠/过剔除；
- VoroCrust 的权 w=r² 以球半径几何缩放近似（未做真 power diagram），
  角点（≥3 尖边交汇）未放专用角球，由相邻棱球覆盖；
- 非水密面片依赖射线法投票；薄特征处表面平面裁剪可能过度；
- 性能：Delaunay + 逐胞元裁剪为主要成本，Lloyd 每趟一次全量
  Delaunay；后续可并行化种子裁剪与空间索引；
- 面区域映射（frid/cvol）、质量统计与 scFLOW 对比未做。
