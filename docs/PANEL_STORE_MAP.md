# 面板状态存储映射（R4-3 静态审计）

> 由 tools/panel_store_audit.py 生成（静态启发式，逐条带 file:line 证据）。
> 口径：session=仅内存；xml/xenv/prp/snapshot=落盘存储。
> 源：nav_panels.py（共 37 个面板类）

## 汇总

| 分类 | 面板数 |
|---|---|
| none | 17 |
| persisted | 16 |
| read_only | 3 |

## 明细

| 面板 | 页面 key | 判类 | 读 | 写 | 证据（首个写/读命中） |
|---|---|---|---|---|---|
| CondTypeCatalogDialog | - | memory_only | session, xml | session | session:write@L14934; session:read@L14934; xml:read@L14933 |
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
| AnalysisModelWizardBody | build_am_detailed | persisted:xenv | session, snapshot, xenv, xml | session, xenv | session:write@L12267; session:read@L12267; xml:read@L12572 |
| CreatePartsBody | create_parts | persisted:xenv | session, xenv, xml | session, xenv | session:write@L1045; session:read@L1045; xml:read@L1105 |
| ExecuteBody | execute | persisted:xenv | session, xenv | session, xenv | session:write@L14249; session:read@L14249; xenv:write@L14296 |
| ImportPartBody | import_part | persisted:xenv | session, xenv, xml | session, xenv | session:write@L698; session:read@L698; xml:read@L725 |
| MeshParamBody | mesh_param | persisted:xenv | session, xenv, xml | session, xenv | session:write@L14074; session:read@L14074; xml:read@L14144 |
| MesherFaceterBody | mesher_faceter | persisted:xenv | session, xenv, xml | session, xenv | session:write@L2416; session:read@L2416; xml:read@L2345 |
| ModifyPartsBody | modify_parts | persisted:xenv | session, xenv, xml | session, xenv | session:write@L1774; session:read@L1774; xml:read@L1794 |
| NonSolidBody | non_solid | persisted:xenv | session, xenv, xml | session, xenv | session:write@L3668; session:read@L3668; xml:read@L3695 |
| OctreeParamBody | oct_param | persisted:xenv | session, xenv, xml | session, xenv | session:write@L13457; session:read@L13457; xml:read@L13530 |
| OptionNavBody | option_nav | persisted:xenv | session, xenv | session, xenv | session:write@L14393; session:read@L14365; xenv:write@L14414 |
| _PartsControlFollowupBody | - | persisted:xenv | session, xenv | session, xenv | session:write@L372; session:read@L338; xenv:write@L373 |
| ConditionsBody | conditions | persisted:xml | session, xml | session, xml | session:write@L7117; session:read@L7117; xml:write@L7160 |
| PartMaterialBody | part_material | persisted:xml | prp, session, xml | session, xml | session:write@L4686; session:read@L4609; xml:write@L4672 |
| PartsControlBody | parts_control | persisted:xml | session, xml | session, xml | session:write@L305; session:read@L305; xml:write@L331 |
| RegisterRegionBody | regions | persisted:xml | session, xml | session, xml | session:write@L3025; session:read@L2950; xml:write@L3092 |
| SolverSettingsDialog | - | persisted:xml | xml | xml | xml:write@L6189; xml:read@L6185 |
| GenericCondBody | - | read_only | xml | - | xml:read@L14553 |
| HeatTransferPresetDialog | - | read_only | xml | - | xml:read@L14955 |
| SolarSiteDialog | - | read_only | xml | - | xml:read@L14998 |

## 落盘候选（R4-4 用）

* PartsControlBody -> persisted:xml，页面 key parts_control
* _PartsControlFollowupBody -> persisted:xenv，页面 key -
* ImportPartBody -> persisted:xenv，页面 key import_part
* CreatePartsBody -> persisted:xenv，页面 key create_parts
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
* ExecuteBody -> persisted:xenv，页面 key execute
* OptionNavBody -> persisted:xenv，页面 key option_nav
