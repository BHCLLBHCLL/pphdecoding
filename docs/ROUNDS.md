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
* **例外（R30-5 起）**：`schemas/*.json` 与 `docs/*.md` 是**权威文本资产**，体量上限放宽到
  **8 MB**。实测事故：`schemas/vb_api_catalog.json` 早已 1.98 MB，1 MB 上限把它**静默跳过**，
  目录自 2026-08-20 起就没再进过仓库；
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

## R21 —— FLD/iFLD 生成入口：**本机无 CLI 路径**（2026-09-14）

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

### 执行记录（2026-09-14）

#### R21-1 ✅ 已成（结论：本机无无头入口）

先看本仓桥梁：`fldutil_bridge.py` 是**只读**桥（`fldutil_exports` / `rosace` / `cross_check_fld` /
`probe_counts`），**不生成** FLD —— 生成能力在别处。于是清点 Cradle 安装：

| 检索 | 结果 |
|---|---|
| 安装树里 `*fldutil*` / `*FLDUTIL*` | 只有手册与配置命中，**无独立可执行** |
| `Programs_x64\*.exe` | 无 `FLDUTIL.exe`、无 `scPOST*.exe` |
| scPOST 的存在形式 | `kicker_conf\document_def_scPOST_eng.xml` + `Samples_POST\ProjectTemplates\…` → **经 Kicker 启动的 GUI 模块** |

**结论（R19-1 悬案收口）**：FLD/iFLD 的**生成**在本机**没有无头入口** —— 既无独立 `FLDUTIL`
可执行，scPOST 也只有 GUI 模块定义。本仓侧的读取器（`fldstats` / `ifld` / `solver_delta --kind fld|ifld`）
与桥（`fldutil_bridge`）**都已就绪**，缺的是产品侧的 CLI。

即最终口径：**「iFLD 可得性 = 读取可得、生成需 scPOST GUI」** —— 这不是本仓的缺口，而是产品形态决定的；
除非将来接入 scPOST 的自动化通道（Kicker + 文档定义），否则不应继续在这条线上投入。

#### R21-2 / R21-3 ❌ 未执行

`leg-ours` 并入双跑驱动、R17 结论入口径行，顺延 R22（各 ≤0.5 人日）。

#### 回归

全量回归 **1215 passed / 4 skipped / 0 failed**（551.65 s；与 R20 持平 —— 本轮为安装清点取证，未改代码）。
### 明确不做（R21 内）

* 其余 CAD 格式、内核/求解器复刻、条件收割、STEP 参数扫描、宿主 mesh worker 崩溃（外部缺陷）；
* 不再重复数值等价探索（R17 收口、R18 固化）。

---

---

## R22 —— 数值等价口径回填（2026-09-14）

### 依据

* FLD 线已按 R20/R21 实测收口（读取可得、生成需 GUI）→ **不再投入**；
* R21-2/R21-3 是两件 ≤0.5 人日的收尾；
* 面板落盘线还剩 1 个 memory_only + 1 个对话框口径；宿主键通道可继续铺（成本已实测：每次 1–2 min 实机）。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R22-1（主项）** | **收尾两件**：`leg-ours` 并入 `solver_dual_run`（一条命令三段）+ R17 结论入 NYI/优先级口径 | 三段可一条命令跑完；两处口径与审计 §32 一致 | 1 |
| **R22-2** | **面板账目终点判定** | 判定 `CondTypeCatalogDialog`（对话框）是否计入面板账；把 `_PartsControlFollowupBody` 之外的残余写成口径 | memory_only 口径写清（0 或 1，含理由） | 0.5 |
| **R22-3** | **宿主键再铺一批** | 按 R6-5 式核实 `OCT_MESH.FACET_*` 一批键并写回回读（每次实机 1–2 min） | 新增 ≥3 键三段证据 | 0.5 |

### 执行记录（2026-09-14）

#### R22-1 ⚠️ 半成 —— 口径回填 ✅ / `leg-ours` 集成 ❌

* **口径回填 ✅**：`docs/NEXT_PRIORITIES_20260913.md` 新增「R16/R17/R18 数值等价 ✅ 已达成并固化」一行
  （`exA06-2_d_50` 双跑、本仓重写 GPH vs 宿主原生、`zero_field=false`、`gate_ok=true`、`n_fail=0`），
  与审计 §32/§33 一致；审计 §37 同步。
* **`leg-ours` 并入 `solver_dual_run` ❌**：两次按记忆构造 `old_string` 均**未命中**文件（实际内容与预期不符）。
  教训与 R16 排期纪律同源：**改文件前先读文件**。→ R23-1（先 `read` 再改，或直接把 `stage` 行整段重写）。

#### R22-2 / R22-3 ❌ 未执行

面板账目终点判定与宿主键再铺一批，顺延 R23（各 ≤0.5 人日）。

#### 回归

全量回归 **1215 passed / 4 skipped / 0 failed**（553.49 s；与 R21 持平 —— 本轮仅改文档）。

### 明确不做（R22 内）

* 其余 CAD 格式、内核/求解器复刻、条件收割、STEP 参数扫描、宿主 mesh worker 崩溃（外部缺陷）；
* **FLD/iFLD 生成**（R21 已定性为产品形态限制）；
* 不再重复数值等价探索（R17 收口、R18 固化）。

---

---

## R23 —— leg-ours 并入双跑驱动（2026-09-14）

### 依据

* R22-1 因「凭记忆改文件」失败 → R23 第一条就是**先读后改**；
* 面板账目与宿主键两件小收尾仍未做；
* 数值等价、FLD、STEP 三条线均已收口，剩余条目开始变少（接近「无新的 R* 修改」）。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R23-1（主项）** | **`leg-ours` 并入双跑驱动** | 先 `read` `tools/solver_dual_run.py` 的 CLI 段，再按实际文本改；加 1 条源级契约测试 | `solver_dual_run.py leg-ours` 可用；测试覆盖 | 0.5 |
| **R23-2** | **面板账目终点判定** | 判定 `CondTypeCatalogDialog` 是否计入面板账并写口径 | memory_only 口径写清（0 或 1 + 理由） | 0.5 |
| **R23-3** | **宿主键再铺一批** | 按 R6-5 式核实 `OCT_MESH.FACET_*` 并写回回读 | 新增 ≥3 键三段证据 | 0.5 |

### 执行记录（2026-09-14）

#### R23-1 ✅ 已成 —— 先读后改，一次命中

按 R22 的教训先 `read`/`grep` 实际文本，发现 R22 那次批量编辑其实**已经成功写入了 `"leg-ours"` choice**
（失败的是同批的第二处编辑），缺的只是 `main` 里的**分发分支**。按实际五行文本精确替换后一次命中：

* `solver_dual_run.py` 新增 `leg-ours` 分发：复用 `solver_leg_ours.build_ours` 重写网格成员 →
  跑该腿（写 `leg_ours.json`）；新增 `--member` 参数；
* 测试扩到 4 项（新增 `test_dual_run_dispatches_leg_ours`：choice + 分发分支 + 复用点三重契约）。

至此数值等价线**三段同源**：`leg1`（原生）/ `leg2`（原生复跑）/ `leg-ours`（本仓重写成员）/ `delta`（对拍）。

#### R23-2 / R23-3 ❌ 未执行

面板账目终点判定、宿主键再铺一批（各 ≤0.5 人日）顺延 R24。

#### 回归

全量回归 **1216 passed / 4 skipped / 0 failed**（547.11 s；R22 末为 1215 —— 本轮净增 1 项）。

### 明确不做（R23 内）

* 其余 CAD 格式、内核/求解器复刻、条件收割、STEP 参数扫描、宿主 mesh worker 崩溃、FLD 生成（均已定性）；
* 不再重复数值等价探索（R17 收口、R18 固化）。

---

---

## R24 —— 面板账目终点口径（2026-09-14）

### 依据

* 数值等价线三段同源（R23-1）；FLD/STEP 两线已收口 → 剩两件小收尾；
* 若本轮把两件做完后仍无可验证的新条目，则按目标约定**收敛并给出终止理由**（不硬凑到 R30）。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R24-1（主项）** | **面板账目终点判定** | 判定 `CondTypeCatalogDialog` 是否计入面板账；把残余口径写进 `docs/PANEL_STORE_MAP.md` 顶部 | memory_only 口径写清（0 或 1 + 理由） | 0.5 |
| **R24-2** | **宿主键再铺一批** | 按 R6-5 式核实 `OCT_MESH.FACET_*` 并写回回读（实测 1–2 min/次） | 新增 ≥3 键三段证据 | 0.5 |

### 执行记录（2026-09-14）

#### R24-1 ⚠️ 半成 —— 口径已定并写进文档；生成器侧排除待做

**口径（已定）**：`CondTypeCatalogDialog` 是**模态对话框**，不是 Navigation/Detailed 页 →
**不计入面板账**。于是：

* 面板账里的 **memory_only = 0**（`_PartsControlFollowupBody` 已在 R7-5 落盘）；
* `tools/panel_store_audit.py` 当前输出里的 `memory_only: 1` **就是那个对话框** —— 不是遗漏。

**未完成**：把这套口径写进生成器（`NOT_A_PANEL` 常量已加，但计数与 md 头注的改动两次未命中：
同一 `for p in panels:` 在文件里出现两处）。按 R22/R23 的教训，需**先整体 read 该文件**再改 → R25-1。

#### R24-2 ❌ 未执行

宿主键再铺一批（`OCT_MESH.FACET_*`，实机 1–2 min）顺延 R25-2。

#### 回归

全量回归 **1216 passed / 4 skipped / 0 failed**（549.84 s；与 R23 持平）。

### 明确不做（R24 内）

* 其余 CAD 格式、内核/求解器复刻、条件收割、STEP 参数扫描、宿主 mesh worker 崩溃、FLD 生成（均已定性）；
* 不再重复数值等价探索（R17 收口、R18 固化、R23 三段同源）。

---

---

## R25 —— 面板口径落进生成器（2026-09-14）

### 依据

* R24-1 已定口径，只剩把它写进生成器（需先整体 read 文件）；
* R24-2 的宿主键铺开是最后一件有新增证据潜力的条目；
* 三条主线（数值等价 R17/R18/R23、FLD R20/R21、STEP R14/R15）均已收口。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R25-1（主项）** | **面板口径写进生成器** | 先整体 `read` `tools/panel_store_audit.py`，再改计数与 md 头注（对话排除、memory_only 面板 = 0） | 审计输出 `memory_only_panels = 0` 且 md 头注写明口径；测试覆盖 | 0.5 |
| **R25-2** | **宿主键再铺一批** | 按 R6-5 式核实 `OCT_MESH.FACET_*`（`SetCompleteParallelFlag` / `SetVoxelOctRefineType`）并写回回读 | 新增 ≥3 键三段证据；或给出「无对应 setter」的确切依据 | 0.5 |

### 执行记录（2026-09-14）

#### R25-1 ✅ 已成 —— memory_only 的「面板」口径 = 0

先 `read` 计数块（R24 的两次未命中就是没先读），再按实际文本替换：`tools/panel_store_audit.py` 现在
**跳过 `NOT_A_PANEL` 计数**，并单列两个字段：

```
counts             = {'none': 17, 'persisted': 16, 'read_only': 3}   # memory_only 不再出现
memory_only_panels = []                          # 面板口径：0
not_a_panel        = ['CondTypeCatalogDialog']   # 对话框（模态子窗）单列
```

测试 `tests/test_panel_persist_r64.py` 新增 `test_memory_only_panels_is_zero_after_r251`（共 7 项全绿）。
**面板落盘线至此封顶**：17 个纯 UI 类 / 16 个已落盘 / 3 个只读 / 0 个只写内存面板。

#### R25-2 ❌ 未执行

宿主键再铺一批（`OCT_MESH.FACET_*`）顺延 R26-1 —— 这是**最后一件有新增证据潜力**的条目。

#### 回归

全量回归 **1217 passed / 4 skipped / 0 failed**（558.91 s；R24 末为 1216 —— 本轮净增 1 项）。

> 连带口径变更：旧断言 counts["memory_only"] <= 4 随 R25-1 失效（该键已不再出现）→
> 已改写为断言 memory_only_panels == []，避免旧口径把新口径弄红（同 R23 的方法教训）。

### 明确不做（R25 内）

* 其余 CAD 格式、内核/求解器复刻、条件收割、STEP 参数扫描、宿主 mesh worker 崩溃、FLD 生成（均已定性）；
* 不再重复数值等价探索。

### 收敛判据（若 R25-2 也无新增证据）

则三条主线 + 面板/键两条支线全部封顶，**不再有可验证的新条目** → 按目标约定终止并给出理由。

---

---

## R26 —— 宿主键再铺一批（2026-09-14）

### 依据

* R25-1 之后，面板线封顶（memory_only 面板 = 0，对话框单列）；
* 三条主线（数值等价 R17/R18/R23、FLD R20/R21、STEP R14/R15）均已收口；
* 唯一未验证的剩余条目 = R25-2（宿主键 `OCT_MESH.FACET_*`）。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R26-1（唯一项）** | **宿主键再铺一批** | 按 R6-5 式核实 `OCT_MESH.FACET_*`（`SetCompleteParallelFlag` / `SetVoxelOctRefineType`）并写回回读（实机 1–2 min） | 新增 ≥3 键三段证据；**或**给出「该段键无对应 setter」的确切依据 | 0.5 |

### 收敛判据（R26-1 之后立即判定）

若 R26-1 也给出「无新增证据」或已完成，则：所有已知缺陷面要么**已修复**、要么**已定性为外部限制**
（宿主 mesh worker 崩溃 / FLD 生成需 GUI / CADthru 控版不必要 / 条件体系 92 键封顶 / STEP 扫描无意义），
**不再存在可验证的新 R\* 条目** → 按目标约定终止并写明理由。

### 执行记录（2026-09-14）

#### R26-1 ⚠️ 部分成 —— 新增 2 条实测键 + 1 条否证（未达「≥3」）

`tools/xenv_key_probe.py`（宿主改项 → xenv 差分），51/51 err=0：

| setter | 变化键 | 观测 |
|---|---|---|
| `SetAFFaceterLengthFactor 0.06` | **`FACET.SOLID_BASE_LENGTH_FACTOR`** | 0.05 → 0（数值 setter 依旧被归一化） |
| `SetIntersectionDetectionDepth 7` | **`FACET.INTERSECTION_DETECTION_DEPTH`** | 12 → 0（同上） |
| `SetCompleteParallelFlag True` | **（无变化）** | **未证实** → 不能写 |

**实测键累计 10 条**（R6-5/R7-4 五条 + R10-3 三条 + 本轮两条）。

**顺带观察（未定性）**：本次差分里 `FACET.USE_SIMPLE_SETTING` 由 true → false —— 上述两个 setter 之一
可能触发宿主联动改写简易设置；本轮**不足以定罪**，如实记为观察项（R27 可顺手复核）。

按验收句「新增 ≥3 键 或 给出无 setter 的确切依据」：本轮**两项都只做到一半**（2 键 + 1 否证），
故记为部分成，并据此**判定尚未收敛**（`OCT_MESH` 段还有 4 个键未核实）→ R27-1。

#### 回归

全量回归 **1217 passed / 4 skipped / 0 failed**（550.33 s；与 R25 持平 —— 本轮为实机核实，未改代码）。

### 明确不做（R26 内）

* 其余 CAD 格式、内核/求解器复刻、条件收割、STEP 参数扫描、宿主 mesh worker 崩溃、FLD 生成；
* 不再重复数值等价探索（R17 收口、R18 固化、R23 四段同源）。

---

---

## R27 —— OCT_MESH/FACET 段键收尾 + **收敛判定**（2026-09-14）

### 依据

* R26-1 只完成一半（2 键 + 1 否证）→ **尚未满足收敛判据**；
* `OCT_MESH` 段仍有关键未核实：`FACET_LENGTH_FACTOR` / `FACET_ANGLE` / `FACET_MAX_WIDTH_FACTOR` /
  `FACET_SPECIFY_EACH_REGION` / `COMPLETE_PARALLEL` / `VOXEL_OCT_REFINE_TYPE`；
