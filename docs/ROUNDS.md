# R 轮次台账（R-Series Ledger）

> 约定：**每完成一轮任务，即给出下一轮改进提案**，轮次以 `R<数字>` 命名并累加。
> 每轮必须包含：主题 / 依据 / 条目（含验收句）/ 工作量 / 明确不做。
> 执行记录回填到本轮条目下方，并同步 `docs/CODE_STATE_AUDIT_20260906.md` 与
> `docs/NEXT_PRIORITIES_20260913.md`。

---

## 提交纪律（2026-09-14 起生效）

**每个关键功能完成后，自动提交并推送到 GitHub 远程**（`origin` =
`git@github.com:BHCLLBHCLL/pphdecoding.git`，分支 `main`）。执行方式固定为一条命令：

```
python tools/git_milestone.py --dry-run          # 先看会提交什么
python tools/git_milestone.py --round R3 -m "<一句话主题>"
```

* 收录集（白名单，见脚本 `INCLUDE` / `FORCE_GLOBS`）：根目录与
  `automation/` / `tools/` / `tests/` 下的 `*.py`、`*.md`、`schemas/*.json`，
  以及 `_p12*/` 证据目录下的 `*.json` / `*.jsonl` / `*.vbs` / `*.log`；
* **不入库**：`*.pph` / `*.mdl` / `*.oct` / `*.gph` / `*.x_t` / `*.stl` / `*.fph` /
  `*.sph` / `*.l` / `*.dmp` / `*.prp` / `*.xenv` / `*.js` / `*.sctsnapshot` 等
  二进制与大运行产物（单文件 > 1 MB 也一律跳过并告警）—— 仓库不承担产物体量；
* `.gitignore` 含 `tests/*`，新增测试模块**必须** `git add -f`，脚本已内置；
* 提交信息形如 `feat: R3 <主题>`，正文写明纳入文件数与产物排除纪律；
* 每轮收口时把该轮的「回归数字 + 证据路径」写进本轮执行记录，然后跑一次本命令。

---

---

## R0 —— 基线轮（2026-09-13，✅ 已完成）

| 条目 | 结果 |
|---|---|
| P0-1 修红 | 删除 6 份重复 `TestBackendConvergence`（380 行死代码）；陈旧字面量断言改契约断言 |
| P1-0/P1-3 CADthru 通道 | `scConverter` 证实非 CAD 转换器；改走 `CADthru_Bx64net.Application.2025`（免宿主免许可，STEP→x_t 9.5–18 s）；内容寻址缓存（命中 0.27 s）+ PPH 成员注入 → `tools/cadthru_convert.py` |
| P2 写端字节保真 | MDL/OCT/GPH 三写端对宿主原生产物**逐字节往返相同**；四条通用布局规律钉死；新增 `tests/test_writer_host_fidelity.py` |
| P2 宿主验收 | 三成员全本仓重写的工程被宿主正常打开（`sn_/mdl_/oct_=True`、`mesh_exists=True`、bbox [0,0.01]、31/31 err=0，两次独立运行） |
| 回归 | **1115 passed / 4 skipped / 0 failed**（622 s） |

---

## R1 —— CAD 双格式闭环 + 证据可信化（提案，≈6 人日）

### 依据

* 用户指定 **CAD 只做 x_t 与 STEP**，其余格式忽略；
* R0 已证：`CADthru` 可免宿主免许可做 STEP→x_t；pskernel 可免许可剖分 x_t；
  MDL/OCT/GPH 写端已达宿主字节保真 —— **闭环的只剩"端到端 gate + 量化对拍"**；
