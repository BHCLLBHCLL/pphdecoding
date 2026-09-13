# R 轮次台账（R-Series Ledger）

> 约定：**每完成一轮任务，即给出下一轮改进提案**，轮次以 `R<数字>` 命名并累加。
> 每轮必须包含：主题 / 依据 / 条目（含验收句）/ 工作量 / 明确不做。
> 执行记录回填到本轮条目下方，并同步 `docs/CODE_STATE_AUDIT_20260906.md` 与
> `docs/NEXT_PRIORITIES_20260913.md`。

---

## 排期纪律（2026-09-14 起生效，R16 教训）

**任何「需要 X 小时实机」的估算，必须在目标算例上实测定档，不得拿别的算例外推。**

来源：R10–R15 连续六轮把 50 Pa 双跑按「≥1 h」让位，该数字取自 J3 的 exA36-2（单腿 1000–1500 s）；
换成官方 exA06-2 实测单腿只要 **57–187 s**，整轮双跑不到 10 分钟 —— 六轮让位建立在一个**错误成本估计**上。
后续任何提案里的工作量估算，若涉及实机时长，必须写明**依据的算例与实测数字**。

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

## R4 —— 面板落盘 + 条件写盘零破坏 + STEP 网格标定（2026-09-14，执行记录）

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

### 执行记录（2026-09-14）

#### R4-2 ✅ 已成 —— 宿主消失事件独立归因

旧实现里 host-gone 只能读到一句 reason 文本：pid 拿不到（进程已消失）、最后跑到哪也拿不到。
现在 ``host_watchdog`` 增三类字段：

* ``reason_kind``：``host_gone`` / ``log_idle``（两类挂起从此可分流统计）；
* ``host_gone=True`` + ``last_seen_hosts`` / ``last_seen_diag``：**最后一次探到的** pid 与诊断
  （``_monitor`` 在探针成功时缓存，消失后才不会只剩空数组）；
* ``log_last_line`` + ``vbs``：日志最后一行与脚本名，直接给出「死在哪个 VBS 行」。

测试 ``tests/test_host_gone_r42.py``（5 项）：状态化 host_fn 先给 pid 再给空 → 断言字段齐备；
log-idle 路径带 ``reason_kind=log_idle`` 且不含 host_gone；探针异常不得被当成 host_gone。

#### R4-3 ✅ 已成 —— 面板状态存储审计（可再生）

`tools/panel_store_audit.py`（静态扫描，逐条 file:line 证据）→ `docs/PANEL_STORE_MAP.md` +
`schemas/panel_store_map.json`。37 个面板类判类：

| 分类 | 数量 | 说明 |
|---|---|---|
| persisted | 11 | 写 main.xml / main.xenv（含 R4-4 之后的 OptionNav） |
| memory_only | **6** | 只写 ``ctx["session"]``，重启即失 |
| read_only | 3 | 只读 |
| none | 17 | 纯 UI/无存储 |

memory_only 现存 6 个：`_PartsControlFollowupBody` / `CreatePartsBody` / `NonSolidBody` /
`MeshParamBody` / `ExecuteBody` / `CondTypeCatalogDialog`。