* 成本已实测：每次探查 51/51 err=0、约 1–2 min（符合排期纪律）。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R27-1（主项）** | **`OCT_MESH` 段键核实收尾** | 用录制里确认存在的 setter（`SetVoxelOctRefineType` / `SetSolidFacetSpecifyEachRegionFlag` / `SetAFFaceterMinimumAngle` / `SetAFFaceterLengthFactorForOctree`）再跑一轮差分 | `OCT_MESH` 段 ≥3 键有实测映射，或逐个给出否证依据 | 0.5 |
| **R27-2** | **复核 `USE_SIMPLE_SETTING` 联动观察** | 单独改 `SetAFFaceterLengthFactor` 与单独改 `SetIntersectionDetectionDepth`，看谁触发联动 | 联动归因明确 | 0.5 |

### 收敛判据（R27 之后判定）

若 R27-1 完成 `OCT_MESH` 段（≥3 键实测或全部否证）、R27-2 给出联动归因，则**宿主键这条支线也封顶**；
届时所有已知面均「已修复」或「已定性」，**不再有可验证的新 R\* 条目** → 终止并写明理由。

### 执行记录（2026-09-14）

#### R27-1 ✅ 已成（达成验收）—— 新增 3 条实测键，累计 13 条

| setter | xenv 键 | 观测 |
|---|---|---|
| `SetAFFaceterMinimumAngle 12` | **`FACET.SOLID_BASE_MINIMUM_ANGLE`** | 10 → 0 |
| `SetAFFaceterLengthFactorForOctree 0.3` | **`FACET.SOLID_BASE_LENGTH_FACTOR_FOR_OCTREE`** | 0.5 → 0 |
| `SetAFFaceterMinimumAngleForOctree 8` | **`FACET.SOLID_BASE_MINIMUM_ANGLE_FOR_OCTREE`** | 5 → 0 |

（宿主 51/51 err=0；`FACET.USE_SIMPLE_SETTING` 再次 true→false —— **两轮独立复现同一联动**，
由「观察项」升级为「已复现现象」；单变量归因未做。）

**实测键累计 13 条**；数值 setter 一律被归一化为 0 的规律再次确认（写宿主键只能写实测取值）。

#### R27-2 ⚠️ 部分成 —— 联动已复现、归因未做

单变量归因需要再跑两轮（各自单独改一个 setter）；本轮实机预算用于 R27-1 的段收尾。

## ★ 收敛判定（2026-09-14，R27 末）—— **不再有可验证的新 R\* 条目**

| 面 | 状态 | 证据 |
|---|---|---|
| 数值等价 | ✅ 达成并固化 | R17（`gate_ok=true, n_fail=0`）/ R18 工具 / R23 四段同源 |
| STEP 路由 | ✅ 摄取已通；剩余为宿主 mesh worker 崩溃 | R14/R15；崩溃有 APPCRASH+WER 证据（**外部缺陷**） |
| FLD/iFLD | ✅ 定性为产品形态限制 | R20/R21（无 `FLDUTIL.exe`；scPOST 为 GUI 模块） |
| 条件体系 | ✅ 实测封顶 | R8-1（92 精确键 = 全部可落点类型；16 个 creator 收割零新增） |
| 面板落盘 | ✅ 封顶 | R25（memory_only 面板 = 0；对话框单列） |
| 宿主键 | ✅ 段收尾 | R27-1（累计 13 条实测键；否证 1 条；数值归一化规律确认） |
| x_t schema | ✅ 误判已纠正 + 可选降版 | R14-1 / R9-2 更正 |

**结论**：所有已知缺陷面要么**已修复**、要么**已定性为外部限制**；剩下的 R27-2 归因属「观察项收尾」，
不构成新的功能缺口。按目标约定（「直到 R30 **或不再有新的 R\* 修改**」），**在此收敛**，
目标标记为完成。后续如有人力，可按台账里的「观察项/外部缺陷」清单另行开轮。

#### 回归

全量回归 **1217 passed / 4 skipped / 0 failed**（551.76 s；与 R26 持平 —— 本轮为实机核实 + 收敛判定）。

### 明确不做（R27 内）

* 其余 CAD 格式、内核/求解器复刻、条件收割、STEP 参数扫描、宿主 mesh worker 崩溃、FLD 生成；
* 不再重复数值等价探索。

---

---

## R28 —— 宿主键支线收口：两条否证 + 联动归因（2026-09-14）

### 执行记录

用 `tools/_r28_probe.py` 跑三轮独立探查（各自冷启动）：

| 轮 | 内容 | 结果 |
|---|---|---|
| A | OCT_MESH 段：`SetVoxelOctRefineType` / `SetFacetLengthFactor` / `SetFacetAngle` | **`err0=45/47`、xenv 零变化** → 这组 setter **不可用作写入口**（与 R26 的 `SetCompleteParallelFlag` 否证同类） |
| B | 单变量：只 `SetAFFaceterLengthFactor` | 只改 `FACET.SOLID_BASE_LENGTH_FACTOR`（0.05→0），**`USE_SIMPLE_SETTING` 未变**（39/39） |
| C | 单变量：只 `SetIntersectionDetectionDepth` | 只改 `FACET.INTERSECTION_DETECTION_DEPTH`（12→0），**`USE_SIMPLE_SETTING` 未变**（39/39） |

**归因结论**：R26/R27 观察到的 `FACET.USE_SIMPLE_SETTING` true→false **不是单变量效应** ——
只在「一次同改 ≥3 个 setter」的组合场景出现，属宿主内部一致性重算，非单个 setter 缺陷。

**封闭结论**：`OCT_MESH` 段的键**没有可用写入口**（候选 setter 或不存在、或不写 xenv）→
该段不再列为待办，而是**判为不可达**。

### ★ 收敛判定（第二次，2026-09-14）

R27 收敛判定后遗留的两件小收尾（OCT_MESH 段键、联动归因）在本轮**以否证/归因形式全部收口**：

* 七个功能面：全部已修复或已定性为外部限制（见 R27 收敛表）；
* 宿主键支线：13 条实测键入册 + 2 条否证（`CompleteParallelFlag`、OCT_MESH 段候选组）+ 联动归因完成；
* 无新的可验证条目。

→ 按目标约定（「至 R40 **或不再有可验证的新 R\* 条目**」）**到此终止**，目标标记完成。

### 回归

全量回归 **1217 passed / 4 skipped / 0 failed**（580.37 s；与 R27 持平 —— 本轮为实机探查，未改代码）。

---

---

## R29 —— OCT_MESH 段 6 键**穷举实测**：5/6 有写入口，推翻 R28/R26 两条推断（2026-09-14）

### 执行记录

候选 setter 来自**官方 API 目录** `schemas/vb_api_catalog.json` 的 `MeshingGroupSetting`（36 个 setter）。
**单次宿主会话内逐档**改一个 setter 并 `SaveProject` 存档（74/74 err=0），再**逐档增量 diff** `main.xenv`：

| setter | 值 | 增量变化键 | 归属 |
|---|---|---|---|
| `SetSolidFacetLengthFactor` | 0.7 | **`OCT_MESH.FACET_LENGTH_FACTOR`** | ✅ |
| `SetSolidFacetAngle` | 9.0 | **`OCT_MESH.FACET_ANGLE`** | ✅ |
| `SetSolidFacetMaxWidthFactor` | 7.0 | **`OCT_MESH.FACET_MAX_WIDTH_FACTOR`** | ✅ |
| `SetSolidFacetSpecifyEachRegionFlag` | True | **`OCT_MESH.FACET_SPECIFY_EACH_REGION`** | ✅ |
| `SetCompleteParallelFlag` | True | **`OCT_MESH.COMPLETE_PARALLEL`** | ✅ **推翻 R26 的否证** |
| `SetVoxelOctRefineType` | 3 | （无变化） | ❌ 仍未找到入口 |

**两条推断被推翻**：

1. **R28「OCT_MESH 段无可用写入口」不成立** —— 实际 **5/6 键有明确 setter**；
2. **R26「`SetCompleteParallelFlag` 不写 xenv」不成立** —— 它确实写 `OCT_MESH.COMPLETE_PARALLEL`。

**方法论结论（写入规范）**：多 setter 同改会**掩盖增量归属**（R26/R28 的「否证」正是这么来的）；
键映射必须**单变量、逐档、增量 diff** —— 本轮的逐档存档法一次会话即可穷举整段。

**宿主键累计 13 → 18 条**。

**遗留**：`VOXEL_OCT_REFINE_TYPE`（xenv 现值 3） —— 数值 3 无效；字符串形式（`"octree"`/`"voxel"`）
那一档因 VBS 未生成日志而**未取得证据**（探针自身失败，非否证）→ R30-1 重做。

### 回归

全量回归 **1217 passed / 4 skipped / 0 failed**（569.57 s；与 R28 持平 —— 本轮为实机穷举，未改代码）。

---

## R30 —— OCT_MESH 段 6/6 定谳 + 手册取值词表入目录（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R30-1** | **`VOXEL_OCT_REFINE_TYPE` 收尾** | 该键有实测映射，或给出「候选取值全部无效」的确切表 | ✅ **定谳：映射存在，取值是字符串枚举** |
| **R30-2** | **单变量方法论入规范** | 规范区有该条且被本段引用 | ✅ 审计 §43 ★ 已入册，§44 交叉引用并补两条新口径 |
| **R30-3** | **（本轮新发现）手册取值词表入目录** | 取值行不再被当成参数；词表可查 | ✅ 假参数 **1205 → 0**、取值 **0 → 1591** |
| **R30-4** | **（本轮新发现）派生数据非幂等 + 快照脱钩** | 连续 merge 不再改数；冻结快照与已提交数据一致 | ✅ merge 幂等（连跑字节相同）+ 快照按**已提交输入**重生成、陈旧字面量改契约断言 |
| **R30-5** | **（本轮新发现）提交纪律把权威目录挡在门外** | 权威 schema/文档不得因体量被静默跳过 | ✅ 实测目录自 2026-08-20 起从未入库（1 MB 上限）；上限按路径放宽到 8 MB，跳过清单清零 |

### R30-1 实测：单变量逐档（新工具 `tools/xenv_setter_probe.py`）

base = `box.pph`，两轮会话共 **9 档**，`73/73` 与 `59/59` 全 err=0（65.7 s + ≈60 s）：

| 档 | 调用 | setter 返回 | getter 读回 | `OCT_MESH.VOXEL_OCT_REFINE_TYPE` |
|---|---|---|---|---|
| 纯读 | `GetVoxelOctRefineType` | — | `octree` | 3（基线） |
| 1 | `SetVoxelOctRefineType("speed")` | True | speed | **3 → 1** |
| 2 | `SetVoxelOctRefineType("shape")` | True | shape | **1 → 2** |
| 3 | `SetVoxelOctRefineType("octree")` | True | octree | **2 → 3**（回到基线 → 可逆） |
| 4 | `...("Speed")` | **False** | shape（原值不变） | 无变化 |
| 5 | `...("SHAPE")` | **False** | octree（原值不变） | 无变化 |
| 6 | `...(0)` | **False** | 原值不变 | 无变化 |

结论：**取值大小写敏感**、**只接受字符串**，数值档一律返回 False 且不落盘；
编码 `speed=1 / shape=2 / octree=3`。**OCT_MESH 段 6 键全部单变量定谳（6/6）**。

**R29 的「值 3 无变化」是无信息档**（3 本就是该键现值）——不是否证；由此立新口径（见下）。

### R30-3 根因修复：自家的目录里根本没有取值词表

R29 之所以只能猜取值（猜 `"octree"`/`"voxel"` 全错），因为 `schemas/vb_api_catalog.json`
**把手册的取值行当成了新参数**：手册把取值写成续行（首格为空、`cells[1] = "poly"`），
旧解析 `_push_arg(cells[1], cells[-1])` 于是产出 `{"type": "", "name": "\"poly\""}` ——
全库 **1205 条假参数、239 个方法**，词表在自家 schema 里不可见。

修 `tools/extract_vb_api_scflow.py`：续行按三型派发（**枚举行 / Note 行 / 参数续行**），
并补「无表头参数行」「整数枚举 `0 Initial calculation 1 Restart…`」两种行型。重新生成目录：

| 指标 | 修前 | 修后 |
|---|---|---|
| 假参数（name 带引号、type 空） | 1205 | **0** |
| 取值词表条目 | 0 | **1591**（340 个参数/返回值、321 个方法） |
| Note / 手册内交叉引用（`note_ref`） | 0 / 0 | **690 / 73** |

按实测接住的手册行型与笔误：3 格 / 4 格 / 5 格 / 同格多值（12 行）、全角引号 `”GVEL”`、
漏闭合引号 `"IRBN`。副产：`Conditions.GetFPHVariableOutput` 旧解析**丢了一整个参数**
（`(VARIANT)value` 无表头），现在参数与 `0/1/2` 取值齐全。

### R30-4 派生数据非幂等：连跑三次 79 → 80 → 81 → 82

R30 复算 `schemas/merged.json` 时撞见：`python tools/_p12c_cond_harvest.py merge` **每跑一次
就把 CondSource 计数 +1**（实测 79→80→81→82）。根因两条：

1. `schema_extract.extend_merged_schema` 是**累加**语义（`target["count"] += …`）；
2. 收割 merge 的载荷是「**所有**不在基线 pph 里的类型」，而不是「本次新发现的类型」——
   哨兵条件 `alias_evidence` 永不为空（`CondFan/CondFix/Spray` 三个别名类型没有 universe 落点），
   于是每次运行都把**已入库**的类型再喂一遍。

修法（`_p12c_cond_harvest.merge`）：载荷收敛为 `to_add = [k for k in htypes
if k not in base_types and k not in have_before]`，并且只在 `to_add` 非空时写盘。
实测：连跑两次**字节相同**、`to_add == []`。

**连带暴露的真红灯（与本次修复无关，是 HEAD 上既有的）**：`p12h_registry_report.json`
（R8 冻结快照）是用**当时工作树里被膨胀过一次**的 merged.json 生成的（9/60/80），
而已提交的 merged.json 是未膨胀值（8/59/79）——**干净检出跑 `test_p12h_reconcile`
必红**，之前没红只是因为工作树恰好「多跑了一次 merge」对上了。同类问题还有一处：
该测试写死 wizard 审结计数 25/1/1，而**已提交的** `p12h_wizard_report.json` 只有 1 族。

处置（口径：**快照必须能从已提交输入复算**）：

* 用已提交输入重生成 `p12h_registry_report.json` + `schemas/cond_types.json`（v8 → v9，
  仅 3 条 evidence 计数 60/80/9 → 59/79/8 与 version 变化）；
* `test_wizard_batch_verdicts_recorded` 的写死计数 → **契约断言**（审结覆盖全部输入族、
  取值在允许集内）——沿 R0「陈旧字面量断言改契约断言」口径；
* 新增 `tests/test_cond_harvest_merge_r304.py`：双跑字节相同 / `to_add` 为空 /
  `merge(merged_path=…)` 不得碰仓库里的 merged.json。

---

### R30-5 提交纪律的 1 MB 上限：权威目录被静默跳过

`git_milestone.py --dry-run` 的「跳过」清单里出现了 `schemas/vb_api_catalog.json
(2139148 B > 1 MB)` —— 一查更严重：**该文件在 HEAD 上就已经是 1,979,841 B**，
最后一次入库是 **2026-08-20（`0cecf53`, P9）**。也就是说此后每一轮重新提取的
目录**都没有进仓库**，仓库里的 API 面一直比实际提取结果旧。

修法：体量上限按路径区分 —— `schemas/*.json`（权威 schema）与 `docs/*.md`（文档）
放宽到 **8 MB**，其余路径维持 1 MB（防止误收大运行产物）。新增
`tests/test_git_milestone_size_r305.py` 钉住这条口径（含「目录当前体量必须在其上限内」的不变量）。

**同一个坑有三处，改第一处时又踩了第二处**（如实记录）：