* 仍未做的两处基础设施：`E2E 证据入回归`（P0-2）与 `写端宿主回读 harness 产品化`（P0-3）；
* 审计发现 `cad_import.available()` 只查 pskernel 在位、不查许可/宿主 → GUI 会误报可用。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R1-1** | **x_t 离线↔宿主量化对拍** | 同一 `.x_t`：宿主 `OpenCadFile` 产出的 MDL vs 本仓 `ps_tessellate` / `decode_brep` 结果，逐项比 BODY/FACE/EDGE/VERTEX 计数、表面积、bbox、体素数 | 对拍表入册；差异 ≤ 容差或逐项给出归因（同内核，目标数值级一致） | 1.5 |
| **R1-2** | **STEP 离线化接线** | 把 `cadthru_convert.convert_cached` + `inject_into_pph` 接到 GUI 的 Import 流程（或一条 CLI 子命令）：导入 STEP → 落 `*_step.x_t` 成员 → 后续全部离线复用 | 单命令完成转换+落成员；**二次导入走缓存（≤0.5 s，不启动 CADthru）** | 1 |
| **R1-3** | **双格式端到端 gate** | `OpenCadFile → BAM(CreateMDL/VMDL) → CreateOctree → CreateMesh → SaveProject → 宿主重开`，x_t 与 STEP 各一条 | 两条 gate 全 err=0 + 产物宿主重开非空（`sn_/mdl_/oct_/mesh_exists`）；证据入 `_p12t/` | 1.5 |
| **R1-4** | **多体/装配/错误路径矩阵** | 多 body x_t、装配 STEP（AP203/214/242）、损坏文件、超版本文件、路径含空格与中文。注意 STEP 顶节点命名与 x_t 不同（`QuerySNodeByName("Part")` 实测 False）→ 走 SNode 树枚举 | 每格有明确业务判定（成功/业务拒/报错），**无静默零几何** | 1 |
| **R1-5** | **格式范围收敛（按用户指示）** | `docs/NYI_INVENTORY.md` 改为「产品决策：CAD 仅支持 x_t/STEP」；CATIA/3DXML/SolidEdge/JT/Rhino/VDAFS 移出 backlog；附本机许可实证（缺 5 种 `OP_*`；CATIA 已授权但转换核静默零几何） | 域 4 从"边界待裁决"变为"范围已定"；扫描脚本再生不丢账 | 0.5 |
| **R1-6** | **E2E 证据入回归** | 新增 `tests/test_e2e_artifacts.py`：解析根目录 `p12*_e2e.log`，断言 `has_end` + `err0==total` + 关键 alive 键（`sn2_/mg_/vmdl_`…） | 任一被截断/回归的日志立即变红；**永久堵死"截断日志当成功凭证"** | 0.5 |
| **R1-7** | **写端宿主回读 harness 产品化** | 把 `_p2_accept` 的做法做成 `tools/host_reopen_check.py`：写出 → 注入 → 宿主打开 → 探针 → JSON 证据；纳入 R1-6 的回归（无宿主时 skip） | MDL/OCT/GPH/PPH 四类各有 1 条 host round-trip 绿 | 1 |
| **R1-8** | **CAD 可用性判据拆分** | `cad_import.available()` → `offline_cad_available()`（pskernel 在位）与 `host_cad_available()`（宿主可达 + 许可）；GUI 据此分别灰显/提示 | 无宿主或无许可时 GUI 不再误报"CAD 可用" | 0.5 |

### 明确不做（R1 内）

* CATIA / 3DXML / SolidEdge / JT / Rhino / VDAFS 导入 —— 用户指示 + 本机缺 `OP_*` 许可；
* STEP 离线解析器 —— 与宿主 Datakit 结果不可能一致，改用 R1-2 的"转一次 x_t"；
* Parasolid/scFLOW 内核、求解器、scPOST 复刻 —— 策略豁免。

### 完成后自动给出

**R2**（预期方向，待 R1 收口后按实测重排）：条件体系 90→≥140 精确键 + BC 子编辑器去"3–5 标签壳"；
GUI 面板落盘化（Option Settings 20/23 页 + 快照回写）；真实流场算例的求解数值等价。

---

## R1 —— CAD 双格式闭环 + 证据可信化（2026-09-13，✅ 已完成；回归 **1129 passed / 4 skipped / 0 failed**，640 s）

> R1 净新增 14 个测试：`test_e2e_artifacts`(7) + `test_cad_availability`(4) +
> `test_cad_import_workflow`(3)。新增工具 4 个：`host_reopen_check.py` /
> `cad_compare.py` / `cad_pipeline_gate.py` / `cad_matrix_check.py`。
> **唯一未闭合项**：R1-3 的 `mesh_exists`（体积网格腿）→ 已列入 **R2-1**。

