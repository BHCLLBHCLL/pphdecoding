# 原生 BAM（Build Analysis Model）—— native_bam.py

> 状态：2026-08-14 第一版。
> 定位：未启用 scFLOWpre API（Execute「使用 scFLOWpre API」关闭）时，
> 用**原生实现**跑完 Analysis Model Wizard 的全部关键步骤，产物为
> 布局与宿主一致的 `*_part.mdl`（`mdl.write_mdl` 扩展写端）。
> 官方 BAM 仍由 AutomationBridge（VBS/COM）驱动，见
> `automation/pipeline_plan.BAM_WIZARD_ACTIONS`。

## 1. 步骤对照（与录制 VBS 一一对应）

录制来源：`box_scflow_mdl.vbs`（2026-08-14）。

| # | scFLOWpre MDLWizard（VBS） | 原生实现（native_bam） |
|---|---------------------------|------------------------|
| 1 | `BeginMDLWizard` / `Proj_.SetRidgeProjectSolids/Sheets` / `SetUseAFFacetter` / `SetFacetAccuracySpecificationType` | `BamParams`（session["build_am"] / xenv FACET 键，见 `BamParams.from_session`） |
| 2 | `MDLWizard_.CreateBoundary` | `create_boundary`：BFS 一致定向（共享边反向遍历）→ 水密闭分量符号体积朝外 → 连通分量闭体识别 → `csid=(0,k)`；非水密分量 → `(0,0)` + 开放边计数 |
| 3 | `CreateMultiEntityInfo` ×6 | `detect_multifold`：多重边（>2 面共享）/ 多重面（顶点集重复） |
| 4 | Facet 精度设置（AF 角度/边长比/最大边、绝对值） | 参数透传（原生面片已存在，不重剖分） |
| 5 | `Set/ReconfigureSpatialSeparationSettings`（Influence of adjacent part） | 记录 `influence_enable/targets`（几何效应在宿主内核） |
| 6 | `SetAutoRemoveTinyFaceConfigured` | `remove_tiny` + `remove_tiny_tol` / `tiny_pct` |
| 7 | `MDLWizard_.CreateMDL` | 面片装配（输入即剖分结果：CAD 剖分或既有 MDL） |
| 8 | `FindAFFaceMatching(tol)` + `SetFaceMatched` | `match_faces`：质心距 ≤ tol + 法向相反 + 面积差 ≤1% → frid 合并 |
| 9 | `FindTinyFace(tol)` + `SetTinyFacesRemoved` | `remove_tiny_faces`：微小面顶点坍缩（union-find → 质心），退化面丢弃 |
| 10 | `RepairMDL` | `repair_surface`：焊接重复顶点 → 去退化/重复面 → 一致定向 → 去孤立点 |
| 11 | `CheckMDLErrors` | `check_errors`：报告行（level/count/type/cause）+ `buildable` |
| 12 | Ridge（CreateBoundary 副产品） | `detect_ridges`：二面角 > 阈值 → `LS_EdgeStateOfFaces` / `LS_StateOfNodes` |

拓扑变更步骤（微小面坍缩/修复）之后会**重跑 CreateBoundary** 得到最终
csid——对应录制中 `CreateMDL` 在全部配置完成后才执行。

## 2. 产物与写端

`build_analysis_model(points, faces, BamParams)` → `BamResult`：

- `csid=(b1,b2)`：part MDL 语义（b1=0 外部 / b2=所属闭体；体间界面属
  ridge MDL，原生 part 不内嵌——与 laptop 样例一致）；
- `frid` / `surface_regions` / `closed_volumes`（含记录 0=外部）/
  `volume_regions`（默认 `["FluidRegion"]`）；
- `edge_state`/`node_state`：尖边（默认二面角 >30°）与特征点（≥2 条
  尖边交汇），写出后查看器按 ridge 显示；
- `report`：`BamReport.rows`（level/count/type/cause，喂给向导
  Repair 页）+ 各步骤计数 + `buildable`。

