# 面板状态存储映射（R4-3 静态审计）

> 由 tools/panel_store_audit.py 生成（静态启发式，逐条带 file:line 证据）。
> 口径：session=仅内存；xml/xenv/prp/snapshot=落盘存储。
> 源：nav_panels.py（共 37 个面板类）

## 汇总

| 分类 | 面板数 |
|---|---|
| none | 17 |
| persisted | 11 |
| memory_only | 6 |
| read_only | 3 |

## 明细

| 面板 | 页面 key | 判类 | 读 | 写 | 证据（首个写/读命中） |
|---|---|---|---|---|---|
| CondTypeCatalogDialog | - | memory_only | session, xml | session | session:write@L14847; session:read@L14847; xml:read@L14846 |
| CreatePartsBody | create_parts | memory_only | session, xenv, xml | session | session:write@L1025; session:read@L1025; xml:read@L1080 |
| ExecuteBody | execute | memory_only | session, xenv | session | session:write@L14189; session:read@L14189; xenv:read@L14233 |
| MeshParamBody | mesh_param | memory_only | session, xml | session | session:write@L14027; session:read@L14027; xml:read@L14092 |
| NonSolidBody | non_solid | memory_only | session, xenv, xml | session | session:write@L3640; session:read@L3640; xml:read@L3667 |
| _PartsControlFollowupBody | - | memory_only | session | session | session:write@L361; session:read@L337 |
| BeginWrappingBody | begin_wrap | none | - | - |  |
| CancelWrappingBody | cancel_wrap | none | - | - |  |
| ExecuteWrappingBody | exec_wrap | none | - | - |  |
| NavParamDialog | - | none | - | - |  |
| OctreeDetailDialog | - | none | - | - |  |
| OversetMeshBody | overset_mesh | none | - | - |  |
| PrismLayerDetailDialog | - | none | - | - |  |
| RetryWrappingBody | retry_wrap | none | - | - |  |
| SpecifyDiscontinuousPartsBody | specify_disc | none | - | - |  |
| WrappingOctreeParamBody | wrap_octree | none | - | - |  |
| WrappingParamBody | wrap_param | none | - | - |  |
| _Body | - | none | - | - |  |
| _ContactThicknessDialog | - | none | - | - |  |
| _CoordSpecifiedPartDialog | - | none | - | - |  |
| _FacetAccuracyEditDialog | - | none | - | - |  |
| _MaterialOptionsDialog | - | none | - | - |  |
| _MeshSubDialog | - | none | - | - |  |
| AnalysisModelWizardBody | build_am_detailed | persisted:xenv | session, snapshot, xenv, xml | session, xenv | session:write@L12225; session:read@L12225; xml:read@L12530 |
| ImportPartBody | import_part | persisted:xenv | session, xenv, xml | session, xenv | session:write@L682; session:read@L682; xml:read@L709 |
| MesherFaceterBody | mesher_faceter | persisted:xenv | session, xenv, xml | session, xenv | session:write@L2388; session:read@L2388; xml:read@L2317 |
| ModifyPartsBody | modify_parts | persisted:xenv | session, xenv, xml | session, xenv | session:write@L1746; session:read@L1746; xml:read@L1766 |
| OctreeParamBody | oct_param | persisted:xenv | session, xenv, xml | session, xenv | session:write@L13415; session:read@L13415; xml:read@L13488 |
| OptionNavBody | option_nav | persisted:xenv | session, xenv | session, xenv | session:write@L14306; session:read@L14278; xenv:write@L14327 |
| ConditionsBody | conditions | persisted:xml | session, xml | session, xml | session:write@L7075; session:read@L7075; xml:write@L7118 |
| PartMaterialBody | part_material | persisted:xml | prp, session, xml | session, xml | session:write@L4644; session:read@L4567; xml:write@L4630 |
| PartsControlBody | parts_control | persisted:xml | session, xml | session, xml | session:write@L304; session:read@L304; xml:write@L330 |
| RegisterRegionBody | regions | persisted:xml | session, xml | session, xml | session:write@L2997; session:read@L2922; xml:write@L3064 |
| SolverSettingsDialog | - | persisted:xml | xml | xml | xml:write@L6147; xml:read@L6143 |
| GenericCondBody | - | read_only | xml | - | xml:read@L14466 |
| HeatTransferPresetDialog | - | read_only | xml | - | xml:read@L14868 |
| SolarSiteDialog | - | read_only | xml | - | xml:read@L14911 |

## 落盘候选（R4-4 用）

* PartsControlBody -> persisted:xml，页面 key parts_control
* ImportPartBody -> persisted:xenv，页面 key import_part
* ModifyPartsBody -> persisted:xenv，页面 key modify_parts
* MesherFaceterBody -> persisted:xenv，页面 key mesher_faceter
* RegisterRegionBody -> persisted:xml，页面 key regions
* PartMaterialBody -> persisted:xml，页面 key part_material
* SolverSettingsDialog -> persisted:xml，页面 key -
* ConditionsBody -> persisted:xml，页面 key conditions
* AnalysisModelWizardBody -> persisted:xenv，页面 key build_am_detailed
* OctreeParamBody -> persisted:xenv，页面 key oct_param
* OptionNavBody -> persisted:xenv，页面 key option_nav