| # | 条目 | 结果 | 证据 / 关键发现 |
|---|---|---|---|
| **R1-1** | x_t 离线↔宿主量化对拍 | ✅（体数+bbox 级） | `tools/cad_compare.py`。**发现**：`OpenCadFile` 本身不产 `*_part.mdl`（需 BAM 步），故宿主侧改取 `main.sctsnapshot` 的 `CADthru/PKBody3` → **宿主存储 2 体 == 本仓离线 2 体**；bbox 取 `GetAllPartsBoundingBox`。离线侧 box.x_t 面积 **0.0006 = 6×0.01²**（解析值精确吻合）。面片级对拍待 R2-2 用 VMDL 产物补 |
| **R1-2** | STEP 离线化接线 | ✅ | `tools/cadthru_convert.py --import-cad`：冷 21 s（转换 18.6 s + 注入）/ **暖 0.244 s**（`cached:true` + `skipped:"member already present"`，不启动 CADthru）。测试 `tests/test_cad_import_workflow.py`（3 项，全离线：预置缓存命中） |
| **R1-3** | 双格式端到端 gate | ⚠️ **两腿主链绿，mesh 腿未闭合** | `tools/cad_pipeline_gate.py`：x_t build **48/48 err=0**（95 s）+ reopen **25/25**；STEP build **48/48**（125 s）+ reopen **25/25**；重开后 `vmdl_/oct_=True`（产物持久化）。**关键修正**：① `MG_.CreateVMDL` 实测抛 **Err 91**，改走 `Doc_.BuildAnalysisModel`（ret=True）；② octree 需先 `GetOctParam → Initialize → SetOctType/SetMeshNum/SetMinSize`；③ `CreateMeshMonitor` 返回 True 但 `mesh_exists=False`（遗留 R2-1） |
| **R1-4** | 多体/装配/错误路径矩阵 | 见下 | `tools/cad_matrix_check.py`；本机 STEP 样本 **全为 AP214**（无 AP203/AP242 可测，如实记录） |
| **R1-5** | 格式范围收敛 | ✅ | `tools/scan_nyi_menus.py` 的 `BOUNDARY_DECLARATIONS` 改为「CAD 仅 x_t/STEP（产品决策）」+ 许可实证；`docs/NYI_INVENTORY.md` 再生 |
| **R1-6** | E2E 证据入回归 | ✅ | `tests/test_e2e_artifacts.py`（7 项）：语料下限、未登记截断即红、截断登记准确性、非零 err 策略上限、关键 alive 探针、P2 验收日志、台账可解析 |
| **R1-7** | 写端回读 harness | ✅ **5/5** | `tools/host_reopen_check.py` pph/mdl/oct/gph/all 各 27/27 err=0、`mesh_exists=True`、bbox [0,0.01]；证据 `_p12u_reopen/r1_7_summary.json` |
| **R1-8** | CAD 可用性判据拆分 | ✅ | `cad_import.offline_available()` / `host_available()`（返回 dict + hint，无副作用）；GUI 两处接线；测试 `tests/test_cad_availability.py`（4 项） |

### R1-4 矩阵结果 —— **6/6 通过**

判据：期望落几何者必须有 `main.sctsnapshot` 成员；期望拒绝者必须**没有** snapshot 且无挂起、无静默零几何。

| 用例 | 期望 | 结果 | 探针 |
|---|---|---|---|
| `xt_multibody`（CADthru 转出的 2 体 x_t） | geometry | ✅ 落几何 | `sn_=True`、snapshot 在位 |
| `step_ap214`（key v2.step） | geometry | ✅ 落几何 | `sn_=True`、29/29 err=0 |
| `step_large`（top v5.step，1.39 MB） | geometry | ✅ 落几何 | `sn_=True`、29/29 err=0 |
| `step_unicode`（中文目录 + 空格路径） | geometry | ✅ 落几何 | `sn_=True`、29/29 err=0 |
| `step_corrupt`（截断 2 KB） | reject | ✅ **干净业务拒绝** | `sn_=False`、`parts_ub=-1`、**无 snapshot**、无挂起 |
| `step_garbage`（非 STEP 垃圾） | reject | ✅ 同上 | 同上 |

**两条实测发现**：

1. **ANSI VBS 通道无法承载非 ASCII 路径**——中文目录直接抛 `UnicodeEncodeError: mbcs`。
   改用 `_write_utf16_vbs` 后中文路径导入正常。已在 `tools/cad_matrix_check.py` 中按
   "路径含非 ASCII 即走 UTF-16" 固化为规则（GUI/驱动若有同类路径需同样处理）。
2. **本机 STEP 样本全为 AP214**（`AUTOMOTIVE_DESIGN { 1 0 10303 214 ... }`）；
   AP203 / AP242 无样本可测，如实记录（`r1_4_summary.json.note`）。

