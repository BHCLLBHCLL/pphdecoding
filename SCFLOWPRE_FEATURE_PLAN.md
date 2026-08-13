# scFLOWpre 功能对照与未实现功能开发计划

> 更新日期：2026-08-10 ｜ 仓库：`pphdecoding` ｜ 对照：Cradle CFD 2025.2
>
> 完整 NYI 菜单清单由 `python tools/scan_nyi_menus.py` 生成 → [`docs/NYI_INVENTORY.md`](docs/NYI_INVENTORY.md)。

---

## 1. 当前实现状态（相对 2026-08-08 基线）

### 1.1 已交付（含近期追上项）

| 能力域 | 状态 | 说明 |
|------|------|------|
| `.pph` ZIP / 文本成员 / CRDL-FLD | ✅ | 打开、另存、成员编辑写回 |
| MDL / OCT 读 + GPH 统计 | ✅ / ◑ | 3D 显示；GPH 写端未自研 |
| GUI 四窗格 | ✅ | Navigation / Tree / Property / Draw / Message |
| 空工程 / Save / 项目文件夹 | ✅ | `new_empty_project` |
| XT CAD 导入预览 | ✅ | `cad_import` + pskernel facet_2 |
| Settings / Environment | ✅ | `option_settings` 多页 |
| Execute → COM VBS | ✅ | `ExecuteVBSWithFile` + `_FlagAsMethod`；`GetConditions`；OctParam `SetOctType`/`SetMinSize`/`DeleteOctree` |
| Octree Size for regions 列表 | ✅ | 按 `main.xml` 零件展开（非写死 Part） |
| Draw 视图键 | ✅ | X/Y/Z(/Shift)、F / Ctrl+F |
| 导航参数表单 | ◑ | 存 xenv/xml/session；网格/几何执行依赖宿主 |

### 1.2 仍存在的缺口

1. **约 20 个菜单项**仍灰显（见 `docs/NYI_INVENTORY.md`；Select/View/File VBS/Octants 多数已接线）。
2. **Wrapping / Disc / Overset** 可写 VBS 草稿；高层 ExecuteWrapping 仍待录制锁定。
3. **条件体系**有 `schemas/conditions.yaml` + `conditions_schema` 合并过滤器；~180 Cond* 表单仍不全。
4. **几何编辑** Create/Modify 写出 `BeginSolidEdit` VBS 草稿；实体 API 待录制。
5. **Solver / CMB / FPH** 未做。
6. **Select**：Pick Part/Face/Edge/Vertex 已接线；Rubber Box/Circle/Polygon 已改为
   真实框选（VTK HardwareSelector + 圆/多边形过滤）；宿主侧另有
   `Doc_.RubberBox/RubberCircle/RubberPolygon` 可锁定用于宿主内选择。

---

## 2. 「not available」分类

| 类型 | 机制 | 数量级 |
|------|------|--------|
| 纯 NYI 菜单 | `add_act` 无 `slot` → 灰显 + tooltip | ~70 |
| 导航 hint stub | Disc/Overset/Wrap×6 | 8 |
| 存参不执行 | Create/Modify/Regions/Oct/Mesh Create 等 | 十余处 |
| 双触发（已清理） | Face Pick / Option 1-Button 曾先 `_nyi` 再执行 | 已修 |

---

## 3. 分阶段计划（现行优先级）

### 阶段 0 — 文档与卫生（本迭代）
- ✅ 刷新本文与 `docs/NYI_INVENTORY.md`
- ✅ 清理双重 `_nyi`；NYI 菜单灰显 + tooltip

### 阶段 1 — 预处理主链路
- ✅ Octree 区域 Size 预填（xml/session/宿主参数）
- ✅ BAM/Wrapping 生成可执行 VBS 草稿
- ✅ Execute 默认 `use_api=True`；Solver 仍明确不可用

### 阶段 2 — Select / View
- ✅ Pick Part/Face/Edge/Vertex；Rubber Box/Circle/Polygon 真实框选
  （HardwareSelector；宿主 RubberBox API 已定位）
- ✅ Select All / Hide / Only Selected / Fit to Selected
- ✅ Refinement Level / 八叉树显示开关；Parts List / Region Check

### 阶段 3 — 几何 Edit
- ✅ Create/Modify → `BeginSolidEdit` VBS 草稿
- ✅ Register Region：拾取面 → `sface_num` 写 `main.xml`
- ✅ Ridge VBS 手册锁定：`VMDL_.RecalcRidge` /
  `RecalcRidgeFromProjectSetting` / `SetSelectedEdgeToRidge` /
  `SetSelectedEdgeToNonRidge`（+ `GetEdge`/`SetSelect`）
- ✅ Octant VBS 手册锁定：`Octree_.Refine` / `Merge` /
  `RefineByLevel` / `RefineByNumber` / `RefineFromCurvature` /
  `ShowOctBySelectedFace` / `ShowOctBySelectedEdge`；本地 refine/merge 并行
- ✅ Measurement；Undo 栈

### 阶段 4 — 条件与 File 自动化
- ✅ `schemas/conditions.yaml` + `conditions_schema` 合并过滤器
- ✅ File Start/Stop/Execute VBScript → COM
- ✅ Project Type / Fluid Material 对话框入口
- Solver/CMB/FPH 明确延后

### 阶段 5 — 可选自研 mesher
- ✅ Voxel/hex-dominant MVP：`voxmesh.py`（MDL/STL → 八叉树 → inside hex +
  切割带 polyhedra/rough hex → 写 `.oct`+`.gph`），GUI `Execute → Voxel
  Fitting Mesh (Self Build)…`；详见 `docs/VOXMESH_NOTES.md`
- ✅ 原生多面体 MVP：`polymesh.py`（Delaunay/Voronoi 对偶 + 表面平面裁剪，
  cfMesh pMesh / VoroCrust / LAVA 路线），GUI `Execute → Polyhedral Mesh
  (Self Build)…`；详见 `docs/POLYMESH_NOTES.md`
- ⏳ 2:1 平衡/pairing、边界层、面区域映射、质量平滑、性能优化

---

## 4. 近端里程碑

| ID | 内容 | 验收 |
|----|------|------|
| M0 | 文档 + 双触发清理 + NYI 灰显 | 无重复 WARN |
| M1 | 区域 Size 预填 + API Execute | 边长≈SECTITEM |
| M2 | Select/Fit/Hide 基础 | 手工清单 |
| M3 | Wrapping VBS 最小路径 | 录制对拍 |
| M4 | 一项几何操作经 COM | 重开 PPH 可见 |

---

## 5. 架构（不变）

计算密集步骤优先 **AutomationBridge（COM/VBS）**，自研引擎长期并行。详见历史 §4.1 服务层划分（Project / Schema / Geometry / Meshing / Job）。

## 6. 证据与工具

- 菜单扫描：`python tools/scan_nyi_menus.py`
- 宿主：`automation/host_pipeline.py`、`automation/pipeline_plan.py`
- 手册 / DLL 证据：原附录仍适用（Pre_eng、scFLOWpreCmd、SCTprime）
