# 下一步开发优先级建议（2026-09-13）

> 目标：**用最短路径补齐功能完整性与深度**。前提约束（用户指定）：
> **CAD 只做 x_t 与 STEP，其余格式先忽略。**
> 基线：HEAD `7838278` + J6/J7 未提交改动；独立复核见
> `docs/CODE_STATE_AUDIT_20260906.md`（全量回归 1 failed / 1101 passed / 4 skipped）。

---

## 排序原则（为什么是这个顺序）

1. **先让"完成"可被验证**。当前回归是红的、E2E 证据没有回归锁定、36 个测试被同名类遮蔽——
   在这个基线上做任何新功能，都无法证明它没把别的东西弄坏。这一步最便宜（≈3 人日），
   却是后面所有"已完成"的前提。
2. **再做用户指定的 CAD 双格式**。x_t 与 STEP 是目前**唯一既有宿主通道、又有（x_t）离线通道**
   的格式，投入产比最高；且它们的闭环需要 P0 建立的"宿主回读验收"基建，两者咬合。
3. **把"写端宿主回读"当成跨域杠杆**。MDL/OCT/GPH/PPH 四个写端目前全部只在本仓 reader 上
   自证（L2）。一旦打通宿主回读，域 1/2/5/9/10 同时从 L2 抬到 L3——这是全仓最大的一处
   单点杠杆。
4. **修 3 个确定性缺陷**，让自研网格产物第一次能被宿主打开。
5. 之后按"落差 × 杠杆"排：条件体系（65%）→ GUI 落盘（语义 35–40%）→ 数值等价证据 → 文档口径。

---

## P0 · 解锁项：把基线与证据变成可信（≈3 人日）

| # | 任务 | 具体动作 | 验收 | 人日 |
|---|---|---|---|---|
| P0-1 ✅**已完成**（2026-09-13） | ~~修红~~ | 已删除 6 份重复 `TestBackendConvergence`（380 行死代码），并把字面量断言改为契约断言；`tests/test_host_pipeline.py` 29 passed | **全量回归 1112 passed / 4 skipped / 0 failed（643 s）—— 首次全绿** | 1 |
| P0-2 | **E2E 证据入回归** | 新增 `tests/test_e2e_artifacts.py`：解析根目录 `p12*_e2e.log`，断言 `has_end` + `err0==total` + 关键 alive 键（`sn2_`/`mg_`/`vmdl_`…）；对 `_p12q_j7_summary.json` 做结构断言 | 任一被截断/回归的日志立即变红；**永久堵死"截断日志当成功凭证"** | 1 |
| P0-3 | **写端宿主回读 harness** | 通用流程：本仓写出 `*.pph` → 宿主 `OpenProject` → 成员清单/几何探针（`GetSParts`/`BoundingBox`/`DoesMeshExist`）→ 落 JSON 证据 | MDL / OCT / GPH / PPH 四类写端各 1 条 host round-trip 绿；无宿主时 skip | 2 |

> P0-3 同时是 CAD 闭环的最后一环，不要把它当成"格式层的事"。

---

## P1 · CAD x_t + STEP 双格式闭环到 L3（≈8 人日，用户指定优先）

### 现状（实测）
| 通道 | x_t | STEP |
|---|---|---|
| 宿主 `OpenCadFile` | ✅ 绿（我方对照腿 2/2：SNode + bbox [0,0.01]） | ✅ 部分（J2 r3：2 零件 + 真实 bbox） |
| 离线解析/剖分 | ✅ `cad_import.py` + `ps_tessellate` + `ps_facet2_nodes`（pskernel 同内核） | ❌ **无** |
| 拓扑对拍（宿主 vs 本仓） | ❌ 从未做 | ❌ |
| 导入 → BAM → 产物 → **宿主重开** | ❌ | ❌ |
| 多体/装配/单位/命名 | ⚠️ 仅单零件冒烟 | ⚠️ 仅 bbox |
| 错误路径（损坏/超版本） | ❌ | ❌ |

### 任务