> 复跑命令：`python tools/cad_matrix_check.py`（全 6 例）或
> `--cases step_unicode,step_corrupt,step_garbage`（负例）。

---

## R2 —— CAD 端到端闭环补全 + 条件/面片深度（2026-09-14，执行记录）

| # | 条目 | 依据 | 验收句 | 人日 |
|---|---|---|---|---|
| **R2-1** | **闭合 mesh 腿** | R1-3 遗留：`CreateMeshMonitor` 返回 True 但 `mesh_exists=False` | STEP/x_t 两条 gate 的 `mesh_exists=True`（补 mesh 参数或延长 WaitForWorker） | 1 |
| **R2-2** | **面片级量化对拍** | R1-1 只到体数/bbox；R1-3 现已产 VMDL/MDL | 同一 CAD：宿主 VMDL 与本仓剖分的三角数/面积/拓扑对拍表入册 | 1 |
| **R2-3** | **条件体系补深** | 域 8：90/165 精确键（审计 §4） | 精确键 ≥140/165；写盘条件在宿主零破坏 | 3 |
| **R2-4** | **BC 子编辑器去壳** | flow BC 只写 3–5 标签 vs 宿主 592 字段路径 | 主要 BC 类型按 schema 全字段可编辑并落盘 | 2 |
| **R2-5** | **GUI 面板落盘化** | Option Settings 20/23 页 + 3 个面板仅写内存 session；快照从不回写 | 重启后设置保留；编辑后快照一致 | 3 |
| **R2-6** | **数值等价证据质量** | I5 delta 建立在零流场（审计 §5-O3） | 用 50 Pa 变体双跑出非零场 delta 表；FLD/iFLD 可得性明确 | 2 |
| **R2-7** | **写端布局规律入格式规范** | R0 钉死的四条规律（容器头/节头哨兵/描述符逐块交错/type=1） | `PPH_FORMAT_SPEC.md` 更新，后人不再重复踩坑 | 0.5 |

### 执行记录（2026-09-14）

#### R2-1 ✅ 已成 —— mesh 腿闭合（根因与 R1-3 的猜测不同）

**结论**：`CreateMesh` / `CreateMeshMonitor` 的返回值是**不可靠信号**；真正的缺口是
**流体区域登记**（`Doc_.CreateFluidRegion` + `FluidRegion.RegisterSPart`）。

三条否定配方（每条都日志 err=0 全绿，但网格不成立）：

| # | 配方 | 结果 | 证据 |
|---|---|---|---|
| 1 | 同会话 `BuildAnalysisModel` → typed `CreateMesh` | `ret_mesh=False`、`mesh_err=True` | `_p12u_gate/r2_1_probe.json`（84/84 err=0） |
| 2 | 拆段：存盘 → 重开工程 → `CreateMesh`（历史验证过的 `p12e_mesh_e2e.vbs` 配方） | 仍 `False` + mesh error | `_p12u_gate/r2_1_xt.json` |
| 3 | 补录制配方（`ChangeMesher` / `ChangeSurfMesher` / `SetMDLMethod 1` / `SetUseAFFacetter` / `Proj_.SetUseAFFacetter` + MDL wizard + 录制八叉树参数表 `SetParams`） | `CreateMeshMonitor=True`、`wait_ret=1`，但 `mesh_exists=False`、`mesh_err=True` | `_p12u_gate/r2_1_xt_wizard.json`、`r2_1_xt_recorded.json` |

**归因证据**：三条否定配方产出的 `meshinggroup1_error.mdl` 内容为 **17150 faces / 8577 verts**，
与绿色参照 `p12a_bam_e2e_out.pph` 的 `meshinggroup1_ridge.mdl`（同 17150 / 8577）**同规模**
—— 面/ridge 阶段是忠实的，缺的是 **gph**（网格本体）。录制 `box_scflow_mdl.vbs` :274-348 在
`SetModePart` 之后有 `CreateFluidRegion` + `RegisterSPart`（把 Part 挂进流体区域），最小配方
完全没有该步 → 八叉树参数表里 `NUMERICALREGION.N = 0` → **有八叉树、无网格**。

**修法**（`tools/cad_pipeline_gate.py`）：