`write_bam_mdl(result, path)` 走 `mdl.write_mdl` 扩展写端：

- `LS_MdlSurfaceRegions` 按宿主精确布局（`desc(type=1,255,1)` 名称记录 +
  20 字节节尾，box/laptop 样例钉死）；
- 新增 `LS_MdlClosedVolumes`（记录 0=外部；每记录 6 描述符，末值=体索引）
  与 `LS_MdlVolumeRegions`（box 风格，无内部种子点）写端；
- 全部经 `parse_mdl` round-trip 锁定（`tests/test_native_bam.py` /
  `tests/test_mdl_writer.py`）。

## 3. GUI 接线

| 入口 | 行为 |
|------|------|
| Execute（未勾选「使用 scFLOWpre API」）勾选 BAM | `_run_native_pipeline`：表面（MDL 或 CAD 剖分）→ 原生 BAM → 写 `*_part.mdl` → 后续 Octree/Mesh 用 BAM 后表面；报告存 `session["build_am"]["native_report"]` |
| Analysis Model Wizard → Create Facet / Build（API 关闭） | `_run_bam_pipeline` → `_run_native_bam`：写回 `*.native.pph` 并刷新 |
| 向导页按钮 Match / Clean / Clean all / Remove tiny faces | 置 session 标志（`apply_face_matching`/`repair`/`remove_tiny`），原生 BAM 执行对应步骤；宿主路径仍记 VBS 注释 |
| 向导 Repair 页 | 优先显示 `native_report`（真实 BAM 运行结果），否则回退本地 MDL 启发式探测 |

**宿主 MDL 保护**：既有宿主生成的 `*_part.mdl`（Application ≠
pphdecoding）**不覆写**——原生 BAM 仅更新检测报告；仅原生生成过的 MDL
或 CAD 剖分来源允许重写。

## 4. 参数（BamParams，键位对齐向导 session）

| 参数 | 默认 | 来源（session / xenv FACET） |
|------|------|------------------------------|
| `project_solids` / `project_sheets` | True | `project_solids` / `PROJECT_SOLIDS` |
| `use_facetter` | True | `use_facetter` / `USE_FACETTER` |
| `acc_type` | "0" | `acc_type` / `FACET_ACCURACY_SPECIFY_TYPE` |
| `tol_multifold_edge/face` | 1e6 | `tol_multifold_*`（1/N 分母） |
| `match_tol` | 1e-3 | `match_tol` |
| `remove_tiny` / `remove_tiny_tol` | True / 1e-3 | 同名 session 键 |
| `tiny_pct` | 5.0 | `tiny_pct` / `SOLID_BASE_TINY_FACE_WIDTH_RATIO`（0-1→%） |
| `apply_face_matching` / `repair` | True | 向导按钮标志 |
| `influence_enable` / `influence_targets` | False / [] | 同名 session 键 |
| `ridge_angle_deg` | 30.0 | — |

## 5. 已知限制

- 多重实体容差（`tol_multifold_*`）当前仅透传：原生多重边/面识别按
  精确拓扑（共享边计数/顶点集），不做容差合并；
- Influence of adjacent part 的几何效应（邻域尺寸影响）在宿主内核，
  原生仅记录 targets；
- 微小面坍缩是几何近似：宿主按特征线保留规则删除，原生为质心坍缩 +
  退化丢弃，薄特征处可能过度合并（可用 `remove_tiny=False` 关闭后仅报告）；
- 闭体名为空（与样例一致）；体区域不写内部种子点（box 风格）。

## 6. 测试

`tests/test_native_bam.py`（18 项）：单/双闭盒闭体识别、开放面片
buildable=False、反向面重定向、多重边/面、容差匹配与 frid 合并、
微小面删除/禁用、焊接去重去孤立点、写端全记录 round-trip、
session/xenv 参数映射、GUI 接线。