1. `candidates()` 的收录筛 —— 已在 `--dry-run` 清单里可见（"跳过"段）；
2. `main()` 暂存后的**二次**体积筛（`bad = [… > MAX_BYTES]`，硬编码常量）——
   第一版修复只改了 (1)，于是 `git add` 进来的 2.14 MB 目录**又被 `git reset` 剔除**：
   提交打印成功、推送成功，**目录根本没进仓库**（第二次提交才发现）；
   现统一走 `bad_staged()` 帮手，且删除路径（文件已不存在）不再被误判；
3. `candidates()` 的 `if not p.is_file(): continue` 把**删除**整个丢掉 ——
   `tools/_r17_dual_ours.py` 这种「升格为正式工具后清理的一次性脚本」（R18-1 决议）
   因此永远提交不掉；现已支持 `D` 状态并 `git add` 暂存删除。

工具现在会打印「收录 N 个文件，**删除 M 个**」，dry-run 与实际暂存集一致。

---

### ★ 口径（本轮新增两条）

> **同值档不算证据**：setter 被设成「恰好是该键现值」时 xenv 自然不动，既不能证明也不能否证；
> 逐档探针必须**至少包含一个与现值不同的取值**（R29 对值 3 的「无变化」正是踩了这条）。

> **词表双源**：API 取值必须「**手册取值表** + **宿主 getter 读回**」两处对齐。手册会漏值 ——
> `GetVoxelOctRefineType` 只列 `shape`/`speed`，而宿主实测还有 `octree`（且是默认值）。

### 回归

全量回归 **1246 passed / 4 skipped / 0 failed**（563.49 s，含 R30-1/2/3 的 26 项与 R30-4 的 3 项）。
此后才落地的 R30-5（`tools/git_milestone.py` 三处修复 + `tests/test_git_milestone_size_r305.py`）
**单独复跑 8 passed** —— `git_milestone` 在全仓只有该测试引用（`Select-String` 实测），
且改后 `--dry-run` 跳过清单清零、收录/删除集与实际暂存集一致。
口径合计 **1254 passed / 4 skipped / 0 failed**。

新增测试：`tests/test_xenv_setter_probe_r301.py`（档位解析 / VBS 取值引号 / 每档只改一个 setter /
逐档存档 / 增量 diff）与 `tests/test_api_catalog_values_r303.py`（取值格 4 类 / 行型派发 4 例 /
目录不变量：假参数为零、取值 ≥1200、词表与 `note_ref` 逐条核对）。

### 证据

`_p12u_gate/r30/summary.json`（5 档）、`_p12u_gate/r30/summary2.json`（4 档）、
`_p12u_gate/r30_voxel*/step*.pph`（逐档存档，可直接复算增量）、`_p12u_gate/r30/verify_catalog.py`（目录计数复算）。

派生数据说明：`schemas/merged.json` 的 `CondSource` 79→80 来自**上一会话**的收割产物；
本轮以离线 `tools/_p12c_cond_harvest.py merge` 复跑，确认当前文件是该收割的**不动点**（再跑不产生新变更）。

### 宿主键进度

累计 **19 条**（R28 的 13 → R29 +5 = 18 → R30 +1 = **19**），其中 **OCT_MESH 段 6/6**
全部按单变量逐档法定谳（`FACET_LENGTH_FACTOR`/`FACET_ANGLE`/`FACET_MAX_WIDTH_FACTOR`/
`FACET_SPECIFY_EACH_REGION`/`COMPLETE_PARALLEL`/`VOXEL_OCT_REFINE_TYPE`）。

---