* 新增 `_fluid_region_lines()` —— 录制 :274-348 的流体区域登记块；
* 新增 `_recorded_oct_param_lines()` —— 录制 :562-635 的 35 对八叉树参数表（`TARGETNUMBER=100000`、`BASESIZE.MIN=0.00021875`、`SECTITEM[0].NAME=@PartSurface_Part`、`SECTITEM[0].SIZE=0.001` …）；
* 配方顺序对齐录制：网格器 / MDL 方法 / AF facetter → 区域登记 → MDL wizard → 八叉树参数表 → `CreateOctree` → `CreateMeshMonitor`；
* mesh 段改走 **UTF-16 通道**（wizard 在 ANSI 通道静默失败，`GetMDLWizard` 恒 Nothing）；
* gate 拆成 build / mesh / reopen **三段会话**，新增 `--mesh-mode wizard|reopen`，并把 `DoesMeshErrorExist` 作为并行判据（不能只看返回值）。

**验收**（`_p12u_gate/r2_1_xt_fluidregion.json`）：mesh 段 **176/176 err=0**、`fluidregion_=True`、
`wiz_=True`、`ret_mesh=True`、`wait_ret=1`、**`mesh_exists=True`**、`mesh_err=False`；
reopen 段 **25/25 err=0**、**`mesh_exists_after_reopen=True`**（`r2_1_both.json` 里 x_t 腿同值，
即提交后的配方顺序复跑仍绿）。

STEP 腿：build **42/42 err=0**、reopen **25/25 err=0**（`sn_=False` —— STEP 顶节点命名与 x_t 不同，
R1-4 已记录），但 **mesh 段被基础设施超时中止**：`TimeoutExpired: Get-Process STpre_Bx64net …`
（宿主进程探测的 20 s 上限撞上正在跑的重网格计算）。这是探针健壮性问题、不是配方失败，
STEP 复核归 **R3-1**。


**回归保护**：`tests/test_cad_gate_actions_r21.py`（8 项不变量：build 段禁 `CreateMesh`、配方
顺序、UTF-16 通道、区域块指向 `Part`、参数表 35 对 / 70 槽形态、`_vbs_lit` 数字 vs 字符串）。

#### R2-2 ✅ 已成 —— 面片级量化对拍（机器精度等价）

`tools/cad_compare.py` 新增 `--facets`：面元画像（三角数 / 总面积 / 面积累积分布 / 六轴向
面积分解）+ `facet_compare`（相对量优先，对分面策略不敏感）。

同一 0.01 立方（`tests/box/box.x_t`）对拍宿主原生控制件 `_p2_accept/control_out.pph::meshinggroup1_part.mdl`：

| 量 | 本仓离线剖分 | 宿主 BAM 分面 | 差异 |
|---|---|---|---|
| 三角数 | 12 | 60 492 | 比值 5 041（分面密度，非几何） |
| 总面积 | 0.0006 | 0.0006 | **相对误差 0.0** |
| 六轴向面积 | 1e-4 ×6 | 1e-4 ×6 | **逐轴相对误差 0.0** |
| bbox | [0,0,0]–[0.01,0.01,0.01] | 同 | 一致 |
| 面积累积分布 | 均匀 12 片 | 均匀 60 492 片 | 最大偏差 0.0167 |

即：**几何量到机器精度一致**（总面积与轴向分解完全相同），差别只在分面密度 —— 宿主把每个
0.01 面剖成 71×71 网格（8e-5 宽，1e-8 面积/三角）。证据 `_p12u_cmp/r2_2_facets.json`。

附带修正：`mdl.triangulate_faces` 返回的是**顶点下标**而非坐标，`cad_compare` 旧路径把它当
坐标用（该分支此前从未被执行）→ 新增 `facet_profile_mesh()` 正确还原。

#### R2-4 ⚠️ 部分成 —— BC 子编辑器去壳（入口落地并过测，尚未铺开到全部页）

`nav_panels.py`：

* `GenericCondBody(..., initial=...)` 支持既有条件预填（name / regions / fields，标题切 `Edit Condition`）；
* `write_condition_to_xml(..., replace_el=...)` **原地重写**（不新增重复条件、清空旧字段）；
* 新增 `_find_condition_el` / `_flatten_cond` / `_condition_to_initial`；
* flow BC 详情页新增 **All fields (schema)…** 按钮 → `_open_schema_cond_editor()`：以 `schemas/*.json` 合并出的 schema 全字段表单编辑当前条件并原地落盘。

