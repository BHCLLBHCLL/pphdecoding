# 自研原生多面体 mesher（MVP）—— clipped Voronoi / Delaunay 对偶

> 状态：2026-08-13 第一版（`polymesh.py`）。
> 定位：DEV_PLAN §0.5 的自研旁路 —— 产物兼容 CRDL-FLD GPH，**算法不等价**
> scFLOW/Cradle；官方 polyhedral 仍由 AutomationBridge 驱动宿主。

## 1. 学术/开源参照

| 来源 | 要点 | 本实现对应 |
|------|------|------------|
| cfMesh《An Inside-Out Method For Arbitrary Polyhedra》(2014) | 八叉树模板 → tet → **tet 对偶 = polyhedra** | Delaunay 对偶（Voronoi 胞元） |
| VoroCrust（ACM TOG, Sandia） | conforming Voronoi、无裁剪、保尖角 | 目标形态参考；MVP 用裁剪而非加权 seed |
| NASA LAVA Voronoi mesher（AIAA 2024-4306） | seed → 近壁处理 → Lloyd 平滑 → **cell clipping** | seed + 表面平面裁剪；未做平滑 |
| meshless_voronoi / OpenTissue | 凸多面体半空间裁剪工程实现 | `_Poly.clip`（Sutherland–Hodgman 3D） |

## 2. 算法

```text
MDL/STL 面片
  → 根盒（包围盒外扩 margin_ratio）
  → 表面点抽样（surface_stride）+ 内部格点（divisions/轴，射线法过滤 inside）
  → 联合 Delaunay（scipy）→ vertex_neighbor_vertices
  → 每个 seed：根盒 ∩ 邻居垂直平分半空间 = 有界 Voronoi 胞元
  → 表面 seed 胞元：按表面三角形平面裁剪（保留含最近内部种子一侧）
  → 凸多面体面表（顶点+面，n-gon）→ 全局顶点注册
  → owner/neigh 面装配（每单元至少拥有一个面，外向法向）
  → 写 .gph（gphstats.write_gph_volume）
```

关键实现点：

- `_Poly` 维护“顶点 + 面表”，半空间裁剪用 3D Sutherland–Hodgman，
  每次裁剪后压实顶点表并去重面（避免退化边/重复面）；
- 表面种子胞元未裁剪时大部分体积在域外，裁剪平面按**最近内部种子**
  定向（保留内侧），避免按胞元质心定向导致裁反；
- 面装配后翻转“仅作 neigh”的单元的一条共享面，保证
  `owner.max()+1 == n_cells`（GPH 统计口径）。

## 3. 参数

| 参数 | 含义 | 默认 |
|------|------|------|
| `divisions` | 根盒内部格点每轴划分数（seed 密度） | 12 |
| `surface_stride` | 表面点抽样步长（1=全部） | 8 |
| `clip_to_surface` | 表面 seed 胞元按表面平面裁剪 | True |
| `max_clip_planes` | 每胞元裁剪平面数上限 | 64 |
| `max_cells` | 单元上限 | 200_000 |

## 4. 使用

```bat
python -m polymesh box.pph -o out\poly_vox --divisions 8 --surface-stride 16
python -m polymesh part.stl -o out\poly_vox --divisions 10 --surface-stride 4
python -m polymesh box.pph -o out\poly_rough --no-clip   # 不贴体（纯 Voronoi）
```

GUI：`Execute → Polyhedral Mesh (Self Build)…`（需要 PPH 已有 GPH 成员占位；
写回为 `*.polymesh.pph`）。

## 5. 实测（box.pph，divisions=8 / stride=16）

- 2202 单元（1891 表面边界单元 + 336 内部单元），1866 个表面胞元被裁剪；
- 面边数分布 3–12（真多面体：四边形为主 + 五/六边形 + 少量三角形/高边形）；
- 单元总体积 ≈ 域体积（均值 × 单元数 ≈ 9.9e-7 vs 盒 1e-6）；
- GPH 读回：13582 面 / 2202 单元 / 3271 边界面，查看器可渲染。

## 6. 已知限制与后续

- 无 Lloyd/平滑、无近壁层、无特征保形（尖角/ridge 需 VoroCrust 式加权 seed）；
- 非水密面片依赖射线法投票；薄特征处表面平面裁剪可能过度；
- 边界单元由表面 seed 生成，单元数 ≈ 表面 seed 数 + 内部 seed 数，
  粗网格时边界单元占比高；
- 性能：Delaunay + 逐胞元裁剪在 box 样例约 40s（stride 16），
  后续可并行化种子裁剪与空间索引；
- 面区域映射（frid/cvol）、质量统计与 scFLOW 对比未做。