| # | 任务 | 动作 | 验收 | 人日 |
|---|---|---|---|---|
| P1-1 | **验收口径钉死** | 定义 x_t/STEP 的"完成"= ①导入非空几何 ②拓扑计数与宿主一致 ③零件名/单位/材料映射可持久化 ④产物宿主可重开 ⑤错误路径有明确报错不静默 | 写入 DEV_PLAN 新章；后续所有条目按此判定 | 0.5 |
| P1-2 | **x_t 离线↔宿主量化对拍**（最高价值） | 同一 `.x_t`：宿主 `OpenCadFile` 的 MDL 产物 vs 本仓 `ps_tessellate.tessellate_xt` 结果，逐项比 BODY/FACE/EDGE/VERTEX 计数、表面积、bbox、体素数 | 对拍表入册；差异 ≤ 容差或给出归因；**这是同内核可达 L3 的最短路径** | 2 |
| **R2-1/R2-2 CAD 全链闭环 + 面元等价** ✅**已达成**（2026-09-14） | 三段 gate（build/mesh/reopen）+ 录制配方补全 | x_t 腿 build 42/42、mesh **176/176**、reopen 25/25 全 err=0，**`mesh_exists=True`（同会话 + 重开）**；根因=**流体区域登记缺失**（`CreateFluidRegion`/`RegisterSPart`），`CreateMesh*` 返回值不可信；面元级：总面积 **0.0006==0.0006（相对误差 0.0）**、六轴向面积逐轴相同 | 见审计 §17 / `_p12u_gate/r2_1_*.json`、`_p12u_cmp/r2_2_facets.json` | **已完成** |
| **R3-1/R3-2 端到端健壮化 + BC 去壳铺开** ⚠️**部分成**（2026-09-14） | 修探针/编码两个基础设施缺陷；去壳做成全页右键通用入口 | x_t 腿 mesh 176/176 + `mesh_exists=True`（含重开）稳定复现；**STEP 腿定位为宿主在网格计算中真崩溃**（`host_pids: []`）→ R4-1 参数标定；条件页去壳一次全覆盖（`tests/test_cond_deshell_r32.py`） | 见审计 §18 | x_t 已完成 / STEP 入 R4 |
| **R4 面板落盘 + 条件零破坏 + STEP 定性** ⚠️**4/5 成**（2026-09-14） | R4-2 host-gone 归因字段 / R4-3 面板存储审计（37 类：persisted 11、memory_only 6）/ R4-4 OptionNav→main.xenv（宿主 25/25 err=0）/ R4-5 24 条去壳改写（宿主 71/71 err=0、条件回读 12/12）/ R4-1 STEP 定性为宿主参数敏感的自行退出（90 s→1502 s+，仍无成功档） | 见审计 §19、`_p12u_gate/r4_4_xenv.json`、`r4_5_cond.json`、`r4_1_step_A.json`；面板映射 `docs/PANEL_STORE_MAP.md` | R4-1 交 R5-1/R5-2 |
| **R5 进度信号 + 面板落盘再切 2 页** ✅**2/5 成**（2026-09-14） | R5-1 CPU 进度信号（宿主在场才生效）+ 内存取证 / R5-3 `MeshParamBody`+`NonSolidBody` 落 main.xenv（审计 persisted 13、memory_only 4，宿主 25/25 err=0）；R5-2/4/5 顺延 R6 | 见审计 §20、`_p12u_gate/r5_3_xenv.json`、`docs/PANEL_STORE_MAP.md` | R5-2 已被 R5-1 解锁 |
| **R6 宿主键实测 + 面板收尾 + STEP 阶梯** ⚠️**3.5/5 成**（2026-09-14） | R6-5 实测 5 条宿主键（含「数值 setter 不回读原值」发现）/ R6-4 memory_only 4→2 / R6-1 三档实测推翻参数假说且用内存探针否证 OOM；R6-2、R6-3 顺延 R7 | 见审计 §21、`_p12u_gate/r6_5_keys.json`、`r6_1_step_coarse.json` | R7-1 换假设定性 |
| **R7 宿主崩溃定性 + 反向写宿主键 + 面板收尾** ✅**3/5 成**（2026-09-14） | R7-1 定性为**工作进程 APPCRASH（mfc140u.dll）**（非优雅退出、非 OOM）/ R7-4 写 xenv 键宿主 3/3 回读一致、27/27 err=0 / R7-5 memory_only 2→1（仅剩对话框）；R7-2、R7-3 连续三轮顺延 → R8 定为主项 | 见审计 §22、`_p12u_gate/r7_4_write.json` | R8-1/R8-2 主项 |
| **R8 条件封顶 + STEP 绕行定位 + 取证/宿主键闭环** ✅**4/5 成**（2026-09-14） | R8-1 实测封顶（16 个未落键 creator 收割后零新增 → 92 精确键 = 全部可落点类型，≥140 前提有误）/ R8-3 拦路石定位到**宿主摄取 CADthru x_t**（离线产物正常、宿主 `sn_=False`）/ R8-4 host-gone 补记工作进程画像 + WER / R8-5 面板键=实测键闭环；R8-2 数值等价连续四轮顺延 → R9 唯一主项 | 见审计 §23、`p12c_harvest_report.json`、`_p12u_gate/r8_3_*` | R9-1 主项 |
| **R9 x_t 拒收判据 + 崩溃标记 + 账目口径** ✅**3/5 成**（2026-09-14） | R9-2 定位**宿主拒收 CADthru x_t = schema 版本 v37 > 宿主 v34**（`SCH_*` 行可复现判据）/ R9-4 `host_crash` 标记 / R9-5 账目常量 165 = 92+1+72；R9-1 数值等价连续五轮顺延 → R10-1 锁定预算，R9-3 顺延 R10-3 | 见审计 §24、`_p12u_gate/r9_2_xt_diff.json`、`r9_5_cond_ledger.json` | R10 单主项 |
| **R10 零流场判据 + 控版否证 + 宿主键 8 条** ⚠️**2.5/3 成**（2026-09-14） | R10-1 前提修复：`zero_field_report`（主变量判据）+ 真数据证明 I5 b1/b2 是零流场；双跑未做 → R11-1 锁定 / R10-2 CADthru 固定 v37、COM 无法控版（否证）/ R10-3 新核实 3 键、写回回读 3/3、27/27 err=0（累计 8 条） | 见审计 §25、`_p12u_gate/r10_3_*.json` | R11-1 唯一主项 |
| **R11 零流场入 gate + 宿主侧导出否证** ⚠️**1.5/3 成**（2026-09-14） | R11-3 零流场直接 FAIL（CLI exit=2，7 项测试）/ R11-2 证伪「宿主侧导出 v34」（宿主内核 v37、写得出读不了，悬挂 729 s），**但发现 `transmit_nw_version` 未使用 → 离线降版可达**；R11-1 因宿主挂起**显式让位** | 见审计 §26、`_p12u_gate/r11_2_host_xt.json` | R12-1 降版 / R12-2 双跑 |
| **P2 验收** ✅**已达成**（2026-09-13 收口） | 宿主回读自研产物 | MDL/OCT/GPH 三写端对宿主原生产物**逐字节往返相同**（新增 `tests/test_writer_host_fidelity.py`）；宿主实机打开"三成员全部本仓重写"的工程：`sn_/mdl_/oct_=True`、`mesh_exists=True`、bbox [0,0.01]、31/31 err=0（两次独立运行） | 见审计报告 §16.10 | **已完成** |
| ~~P2 验收~~ ⚠️*（历史）* | 宿主回读自研产物 | ① 容器路径 ✅（纯克隆通过）；② MDL/OCT 结构达标（MDL 全节逐字节等、OCT 差 2 字节）；③ **GPH 写端从 8 节补到 20/23 节、LS_Links/LS_Nodes 已与宿主逐字节相同**；④ 宿主行为由「干净拒绝」变为「`OpenProject` 挂起」= 开始解析我们的成员。**剩余靶心：LS_SurfaceRegions 缺每区面号数组（−38,416，占 98%）** + VolumeRegions/Parts 各 −16 + 三个元数据节 608 B | 见审计报告 §16.8/§16.9 | **≈1 人日**（原估 3） |
| **P1-0** ✅**已完成** | ~~验证 `scConverter` 通道~~ → **改判：用 CADthru COM** | 实测：`scConverter` **不是** CAD 转换器（只有 FLD/iFLD/P2FLD 三个对话框）→ 不通。**改走 `CADthru_Bx64net.Application.2025`**（独立 LocalServer32）：`doc.OpenXtFile(step)` + `doc.SaveXTFile(asm, out)` → **通了**，且**不需宿主、不需许可**（死许可地址下仍成功），单文件 9.5–18 s。几何与直接导入 STEP **完全一致**（bbox [-82.2,36] / parts 1）。产出工具 `tools/cadthru_convert.py`。详见审计报告 §15 | 已完成（0.5 人日） |
| P1-3 | **STEP 离线化（缓存 x_t）**——**改用 P1-0 的 CADthru 通道** | 用 `tools/cadthru_convert.py`（`doc.OpenXtFile` + `doc.SaveXTFile`）把 STEP → x_t 落成员，**不启动 scFLOWpre、不需要许可**；之后复用离线栈；装配树/零件名/单位写进 `main.xml` | STEP 具备全免许可离线通道；单文件 ≈10–18 s | **1**（原 2，因 P1-0 已铺路） |
| P1-4 | **端到端 gate ×2** | `OpenCadFile → BAM(CreateMDL/VMDL) → CreateOctree → CreateMesh → SaveProject → 宿主重开`，x_t 与 STEP 各一条 | 两条 gate 全 err=0 + 产物宿主重开非空；证据入 `_p12s/` 并纳入 P0-2 的回归 | 2 |
| P1-5 | **多体/装配/错误路径矩阵** | 多 body x_t、装配级 STEP（AP203/214/242）、损坏文件、超版本文件、路径含空格与中文。**注意**：STEP 导入后 `QuerySNodeByName("Part")` 与 stem 查询**均返回 False**（三腿实测），零件/装配发现须改走 SNode 树枚举，不能沿用 x_t 的按名查询配方 | 每格有明确业务判定（成功/业务拒/报错），无静默零几何 | 1.5 |
| P1-6 | **格式策略落地（按用户指示收敛）** | 把 CATIA/3DXML/SolidEdge/JT/Rhino/VDAFS 从 backlog 移除；`docs/NYI_INVENTORY.md` 改为**产品决策：CAD 仅支持 x_t/STEP**，并附本次许可实证（本机缺 3DXML/SolidEdge/JT/Rhino/VDAFS 的 `OP_*`；CATIA 虽已授权但转换核静默零几何） | 域 4 从"边界待裁决"变成"范围已定"，不再消耗后续冲刺 | 0.5 |