测试 `tests/test_cond_deshell_r24.py`（4 项：初始值往返 + 定位、原地重写语义、create 仍追加、
`GenericCondBody` 预填与 Edit 标题）。

未完成：wall / thermal / sym / periodic / source / initial 各 dedicated 页尚未接同一入口（helper 已
可复用）→ 推入 **R3-2**。

#### R2-7 ✅ 已成 —— 写端四条布局规律入 `PPH_FORMAT_SPEC.md` §2

容器头 / 40 B 节头 + 20 B 哨兵 / 数组描述符逐数据块交错 / `type=1` 描述符 + 区域记录
`desc(1,255,1)`，全部带实测出处。

#### R2-3 / R2-5 / R2-6 ❌ 本轮未执行（如实记账，推入 R3）

* **R2-3**：需多轮宿主批量收割（43 个未落键的 `CreateCond*`），且已知毒类型 `CreateCondBatteryARCDataPreprocessing` 会毒杀同脚本 `SaveProject`、旧版工程触发三层版本转换确认链 —— 属「实机批跑 + 已知毒点隔离」的活，3 人日估不足；
* **R2-5**：Option Settings 20/23 页 + 3 个面板落盘化 = GUI 多页持久化 + 快照回写，3 人日估不足；
* **R2-6**：需要跑求解器（50 Pa 变体双跑）才有非零场 delta，超出本轮离线 / 宿主自动化范围。

#### 回归

全量回归 **1141 passed / 4 skipped / 0 failed**（660.66 s；R1 末为 1129 —— 本轮净增 12 项：
`tests/test_cond_deshell_r24.py` 4 项 + `tests/test_cad_gate_actions_r21.py` 8 项）。

### 明确不做（R2 内）


* CATIA 等其余 CAD 格式（R1-5 已定范围）；
* 内核/求解器/scPOST 复刻（策略豁免）。

---

## R3 —— 端到端健壮化 + BC 去壳铺开（2026-09-14，执行记录）

### 依据

* R2-1 把「CAD → 面片 → 八叉树 → **网格** → 存盘 → 宿主重开」全链打通，且证明
  `CreateMesh*` 返回值不可信、必须以 `DoesMeshExist` / `DoesMeshErrorExist` 判定 —— 该判据
  需要固化进所有后续实机 gate；
* R2-2 给出面元级机器精度等价，缺陷面已从「几何是否一致」转为「分面密度是否可控」；
* R2-4 只铺了 flow BC 一个入口，去壳的边际收益最大且成本最低的是**把它铺到全部 BC 页**；
* R2-3 / R2-5 / R2-6 三项在本轮已做完整侦察与可行性判定（毒类型、版本转换链、求解器依赖），
  推入本轮按切片执行。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R3-1** | **STEP 腿网格闭合** | 用 R2-1 配方复跑 STEP 腿（`--cases step`），确认 wizard + 区域登记对 STEP 顶节点命名同样成立 | `_p12u_gate/` 两腿均 `mesh_exists=True`（含 reopen），全 err=0 | 0.5 |
| **R3-2** | **BC 去壳铺开** | 把 `_open_schema_cond_editor` 接到 wall / thermal / sym / periodic / source / initial 各 dedicated 页；每页一个入口按钮 + 一项回归 | 6 个页签均可展开全字段并原地落盘；`tests/test_cond_deshell_r24.py` ≥10 项 | 1.5 |
| **R3-3** | **条件体系补深（原 R2-3）** | 宿主批量收割 43 个未落键 `CreateCond*`：毒类型 `CreateCondBatteryARCDataPreprocessing` 单进程隔离、旧版工程先做版本转换前置、每批 `Create→SaveProject→深扫` 三件套 | 精确键 90 → **≥140 / 165**；写盘条件宿主零破坏 | 3 |
| **R3-4** | **面板落盘切片（原 R2-5）** | 先做 `main.sctsnapshot` 回写通道 + **1 个**面板端到端（选 Part Material：改→存→重启→保留），再评估其余 19 页 | 1 个面板设置经重启保留；快照写回不破坏宿主打开 | 2 |
| **R3-5** | **数值等价（原 R2-6）** | 50 Pa 变体双跑（宿主 vs 本仓产物）出非零场 delta 表；明确 FLD / iFLD 可得性 | delta 表入册且**非零场**；FLD/iFLD 结论明确 | 2 |

### 执行记录（2026-09-14）

