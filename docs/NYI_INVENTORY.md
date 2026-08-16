# PPH Viewer NYI 菜单清单

> 由 `tools/scan_nyi_menus.py` 自动生成。
> 对应日志：`[…] not available in PPH viewer`（现已灰显）。

合计 **7** 项。P4-4 逐项评估见各条附注。

## File(&F)

- Create Actran Files… — **产品边界**：仅 scFLOW2Actran Acoustic Session 可用（帮助页原文），保持灰显。
## Edit(&E)

- Define Facet Part… — **暂缓**：依赖 facet(patch) 数据导入链路，查看器暂无 patch 导入。
- Create Non-Facet/Closed Volume Part… — **暂缓**：坐标指定 part 表单可做，但需补 pph 写回语义验证。
- Create 2D Sub-mesh Meshing Unit… — **暂缓**：2D sub-mesh 单元编辑属 mesher 深水区（且 patch/网格导入/wrapping 场景不可用）。
## Ridge

- Restore Closed Volume Data… — **产品边界**：仅 patch 导入 + Store and Open 再导入场景可用。
- Fix Marked Element Shape — **暂缓**：选中单元形状修改（网格编辑），需单元级编辑器。
## Select(&S)

- Spread Selected Face to Selected Edge — **暂缓**：仅 MDL 导入时有效；需边约束的面扩散算法（可基于 polymesh 邻接后续实现）。
