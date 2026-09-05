# PPH Viewer NYI 菜单清单

> 由 `tools/scan_nyi_menus.py` 自动生成。
> 对应日志：`[…] not available in PPH viewer`（现已灰显）。

合计 **1** 项。P4-4 逐项评估见各条附注。

## Ridge

- Restore Closed Volume Data… — **产品边界**：仅 patch 导入 + Store and Open 再导入场景可用。

## 产品边界声明（Sprint H5 统一入册）

### CATIA V4/V5/V6 导入（域 4）

**I7 实测升级（2026-09-05，DEV_PLAN §20.11 / gap §10.19）**：全机再扫推翻 G3「0 真样本」前提——`starcat5` 教程数据 15 个真 CATIA V5 文件（魔数 `V5_CFV2`，10 CATPart + 5 CATProduct）在位；宿主读链 e2e 绿（`OpenCadFile` 真样本 → SNode "Part" 落地 + 全步 err=0，与 P12-D STEP 同型；`ImportCADAsFacet` 对 CATPart 与 XT 对照同 retval=False——非 CATIA 特异拒绝）。**V5 导入边界解除**；余边界：V4/V6 样本仍全机缺失；原生存写向（CATIA V5 / SAT / IGES）为许可门控的 CADthru 导出面，非域 4 导入缺口。Datakit 转换器许可特性矩阵（二进制串级）：9 家 CAD 读向，唯 CATIA V5 带 R/RW 双变体。

### Actran Acoustic（域 3 菜单 / 域 8 链）

**产品边界**：typed 接线链绿（`CreateActranFiles` e2e err=0）但业务 retval=False——Acoustic Session 前置在本机无样本可构造；菜单已接线，前置具备即可复验（P12-F §10.8 如实记录）。

### Restore Closed Volume Data…（域 10）

**产品边界**：仅 patch 导入 + Store and Open 再导入场景可用（P4-4 评估沿用；P12-I I3 实测升级：帮助页前置原文钉死 + 存储腿持久化成立 `meshinggroup1_restore_cvol.his` + 再导入腿成立；恢复腿受 MDL Wizard 重放前置阻塞——patch 换件重置 `<mdl>` 块致 `GetMDL` Nothing，重建须 bam 级向导重放，受遗留③-e 宿主能力时变约束。前置不可构造证据入册 DEV_PLAN §20.7，遗留⑤待复验）。