> **不建议**：为 STEP 写离线解析器（工作量以月计，且与宿主 Datakit 结果不可能一致）；
> P1-3 的"宿主转一次、离线复用"是同等效果下便宜一个数量级的做法。

---

## P2 · 让自研产物第一次被宿主打开（≈4 人日）

| # | 任务 | 证据/影响 | 人日 |
|---|---|---|---|
| P2-1 | `voxmesh` 子序改宿主约定 `x+2y+4z`（`voxmesh.py:459-467` 与 `578-589`），并加**非对称树**交叉校验测试 | 当前 L-shape 回读 127/155 叶子错盒；GUI 写出的 `.oct` 宿主会重建为另一棵树 | 1 |
| P2-2 | `native_bam` 改用相对微小面判据（`tiny_pct`/`SOLID_BASE_TINY_FACE_WIDTH_RATIO`，已接线但被丢弃）或按 bbox 对角缩放；ridge 节点规则 `>=2` → `>=3` | 默认参数会把黄金 box 的 60,492 面**全部删除**（kept=0）；ridge 节点 1,877 vs 宿主 188 | 1 |
| P2-3 | MDL/OCT section 头 36→40 字节（对齐 `gphstats.py:807`）；补 MDL 种子点与 ridge 区域数组写出；修 `oct.unit` 误判 | 写端唯一挡在 L3 前的格式偏差 | 1.5 |
| P2-4 | `quality.py` 长宽比按文档定义重写或从报告移除；`fit_to_surface` 效果核查 | 当前在宿主黄金网格上给 NaN/62,777，在 polymesh 上给 1e14 | 0.5 |
| **P2-5**（P1-0 新发现） | **补装配遍历**：`ps_facet2_nodes` 的 `receive_xt` 对 `PART1` 装配流返回装配 tag，`body_faces`/`facet_body`/`decode_brep` 直接 `access violation reading 0x5C`。需按 `PK_ASSEMBLY_*` 枚举子部件后再剖分 | 离线 x_t 管线目前只能吃单 body 流；CADthru 输出（以及 `box.x_t` 的 5 tag→1 部件）都受影响 | 1 |

