# 面板状态存储映射（R4-3 静态审计）

> 由 tools/panel_store_audit.py 生成（静态启发式，逐条带 file:line 证据）。
> 口径：session=仅内存；xml/xenv/prp/snapshot=落盘存储。
> 源：nav_panels.py（共 37 个面板类）

## 汇总

| 分类 | 面板数 |
|---|---|
| none | 17 |
| persisted | 13 |
| memory_only | 4 |
| read_only | 3 |

## 明细

| 面板 | 页面 key | 判类 | 读 | 写 | 证据（首个写/读命中） |
|---|---|---|---|---|---|
| CondTypeCatalogDialog | - | memory_only | session, xml | session | session:write@L14894; session:read@L14894; xml:read@L14893 |
| CreatePartsBody | create_parts | memory_only | session, xenv, xml | session | session:write@L1026; session:read@L1026; xml:read@L1081 |
| ExecuteBody | execute | memory_only | session, xenv | session | session:write@L14218; session:read@L14218; xenv:read@L14262 |
| _PartsControlFollowupBody | - | memory_only | session | session | session:write@L362; session:read@L338 |
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
| AnalysisModelWizardBody | build_am_detailed | persisted:xenv | session, snapshot, xenv, xml | session, xenv | session:write@L12240; session:read@L12240; xml:read@L12545 |
| ImportPartBody | import_part | persisted:xenv | session, xenv, xml | session, xenv | session:write@L683; session:read@L683; xml:read@L710 |
| MeshParamBody | mesh_param | persisted:xenv | session, xenv, xml | session, xenv | session:write@L14047; session:read@L14047; xml:read@L14117 |
| MesherFaceterBody | mesher_faceter | persisted:xenv | session, xenv, xml | session, xenv | session:write@L2389; session:read@L2389; xml:read@L2318 |
| ModifyPartsBody | modify_parts | persisted:xenv | session, xenv, xml | session, xenv | session:write@L1747; session:read@L1747; xml:read@L1767 |
| NonSolidBody | non_solid | persisted:xenv | session, xenv, xml | session, xenv | session:write@L3641; session:read@L3641; xml:read@L3668 |
| OctreeParamBody | oct_param | persisted:xenv | session, xenv, xml | session, xenv | session:write@L13430; session:read@L13430; xml:read@L13503 |
| OptionNavBody | option_nav | persisted:xenv | session, xenv | session, xenv | session:write@L14353; session:read@L14325; xenv:write@L14374 |
| ConditionsBody | conditions | persisted:xml | session, xml | session, xml | session:write@L7090; session:read@L7090; xml:write@L7133 |
| PartMaterialBody | part_material | persisted:xml | prp, session, xml | session, xml | session:write@L4659; session:read@L4582; xml:write@L4645 |
| PartsControlBody | parts_control | persisted:xml | session, xml | session, xml | session:write@L305; session:read@L305; xml:write@L331 |
| RegisterRegionBody | regions | persisted:xml | session, xml | session, xml | session:write@L2998; session:read@L2923; xml:write@L3065 |
| SolverSettingsDialog | - | persisted:xml | xml | xml | xml:write@L6162; xml:read@L6158 |
| GenericCondBody | - | read_only | xml | - | xml:read@L14513 |
| HeatTransferPresetDialog | - | read_only | xml | - | xml:read@L14915 |
| SolarSiteDialog | - | read_only | xml | - | xml:read@L14958 |

## 落盘候选（R4-4 用）

* PartsControlBody -> persisted:xml，页面 key parts_control
* ImportPartBody -> persisted:xenv，页面 key import_part
* ModifyPartsBody -> persisted:xenv，页面 key modify_parts
* MesherFaceterBody -> persisted:xenv，页面 key mesher_faceter
* RegisterRegionBody -> persisted:xml，页面 key regions
* NonSolidBody -> persisted:xenv，页面 key non_solid
* PartMaterialBody -> persisted:xml，页面 key part_material
* SolverSettingsDialog -> persisted:xml，页面 key -
* ConditionsBody -> persisted:xml，页面 key conditions
* AnalysisModelWizardBody -> persisted:xenv，页面 key build_am_detailed
* OctreeParamBody -> persisted:xenv，页面 key oct_param
* MeshParamBody -> persisted:xenv，页面 key mesh_param
* OptionNavBody -> persisted:xenv，页面 key option_nav
