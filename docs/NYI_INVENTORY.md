# PPH Viewer NYI 菜单清单

> 由 `tools/scan_nyi_menus.py` 自动生成。
> 对应日志：`[…] not available in PPH viewer`（现已灰显）。

合计 **1** 项。P4-4 逐项评估见各条附注。

## Ridge

- Restore Closed Volume Data… — **产品边界**：仅 patch 导入 + Store and Open 再导入场景可用。

## 产品边界声明（Sprint H5 统一入册）

### CATIA V4/V5/V6 导入（域 4）

**J2 实测重注册（2026-09-05，DEV_PLAN §21.6 / gap §10.21；推翻 §10.19-I7「V5 导入边界解除」）**：真样本在位（starcat5 15 件 V5_CFV2）但宿主 COM 读链对 CATPart **静默零几何**——4 格式裸宿主矩阵（J2 r3 cadmatrix）：XT（SNode alive + 1 零件 + bbox [0,0.01]）与 STEP（SNode alive + 2 零件 + 真实 bbox）几何落地 = Datakit 链在本机 COM 面活着，唯 CATPart ×2 样本零 SNode、`GetSParts` 空（早/晚两轮一致，排除异步慢导入）、bbox = ±DBL_MAX 空指纹，全程 err=0 无模态（29/29 × 4 冷启动）。I7 的 sn2__alive=True 实为 box.pph 自带 "Part" 节点混淆（c1_out 容器差分零 CATPart 几何）——I7 结论撤回。①MDL 产物级闭环不可达：P12-D snode 全链配方在 CATPart 上复放 err=0（137 checks）但跑在空组上（MDL/VMDL Nothing）。根因 = CATIA 特异性（同链 XT/STEP 均落地）：指向本机 CADthru CATIA V5 读特性未授权（许可矩阵唯 CATIA V5 带 R/RW 双变体 = 独立特性）或 Datakit CATIA 转换器 headless no-op；手册导入矩阵无许可注（导出才注）。**余边界**：复验前置 = CADthru CATIA 读特性授权（或 GUI 导入路线对照判别 license vs COM 特异）；V4/V6 样本全机缺失；原生存写向（CATIA V5 / SAT / IGES）为许可门控导出面，非域 4 导入缺口。`ImportCADAsFacet` 前置已钉死为输入格式 = 面片格式（STL True 落 part.mdl；XT/CATPart 干净业务拒 = 归 OpenCadFile 链，非许可门）。

### Actran Acoustic（域 3 菜单 / 域 8 链）

**产品边界**：typed 接线链绿（`CreateActranFiles` e2e err=0）但业务 retval=False——Acoustic Session 前置在本机无样本可构造；菜单已接线，前置具备即可复验（P12-F §10.8 如实记录）。

### Restore Closed Volume Data…（域 10）

**J1 实测升级（2026-09-05，DEV_PLAN §21.5 / gap §10.20）**：全链前三腿打通——①同几何 12 三角立方体换件秒级成立（60k 三角同几何 STL 使 ImportPatchAsCAD 在工作进程内病态空转 2/2 复现，面片规模边界实证）；②MDL Wizard 重放 **151/151 err=0 全绿**（遗留⑤向导腿解除：录制变量别名 + AF 前置 + 模型状态 1.8MB snapshot 内嵌实证）；③容器级成对注入（`.his` 成员 + main.xml `<storedclosedvolumes>` 声明——装载开关，COM 换件重置该块的精确元素落点）→ 重开 `GetStoredClosedVolumes`=1。**恢复腿产品闸门维持关闭**：重开场景 `IsClosedVolumeRestorationAvailable`=False、候选查询空数组（cand_ub=-1）、`RestoreClosedVolumes` err=0 retval=False——两独立场景复现（I3 r3 cv1b 原生存储 + J1 r7 向导重建+注入），restorable 三态=-1 如实入册。域 10 边界维持：恢复可用性闸门在 COM 面不可构造（GUI [Store and Open] 对话钮无 COM 等价物），前置具备即可复验。遗留④宿主 VBS 能力时变当日未复现（重载日午后向导段正常执行）。