#### R3-1 ⚠️ 部分成 —— x_t 腿闭合复现；STEP 腿定位到**宿主在网格计算中崩溃**

修掉了两个把失败伪装成别的问题的基础设施缺陷：

| # | 缺陷 | 证据 | 修法 |
|---|---|---|---|
| 1 | 进程探针走 `powershell Get-Process` 且 20 s 上限；忙时 `TimeoutExpired` 直接崩 flow，探针无输出还会被判成“宿主消失” | `r13_step_mesh.log` 的 `TimeoutExpired`；`hang_characterization.jsonl` 17:58 前的 step_mesh 行 | `automation/modal_watch.py` 新增 `host_pids_toolhelp()` / `pid_alive()`（Toolhelp32 + OpenProcess，纯 ctypes、毫秒级、无子进程）；`host_watchdog` 新增 `_hosts_safe()`：探针异常/超时折成 `None`（**未知**），`_monitor` 对未知**绝不**判“宿主消失” |
| 2 | `json.dumps(..., ensure_ascii=False)` 打印到 ANSI 代码页的 stdout → `UnicodeEncodeError`，把真实原因（宿主崩溃）掩盖成编码错误 | step_mesh 的 `error: UnicodeEncodeError: 'charmap' ...` | `tools/_p12e_e2e_run.py` 新增 `utf8_stdout()`（stdout/stderr 切 UTF-8 + replace），gate 启动即调用 |

另按段放宽自愈惰性阈值（网格段 1500 s / 重开段 900 s）：网格与重开都在**同一条 VBS 行内**长时间不写日志，实测 x_t mesh 170 s、STEP reopen 20–360 s，默认 420 s 阈值会把正常计算判成 hung。

**验收**（`_p12u_gate/r3_1_both.json`）：

* **x_t 腿 ✅ 全绿**：build 42/42、mesh **176/176**（170.5 s）、reopen 25/25；`fluidregion_/wiz_=True`、`ret_mesh=True`、`wait_ret=1`、**`mesh_exists=True`（同会话 + 重开后）**、`mesh_err=False`、bbox [0,0.01]。
* **STEP 腿 ❌ 未闭合，但归因明确**：build 42/42、reopen 25/25 绿；mesh 段三次尝试全部以 **`host process gone while worker blocked (idle 90.1s)` 且 `host_pids: []`** 结束 —— 即**宿主进程在 STEP 网格计算中真的退出了**（不是探针超时、不是惰性误判）。这是本轮新钉死的事实：`key v2.step`（风扇，bbox ≈82 mm）在录制八叉树参数（`TARGETNUMBER=100000`、`BASESIZE.MIN=0.00021875`）下把宿主算崩。

回归保护：`tests/test_host_probe_r31.py`（8 项：Toolhelp 自进程/未知映像、探针优先级与回退、`_hosts_safe` 吞异常、**探针未知时不得判宿主消失**的 `_monitor` 行为断言）＋ `tests/test_cad_gate_actions_r21.py` 新增 idle_limit / UTF-8 断言。

#### R3-2 ✅ 已成 —— BC 去壳铺开（一次覆盖全部页，而非逐页加按钮）

把 R2-4 的“单页按钮”泛化成**每页条件列表的右键入口**：

* 新增模块级 `_find_condition_el_any(xml, name)` —— 按条件名（不限类型）定位，绕开逐页的 `type` 映射表；
* 新增 `_deshell_condition_el(el)`（任意类型：取 `type` → schema → 预填表单 → 原地重写）与 `_schema_type()` / `_refill_condition_lists()`；
* 新增 `_install_deshell_menus()`：遍历 `self._pages`，给每个带 `_cond_list` 的页挂 `CustomContextMenu`（`id()` 记账保证幂等），在 `_fill_condition_lists()` 首次调用时安装 —— flow / wall / thermal / sym / periodic / source / fixed / 其余条件页**一次全覆盖**；树形页的区域节点因查不到同名条件而自动不弹菜单；
* `_open_schema_cond_editor()` 改为「有元素 → 原地编辑；无元素 → 全字段新建」，R2-4 行为保留。

测试 `tests/test_cond_deshell_r32.py`（4 项：按名定位/缺陷入参、挂载幂等且覆盖多页、非条件节点不弹菜单、入口委派契约）；连同 R2-4 的 4 项共 **8 项**，条件域全量 **92 passed**。

