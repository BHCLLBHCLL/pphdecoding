# PPH Viewer NYI 菜单清单

> 由 `tools/scan_nyi_menus.py` 自动生成。
> 对应日志：`[…] not available in PPH viewer`（现已灰显）。

合计 **1** 项。P4-4 逐项评估见各条附注。

## Ridge

- Restore Closed Volume Data… — **产品边界**：仅 patch 导入 + Store and Open 再导入场景可用。

## 产品边界声明（Sprint H5 统一入册）

### CATIA V4/V5/V6 导入（域 4）

**产品边界**：全机 0 真 CATIA 几何样本（CATPart/CATProduct/cgr 均无；命中仅为 HDF5 `.exp`/链接器 export/Datakit `dtk.model` schema 误报）；Datakit schema 在位证明宿主 CATIA 转换链已装。样本缺失非代码缺口（§18.8 G3 裁决，2026-09-01）。

### Actran Acoustic（域 3 菜单 / 域 8 链）

**产品边界**：typed 接线链绿（`CreateActranFiles` e2e err=0）但业务 retval=False；菜单已接线。I4 实测升级（DEV_PLAN §20.8 / gap §10.16）：**条件面可构造**——`GetCondActranAnalysisControl` + 5 条件族（Source/OutputSolution/BoundaryNonReflection/Absorption/PointSource）全建 err=0、XML 落键 `actran_analysis_control`/`actran_acoustic_analysis_name`；`CreateActranFilesMonitor`（目录预存在）仍 retval=False、0 文件。**前置构成钉死** = 求解器侧 scFLOW2Actran 输出开关（etco `actran_acoustic_analysis_name.output`，官方样本缺省 false，无 COM Set 接口）+ CFD 瞬态数据流——scFLOW2Actran 为 CFD→Actran 单向耦合导出，纯前处理 COM 面不可构造完成态；retval=False 是产品闸门的确定性拒绝。前置具备（求解器侧开关 + 瞬态解）即可复验。

### Restore Closed Volume Data…（域 10）

**产品边界**：仅 patch 导入 + Store and Open 再导入场景可用（P4-4 评估沿用；P12-I I3 实测升级：帮助页前置原文钉死 + 存储腿持久化成立 `meshinggroup1_restore_cvol.his` + 再导入腿成立；恢复腿受 MDL Wizard 重放前置阻塞——patch 换件重置 `<mdl>` 块致 `GetMDL` Nothing，重建须 bam 级向导重放，受遗留③-e 宿主能力时变约束。前置不可构造证据入册 DEV_PLAN §20.7，遗留⑤待复验）。