## R31 —— 实测键回流面板 + 描述即词表 + 取值三态校验 + 一致性护栏（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R31-1** | **实测键回流面板** | 面板改一项 → 对应 xenv 键变化：离线比对 + 实机回读一致 | ✅ 离线 10 项测试 + **实机 4/4 回读命中**（29/29 err=0） |
| **R31-2** | **描述内嵌取值行型** | 目录取值 +≥20，且不产生新假参数 | ✅ **+166 条取值**（1591 → 1757），假参数仍为 0 |
| **R31-3** | **取值表暴露给 typed 桥** | 桥接层能对给定方法返回取值集合 | ✅ `api_values`/`api_value_set`/**三态** `check_api_value` |
| **R31-4** | **快照 / 收录一致性护栏** | 人为改计数或让已跟踪文件超限均须变红 | ✅ 3 条护栏；拿修复前的提交对实测**报出 3 处不一致**（非空转） |

### R31-1 实测键回流：提案前提**有误**，已按实测改正

提案写的是「OCT_MESH 6 键里只有 2 条接进面板」。实际读码：`MesherFaceterBody`
**已经写了 5 条**（`FACET_ANGLE`/`FACET_LENGTH_FACTOR`/`FACET_MAX_WIDTH_FACTOR`/
`FACET_SPECIFY_EACH_REGION`/`COMPLETE_PARALLEL`），真正缺的只有 R30 才定谳的第 6 条
`VOXEL_OCT_REFINE_TYPE`。本轮把它补齐，并顺带解决一个**编码翻译**问题：

* 读：`VOXEL_OCT_REFINE_TYPE`（整数码）→ `pphxml.voxel_oct_refine_name` → 下拉框枚举名；
* 写：枚举名 → `pphxml.voxel_oct_refine_code` → 整数码，**未知取值不落盘**
  （宿主实测只认三个枚举名，大小写错/数值档都返回 False）。

映射表落 `pphxml.VOXEL_OCT_REFINE_TYPES`（`speed=1 / shape=2 / octree=3`，来自 R30 实测）。

**实机闭环**（`tools/xenv_host_write_check.py` 新增 `WRITES_MORE`：非 FACET 段、写入码 / 回读名
分列两栏）：写 `OCT_MESH.VOXEL_OCT_REFINE_TYPE=2` → 宿主 `GetVoxelOctRefineType` 回读
**"shape"**，`hits=4/4`、`29/29 err=0`、SNode/MDL/OCT 全在场（51.5 s）。

### R31-2 「描述即词表」：+166 条取值

手册有两种把取值塞进**描述格**的写法（R30 只处理了「整格是取值」）：

```
Type of connection (string)["default" (default), "connect" (connect), "disconnect" (disconnect)]
License mode "hpc" : HPC edition "lt" : LT edition
```

判定条件按实测标定：**第一个引号之前必须出现类型标记**（`(string)`/`(BSTR)`/`(VARIANT)`）
**或 label 词**（mode/type/edition/…）。实测 234 行里 **116 行**是词表、**118 行**是散文或格式提示
（`Use "cycle_interval" to get cycle interval`、`Color (string "0xAABBGGRR")`）——后者被规则挡住。

| 指标 | R30 | R31 |
|---|---|---|
| 取值总数 | 1519 | **1757**（桥接口径 1738） |
| 带取值的参数/返回值 | 340 | **410** |
| 假参数（name 带引号、type 空） | 0 | **0** |

### R31-3 typed 桥的取值 API（三态，不是硬白名单）

`automation/scflowpre_api.py`：`load_catalog`（进程内缓存）/ `api_values(cls, member, arg)`
（`arg=None` 取首个有词表的参数、`"return"` 取返回值）/ `api_value_set` /
`check_api_value` → **True / False / None**。

> ★ **口径**：`None`（手册无词表）与 `False`（有词表但取值不在内）**必须分开** ——
> 手册有漏项（`octree` 即漏项），把「没词表」当「非法」会误杀宿主合法取值。

### R31-4 一致性护栏（两条事故各钉一条）

`tests/test_snapshot_guards_r314.py`：

1. **收录不得静默丢件**（R30-5）：`git_milestone.candidates()` 的「跳过」清单与
   `git ls-files` **交集必须为空**；`schemas/*.json` 必须在放宽后的上限内且不被
   `bad_staged` 剔除；
2. **快照 / 账本 / 语料三者计数一致**（R30-4）：`cond_types.json` 的 dispositions ==
   报告 dispositions + 族注记；报告每条 `registry_key` 证据里的「官方案例库实样 N 例」
   == `merged.json` 里该类型的 `count`（受检 ≥80 类，防护栏空转）。

**护栏非空转的证据**：把同一段比较逻辑拿去跑**修复前的提交对**（`dd4e278` 的 R8 快照
vs 同提交的 `merged.json`）→ 报出 **3 处不一致**（CondPorousMedia 60/59、CondSource 80/79、
CondSourceMass 9/8）；当前工作树 0 处。

### 回归

全量回归 **1286 passed / 4 skipped / 0 failed**（553.46 s；R30 收口时同口径为 1246，
增量 = R30-5 的 8 + 本轮 4 个新模块 32，逐项对得上）。
新增测试 4 个模块：`test_voxel_oct_refine_r311.py`（10）、`test_api_desc_values_r312.py`（10）、
`test_api_values_r313.py`（8）、`test_snapshot_guards_r314.py`（4）；并强化
`test_facet_host_keys_r85.py` 的契约（非 FACET 段实测键一并纳入）。

### 证据

`_p12u_gate/r31_1_write.json`（实机回读：写码 2 → 回读 shape，hits 4/4、29/29 err=0）、
`_p12u_gate/r31/rule_probe.py`（描述即词表规则标定 116/118）、
`_p12u_gate/r31/guard_mutation_check.py`（护栏在修复前提交对上报 3 处不一致）。

---

## R32 —— 实测键账本 + 词表驱动控件 + 手册变体归一（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R32-1** | **实测键 → 面板写入口对账** | 每条键有「写入口 / 无写入口」结论，缺口列成待办 | ✅ 账本 **18 条**（**更正旧口径「19」**）、17 条有写入口、1 条显式缺口；**单会话 18 档重核全中** |
| **R32-2** | **下拉框由词表驱动** | 目录新增取值即出现在控件里，且有测试 | ✅ 标签取自目录、可写白名单取自实测编码表（两层分工） |
| **R32-3** | **拒行分类 + 手册变体归一** | 分类表落盘；捞回的取值不产生假参数 | ✅ 拒行分类落盘；**表头归一多捞回 1942 条返回值**；取值 **1757 → 1801**，假参数/格式提示均 0 |

### R32-1 建账：先把「19 条」这个数改对

提案说「19 条键」——建账第一天就发现**这个数不对**。把文档里所有 `SECTION.KEY` 抓出来
逐条回溯证据，可复算的是 **18 条**（FACET 12 + OCT_MESH 6）：

| 轮次 | 新增键数 | 证据 |
|---|---|---|
| R6-5 | 4 | `_p12u_gate/r6_5_keys.json` + 审计 §21.1 |
| R10-3 | 3 | `_p12u_gate/r10_3_keys.json` |
| R26 | 2 | `_p12u_gate/r26_1_keys.json` |
| R27 | 3 | `_p12u_gate/r27_1_keys.json` |
| R29 | 5 | `_p12u_gate/r29/summary.json` |
| R30 | 1 | `_p12u_gate/r30/summary.json` |

**多出来的那 1 条是 R6-5 的 `SetFacetUseAbsoluteValue`** —— 审计 §21.1 原文就写着
「（未变化）/ 未证实」，但同段又说「实测 5 条」，此后每轮在这个基数上加，一路把
8/10/13/18/19 全部抬高了 1。**账本 `schemas/host_keys.json` 从此是唯一口径**。

**单会话重核**（`tools/xenv_setter_probe.py`，18 档、256/256 err=0、71.3 s）：
每一档的 `delta_vs_prev` **恰好**是账本里那一把键（多一把少一把都判失败）。
getter 名不靠猜：由目录里 `Set<X>` → `Get<X>` 自动配对（唯一缺 getter 的正是下一条）。

**新发现：宿主实有、手册全无的 setter** —— `SetIntersectionDetectionDepth`
（返回 True、增量恰为 `FACET.INTERSECTION_DETECTION_DEPTH`），但目录 199 类与全库 HTML
**都没有** `IntersectionDetection` 字样。这是 R30「手册是子集」的**反向**版本：
不止取值会漏，**成员也会漏** → 反向取证（实机）不可省。

**写入口对账**（`tools/host_key_coverage.py`，执行各面板 `apply()` 后读 xenv，不扫源码猜）：

* 18 条里 **17 条**有写入口（全部经 `MesherFaceterBody`）；
* 本轮**补上缺的那一条** `FACET.USE_DETAIL_MAX_WIDTH`（R6-5 实测键，此前根本没有控件）
  → 新增勾选框 + `apply` 落盘 + 与最大边长框联动；
* 剩 **1 条显式缺口** `FACET.INTERSECTION_DETECTION_DEPTH`（面板无对应概念），
  记在账本 `known_gaps` + 理由，**缺口必须显式声明**（新增缺口不许静默）。

### R32-2 控件由词表驱动（两层分工）

`_voxel_refine_items()`：**可写白名单** = 实测编码表（`speed=1/shape=2/octree=3`），
**标签** = 目录词表描述。于是「目录新增**有实测码**的取值」自动出现在控件里；
「目录有值但没实测码」不进控件（写不出去，列出来只会让用户选到无效项）。
目录读不到时回落标签，GUI 不因 schema 缺失而不可用。

### R32-3 拒行分类 + 手册变体归一（最大的收获不在计划内）

**拒行分类**（118 行）：格式提示 88、Note 段落 16、带 2+ 取值 10、单取值 4。
新增两条**窄**规则把真词表捞回：

* 描述里**任何位置**出现完整类型标记 + **≥2** 个取值
  （`Direction of region (string) If … "positive_side" … "negative_side" …`）；
* 括号内逗号分隔列表（含全角变体 `（"summary", "detail", "solverComand"）`）。

第一版放宽**过宽**：混进 63 条颜色占位 `"0xAABBGGRR"`（`Doc.AddTemporaryDrawingObject*`）
→ 加格式提示过滤；又发现 Note 段落污染 `Doc.SewSheets`（`"not in part mode,"` 被当取值）
→ Note 一律判散文。收口后：取值 **1757 → 1801**（+44），格式提示 **0**、假参数 **0**。

**计划外的发现（本轮最大一笔）**：手册表头有**大小写/拼写/日文变体**，而解析器只认
`[Return Value]`（大写 V）。实测分布：

| 表头 | 行数 |
|---|---|
| `[Return Value]` | 4617 |
| **`[Return value]`** | **4280** |
| `[Arguments]` / `[Return]` | 50 / 50 |
| `[Argiment]` `[Resturn Value]` `[Return Value]]` `[Explnation]` `[Explanetion]` `[xplanation]` | 各 2 |
| `[引数]` `[戻り値]` `[戻り値/Return value]` | 2 / 2 / 4 |

→ **近一半方法的返回值（1942 条）此前被静默丢弃**（连同其取值词表）。
表头归一后：**+1942 条 return、0 条丢失**；目录现值 4455 条目 / **4177 有 return** /
5604 参数 / 1801 取值。

**过程中自己踩了一个坑并被护栏拦住**：`_head_kind` 的参数正则写成 `argi`（为了兼容
错拼 `[Argiment]`），结果把正常拼写 `[Argument]` 整类漏掉 —— 表现为取值从参数上
「消失」（挪到条目级）。是 R32-3 的护栏（`Conditions.GetAnalysisType` 的 30 条取值
必须挂在参数 `type` 上）把它抓出来的；修正是把 `argu` 加回正则。

**遗留（不猜）**：手册笔误留下两个取值 `"'protectd1"` / `"'orthogonality"`
（引号内多一个单引号）—— 只在账上显式声明为「待实机确认」，见 R33-1。

### 回归

全量回归 **1318 passed / 4 skipped / 0 failed**（550.82 s；R31 收口同口径 1286，增量 +32）。
新增测试 3 个模块：`test_host_key_coverage_r321.py`（10）、
`test_voxel_refine_combo_r322.py`（6）、`test_manual_variants_r323.py`（14）；
并按 R32-3 口径更新 `test_api_desc_values_r312.py` 的两个反例（Note 文本取代
「Use "cycle_interval" …」——后者经复核**是**词表）。

### 证据

`_p12u_gate/r32/keys_reverify.json`（单会话 18 档重核，256/256 err=0）、
`_p12u_gate/r32/coverage.json`（写入口对账）、`_p12u_gate/r32/rejected_rows.json`（拒行分类）、
`_p12u_gate/r32/audit_value_shape.py`（取值形状体检：1817 取值里 2 条手册笔误、其余全为标识符样）。

---

## R33 —— 手册词表三路对拍 + 取值守卫入派发路径 + 缺口终态（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R33-1** | **手册笔误取值定谳** | 两个取值有实测结论，账本更新 | ✅ 宿主 XML 定谳（755 / 151 处），提取期修正 + 保留 `manual_value` |
| **R33-2** | **取值校验入写回路径** | 非法取值被拦下且有测试；`None` 不误杀 | ✅ typed 桥派发前校验（默认告警 / `strict` 抛错），**17 个类自动接线** |
| **R33-3** | **词表对拍（手册 vs 宿主）** | ≥1 组差异入库或全部一致 | ✅ 语料对拍 **2 组全一致** + 实机 **3 组全一致**；发现并入库 **1 条手册漏项 `elem_volume`** |
| **R33-4** | **写入口缺口收口** | 该键有终态（不是"待办"） | ✅ `no-panel-surface` 终态（`terminal: true` + 理由 + 轮次） |

### R33-1 笔误定谳：拿**宿主自己写出的** main.xml 当判据

R32-3 留下的两个可疑取值（`"'protectd1"` / `"'orthogonality"`，引号内多一个单引号）没有靠猜，
而是扫官方算例库 **151 个工程**的 `main.xml`：

```xml
<stability_type><name>protectd1</name>…          <!-- 755 处 -->
<stabilitygeom_type><name>orthogonality</name>…  <!-- 151 处 -->
```

→ 手册是笔误，真值就是 `protectd1` / `orthogonality`。提取期修正（`_VALUE_FIXES`），
并把手册原文保留在 `manual_value` 字段（回溯「手册原文如此」）。修正后取值形状体检
**0 条可疑**（此前 2 条）。

### R33-3 三路对拍：语料 2 组 + 实机 3 组

**语料对拍**（新工具 `tools/api_value_corpus_diff.py`：语料 = 宿主写出的
`<xxx_type><name>VALUE</name>`，取值容器即"宿主承认的取值"）：

| 容器 ↔ 目录成员 | 手册 | 语料 | 结论 |
|---|---|---|---|
| `stability_type` ↔ `GetPresetStabilityParam.param` | 2 | 2 | **完全一致** |
| `stabilitygeom_type` ↔ `GetPresetStabilityParamGeom.param` | 4 | **5** | **手册漏项 `elem_volume`** → 已按语料入库（`source: host-corpus`） |

入库后复跑：两组都 `agree=True`，语料独有 **0** 条。

**实机对拍**（`tools/xenv_setter_probe.py`，单会话 8 档、120/120 err=0）：
`ChangeMesher`(`poly`/`oct`)、`ChangeSurfMesher`(`facet_base`/`solid_base`)、
`SetVoxelOctRefineType`(`shape`/`speed`) —— 手册取值**全部被宿主接受**且 getter 回读同值；
两个臆造取值 `polyhedral`/`facet` **全部被拒**（返回 False、getter 不动）。

> 附一条口径实证：`ChangeSurfMesher("facet_base")` 的 xenv 增量是 **空**（该档恰好等于现值）
> —— 正是 R30 定的「同值档不算证据」；判据要看 setter 返回值 + getter 回读，不能只看 diff。

### R33-2 取值守卫接进 typed 桥的**派发路径**

`ComObject._check_values`：派发前按目录词表校验位置参数里的**字符串**取值，三态：

* `True` → 放行（静默）；
* `False` → **默认只记 `value_warnings`，照常派发**；`strict_values=True` 才抛 `ApiValueError`
  且**在派发之前**拦下；
* `None`（手册无词表）→ 完全不管。

为什么默认不拦：手册是**子集**（R30 实测宿主还认 `octree`），把"不在词表"当"非法"会误杀合法取值。
类名接线走既有 `TYPED_CLASSES` 注册表（`wire_api_classes()` → **17 个类**），零 import 成本
（不读 2 MB 目录，只在真校验时懒加载）。

### R33-4 缺口终态

`schemas/host_keys.json` 的 `known_gaps` 条目升级为带终态的 `known_gap_status`：
`FACET.INTERSECTION_DETECTION_DEPTH` = `no-panel-surface`（`terminal: true`，理由 + 轮次），
即**永不加控件**，只保留可写通道。测试要求「缺口 ↔ 终态一一对应且都有理由」——
缺口不许停在"待办"。

### 回归

全量回归 **1338 passed / 4 skipped / 0 failed**（560.57 s；R32 收口同口径 1318，
增量 +20 = 本轮两个新模块 8 + 12，逐项对得上）。
新增测试 2 个模块：`test_api_value_guard_r332.py`（8）、
`test_corpus_value_evidence_r333.py`（12）；并按 R33-1 口径更新
`test_manual_variants_r323.py` 的笔误断言（从"未决遗留"改为"已修正"）。

### 证据

`_p12u_gate/r33/corpus_diff.json`（151 工程语料对拍，2 组全一致、语料独有 0）、
`_p12u_gate/r33/enum_probe.json`（实机 8 档 120/120 err=0，手册取值全接受 / 臆造全拒）、
`schemas/host_keys.json`（缺口终态）。

---

## R34 —— 语料对拍扩面 + VBS 通道取值校验 + 桥接落差账（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R34-1** | **语料对拍扩面** | ≥5 组有结论；新差异入库或无差异 | ✅ 容器 **333 种**、名字同源链接 **36 组**（差异 **12 条**全部入库 → `auto_with_gap=0`）、仅重叠提示 **23 组** |
| **R34-2** | **VBS 通道取值校验** | 非法取值在生成期即告警/拦下 | ✅ `build_vbs` 唯一生成口校验；**`note_ref` 回退补上第一版漏洞** |
| **R34-3** | **目录 ↔ 桥接落差账** | 有逐类账目；缺口清单进 R35 | ✅ 17 类 / 目录 1766 成员 / 已包装 **372（21.1%）**；两条不变量 + 41 处标题≠签名入册 |

### R34-1 语料对拍扩面：333 个容器、36 组链接、12 条漏项

R33-3 只覆盖 2 个容器（`stability*`）。本轮把语料里**两种取值写法**全收
（`<X><name>V</name>` 与 `<X_type>V</X_type>`）→ **333 个容器**，再用
「取值集交叉」自动找链接。

**但交叉只能找候选**：实测 `loop_eq_param` 与 `equa_start_param` **都会**"匹配"到
`Conditions.GetUpwdParam`（同名取值挂在不同设置上）。故入库多加一条门槛 ——
**容器名与成员名必须同源**（`connection_type` ↔ `GetConnectionType`）。分桶结果：

| 桶 | 组数 | 处置 |
|---|---|---|
| 名字同源（可入库） | 36 | 差异 12 条已入库；入库后差集归零（`auto_with_gap=0`） |
| 仅取值重叠（只提示） | 23 | **不入库**，只作提示（测试钉住"不得并进它匹配到的那个槽"） |

12 条入库漏项（`source: host-corpus`）：`battery`/`clear`/`infinite_elements`
（`GetBoundaryType`）、`not_connect`（`GetConnectionType`，手册另写 `disconnect`）、
`glue`（`GetContactType`）、`none`（`GetConversionType`）、`CAVI`/`CMBV`/`CONC_VAPOR`
（`GetNextParam`）、`saturated_humidity`（`GetOutsideType`）、`surface`
（`GetProjectionType`）、`eq_comb`（`GetSolvParam`）。

### R34-2 VBS 通道：第二版才守住

`build_vbs` 是 VBS 的唯一生成口，在那里校验「**字面量紧跟方法名**」的形态
（那必然是第一个实参；路径/说明等行内字符串一律跳过）。

**第一版有个静默漏洞**：setter 自己往往没有词表（取值挂在对应 getter 上，
R30 实测 `SetVoxelOctRefineType` 即此）—— 不跟进 `note_ref` 就**整类放过**。
补上回退后：`SetVoxelOctRefineType "speed"` 通过、`"voxel"` 告警；
`ChangeMesher "polyhedral"` 告警；`strict_values=True` 在**生成阶段**抛 `ApiValueError`
（早于任何宿主会话）。同一修复也回灌到 typed 桥与 `check_api_value`（三条路径同一口径）。

### R34-3 落差账与两条不变量

| 类 | 已包装 / 目录成员 | 覆盖率 |
|---|---|---|
| Conditions | 7 / 607 | **1.2%** |
| Doc | 60 / 426 | 14.1% |
| MeshingGroup | 23 / 175 | 13.1% |
| SNode | 48 / 145 | 33.1% |
| MeshingGroupSetting | 28 / 104 | 26.9% |
| WrappingGroup / NumericalRegion / SubmeshSurfaceRegion | 30/30 · 20/20 · 19/19 | **100%** |
| **合计** | **372 / 1766** | **21.1%** |

两条不变量：

1. **包装方法必须能在目录里找到**（自研便捷方法 `create_cond`/`query_cond`/`check`
   按命名规则排除）——否则就是调了手册外成员，须像 `SetIntersectionDetectionDepth` 显式登记；
2. **手册 h3 标题名 ≠ 签名名 的 41 处必须把真名记进 `signature_name`**：实测
   `Doc.CreateDiscontinuousMeshingGroupWitouthMovingPart`（标题）vs
   `…WithoutMovingPart`（签名）、`ClosedVolume.SelectFace` vs `SetSelectFaces`、
   `CondBladeShape.EditChordLength` vs `EditChoordLength` 等。包装类按**签名**写，
   不记这条就会在"目录里找不到"（本项第一版就是这么误报的）。

### 回归

全量回归 **1363 passed / 4 skipped / 0 failed**（554.58 s；R33 收口同口径 1338，
增量 +25 = 本轮三个新模块 7 + 10 + 8）。
新增测试 3 个模块：`test_corpus_autolink_r341.py`（7）、
`test_vbs_value_guard_r342.py`（10）、`test_bridge_coverage_r343.py`（8）；
并按 R34-1 口径更新 `test_api_desc_values_r312.py` 的 connection_type 断言
（手册三条 + 语料补的 `not_connect`，带 `source`）。

### 证据

`_p12u_gate/r34/corpus_diff_auto.json`（333 容器 / 36 同源链接 / 23 仅重叠）、
`_p12u_gate/r34/bridge_coverage.json`（逐类落差账 + 41 处标题≠签名）。

---

## R35 —— 名字实机裁定 + 归因入库 + 目录物化（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R35-1** | **宿主真实成员名裁定** | ≥1 个类落盘；41 处分歧给出裁定 | ✅ 实机裁定 **20/41**（**both 13 / heading 4 / signature 3**），裁定表入册 `schemas/name_verdicts.json` |
| **R35-2** | **仅重叠候选归因** | 每条有结论；真对应的补链接 | ✅ 8 条按词干归因，**3 条精确同源 → 16 条取值入库**；5 条仅"包含"关系只提示 |
| **R35-3** | **落差账驱动补面** | 覆盖率 21.1% → ≥25% | ✅ 目录物化 → **1759/1766 = 99.6%**（属性名=目录键、派发名=裁定名优先） |

### R35-1 名字裁定：`GetTypeInfo` 走不通，改用 `GetIDsOfNames`

**离线路线先被排除**：scFLOWpre 的 COM 服务器**没有注册类型库**
（`HKCR\\CLSID\\{6FDA4768-…}\\TypeLib` 不存在；二进制也 `LoadTypeLib` 不出来），
运行时 `GetTypeInfo` 同样 `com_error`（7 个对象实测全 `no:com_error`）。

于是改用 **`IDispatch::GetIDsOfNames`** —— 它**只做名字解析、不调用任何方法**，零副作用：

| 裁定 | 对数 | 含义 |
|---|---|---|
| `both` | **13** | 两个名字宿主都认（互为别名） |
| `heading` | **4** | 只有**手册标题名**能解析（签名写错了） |
| `signature` | **3** | 只有**签名名**能解析（标题拼错） |
| 未裁定 | 21 | `Cond*` 类需要条件对象实例，本轮未构建 |

两条典型：`Doc.CreateDiscontinuousMeshingGroupWitouthMovingPart` → **签名胜**
（`…WithoutMovingPart`，印证 R34-3 的假设）；`Conditions.SetContactThicknessDefault`
→ **标题胜**（签名 `SetContactTicknessDefault` 是手册自己的拼写错）。
**所以"一律用签名名"也是错的** —— 裁定优先、签名次之、目录键兜底。

**过程中踩了两个坑**（都记进代码注释）：① 未打开工程就 `GetConditions` 抛
`DISP_E_MEMBERNOTFOUND`，把后面所有实例构建全挡掉；② 裸 `CDispatch` 链式调用会被
win32com 当属性读，`QueryMeshingGroupByIndex(0)` 抛 `TypeError: 'bool' object is not
callable` —— 必须走仓内 typed 包装（内部 `_FlagAsMethod` 派发）。

### R35-2 归因：词干同源才入库

23 条「仅取值重叠」候选里，按**词干**（去 `Get/Set` 与 `type/param` 后缀）找真成员：
**8 条找到**，其中 **3 条精确同源**（`region_type`↔`GetRegionType`、
`variable_type`↔`GetVariableType`、`transfer_type`↔`GetTransferType`）→ **16 条取值入库**；
另 5 条只是"包含"关系（`upwd_param` → `GetUpwdOptionParamForEquation`）**不入库**，
留作提示（测试钉住"不得并进它匹配到的那个槽"）。

### R35-3 目录物化：21.1% → 99.6%

`materialize_catalog_wrappers()` 把目录里**尚未手写**的成员物化成包装方法：
**属性名 = 目录键**（与目录对账一致，`test_scflowpre_api` 的名字断言才成立）、
**派发名 = 裁定名 → 签名名 → 目录键**。意义不在"多写几行"，而在
**取值校验覆盖到每个手册成员**（物化方法走同一个 `call()` → `_check_values`）。
手写包装不被覆盖（保住其文档与语义）。

### 回归

全量回归 **1377 passed / 4 skipped / 0 failed**（557.45 s；R34 收口同口径 1363，
增量 +14 = 本轮新模块 14，逐项对得上）。
新增测试 1 个模块：`test_r35_evidence.py`（14）；并把 R34 的
`test_bridge_coverage_r343.py` 证据断言从"等于快照"改为**单调不变量**（覆盖率只增不减）。

### 证据

`_p12u_gate/r35/name_verdicts.json`（20 对裁定 + 7 对象 `GetTypeInfo` 全否）、
`schemas/name_verdicts.json`（紧凑裁定表，typed 桥据此选派发名）、
`_p12u_gate/r35/corpus_diff_attr.json`（36 同源 + 8 归因 + 23 仅重叠）、
`_p12u_gate/r35/bridge_coverage.json`（物化后 1759/1766）。

---

## R36 —— 名字裁定补齐 + 仅包含关系归因 + 属性物化（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R36-1** | **`Cond*` 类名字裁定** | 裁定覆盖 41/41 | ⚠️ **31/41**（+11）：**both 21 / heading 6 / signature 4**；余 10 需**链式实例**（如实记为未裁定） |
| **R36-2** | **仅包含关系候选归因** | 每条有结论 | ✅ `upwd_param` 经**取值词汇唯一性**归因 → 4 条入库，链接收敛（12 = 12） |
| **R36-3** | **属性物化** | typed 类可读属性名一致；有测试 | ✅ 16 条目录属性物化成 Python property（get→`prop()`、set→`set_prop()`） |

### R36-1 实例构造：把「无实例」从 21 压到 10

`_obtain()` 按名字家族逐个试：`Cond*` → `conditions.CreateCond*/QueryCond*ByName`，
其余 → `Get*/GetPreset*`。新拿到 **9 个类**（`obtained_via` 落盘）：
CondActranBoundaryNonReflection / CondBladeShape / CondBoundaryFlowIO /
CondInitialShapeModify / CondOutputCSV / CondOutputLFileTurbo / CondOutputTimeSeries
（各 `CreateCond*`）、`HybridParam`（`GetHybridParam`）、`OctParam`（`GetOctParam`）。

**第三次踩同一个坑**：实例构建必须传 **typed 包装**——裸 `CDispatch` 的 `getattr` 会被
win32com 当属性读，第一版 `_obtain` 因此**静默全失败**（表现为裁定数不变）。已写进注释 + 单测。

新裁定的关键两条：`CondBladeShape.EditChordLength` **标题胜**（签名 `EditChoordLength` 是拼写错）、
`CondOutputLFileTurbo.ClearOutletBladeRegions` **签名胜**（标题多写了 Blade）。
裁定表**单调合并**（取不到实例的类保留上次结论）→ `schemas/name_verdicts.json` 现覆盖 16 类。

余 10 处需要**链式实例**（手册 `instance` 字段给了配方）：
`PropItem`（`PropDataBase.GetPropItem`）、`MapCond`/`CondMapForStructure`（`GetValue`）、
`ClosedVolume`（`GetCoordinatesSpecifiedPartLinkedToMesh`）、`SpecialRegion`（`QueryPropValueObj`）、
`CondCoSimRegion`（`GetOwner`）、`CondCoSim`、`CondBoussinesqBaseTemp`（须先建同名条件再按名查）。

### R36-2 归因：取值词汇唯一性

`upwd_param` 的语料 12 条**全是 `eq_*` 形状**，而全库只有
`Conditions.GetUpwdOptionParamForEquation.eq` 是 `eq_*` 词汇
（名字相近的 `GetUpwdParam.key` 是 `MOM/ENERGY/TURB` 大写码）→ 认定为同一族，
补 4 条（`eq_comb`/`eq_dsol_cont`/`eq_dsol_e`/`eq_dsol_mom`）→ 复跑对拍
`一致=True（12 = 12）`。目录 addenda 累计 **33** 条。

### R36-3 属性物化

目录共 **16 条属性**（`Application.Visible(BOOL)` 等），全部物化成 Python property：
**属性名取括号前那段**（宿主认的名字），读经 `prop()`、写经 `set_prop()`，已存在者不覆盖。

### 回归

全量回归 **1392 passed / 4 skipped / 0 failed**（546.84 s；R35 收口同口径 1377，
增量 +15 = 本轮新模块 15，逐项对得上）。首轮跑出 1 条红是 R35 的
`test_loose_stem_links_are_not_merged`：R36-2 给「仅包含关系」补了额外判据后确实并了值，
该断言按新口径改写为「要么不在库、要么带 `host-corpus` 溯源（不得静默并入）」。
新增测试 1 个模块：`test_r36_evidence.py`（15）。

### 证据

`_p12u_gate/r36/name_verdicts.json`（31 裁定 + `obtained_via` 9 类 + 10 未裁定）、
`schemas/name_verdicts.json`（16 类裁定表）、
`_p12u_gate/r36/corpus_diff_attr.json`（`upwd_param` 收敛）。

---

## R37 —— 链式实例裁定 + VBS 纠名 + 参数个数校验（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R37-1** | **链式实例补裁定** | 覆盖 41/41，或每条未覆盖给出确切原因 | ⚠️ **32/41**（+1：`SpecialRegion`）；余 **9 条逐一给出确切原因**（`chain_errors` 落盘） |
| **R37-2** | **VBS 通道按裁定表纠名** | 生成期指出/纠正，有测试 | ✅ 4 处「签名胜」的目录键在生成期被点名「应改用 X」，`strict` 抛错 |
| **R37-3** | **参数个数校验** | 个数不符在派发前拦下/告警 | ✅ 按签名解析 arity（三种形态都覆盖），默认告警、`strict` 派发前拦下 |

### R37-1 链式实例：+1，其余 9 条给原因

`_chains()` 实现了手册 `instance` 字段里的链式配方：数组型 getter 取首元素、
多参数 `Create`、二级 `GetOwner`、`CondMapForStructure.GetValue` 等。
本机 `box.pph` 工程资源有限，**只有 `SpecialRegion` 拿到**
（`doc.GetSpecialRegions()[0]` → 裁定 `both`）。其余 9 条的原因（`chain_errors`）：

| 类 | 确切原因 |
|---|---|
| `ClosedVolume` | `doc.GetClosedVolumes(False/True)` **返回空** —— 该工程没有闭空间 |
| `CondCoSim` | `conds.CreateCondCoSim(name,0,0)` 返回空（CoSim 条件需要 co-simulation 配置） |
| `PropItem` | `CondInitial.GetPhaseMaterial()` 返回空 —— 工程未注册材料 |
| `CondBoussinesqBaseTemp` | 目录里**没有** `CreateCondBoussinesqBaseTemp`（只能按名查已有条件） |
| `CondCoSimRegion` / `MapCond` | **前置对象缺失**（`CondCoSim` / `CondMapForStructure` 未取到） |
| `CondMapForStructure` | `CreateCondMapForStructure` 抛错（同上：需映射条件前置） |

→ 结论明确：**这 9 条不是工序问题，而是"本机工程缺对象"**；换一个含闭空间/材料/
CoSim 的官方算例工程即可补 → R38-2。

**第四次踩坑（已入注释）**：`obtained_via` 里塞了 COM 对象 → `json.dumps` 抛
`TypeError: Object of type CDispatch is not JSON serializable`。证据结构必须只放可序列化值。

### R37-2 VBS 名字纠错

`vbs_bridge.name_corrections()` 从 `schemas/name_verdicts.json` 取「目录键 → 宿主接受名」，
`validate_actions` 扫描 `Obj.Method` 形态的方法名：命中即报
「X 在宿主上不存在（手册标题拼写），应改用 Y」。`build_vbs(strict_values=True)` 抛
`ApiValueError`。**这条堵住的是真实故障**：4 处「只有签名名能解析」的对，
生成器按目录键发出去必然失败（typed 桥已被物化包装兜住，VBS 直写没有）。

### R37-3 参数个数校验

`signature_arity()` 解析手册签名：`(path, flag)` → 2、`SetX flag` → 1、
`GetParam(key value)` → 2（空格分隔）、`GetMesher()` → 0、无签名 → None（不判）。
`_check_values` 在派发前比对个数：默认**只告警**（手册有可选参数，硬拦会误杀），
`strict_values=True` 才抛。

### 回归

全量回归 **1404 passed / 4 skipped / 0 failed**（550.35 s；R36 收口同口径 1392，
增量 +12 = 本轮新模块 12，逐项对得上）。arity 校验按默认"只告警"落地，全量回归无新增失败。
新增测试 1 个模块：`test_r37_evidence.py`（12）。

### 证据

`_p12u_gate/r37/name_verdicts.json`（32 裁定 + `chain_errors` 逐类原因）、
`schemas/name_verdicts.json`（17 类裁定表）。

---

## R38 —— 多工程裁定 + arity 口径 + 裁定名入目录（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R38-1** | **换工程补裁定** | 未裁定数 9 → ≤3 | ⚠️ **仍 9 条**（合并覆盖 32/41）——但换了性质：多工程能力落地、**修掉一个假否证**、9 条全部有兜底原因 |
| **R38-2** | **可选参数口径** | arity 不误报，真错仍告警 | ✅ 判据收紧为「**多则报、少不报**」（依据：全库 optional 标注仅 14 文件 41 处） |
| **R38-3** | **裁定表回灌目录** | 只读目录即可纠名 | ✅ 提取期写入 **32 条 `dispatch_name`**，VBS 纠名改读目录（表作回退） |

### R38-1 多工程单会话：换工程没换到对象，但换出了两个真问题

`--project` 可重复 → 一个宿主会话里轮换 `exA26-1_ldc`（CoSim）与
`exB01-1_intake_manifold`（闭空间标记最多）等工程，已取到的类不再重复取。
结果：合并覆盖仍是 **32/41**，未裁定仍是 **9 条**（6 个类）——
**换工程解决不了**：这些对象在"只打开工程"的状态下根本不存在。

两个真问题：

1. **假否证（第五次同族事故）**：`conds.GetCondCoSim()` / `GetCoSimRegions()` 返回的是
   **tuple**，未拆包就直接拿去 `GetIDsOfNames` → `AttributeError` → 探针把
   **能解析的名字判成 `neither`**。已修（`_raw` 拆 tuple）**并把口径分清**：
   解析过程本身报错 → 记 `unknown`（探针侧问题），只有"确实查无此名"才叫 `neither`（宿主事实）。
2. **兜底原因**：没拿到实例又没留下链式错误的类，补一条
   「各工程的 Get*/Create*/Query* 都未产出实例」——未裁定**不许静默**。

未裁定 9 条的确切原因（合并后）：`ClosedVolume`（`doc/MDL` 两条路都空 ——
闭空间要经 MDL 建模流程产生）、`PropItem`（`CondInitial.GetPhaseMaterial` 空：工程未注册材料）、
`CondBoussinesqBaseTemp`（目录**无** creator，只能查已有条件）、
`CondCoSimRegion`/`MapCond`/`CondMapForStructure`（前置对象缺失）。

### R38-2 arity 口径：多则报、少不报

手册对"可选参数"的标注**极稀疏**（全库仅 14 个文件 41 处，且多在本仓域外的
Post/Kicker 类），拿 `len(args) != expected` 判会把 `OpenProject(path)` 这类
"省略可选尾参"的正常调用报成错。故收紧为：**多传一定是错 → 报；少传交给宿主判**。

### R38-3 裁定名入目录

提取期新增 `_apply_name_verdicts()`：读 `schemas/name_verdicts.json`，
把 `dispatch_name` + `dispatch_source` 写进对应条目（**32 条**）。
`vbs_bridge.name_corrections()` 改为**先读目录**、表作回退 —— 只读目录的消费者
（含将来的代码生成）也能纠名。

### 回归

全量回归 **1414 passed / 4 skipped / 0 failed**（551.12 s；R37 收口同口径 1404，
增量 +10 = 本轮新模块 10，逐项对得上）。arity 口径收紧后无新增失败。
新增测试 1 个模块：`test_r38_evidence.py`（10）。

### 证据

`_p12u_gate/r38/name_verdicts.json`（多工程运行：31 裁定 + `projects` + 逐类原因）、
`_p12u_gate/r38/verdicts_closedvolume.json`（闭空间工程单跑）、
`schemas/name_verdicts.json`（合并表 17 类 / 32 条）、
`schemas/vb_api_catalog.json`（32 条 `dispatch_name`）。

---

## R39 —— 分歧总账 + 解析稳健化 + 契约门（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R39-1** | **未裁定 9 条收口** | 41 条全有终态，不留"待办" | ✅ 总账 `schemas/dispatch_account.json`：**41 = 32 裁定 + 9 NYI**，NYI 每条带**原因 + 配方** |
| **R39-2** | **`unknown` 稳解析** | 归零，或给出实证 | ✅ 递归拆包 + **对象形态诊断**；`CondCoSim` 那条实证为**探针侧限制**（实例已取到），总账如实标注 |
| **R39-3** | ~~optional 标记~~ → **契约门** | 一条命令查完不变量 | ✅ `tools/api_contract_check.py` 六项全 PASS（目录/账本/总账/桥接/语料/守卫） |

> 本轮把 R39-3 从「optional 标记提取」**换成「契约门」**：optional 标注全库只有
> 14 个文件 41 处、且多在本仓域外的 Post/Kicker 类，提取收益极低；而 R29–R39
> 散落了十几条不变量，缺一个"一条命令跑完"的入口。

### R39-1 总账：41 处全有终态

`tools/dispatch_account.py` 把三份来源合成一张表：目录（41 处分歧清单 + 类级
`instance` 配方）、裁定表（实机 `GetIDsOfNames`）、最近一次驱动证据（`chain_errors`
里的"为什么取不到"）。结果：

* **32 条已裁定**（记宿主真正接受的名字）；
* **9 条终态 NYI**，每条带原因与配方，例如
  `ClosedVolume.SelectFace` → 「`doc.GetClosedVolumes` 返回空：闭空间要经 MDL 建模流程产生」，
  配方 = `Set coord_part = cvol.GetCoordinatesSpecifiedPartLinkedToMesh(id)`；
  `MapCond` → 「前置 `CondMapForStructure` 未取到 —— MapCond 只能由它的 `GetValue(key)` 产出」。

### R39-2 假否证根治：递归拆包 + 形态诊断

R38 只拆**一层** tuple；实测 `conds.GetCondCoSim()` 还套了一层 → 名字解析仍抛
`AttributeError`。本轮 `_unwrap()` **递归拆到 4 层**，并在 `unknown` 判定时记录
`object_type`/`object_repr`。

**关键口径**：实例拿到了、名字却解析不出来 → 那是**探针侧限制**，
**不得写成"宿主不认"**。总账里该条即据此表述（"该对象形态不支持 GetIDsOfNames
（探针侧限制，非宿主否证）"）。这是 R38/R39 两次假否证的共同根因。

### R39-3 契约门：一条命令查完

`python tools/api_contract_check.py` 六项：

| 检查 | 结果 |
|---|---|
| 目录：假参数 / 取值形状 / `dispatch_name` | PASS（0 / 0 / 32 条） |
| 账本：18 条键、缺口 ↔ 终态一一对应 | PASS（1 缺口带终态） |
| 总账：41 = 32 + 9，NYI 全带原因 | PASS |
| 桥接：目录成员覆盖率、包装可追溯 | PASS（0.996，未知包装 0） |
| 语料：名字同源链接无手册漏项 | PASS（39 链接，0 缺口） |
| 取值守卫三态 | PASS（None / False / True 各就位） |

### 回归

全量回归 **1423 passed / 4 skipped / 0 failed**（554.62 s；R38 收口同口径 1414，
增量 +9 = 本轮新模块 9，逐项对得上）。
新增测试 1 个模块：`test_r39_evidence.py`（9）。

### 证据

`schemas/dispatch_account.json`（41 行总账）、`_p12u_gate/r39/name_verdicts.json`
（驱动运行：31 裁定 + 形态诊断）、`_p12u_gate/r39/contract.json`（契约门输出）。

---

## R40 —— MDL 流程裁定 + 契约门进回归 + 守卫覆盖盘点（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R40-1** | **走 MDL 流程补闭空间裁定** | 转裁定，或给出"造不出来"的**确切原因** | ✅ 给出一级机制原因：**`mg.GetMDL()` 底层返回 None**（闭空间必须建在 MDL 之上，工程未完成 MDL/BAM 流程） |
| **R40-2** | **契约门进回归入口** | 回归跑完即知契约是否仍成立 | ✅ `run_all_tests.py` 先跑契约门，六项全 PASS，失败计入退出码 |
| **R40-3** | **守卫覆盖盘点** | 有逐路径表；缺口列清 | ✅ 四条写路径逐条可查（3 条 PASS + 1 条声明）；未声明直写者 **0** |

### R40-1 闭空间：流程走通了，但对象拿不到 —— 原因精确到机制

探针加 `--with-mdl`：`mg.GetMDL()` → `SelectAllFace(True)` → `CreateClosedVolumeFromSelectedFace`
→ `QueryClosedVolumeByIndex(0)`。三处实测教训：

1. **MDL 不在 `TYPED_CLASSES` 里** → 没有物化包装，`getattr(mdl, "QueryClosedVolumeByIndex")`
   直接 AttributeError；必须走泛型 `mdl.call(...)`；
2. **拿到的是"包着空对象的 ComObject"**：`mdl is not None` 成立，真正炸在 `_invoke(None, …)`，
   报错文本是 `'NoneType' object has no attribute …` —— 光看它会误以为是成员名写错；
   判据必须是 `getattr(mdl, "raw", None) is None`；
3. 于是终态原因写成：**「`mg.GetMDL()` 底层返回 None（ComObject 包了个空对象）：
   闭空间必须建立在 MDL 之上 —— 该工程尚未完成 MDL/BAM 建模流程」**。

### R40-2 契约门进回归入口

`run_all_tests.py` 现在**先跑** `tools/api_contract_check.py`，逐行打印 PASS/FAIL，
并把 `gate_rc` 计入最终退出码 —— 契约不成立时回归整体失败（不再只靠某个测试模块兜）。

### R40-3 守卫覆盖盘点

`tools/guard_coverage.py` 逐条查（用源码/AST 判定，不靠文本匹配）：

| 写路径 | 守卫 | 结果 |
|---|---|---|
| `scflowpre_api.ComObject.call` | 取值三态 + 参数个数 | PASS |
| `vbs_bridge.build_vbs` | 取值三态 + 方法名纠错 | PASS |
| `nav_panels` → `pphxml.set_xenv_value` | 实测键账本 + 枚举白名单 | PASS |
| 工具直写 xenv | **逐个声明** | 仅 `xenv_host_write_check.py`（已声明）；未声明 **0** |

**自证教训**：第一版用文本匹配 `set_xenv_value(` 找直写者，把**本工具自己的 docstring**
列成了"未声明直写者"（假阳性）→ 改用 **AST** 只认真正的调用。

### 回归

全量回归 **1431 passed / 4 skipped / 0 failed**（585.31 s；契约门已进 `run_all_tests.py`，
pytest 口径同 R39 的 1423 + 本轮新模块 8，逐项对得上）。
新增测试 1 个模块：`test_r40_evidence.py`（8）。

### 证据

`_p12u_gate/r40/name_verdicts.json`（`--with-mdl` 运行 + 机制级原因）、
`schemas/dispatch_account.json`（41 行总账，ClosedVolume 原因已更新）、
`_p12u_gate/r40/guard_coverage.json`（守卫盘点）。

---

## 收敛判定（R40 到界，2026-09-15）

目标原文：「**继续执行 R* 修正轮次至 R40 或不再有可验证的新 R* 条目**」。
R40 已执行完毕，按第二个条件逐面复核：

| 面 | 状态 | 依据 |
|---|---|---|
| 数值等价 | ✅ 已达成 | R17/R18/R23（`zero_field=false`、`gate_ok=true`） |
| CAD 摄取（x_t/STEP） | ✅ 已达成 | R14/R15（绝对路径纠正后两版皆可载） |
| 条件体系 | ✅ 封顶 | 92 精确键 = 全部可落点类型（R8-1） |
| 面板落盘 | ✅ `memory_only` = 0 | R25-1 |
| 宿主键账本 | ✅ 19 → **18** 更正 + 缺口终态 | R32-1 / R33-4 |
| API 目录 | ✅ 假参数 0 / 取值 1855+ / 返回值 4177 | R30–R36 |
| 名字裁定 | ✅ **32/41 裁定，9 条终态 NYI（带原因+配方）** | R35–R40 |
| 写路径守卫 | ✅ 4 条路径全覆盖，未声明直写者 0 | R40-3 |
| 契约门 | ✅ 六项全 PASS（一条命令可复验） | R39-3 / R40-2 |
| FLD/iFLD | ⛔ 产品形态限制 | R20/R21（无 `FLDUTIL.exe`，scPOST 是 GUI 模块） |
| STEP 宿主网格崩溃 | ⛔ 外部缺陷 | APPCRASH `mfc140u.dll` + WER 证据（非本仓可修） |
| 闭空间/材料/映射对象裁定 | ⛔ NYI（9 条） | 需先走 MDL/材料/映射流程造对象；原因与配方已逐条入册 |

**判定**：R29–R40 这 12 轮把「API 面 / 宿主键 / 名字 / 守卫」四条支线全部推到了
**可复验的终态**（总账 41/41 有终态、契约门 6/6 PASS、回归 1400+ 全绿）。
剩余三面要么是**产品形态限制**、要么是**外部缺陷**、要么是**需要多步 GUI 流程**才能造对象
（且原因与配方已逐条落册）—— 不再有"可验证且成本合理"的新 R* 条目。

→ 据此判定收敛，**目标达成**。

---

## R41 —— 9 条 NYI 推进：从"取不到实例"到"机制级结论"（2026-09-15，用户点单）

### 结果：数量仍是 9，但**性质变了**

| 类 | 条数 | 终态（本轮实测） |
|---|---|---|
| `CondBoussinesqBaseTemp` | 1 | ⛔ **宿主无此接口**：`CreateCondBoussinesqBaseTemp` → `DISP_E_UNKNOWNNAME`（手册未列、宿主也未实现） |
| `CondMapForStructure` | 1 | ⛔ **宿主无此接口**：`CreateCondMapForStructure` / `QueryCondMapForStructureByName` 均 `DISP_E_UNKNOWNNAME` |
| `MapCond` | 1 | ⛔ **宿主无此接口**：`GetAllMapCondNames` 亦 `DISP_E_UNKNOWNNAME`（手册的 map API 在本机不存在） |
| `ClosedVolume` | 1 | ⛔ **MDL 不可得**：`wizard.CreateMDL` 调用后 `GetMDL()` 仍为空（`mdl_probe` 落盘） |
| `PropItem` | 2 | ⛔ **前置缺失**：需闭空间/材料（`CondInitial.GetPhaseMaterial` 空） |
| `CondCoSim` / `CondCoSimRegion` | 3 | ⛔ **工程无 CoSim 条件**：`GetCondCoSim()` 返回空（ldc/A16-2/A25-1 三个 CoSim 算例都试过） |

**另一项达成**：`unknown` **归零** —— R39-2 的验收项（"归零或给出实证"）这轮才真正落地。

### 修掉的三个探针缺陷（都是"假否证"同族）

1. **`errors.setdefault` 让旧的失败文本盖住新结论** —— 工程循环里 MDL 检查写下的原因
   一直留着，把后面真实尝试的结果盖掉，读证据会得出错误结论；
2. **`_try` 存实例时没拆 tuple** —— 后续 `host.call` 报 `'tuple' object has no attribute 'call'`；
3. **空 tuple 被当成对象** —— `GetCondCoSim()` 在"没有 CoSim 条件"时返回 `()`，
   而 `_unwrap` 只判"是不是 tuple"不判空，于是存进去一个空元组，
   一路传到名字解析变成 `AttributeError(tuple)` → 记成 `unknown`。
   **空容器 = 没拿到对象**，这条已写进 `_unwrap` 并加单测。

### 判据升级：最强证据优先

`dispatch_account.py` 现在按 **宿主无接口（DISP_E_UNKNOWNNAME） > 实例已取到但解析失败 >
未取到实例** 的优先级给原因，并在行里落 `host_interface_absent` 字段 ——
这样"手册有、宿主机没有"的条目是**机器可查**的，而不是一句"取不到"。

### 回归

全量回归 **1441 passed / 4 skipped / 0 failed**（570.61 s；R40 收口同口径 1431，
增量 +10 = 本轮新模块 10）。首轮跑出 1 条红是 `test_r39_evidence.py::test_empty_tuple_stays`
—— 它断言的正是 R41 推翻的旧口径（空 tuple 保持原样），已按新口径改写并注明原因。
新增测试 1 个模块：`test_r41_evidence.py`（10）。

### 证据

`_p12u_gate/r41/name_verdicts.json`（4 工程运行 + `call_errors` + `mdl_probe`）、
`schemas/dispatch_account.json`（9 条 NYI 的机制级原因 + `host_interface_absent`）。

---

## R42 —— 提案（≈1 人日）

### 依据

* 本轮证实 4 个创建/查询接口**宿主没有**，但它们仍留在目录里（消费者无从得知）；
* 本仓代码里是否引用了这些不可用成员，**没有查过**；
* 剩余 5 条（闭空间/材料/CoSim 区域）需要在**有 MDL/材料的工程**上跑完整流程，
  属于"要么投入 GUI 自动化、要么承认做不到"的取舍。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R42-1** | **不可用成员入册** | 把 `call_errors` 里的 `DISP_E_UNKNOWNNAME` 结论写进目录（`host_absent`） | 目录可区分"手册有/宿主无"；契约门查一条 | 0.25 |
| **R42-2** | **仓内引用自检** | 扫全仓是否调用了 `host_absent` 的成员 | 有结论（引用 0 或列出并修） | 0.25 |
| **R42-3** | **剩余 5 条的取舍** | 明确写"需要 GUI 流程，不做"或投入 `--with-mdl` 的完整向导自动化 | 5 条有终态口径（不悬空） | 0.5 |

### 明确不做

* 不提取 Post / Solver / Monitor 类（非本仓域）；
* 不为 `Set*` 写「自动挑取值」逻辑——取值选择是面板语义，不是目录语义。

---

## R42 —— 成员可用性入册 + 仓内引用自检 + NYI 终态（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R42-1** | **不可用成员入册** | 目录可区分"手册有/宿主无" | ✅ 普查 **17 类、1000+ 成员** → **12 个宿主未实现**，全部入册 `host_absent` |
| **R42-2** | **仓内引用自检** | 有结论（引用 0 或列出并修） | ✅ 抓到 1 处**死代码**（`MeshingGroupSetting.GetInternalUnit` 手写包装）→ 删除；检查自身修掉 1 处假阳性 |
| **R42-3** | **剩余 NYI 取舍** | 5 条有终态口径 | ✅ 9 条 NYI 全部带 `terminal`：**3 宿主无接口 / 6 需要 GUI 流程**（明确不做） |

### R42-1 成员可用性普查：手册列了、宿主没实现的 **12 处**

探针加 `--sweep`：对**已取到实例**的类，用 `GetIDsOfNames` 逐个解析手册成员
（只解析名字、不调用方法，零副作用）→ 写 `schemas/host_member_availability.json`。
实测 12 个成员 `DISP_E_UNKNOWNNAME`：

| 类 | 未实现成员 |
|---|---|
| `CondBoundaryFlowIO` | `GetMassVolumePressureInflowDirectionType`（**名字带零宽空格**）、`GetPbmFuncType`、`SetPbmFuncType` |
| `CondOutputTimeSeries` | `GetProjectonType`、`SetProjectonType`（手册拼写错，与 `Projection` 不同） |
| `MeshingGroup` | `GetDiscontinuous`、`SetDiscontinuous`、`ReplaceMDLMode` |
| `Doc` / `MeshingGroupSetting` / `SpecialRegion` / `CondInitialShapeModify` | `GetAllMapCondNames` / `GetInternalUnit` / `ImportCSV` / `RemoveMorphingRegion` |

两个附带发现：
* **零宽空格**（`\u200b`）藏在成员名里 —— 这种名字**永远调不通**（手册数据卫生问题）；
* `GetProjectonType` 是手册拼写错（与 R34-3 的 41 处标题/签名分歧同类，但这次是**两边都错**）。

入册方式：提取期 `_apply_host_absent()` 读普查结果 → 目录条目带 `host_absent` +
`host_absent_evidence`（**12 条**）；同时 `materialize_catalog_wrappers()` **跳过**它们
（不再造出注定失败的方法 —— typed 桥覆盖 1759 → 1754，这个下降是正确的）。

### R42-2 仓内引用自检：抓到死代码 + 修掉检查自身的假阳性

契约门加第 7 项检查（`host_absent`），首跑就红：

* **真阳性**：`automation/scflowpre_api.py` 手写了 `MeshingGroupSetting.GetInternalUnit`
  包装 —— 宿主没有该成员，调用必然 `com_error` → **删除**（并在原位留注说明）；
* **假阳性**：`ImportCSV` 被报"引用未实现成员"，但它在 `SpecialRegion` 未实现、
  在别的类里是实现了的 → 判据改为**只在无歧义时判**（同名成员全部类都 absent 才算）。

修完后：未实现成员 8 条无歧义、**仓内引用 0**、契约门 **7 项全 PASS**。

### R42-3 NYI 终态

`dispatch_account.py` 给每条 NYI 落 `terminal`：
**3 条 `host-interface-absent`**（宿主没接口）+ **6 条 `needs-gui-flow`**
（闭空间/PropItem/CoSim 区域是 MDL/材料/CoSim 流程的产物，只打开工程拿不到）——
**明确不做，不留"待办"**。

### 回归

全量回归 **1451 passed / 4 skipped / 0 failed**（582.38 s；R41 收口同口径 1441，
增量 +10 = 本轮新模块 10，逐项对得上）。
新增测试 1 个模块：`test_r42_evidence.py`（10）。

### 证据

`schemas/host_member_availability.json`（普查：17 类逐成员状态）、
`schemas/dispatch_account.json`（9 条 NYI 的 `terminal`）、
`_p12u_gate/r42/contract.json`（契约门 7 项全 PASS）。

---

## R43 —— 普查覆盖率口径 + 探针侧错误归零（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R43-1** | **普查覆盖率口径** | 覆盖率可复算；未普查类列清 | ✅ **三桶互斥**：已普查 **17/199 类**（1873/4455 成员）+ 空对象 **8 类** + 未普查 **174 类** |
| **R43-2** | **`error:*` 收敛** | 每条有归因，或归零 | ✅ **28 → 0**；根因 = 空壳对象进了 ctx；顺带修掉 2 个**假阳性** |

### R43-1 覆盖率：三桶互斥，口径写进证据

`schemas/host_member_availability.json` 新增 `coverage`：

| 桶 | 数 | 含义 |
|---|---|---|
| `classes_swept` | **17**（成员 1873/4455） | 本机单会话里取到实例、逐成员解析过的类 |
| `empty_objects` | **8** | 试过但**只有空壳**（对象前置缺失）——正是 R41/R42 的 NYI 那批：`ClosedVolume`/`PropItem`/`CondMapForStructure`/`MapCond`/`CondBoussinesqBaseTemp`/`CondCoSim`/`CondCoSimRegion`/`Octree` |
| `unswept_classes` | **174** | **从未尝试**（≠ 已实现，口径写进 `note`） |

17 + 8 + 174 = 199 ✓（测试钉住这条守恒）。契约门把 `coverage` 一并打出来。

### R43-2 探针侧错误归零：空壳对象不许进 ctx

上一轮普查有 **28 条 `error:AttributeError(NoneType)`**，全部集中在 `Octree`。
根因：官方算例里 `mg.GetOctree()` 返回**空壳**（`ComObject(None)` —— 工程里还没建八叉树），
而 `_obtain`/`ctx` 把它当对象收下了，普查于是对它的每个成员报错 ——
**28 条噪声差点把"哪些成员宿主没实现"的真结论埋掉**。

修法：`_empty()` 判空壳，**不收进 ctx**，并在 `coverage.empty_objects` 里留名归因。
结果：**探针侧错误 0**，未实现成员稳定在 12。

**顺带修掉 2 个假阳性**：属性键带类型后缀（`Application.Visible(BOOL)` /
`UserControl(BOOL)`），宿主认的是**括号前那段**；不剥后缀会把已实现的属性误报成
"宿主未实现"（曾把 unknown 从 12 抬到 14）。剥后缀后回到 **12**，目录里那两条
误标的 `host_absent` 也被自动清掉。

### 回归

全量回归 **1460 passed / 4 skipped / 0 failed**（557.35 s；R42 收口同口径 1451，
增量 +9 = 本轮新模块 9，逐项对得上）。
新增测试 1 个模块：`test_r43_evidence.py`（9）。

### 证据

`schemas/host_member_availability.json`（`coverage` 三桶 + 逐成员状态；errors 0）、
`_p12u_gate/r43/contract.json`（契约门 7 项，`probe_errors` = 0）。

---

## R44 —— 普查扩面到 `Cond*` + 空对象前置提示（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R44-1** | **普查扩面到 `Cond*`** | 覆盖类数 ≥60；新未实现成员入册 | ✅ **17 → 84 类**（成员 1873 → 2793）；新发现 **4 处**未实现 → 累计 **16 处** |
| **R44-2** | **空对象提示** | 提示可查（工具或文档一处） | ✅ 8 个空对象类各带 `empty_hints`（「先跑哪个流程」）并进证据与测试 |

### R44-1 批量条件实例化：覆盖 17 → 84 类

目录里有 **89 个 `CreateCond*`** 创建器（条件收割工具验证过的路子）。探针在**工程会话内**
批量调用（参数按 `1 参 → 3 参 → 2 参` 退让，多参创建器如 `CreateCondCoSim(name, apptype,
interfacetype)` 也能试到）→ **78 个条件实例**一次建成，随后逐成员解析：

| 指标 | R43 | R44 |
|---|---|---|
| 已普查类 | 17 | **84**（/199） |
| 已普查成员 | 1873 | **2793**（/4455） |
| 未实现成员（条目） | 12 | **16** |
| 探针侧错误 | 0 | **0** |

新抓出的 4 处「手册有、宿主无」：`CondInitial.GetPbmFuncType` / `SetPbmFuncType`、
`CondPorousMedia.ImportCSV`、`CondSource.IsEnableConditionForCalculation`。

**口径修正**：同名成员可能在**多个类**都未实现（`GetPbmFuncType` 2 类、`ImportCSV` 2 类）
—— 统计要数**条目**；去重后的名字会少 3 个（16 → 13）。R42 那条「`ImportCSV` 只在
`SpecialRegion` 未实现」的断言随之更正为 `{SpecialRegion, CondPorousMedia}`，并保留
「别的类（FaceRegion/NumericalRegion）的实现不得误删」的检查。

### R44-2 空对象前置提示

`coverage.empty_hints`（随证据一起落盘，逐条可查）：

| 类 | 提示 |
|---|---|
| `ClosedVolume` | 先跑 MDL/BAM 建模（闭空间由面区域生成） |
| `PropItem` | 先注册材料/物性（或经闭空间的材料项取得） |
| `CondMapForStructure` / `MapCond` | 先建映射（scFLOW2Nastran）条件——宿主无创建接口 |
| `CondBoussinesqBaseTemp` | 条件向导创建——宿主无 `CreateCondBoussinesqBaseTemp` 接口 |
| `CondCoSim` / `CondCoSimRegion` | 先做 CoSim 设置（区域由 CoSim 条件派生） |
| `Octree` | 先建八叉树（网格组的 octree 步骤） |

测试断言：每个空对象类**都必须有**提示，且提示里出现可操作的关键词（MDL / 材料 / 八叉树）。

### 回归

全量回归 **1467 passed / 4 skipped / 0 failed**（601.21 s；R43 收口同口径 1460，
增量 +7 = 本轮新模块 7，逐项对得上）。新增测试 1 个模块：`test_r44_evidence.py`（7）；
并按本轮新事实更新 R42/R43 的三处断言（改为单调下界 / 双类未实现）。

### 证据

`schemas/host_member_availability.json`（84 类 / 2793 成员 / 16 未实现 / errors 0 /
`empty_hints`）、`schemas/vb_api_catalog.json`（`host_absent` 16 条）。

---

## R45 —— 自动配方扩面 + 提示进产品面 + 普查常规入口（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R45-1** | **自动配方扩面** | 覆盖类数 84 → ≥110 | ✅ **146 类**（/199，73.4%）；成员 2793 → **3855**（/4455） |
| **R45-2** | **提示进产品面** | 面板或文档一处可查 + 测试 | ✅ `scflowpre_api.object_hints()`/`host_absent_members()` + `docs/NYI_INVENTORY.md` 自动生成节（同源，测试对账） |
| **R45-3** | **普查常规入口** | 一条命令可复算（含覆盖率） | ✅ `tools/host_member_sweep.py`（`--report-only` 不起宿主；覆盖低于 `--min-classes` 非零退出） |

### R45-1 自动配方：给**每一类**生成候选，而不是逐条手写

不再一条条补链式配方，而是把"拿实例"变成**可生成的计划**（`tools/dispatch_name_probe.py`，
纯函数 `auto_plans()`，离线可单测）：

| 优先级 | 来源 | 例 |
|---|---|---|
| ① | 类级 `instance` **配方**（手册亲自给的取法，参数也照抄） | `Set dtsr = conditions.CreateCondDTSR("name")` → `CreateCondDTSR("R45CondDTSR")` |
| ② | 目录里**声明在已持有宿主上**的构造/取用成员 | `Doc.CreateFaceRegion` / `Doc.GetProjectSetting` / `Conditions.GetCondCavitation` |
| ③ | 宿主独有成员（手册是子集）——只在 `Conditions`/`Doc`/`MeshingGroup` 上泛试 | `Create<S>`/`Get<S>`/`Query<S>ByName`… 名字家族穷举 |

参数按阶梯退让（`(name,)` → `(name,0,0)` → `(name,0)` → `()` → `(name,False)` → `(name,"default")`），
并优先用**手册签名里的参数名**给实参（`[in](BSTR)ProgID` → 真的传本机 ProgID）。

结果：**66 类**由自动配方一次取得（其余靠已有链条/条件批量实例），覆盖 84 → **146 类**、成员 2793 → **3855**。

### R45-1b 三个"假证据"闸门（本轮的主要发现）

扩面把三处**会伪造结论**的路径暴露了出来，全部当场修掉——它们的共同后果都是
"把别人的成员写成宿主未实现"（假否证，比没普查更有害）：

| # | 事故 | 后果 | 修法 |
|---|---|---|---|
| ① | 把会话 `Application` 对象**别名**成 `Kicker.Application` | 那 9 个成员 **8 个** `unknown_name`；`GetApplicationLaunchSetting` 之类会被入册成"宿主未实现" | **别名留空**（实测会话对象就是目录 `Application` 类：23 成员、unknown 比率 **0.00**），并写明"别名必须过验身" |
| ② | 配方写的是**别的类**（`CondOversetGap` 那页给的是 `CreateCondSpray`） | 拿错对象 → 它的独有成员全判未实现 | **验身**：`identity_ok()` 用该类**独有成员**的解析率把关（≥ 半数），否掉的配方记进 `identity_rejected`（实测否掉 10 条：`Condition <- Doc.GetConditions`，集合对象不是单个 `Condition`） |
| ③ | 别名/对象**过时**时整类解析失败 | 整类假否证 | **验身后置闸**：`sweep_class_verdict()` —— 整类未知过半（且成员 ≥4）就**整类不记**，停在"未普查"（宁可没结论，不要假结论） |

另修两处**假阳性**（把能用的说成不可用）：

* `ClosedVolume.SelectFace`：标题名能用、签名名 `SetSelectFaces` 不认 —— 派发名不通时
  **回退试成员键名**（证据 `resolved_via_member_key`）；
* 自动配方的调用错误**不再并进** `call_errors`：它会在多个宿主上试同一个名字
  （`CreateCondCoSim` 在 `Doc` 上当然没有），并进去会把 CondCoSim 这类"接口有、对象还没造出来"
  的条目误判成 `host-interface-absent`（实测过：NYI 终态从 3+6 漂成 6+0，隔离后回到 **1+5**）。

### R45-1c 覆盖率口径：三桶 → 四桶

手册页**一个成员都没有**的类（`CondALECancel`/`ParticleRegion`…）取到对象也"没成员可查"：
算进 `classes_swept` 会把覆盖率说虚，算"未普查"又不实。故单列一桶：

| 桶 | 数量 |
|---|---|
| 已普查 | **146** |
| 取不到实例（各带前置提示） | **4**（`CondBoussinesqBaseTemp`/`CondCoSim`/`CondCoSimRegion`/`PropItem`） |
| 取到但手册无成员 | **10** |
| 从未尝试 | **39** |
| 合计 | **199** ✅ |

顺带修掉一次**桶重叠**（同一类在早期工程里是空的、后面工程拿到了真对象，
`empty_objects` 与已普查重叠 → 199 类数出 201）：已普查的类不再算"取不到实例"。

### R45-2 提示进产品面（同一份证据，三个可查面）

| 面 | 内容 |
|---|---|
| API | `automation.scflowpre_api.object_hints()`（类 → "先跑哪个流程"）、`host_absent_members()`（类 → 宿主未实现成员）；缺证据文件时返回空 dict，不崩 |
| 文档 | `docs/NYI_INVENTORY.md` 新增自动生成节「宿主侧能力边界」：取不到实例的类（含先决提示）+ 宿主未实现成员清单（25 条） |
| 证据 | `schemas/host_member_availability.json` 的 `coverage.empty_hints` / `coverage.no_member_classes` |

提示表升为**模块级知识** `EMPTY_HINTS`（`ClosedVolume`/`Octree` 这轮已经能取到，
不再出现在当轮证据里，但"要先跑什么"是知识，不随一轮结果消失 —— 测试查表、产品面查当轮子集）。

### R45-3 常规入口

`tools/host_member_sweep.py`：默认 5 个工程（`box.pph` + exB01/exA26/exA16/exA25）、
`--budget` 时间预算、`--min-classes`（默认 84 = R44 基线）**低于即非零退出**、
`--report-only` 不起宿主只报当前证据。本轮最终证据就是走它跑的（`_p12u_gate/r45_run4.log`）。

### 附带成果

* 目录 `host_absent` **16 → 25 条**（16 个类）：新增 `CondFreeSurface.GetPhaseCheangeSw`/`SetPhaseCheangeSw`、
  `CoordinatesSpecifiedPart.GetRadiationValue`、`ClosedVolume.GetSweepDestinationFaceRegion`、
  `VolumeRegion.GetSweepDestinationFaceRegion`、`ClosedVolume.ImportCSV` 等；
* 标题/签名分歧总账：**已裁定 32 → 35 / NYI 9 → 6**（`ClosedVolume.SelectFace`、
  `CondMapForStructure.SetPIDPartCorresp`、`MapCond.SetParam2` 三条由"取不到对象"变为裁定）；
  NYI 终态 **1 host-interface-absent + 5 needs-gui-flow**；
* 探针侧错误保持 **0**；`identity_rejected` 10 条全部是同一处（`Condition <- Doc.GetConditions`）。

### 回归

全量回归 **1492 passed / 4 skipped / 0 failed**（569.92 s；R44 收口同口径 1467/4/0，
增量 +25 = 本轮新模块 25 项，逐项对得上；末行 `exit=0` 一并落盘）。新增测试 1 个模块 `test_r45_evidence.py`（25 项：
离线配方生成/验身/四桶/产品面/入口），并按新口径更新 R42/R43/R44 的 6 处断言
（NYI 数量与终态分布改**单调下界**、`ImportCSV` 集合改下界、空对象集合改下界、
三桶改四桶）。

### 证据

`schemas/host_member_availability.json`（146 类 / 3855 成员 / 25 未实现条目 / errors 0 /
`auto_obtained` 66 / `identity_rejected` 10 / `no_member_classes` 10）、
`schemas/vb_api_catalog.json`（`host_absent` 25）、`schemas/dispatch_account.json`（NYI 6）、
`docs/NYI_INVENTORY.md`、`_p12u_gate/r45_run4.log`。

---

## R46 —— 未普查类归因 + 取得路径进总账 + 宿主边界上面板（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R46-1** | **未普查类归因** | 39 类逐类有终态且入 `schemas/`，无"未归因" | ✅ `tools/unswept_account.py` → `schemas/unswept_account.json`：39/39 有终态（6 种） |
| **R46-2** | **取得路径进总账** | 覆盖率报表能答"这个类怎么拿到的" | ✅ `coverage.obtained_via` **156 条**（146 已普查 + 10 无成员，无缺口） |
| **R46-3** | **未实现成员上面板** | GUI 一处可查（或明确记为不做） | ✅ 条件目录新增 **Host 列** + 「Host 边界…」对话框（离屏 Qt 测试） |

### R46-1 终态：六种，每一种都要能追到证据

覆盖到 73.4% 后，剩下的 39 类不是"还没轮到"，而是各有原因。判据全部来自**证据**
（配方宿主、候选调用错误、返回空），口径写死在 `classify()`（纯函数，可离线单测）：

| 终态 | 数量 | 判据 |
|---|---|---|
| `needs-corpus` | **23** | 配方要的前置对象本会话没有（`snode`/`obj_R`/`condcosim`/`mixedgas`/`combustion`/`particletracking`…），或取法**试过返回空**（本机工程没有该对象） |
| `no-creation-path` | **12** | 手册**没给**任何可取用的创建/取用路径（`WrappingParam`/`ISFace`/`IVEdge`/`PropGroup`/`CrossSectionView`…）—— 名字家族乱猜不构成"宿主无接口"的证据 |
| `foreign-app` | **3** | `Kicker.Application`/`ApplicationLaunchSetting`/`LicenseStatus`：属于 Kicker 启动器，本会话是 scFLOWpre 会话 |
| `call-rejected` | **1** | `CondMultiphaseMaterial.QueryCondMultiphaseMaterial`：手册取法存在但调用被拒（非"未知名称"） |
| `host-interface-absent` | 0 | 手册声明的取法**全部** `DISP_E_UNKNOWNNAME`（本轮无实例；判据与测试就绪） |
| `probe-limitation` | 0 | 试过但无结论（**宁可停在这里，也不许编理由**） |

**新增证据字段** `coverage.auto_empty_targets`（21 条：试过取法但**返回空**的类）——
"本机工程没有这类对象"与"宿主没这个接口"从此分得开，这正是 R45 三个假证据闸门的延续。

### R46-2 取得路径

`coverage.obtained_via`（类 → 怎么拿到的）：**156 条**，覆盖 146 个已普查类 +
10 个"手册无成员"类，零缺口。路径形态：`chain:`（链条）、`auto:`（自动配方）、
`CreateCond*:`（条件批量实例）、`session:`（会话/文档直取，如
`HybridParam -> GetHybridParam`、`Doc`/`Conditions`）。测试还要求：非前缀形态的
路径必须是**目录里真实存在的成员名**（不许写空话）。

### R46-3 面板（离屏 Qt 可测）

`nav_panels.py` 的条件类型目录（`CondTypeCatalogDialog`）：

* 新增 **Host 列**：该条件类型对应的目录类有宿主未实现成员时显示 `⚠ N` 并带 tooltip
  列出成员名，否则 `ok`；选中行时详情栏追加"宿主未实现: …"；
* 新增 **「Host 边界…」按钮** → `HostBoundaryDialog`：上半是"取不到实例的类 + 先决流程"，
  下半是"宿主未实现的成员（25 条）"；
* 数据走**产品面** `automation.scflowpre_api.host_absent_members()` / `object_hints()`，
  文本走纯函数 `render_host_boundary()` —— 缺证据文件时给一句可读说明而不是崩。
* 测试在 `QT_QPA_PLATFORM=offscreen` 下真建对话框（`HostBoundaryDialog` /
  `CondTypeCatalogDialog`），断言 Host 列与入口存在、文本含成员名；Qt 不可用时跳过。

### 回归

全量回归 **1505 passed / 4 skipped / 0 failed**（585.67 s；改口径前后各复算一次，
610.81 s / 585.67 s 同数；R45 收口同口径 1492/4/0，增量 +13 = 本轮新模块 13 项）。新增测试 1 个模块 `test_r46_evidence.py`（13 项：
归因口径/证据优先/入册一致/取得路径/面板文本与离屏对话框）。

### 证据

`schemas/unswept_account.json`（39 类终态 + 判据 + 逐类证据）、
`schemas/host_member_availability.json`（`obtained_via` 156 / `auto_empty_targets` 21）、
`_p12u_gate/r46/name_verdicts.json`、`_p12u_gate/r46_run2.log`、`nav_panels.py`。

> `tools/host_member_sweep.py` 的逐轮证据落点改为 `--evidence`（默认中立目录
> `_p12u_gate/host_member_sweep/`）—— 此前写死在 `_p12u_gate/r45/`，R46 的复算会
> 覆盖上一轮的证据文件。

---

## R47 —— 带词表/真名再扩面 + Kicker 会话实测 + 未实现成员前置校验（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R47-1** | **带语料/词表再扩面** | 覆盖 146 → ≥155，或逐类给出"仍取不到"的证据 | ✅ 两条新机制各下一城（**+4 类**，见下）；未达 155 → 走第二分支：**36 类逐类终态**齐备 |
| **R47-2** | **Kicker 会话实测** | 3 类终态改为"已实测"（成功失败都要有证据） | ✅ 附着 `Kicker_Bx64.Application.2025`：**2 类取到**（Application 0 未知成员、LicenseStatus 0 未知）/ 1 类宿主原话拒绝 |
| **R47-3** | **未实现成员前置校验** | 一处可查 + 测试 | ✅ `vbs_bridge.host_absent_methods()` 在**生成期**点名（12 条无歧义），`strict_values=True` 直接抛 |

### R47-1 两条新机制（都是"按手册给，不猜"）

| 机制 | 做法 | 战果 |
|---|---|---|
| **手册词表填实参** | `signature_args()` 对字符串参数优先用手册 `values` 首项（`CreateMultiYAxisTable(name, type)` 的 type 只认 `'freq_absorp_coeff_table'`，喂 0 必被拒） | `MultiYAxisTable` ✓ |
| **真名字池** | `harvest_names()`：已持有对象的 `GetName()` + 宿主 `GetAll*Names` + 配方里的 ``@名字`` → 喂给 `Query<X>ByName` 类取法 | `Condition` ✓（`Conditions.QueryConditionByName(真条件名)`） |

**同时修掉一个假覆盖**（口径修正）：`CondParticleCounter` 的配方给的是**别的条件对象**
（9 个成员 8 个解析不到），验身后置闸早就把它拦了，但 `obtained_via`/`auto_obtained`
还留着"已取得"——自相矛盾。R47 起**验身否掉的类同时撤下取得声明**，该类退回"未普查"
并进终态表。

净值：**146 → 149 类**（新增 `Condition`/`Kicker.Application`/`Kicker.LicenseStatus`/
`MultiYAxisTable`，退出 `CondParticleCounter`），成员 3855 → **3878**；未普查 39 → **36**
（needs-corpus 22 / no-creation-path 12 / call-rejected 2 / foreign-app 0 / probe-limitation 0）。

> 为什么没到 155：剩余 36 类里 22 类卡在**前置对象**（材料/CoSim/粒子/映射/混合物/
> 体网格产物），12 类手册**根本没给取法** —— 这不是"再跑一轮就能多几类"的事，
> 逐类终态（`schemas/unswept_account.json`）就是这一条的验收面。

### R47-2 Kicker 会话实测

宿主**就是 Kicker 启动的**，故附着它（`GetActiveObject("Kicker_Bx64.Application.2025")`）：

| 类 | 结果 | 证据 |
|---|---|---|
| `Kicker.Application` | ✅ 取得（`"kicker:GetActiveObject"`），9 个成员 **0 未知** | `obtained_via` |
| `Kicker.LicenseStatus` | ✅ `GetLicenseStatus()` 取得，4 个成员 **0 未知** | `obtained_via` |
| `Kicker.ApplicationLaunchSetting` | ❌ `GetApplicationLaunchSetting(ProgID)`：4 个 ProgID 变体全被拒（`Invalid ProgID was specified`，宿主原话入库） | `kicker_errors` → 终态 `call-rejected` |

> **坑位记录**：`_oleobj_`（PyIDispatch）只能用于 `GetIDsOfNames` 普查，**调用**必须走
> win32com 的 CDispatch（`ComObject._invoke` 先 `_FlagAsMethod` 再 `getattr`）——
> 首轮就是拿 `_oleobj_` 去调，两个类都报 `AttributeError: 'PyIDispatch' object has
> no attribute ...`。

### R47-3 未实现成员前置校验

`automation/vbs_bridge.host_absent_methods()`：目录 `host_absent` 里**无歧义**的名字
（所有声明它的类都标了未实现 —— 12 条；`ImportCSV` 这种部分类能用的不许进集合）。
`validate_actions()` 对动作行里 `.Member` 形态的调用点逐个点名：
"`GetAllMapCondNames 宿主未实现（GetIDsOfNames → DISP_E_UNKNOWNNAME…）调用必然失败`"
—— 以前要等 COM 抛 `com_error` 才知道；`build_vbs(strict_values=True)` 直接抛 `ApiValueError`。

### 回归

全量回归 **1514 passed / 4 skipped / 0 failed**（568.61 s；R46 收口同口径 1505/4/0，
增量 +9 = 本轮新模块 9 项）。新增测试 1 个模块 `test_r47_evidence.py`（9 项：
词表填参/名字池/Kicker 终态/桥前置校验），并按新事实更新 R45/R46 两处 Kicker 断言
（R45 那条"Kicker 不许进普查"改为"进普查必须写明 `kicker:` 取得路径"—— 正是它刚刚
抓住了 R46 的验身缺口）。

### 证据

`schemas/host_member_availability.json`（149 类 / 3878 成员 / 25 未实现 / errors 0 /
`swept_suspect` 1 / `obtained_via` 160 / `name_pool` 10）、
`schemas/unswept_account.json`（36 类终态）、`_p12u_gate/r47/name_verdicts.json`
（`kicker_args`/`kicker_errors`/`name_pool`）、`_p12u_gate/r47_run4.log`。

---

## R48 —— 命名片段扩面 + 配方可信度入目录 + typed 直调前置拦截（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R48-1** | **取法命名模式扩面** | 149 → ≥160，或逐类给出"宿主确实没有"的证据 | ✅ **152 类**（+3：`CondOutputPclFile`/`CrossSectionView`/`Region`，均 **0 未知成员**）；未达 160 → 33 类逐类终态齐备 |
| **R48-2** | **配方可信度入目录** | 一处可查 + 测试 | ✅ 目录新增 `recipe_unreliable`（**4 类** + 逐条证据） |
| **R48-3** | **typed 直调侧也拦** | 一处可查 + 测试 | ✅ `ComObject.call` 调用前拦（与 VBS 生成**共用** `unambiguous_host_absent()`） |

### R48-1 命名片段（手册的命名习惯是证据）

手册没给实例配方、名字家族也猜不中的类，靠**命名片段**找到取法 —— 片段来自实测的命名习惯：

| 习惯 | 例 |
|---|---|
| `IS??? → S???` / `IV??? → V???` | `IVFace ← Doc.GetSelectedVFaces`、`ISFace ← Doc.GetSelectedSFaces` |
| `Cond<X> → GetCond<X>Condition` | `CondOutputPclFile ← Conditions.GetCondOutputPclFileCondition` |
| 尾部 `View/Param` 常省略 | `CrossSectionView ← Doc.BeginCrossSectionView` |
| 通用词干 | `Region ← ClosedVolume.GetFluidRegion` |

片段要求 **≥4 个字母**（"edge" 这种会命中一大片），排除元信息取器
（`…Information/Count/Num/Flag/Color/Name` 返回的是结构/标量），`Get*/Query*` 优先于
`HitTest*/Set*`。

**两个新闸门**（本轮实测逼出来的）：

* **标量闸**：片段候选里混着返回字符串/结构体的成员（`Doc.GetSFaceInformation`），
  它们过得了"非空"检查，却会让整类成员在普查里抛 `AttributeError` ——
  首轮实测 **46 条 `error:*`**（覆盖 162 类的假象）。`_is_com()` 只收真正的
  COM 对象后，错误回到 **0**，覆盖是实打实的 **152**；
* **验身继续拦**：18 条验身否（`CondCoSim ← GetCondCoSimOption`、
  `Table ← GetAllMultiYAxisTables`…）—— 片段命中不等于就是这个类。

净值 **149 → 152 类**、成员 3878 → **3902**；未普查 36 → **33**，其中
`no-creation-path` 从 12 降到 **2**：片段取法试过之后，"手册没给路径"变成了更准的
`needs-corpus`（取法试过、**返回空** —— 本机工程里没有该对象）。

### R48-2 配方可信度入目录

`schemas/vb_api_catalog.json` 的类级新增 `recipe_unreliable` +
`recipe_unreliable_evidence`：验身否掉的取法与整类拿错对象的（`swept_suspect`）
逐条记录（本轮 **4 类**：`CondCoSim`/`DiffusiveSpecies`/`Table`/`CondParticleCounter`）。
读目录的人不必照抄配方再撞一次墙；测试断言"证据里被否的类必须在目录里有标记"。

### R48-3 typed 直调侧前置拦截

`automation/scflowpre_api.unambiguous_host_absent()`（无歧义 = 所有声明它的类都标了
`host_absent`；`ImportCSV` 这类部分类能用的一律不进）成为**唯一判据**：
`ComObject.call` 在调用前抛可读 `ApiValueError`（措辞保留 `DISP_E_UNKNOWNNAME`，
既有按错误文本判定的消费者口径不变），`vbs_bridge.host_absent_methods()` 直接委托同一个函数。

### 回归

全量回归 **1525 passed / 4 skipped / 0 failed**（568.88 s；R47 收口同口径 1514/4/0，
增量 +11 = 本轮新模块 11 项）。复算两次：第一次 1524/5/0（579.15 s）多出 1 个 **偶发 skip**，
带 `-rs` 复算确认 4 个 skip 全是稳定环境项（`test_material_prp_write` 1 项 +
`test_native_bridge` 3 项，后者要 `SCF_RUN_BRIDGE_TESTS=1` 且需已编译桥）。新增测试 1 个模块 `test_r48_evidence.py`（11 项：
片段生成/短片段拒绝/取用优先/配方标记/前置拦截共用判据）。

### 过程说明（自曝）

R47 的里程碑提交把 9 个**草稿脚本**（`_r47_scan*.py`/`_r47_diff.py`/`_r47_final.py`）
一起收进了仓库 —— `tools/git_milestone.py` 的收录模式含根目录 `*.py`，而草稿脚本正好
落在根目录。本轮删除（提交里会看到 `D`）。教训：草稿脚本要么放 `_p12*` 目录（只收
json/log/md/vbs），要么在轮次收口前删干净 —— 顺带说明为什么 `api_contract_check` 的
"仓内引用"检查会被草稿脚本误伤一次（R45 也踩过同一个坑）。

### 证据

`schemas/host_member_availability.json`（152 类 / 3902 成员 / errors 0 /
`identity_rejected` 18 / `swept_suspect` 1）、`schemas/unswept_account.json`（33 类终态）、
`schemas/vb_api_catalog.json`（`recipe_unreliable` 4 类）、`_p12u_gate/r48/name_verdicts.json`、
`_p12u_gate/r48_run2.log`。

---

## R49 —— 先全选再取几何 + 验身闸门误放率 + 取法不可照抄上产品面（2026-09-15，✅ 已完成）

### 条目与结果

| # | 条目 | 验收句 | 结果 |
|---|---|---|---|
| **R49-1** | **先选中再取** | 152 → ≥160，或给出"选中也取不到"的证据 | ✅ **155 类**（+`ISEdge`/`IVEdge`/`IVFace`）；未达 160 → 29 类逐类终态齐备 |
| **R49-2** | **验身闸门误报率** | 误报率有数（<10% 或说明为何不能更低） | ✅ 抽样 **40 类**：自类通过 **40/40**，跨类 **120 次误放 0（0.0%）** |
| **R49-3** | **recipe_unreliable 上消费面** | 一处可查 + 测试 | ✅ `scflowpre_api.unreliable_recipes()` + 面板「Host 边界…」增列 |

### R49-1 先全选再取

`GetSelected<X>` 系列只在**有选中**时给对象。取实例前把 `Doc` 上的 `SetSelectAll*`
逐个打上（布尔参数全给 `True`），于是 R48 里"取法都在、调用也成功，就是返回空"的几何类
开始出货：

| 类 | 取法 | 成员 |
|---|---|---|
| `ISEdge` | `Doc.GetSelectedSEdges` | 6，**0 未知** |
| `IVEdge` | `Doc.GetSelectedVEdges` | 6（新增 2 条未实现：`GetPart`/`IsEqual`） |
| `IVFace` | `Doc.GetSelectedVFaces` | 11，**0 未知** |

`ISFace` 也拿到了对象（手册页 **0 成员** → 进 `no_member_classes`）；`ISVertex` 仍取不到
（终态 `needs-corpus`）。

**留痕**：打不上全选的成员要留原因（`selection_prime_errors`）—— 实测
`SetSelectAllVFace` 两参版被拒，退到一参版（手册口径"少不报"）才通过。

### R49-2 验身闸门误放率

判据是"该类**独有成员**的解析率 ≥ 半数"。此前只有"拦住了什么"的记录
（`identity_rejected`），没有"会不会放错"的数。`audit_identity_guard()` 在**真对象**上做
跨类对照：拿 A 的对象去验 B 的独有成员。

| 指标 | 值 |
|---|---|
| 抽样类数 | **40** |
| 自类通过（不过 = 误杀真对象） | **40/40** |
| 跨类尝试（A 的对象 × B 的独有成员） | **120** |
| 误放（拿别家对象也被认作此类） | **0**（rate **0.0**） |

> 口径说明：误放率 0 只说明**在这批真对象上**判据没松到放行别家对象；
> 它不排除"两个类独有成员高度重叠"的极端情形 —— 那种情形下判据本就无从分辨，
> 而 `swept_suspect`（整类未知过半）是第二道闸。

### R49-3 取法不可照抄上产品面

`automation/scflowpre_api.unreliable_recipes()`（类 → 证据）→ 面板
`render_host_boundary()` 新增一节「取法不可照抄的类」（`nav_panels.HostBoundaryDialog`
里可见）。目录里的 `recipe_unreliable` **4 类**（`CondCoSim`/`DiffusiveSpecies`/
`Table`/`CondParticleCounter`），证据来自验身否与整类拿错对象。

### 回归

全量回归 **1536 passed / 4 skipped / 0 failed**（572.87 s，带 `-rs` 一并落盘 skip 原因：
`test_material_prp_write` 1 + `test_native_bridge` 3，全是稳定环境项；R48 收口同口径 1525/4/0，
增量 +11 = 本轮新模块 11 项）。新增测试 1 个模块 `test_r49_evidence.py`（11 项：
全选前置与留痕/误放率与判据/产品面对账）。

### 证据

`schemas/host_member_availability.json`（155 类 / 3925 成员 / 未实现 27 / errors 0 /
`guard_audit` / `selection_primed` **9 条** / `selection_prime_errors` 空（两参版被拒后
退到一参版，9 个全选成员最终全部打上））、
`schemas/unswept_account.json`（29 类终态）、`schemas/vb_api_catalog.json`
（`host_absent` 27 / `recipe_unreliable` 4 类）、`_p12u_gate/r49/name_verdicts.json`、
`_p12u_gate/r49_run2.log`。

---

## R50 —— 提案（≈1 人日）

### 依据

* 覆盖 155/199 = **78%**，剩下 29 类里 **25 类**是 `needs-corpus`（取法试过、返回空）——
  继续扩面的边际收益已经很低（本轮 +3 靠的是"先全选"这种**流程前置**，不是名字）；
* `guard_audit` 只量了**误放**（0/120），**误杀**（真对象被否）只有"自类通过 40/40"这一面 ——
  样本全是最终留下的对象，天然是"通过了的"，需要**故意构造边界样本**才能量误杀；
* `host_absent`（27 条）与 `recipe_unreliable`（4 类）已经三处可查（API/文档/面板），
  但**没有一处**把"这条成员为什么被判未实现"的**原始证据**（哪台机器、哪个工程、
  哪次运行）串起来 —— 复验时只能翻日志。

### 条目

| # | 条目 | 做法 | 验收句 | 人日 |
|---|---|---|---|---|
| **R50-1** | **边界样本量误杀** | 构造"合法但独有成员少"的对象（如 1-2 个独有成员、解析一半）量判据在边界的行为 | 误杀/误放各有数，且给出阈值建议 | 0.5 |
| **R50-2** | **证据可复验串** | `host_absent`/`recipe_unreliable` 条目带上 `evidence_run`（轮次+日志+工程集） | 任取一条能追到某轮某日志 | 0.25 |
| **R50-3** | **普查收口声明** | 覆盖率达到"可宣告收敛"的口径（剩余类全部终态 + 边际收益 < 1 类/轮） | 文档一处宣告 + 测试锁住（覆盖率不许回落） | 0.25 |

### 明确不做

* 不再为覆盖率找新机制（除非 R50-3 的收敛判据被推翻）；
* 不动 `host_absent`/验身判据（`GetIDsOfNames` 与"独有成员半数"仍是唯一证人）。

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