**验收**：自研 `.oct`/`.gph`/`_part.mdl` 首次被**宿主打开且几何非空**（依赖 P0-3）。

---

## P3 · 条件体系补深（最大单域洼地，≈6 人日）

| # | 任务 | 说明 | 人日 |
|---|---|---|---|
| P3-1 | **停止写猜测键** | 64 个 `inject_sibling_sample_fields` 复制来的 schema 在 UI 上标注"推测"，默认不写盘；`write_condition_to_xml` 加白名单 | 1 |
| P3-2 | **宿主收割扩面** | 89 个 `CreateCond*` 仍有约 43 个未收割；脚本化 `create → Save → diff main.xml → 提键` | 3 |
| P3-3 | **BC 子编辑器去壳** | 由"3–5 标签"升级为 schema 驱动全字段（`CondBoundaryFlowIO` 有 592 个字段路径） | 2 |
| 验收 | 精确键 90 → **≥140/165**；写盘条件在宿主零破坏（P12-C 的 71=71 恒等法） | | |

---

## P4 · GUI 面板落盘化（≈5 人日）

| # | 任务 | 现状 | 人日 |
|---|---|---|---|
| P4-1 | Option Settings 20/23 页落 `main.xenv` | 现在只写内存 session，重启即失 | 2 |
| P4-2 | Part Material / Mesh Param / Non-Solid / Register Region Apply 落盘 | 同上 | 2 |
| P4-3 | `main.sctsnapshot` 回写 + Undo 真回滚 `member_bytes` | 快照在编辑后即过期，宿主可能拒开 | 1 |