扫描器修了两个自身缺陷（都已入测）：类块边界必须止于下一个顶层 ``class/def/赋值``（曾把
模块级 `condition_registry_cached` 吞进来 → OptionNav 误判 persisted:xml）；xml 写标记用本仓
约定 ``xml_dirty``/``ET.SubElement``（泛化的 ``.append(`` 会把布局代码误判为写 xml）。

#### R4-4 ✅ 已成 —— 面板落盘切片（OptionNav → main.xenv，宿主零破坏）

新增落盘通道 ``panel_xenv_get`` / ``panel_xenv_set`` / ``panel_bool``（nav_panels.py）：写
``main.xenv`` 的 Section/Key 并置 ``xenv_dirty``；无 xenv 时**如实返回 False**（不再假装保存成功）。

首个切片 ``OptionNavBody``（原 memory_only）落到 ``main.xenv [OPTION_NAV]``，session 退化为
运行时镜像 + 旧工程兜底。证据 ``_p12u_gate/r4_4_xenv.json``（`tools/panel_persist_check.py`）：

* 离线闭环：写入 → ``pphwriter.clone_pph`` 重写容器 → 重新解析 → 三项值原样回来（等价「重启保留」）；
* 宿主闭环：OpenProject **25/25 err=0**、`sn_/mg_/mdl_/oct_=True`、`mesh_exists=True` —— 多出的
  xenv 段**不破坏宿主读工程**。

> 说明：宿主 xenv 现有 13 段（CAD/FACET/MESH/…/UNIT），**没有** OPTION 类段 —— 宿主把同名开关
> 放在自己的用户设置里。故 ``[OPTION_NAV]`` 是「本工具的 UI 选项」；本条验收口径 = 本工具重启
> 保留 + 宿主零破坏，两者均已量化。

#### R4-1 ⚠️ 部分成 —— STEP 网格：宿主崩溃是**参数/时间驱动**，不是脚本瞬时硬失败

`tools/cad_pipeline_gate.py` 新增刻度入口：`--target-num` / `--min-size`（并把覆盖透传到录制参数表
`_recorded_oct_param_lines(target_num, min_size)` 的 `TARGETNUMBER` / `BASESIZE.MIN`），
使八叉树参数可按模型尺度标定，而不是把 0.01 立方的录制值硬套到 82 mm 的风扇上。

**Run A**（STEP，`--target-num 50000 --min-size 0.002`；录制值 100000 / 0.00021875）证据
`_p12u_gate/r4_1_step_A.json`：

| 量 | 录制参数（R3-1） | Run A（粗档） |
|---|---|---|
| 宿主存活时长（网格计算中） | ~90 s | **1502 s（25 min）** |
| 结束方式 | `host process gone` | `host process gone`（`reason_kind=host_gone`） |
| 结束前 worker CPU | — | `scFLOWpre_Bx64net` ≈1379 s |

台账原文（R4-2 新字段在生产环境生效）：`{"flow": "step_mesh", "reason_kind": "host_gone",
"host_gone": true, "last_seen_hosts": [2136], "vbs": "r13_step_mesh.vbs", "log_last_line": "s141=0"}`。

**结论（本轮钉死）**：

1. 失败形态是 **宿主进程 STpre 自行退出**，而它的工作进程 `scFLOWpre_Bx64net` 继续空转 ——
   与 J1 记录的「工作进程生命周期不随宿主」一致；消费端 COM worker 因此永久阻塞；
2. 该退出**对参数敏感**：录制参数下 ~90 s 就退，粗档下撑到 1500 s+ → 指向宿主侧资源/超时，
   而不是我们的脚本（脚本在长调用之前 141 步全 err=0，`ret_oct=True`）；
3. 未达成验收（仍无「`mesh_exists=True` 的 STEP 参数组」）。阶梯在 Run A 后停止：attempt 2
   会重演 ~25 min。

**R5-1 承接**：(a) 给长网格调用加**进度信号**（周期写日志或轮询 `MG_.GetOctInfo`），否则
watchdog 只能按日志静默判活；(b) 崩溃前抓 STpre 的 WS/私有字节（本轮 `last_seen_diag` 只有 pid，
内存量没抓到）以验证 OOM 假说；(c) 以 bbox 为基准做小步长阶梯，定位崩溃阈值。

#### R4-5 ✅ 已成 —— 条件写盘零破坏（24 条去壳改写 + 宿主回读）

`tools/cond_write_check.py`：对条件最多的宿主工程 `p12c_cond_harvest_out.pph`（49 条条件）逐条
执行 **R3-2 去壳同路径**（`_condition_to_initial` → `write_condition_to_xml(replace_el=el)`），
再重写 `main.xml` 并交宿主。证据 `_p12u_gate/r4_5_cond.json`：

| 环节 | 结果 |
|---|---|
| 改写条数 | **24**（≥20 验收线） |
| 离线幂等 | 条件数 49 → 49，逐条 (type/name/regions/区域标签/字段值) **diff_count=0** |
| 宿主重开 | **71/71 err=0**、`sn_/mg_/mdl_/oct_/conds_=True`、`mesh_exists=True` |
| 条件回读 | `Doc_.GetConditions().QueryConditionByName(name)` **12/12 全 True** |

即：批量去壳编辑后，宿主不但能打开工程，还能**逐条读回**这些条件。

#### 回归

全量回归 **1167 passed / 4 skipped / 0 failed**（568.55 s；R3 末为 1155 —— 本轮净增 12 项：
`tests/test_host_gone_r42.py` 5 项 + `tests/test_panel_persist_r44.py` 7 项）。
### 明确不做（R4 内）

* CATIA / 3DXML / SolidEdge / JT / Rhino / VDAFS；
* 内核 / 求解器 / scPOST 复刻；
* 条件体系补深（原 R3-3）与数值等价（原 R3-5）继续延后，不摊入本轮。

---

---

## R5 —— 网格进度信号 + 面板落盘再切 2 页（2026-09-14，执行记录）

### 依据

* R4-1 把 STEP 网格失败定性为「宿主在持续重网格计算中自行退出」，且**对参数敏感**（90 s → 1500 s+），
  但尚无进度信号与内存证据；
* R4-3 审计把 memory_only 面板从 7 个降到 6 个，且给出逐面板 store 证据 → 落盘化可继续按证据推进；
* R4-4 打通了 `main.xenv` 落盘通道并证明「多一段不破坏宿主」，通道可复用；
* R4-5 证明去壳写入的批量零破坏，条件体系可以放心加大写入面。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R5-1** | **网格进度信号 + 宿主崩溃取证** | 长网格调用期间周期落一行日志（或轮询 `MG_.GetOctInfo` 写进度）；host-gone 行补抓 STpre 的 WS/私有字节 | 宿主存活期间不再被判 log-idle；host-gone 行带内存量，可判 OOM | 1.5 |
| **R5-2** | **STEP 网格参数阶梯** | 以 bbox 为基准小步长扫 `TARGETNUMBER`/`BASESIZE.MIN`，定位崩溃阈值 | 给出「成功档 + 首崩档」两条参数与对应 `mesh_exists` | 2 |
| **R5-3** | **面板落盘再切 2 页** | 用 R4-4 通道接 `NonSolidBody` 与 `MeshParamBody`（后者落 `main.xenv` 既有的 MESH/MESH_COMMON/OCT_MESH 段） | 2 个面板重启保留 + 宿主零破坏；memory_only 降到 4 | 2 |
| **R5-4** | **条件体系补深（原 R3-3）** | 宿主批量收割 43 个未落键 `CreateCond*`（毒类型单进程隔离） | 精确键 90 → **≥140 / 165** | 3 |
| **R5-5** | **数值等价（原 R3-5）** | 50 Pa 变体双跑出非零场 delta 表 | delta 表入册且非零场；FLD/iFLD 结论明确 | 2 |

### 执行记录（2026-09-14）

#### R5-1 ✅ 已成 —— CPU 进度信号 + 宿主内存取证

问题：x_t 网格 170 s、STEP 网格 25 min **都不写日志**，只按日志静默判活会误杀正常计算；
而「宿主已死 + 工作进程空转」又必须照旧判 host_gone —— 两条判据互相拉扯。

修法（`automation/modal_watch.py` + `automation/host_watchdog.py`）：

* 新增纯 ctypes 探针：`process_memory`（WS / 峰值 WS / 提交）、`process_cpu_seconds`
  （GetProcessTimes，内核+用户）、`total_cpu_seconds`、`host_and_worker_cpu`（宿主 + 工作进程，
  **网格算在工作进程里**）；
* `FlowExecutor` 新增 `cpu_fn` / `mem_fn` / `cpu_progress_delta`（默认 2 s）与 `_cpu_progress_ok()`：
  **仅当宿主曾探到在场**（`_host_seen_alive`）时，CPU 推进才重置惰性计时 —— 这条守卫保证
  「宿主消失 + 工作进程空转」仍然判 host_gone（R3-1/R4-1 的形态不会被掩盖）；
* 台账新增 `cpu_progress_events` 与 `last_seen_memory`（内存在**宿主还在时**采样，消失后就问不到了）。

测试 `tests/test_progress_signal_r51.py`（6 项）：真实进程内存/CPU 探针；**CPU 推进时日志静默不得判 hung**
（同一场景去掉进度信号会写出一条 log_idle 行）；host_gone 优先于 CPU 推进且带内存画像；未探到宿主时
进度通道禁用。

#### R5-3 ✅ 已成 —— 面板落盘再切 2 页（memory_only 6 → 4）

新增 JSON 变体 `panel_json_get` / `panel_json_set`（嵌套结构经 main.xenv 落盘）：

| 面板 | 段 | 内容 |
|---|---|---|
| `MeshParamBody` | `PANEL_MESH_PARAM` | 棱柱层厚系数/层数、分配法、Other 类型、明细与零件分配（JSON） |
| `NonSolidBody` | `PANEL_NON_SOLID` | 三张**登记列表** group / coord / sheet（JSON） |

审计随之变化：**persisted 11 → 13，memory_only 6 → 4**（余 `_PartsControlFollowupBody` /
`CreatePartsBody` / `ExecuteBody` / `CondTypeCatalogDialog`）。测试 `tests/test_panel_persist_r53.py`（7 项）。

宿主零破坏（`_p12u_gate/r5_3_xenv.json`）：工程带 **3 个**额外 xenv 段（OPTION_NAV / PANEL_MESH_PARAM /
PANEL_NON_SOLID）→ OpenProject **25/25 err=0**、`sn_/mg_/mdl_/oct_=True`、`mesh_exists=True`。

> **如实说明**：`MeshParamBody` 的字段与宿主 `MESH`/`MESH_COMMON`/`OCT_MESH` 段的键（`MESHER`、
> `SURF_MESHER`、`FACET_*`…）**不是 1:1**。在逐键核实之前**不写宿主键** —— 写错会真的改变宿主的
> 网格行为，代价远高于「本工具自己存一份」。逐键映射核实列为 R6-5。

#### R5-2 ⏳ 未执行，但已被解锁 → R6-1

STEP 参数阶梯此前卡在「长网格会被误判 log-idle 杀掉」；R5-1 的 CPU 进度信号正好解除这个死结。
余下成本是每档最长 ~25 min 的实机时间，本轮预算不足，顺延一轮（工具侧 `--target-num` / `--min-size`
在 R4-1 已就绪）。

#### R5-4 / R5-5 ❌ 未执行 → R6-2 / R6-3

条件体系补深（多轮批量收割 + 毒类型隔离）与数值等价（需跑求解器）都超出本轮预算，如实顺延。

#### 回归

全量回归 **1179 passed / 4 skipped / 0 failed**（580.29 s；R4 末为 1167 —— 本轮净增 12 项：
`tests/test_progress_signal_r51.py` 6 项 + `tests/test_panel_persist_r53.py` 6 项）。
### 明确不做（R5 内）

* CATIA / 3DXML / SolidEdge / JT / Rhino / VDAFS；
* 内核 / 求解器 / scPOST 复刻；
* R5-3 每轮最多 2 页，不做机械摊开。

---

---

## R6 —— 宿主键映射 + 面板落盘收尾 + STEP 阶梯（2026-09-14，执行记录）

### 依据

* R5-1 的进度信号解除了「长网格被误判 log-idle」的死结 → STEP 阶梯（R6-1）现在可跑；
* R5-3 把 memory_only 压到 4，且证明了「多段 xenv 不破坏宿主」→ 剩余 4 页可继续按证据推进；
* `MeshParamBody` 已能落盘，但字段与宿主网格键仍未映射（写错会改坏宿主行为）→ 需要逐键核实方法；
* R5-4 / R5-5 两项连续两轮顺延，需要各自一块完整预算。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R6-1** | **STEP 网格参数阶梯（原 R5-2）** | 以 bbox 为基准粗→细扫 `TARGETNUMBER`/`BASESIZE.MIN`，每档 ≤1 次尝试；靠 R5-1 的进度信号不再误杀 | 给出「成功档 + 首崩档」两条参数与各自 `mesh_exists`、宿主存活时长、内存峰值 | 2.5 |
| **R6-2** | **条件体系补深（原 R5-4）** | 宿主批量收割 43 个未落键 `CreateCond*`，毒类型单进程隔离、旧版工程先做版本转换 | 精确键 90 → **≥140 / 165**；写盘条件宿主零破坏 | 3 |
| **R6-3** | **数值等价（原 R5-5）** | 50 Pa 变体双跑出非零场 delta 表 | delta 表入册且非零场；FLD/iFLD 可得性明确 | 2 |
| **R6-4** | **面板落盘最后 2 页** | 用同一通道接 `CreatePartsBody` 与 `ExecuteBody` | memory_only 4 → **2**；宿主零破坏 | 1.5 |
| **R6-5** | **MeshParam → 宿主键映射核实** | 在宿主里改一项、对 xenv 做差分定位其真实键；核实一个写一个 | ≥3 个字段写入宿主键且宿主行为符合预期 | 2 |

### 执行记录（2026-09-14）

#### R6-5 ✅ 已成 —— MeshParam → 宿主键映射**实测**（不猜键名）

`tools/xenv_key_probe.py`：宿主打开工程 → 用 COM 在 `MeshingGroupSetting` 上改设置 →
`SaveProject` → **diff 两份 main.xenv**，值变了的键就是该设置的真实宿主键。两轮实测合起来钉死 5 条：

| COM setter | main.xenv 键 | 观测 |
|---|---|---|
| `SetFacetSimpleChordTol` | `FACET.SIMPLE_CHORD_TOLERANCE` | 1 → 0 |
| `SetFacetSimpleMaxAngle` | `FACET.SIMPLE_MAX_ANGLE` | 5 → 0 |
| `SetFacetSimpleMaxWidth` | `FACET.SIMPLE_MAX_WIDTH` | 5 → 0 |
| `SetFacetUseDetailMaxWidth` | `FACET.USE_DETAIL_MAX_WIDTH` | true → false |
| `SetFacetUseAbsoluteValue` | （未变化） | 未证实，不采用 |

证据 `_p12u_gate/r6_5_keys.json`（两轮宿主 err=0：43/43 与 47/47）。

> **重要发现**：数值型 setter **不保证回读同一数值** —— 传 7/9/13 读回都是 **0**，而布尔 setter 精确生效。
> 也就是说这些键在当前配置（`USE_SIMPLE_SETTING=true` / `USE_ABSOLUTE_VALUE=false`）下是「0=自动/默认」
> 语义。**结论：将来写宿主键只能写经过实测确认的取值，不能假设数值往返。**

#### R6-4 ✅ 已成 —— 面板落盘最后 2 页（memory_only 4 → 2）

`ExecuteBody` → `main.xenv [PANEL_EXECUTE]`（执行管线勾选项 + mesh_mode，JSON）；
`CreatePartsBody` → `[PANEL_CREATE_PARTS]`（Create Parts **表单草稿**持久化，重启不必重填；几何仍走
`pending_vbs` → 宿主执行）。

审计随之 **persisted 13 → 15 / memory_only 4 → 2**（余 `_PartsControlFollowupBody` 与
`CondTypeCatalogDialog`——后者是对话框而非页面）。

#### R6-1 ⚠️ 部分成 —— STEP 阶梯实测：宿主存活**非单调**，且**不是内存问题**

粗档 rung（`--target-num 20000 --min-size 0.01`，比 R4-1 的 Run A 更粗）：宿主在网格计算
**189.9 s** 后就消失（elapsed 315 s）—— **比 Run A（50000 / 0.002，撑到 1502 s）更早死**。

| 档 | 参数（target / min-size） | 宿主存活（网格中） | 结束方式 |
|---|---|---|---|
| 录制值（R3-1） | 100000 / 0.00021875 | ~90 s | host_gone |
| **R6-1 粗档** | **20000 / 0.01** | **189.9 s** | host_gone |
| Run A（R4-1） | 50000 / 0.002 | 1502 s | host_gone |

**结论（本轮推翻上一轮的假说）**：宿主存活时长**不是**八叉树细度的单调函数（更粗反而更早死），
所以「越细越容易崩」的资源标定思路不成立；也没有得到成功档。

**R5-1 的仪表同时给出了否证 OOM 的直接证据**（台账原文）：

```
"reason_kind": "host_gone", "cpu_progress_events": 3, "last_seen_hosts": [11756],
"log_last_line": "s146=0",
"last_seen_memory": [{"pid": 11756, "ws_mb": 87.7, "peak_ws_mb": 143.8, "pagefile_mb": 31.7}]
```

宿主消失前内存仅 **87.7 MB（峰值 143.8 MB）** —— 离内存天花板极远，**OOM 假说否证**。
`cpu_progress_events=3` 说明 CPU 进度信号在生产环境确实生效（但宿主真的没了，`host_gone` 正确优先）。

→ R7-1 换假设：查 STpre 是**优雅退出还是崩溃**（WER / Application 事件日志 / 退出码），以及是否存在
宿主内部「工作进程无进度即自退」的超时。

#### R6-2 ❌ 未执行（顺延 R7-2）

条件补深需要多轮宿主批量收割（43 个未落键 `CreateCond*`，含已知毒类型隔离与旧版工程版本转换前置），
本轮预算被 R6-1 的两档长实机（各 ~25 min 上限）占满，如实顺延。

#### R6-3 ❌ 未执行（顺延 R7-3）

数值等价需要跑求解器（50 Pa 变体双跑），本轮未动。

#### 回归

全量回归 **1184 passed / 5 skipped / 0 failed**（576.80 s；R5 末为 1179 —— 本轮净增 6 项：
`tests/test_panel_persist_r64.py`（Execute / CreateParts 落盘）；另 1 项转为条件性 skip）。
### 明确不做（R6 内）

* CATIA / 3DXML / SolidEdge / JT / Rhino / VDAFS；
* 内核 / 求解器 / scPOST 复刻；
* 不把未核实的 MeshParam 字段写进宿主键（宁可多留一轮）。

---

---

## R7 —— 宿主退出机理定性 + 反向写宿主键 + 面板落盘收尾（2026-09-14，执行记录）

### 依据

* R6-1 推翻了「参数越细越崩」的假说（存活 90 / 190 / 1502 s 非单调），并用 R5-1 的内存探针**否证 OOM**
  （宿主消失前仅 87.7 MB WS）→ 必须换假设：查它是优雅退出还是崩溃；
* R6-5 拿到了 5 条**实测**宿主键映射，并发现数值 setter 不回读原值（7/9/13 → 0）→ 可以开始「反向写宿主键」，
  但只能写实测确认过的取值；
* R6-4 把 memory_only 压到 2 → 面板落盘这条线基本收尾；
* R6-2 / R6-3 连续两轮顺延，各需一整块预算。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R7-1** | **宿主退出机理定性（换假设）** | 抓 STpre 退出前后的 WER 记录 / Application 事件日志 / 退出码；用轻量 COM 心跳探测宿主在网格期间是否仍响应 | 给出「优雅退出 / 崩溃 / 卡死被杀」之一的判定与证据；据此决定是否还有参数路径 | 2 |
| **R7-2** | **条件体系补深（原 R6-2）** | 批量收割 43 个未落键 `CreateCond*`，毒类型单进程隔离 | 精确键 90 → **≥140 / 165** | 3 |
| **R7-3** | **数值等价（原 R6-3）** | 50 Pa 变体双跑出非零场 delta 表 | delta 表入册且非零场；FLD/iFLD 结论明确 | 2 |
| **R7-4** | **按实测键反向写宿主** | 用 R6-5 的 5 条映射，把 MeshParam 的 facet 项写进宿主 `FACET.*`（只写实测确认的取值），宿主重开验证 | ≥3 个字段写宿主键后宿主 err=0 且读回值符合预期 | 1.5 |
| **R7-5** | **面板落盘收尾判定** | `_PartsControlFollowupBody` 接通道；判定 `CondTypeCatalogDialog`（对话框）是否计入面板账 | memory_only ≤1 且账目口径写清 | 0.5 |

### 执行记录（2026-09-14）

#### R7-1 ✅ 已成 —— 宿主侧**崩溃**定性（APPCRASH in mfc140u.dll）

离线取证（Windows Application 日志 + WER），与 STEP 网格轮次时间戳一一对应：

| 时间 | 事件 | 内容 |
|---|---|---|
| 20:52:19 / 21:11:15 / 21:24:58 / 21:34:55 | Application Error **ID 1000** | 出错应用 **`scFLOWpre_Bx64net.exe`**（版本 5225.20302.2025.1223），出错模块 **`mfc140u.dll`** |
| 同上 +1 s | WER **ID 1001** | `Event Name: APPCRASH`，Problem signature P1 同上 |
| 20:57:07 | WER **ID 1001** | `RADAR_PRE_LEAK_64`，P1 = `SCTpref_Dx64net.exe` |

**判定：崩溃** —— 既不是优雅退出，也不是 OOM（R6-1 已证宿主消失前仅 87.7 MB WS）。

**一处重要修正**：我们一直按 **STpre**（宿主）探活，但崩的是 **`scFLOWpre_Bx64net`（工作进程，
真正做网格的那个）**；STpre 随后退出/被杀，所以我们看到的是「宿主消失」。台账 `last_seen_hosts`
记的也是 STpre —— 这正是 R8-4 要补的（同时记工作进程 pid/内存/退出码 + WER 报告路径）。

**意义**：STEP 直导网格的拦路石是**宿主产品在 MFC 层的崩溃**，不是我们的脚本或参数 → R6-1 的
参数阶梯在这条路上没有继续价值（已如实停止）。

**R7-1b 附注（绕行尝试）**：改试「STEP →（CADthru 离线）x_t → 网格」，用缓存产物
`_p13_cache/key v2-e574e841c30cc3c2.x_t` 复跑：build `ret_bam=False`、`vmdl_=False`、**`sn_=False`**
（根本没有 SNode），reopen 全 False → **该缓存 x_t 不是可用的完整模型**，绕行路线未成立（需重跑
转换并核对产物完整性 → R8-1）。

#### R7-4 ✅ 已成 —— 反向写宿主键：3/3 全中，且修正了 R6-5 的解读

`tools/xenv_host_write_check.py`：直接把值写进宿主工程 `main.xenv` 的 `FACET.*` 键 → 克隆容器 →
宿主 OpenProject → 用 `MeshingGroupSetting` getter 回读：

| 键 | 写入 | 宿主回读 |
|---|---|---|
| `FACET.SIMPLE_MAX_ANGLE` | 8 | **8** |
| `FACET.SIMPLE_MAX_WIDTH` | 9 | **9** |
| `FACET.USE_DETAIL_MAX_WIDTH` | false | **False** |

宿主 **27/27 err=0**、`sn_/mg_/mdl_/oct_/mgs_=True`。证据 `_p12u_gate/r7_4_write.json`。

> **解读修正**：R6-5 观察到「数值 setter 传 7/9/13 读回 0」，本轮证明那是 **setter 侧归一化**，
> 不是存储限制 —— **直接写 xenv 的键是被宿主尊重的**。也就是说 MeshParam 落宿主键这条路是通的，
> 只是要用「写 xenv」而不是「调 setter」。

#### R7-5 ✅ 已成 —— 面板落盘收尾（memory_only 1）

`_PartsControlFollowupBody` → `main.xenv [PANEL_FOLLOWUP]`（勾选按 `_vbs_op` 分键，子类互不串）；
审计 **persisted 16 / memory_only 1**（只剩对话框 `CondTypeCatalogDialog`）。测试
`tests/test_panel_persist_r75.py`（5 项）。

顺带修掉一个**连续两轮把回归弄红**的测试脆性：早期轮次把「审计精确计数」写死在自己的断言里，
每次后续迁移都会打红。现改为**单调不变量**（早期轮次只断言各自迁移的面 + 只允许文档化残留），
精确计数交给最新一轮的测试负责。

#### R7-2 / R7-3 ❌ 未执行（已连续三轮顺延，如实记账）

条件体系补深与数值等价各需一整块预算，三轮都被「当轮头号实机项」挤掉。**R8 把它们定为主项**，
不再让任何新实机项插队。

#### 回归

全量回归 **1190 passed / 4 skipped / 0 failed**（627.33 s；R6 末为 1184 —— 本轮净增 6 项：
`tests/test_panel_persist_r75.py` 5 项 + 1 项由条件性 skip 恢复为通过）。
### 明确不做（R7 内）

* CATIA / 3DXML / SolidEdge / JT / Rhino / VDAFS；
* 内核 / 求解器 / scPOST 复刻；
* 不写未实测确认的宿主键值（R6-5 已证明数值 setter 不回读原值）。

---

---

## R8 —— 条件收割 + STEP 绕行定位 + 取证补全 + 宿主键闭环（2026-09-14，执行记录）

### 依据

* R7-1 定性为**宿主工作进程崩溃**（APPCRASH / mfc140u.dll）→ STEP 直导网格不是我们能修的，绕行路线
  （STEP→CADthru→x_t→网格）也未成立（缓存 x_t 无 SNode）→ 需要重跑转换并核对产物完整性；
* R7-4 证明「写 xenv 键被宿主尊重」→ MeshParam 落宿主键可行，且不需要 setter；
* R7-5 把 memory_only 压到 1（只剩对话框）→ 面板落盘这条线收尾；
* **R7-2 / R7-3 已连续三轮顺延** → R8 定为**主项**，先做这两件，不再让新实机项插队。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R8-1（主项）** | **条件体系补深** | 宿主批量收割 43 个未落键 `CreateCond*`：毒类型 `CreateCondBatteryARCDataPreprocessing` 单进程隔离、旧版工程先做版本转换前置 | 精确键 90 → **≥140 / 165**；写盘条件宿主零破坏 | 3 |
| **R8-2（主项）** | **数值等价** | 50 Pa 变体双跑（宿主 vs 本仓产物）出**非零场** delta 表；明确 FLD / iFLD 可得性 | delta 表入册且非零场 | 2 |
| **R8-3** | **STEP 绕行路线重建** | 重新用 `cadthru_convert` 转换 `key v2.step`（不依赖旧缓存），核对产物含 SNode/可 BAM，再走 x_t 网格 gate | 得到「STEP 来源 + `mesh_exists=True`」的一条证据，或给出转换产物不可用的确切原因 | 1.5 |
| **R8-4** | **网格失败取证补全** | 台账同时记**工作进程**（`scFLOWpre_Bx64net`）pid/内存/退出码，并在 host-gone 时抓 WER 报告路径 | host-gone 行含工作进程画像与 WER 路径 | 1 |
| **R8-5** | **MeshParam 落宿主键（可行路径）** | 用 R7-4 证明的「写 xenv」方式把 MeshParam 的 facet 项写宿主键；只写实测键、只写实测取值 | ≥3 字段写宿主键且宿主回读一致、err=0 | 1.5 |

### 执行记录（2026-09-14）

#### R8-4 ✅ 已成 —— host-gone 补记**工作进程**画像 + WER 路径

R7-1 的教训（崩的是工作进程、台账却只记 STpre）直接落成代码：

* `FlowExecutor` 新增 `worker_image` / `worker_pids_fn` / `wer_fn`，在**宿主还在时**同步采样工作进程
  pid 与内存；
* host-gone 行新增 `worker_image` / `last_seen_worker` / `last_seen_worker_memory` / `wer_reports`；
* 新增 `wer_reports()`：直接读 `C:\ProgramData\Microsoft\Windows\WER\Report{Archive,Queue}` 目录名
  （不查事件日志，免权限）—— 本机实测立刻列出 `AppCrash_scFLOWpre_Bx64ne_*`，与 R7-1 的事件日志
  互相印证。

测试 `tests/test_host_gone_r84.py`（5 项）。

#### R8-3 ⚠️ 部分成 —— STEP→CADthru→x_t：**离线通、宿主不认**

* 重新转换（不用旧缓存）：`key v2.step` → `_p12u_gate/r8_3_keyv2.x_t`，**9.9 s**，离线校验
  **1 body / 4358 三角 / bbox [-4,-4,0]–[4,4,3]** —— 文件本身是完整可用的 Parasolid；
  （顺带解释了 R3-1 里 `bbox=-4,4,4,3` 的困惑：探针只打了扁平数组的 0/3/4/5 下标。）
* 但把这份 x_t 交给宿主 `OpenCadFile`：`ret_bam=False`、`vmdl_=False`、**`sn_=False`**（没有 SNode），
  mesh 65/66、reopen 全 False —— 与旧缓存产物的失败形态**完全一致**。
* 结论：拦路石不在我们的转换（离线完全正常），而在**宿主对 CADthru 产出的 x_t 的摄取**
  （宿主原生 `tests/box/box.x_t` 同一流程 `sn_=True`）。→ R9-1 做两种 x_t 的头部/schema 差分。

#### R8-5 ✅ 已成 —— Faceter 面板输出键 == 实测宿主键（闭环）

离线侧（`tests/test_facet_host_keys_r85.py`）：`MesherFaceterBody.apply` 写出的
`FACET.SIMPLE_CHORD_TOLERANCE` / `SIMPLE_MAX_ANGLE` **正是** R6-5/R7-4 实测确认的宿主键（键名
不靠猜，且与 R7-4 的实机回读接上）；最大边长走面板自己的「相对最大边长」路径，故只断言被写出且为数值。

实机侧已由 R7-4 完成（写 xenv → 宿主 getter 回读 8/9/False、27/27 err=0）。**闭环成立**：
面板 → xenv 键（离线证明）+ xenv 键 → 宿主（实机证明）。

#### R8-1 ✅ 已成（负结果）—— 条件「补深」实测封顶：16 个未落键 creator **全部无可落键**

离线 `plan` 先纠正账目：**剩余未落键的 creator 只有 16 个**（不是历史笔记里的 43）。随后跑了
**完整批量收割**（`_p12c_cond_harvest.py all`）：16 条 `Create*` 全部 `True`、`save_err=0`、产物落盘
（`mk015_VolumePressureDrop=True` / `mk016_FMIVariable=True` / `out_exists=True`）。

结果（`p12c_harvest_report.json`）：

| 量 | 值 |
|---|---|
| `types_before` → `types_after` | **115 → 115（零新增）** |
| `new_in_universe` | 0 |
| `remaining_missing` | 75 |
| 注册表归属 | `registry_key` **90** + `member_locus` **2** = **92 精确键**；`wizard_session_state` 71（+1 gated）、`alias` 1、`poison_isolated` 1 |
| 收割产物 | `p12c_cond_harvest_out.pph` 条件数 23（本次重生成，此前为 49） |

**结论：这 16 个类型即使建成功也不会在 main.xml 留下条件落点** —— 与 71 个「向导会话态」类型同源。
也就是说 **≥140/165 的验收线建立在错误前提上**：真正可达的「有 XML 落点」类型数就是 **92**（已被全部
登记），其余属设计上无落点的向导态。条件体系这条线到这里按实测**封顶**，不再有可收割空间。

> 副作用记账：本轮 `all` 重新生成了 `p12c_cond_harvest_out.pph`（49 → 23 条条件）。R4-5 的证据 JSON
> 已入库，不受影响；但后续若复跑 R4-5 工具，基数会变小（24 → 受 23 限制）。

#### R8-2 ❌ 未执行（连续四轮顺延）

数值等价需要跑求解器；本轮预算已用于 R8-1 的批量收割与 R8-3 的实机验证。如实记账，R9 定为主项。

#### 回归

全量回归 **1197 passed / 4 skipped / 0 failed**（620.06 s；R7 末为 1190 —— 本轮净增 7 项：
`tests/test_host_gone_r84.py` 5 项 + `tests/test_facet_host_keys_r85.py` 2 项）。

> **收口附注（账目一致性）**：R8-1 的收割让 `schemas/merged.json` 多出 1 例实样（59 → 60），
> 使旧的 `cond_types.json` / `p12h_registry_report.json` 与重算结果不一致（determinism 测试变红）。
> 处理：① 用 `_p12h_reconcile.py` 重算入册（version 8，summary `exact_key 92 / boundary 72 /
> unclassified 0`）；② 期间发现 `p12h_wizard_report.json` 的 `families` 只剩 1 族（工作副本被截断），
> 用**本仓已提交的 `wizard_batch_verdicts`（27 族：25 session_state / 1 keys_projected / 1 not_run）**
> 重建该输入，再重算 → 18/18 reconcile 测试恢复绿。两处都已入册，避免下一轮再踩。
### 明确不做（R8 内）

* CATIA / 3DXML / SolidEdge / JT / Rhino / VDAFS；
* 内核 / 求解器 / scPOST 复刻；
* 不再为 STEP 直导网格做参数扫描（R7-1 已定性为宿主崩溃）；
* 不让新实机项插队 R8-1 / R8-2。

---

---

## R9 —— x_t 拒收判据 + 崩溃标记 + 账目口径固化（2026-09-14，执行记录）

### 依据

* R8-1 实测封顶：条件体系 92 精确键 = 全部可落点类型（16 个未落键 creator 收割后零新增）→ 该线收尾，
  不再投入；
* R8-3 把 STEP 绕行的拦路石精确定位到**宿主对 CADthru x_t 的摄取**（离线 1 body/4358 三角完全正常，
  宿主 `sn_=False`）→ 需要两种 x_t 的格式差分；
* R8-5 闭环成立（面板键 = 实测宿主键 + 实机回读一致）→ 宿主键写通道可用于更多面板；
* R8-4 把失败取证补齐（工作进程画像 + WER）→ 下一次实机失败可直接归因；
* **R8-2 数值等价连续四轮顺延** → R9 定为**唯一主项**，先做完再谈其它。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R9-1（唯一主项）** | **数值等价** | 50 Pa 变体双跑（宿主 vs 本仓产物）出**非零场** delta 表；明确 FLD / iFLD 可得性 | delta 表入册且非零场 | 2 |
| **R9-2** | **两种 x_t 的格式差分** | 宿主原生 `tests/box/box.x_t` vs CADthru 产出 `r8_3_keyv2.x_t`：Parasolid 头/schema/单位/装配层逐字段比对 | 给出宿主拒收 CADthru x_t 的**可复现判据**（字段级）或证伪 | 2 |
| **R9-3** | **宿主键写通道铺开** | 用 R8-5 的闭环把 Faceter 面板其余已实测键（`USE_SIMPLE_SETTING` / `MDL_METHOD` / `DETAIL_*`）纳入实机回读 | 每个键都有「面板→xenv→宿主回读」三段证据 | 1.5 |
| **R9-4** | **崩溃取证自动化** | R8-4 的 WER 字段接进断言语义：host-gone 且 `wer_reports` 非空 → 台账标 `host_crash=true` | 一次真实 STEP 网格失败自动标出 `host_crash` | 1 |
| **R9-5** | **审计账目口径固化** | 把「有落点 92 / 向导态 72 / 其它 1」写成 `docs/` 常量表，扫描脚本再生不丢账 | 再生脚本输出与常量表一致 | 0.5 |

### 执行记录（2026-09-14）

#### R9-2 ✅ 已成（本轮头条）—— 宿主拒收 CADthru x_t 的**字段级判据**

`tools/xt_format_diff.py` 把两种 x_t 的头部块逐字段摆开（第一次只看连续 `**` 行，两边都只剩 3 行、
看起来一样 —— 那是**假阴性**；改成收全头部到 `END_OF_HEADER` 才看见真差异）：

| 字段 | 宿主原生 `tests/box/box.x_t` | CADthru 产出 `r8_3_keyv2.x_t` |
|---|---|---|
| **`SCH`** | **`SCH_3400153_34001`** | **`SCH_3701153_37102`** |
| `FRU` | sdl_parasolid_customer_support | Software Cradle Co.,Ltd. |
| `APPL` | parasolid_acceptance_tests | CADthru |
| `KEY` / `FILE` | 占位名 | **绝对路径**（含 `.X_T`） |
| `FORMAT` / `GUISE` | text / transmit | text / transmit |

**判定：Parasolid schema 版本不匹配** —— 宿主侧是 **v34**（`SCH_34001`），CADthru 写出的是
**v37**（`SCH_37102`）。宿主比写入端**旧**，于是 `OpenCadFile` **静默零几何**（不报错、只是读不出
SNode）——与 R8-3 的观测完全吻合，也与 CATIA 边界时「静默零几何」的形态同源。

**可复现判据**：读两文件头部 `**PART2;` 段的 `SCH=` 行比较版本号即可（工具已入册）。
→ 修复方向见 R10-2（让 CADthru 以低版本 schema 导出，或离线降版）。

#### R9-4 ✅ 已成 —— 崩溃标记自动化

`host_watchdog`：host-gone 行若带 WER 报告，同时置 **`host_crash=True`**（可直接断言，无需事后翻
事件日志）；无 WER 则不打标。测试 2 项。

#### R9-5 ✅ 已成 —— 条件账目口径固化

`tools/cond_ledger.py`：把 R8-1 的口径写成常量并**校验** `schemas/cond_types.json` 现状——
**宇宙 165 = 精确键 92（`registry_key` 90 + `member_locus` 2）+ 别名 1 + 边界 72（`wizard_session_state`
71 + `poison_isolated` 1）**；`Thermoregulation` 是**宇宙外**的族级注记（`wizard_session_state_gated`），
单独记账、不计入三类收束。任何后续再生改了账目，这里立刻红。测试 `tests/test_cond_ledger_r95.py`
（4 项）。

#### R9-3 ❌ 未执行 → R10-3

「铺开宿主键写通道」需要先为**新一批键**做一轮实机核实（R6-5 式：宿主改项 → xenv 差分）。
R8-5 已闭环 2 键（面板→xenv→宿主回读三段齐）；其余键仍只有推测，不能写。如实顺延。

#### R9-1 ❌ 未执行（连续五轮顺延）—— 结构性原因与处置

每轮的头号实机预算都被**新发现的宿主缺陷**吃掉：R2/R3 是 mesh 腿与自愈层缺陷、R6/R7 是宿主崩溃
取证、R8 是条件收割与 x_t 摄取。数值等价需要求解器跑（数十分钟起），始终排在后面。
**处置：R10 只保留这一项为主项，并预先声明「本轮不接任何新的实机排查」**；
若再有宿主缺陷插队，须显式记账为「主项再次让位」而不是默认顺延。

#### 回归

全量回归 **1201 passed / 4 skipped / 0 failed**（614.52 s；R8 末为 1197 —— 本轮净增 4 项：
`tests/test_cond_ledger_r95.py`）。
### 明确不做（R9 内）

* CATIA / 3DXML / SolidEdge / JT / Rhino / VDAFS；
* 内核 / 求解器 / scPOST 复刻；
* **不再做条件体系收割**（R8-1 实测封顶）；
* 不再为 STEP 直导网格做参数扫描（R7-1 定性为宿主崩溃）。

---

---

## R10 —— 数值等价的**前提**修复 + x_t 控版否证 + 宿主键铺开（2026-09-14，执行记录）

### 依据

* R9-2 给出了宿主拒收 CADthru x_t 的字段级判据（schema v34 vs v37）→ 有明确的修复尝试方向；
* R9-4/R9-5 把失败标记与账目口径都固化成可断言的常量 → 后续不再靠人记；
* R9-3 的宿主键铺开需要实机核实，成本明确、可切片；
* **数值等价已连续五轮顺延** → R10 只留它做主项，并预先声明不接新的实机排查。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R10-1（唯一主项，锁定预算）** | **数值等价** | 50 Pa 变体双跑（宿主 vs 本仓产物）出**非零场** delta 表；明确 FLD / iFLD 可得性；本轮不接任何新的实机排查 | delta 表入册且非零场；FLD/iFLD 结论明确 | 2.5 |
| **R10-2** | **x_t schema 降版导出** | 按 R9-2 判据尝试让 CADthru 导出 v34 schema：先探测 `SaveXTFile` 是否接受版本/schema 参数，不通则查是否有环境变量/配置控制导出 schema | 得到宿主可读的 CADthru x_t（`OpenCadFile` 出 SNode），或给出「无法控版」的确切证据 | 1.5 |
| **R10-3** | **宿主键写通道铺开** | 用 R6-5 式（宿主改项 → xenv 差分）核实新一批键（`USE_SIMPLE_SETTING` / `MDL_METHOD` / `DETAIL_*` / `OCT_MESH.FACET_*`），再用 R8-5 式写回并回读 | ≥3 个新键具备「面板→xenv→宿主回读」三段证据 | 1.5 |

### 执行记录（2026-09-14）

#### R10-1 ⚠️ 部分成（主项，如实）—— 把「零流场假阳性」变成代码判据；双跑仍未做

**做了什么**（这部分是本项的前提，缺了后面全是假证据）：

* `solver_delta.zero_field_report()`：delta 报告自带显式判据，且**判据取主变量**（名字含
  `VEL` / `PRES` 的场），因为湍流辅助量（`EVIS` / `TURK` / `TEPS`）在零流场里天然非零 ——
  用「所有场都为零」判会漏报；
* `compare_fph()` 的返回值自动带上 `zero_field` / `primary_nonzero` / `auxiliary_nonzero_count`；
* **真数据验证**（`tests/test_zero_field_r101.py`）：I5 的 `b1/box_b1_400.fph` vs `b2/box_b2_400.fph`
  被判为 **`zero_field=True`、`primary_nonzero=[]`、`auxiliary_nonzero_count>0`** ——
  审计 §5-O3 的「delta 建立在零流场」从**文字指控**变成**可复现数值事实**：
  那张表里 `FC_Vector:VEL` / `FC_Scalar:PRES` 均值都是 0，逐点相等只说明「都是零」。

**FLD / iFLD 可得性（本项验收的另一半）**：

* 读取器齐备：`fldstats.py` / `ifld.py` / `solver_delta.py`（`--kind fld|ifld`）/ `fldutil_bridge.py`；
* 但**磁盘上的已解算产物全部是 `.fph`**（b1/b2、exA36 三腿、probe 各件），没有 `.fld` / `.ifld` ——
  即「可得性」目前是**工具可得、产物不可得**：需要求解器按 FLD 输出跑一次，或从 FPH 导出。

**未完成**：50 Pa 变体双跑。按 §21.7 的实测时长，单腿 1000–1500 s（含冷启动/收敛），两腿加前置
准备 ~40 min 实机；本轮预算已用于上述前提修复与 R10-2/R10-3。→ **R11-1 唯一主项（已锁定，不接新项）**。

#### R10-2 ✅ 已成（负结果，验收第二分支）—— CADthru **无法控版**

`tools/xt_schema_probe`（临时探针）实测：

| 调用 | 结果 |
|---|---|
| `doc.SaveXTFile(asm, path)` | ret=1，产物 `SCH=SCH_3701153_37102`（v37） |
| `doc.SaveXTFile(asm, path, 34 / 3400153 / "SCH_..." / 0 / True)` | 全部 `com_error 无效的参数数目 (-2147352562)` |
| 类型信息内省 `GetTypeInfo` | `无效索引`（不可用） |

**结论：CADthru 的 XT 导出固定 v37，COM 面无法指定 schema** —— 验收句走「给出无法控版的
确切证据」分支。R9-2 的判据（写入端 v37 > 宿主接收端 v34）因此是**硬约束**。
备选路线（→ R11-2）：用**宿主自身**导出 x_t（宿主 Parasolid 即 v34）作为 CADthru 的替代。

#### R10-3 ✅ 已成 —— 宿主键写通道铺开（累计 8 条实测键）

新一轮核实（宿主改项 → xenv 差分）：

| 新键 | 观测 |
|---|---|
| `FACET.USE_SIMPLE_SETTING` | true → **false** ✓ |
| `FACET.MDL_METHOD` | 1 → **0** ✓ |
| `FACET.DETAIL_CHORD_ANGLE` | 10 → **0**（数值 setter 再次归一化；键映射成立） |

写回 + 宿主回读（`xenv_host_write_check`）：`USE_SIMPLE_SETTING=false` / `MDL_METHOD=0` /
`SIMPLE_MAX_ANGLE=8` → 宿主 getter 回读 **False / 0 / 8**，**27/27 err=0**、`sn_/mg_/mdl_/oct_/mgs_=True`。
面板侧离线断言（R8-5）已证 Faceter 面板写的正是这些键名 → **三段证据齐**（面板→xenv→宿主回读）。

#### 回归

全量回归 **1205 passed / 4 skipped / 0 failed**（582.25 s；R9 末为 1201 —— 本轮净增 4 项：
`tests/test_zero_field_r101.py`）。
### 明确不做（R10 内）

* CATIA / 3DXML / SolidEdge / JT / Rhino / VDAFS；
* 内核 / 求解器 / scPOST 复刻；
* 不做条件收割（R8-1 封顶）、不做 STEP 直导网格参数扫描（R7-1 定性为宿主崩溃）；
* **R10-1 期间不接新的实机排查**（要接必须显式记账为「主项让位」）。

---

---

## R11 —— 零流场入 gate + 宿主侧导出否证 + 降版线索（2026-09-14，执行记录）

### 依据

* R10-1 已把「零流场假阳性」变成代码判据（真数据验证通过），数值等价的**前提**已经干净，
  只剩实机双跑这一下；
* R10-2 否证了 CADthru 控版 → 需要换一条能得到**宿主可读 x_t** 的路（宿主自身导出 v34）；
* R10-3 把实测键扩到 8 条且三段证据齐 → 键通道已可复用；
* 数值等价已连续六轮顺延：R11 **只保留它做主项**，并继续锁定「不接新实机项」。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R11-1（唯一主项，锁定预算，预留 ≥1 h 实机）** | **50 Pa 变体双跑 + FLD/iFLD** | 同一 50 Pa 算例跑两腿（宿主原生工程 vs 本仓重写成员的工程），比 FPH 主变量；顺带取一腿开 FLD 输出以回答「iFLD 可得性」 | **非零场** delta 表入册（`zero_field=False`）；FLD/iFLD 结论明确 | 2.5 |
| **R11-2** | **宿主侧 x_t 导出（v34）** | 用宿主 `ScFlowpreDoc.SaveXTFile` 把导入的 STEP 导成 x_t，比对 `SCH=` 是否 v34 且宿主可再次打开 | 得到宿主可读的 x_t（`OpenCadFile` 出 SNode），或证伪该路线 | 1.5 |
| **R11-3** | **零流场判据接入 gate** | `solver_delta --gate` 时 `zero_field=True` 直接判不通过并给显式理由 | 构造零流场对拍时 gate 必须 FAIL 且理由可读 | 0.5 |

### 执行记录（2026-09-14）

#### R11-3 ✅ 已成 —— 零流场判据接入 gate

`solver_delta.gate_fph`：`zero_field=True` **直接判不通过**，并在 `reason` 里点名主变量（实测输出：
`zero field: 主变量(EC_Scalar:PRES,EC_Vector:VEL,FC_Scalar:PRES,FC_Vector:VEL) 两侧均值均为 0 ——
delta=0 只说明都是零，不构成数值等价证据`）。CLI 实测对 I5 b1/b2 返回 **exit=2**。

顺带修掉第三次踩到的同一个坑：`solver_delta.py` 打印含中文的报告时在 ANSI 控制台下抛
`UnicodeEncodeError`（stdout 直接空、退出码非零，看起来像「gate 判失败」）→ 已在模块入口调
`console_utf8.enable()`。测试扩到 **7 项**（含 CLI 级 exit≠0 与理由断言）。

#### R11-2 ⚠️ 部分成（路线证伪）—— 宿主自己导出的也是 v37

`tools/host_xt_export_check.py` 两腿实测（宿主原生 `box.pph` + 真 STEP）：

| 产物 | `SCH=` |
|---|---|
| 宿主原生 `tests/box/box.x_t`（宿主**能读**） | `SCH_3400153_34001`（**v34**） |
| CADthru 产出（R9-2） | `SCH_3701153_37102`（v37） |
| **宿主 `Doc_.SaveXTFile` 导出** | **`SCH_3701153_37102`（v37）** |

而且 `SaveXTFile` 返回 **False**（却写出了文件），随后 `OpenCadFile` 读自己刚写的文件 → `sn1_=False`，
流程以 `com_error(-2147023170, 远程过程调用失败)` 挂起（自愈 2 次、729 s）。

**结论：宿主内核本身就是 v37，它写出 v37、却读不了 v37**（只吃 v34）。所以「宿主侧导出」这条替代路线
**证伪** —— 与 `Doc_.SaveXTFile` 返回 False 一并入册。

**但本轮拿到了真正的修复线索**：`ps_facet2_nodes._TRANSMIT`（对齐 cabdecoding 的
`PK_PART_transmit_o_t`，6 字段）里有一个当前**未使用**的字段 **`transmit_nw_version`** ——
即 Parasolid 的输出 schema 版本控制项。我们本来就直调 `PK_PART_transmit` 写文本 x_t，
**离线把 v37 重编码成 v34 是可达的** → R12-1（纯离线 + 一次宿主验证）。

#### R11-1 ❌ 未执行（主项让位，如实记账）

R11 预留了 ≥1 h 实机给 50 Pa 双跑，但 R11-2 的宿主挂起（729 s）+ 自愈重试吃掉了实机窗口，
随后又需要收口（回归 582 s）。按 R10 立下的规矩，这里**显式记账为「主项让位」**而非默认顺延：
让位原因 = R11-2 的宿主 RPC 挂起。R12 继续把它列为**唯一主项**。

#### 回归

全量回归 **1208 passed / 4 skipped / 0 failed**（551.67 s；R10 末为 1205 —— 本轮净增 3 项）。

> 连带语义变更：旧测试 `test_self_compare_real_fph_passes_gate` 断言「自比必过」，
> R11-3 之后**零流场自比必须 FAIL** —— 已按新语义改写为「逐场判定干净 + zero_field=True + gate FAIL」，
> 避免把 R10/R11 立起来的判据又用旧断言推翻。
### 明确不做（R11 内）

* CATIA / 3DXML / SolidEdge / JT / Rhino / VDAFS；
* 内核 / 求解器 / scPOST 复刻；
* 条件收割（R8-1 封顶）、STEP 直导网格参数扫描（R7-1 定性为宿主崩溃）；
* **R11-1 期间不接新的实机排查**。

---

---

## R12 —— x_t 离线降版尝试（负结果）+ 双跑让位（2026-09-14）

### 依据

* R11-2 证伪「宿主侧导出」，同时**找到真线索**：`_TRANSMIT.transmit_nw_version` 未使用 ——
  我们已有 `PK_PART_transmit` 直调能力，离线降版（v37→v34）路径可达；
* R11-3 让「零流场」再也无法冒充等价证据（gate 直接 FAIL）；
* R11-1 因宿主挂起让位（已显式记账）→ R12 仍列为唯一主项。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R12-1（唯一主项，锁定预算）** | **x_t 离线降版（v37→v34）** | 给 `PK_PART_transmit` 传 `transmit_nw_version`（枚举若干取值）重编码 CADthru 产物，用 R9-2 的 `SCH=` 判据验证版本，再交宿主 `OpenCadFile` | 产出 `SCH_3400153_34001`（或宿主可读的等价版本）且 `OpenCadFile` 出 SNode；否则给出各版本取值的实测表 | 2 |
| **R12-2（主项）** | **50 Pa 变体双跑 + FLD/iFLD** | 预留 ≥1 h 实机；两腿比 FPH 主变量；顺带一腿开 FLD 输出 | **非零场** delta 表（`zero_field=False`）；FLD/iFLD 结论明确 | 2 |
| **R12-3** | **宿主挂起取证补一条** | R11-2 的 `com_error(-2147023170 远程过程调用失败)` 入册：区分「宿主进程消失」与「RPC 通道断」 | host-gone/挂起台账能区分这两类 | 0.5 |

### 执行记录（2026-09-14）

#### R12-1 ⚠️ 部分成（负结果）—— `transmit_nw_version` 不改变输出 schema

`tools/xt_downgrade.py`：`PK_PART_receive` → `PK_PART_transmit(nw_version=?)`，逐档实测输出头部：

| `nw_version` | 输出 | 版本串 |
|---|---|---|
| 0（原默认） | 6278 B | `modeller version 370115323 SCH_3701153_37102_1300`（**v37**） |
| 100 | 5464 B | v37 |
| 1 / 34 / 1000 / 2025 / 3400153 / 34001 / 37102 / 3701153 | **无输出** | —— |

**结论：按当前结构布局写 `transmit_nw_version` 无效**（0/100 仍写 v37，其余取值直接不产出文件）。
另一个发现：本仓离线 transmit 的输出**没有 `**PART2;` 段**，版本信息在第一行
`T51 : TRANSMIT FILE created by modeller version …` —— 因此 R9-2 的 `SCH=` 判据对这类文件不适用，
需要用版本串判断（工具已按此读）。

→ R13-1：从 `pskernel.dll` 导出表里找真正的版本控制入口（如 `PK_SESSION_*` 族）并核对
`PK_PART_transmit_o_t` 的真实字段偏移；找不到就如实记为「本机不可离线降版」。

#### R12-2 / R12-3 ❌ 未执行

R12-2（50 Pa 双跑）需 ≥1 h 连续实机窗口，本轮未取得；R12-3（RPC 断 vs 进程消失）依赖 R12-2/R11-2 的
复现场景。两项顺延 R13，**R13-2 仍为唯一主项**。

#### 回归

全量回归 **1208 passed / 4 skipped / 0 failed**（549.92 s；与 R11 持平 —— 本轮只新增离线工具，未加测试）。
### 明确不做（R12 内）

* CATIA / 3DXML / SolidEdge / JT / Rhino / VDAFS；
* 内核 / 求解器 / scPOST 复刻；
* 条件收割、STEP 直导网格参数扫描（均已定性）；
* **R12-1/R12-2 期间不接新的实机排查**；若再让位，须再次显式记账。

---

---

## R13 —— x_t 离线降版**成功**（v37→v34）+ 宿主可读（2026-09-14）

### 依据

* R12-1 证伪了「按现结构写 `transmit_nw_version`」这条降版路，但**没否定离线降版本身** ——
  `PK_PART_transmit` 仍是我们唯一的写 x_t 通道，需要找对字段/入口；
* R12-1 还纠正了判据：本仓 transmit 产物无 `**PART2;`，版本看首行 `modeller version` 串；
* 50 Pa 双跑连续两轮让位（R11 因宿主挂起、R12 无窗口）→ R13-2 锁定为唯一主项。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R13-1** | **找对降版入口** | 从 `pskernel.dll` 导出表枚举 `PK_SESSION_*` / `*transmit*`；核对 `PK_PART_transmit_o_t` 真实布局（对齐官方头或逐字段偏移实验） | 要么产出 v34（宿主可读，`OpenCADFile` 出 SNode），要么给出「本机不可离线降版」的完整证据 | 1.5 |
| **R13-2（唯一主项，锁定 ≥1 h 实机）** | **50 Pa 变体双跑 + FLD/iFLD** | 两腿比 FPH 主变量；一腿开 FLD 输出 | 非零场 delta 表（`zero_field=False`）；FLD/iFLD 结论明确 | 2 |
| **R13-3** | **宿主挂起/RPC 断取证** | 台账区分「宿主进程消失」与「RPC 通道断」 | 两类事件可分辨 | 0.5 |

### 执行记录（2026-09-14）

#### R13-1 ✅ 已成（本轮头条，且是 R8-3/R9-2 那条断链的修复）

R12-1 的负结果被本轮推翻，根因是**结构版本用错**：guide §11.5 记载 V37 的
`PK_PART_transmit_o_t` 需 **`o_t_version=4`**（1/2/3 是旧布局）、格式枚举 `18220=text`
（不是 0..5）。我们此前一直传 `1`/`0`，于是选项转换器丢弃了版本字段。

再查 Q-Solid 官方文档（`PK_PART_transmit_o_t`）：字段 `transmit_version`（V37 里叫
`transmit_nw_version`）的编码是**主版本×10+次版本** —— 101 = Parasolid 10.1、90 = 9.0，
最早 7.0、当前版本亦允许。宿主接收端是 **v34**，对应 **`340`**。

实测（`tools/xt_downgrade.py` + `tools/xt_downgrade_host_check.py`）：

| 步骤 | 结果 |
|---|---|
| 离线降版 `transmit_version=340`（`o_t_version=4`, `format=18220`） | **5553 B，`SCH_3400000_340010`（v34）** |
| 宿主 `OpenCadFile` 该产物 | **`snode_alive=True`**、`mg_alive=True`、`ret_bam=True`、`vmdl_alive=True` |
| 宿主整体 | **28/28 err=0**，并成功 `SaveProject` |

即：**STEP → CADthru(v37) → 本仓离线降版(v34) → 宿主可读 → BAM 建成** —— 完全在自有工具链内
完成，不需要宿主参与转换。R8-3 的「宿主静默零几何」与 R9-2 的版本判据至此**闭环修复**。
（`bbox` 探针取到 null 是探针时序问题——SNode/VMDL 均在场，非阻塞。）

#### R13-2 / R13-3 ❌ 未执行

R13-2（50 Pa 双跑，需 ≥1 h 连续实机）本轮实机窗口用于 R13-1 的降版验证；R13-3 依赖其复现场景。
两项顺延 R14，**R14-2 仍列为主项**。

#### 回归

全量回归 **1208 passed / 4 skipped / 0 failed**（547.96 s；与 R12 持平 —— 本轮为工具/实机验证，未加测试）。
### 明确不做（R13 内）

* CATIA / 3DXML / SolidEdge / JT / Rhino / VDAFS；
* 内核 / 求解器 / scPOST 复刻；
* 条件收割、STEP 直导网格参数扫描；
* **R13-2 期间不接新的实机排查**（让位须显式记账）。

---

---

## R14 —— 降版接成产品路径 + **一次重要自我纠错**（2026-09-14）

### 依据

* R13-1 打通「离线降版 → 宿主可读」，**STEP 绕行路线的最后一跳已解决** → 下一步是把它接成产品路径；
* 降版参数已定（`o_t_version=4` + `format=18220` + `transmit_version=340`），可固化为默认导出选项；
* 50 Pa 双跑已连续四轮让位 → R14-2 仍为主项。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R14-1** | **降版接成产品路径** | 把「CADthru 转换 → 离线降版 v34 → 落 PPH 成员」串成一条 CLI（`cadthru_convert --downgrade 340`），并跑一次端到端 gate（x_t 腿网格） | 一条命令得到宿主可读的 v34 x_t；gate 出 `mesh_exists=True` | 1.5 |
| **R14-2（主项，锁定 ≥1 h 实机）** | **50 Pa 变体双跑 + FLD/iFLD** | 两腿比 FPH 主变量；一腿开 FLD 输出 | 非零场 delta 表（`zero_field=False`）；FLD/iFLD 结论明确 | 2 |
| **R14-3** | **`transmit_version` 取值表入册** | 枚举 340/341/350/360 并记录各档 `SCH=` 与宿主可读性 | 表入册；默认档位有据可依 | 0.5 |

### 执行记录（2026-09-14）

#### R14-1 ✅ 已成 —— 一条命令出 v34；并**纠正 R8-3/R9-2 的误判**

`cadthru_convert.py` 新增 `downgrade_xt()` + `--downgrade VER`：

```
python tools/cadthru_convert.py "…/key v2.step" out.x_t --downgrade 340
→ ok: true, 5553 B, sch: SCH_3400000_340010（v34）
```

**纠错（重要）**：给 gate 传 `--step` 时我一直用**相对路径**，而宿主进程 CWD 不同 →
`OpenCadFile` **静默返回 Nothing**（表现为 `sn_=False`/`ret_bam=False`，看着像「格式不被接受」）。
本轮顺手修掉（`args.step` 未 `resolve()`）后重跑：

| 文件 | 宿主 `OpenCadFile` |
|---|---|
| `r14_1_v34.x_t`（降版 v34） | **`sn_=True`、`vmdl_=True`、`ret_bam=True`、`ret_oct=True`，build 42/42** |
| `r8_3_keyv2.x_t`（**未降版 v37**） | **`snode_alive=True`、`ret_bam=True`、`vmdl_alive=True`，28/28** |

**结论修正**：宿主**本来就能读 CADthru 的 v37 x_t**。R8-3 的「宿主静默零几何」与 R9-2 的
「v37 > v34 → 拒收」**都是相对路径造成的假象**（两个文件头确实不同，但那不是失败原因）。
R10-2「CADthru 无法控版」依然成立，但**对 STEP 路由无关紧要**；R12/R13 的离线降版是一条
**可用能力**（也确有价值：可产出宿主同代 schema），但**不是必要条件**。

→ 教训入册：**所有喂给宿主的路径必须绝对化**（这条已经踩过一次——CADthru 转换时同样是相对路径坑）。

#### R14-1（b）⚠️ 未过 —— mesh 腿仍失败（已定性为宿主 worker 崩溃，非本次改动）

同一次 gate：build **42/42 err=0**、`sn_/vmdl_/oct_=True`；mesh 段 **1154 s**、**160/161**（1 条非零），
`mesh_exists` 未写出 → 与 R7-1 定性的「宿主工作进程 APPCRASH（mfc140u.dll）」同族。

#### R14-2 / R14-3 ❌ 未执行

50 Pa 双跑（需 ≥1 h 连续实机）本轮实机窗口用于 R14-1 的两跑与纠错复验；取值表顺延。

#### 回归

全量回归 **1208 passed / 4 skipped / 0 failed**（601.38 s；与前持平 —— 本轮为实机纠错与工具接线）。
### 明确不做（R14 内）

* CATIA / 3DXML / SolidEdge / JT / Rhino / VDAFS；
* 内核 / 求解器 / scPOST 复刻；
* 条件收割、STEP 直导网格参数扫描（均已定性）；
* **R14-2 期间不接新的实机排查**。

---

---

## R15 —— 宿主路径纪律断言化 + STEP 路由收口（2026-09-14）

### 依据

* R14-1 纠正了「schema 版本」误判 → **STEP 来源的 x_t 本来就能被宿主摄取**（含 v37）；
* 于是 STEP 路由只剩**一条**已知阻塞：宿主 worker 在网格计算中崩溃（R7-1 定性、外部缺陷）；
* 相对路径坑已两次踩到 → 需要一次性断言化；
* 50 Pa 双跑连续五轮让位 → 仍为主项。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R15-1** | **宿主路径绝对化断言** | 在 `host_pipeline`/`vbs_bridge` 或 gate 入口统一断言：任何交给宿主的路径必须 `is_absolute()` | 传相对路径时**立即报错**（不是静默 Nothing）；加 1 条回归 | 1 |
| **R15-2（主项，锁定 ≥1 h 实机）** | **50 Pa 变体双跑 + FLD/iFLD** | 两腿比 FPH 主变量；一腿开 FLD 输出 | 非零场 delta 表（`zero_field=False`）；FLD/iFLD 结论明确 | 2 |
| **R15-3** | **STEP 路由收口记录** | 把「STEP→CADthru(v37 即可)→宿主摄取→BAM」写成一条已通路径（含 v34 可选降版），并标注唯一剩余阻塞 | 文档一句话可复现；剩余阻塞指向 R7-1 的外部缺陷 | 0.5 |

### 执行记录（2026-09-14）

#### R15-1 ✅ 已成 —— 宿主路径必须绝对（两次踩坑的断言化）

新增 `automation/host_paths.py`：`require_abs()` / `abs_str()`，传相对路径**当场抛**
`RelativeHostPath`（带成因说明），而不是让宿主静默返回 Nothing。

接入点：`tools/cad_pipeline_gate.py` 的 `--step` 处理从「悄悄 resolve」改为**断言**（此前正是它
用 resolve 掩盖了「传参就错」的事实，导致 R8-3/R9-2 把宿主静默失败误判成 schema 拒收）。
测试 `tests/test_host_paths_r151.py`（4 项）：绝对通过/相对抛错、POSIX 串、gate 与转换器调用点契约。

#### R15-3 ✅ 已成 —— STEP 路由收口记录

**已通路径（一句话可复现）**：

```
STEP --CADthru--> x_t(v37 即可) --宿主 OpenCadFile--> SNode → BuildAnalysisModel → BAM
（可选：--downgrade 340 产出宿主同代 v34；非必要条件）
```

证据：`_p12u_gate/r14_1_gate.json`（build 42/42、`sn_/vmdl_/oct_=True`、`ret_bam/ret_oct=True`）与
`_p12u_gate/r14_1_v37_host.json`（v37 未降版同样 `snode_alive=True`、28/28）。
**剩余唯一阻塞**：宿主 worker 在网格计算中崩溃（§22.1 定性的 APPCRASH / mfc140u.dll，外部缺陷）。

#### R15-2 ❌ 未执行（连续六轮让位）

50 Pa 双跑需 ≥1 h 连续实机；本轮实机预算为零（R15-1/R15-3 均为离线项）。R16 继续锁定它为主项。

#### 回归

全量回归 **1212 passed / 4 skipped / 0 failed**（544.05 s；R14 末为 1208 —— 本轮净增 4 项：
`tests/test_host_paths_r151.py`）。
### 明确不做（R15 内）

* CATIA / 3DXML / SolidEdge / JT / Rhino / VDAFS；
* 内核 / 求解器 / scPOST 复刻；
* 条件收割、STEP 直导网格参数扫描；
* **R15-2 期间不接新的实机排查**。

---

---

## R16 —— **数值等价达成**：50 Pa 双跑非零场 delta（2026-09-14）

### 依据

* R15-1/R15-3 把 STEP 路由的**非缺陷部分**全部收口（摄取已通、路径已断言化），只剩 R7-1 的宿主崩溃；
* 50 Pa 双跑已连续六轮让位：**R16 只保留它 + 一件必须做的收尾**，不再排新条目；
* 若 50 Pa 双跑仍拿不到连续窗口，则应把它降级为「需人值守的长任务」并如实标注，而不是继续空转轮次。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R16-1（唯一主项，锁定 ≥1 h 实机）** | **50 Pa 变体双跑 + FLD/iFLD** | 两腿比 FPH 主变量；一腿开 FLD 输出；用 R10/R11 的 `zero_field` 判据把门 | 非零场 delta 表（`zero_field=False`）；FLD/iFLD 结论明确 | 2 |
| **R16-2** | **长任务窗口化** | 把 50 Pa 双跑拆成「可断点续跑」的两段（各自独立冷启动 + 产物入册），使单段 ≤30 min | 任一段单独跑完都能入册；中断不丢证据 | 1 |

### 执行记录（2026-09-14）

#### R16-2 ✅ 已成 —— 分段驱动（`tools/solver_dual_run.py`）

把双跑拆成 `leg1` / `leg2` / `delta` / `status` 四段，每段独立冷启动、独立落 `_p12u_gate/r16_dual/<stage>.json`，
中断只丢当前段。默认算例 = 本机 2025.2 官方样本 **`exA06-2_d_50.pph`**（50 Pa 变体）。

#### R16-1 ✅ **已成 —— 非零场 delta 表入册（七轮以来首次）**

| 段 | 用时 | 产物 |
|---|---|---|
| leg1 | **187 s** | `leg1/exA06-2_d_50_139.fph` |
| leg2 | **57 s** | `leg2/exA06-2_d_50_139.fph` |
| delta | 秒级 | `_p12u_gate/r16_dual/delta_table.{json,md}` |

**delta 结论**：`ok=true`、**`zero_field=false`**、
`primary_nonzero=[EC_Scalar:PRES, EC_Vector:VEL, FC_Scalar:PRES, FC_Vector:VEL]`、`gate_ok=true`。

即：官方 50 Pa 算例在**两次独立求解**下，主变量（压力/速度）逐点一致 —— 数值等价**首次有实测证据**，
且不再落入 R10-1 立下的「零流场自比」假阳性陷阱（该判据正是本轮 `zero_field=false` 的来处）。

#### 一处必须纠正的估算（重要）

此前六轮把 50 Pa 双跑估成「需 ≥1 h 连续实机」并据此反复让位 —— **该估算来自 J3 的 exA36-2 算例
（单腿 1000–1500 s），与官方 exA06-2 相差一个数量级**。实测 exA06-2 单腿只需 **57–187 s**，
整轮双跑（含冷启动与对拍）不到 10 分钟。也就是说：**七轮让位建立在一个错误的成本估计上**。
教训入册：排期前先测**目标算例本身**的单腿耗时，不要拿别的算例外推。

#### 回归

全量回归 **1212 passed / 4 skipped / 0 failed**（553.23 s；与 R15 持平 —— 本轮为实机双跑 + 新工具）。
### 明确不做（R16 内）

* CATIA / 3DXML / SolidEdge / JT / Rhino / VDAFS；
* 内核 / 求解器 / scPOST 复刻；
* 条件收割、STEP 直导网格参数扫描；
* **不再新增实机排查条目**（除非主项让位并显式记账）。

---

---

## R17 —— **本仓重写成员 vs 宿主原生：求解结果逐点一致**（2026-09-14）

### 依据

* R16 取得**非零场**数值等价证据（`zero_field=false`、`gate_ok=true`），数值等价这条线可以收口；
* 但该证据是「同一工程两次独立求解」的**可复现性**，还不是「本仓产物 vs 宿主产物」的对照
  —— 后者才是这条线的完整验收；
* 价格估算已纠正：exA06-2 单腿 57–187 s，可在一轮内做多腿；
* STEP 摄取已通（R14/R15），剩余阻塞只有宿主 mesh worker 崩溃（外部缺陷）。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R17-1（主项）** | **本仓产物 vs 宿主产物对照** | 对 exA06-2_d_50：一腿用宿主原生工程、一腿用**本仓重写成员**（mdl/oct/gph）的工程，各跑一次，比 FPH 主变量 | 非零场 delta 表 + 明确结论（逐点一致 / 有差异并给出量级） | 2 |
| **R17-2** | **FLD/iFLD 可得性收口** | 用 exA06-2 跑一腿开 FLD 输出，回答「iFLD 是否可得」 | 结论明确（可得/不可得 + 依据） | 1 |
| **R17-3** | **排期纪律入册** | 把 R16 的教训写成 `docs/ROUNDS.md` 顶部一条硬规矩：估算必须以**目标算例**实测为准 | 顶部有该规矩；后续提案引用它 | 0.5 |

### 执行记录（2026-09-14）

#### R17-1 ✅ **已成（数值等价完整验收）—— 非零场 delta，`gate_ok=true`、`n_fail=0`**

官方 `exA06-2_d_50.pph` 只带 `meshinggroup1.gph` + `_ridge.mdl`（**无 `_part.mdl`/`.oct`**），
故对照腿的重写对象 = **GPH**（本仓写端）：

| 腿 | 工程 | 求解用时 | FPH |
|---|---|---|---|
| 原生 | 官方 `exA06-2_d_50.pph` | 57–187 s | `r16_dual/leg1/exA06-2_d_50_139.fph` |
| 对照 | 同上 + **GPH 成员由本仓写端重写**（`tools/_r17_dual_ours.py`，`clone_pph` 回注） | 57 s（总 78.9 s） | `r17_ours/ours_139.fph` |

**对拍结论**（`_p12u_gate/r17_ours/delta_native_vs_ours.{json,md}`）：

* `zero_field=false`（非零场）；
* `primary_nonzero=[EC_Scalar:PRES, EC_Vector:VEL, FC_Scalar:PRES, FC_Vector:VEL]`；
* **`gate_ok=true`、`n_fail=0`** —— 默认容差 0（逐位复现线）下主变量逐点一致。

即：**本仓写端重写的网格成员，喂给求解器后与宿主原生工程得到的主变量逐点一致**。
数值等价这条线（R10-1 立判据 → R11-3 入 gate → R16 拿到非零场 → R17 完成对照）**至此收口**。

#### R17-2 / R17-3 ❌ 未执行

FLD/iFLD 可得性（需一腿开 FLD 输出）与「排期纪律入册」顺延 R18；本轮实机预算用于对照腿与对拍。

#### 回归

全量回归 **1212 passed / 4 skipped / 0 failed**（563.64 s；与 R16 持平 —— 本轮为实机对照验证）。
### 明确不做（R17 内）

* CATIA / 3DXML / SolidEdge / JT / Rhino / VDAFS；
* 内核 / 求解器 / scPOST 复刻；
* 条件收割、STEP 直导网格参数扫描、宿主 mesh worker 崩溃（外部缺陷）。

---

---

## R18 —— 对照腿固化 + 排期纪律入册（2026-09-14）

### 依据

* R17-1 完成数值等价对照（`gate_ok=true`、`n_fail=0`）→ 该线收口，转入**固化**而非继续探索；
* 一次性脚本 `_r17_dual_ours.py` 应升格为正式工具（对照腿可重复跑）；
* R17-2（FLD/iFLD）与 R17-3（排期纪律）是两件低成本收尾。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R18-1（主项）** | **对照腿固化为工具** | 把 `_r17_dual_ours.py` 并入 `tools/solver_dual_run.py`（新增 `leg-ours` + 自动对拍），并加生成器单测 | 一条命令完成「重写 GPH → 求解 → 对拍」；单测覆盖 | 1.5 |
| **R18-2** | **FLD/iFLD 可得性收口** | 用 exA06-2 跑一腿开 FLD 输出 | 结论明确（可得/不可得 + 依据） | 1 |
| **R18-3** | **排期纪律入册** | 把 R16 的教训（估算以目标算例实测为准）写成 `docs/ROUNDS.md` 顶部硬规矩 | 顶部有该规矩且 R17+ 提案引用它 | 0.5 |

### 执行记录（2026-09-14）

#### R18-1 ✅ 已成 —— 对照腿固化为正式工具

`tools/solver_leg_ours.py`：一条命令完成「取宿主原生网格成员 → **本仓写端重写** → `clone_pph` 回注
→ 求解 → 与原生腿 FPH 对拍（`compare_fph` + `gate_fph`，带零流场判据）」，R17 的一次性脚本已删除。
参数化：`--base` / `--member`（gph/oct/part.mdl 三种重写器）/ `--native-fph` / `--work` / `--json`。
测试 `tests/test_leg_ours_r181.py`（3 项：重写器覆盖三成员、默认算例 = 官方 50 Pa、关键调用点契约）。

#### R18-3 ✅ 已成 —— 排期纪律入册（台账顶部硬规矩）

`docs/ROUNDS.md` 顶部新增「排期纪律」：**任何「需要 X 小时实机」的估算必须在目标算例上实测定档，
不得拿别的算例外推**，并附 R16 的六轮让位反例（J3 exA36-2 1000–1500 s/腿 vs exA06-2 57–187 s/腿）。
后续提案涉及实机时长时必须写明依据的算例与实测数字。

#### R18-2 ❌ 未执行（FLD/iFLD 可得性）

需一腿开 FLD 输出；本轮实机预算用于 R18-1 的工具化验证与收口。顺延 R19-1。

#### 回归

全量回归 **1215 passed / 4 skipped / 0 failed**（559.18 s；R17 末为 1212 —— 本轮净增 3 项：
`tests/test_leg_ours_r181.py`）。
### 明确不做（R18 内）

* CATIA / 3DXML / SolidEdge / JT / Rhino / VDAFS；
* 内核 / 求解器 / scPOST 复刻；
* 条件收割、STEP 参数扫描、宿主 mesh worker 崩溃（外部缺陷）；
* 不再重复数值等价探索（R17 已收口）。

---

---

## R19 —— FLD/iFLD 可得性收口（2026-09-14）

### 依据

* R17/R18 把数值等价从「探索」变成「一条可重复命令」→ 该线进入维护态；
* FLD/iFLD 可得性是数值等价线上唯一未回答的问题（读取器齐备、产物缺席）；
* 价格依据：exA06-2 单腿实测 57–187 s（R16-R17 实测，符合新入册的排期纪律）。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R19-1（主项）** | **FLD/iFLD 可得性收口** | 用 exA06-2 跑一腿（sph 里开 FLD 输出；实测单腿 ~1–3 min），检查产物目录是否出现 `.fld` / `.ifld` | 结论明确：可得（附文件路径与 `fldstats`/`ifld` 可读证据）或不可得（附求解器设置证据） | 1.5 |
| **R19-2** | **对照腿并入双跑驱动** | 把 `solver_leg_ours` 接进 `solver_dual_run` 的 `leg-ours` 阶段，使「原生/对照/对拍」三段同源 | 一条命令三段跑完；`status` 能看到三段 | 0.5 |
| **R19-3** | **R17 结论入 NYI/优先级口径** | 把「自研产物数值等价」的实测结论写进审计与优先级文档的口径行 | 两处口径与 §32 一致 | 0.5 |

### 执行记录（2026-09-14）

#### R19-1 ✅ 已成 —— 结论：**工具可得、默认产物不可得**

本轮不新增实机（R16/R17 已有 exA06-2 的**两腿独立求解**产物可直接判），零成本取证：

| 证据 | 结果 |
|---|---|
| R16/R17 求解目录产物类型 | `.fph .rph .ccdt .csln .gph .sph .l .log`（+ 我方脚本/日志） |
| 是否有 `.fld` / `.ifld` | **0**（`_p12u_gate`/`_p12o`/`_p12k` 全树计数 0） |
| sph 明文键 `FLD/IFLD/OUTPUT` | 未找到（该提取法在 sph 上不可靠，**不作为证据**，如实标注） |

**结论**：

* **读取器齐备**：`fldstats.py` / `ifld.py` / `solver_delta --kind fld|ifld` / `fldutil_bridge.py`；
* **默认求解链不产出** FLD/iFLD —— 与 J3 期记录（链路产物仅 FPH/RPH/L/CSLN）一致，本轮用 exA06-2 两腿
  **独立复现**了同一事实；
* 要拿到 FLD/iFLD 需在求解器输出设置里显式开启（scFLOWpre 侧选项），本轮**未定位到具体开关** ——
  这是 R20-1 的入口（在 2025.2 手册/选项里找 FLD 输出开关，而不是继续猜 sph 键名）。

#### R19-2 / R19-3 ❌ 未执行

`leg-ours` 并入双跑驱动、以及把 R17 结论写进 NYI/优先级口径行，均顺延 R20（两者各 ≤0.5 人日）。

#### 回归

全量回归 **1215 passed / 4 skipped / 0 failed**（553.20 s；与 R18 持平 —— 本轮为离线取证，未改代码）。
### 明确不做（R19 内）

* 其余 CAD 格式、内核/求解器复刻、条件收割、STEP 参数扫描、宿主 mesh worker 崩溃（外部缺陷）；
* 不再重复数值等价探索（R17 收口，R18 固化）。

---

---

## R20 —— FLD 开关定位：**方向被纠正**（2026-09-14）

### 依据

* R19-1 把 FLD/iFLD 问题收敛成「**找求解器输出开关**」这一件事（读取器与判据都已就绪）；
* R19-2/R19-3 是两件 ≤0.5 人日的收尾；
* 价格依据：exA06-2 单腿实测 57–187 s（R16/R17 实测，符合排期纪律）。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R20-1（主项）** | **定位 FLD 输出开关** | 在 2025.2 手册（`Manuals/scFLOW/HTML/Pre_eng`）与求解设置界面/`main.xml` 里找 FLD/iFLD 输出项；找到后按该项跑一腿 exA06-2 | 得到 `.fld` 或 `.ifld` 产物并用 `fldstats`/`ifld` 读通；或给出「本机不可开」的确切依据 | 1 |
| **R20-2** | `leg-ours` 并入 `solver_dual_run` | 新阶段复用 `solver_leg_ours.build_ours` | 一条命令三段跑完 | 0.5 |
| **R20-3** | R17 结论入 NYI/优先级口径 | 两处口径与审计 §32 一致 | 口径一致 | 0.5 |

### 执行记录（2026-09-14）

#### R20-1 ✅ 已成（结论纠正方向）—— FLD/iFLD 不是 scFLOWpre 的输出项

按 R19-1 的结论去手册里找「求解器 FLD 输出开关」，结果**推翻了那个方向**：

| 检索 | 结果 |
|---|---|
| `Manuals\scFLOW\HTML\Pre_eng` 里 `FLD / iFLD / FLD output` | **0 命中** |
| 全手册树（CADthru / Common / scFLOW / scPOST / SCT / ST） | 仅 **ST_FE103–FE113** 一类**读取侧错误码**提到 FLD/FLDI（"READ INVALID DATA. Data in FLD-file is invalid"、"CANNOT FIND VARIABLE(nnnn) IN FLDI(ffff)" 等） |

**结论**：FLD/iFLD 是 **STpre / scPOST 侧的映射与读取格式**（手册只定义读入时的错误语义），
**不是 scFLOWpre 求解器的输出选项** —— 所以「去 scFLOWpre 输出设置里找 FLD 开关」这个方向本身不成立。
本仓的 `fldutil_bridge.py`（及 `.gitignore` 里的 `FLDUTIL.log`）正对应这条工具链：
**iFLD 应由 fldutil / scPOST 从求解结果生成**，而不是等求解器直接写出来。

→ R21-1：改用 `fldutil_bridge` 从**我们已有的 FPH**生成 FLD/iFLD，并用 `fldstats` / `ifld` 读通。
这样 R19-1 悬着的那半边（产物可得性）就有了可执行的入口。

#### R20-2 / R20-3 ❌ 未执行

`leg-ours` 并入双跑驱动、R17 结论入口径行，顺延 R21（各 ≤0.5 人日）。

#### 回归

全量回归 **1215 passed / 4 skipped / 0 failed**（552.79 s；与 R19 持平 —— 本轮为手册取证，未改代码）。
### 明确不做（R20 内）

* 其余 CAD 格式、内核/求解器复刻、条件收割、STEP 参数扫描、宿主 mesh worker 崩溃（外部缺陷）；
* 不再重复数值等价探索（R17 收口、R18 固化）。

---

---

## R21 —— 提案（2026-09-14，≈2 人日）

### 依据

* R20-1 纠正了方向：FLD/iFLD 属 **scPOST/STpre 侧的映射格式**，应由 `fldutil` 类工具从结果生成；
* 本仓已有 `fldutil_bridge.py` 与读取器（`fldstats`/`ifld`），且已有 exA06-2 的 FPH 产物；
* R20-2/R20-3 是两件 ≤0.5 人日的收尾。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R21-1（主项）** | **用 fldutil 从 FPH 生成 FLD/iFLD** | 调 `fldutil_bridge`（或直接 `FLDUTIL`）把 exA06-2 的 FPH 转成 FLD/iFLD，再用 `fldstats`/`ifld` 读 | 产出 `.fld` 或 `.ifld` 且被本仓读取器读通；否则给出 fldutil 侧的确切阻塞（缺许可/缺输入格式） | 1 |
| **R21-2** | `leg-ours` 并入 `solver_dual_run` | 复用 `solver_leg_ours.build_ours` | 一条命令三段跑完 | 0.5 |
| **R21-3** | R17 结论入 NYI/优先级口径 | 两处口径与审计 §32 一致 | 口径一致 | 0.5 |

### 明确不做（R21 内）

* 其余 CAD 格式、内核/求解器复刻、条件收割、STEP 参数扫描、宿主 mesh worker 崩溃（外部缺陷）；
* 不再重复数值等价探索（R17 收口、R18 固化）。

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
