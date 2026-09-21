# PPH Viewer NYI 菜单清单

> 由 `tools/scan_nyi_menus.py` 自动生成。
> 对应日志：`[…] not available in PPH viewer`（现已灰显）。

合计 **1** 项。P4-4 逐项评估见各条附注。

## Ridge

- Restore Closed Volume Data… — **产品边界**：仅 patch 导入 + Store and Open 再导入场景可用。

## 产品边界声明（Sprint H5 统一入册）

### CAD 格式范围：仅 x_t / STEP（域 4 · 产品决策 2026-09-13，R1-5）

**范围收敛**：本仓 CAD 导入只支持 **x_t** 与 **STEP**；CATIA V4/V5/V6、3DXML、SolidEdge、JT、Rhino、VDAFS 移出 backlog（不再排期）。依据：① **许可实测**（审计 §10，license.dat + lmstat 实证）：本机授权 CADTHRUSTD、OP_CATIAV5R/RW、OP_CATIAV4、OP_IGES、OP_SAT、OP_PROE、OP_SLDWRKS、OP_UNIGRAPHICS、OP_INVENTOR，但**无** 3DXML / SolidEdge / JT / Rhino / VDAFS 的 OP_*；② CATIA V5 读特性虽已授权，转换核仍**静默零几何**（6/6 样本、容器无 snapshot 成员，§9/§15）；③ x_t 与 STEP 既有宿主通道，x_t 另有**免宿主免许可**离线通道（§12–§15：pskernel 剖分 + CADthru 独立 COM 转换）。**前置钉死**：STEP 不在按格式许可门控名单内（CADthru 的 13 条 No valid license found to import 不含 STEP；DKCTCore 0 处 step）；ImportCADAsFacet 只接受面片格式（STL/MDL），CAD kernel 格式一律走 OpenCadFile。**复验前置**（若将来恢复 CATIA）：CADthru CATIA 读特性授权，或 GUI 导入路线对照以判别 license vs COM/headless 特异。

### Actran Acoustic（域 3 菜单 / 域 8 链）

**产品边界**：typed 接线链绿（`CreateActranFiles` e2e err=0）但业务 retval=False——Acoustic Session 前置在本机无样本可构造；菜单已接线，前置具备即可复验（P12-F §10.8 如实记录）。

### Restore Closed Volume Data…（域 10）

**J1 实测升级（2026-09-05，DEV_PLAN §21.5 / gap §10.20）**：全链前三腿打通——①同几何 12 三角立方体换件秒级成立（60k 三角同几何 STL 使 ImportPatchAsCAD 在工作进程内病态空转 2/2 复现，面片规模边界实证）；②MDL Wizard 重放 **151/151 err=0 全绿**（遗留⑤向导腿解除：录制变量别名 + AF 前置 + 模型状态 1.8MB snapshot 内嵌实证）；③容器级成对注入（`.his` 成员 + main.xml `<storedclosedvolumes>` 声明——装载开关，COM 换件重置该块的精确元素落点）→ 重开 `GetStoredClosedVolumes`=1。**恢复腿产品闸门维持关闭**：重开场景 `IsClosedVolumeRestorationAvailable`=False、候选查询空数组（cand_ub=-1）、`RestoreClosedVolumes` err=0 retval=False——两独立场景复现（I3 r3 cv1b 原生存储 + J1 r7 向导重建+注入），restorable 三态=-1 如实入册。域 10 边界维持：恢复可用性闸门在 COM 面不可构造（GUI [Store and Open] 对话钮无 COM 等价物），前置具备即可复验。遗留④宿主 VBS 能力时变当日未复现（重载日午后向导段正常执行）。


## 宿主侧能力边界（R45 自动生成）

> 与 `tools/host_member_sweep.py --report-only` 同源（证据 `schemas/host_member_availability.json` + 目录的 `host_absent` 标记）。这一节**不是菜单缺口**，是宿主 COM 面的实测边界。

### 取不到实例的类（先把前置流程跑出来）

- CondBoussinesqBaseTemp — 条件向导创建——宿主无 CreateCondBoussinesqBaseTemp 接口
- CondCoSim — 先做 CoSim 设置（本机语料无该条件）
- CondCoSimRegion — 先有 CoSim 区域（由 CoSim 条件派生）
- PropItem — 先注册材料/物性（或经闭空间的材料项取得）

### 宿主未实现的成员（27 条）

> Python 侧**不会**为这些条目造包装（调用必然 `com_error`）；手册有、宿主 `GetIDsOfNames` 解析不到。

- ClosedVolume — GetSweepDestinationFaceRegion / ImportCSV
- CondBoundaryFlowIO — GetMassVolumePressureInflowDirectionType​ / GetPbmFuncType / SetPbmFuncType
- CondFreeSurface — GetPhaseCheangeSw / SetPhaseCheangeSw
- CondInitial — GetPbmFuncType / SetPbmFuncType
- CondInitialShapeModify — RemoveMorphingRegion
- CondOutputTimeSeries — GetProjectonType / SetProjectonType
- CondPorousMedia — ImportCSV
- CondSource — IsEnableConditionForCalculation
- CoordinatesSpecifiedPart — GetRadiationValue / ImportCSV
- Doc — GetAllMapCondNames
- FaceRegionDerivedSheet — ImportCSV
- FluidRegion — ImportCSV
- IVEdge — GetPart / IsEqual
- MeshingGroup — GetDiscontinuous / ReplaceMDLMode / SetDiscontinuous
- MeshingGroupSetting — GetInternalUnit
- SpecialRegion — ImportCSV
- VolumeRegion — GetSweepDestinationFaceRegion