---

## P5 · 数值等价的证据质量（≈3 人日）

- 用**有真实流场**的算例（50 Pa 变体）重做 I5 双跑——当前 delta 表算在 PRES/VEL 恒为 0 的零流场上，近乎空断言。
- 明确 `.fld/.iFLD` 是否可得：得则接入，不得则在文档中撤回该项 ✅。
- `solver_delta` gate 模式常态化（已有，接进 P0-2 的证据回归）。

---

## P6 · 文档口径修正（0.5 人日，可与任意阶段并行）

- §9.7 第 12 项（FLD 回读）撤回；"12 域 100%"改为分域实测值 + 显式豁免清单；
  修正 `p12h_wizard_report.json` 与 `p12h_registry_report.json` 的矛盾；
  `_p12h_reconcile.py` 去掉硬编码 `{92,1,72}` 断言。

---

## 明确不做（建议写进范围声明）

| 项 | 理由 |
|---|---|
| CATIA V4/V5/V6、3DXML、SolidEdge、JT、Rhino、VDAFS 导入 | 用户指示；且本机缺对应 `OP_*` 许可 |
| STEP 离线解析器 | 与宿主 Datakit 结果不可能一致，月级投入 |
| Parasolid/scFLOW 内核、求解器、scPOST 复刻 | 策略豁免；本仓定位是"驱动 + 格式 + 验证" |
| 远程集群派发（SSHTransport） | 部署层豁免，本地端到端已够 |
| 自研 mesher 与官方内核的数值 bit 等价 | 不可行且无必要；改为质量阈值 + 宿主可开 |

---

## 一页速览

| 优先级 | 内容 | 人日 | 解锁什么 |
|---|---|---|---|
| **P0** | 修红 + E2E 入回归 + 写端宿主回读 harness | 3 | 让后续一切"完成"可验证；写端 L2→L3 的共同前置 |
| **P1** | **CAD x_t/STEP 闭环 L3** + 格式范围收敛 | 8 | 用户指定优先；域 4 从 70% 到可判定的 100% |
| **P2** ✅**代码部分已完成**（2026-09-13） | 5 个确定性缺陷全部修复（voxmesh 子序 / native_bam 容差与 ridge / MDL·OCT 段框 / oct.unit / quality 长宽比）+ P2-5 装配遍历；**MDL 已与宿主逐字节相同、OCT 仅差 2 字节**；新增 10 测试 | 4 | 宿主回读验收仍差 **GPH 写端补全**（≈3 人日，已定位到 13 个缺失节） |
| **P3** | 条件体系 90→140 精确键 + BC 去壳 | 6 | 最大洼地（域 8: 65%） |
| **P4** | GUI 面板落盘 + 快照回写 | 5 | GUI 语义 35%→70% |
| **P5** | 真实流场数值等价 | 3 | 域 12 证据可信 |
| **P6** | 文档口径修正 | 0.5 | 停止漂移 |

**合计 ≈ 29.5 人日（约 6 周单人）**。若只有一周：**P0 + P1-1/P1-2** ——
即"先让基线可信，再把 x_t 的离线↔宿主量化对拍做出来"，这两件做完，
CAD 域的深度就有了可复制的模板，其余格式与域照此复制即可。
