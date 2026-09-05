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

**J1 实测升级（2026-09-05，DEV_PLAN §21.5 / gap §10.20）**：全链前三腿打通——①同几何 12 三角立方体换件秒级成立（60k 三角同几何 STL 使 ImportPatchAsCAD 在工作进程内病态空转 2/2 复现，面片规模边界实证）；②MDL Wizard 重放 **151/151 err=0 全绿**（遗留⑤向导腿解除：录制变量别名 + AF 前置 + 模型状态 1.8MB snapshot 内嵌实证）；③容器级成对注入（`.his` 成员 + main.xml `<storedclosedvolumes>` 声明——装载开关，COM 换件重置该块的精确元素落点）→ 重开 `GetStoredClosedVolumes`=1。**恢复腿产品闸门维持关闭**：重开场景 `IsClosedVolumeRestorationAvailable`=False、候选查询空数组（cand_ub=-1）、`RestoreClosedVolumes` err=0 retval=False——两独立场景复现（I3 r3 cv1b 原生存储 + J1 r7 向导重建+注入），restorable 三态=-1 如实入册。域 10 边界维持：恢复可用性闸门在 COM 面不可构造（GUI [Store and Open] 对话钮无 COM 等价物），前置具备即可复验。遗留④宿主 VBS 能力时变当日未复现（重载日午后向导段正常执行）。