#### R3-3 / R3-4 / R3-5 ❌ 本轮未执行（已把 R3-4 的关键未知量消掉）

* **R3-3**（条件补深 90 → ≥140）：需多轮宿主批量收割 + 毒类型隔离，未动；
* **R3-4**（面板落盘切片）：**侦察结论** —— `main.sctsnapshot` 的回写通道**已经存在且逐字节保真**：`sctsnapshot.SctSnapshot.serialize()` + `SnapRecord.serialize()` 有 `tests/test_snapshot_reserialize.py` 证明 `snap.serialize(raw) == raw`。真正缺口是 **GUI 侧从无调用**（`pph_gui.py` 只 `SctSnapshot.load` 用于展示）→ R4-3 先做「面板状态住哪个存储（xml / xenv / prp / sctsnapshot）」的逐面板审计，再接回写，避免盲写；
* **R3-5**（数值等价）：需要求解器双跑，未动。

#### 回归

全量回归 **1155 passed / 4 skipped / 0 failed**（605.24 s；R2 末为 1141 —— 本轮净增 14 项：
`tests/test_host_probe_r31.py` 8 项 + `tests/test_cond_deshell_r32.py` 4 项 + gate 不变量 +2）。
### 明确不做（R3 内）

* CATIA / 3DXML / SolidEdge / JT / Rhino / VDAFS（R1-5 已定范围：CAD 仅 x_t / STEP）；
* 内核 / 求解器 / scPOST 复刻（策略豁免）；
* R3-4 只做 1 个面板切片，不摊薄成 20 页的机械劳动。

---

---

## R4 —— 提案（2026-09-14，≈7 人日）

### 依据

* R3-1：x_t 全链稳定；STEP 网格把**宿主算崩**（`host_pids: []`）→ 录制网格参数不能直接搬到不同尺度的模型上；
* R3-1 的两个基础设施缺陷（进程探针 / stdout 编码）说明「自愈层自身的失败会掩盖真实原因」→ 需要把「宿主消失」单列事件台账；
* R3-2：去壳入口已一次覆盖全部条件页，下一步价值不在「能编辑」而在「写盘不破坏宿主」；
* R3-4 侦察：`SctSnapshot.serialize` 写通道已就绪且逐字节保真（`tests/test_snapshot_reserialize.py`），缺口是 GUI 从未调用 + 不知道各面板状态住在哪个存储。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R4-1** | **STEP 网格参数标定** | 以 bbox 自适应缩放 `TARGETNUMBER` / `BASESIZE.MIN` 跑 3–4 档阶梯，定位宿主崩溃阈值 | 找到一组让 `key v2.step` 网格成功且 `mesh_exists=True`（含 reopen）的参数；崩溃档位如实入册 | 2 |
| **R4-2** | **宿主消失事件台账** | `_monitor` 判定 host gone 时写独立行：退出码、崩溃 dump、该 attempt 的 VBS 最后一行 | 每条 host-gone 可单独归因，不再与 log-idle 挂起混记 | 0.5 |
| **R4-3** | **面板状态存储审计** | 逐面板（Option Settings 20/23 页 + Part Material / Mesh Param / Non-Solid）标注状态住 `xml` / `xenv` / `prp` / `sctsnapshot` | 映射表入册，成为落盘化的唯一依据 | 1 |
| **R4-4** | **面板落盘切片** | 按 R4-3 映射选 **1 个**纯 xml 面板做端到端（改 → 存 → 重启 → 保留 → 宿主可开） | 1 个面板设置经重启保留且宿主零破坏 | 2 |
| **R4-5** | **条件写盘零破坏回归** | 用 R3-2 的通用入口批量改条件后宿主重开 | ≥20 条条件经去壳编辑后宿主 `err=0` 且条件可读 | 1.5 |

### 明确不做（R4 内）

* CATIA / 3DXML / SolidEdge / JT / Rhino / VDAFS；
* 内核 / 求解器 / scPOST 复刻；
* 条件体系补深（原 R3-3）与数值等价（原 R3-5）继续延后，不摊入本轮。

---

## R 轮次模板（后续轮次照此填写）

```
## R<n> —— <主题>（提案/执行中/已完成，日期，≈工作量）

### 依据
- 上一轮遗留 / 新实测发现 / 口径变化

### 条目
| # | 条目 | 做法 | 验收句 | 人日 |

### 明确不做

### 执行记录（收口时回填）
```
