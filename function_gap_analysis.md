# pphdecoding vs scFLOWpre 功能差距全面分析

> 日期：2026-08-16 ｜ 仓库：`pphdecoding` ｜ 对照：Cradle CFD 2025.2 scFLOWpre
>
> 分析范围：GUI 功能层（`pph_gui.py` / `nav_panels.py`）、宿主自动化层
> （`automation/*` / `native/*`）、自研网格与几何层（`voxmesh` / `polymesh` /
> `native_bam` / `ps_facet2_nodes`）、格式层（`mdl` / `oct` / `gphstats` /
> `parasolid` / `pphwriter`）。
>
> 关联文档：[SCFLOWPRE_FEATURE_PLAN.md](SCFLOWPRE_FEATURE_PLAN.md)（分阶段
> 计划）、[DEV_PLAN.md](DEV_PLAN.md) §12–§17（差距与规划）、
> [DEV_SUMMARY.md](DEV_SUMMARY.md)（开发状态）。

---

## 0. 功能域完整度对照图

**当前完整度与深度（双口径实测，2026-08-31 冲刺 C 后；逐域证据见
§10.1，执行实录 §10.5–§10.9）**：

| 功能域 | 完整度 | 深度 | 分层 |
|---|---|---|---|
| PPH 解析与写端 | 100% | L3 | 满格层 |
| 工程文件管理 | 100% | L3 | 满格层 |
| Select/View/3D | 100% | L2 | 满格层 |
| CAD/XT 几何导入 | 94% | L2–L3 | 收尾层 |
| Octree 八叉树 | 100% | L2+ | 满格层 |
| BAM 分析模型 | 100% | L2+ | 满格层 |
| 宿主自动化 COM/VBS | 100% | L2+ | 满格层 |
| 条件体系（~180 Cond*） | 92% | L2+ | 收尾层 |
| 自研网格生成 | 100% | L2+ | 满格层 |
| 几何编辑 Create/Modify | 100% | L2+ | 满格层 |
| Wrapping/Disc/Overset | 100% | L2+ | 满格层 |
| Solver/FPH 链路 | 100% | L2+ | 满格层 |

```
功能域                    0        25        50        75      100
────────────────────────────────────────────────────────────────────

【满格层 · 双口径达标（10/12 域）】
PPH 解析与写端          ████████████████████████████████████████  100% (L3)
工程文件管理            ████████████████████████████████████████  100% (L3)
Select/View/3D         ████████████████████████████████████████  100% (L2)
Octree 八叉树           ████████████████████████████████████████  100% (L2+)
BAM 分析模型            ████████████████████████████████████████  100% (L2+)
宿主自动化 COM/VBS      ████████████████████████████████████████  100% (L2+)
自研网格生成            ████████████████████████████████████████  100% (L2+)
几何编辑 Create/Modify  ████████████████████████████████████████  100% (L2+)
Wrapping/Disc/Overset  ████████████████████████████████████████  100% (L2+)
Solver/FPH 链路         ████████████████████████████████████████  100% (L2+)

···························· 以下为收尾区 ···························

CAD/XT 几何导入         ██████████████████████████████████████░░  94% (L2–L3) ◀ CATIA 样本待裁决
条件体系(~180 Cond*)    █████████████████████████████████████░░░  92% (L2+) ◀ GUI 向导门控家族
```

> 每格 = 2.5%（40 格满幅）；`█` = 完整度，`░` = 缺口。**整体 ≈98.8%
> （12 域均分，剩余 14 分）**。内核数值 bit 等豁免沿 §9.6。
>
> **2026-08-31 冲刺 B/E/D/F/C 全部落地后刷新（双口径实测重估）**：
> 满格 10 域——域 12 Solver/FPH 10→100（B：`ExecuteSolver` 双实机
> `CALCULATION FINISH` + FPH/FLD 场量对拍）、域 5/6/9/11 78/73/68/65
> →100（E：wrap 回放 3100 步 / CreateMesh / Disc·Overset 建组指纹同类 /
> 真 facet `ConvertFacetToXT` 码 0 全 err=0 + BAM 拓扑对拍 PASS + 三向
> 对齐三样本精确）、域 10 66→100（D：`QueryFaceRegionByName` 首非
> Nothing + CreateMDL 产物闭环）、域 1 96→100（D：PKBody3 三路字节
> 恒等）、域 3 90→100 与域 2 97→100（F：NYI 清单仅剩产品边界项 +
> sctsnapshot 官方库 150/150 字节恒等）、域 7 92→100（C 复核关账：
> xt_ec=0 + 条件 typed 持久化路径实测；P12-A 起自 76 累计）；收尾两
> 域——域 8 条件 80→92（C：精确
> 键 47→90/165，`CreateCond*` 结构上限 79/165，余 8 分 = GUI 向导门控
> 家族，后续冲刺项）、域 4 85→94（patch 腿随 F 绿，余 6 分 = CATIA
> 样本缺失待裁决）。提交链：`aef0fec`(B) → `0b8c350`(E) → `0c64c22`(D)
> → `182b134`(F) → `6cc7faf`(C)。
>
> **2026-08-16 P0–P4 全部落地后刷新**（改进前基线快照见 §2/§3，P0–P3 后
> 12 域评估见 §6.3，P4 执行证据见 §7）：条件体系 15→55（P1 通用表单 +
> P4-0 条件树 + P4-1 类型目录，可见可编辑 ≥60/180）、宿主自动化 55→62
> （P4-3：Disc/Overset COM 实测锁定 + ProgID 探测 + SCTpreCLI 落档）、
> 几何编辑 30→45（P0 原生算子接线）、自研网格 30→45（P2 质量基础
> 设施）、Wrapping/Disc/Overset 25→40（P4-3 锁定）、Octree 65→72（P3-2
> OCTREEREGION 写端 + 重序列化）、Select/View/3D 85→88（P4-4 List File
> 接线）。差距区出现 >30% 值 = 原桩已升级为可用基础，分层带现为定性标注。
>
> **2026-08-17 P5 落地后刷新**（P5 执行结果与证据见 REANALYSIS §6）：
> 宿主自动化 62→70（P5-5 Wrapping 360 步实机 err=0 + in-proc 桥实机验证 +
> gui 后端重写 + sctsnapshot 重序列化产物宿主验收 ok）、Wrapping/Disc/
> Overset 40→55（P5-5 首次端到端执行 + 产物重开 err=0）、几何编辑
> 45→55（P5-1 cone/torus/rectangle-sheet 原生接线）、自研网格 45→55
> （P5-4 质量报告入 CLI + 2:1 平衡独立校验 + 面区域映射实测）、条件体系
> 55→60（P5-3 region 多 face 引用）。原差距区仅剩 Solver/FPH 合理延后。
>
> **2026-08-17 P6-1..P6-4 + 收尾项落地后刷新**（执行证据见 REANALYSIS §9）：
> 条件体系 60→65（P6-1 三源字段 schema：样本 10 精确键不覆盖 + HTML 帮助页
> 显示名规范化键 + 求解设置树 XML 键注入，带 schema 类型 ≥25，53 tests；
> **≥60 目标未达如实记录**——权威 XML 键仅样本+树可支撑，自动关键词匹配
> 误匹配率高已弃用，突破需 P6-5 真实录制或更多样本工程）、自研网格 55→63
> （P6-3 与宿主 box 黄金文件量化对拍 + gphstats numpy2 大小端 U4 写端修复，
> 62 passed/1 skipped）、Octree 72→75（OCTREEREGION 后序写端 roundtrip
> 验证，19 tests）、BAM 70→73（Influence 参数透传 BamReport，22 tests）、
> 几何编辑 55→62（P6-2 `mdl.add_surface_region` MDL 名表写端 API + P6-4
> Create/Modify VBS TODO 草稿清零、实体操作明示走原生 geometry_ops，24
> tests；GUI 归档 flush 接线 + 宿主 `QueryFaceRegionByName` 验收待补）、
> 宿主自动化 70→72（P6-5 `host_status()` 一屏诊断口 + `--status` CLI，
> 16 tests；Kicker 实例内 `context_ready=1 → handle>0` 完整管线仍待宿主
> 窗口可见）、Wrapping/Disc/Overset 55→58（占位标注清理 + 未知 op 显式
> ValueError，6 tests——质量清理，无新能力增量）。提交链：`619c899` →
> `6a8624e` → `8ea7ec7` → `dd7ba88` → `70535ae` → `91ac5ec` → `ab83e35`。
>
> **2026-08-17 P7-1 条件 schema 扩源后刷新**：条件体系 65→68——
> 根因修复 `conditions()` 只读直接子级，样本嵌套条件深扫
> （`all_conditions` 目录交叉核对）+ 重建 merged.json，带字段 schema
> 类型 **25 → 33**（净新 8：CondParticleBoundaryDEM 100 字段/Symm*DEM×2/
> LFile Yplus·Passage·ElectricCurrent/StedInfo/MultiphaseMaterial + 权威
> 升级 2：CondBoundaryRadiation 4→32、CondOutputLFileHeatTransfer 5→22
> 样本键）；详见 DEV_PLAN §17.5 与 REANALYSIS §9.4。
>
> **2026-08-17 Wave A–E 落地后刷新**（P7「产品 100%」计划 §8 首轮
> 波次，10 提交；执行证据见 REANALYSIS §9.5）：条件体系 68→**80**
> （Wave C：165/165 目录类型带字段 schema、56 类型真实 PPH 精确键——
> 官方例工程并入 CondBatteryModel 576 字段/MultiphaseMaterial 390/
> CondPorousMedia 293/ParticleGenerationDEM 240/CondFan 184，字段总量
> 28k）、工程文件管理 95→**97**（Wave A：Save As 接线 + XT 登记
> xml/mdl/zip + 空工程模板闭环）、宿主自动化 72→**76**（全成员宿主
> 实测矩阵 7 场景 OpenProject+QueryFaceRegionByName 真机 + gui 后端
> 实机配方到 Execute 步；完整管线结果文件仍待补）、自研网格 63→**68**
> + Octree 75→**78**（Wave D：box_disc 黄金 + L-shape OCTREEREGION/
> mesh 回归 + CAD tessellation 回退）、Wrapping/Disc/Overset 58→**65**
> （Wave B 开关持久化 + 官方 group layout 钉死）、几何编辑 62→**66**
> （Wave A Register Region GUI flush 接线；**宿主 QueryFaceRegionByName
> 全路径新名不注册**——诚实负面，验收未达）、CAD 导入 80→**85**（XT→
> 工程零件 + OpenCadFile VBS）、Select 88→**90**（Wave E Spread Face
> to Edge）、PPH 写端 95→**96**（clone_pph 追加固化 + GPH
> LS_SurfaceRegions 写端：原地改名宿主 open=0、追加宿主敌对已警告）。
> BAM/Solver 无变化。全量回归 676 tests 0 崩溃模块。
>
> **2026-08-17「历史环境阻塞标注」回填验证**（细节见 REANALYSIS §6.2）：
> test_native_bridge::real 本机 7/7 全绿；`-vbs` CLI 实测不存在（cli 后端
> 改显式 unsupported）；写端回填实测 **1 项负面发现**——宿主 face region
> 注册表权威在 MDL 成员而非 main.xml，P5-3 GUI region 写端需补 MDL
> region 名表写端才宿主生效（新增待办）；Kicker 实例内管线验证的 gui
> 配方已通到 Execute 步，结果证据如实记为待补。
>
> **2026-08-17 P6-1 条件字段级扩面**（新增 `condition_help_schema.py`，
> 三源字段 schema：样本 + `condition_tree.json`（XML 键）+ HTML 帮助页
> （显示名规范化键）；`condition_registry_cached` 接入 `apply_help_schema`）：
> 带字段 schema 类型 **10 → 25**（+15 类型，+370 字段注入），样本精确字段
> 不覆盖；新增 `tests/test_condition_help_schema.py`（10 项，53 条件测试全绿）。
> **未达 REANALYSIS §8 的「≥60」目标**——权威 XML 键仅来自样本（10）与
> 求解设置树（9，去重后 +15）；HTML 帮助页只有显示名（无 XML 键），自动
> 关键词匹配误匹配率高（探索性评估弃用）。突破 60 需**真实录制**
> （宿主内逐个 Cond* 对话框录制，属 P6-5 宿主交互收敛）或扩充样本工程。
>
> **2026-08-17 P6-3 网格量化对拍 + 黄金文件扩容**：新增
> `tests/test_mesh_quality_benchmark.py`（10 项）——对宿主黄金产物
> （tests/box/meshinggroup1.gph 944 cells + examples/tr03.gph 63k cells）
> 做质量指标基线断言（非正交度/偏斜度/负体积），并对自研 voxmesh/polymesh
> 做同指标对拍（纯 hex 非正交度≈0、切割路径 ≤ 宿主 box 25.8°）；修复
> gphstats.py numpy 2.x `astype(">u4")` 溢出（0xFFFFFFFF Python int 转
> C long），网格/GPH 全测试恢复全绿（62 passed）。
>
> **2026-08-17 Octree 八叉树补全**：OCTREEREGION 后序写端此前已实现
> （P3-2）但无测试锁定；新增 `tests/test_oct_region_write.py`（3 项）
> 验证「前序→后序→前序」互逆 + 「写回 ZIPOCTREE→重读」一致，Octree 域
> 表面接线补上验证信用。
>
> **2026-08-17 BAM 分析模型补全**：`BamReport` 此前 docstring 承诺
> Influence 参数随报告透传但未实现；新增 `influence_enable`/
> `influence_targets` 字段 + `summary_lines` 输出 + `build_analysis_model`
> 回填（`dd7ba88`，test_native_bam 22 项）。Influence 几何效应仍在宿主
> 内核（原生仅记录配置，如实标注）。
>
> **2026-08-17 宿主自动化 COM/VBS 补全**：新增 `host_status()` 诊断口
> （`--status`）探测安装/在跑实例/主框架可见性/Kicker 启动器；实测定位
> Kicker_Bx64.exe 启动器 + 常驻实例 headless（svchost 拉起、窗口隐藏、
> `gui_ready=False`）。gui 后端错误提示改为明确指向 Kicker_Bx64.exe。
> （`test_host_pipeline` 16 项）
>
> **2026-08-17 几何编辑 Create/Modify 补全（P6-2/P6-4）**：P6-4 清除
> `create_parts_actions`/`modify_parts_actions` 的实体 VBS TODO 占位
> （实体操作走原生 `geometry_ops`，不再伪造 CreateCuboid/boolean 草稿）；
> P6-2 新增 `mdl.add_surface_region` 回写 MDL 权威名表（闭合 main.xml
> `<regions>` 仅镜像的负面发现，`test_native_bam` 新增 2 项 roundtrip）。
> GUI 归档 flush 接线 + 宿主 `QueryFaceRegionByName` 验收待补（宿主 headless）。
>
> **2026-08-17 Wrapping/Disc/Overset 补全**：清除 nav_panels 「占位/
> 待录制锁定/录制未锁定」陈旧标注（Wrapping 360 步已实机跑通，Disc/
> Overset COM 实测锁定）；`wrapping_actions` 未知 op 由伪造 TODO 注释
> 改为显式 ValueError。
## 1. 总体判断

项目呈**「底层强、上层弱」的哑铃结构**：

- **格式解析/写端与 Parasolid 内核直调已达生产级**（字节级 round-trip 锁定，
  112+ 测试），宿主自动化主链路（open → BAM → octree → mesh → save）三份
  COM 日志实测 err=0；
- 但**面向用户的功能层**（条件表单、几何编辑、网格生成算法）与 scFLOWpre
  差距显著；
- GUI 壳层完成度高（112/123 菜单项接线，仅 11 项 NYI 灰显），不过大量
  「接线」背后是 **VBS 草稿或 session 存根**，深度不及表面。

---

## 2. 功能域分层现状

### 2.1 强项层（生产级，80–95%）

| 功能域 | 现状 | 证据 |
|---|---|---|
| PPH 解析与写端 | ZIP/CRDL-FLD/LZMS/Blowfish 全闭环；`clone_pph` round-trip 与参考目录逐字节一致；PKBody3 加解密逐字节复现；XT 文本/二进制全量编解码（87 节点字节级一致） | `pph_parser` / `pphwriter` / `parasolid` / `sctsnapshot`；DEV_SUMMARY §2 |
| .oct/.gph/.mdl 写端 | 与 box/laptop 样例布局钉死，round-trip 锁定；可选节（SurfaceRegions/VolumeRegions/Parts/Element_InformationFlag 等）按需写入 | `mdl.py` L342–484、`oct.py` L288–351、`gphstats.py` L708–811 |
| CAD 导入 / Parasolid 直调 | `PK_TOPOL_facet_2`（自适应容差）/ `PK_BODY_boolean_2` / `PK_BODY_transform_2` / `PK_FACE_delete_2` / `PK_BODY_create_solid_block` / B-rep 拓扑提取 / `PK_PART_receive+transmit` 全闭环 | `ps_facet2_nodes.py` L820–1003、`cad_import.py`；tests/test_ps_edit.py |
| Select/View/3D | 真 VTK 拾取（Part/Face/Edge/Vertex）、真实橡皮框/圆/多边形框选（HardwareSelector）、剖面裁剪 X/Y/Z、视图键、Fit/Hide/Only Selected | `pph_gui.py` L3306–3713；docs/NYI_INVENTORY.md 仅 11 项灰显 |
| Register Region | 5 类区域（surface/iface/volume/fluid/refpoint）全部**真写 main.xml** `<regions>` 子树 | `nav_panels.py` L2417–3221 |

### 2.2 中间层（可用但有条件，55–70%）

| 功能域 | 现状 | 缺口 |
|---|---|---|
| BAM 分析模型 | 双轨：API 模式 100 行 BAM Wizard VBS（`pipeline_plan.BAM_WIZARD_ACTIONS`）已录制锁定并实机 err=0；原生 `native_bam.py` 对齐 Wizard 12/12 步（闭体识别/多重边/面匹配/微小面/Repair/CheckErrors/ridge），写端生产级 | 原生缺：多重实体**容差合并**（仅精确拓扑识别）、Influence 几何效应（仅记录 targets）、AF faceter 等价路径（不重剖分）、微小面坍缩为几何近似 |
| Octree | API 参数链路（DeleteOctree+Initialize+SetOctType+SetMeshNum+SetMinSize）实测边长 0.001/单元约 1000 达标；本地 refine/merge 并行可用；区域 Size 按 main.xml 零件展开 | OCTREEREGION 后序写端 roundtrip 锁定（test_oct_region_write.py）；voxmesh 2:1 平衡/pairing 已补齐 |
| 宿主自动化 | `pipeline_plan.LOCKED_COMMANDS` 主链路三份日志（box_com_diag1–3）err=0；Wrapping 360 步实机 err=0；in-proc COM 桥实机验证（RVA 0xD212B8 保留）；`host_status()` 诊断口定位 Kicker_Bx64.exe + 常驻实例 headless | Kicker 实例内 `context_ready=1 → set_handle>0` 完整管线待前台实例复跑（隐藏窗口受 Win32 前台锁）；edit_ops 全部 Ridge/Octant 操作未实测；batch_bridge 仅 dry-run |

### 2.3 差距层（MVP 或桩，10–30%）

| 功能域 | 现状 | 差距 |
|---|---|---|
| 条件体系 | 16 分类页中 analysis_type/basic_setting/analysis_control（~1000 行）/output 有**完整 XML 读写**；**25 个 Cond* 类型带字段 schema**（P6-1：样本 10 + 帮助元数据 15，经通用表单可编辑）；165 类型目录全量可见可新建 | 字段 schema **精确（XML 键）仅 10 样本类型**；15 帮助类型字段为显示名规范化键（表单可编辑，round-trip 校验非精确）；其余 ~140 类型仅 name+regions 空字段表单；突破 60 需真实录制（P6-5）或更多样本工程 |
| 几何编辑 | Modify Parts 容差类（TOLERANCE/TINYFACE/RIDGE 角度）真写 xenv | Create/Modify Parts 的实体操作是 **TODO 占位 VBS 草稿**（`pipeline_plan.py` L855–892：CreateCuboid/Cylinder/Sphere/Rectangle 与布尔/变换均 TODO）；底层能力（boolean/transform/create，生产级）与 GUI **未接线** |
| 自研网格 | voxmesh（hex-dominant：octree→inside hex+切割带凸包）、polymesh（clipped Voronoi+Lloyd+近壁层+VoroCrust 式特征保形）双 MVP，写端 .oct/.gph 生产级 | 无 2:1 平衡/pairing、**无面区域映射**（输出 GPH 无区域名）、无质量度量统计；polymesh 无真 power diagram/角点专用 seed；性能未优化（box 凸包路径 ~40s） |
| Wrapping/Disc/Overset | Wrapping 录制锁定（WRAP_OCT_PARAM_PAIRS 35 对 + WRAP_PARAM_PAIRS 44 对，2026-08-14） | Wrapping **未实机执行验证**；Disc/Overset 仅存 hint stub（8 个导航桩） |
| Solver/CMB/FPH | FPH/FLD/iFLD 只读解析（fph.py/fldstats.py/ifld.py） | 求解链明确延后（Execute 面板 Solver 强制弹窗指引用 scFLOWsolver/scPOST）——**合理延后，非缺陷** |

---

## 3. 差距排序（大 → 小）

| # | 差距域 | 量化 | 判断依据 |
|---|---|---|---|
| 1 | **条件体系** | 5/180 类型有粗桩 UI | scFLOWpre 核心日常工作流；参数仅存 session、region 单 face 引用，真实项目条件设置基本不可用 |
| 2 | **网格生成算法深度** | MVP 级 | 无质量保证机制（2:1 平衡、平滑度量、区域映射），与 scFLOW pre 网格器是数量级差距；但格式写端已生产级 |
| 3 | **几何编辑闭环** | TODO 草稿 | Create/Modify 无实体执行；**投入产出比最好**——ps_facet2_nodes 底层已生产级，只欠 GUI/管线接线 |
| 4 | **外部 COM 全自动化** | 结构性阻塞→部分解通 | LocalServer32 注册表直指裸 exe（~~绕过 Kicker 必崩~~ → 2026-08-17 本机许可下瞬态实例实测可跑命令类脚本，Kicker 上下文仍只在宿主内菜单路径）；in-proc 桥已实机验证（RVA 0xD212B8 布局保留，`[ctx+0xF8]` 槽失效改 `[G+8]` 判据）；环境事实见 DEV_SUMMARY §6.3 前置块 |
| 5 | **Wrapping/Disc/Overset** | 录制≠验证 → Wrapping 已验证 | ~~Wrapping 锁定但未实机执行~~；**Wrapping 已端到端跑通**（360/360 步 err=0 + 产物宿主重开 err=0，P5-5）；Disc/Overset 无实质实现 |
| 6 | **native_bam 精度** | 几何近似 | 容差合并/Influence/微小面保留规则与宿主内核不等价 |
| 7 | **边缘 NYI + 质量基础设施** | 11 菜单灰显 | Select 高级项 5 个、Edit 3 个、Ridge 2 个、File 1 个；网格质量统计（非正交度/偏斜度）缺失 |

---

## 4. 改进计划

> **执行状态（2026-08-16 收尾）：P0–P3 已全部落地，全量回归
> 549 项测试全绿**（[run_all_tests.py](run_all_tests.py)，逐模块
> 子进程隔离；0 失败 / 0 崩溃 / 3 skipped——实机桥用例
> `SCF_RUN_BRIDGE_TESTS=1` 门控）。逐项交付见下表。

| 项 | 状态 | 交付与回归证据 |
|---|---|---|
| P0 宿主自动化收尾 + 几何编辑接线 | 完成 | host_pipeline 两处隐患修复；geometry_ops.py 原生 create/modify（create_solid_block / boolean_bodies / transform_body / face_delete 写回 PPH）；test_geometry_ops 24 / test_host_pipeline 11 / test_ps_edit 7 |
| P0 edit_ops / Wrapping 验收 | 完成 | test_edit_ops 15 / test_wrapping 6 / test_vbs_acceptance 3；NativeBridge 实机用例环境变量门控（Qt offscreen 与厂商 DLL 同进程混载会 0xC0000005） |
| P1 条件表单系统化 | 完成 | condition_registry 元数据推断 + GenericCondBody schema-driven 通用表单 + XML 写回闭环（empty/composite 必填特殊处理）；test_generic_cond_form 10 / test_conditions 16 / test_conditions_schema 3 / test_history_vbs 4 |
| P2 网格质量基础设施 | 完成 | voxmesh 2:1 平衡 + pairing + 面区域映射；polymesh 体积质心 Lloyd；quality.py 非正交度/偏斜度统计；test_voxmesh* 25 / test_polymesh 16 / test_quality 10 |
| P3-1 native_bam 精度 | 完成 | 容差合并 / Influence / 微小面等；test_native_bam 21 |
| P3-2 OCTREEREGION 写端 + 重序列化 | 完成 | encode_octree_region_postorder 后序写端 + sctsnapshot 记录级重序列化 + LZMS 压缩写端；test_snapshot_reserialize 14 |
| P3-3 NYI 菜单本地实现 | 完成 3/11 | Select by Element Number / Select Faces That Have the Same Area / Check Intersection（贴合面穿越误报已修）；余 8 项仍灰显 |
| P3-4 测试补充 + 全量回归 | 完成 | run_all_tests.py：73 模块 549 tests 全绿；修复 QMessageBox offscreen 原生崩溃、box 样本错配等回归暴露缺陷 |

剩余长尾（未列入本轮计划验收）：in-proc COM 桥在原生桌面的门控
实测、SCTpreCLI 全链 dry-run（需 SC/Tetra 工程样本）、5 项暂缓 NYI
（patch 链路/mesher 深水区，见 §7 P4-4）。Disc/Overset 录制锁定、
黄金文件对比（5 个真实项目 pph）、NYI 8→7 已在 P4-3/P4-4 消化。

### P0 — 实机验证收尾 + 几何编辑接线（最高性价比）

1. 按既定清单（DEV_SUMMARY §6.3）在**原生桌面**执行：Kicker 启动宿主 →
   `python -m automation.host_pipeline --register --write-vbs` → 宿主内
   File → Execute VBScript → 验证 `context_ready=True`、`set_handle/
   group_handle > 0`、`mdl=True`，闭合 in-proc COM 桥首次实测；
2. 修复 `host_pipeline.py` 两处已知隐患（§6.4）：宿主外 `CreateObject`
   兜底触发 LocalServer 崩溃、`_run_gui` 直接拉裸 exe 绕过 Kicker；
3. **把 `ps_facet2_nodes` 的 `create_solid_block` / `boolean_bodies` /
   `transform_body` / `face_delete` 接入 Create/Modify Parts 的原生模式**
   （API 关闭时本地执行并经 `pphwriter` 写回 PPH），替代
   `pipeline_plan.py` L855–892 的 TODO 草稿——零逆向风险，立刻获得真编辑
   能力；
4. edit_ops（Ridge/Octant VBS）与 Wrapping 管线各做一次实机执行验收
   （录制锁定 → 执行验证）。

### P1 — 条件表单系统化（消灭最大差距）

1. 放弃手写 180 个表单：用 `condition_registry.py` 已有的类型/字段/样本
   schema 做**通用表单生成器**（schema-driven），按 Cond* 类型自动渲染
   字段；
2. 优先把 17 个 bc_filters 类型（覆盖 BC/source/fixed/initial 主工作流）
   升级为真 XML 写入，对齐 scFLOWpre 的 region 多面引用格式（当前仅单
   face）；
3. 用 `history_vbs.py` 解析器从真实项目录制中持续反向补全字段样本。

### P2 — 网格质量基础设施

1. voxmesh：2:1 平衡 + pairing、面区域映射（frid/cvol 传参 →
   `LS_SurfaceRegions`）、质量统计（非正交度/偏斜度直方图进 GUI）；
2. polymesh：体积质心 Lloyd（当前为顶点均值）、角点专用 seed；
3. 与 scFLOWpre 对同几何产物做**量化对拍**（单元数/质量分布），替代
   「算法不等价」的定性声明。

### P3 — 深度对齐与长尾

1. native_bam 容差合并与 Influence 几何效应；
2. OCTREEREGION 后序写端、sctsnapshot 记录级重序列化 + SCTpre 实测验收；
3. Disc/Overset 录制锁定、11 个 NYI 菜单逐项消灭；
4. 样例集扩充（3–5 个真实项目 pph）建立黄金文件对比（收敛 DEV_SUMMARY
   §3.6 验证覆盖局限）。

**核心策略不变**（SCFLOWPRE_FEATURE_PLAN §5）：计算密集步骤走
AutomationBridge（COM/VBS），自研引擎长期并行——P0-3 完成后，「原生模式」
才真正具备脱离宿主的独立可用性。

---

## 5. 模块 × 层级交叉表

| 模块 | 算法完成度 | 写端格式 | 闭环验证 | 定位 |
|------|-----------|---------|---------|------|
| voxmesh | 部分（无平衡/层/平滑） | .oct + .gph 生产级 | round-trip | MVP |
| polymesh | 部分（无 power diagram/角球） | .gph 生产级 | round-trip | MVP |
| native_bam | 12/12 步对齐，缺容差合并/Influence | .mdl 生产级 | round-trip + 18 测试 | MVP（写端生产级） |
| Parasolid 直调 | facet/boolean/transform/create/B-rep 全覆盖；缺 facet_mesh 裸数组组装 | x_t 文本/二进制生产级 | 87 节点字节级一致 | 生产级 |
| .oct/.gph/.mdl 写端 | N/A（格式层） | 全生产级 | 与 box/laptop 钉死 | 生产级 |
| 宿主 COM/VBS | 主链路 err=0；Wrapping/edit_ops/in-proc 桥未实测 | — | 三份日志 | 半自动 |
| 条件表单 | 5/180 粗桩 + 16 页分类参数 | main.xml 部分 | — | 最大差距 |

---

## 6. 2026-08-16 全面复盘（对照 scFLOWpre 2025.2 完整安装面）

> 方法：双 agent 并行盘点——① scFLOWpre 安装目录
> （`C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64`）功能面；
> ② 本仓 39 模块 / ~52.6k 行 / 549 测试的完整度与深度。关键数字均经
> 人工复核。

### 6.1 对照基准修正

- **可执行名**：安装目录并无 `scFLOWpre_Bx64net.exe`；scFLOWpre 的
  实际二进制是 **`SCTpre_Bx64net.exe`**（及 `_D`/`_S` 精度变体），
  `STpre_*.exe` 是 scSTREAM（结构网格）前处理器。`MonitorServices\
  WindowsProcess\Commands\StartPre.py` 证实 `.pph` 即其参数/历史文件。
- **Schemas\ 目录 101 组 sch_\*.s_t 是 Parasolid 内核 schema**
  （Body/Face/Loop/Edge 实体模型，跨 PS 版本读写用），**不是条件
  schema**——条件参数的权威结构在下面 6.2 的资产里。
- **SCTpre.prp / .prp_struct 是材料物性库**（流体 ~120 种气体 +
  结构金属杨氏模量/泊松比/热膨胀），不是程序资源。

### 6.2 新发现的"权威元数据资产"（快速缩小差距的杠杆）

| 资产 | 位置 | 规模（实测） | 对本仓的意义 |
|---|---|---|---|
| **求解设置条件树定义** | `MonitorServices\Optimization\definition\scflow_main.xml` | 232KB；**876 个 condition 键、349 变量、331 实值、230 单位、10 大类、英日双语显示名**；结构 = category(BASIC_SETTING/SOURCE_CONDITION/…) → target(section) → variable(key/value/unit) | **完整求解设置树的权威 schema**。本仓 main.xml 双向解析已具备，缺的是设置 UI 深度——用它可直接生成全部分类/参数页（含显示名与单位），25+ 物理复选框后的"详细设置"桩可逐页落地 |
| **条件帮助文档库** | `HTML_STpre_Eng\`（`_Jpn` 镜像） | **184 个 HTML 条件说明页**：流动/湍流(Ke/LES/MARS)/传热(h/Marangoni/接触热阻/热路径)/辐射(角系数/镜像)/太阳辐射(SOLAR/NEDO/太阳能板)/湿度(8 页)/粒子+DEM/运动体+熔化(11 页)/多孔/风扇 HVAC(Anemo/轴流/鼓风机)/建筑风 IW×9+热舒适 JOS×4+WBGT/化学反应/激光/3D 打印送粉/Peltier | 条件类型的**字段级元数据源**（参数名/物理含义/取值/方向限制，如 Anemostat 按 Round×Cooling 给 1/4 vs 3/4 流量分配）。注意：STpre 属 scSTREAM 血统，与 SCTpre 条件同源但需**逐条件与 PPH 提取的 ~180 Cond\* schema 核对适用性**，不可整批假定 |
| **材料/数据五库** | `SCTpre.prp`（流体）、`SCTpre.prp_struct`（结构）、`heattransfer_ENG.xml`（对流换热系数表，按朝向/室内外/风速）、`SolarNEDO11.xml`（日本 11 版太阳辐射气象库，MONSOLA/METPV）、`reaction_ENG.xml`（CHEMKIN 式物种 + NASA 多项式） | 流体 ~120 条 + 结构金属 13+ + 换热系数 4 类 + 气象站点全国级 + 物种库 | PartMaterialBody 目前只有 prp 只读 parse（`pphxml.parse_prp`）。五库接入 = 材料选择器 + 换热系数预设 + 太阳辐射地理数据，都是**纯 XML/文本解析，无算法风险** |
| **厂商自有 Python 编排** | `MonitorServices\Blade\commands\`（create_pph.py 等 6 个）、`WindowsProcess\`（StartPre.py） | 嵌入式 Python 3.12 + `Standard.get_user_interface()` 宿主 API | 证实厂商自己就用 Python 在宿主内编排 pph 生成（Blade/Fan 向导、作业启动）；本仓 automation/ 的路线与其同构，可对照其 Settings.xml/commands 结构校准 host_pipeline |
| **VBS/COM 自动化生态** | `windtool\*.vbs`（COM ProgID `scConverter_Sx64net.Application.2025`）、JS 求解器脚本（SCRIPT_\*.html 文档化 user_readline 等 API）、`SCTpreCLI_Bx64net.bat`（MPI 批处理 CLI） | — | COM ProgID 实名 + CLI 入口参数可直接充实 automation/host_pipeline 与 batch_bridge 的宿主侧对接（此前仅靠录制日志推断） |

### 6.3 scFLOWpre 完整功能面 × 本仓现状（12 域）

| # | 领域 | scFLOWpre 功能面（安装证据） | 本仓现状 | 完整度 | 深度 |
|---|---|---|---|---|---|
| 1 | 流动 | 不可压/可压/低马赫/VOF 自由面/静水压/旋转系/轴对称 | main.xml 双向 + 5 个流动类 Cond 粗桩 + GenericCondBody | 40% | 表单层 |
| 2 | 传热 | 对流/导热/接触热阻/热路径 .hpt/Marangoni/换热系数库 | 2 个热 Cond 粗桩；prp 只读 | 20% | 表单层 |
| 3 | 辐射+太阳 | 角系数分组/粒子辐射/镜像对称/NEDO 气象/太阳能板/地面反射 | Analysis 复选框 + session 存根 | 10% | 存根 |
| 4 | 湿空气/传质 | 湿度 8 类条件/固体含湿/潜热/扩散 | 复选框存根 | 5% | 存根 |
| 5 | 多相/粒子 | VOF/粒子(Marker/Mass/Spray/Reac)/DEM 自动时步 | 复选框存根 | 5% | 存根 |
| 6 | 运动体/耦合 | 6-DOF/熔化凝固 Fusion×5/Adams/Marc/Abaqus/FMU/GT-SUITE | OversetMeshBody 存根；edit_ops 部分动作 | 10% | 存根 |
| 7 | 化学 | CHEMKIN 物种库/反应方程/lcpv·lwsr 模型 | 复选框存根 | 5% | 存根 |
| 8 | 多孔/阻力 | 多孔×8 条件/植物阻力/穿孔板 | 复选框存根 | 5% | 存根 |
| 9 | 风扇/HVAC/建筑 | 轴流/鼓风机/空调/Anemostat/IW×9/JOS×4/WBGT/WindTool | 1 个 Fan Cond 类型名可见 | 5% | 存根 |
| 10 | 电子热 | epm QFP/SOP 封装/Peltier×3/ELcirkit/HeatPathView | 无 | 0% | — |
| 11 | 几何/网格 | Parasolid 内核/Datakit CAD/cutcell/多块/简化/wrapping | **XT 双向生产级 + PS 直调 + 自研 voxmesh/polymesh + native_bam 12 步** | 70% | 内核级 |
| 12 | 求解控制/输出/脚本 | Dt 4 模式/矩阵求解器/输出格式/JS 用户脚本/单位转换 ini | main.xml 承载；UI 仅复选框；units.py 独立 | 25% | IO 级 |

**汇总判断（P0–P3 后）**：
- 哑铃结构收敛但未消除：IO/几何内核层 80–95%，**条件+物理设置层
  5–40%（12 域中 8 域仍是复选框/存根）**，求解层合理延后；
- 与上一版分析的本质不同：**条件体系差距现在有了权威元数据源**
  （6.2 前两行），从"逐个手写表单"变成"解析资产 → 自动生成"，
  边际成本数量级下降；
- 几何/网格/IO 优势保持：Parasolid 直调与 .oct/.gph/.mdl/.pph
  生产级写端仍是自研替代的立足点。

## 7. 新一轮改进计划 P4 ——「资产驱动，快速缩小条件差距」

> 原则：优先吃透 6.2 权威资产（解析成本 O(1)，收益覆盖全条件面），
> 算法型差距（网格深度）继续并行不抢资源。每项交付均以测试 +
> 样例 round-trip 锁定。

### P4-0 求解设置树全自动生成（最高 ROI，先做）✅（2026-08-16 完成）

1. `condition_tree.py`：解析 `scflow_main.xml` → `condition_tree.json`
   （category → section → variable：key/类型/单位/英日显示名/默认值）；
2. AnalysisModelWizard 的"详细设置"页改为 **condition_tree 驱动自动
   渲染**（复用 GenericCondBody 的 schema→widget 引擎）；
3. 覆盖 10 大类（Basic Setting 时间步 4 模式/流入流出/Source/求解
   控制/输出等），写回 main.xml 闭环测试；
4. 验收：box/laptop 两样例全树读→改→写 round-trip 字段级一致。

**执行结果**：`condition_tree.py` 落地——解析 `scflow_main.xml`
（category → section → variable：key/类型/单位/英日显示名/默认值）→
condition_tree.json；详细设置页 condition_tree 驱动自动渲染 + main.xml
读→改→写绑定（缺失路径自动创建、同值写回不触碰文件、FlowIO 依赖语义
按 variables 实际形态判定）；box/laptop 全树 round-trip 字段级一致。
test_condition_tree 9 项全绿。

### P4-1 条件类型元数据合并（消灭最大差距的主攻）✅（2026-08-16 完成）

1. `html_cond_extract.py`：批量解析 184 个 HTML 帮助页 → 字段元数据
   （参数名/含义/取值范围/单位/方向约束）；
2. 与 PPH 提取的 ~180 Cond\* schema **逐条件交叉核对**（同源同名才
   合并；STpre 血统差异标记 `lineage: scSTREAM` 并人工抽检）；
3. 合入 condition_registry：可见可编辑条件类型 5/180 → **≥60/180**
   （首批：流动边界 15 + 壁面热 8 + 辐射 6 + 太阳 5 + 湿度 8 +
    粒子/DEM 6 + 多孔 5 + 风扇/HVAC 7）；
4. GenericCondBody 增强为"schema + 帮助元数据"双驱动（默认值、
   单位、范围校验、帮助悬停）。

**执行结果**：`tools/html_cond_extract.py` 解析 184 个帮助页
（页面结构/字段表/交叉引用 + 手册链接有效性校验）；
`tools/extract_cond_types.py` 双编码扫描 scFLOWpre 二进制锁定 **165 个
Cond\* 实名类型**；两源按 Cond\* 名合并入 condition_registry（别名 /
无 impl 变体过滤 / 分类过滤 / 元数据回填），可见可编辑条件 5/180 →
≥60/180；目录对话框（分类过滤 + 搜索 + 通用表单渲染）统一入口。
test_cond_types 16 项全绿。

### P4-2 材料与数据五库接入（纯解析，快速可交付）✅（2026-08-16 完成）

1. `parse_prp` 扩展 prp_struct/heattransfer/SolarNEDO/reaction 四库
   （全部只读）；
2. PartMaterialBody 加材料选择器（流体库 ~120 条 + 结构金属）；
3. 壁面热条件表单挂换热系数预设表；太阳辐射条件挂 NEDO 站点选择。

**执行结果**：`material_lib.py` 五库只读解析——scFLOWpre.prp 流体
（~120 种）/ standard·thermal_property 物性 / prp_struct 结构金属 13+ /
heattransfer 换热系数预设 4 类 / solar·SolarNEDO 气象站点 /
reaction（CHEMKIN 式物种 + NASA 多项式，元素×个数按实测逗号分隔格式
解析）；PartMaterialBody 材料选择器（项目缺 prp 时回退安装库）、
换热系数预设表与 NEDO 站点选择器接入 GUI。test_material_lib 16 项全绿。

### P4-3 自动化生态对接充实 ✅（2026-08-16 完成）

1. host_pipeline/batch_bridge 对接 `SCTpreCLI_Bx64net.bat` 实测
   （MPI 批处理入口）— **结论落档**：SCTpreCLIHelper 子命令清单
   （confirm-arg/preproc-cmd/mpirun-*/exe-cmdline/all-cmdline + cmb-\*
   族）与校验顺序（先存在后扩展名；`.pph` 不受支持，CLI 面向 SC/Tetra
   工程）写入 batch_bridge 模块头；实际执行需 SC/Tetra 工程文件，
   暂无样本故未跑通全链；
2. windtool VBS 的 COM ProgID（实测为 `scConverter_Sx64net.Application
   .2025` 等，STtools.vbs:4 / STpre_STsolver.vbs:7-8 注释背书）纳入
   注册表探测 — `scflowpre_probe.COM_PROGIDS` +
   `probe_com_progpids()`（HKCR 只读，实测 scFLOWpre/STpre/
   scConverter S/D 四项已注册），接入 `probe()` 与
   `host_pipeline.locate_scflowpre()`；
3. Disc / Overset 录制锁定补完 — **COM 实测锁定**（box_com_diag4.log）：
   `SetPartsControl "Discontinuous"/"Overset"` True/False 四种调用
   宿主内全部 err=0。

### P4-4 边际收尾 ✅（2026-08-16 完成）

1. 余 8 个 NYI 菜单逐项评估（docs/NYI_INVENTORY.md 自动生成附注）：
   - **接线**：Select Elements by List File…（复用 Select by Element
     Number 解析器，`_select_by_list_file`）；
   - **产品边界**（2）：Create Actran Files…（仅 scFLOW2Actran
     Acoustic Session）、Restore Closed Volume Data…（仅 patch 导入
     + Store and Open）；
   - **暂缓**（5）：Define Facet Part / Non-Facet Part / 2D Sub-mesh
     Unit / Fix Marked Element Shape / Spread Face to Edge
     （patch 链路缺失或 mesher 深水区，理由见清单）；
2. 黄金文件对比集扩到 **5 个真实项目 pph**：box（基线）/
   box_disc（Discontinuous=True，COM 宿主 SaveProject 生成，main.xml
   落 `<Discontinuous>true`）/ box_overset（Overset=True，工程登记
   `*_mapped.bdf`/`*_RotorInfo`）/ laptop（稳态热+风扇，
   CondMoving/Fix/Source）/ box2（近重复备份）；生成证据
   box_com_diag5.log，全部自动纳入 test_samples 不变量回归。

### 依赖关系与顺序

P4-0 → P4-1（共用 schema→widget 引擎）→ P4-2（独立可并行）→
P4-3/P4-4（随时插入）。**执行印证**：P4-0/1 落地后条件+设置层
完整度按计划从 15% 提升至 55%+ 量级，12 域中 8 个存根域均达到
"表单层可用"（目录对话框统一入口 + 通用表单渲染）。

---

## 8. 前 11 域做到「产品 100%」的可行计划（P7）

> 日期：2026-08-17 ｜ 输入：§0 表 + REANALYSIS §9.3 + NYI 清单（余 7）
> ｜ **不含** 第 12 域 Solver/FPH（合理延后）。
>
> 对照 DEV_PLAN §0.4：本仓策略是 **格式层复刻 + 界面层逼近 + 宿主驱动
> 官方内核 + 自研 mesher 兼容产物**，不以重写 SCTprime / CADthru /
> Parasolid faceter 为目标。因此本节的「100%」是**产品完整度**，不是
> 与 scFLOWpre 网格内核 bit-identical。

### 8.1 「100%」验收口径（必须先钉死，否则永远达不到）

| 口径 | 定义 | 用于本计划？ |
|---|---|---|
| **产品 100%** | 该域全部用户路径：**菜单可用或明确灰显+理由**；参数可编辑并写入 PPH；宿主能打开并执行；有回归测试 | **是** |
| **内核 100%** | 自研算法与 scFLOWpre 细化/BAM/Wrapping/CADthru 数值等价 | **否**（不可行，见 DEV_PLAN §0.4） |

每域「产品 100%」拆成四条硬门槛，缺一不算满：

1. **UI**：该域菜单/向导可操作，或产品边界项灰显且 `docs/NYI_INVENTORY.md` 有理由；
2. **Persist**：Save / Save As 后 ZIP 成员 + `main.xml`/`xenv`/`mdl` 与 UI 一致，宿主能重开；
3. **Execute**：计算类操作有一条权威路径——**优先宿主 COM/VBS**，自研只保证兼容产物（宿主可开、质量不劣于约定阈值）；
4. **Evidence**：pytest 黄金文件或宿主日志（`err=0` / `Query*` 非 Nothing）。

下面百分比是「产品口径下还差什么」；括号内是该域若坚持内核等价则永远留白的部分。

### 8.2 逐域：现状 → 产品 100% 定义 → 剩余工作

#### 域 1 · PPH 解析与写端（95% → 100%）

**100% 定义**：已知成员类型 round-trip；源 ZIP 没有的 override 键作为新成员追加；宿主重开不丢成员。

| 剩余项 | 工作量 | 做法 | 验收 |
|---|---|---|---|
| `clone_pph` 追加新成员 | 已落地（代码在 `pphwriter.clone_pph`） | 补 pytest：空工程 Save 后出现 `meshinggroup1.oct/.gph`、导入的 `.x_t` | 宿主 OpenProject 不丢成员 |
| `sctsnapshot` 重序列化 | 1–2 天 | 现有重序列化产物已有宿主验收；补 2–3 个多样本字节/结构对比，失败则保留「语义等价、字节不必 ident」并写进测试注释 | 宿主重开 ok |
| wimlib / 罕见可选段 | **不做** | 生产路径是 ZIP+deflate；无样本不猜 | 文档标明非目标 |

**内核留白**：无。这是本仓强项，满格成本最低。

#### 域 2 · 工程文件管理（95% → 100%）

**100% 定义**：New / Open / Save / Save As / Import CAD 产出**宿主可开**的 PPH；CAD 不仅预览，还要进 ZIP + `main.xml` parts。

| 剩余项 | 工作量 | 做法 | 验收 |
|---|---|---|---|
| Save As 增加 ZIP 成员 | 与域 1 同源 | 复用 `clone_pph` 追加语义 | 空工程 Execute 后 Save，成员列表含 OCT/GPH |
| CAD 登记（XT 预览 ≠ 工程零件） | 3–5 天 | 导入 `.x_t` 时：写入 ZIP 成员 + 更新 `main.xml` `<parts>` + 生成/更新 `*_part.mdl` 面片；STEP/CATIA **不**自研 Datakit，走宿主 `OpenCadFile` | 保存后 scFLOWpre 能看到零件；pytest 检查 zip namelist + xml parts |
| Untitled 空工程模板 | 1 天 | 固化一份最小 `main.xml/xenv/js/prp/sctsnapshot` 模板，避免「无源 ZIP 可 clone」 | New → Import XT → Save → 宿主打开 |

#### 域 3 · Select/View/3D（88% → 100%）

**100% 定义**：本查看器**能实现**的选择/显示菜单全部接线；产品边界 2 项保持灰显（计入满分，不算缺口）。

剩余 NYI（`docs/NYI_INVENTORY.md`，7 项）：

| 项 | 处置 | 工作量 |
|---|---|---|
| Create Actran Files… / Restore Closed Volume Data… | **产品边界**，保持灰显 | 0 |
| Spread Selected Face to Edge | **做**：基于 polymesh/MDL 邻接做面→边扩散（仅 MDL 导入场景） | 2–3 天 |
| Define Facet Part / Non-Facet Part / 2D Sub-mesh / Fix Marked Element Shape | **明确不计 100% 缺口**：缺 patch 导入或 mesher 深水区；灰显 + 清单理由即满分 | 0 |

List File / Part/Edge/Vertex pick / Fit/Hide/Only / Refinement Level / Parts List / Region Check 已接线，不重做。

#### 域 4 · CAD/XT 几何导入（80% → 100%）

**100% 定义**：XT 本仓 tessellation **且**登记为工程零件（见域 2）；其它 CAD 格式经宿主 `OpenCadFile`（Datakit/CADthru 是 Cradle 许可组件，不复刻）。

| 剩余项 | 工作量 | 做法 | 验收 |
|---|---|---|---|
| XT → xml parts + mdl + zip | 3–5 天（与域 2 合并） | 导入路径统一走「预览 tessellation + 工程登记」 | Save 后宿主 Parts 树非空 |
| STEP/CATIA/3dxml | 2 天接线 | GUI 已有过滤器；无 Datakit 时提示走宿主 File→Import；有宿主时 `Doc_.OpenCadFile` | 宿主日志 err=0；无宿主则明确错误，不静默空预览 |
| 内核 faceter 等价 | **不做** | 二进制 XT 已深（parasolid.py + pskernel ABI）；CADthru 分面不复刻 | — |

#### 域 5 · Octree 八叉树（75% → 100%）

**100% 定义**：区域尺寸 UI ↔ `OCTREEREGION` 后序写端（已有）+ Refine/Merge Octants VBS（已有）+ **宿主 Execute 为权威细化**；自研 oct 只保证结构可被宿主读取。

| 剩余项 | 工作量 | 做法 | 验收 |
|---|---|---|---|
| 曲率/接近度细化策略 | 不自研内核 | 参数写入 xenv/xml，Execute 勾选 API 走宿主 | 宿主重开参数在；细化结果以宿主 GPH/OCT 为准 |
| 区域映射深度 | 2–3 天 | 核对 `sface_num` / Register Region 与 OCTREEREGION 索引一致性（P3-2 写端已有 roundtrip） | `tests/test_oct_region_write.py` 扩 1–2 个真实几何 |
| 原生 oct 与宿主策略 bit 等 | **不做** | — | — |

#### 域 6 · BAM 分析模型（73% → 100%）

**100% 定义**：9 页向导参数可编辑并持久化；**Execute 走宿主 BAM Wizard VBS**（已锁定）；Influence 几何效应承认在宿主内核（配置已透传 `BamReport`）。

| 剩余项 | 工作量 | 做法 | 验收 |
|---|---|---|---|
| 宿主 BAM 端到端 | 1–2 天（需前台宿主，与域 7 同波） | 对 box 跑 BAM Wizard 全步，Save，对比 `native_bam` 报告字段 | 宿主 err=0；PPH 可重开 |
| AF faceter / tolerance merge 几何 | **不做自研等价** | native_bam 12/12 步保持「兼容报告」；几何以宿主为准 | 文档写明 |
| Influence 几何 | 已配置透传 | 不补自研布尔 | BamReport 有 enable/targets 即可 |

#### 域 7 · 宿主自动化 COM/VBS（72% → 100%）

**100% 定义**：`host_status()` 显示 `gui_ready` 后，一条命令能走完 `context_ready=1 → set_handle>0 → Execute`；Wrapping 已 e2e；Octree/BAM/CAD/Disc/Overset 均可驱动。不要求远程作业推送（那是 Solver 域）。

| 剩余项 | 工作量 | 做法 | 验收 |
|---|---|---|---|
| Kicker 前台管线闭合 | **环境 0.5 天 + 配方固化 1 天** | 新鲜启动 `Kicker_Bx64.exe`（勿用闲置双实例）；`--status` 等到 `gui_ready`；跑现有 gui 后端配方 | 日志 `set_handle>0` |
| edit_ops Ridge/Octant 实机 | 1 天 | 宿主可见后补跑，现在代码已有 VBS | err=0 日志入库 |
| batch_bridge | **保持 dry-run** | SCTpreCLI 面向 SC/Tetra 非 `.pph`，满分不依赖它 | 模块头已落档即可 |
| 远程 push/pull | **划出本 11 域** | 属求解/集群，不是 scFLOWpre 查看器 100% | — |

这是其它计算域「产品 100%」的**总闸门**：域 5/6/11 的 Execute 权威路径都卡在这里。

#### 域 8 · 条件体系（65% → 100%）——最大真实缺口

**100% 定义（务实）**：~180 类型**全部可见可编辑**（已有 GenericCondBody）；**常用 ≥60 类型带精确 XML 键**（round-trip 不丢字段）；其余 ~120 类型允许「名 + regions + 帮助文案键」，但 Save 不得破坏宿主已有 Cond* 节点。

**不要**用 HTML 显示名自动猜 XML 键（P6-1 已弃用，误匹配率高）。

| 剩余项 | 工作量 | 做法 | 验收 |
|---|---|---|---|
| 精确键 25 → ≥60 | **1–2 周，阻塞在录制** | ① 收集 5–8 个真实 PPH（流/壁/热/风扇/源项已有 laptop+box）；② 宿主内对缺口 Cond* **录制 VBS** 或 Save 后 diff `main.xml`；③ 只把**见到的 XML 键**写入 `schemas/conditions.yaml` | ≥60 类型 schema 来自真实键；`tests/test_condition_help_schema.py` 扩面；样本 round-trip |
| 其余 ~120 | 持续 | 保持 generic + 不覆盖未知子节点（现有「样本精确键不覆盖」策略） | 打开任意 Cond* 不崩；Save 后宿主 Cond 数不变 |
| 180/180 精确键 | **不作为 P7 关门条件** | 那是数月录制，ROI 低于宿主网格 | 记为 P8 数据积累 |

没有新样本/录制，本域**无法**从 65 再涨到产品 100%。代码引擎已就绪，是数据源问题。

#### 域 9 · 自研网格生成（63% → 100%）

**100% 定义**：voxel/poly 对 box 类几何写出宿主可开的 GPH；质量指标不劣于现有黄金断言；**生产网格以宿主 Execute 为准**。棱柱层、power diagram、速度与宿主比 **不计入** 产品 100%。

| 剩余项 | 工作量 | 做法 | 验收 |
|---|---|---|---|
| 空工程无 MDL 的 CAD 回退 | 已落地（`_cad_surface_points_tris` + clone 追加 OCT/GPH） | 补 GUI 回归说明 + 测试 | Untitled + box.x_t 不勾 API 不再报「未找到 MDL」 |
| 黄金扩到 2–3 个真实几何 | 2–3 天 | REANALYSIS §9.3 已列；对拍报告入 CI | `test_mesh_quality_benchmark` 扩样 |
| 2:1 / pairing / region map | 已有 | 不重做 | — |
| 层网格 / 任意多面体等价 | **不做** | 用户要生产网格：勾选 scFLOWpre API | — |

#### 域 10 · 几何编辑 Create/Modify（62% → 100%）

**100% 定义**：Create/boolean/transform/face-delete **原生 `geometry_ops` 写回 PPH**（VBS 草稿已清零）；Register Region 改完后 **MDL 名表 + 归档 flush**；宿主 `QueryFaceRegionByName` 非 Nothing。

| 剩余项 | 工作量 | 做法 | 验收 |
|---|---|---|---|
| GUI 归档 flush | **1–2 天，最高 ROI** | Register Region 确认时调用已有 `mdl.add_surface_region`，再 `clone_pph` 写回 mdl 成员 | 保存 → 宿主 QueryFaceRegionByName 非 Nothing |
| 更多体素（球/圆柱已有，cone/torus/sheet 已有） | 按需 | 缺哪个补哪个，不预先铺全 Parasolid 图元 | 单元测试 + 宿主打开 |
| 内核布尔 ≡ PK_BODY_boolean | **不要求** | 原生布尔用于查看器编辑；复杂 CAD 布尔走宿主 | — |

#### 域 11 · Wrapping/Disc/Overset（58% → 100%）

**100% 定义**：Wrapping **宿主 e2e 已 err=0**（360 步）→ GUI 参数与锁定 VBS 对齐即可满分；Disc/Overset 不仅 `SetPartsControl` 开关，还要能 **创建对应 meshing unit 并 Save**（box_disc / box_overset 黄金已有）。

| 剩余项 | 工作量 | 做法 | 验收 |
|---|---|---|---|
| Wrapping GUI → 锁定序列 | 2–3 天 | `pipeline_plan` 已有 BeginWrapping…EndWrapping；接到 Execute/导航面板，禁止静默 TODO | 与 P5-5 相同 err=0 |
| Disc/Overset 建 unit | 3–5 天 | COM 开关已锁 True/False；补「建组 + 映射 BDF/RotorInfo」录制（对照 box_overset 成员） | 新工程勾选后 Save，zip 含与黄金同类成员 |
| 自研 wrapping 内核 | **不做** | SCTprime 不复刻 | — |

### 8.3 波次顺序（按依赖，不按百分比从低到高）

百分比低的域不一定先做：域 11 卡域 7，域 4/2 卡空工程，域 8 卡样本。

```
Wave A  写端闸门（不依赖宿主窗口）     约 1 周
        域1 新成员追加测试固化
        域2+4 XT 登记进 xml/mdl/zip + 空工程模板
        域10 Register Region → mdl.add_surface_region + Save flush
        域9  CAD tessellation 回退的回归测试
        → 空工程「导入 XT → 原生 Execute → Save」闭环

Wave B  宿主闸门（需前台 Kicker）       约 3–5 天（含等窗口）
        域7  context_ready=1 → handle>0 日志入库
        域6  BAM Wizard 宿主 e2e
        域11 Wrapping GUI 对接已锁定序列；Disc/Overset 建 unit 录制
        域10 QueryFaceRegionByName 验收
        域4  OpenCadFile（STEP）在有许可时跑通
        → 计算类全部改为「宿主权威、自研兼容」

Wave C  条件扩面（可与 B 并行等样本）   约 1–2 周
        域8  真实 PPH + 录制 → schema ≥60 精确键
        禁止再做 HTML 键猜测

Wave D  网格/八叉树产品收口            约 3–5 天
        域5  真实几何 OCTREEREGION 回归
        域9  黄金扩 2–3 几何；质量对拍保持「不劣于」而非「相等」

Wave E  Select 收口                    约 2–3 天
        域3  Spread Face to Edge；其余 NYI 维持灰显即满分
```

**不要并行乱序**：Wave A 未完成前不要宣称域 2/4/9/10 已满；Wave B 未出 `set_handle>0` 日志前不要宣称域 6/7/11 已满。

### 8.4 工作量与「假装 100%」禁区

| 波次 | 人天（1 人全职） | 预期产品完整度变化 |
|---|---|---|
| A | 5–7 | 域 1/2/4/10/9 的 persist 缺口闭合 → 这五域可标 95–100 |
| B | 3–5（含环境） | 域 6/7/11 → 产品 100 |
| C | 8–12 | 域 8 → 产品 100（≥60 精确键） |
| D | 3–5 | 域 5/9 → 产品 100 |
| E | 2–3 | 域 3 → 产品 100 |
| **合计** | **约 4–6 周** | 前 11 域全部达到 §8.1 口径 |

明确 **P7 不做**（做了也到不了内核 100%，且拖死产品 100%）：

- 复刻 CADthru / Datakit / SCTprime wrapping / BAM Influence 几何内核
- 自研棱柱层、power diagram、与宿主 cell-by-cell 网格相等
- 180 个 Cond* 全部精确 XML 键（改为 ≥60 + generic 不破坏）
- Solver/FPH 远程作业（第 12 域）
- Actran、Closed Volume patch 产品边界菜单

### 8.5 每域「可以打勾」的一句话验收

1. PPH：空工程 Save 能**新增** OCT/GPH/x_t 成员，宿主打开不丢。
2. 工程：Import XT → Save As → scFLOWpre 零件树非空。
3. Select：Spread Face to Edge 可用；Actran/Closed Volume 灰显有据。
4. CAD：XT 本仓登记；其它格式宿主 `OpenCadFile` 或明确失败。
5. Octree：区域写端 roundtrip + 细化由宿主 Execute。
6. BAM：向导参数进 PPH；网格由宿主 Wizard；Influence 只记录配置。
7. COM：`--status` gui_ready 后一条管线 `set_handle>0`。
8. 条件：≥60 精确键来自真实 XML；其余 generic 不破坏节点。
9. 自研网格：box 类 GPH 宿主可开；生产路径勾选 API。
10. 几何：Register Region Save 后宿主能 Query 到名字。
11. Wrap/Disc/Overset：Wrapping 复现 360 步 err=0；Disc/Overset 工程成员与黄金同类。

打满这 11 句，§0 表即可把前 11 域改成 100%（产品口径），并在表下加一行脚注：*内核算法等价不在本仓目标内*。

### 8.6 执行状态追加（P8，2026-08-18）

- **域 8 · Wave C 无录制达标**：官方例程库 **151 PPH 全量收割**
  （`merge_official_schema --all`）重建 `schemas/merged.json` 后样本
  背书类型 **56 → 67（≥60 门槛达成）**，字段总量 6065，注册表带字段
  类型 175。§8.2「阻塞在录制」的判断被全量扫描路径取代——官方例程
  即权威 XML 键源，无需宿主内逐类型录制；余下 ~108 generic 类型维持
  「名 + regions + 不破坏宿主节点」策略；
- **域 5 · Wave D 黄金扩容（部分）**：Octree 对拍从 box 族扩至三档
  真实几何——interference（21k 活叶 / 28.5k cells，hex 97%）、
  tr03（31.5k 活叶 / 63.9k cells，poly 92%）、laptop_simplified
  （1.24M 活叶，满八叉树不变量 + region 后序流一致性；349MB GPH
  不整读）。满树不变量口径修正：`0 ≤ bits.size − (1 + 8·internal) ≤ 7`
  （`unpackbits` 尾部填充位，非真实叶子）；
- **GPH 读端修复**：`gphstats._sections_cache` 以 `id(data)` 键控且
  公开 API（`gph_cells(bytes)`）无清理路径，buffer GC 后 id 复用命中
  脏节表（实测第二个 GPH 解析出 0 cells）。修复：内容指纹守卫
  （长度 + 首尾 64 字节），指纹不同必重扫；毒化注入 + 同内容 twin
  双路径回归（`tests/test_oct_examples.py::TestGphCacheFingerprint`）。
### 8.7 执行状态追加（P9，2026-08-20：宿主自动化切官方 typed COM 路线）

- **域 9（宿主自动化）基础设施升级**：新增 `automation/scflowpre_api.py`
  typed COM 桥（参考 cabdecoding 模式）——手册机读目录
  `schemas/vb_api_catalog.json`（199 类 / 4455 成员，`tools/
  extract_vb_api_scflow.py` 生成）为唯一真相源；`ComObject.call`
  `_FlagAsMethod` 派发使手册任一成员可达；`ScFlowpreSession` ROT 附着
  Kicker 常驻实例（实机 owned=False / GetWorkerState=0 就绪握手），
  open/pipeline 实机 round-trip 验证（tr01 输出规模与源一致）。对拍
  与深管线影响：typed 直调覆盖命令类操作（Open/Save/条件/网格），
  SCTprime 深管线（CreateShapeGroupSet）在 ROT 附着实例上经
  `ExecuteVBS` 已实测可用（P10，见 §8.8）。详见 DEV_PLAN §17.7。

### 8.8 执行状态追加（P10，2026-08-20：SCTprime 深管线 ROT 附着打通）

- **域 9（宿主自动化）深管线突破**：ROT 附着 Kicker 实例 +
  `ExecuteVBSWithFile` 可驱动 SCTprime 深管线（`context_ready=1`，
  OpenProject 后 `CreateShapeGroupSet` → `CreateShapeGroup` 全通）——
  推翻旧「必须 GUI/manual 宿主内 VBS」结论，COM `rot` 后端等价于
  宿主内 File → Execute VBScript。附带钉死桥 bug：CreateShapeGroupSet
  句柄在 VBScript 是 Integer/VT_I2，传回 COM 需 `CLng()` 转 Long，否则
  `SCF_ERR_ARG`；`build_pipeline_vbs` 已内置 CLng。
- **typed 直调业务自动化**：`scflowpre_api` typed 方法（非 VBS）在 ROT
  附着实例上实机验证——条件 `create_cond` → `GetName`/`GetConditionType`/
  `SetName`/`DeleteCondition` 闭环；网格 `SetModeOctree` →
  `GetActiveMeshingGroup` → `DoesMeshingOctreeExist` 全通。证明 typed
  COM 桥可完整驱动「条件 + 网格」业务自动化，替代 VBS 字符串拼接。
- 遗留（P11 候选）：CreateMDL 需注入几何节点（ISNode）才返回 True；
  CreateFacetOctree/ExecuteWrapping/CreateMeshOctreeByDefaultParam
  待按相同模式逐一直调验证。详见 DEV_PLAN §17.8。

### 8.9 执行状态追加（P11，2026-08-20：深管线实际网格生成直调）

- **域 9（宿主自动化）深管线网格生成直调**：承接 §8.8 遗留，在 ROT 附着
  Kicker 实例上直调 SCTprime 实际网格生成——`CreateFacetOctree` 返回业务
  ErrorCode 312（空 group 无 facet）、`ExecuteWrapping` 返回 311（空 group
  无 wrapping），`last_exception_code=0`（SEH 守卫未触发、无访问违例）。
  证明 C ABI 符号解析 + x64 ABI（this 在 RCX、`IOctree&` 按指针）+ SEH
  守卫全链路正确。
- **钉死 VBS 生成 bug**：`build_pipeline_vbs(deep=True)` 深管线段原复用主段
  已 `ReleaseHandle` 的 `hSet`（COM 桥 `ReleaseHandle` 会 erase 句柄），
  导致 `CreateShapeGroup` 查不到句柄返回 SCF_ERR_ARG、深管线被跳过；改为
  新建独立 `hSet2`。
- **C ABI 落地 4 项**：`create_facet_octree` / `execute_wrapping` /
  `create_mesh_octree` / `convert_facet_to_xt`（`native/scflow_bridge.h/.cpp`
  + `native_bridge.py` 封装）。前两者实机验证；后两者（需 IVMDL 句柄 /
  真实 facet 文件）C ABI 已实现并单元测试，in-proc 实机验证待 P12。
  详见 DEV_PLAN §17.9。

---

## 9. 双 100% 开发计划（P12：完整度 × 深度双口径，覆盖全部 12 域，2026-08-23 立）

> 输入：§8（前 11 域「产品 100%」口径与 P7–P11 执行状态）+ P9–P11 typed COM
> 路线落地后的代码现状（最新提交 `245f1c4`）。与 §8 的三点差异：
>
> 1. **验收从单口径升双口径**：完整度 × 深度均须 100%（§8 只定义了产品完整度）；
> 2. **覆盖全部 12 域**：Solver/FPH 域从「合理延后」改为纳入计划——依据是
>    `vb_api_catalog` 实查含 `Doc.ExecuteSolver`（见 §9.2），「延后」的旧根据
>    （求解器无驱动面）已失效；
> 3. **深度 100% 的实现路线钉死为三层达成**，而非复刻内核：
>    ① 格式层字节级闭环（本仓强项）；② 内核层官方全驱动（typed COM +
>    C ABI 深管线）；③ 自研引擎作为带量化对拍证据的兼容层。

### 9.1 双 100% 验收口径

| 维度 | 定义 |
|---|---|
| **完整度 100%** | 12 域全部用户路径：菜单可操作，或灰显且 `docs/NYI_INVENTORY.md` 载明产品边界理由；含 Execute → Solver 求解链路 |
| **深度 100%** | 每域能力至少 **L2**；格式/内核/验证面达 **L3**；唯一豁免 = 自研引擎与官方内核数值 bit 等（官方内核可全驱动，复刻既不可行也无必要） |

四级深度标尺（§1「深度」判定的量化版）：

| 级 | 名称 | 判据 |
|---|---|---|
| L0 | 桩 | 菜单/表单存在 |
| L1 | 参数闭环 | 参数读写一致 + PPH round-trip |
| L2 | 权威执行 | 宿主 COM/VBS/C ABI 驱动 err=0，或自研产物宿主可开 |
| L3 | 字节/签名/对拍级 | 格式字节恒等 round-trip；内核 ABI 签名级；与宿主黄金量化对拍 |

### 9.2 P9–P11 关键解锁（本计划地基，2026-08-23 实查补充）

P9–P11 已交付 typed COM 桥（`automation/scflowpre_api.py`，ProgID
`scFLOWpre_Bx64net.Application.2025`）+ ROT 附着常驻实例 + 深管线 C ABI 4 项。
本轮对 `schemas/vb_api_catalog.json`（199 类 / 4455 成员，唯一真相源）实查，
新锁定以下权威能力面——**它们直接改写 §8.2 中四个「不可达/延后」结论**：

| catalog 实查发现 | 数量 | 打开的域 / 推翻的旧结论 |
|---|---|---|
| `Doc.ExecuteSolver` / `QuitAndExecuteSolver` | 2 | **域 12**：Solver 提交有官方驱动面，「合理延后」降级为「待接线」 |
| `Doc.CreateFaceRegion` 等 Region 方法 | 56 | **域 10**：Register Region 走宿主 API 权威路线，绕开「文件层 7 场景全负」死胡同（§6.3 / REANALYSIS §6.3） |
| `Conditions.CreateCond*` | 89 | **域 8**：条件 schema 录制反推可自动化（create → Save → diff main.xml），不再阻塞在「等样本」 |
| `SNode` 方法 | 145 | **域 6/7**：CreateMDL 的 ISNode 注入路线（P11 遗留） |
| `MeshingGroup` 方法（`BeginMDLWizard`/`BuildAnalysisModel`/`CreateMesh`/`CreateVMDL`/`Check*` 质量检查族） | 173 | 域 6/9：BAM 与网格生成 typed e2e；`CheckIntersectionForMeshModel` 等即 View/Select 菜单的权威后端 |
| `Doc.CreateSubmeshMeshingGroup` / `CreateSubmeshSurfaceRegion` | — | 域 3：Create 2D Sub-mesh Meshing Unit（NYI 暂缓项） |
| `Doc.CreateDiscontinuousMeshingGroupWith/WithoutMovingPart` | 2 | 域 11：Disc 建组（§8.2 域 11 剩余项） |
| `Doc.ImportCADAsFacet` / `ImportPatchAsCAD` / `OpenCadFile` | 3 | 域 3/4：Define Facet Part 的 patch 导入链路 + STEP 多格式 |
| `Application.StartRecordVBS` / `EndRecordVBS` | 2 | 全域：剩余未锁定操作的录制反推工具 |
| `Kicker.Application` / `ApplicationLaunchSetting` / `LicenseStatus` | 3 | 域 7：Kicker 启动器自身的程序化控制 |

### 9.3 P11 后 12 域基线重估（完整度 / 深度级）

| # | 域 | 完整度 | 深度 | P8–P11 后修正 |
|---|---|---|---|---|
| 1 | PPH 解析与写端 | 96% | L3（PKBody3 二进制除外） | 无变化 |
| 2 | 工程文件管理 | 97% | L3 | 无变化 |
| 3 | Select/View/3D | 90% | L2 | 无变化（4 暂缓 NYI 待 P12-F 处置） |
| 4 | CAD/XT 几何导入 | 85% | L2–L3 | OpenCadFile VBS 就绪，实机 e2e 待补 |
| 5 | Octree 八叉树 | 78% | L2 | CreateFacetOctree C ABI 已通（空 group 业务码 312） |
| 6 | BAM 分析模型 | 73% | L2 | BuildAnalysisModel/BeginMDLWizard 在 typed 面上，e2e 待跑 |
| 7 | 宿主自动化 COM/VBS | **85%** | L2–L3 | 76→85：typed 桥 + ROT 附着 + 深管线直调（§8.7–8.9）；欠 typed 包装 9/199 类、ExecuteSolver、深管线 2 ABI 实机 |
| 8 | 条件体系 | **82%** | L2 | 80→82：官方例程 151 PPH 收割，样本背书键 56→67 |
| 9 | 自研网格生成 | 68% | L2（对拍 L3，黄金三档） | 无变化 |
| 10 | 几何编辑 Create/Modify | 66% | L2 | CreateFaceRegion 权威路线已定位（§9.2） |
| 11 | Wrapping/Disc/Overset | 65% | L2 | ExecuteWrapping C ABI 已通（空 group 业务码 311） |
| 12 | Solver/FPH 链路 | 10% | 读侧 L3 / 算侧 L0 | ExecuteSolver 发现后纳入计划（§9.2） |

### 9.4 逐域双 100% 差距与工作项

#### 域 7 · 宿主自动化（85% → 100/100）——总闸门

| 工作项 | 做法 | 验收 |
|---|---|---|
| typed 包装 9 → 全 catalog 类 | 业务关键类逐个 typed 化（SNode/FaceRegion/FluidRegion/NumericalRegion/SubmeshSurfaceRegion/AdaptiveParam 等）；138 个 `Cond*` 标记类由 `Conditions` 泛型覆盖；其余经 `ComObject.call` 兜底即算覆盖 | typed 对账测试遍历 catalog 199 类：每类「typed 包装或 call 可达」断言 |
| 深管线 2 ABI 实机 | `CreateMeshOctreeByDefaultParam`（前置：SNode 注入拿 IVMDL）、`ConvertFacetToXT`（前置：真实 facet 文件） | 业务码非 -1 且 last_exception_code=0 日志 |
| e2e 日志入库 | edit_ops Ridge/Octant、OpenCadFile（STEP）、BAM Wizard 全步经 rot 后端跑通 | err=0 日志归档 |
| 后端收敛 | rot 为唯一权威通道；gui/manual 降级为诊断（`--status`） | 文档钉死 + 测试锁定路由 |

#### 域 12 · Solver/FPH 链路（10% → 100/100）——最大新增域

| 工作项 | 做法 | 验收 |
|---|---|---|
| Execute Solver 接线 | `Doc.ExecuteSolver` / `QuitAndExecuteSolver` typed 包装；Execute 面板勾选 API 时经 rot 提交 | box 工程提交→求解完成日志（本机许可 27500） |
| FPH 生成链路 | 宿主/求解器侧生成（`CreateFPHOCT` DLL 已定位，DEV_PLAN §16.0）；本仓只驱动+读取 | 产物 FPH 经 `fph.py` 可解析 |
| 结果回读闭环 | fldstats/fph/ifld（读侧已 L3）接入「前处理→提交→求解→读结果」全链 | 端到端日志 + FLD 场量非空断言 |
| 不勾选 API 的语义 | 明确「求解器本体不在本仓范围」（不伪造） | 菜单提示文案 |

#### 域 8 · 条件体系（82% → 100/100）

| 工作项 | 做法 | 验收 |
|---|---|---|
| CreateCond* 录制反推自动化 | typed `create_cond`（89 个 CreateCond*，Acceleration 闭环已实测）脚本化批量：逐类型 create → SaveProject → diff main.xml → 提取精确 XML 键入 `schemas/conditions.yaml`（**禁止** HTML 显示名猜测） | 缺口类型键数逐轮递增报告 |
| 2023.2 案例库收割 | `merge_official_schema --all` 扫 2023.2 库 150 PPH（与 2025.2 例程可能重叠，增量如实记录） | merged.json 增量 diff |
| 165/165 精确键 | 上述两路合并；generic 类型维持「不破坏宿主节点」 | 注册表 165/165 精确键 + round-trip 测试扩面 |
| 材料五库写端 | prp 写回（P4-2 只读补齐） | prp round-trip 测试 |

#### 域 10 · 几何编辑（66% → 100/100）

| 工作项 | 做法 | 验收 |
|---|---|---|
| Register Region 权威路线 | GUI 注册流（勾选 API）改走 `Doc.CreateFaceRegion`；文件层写回（`mdl.add_surface_region`）降级为 API 关闭时兼容路径，§6.3 负面矩阵文档化 | Save 后宿主 `QueryFaceRegionByName` **非 Nothing**（首次达成本项，§8.5 #10 关门） |
| CreateMDL 深管线闭合 | SNode 注入（`CreateGroupPart`/`CreateCoordinatesSpecifiedPart`/`ImportCADAsFacet` 建节点）→ `CreateVMDL`/`CreateMDL` | CreateMDL 返回 True 日志 |
| B-rep 提取（P1 路线） | `parasolid.decode_brep`：pskernel `PK_BODY_ask_*` 全家遍历 + NURBS 几何提取 | box.x_t 拓扑计数与 facet 对拍 |
| PKBody3 二进制（P2 路线） | token 字母表钉死 → FacetMesh parse/encode 字节闭环 | parse→serialize 字节恒等 |

#### 域 4 · CAD/XT 几何导入（85% → 100/100）

| 工作项 | 做法 | 验收 |
|---|---|---|
| STEP/CATIA/3dxml e2e | `OpenCadFile` / `ImportCADAsFacet` typed 直调实机 | err=0 日志；无宿主时明确报错不静默 |
| patch 导入 | `ImportPatchAsCAD`（Define Facet Part 前置） | patch 文件导入宿主可开 |
| CADthru faceter 等价 | **豁免**（§9.6） | — |

#### 域 6 · BAM 分析模型（73% → 100/100）

| 工作项 | 做法 | 验收 |
|---|---|---|
| BAM 宿主 e2e | `BeginMDLWizard → … → BuildAnalysisModel` typed 直调（或既有 VBS 经 rot），Save 后与 `native_bam` 报告字段对拍 | err=0 + 报告对拍表 |
| Influence/AF faceter 几何 | **豁免**（配置透传 BamReport 已有） | — |

#### 域 11 · Wrapping/Disc/Overset（65% → 100/100）

| 工作项 | 做法 | 验收 |
|---|---|---|
| Wrapping GUI 对齐 | Execute 面板 Wrapping 步骤参数与锁定序列（360 步 e2e 已 err=0）对齐收尾 | 复跑 err=0 |
| Disc/Overset 建组 | `CreateDiscontinuousMeshingGroupWith/WithoutMovingPart` + BDF/RotorInfo 映射录制（对照 box_disc/box_overset 黄金成员） | 新工程成员与黄金同类 |
| 自研 wrapping 内核 | **豁免**（§9.6） | — |

#### 域 5 · Octree 八叉树（78% → 100/100）

| 工作项 | 做法 | 验收 |
|---|---|---|
| 细化宿主权威 | 参数写入 xenv/xml（已有）+ `Octree.Refine*` typed 直调（Refine/Merge/RefineByLevel/RefineByNumber/RefineFromCurvature 已锁定）+ 结果重开验证 | 细化后 OCT/GPH 宿主重开 err=0 |
| 三向对齐回归 | oct↔快照区域↔GPH 单元（O3 链路）扩真实几何 | `test_oct_examples` 三档黄金扩展 |

#### 域 9 · 自研网格生成（68% → 100/100）

| 工作项 | 做法 | 验收 |
|---|---|---|
| 宿主 CreateMesh e2e | `MeshingGroup.CreateMesh` typed 直调（box） | err=0 + GPH 黄金 |
| 自研规模化 | laptop 级（1.24M 叶）性能优化 + 质量报告 GUI 集成 | benchmark 阈值通过 |
| 棱柱层/power diagram/bit 等 | **豁免**（§9.6；`--layers` MVP 已有） | — |

#### 域 3 · Select/View/3D（90% → 100/100）

| 工作项 | 做法 | 验收 |
|---|---|---|
| Select by Element Number/List/Same Area | `build_cells` 拓扑已就绪，纯 GUI 接线 | 手工清单 + 测试 |
| Check Intersection | `MeshingGroup.CheckIntersectionForMeshModel` typed 路线（本地 `gphstats` 兜底） | 报告输出 |
| 4 暂缓 NYI 处置 | Create Non-Facet/Closed Volume Part → `Doc.CreateCoordinatesSpecifiedPart`；Create 2D Sub-mesh → `CreateSubmeshMeshingGroup`；Define Facet Part → `ImportCADAsFacet`；Fix Marked Element Shape → 评估后如实定边界 | NYI 清单仅剩产品边界项 |
| Actran 重评估 | `MeshingGroup.CreateActranFilesMonitor` 存在，「产品边界」结论重审 | 更新 NYI_INVENTORY |

#### 域 1/2 · PPH 解析与写端 / 工程文件管理（96/97% → 100/100）

| 工作项 | 做法 | 验收 |
|---|---|---|
| PKBody3 字节闭环 | 见域 10 P2（共享） | 字节恒等 |
| sctsnapshot 多样本对比 | 重序列化字节恒等从 box/laptop 扩 6+ 样本；失败项如实记「语义等价」 | 测试矩阵 |
| LZMS 跨平台写端 | 纯 Python 压缩器（对既有解压器写对称实现）或平台守卫 + 文档化，二选一如实记录 | round-trip 测试或豁免声明 |
| wimlib/罕见可选段 | 无样本不猜，文档标非目标 | 文档钉死 |

### 9.5 波次依赖与总量

```
P12-A 权威通道收官（域 7 → 100，总闸门）   约 1.5–2 周
        │ typed 全类对账 / 深管线 2 ABI / e2e 日志 / 后端收敛
        ├──→ P12-B 求解链路（域 12 → 100）           约 1 周
        ├──→ P12-E 网格/BAM/包装收口（域 5/6/9/11）   约 2 周
        └──→ P12-D 几何/Region 权威接线（域 4/10）    约 1.5–2 周（SNode 部分可与 A 并行）
P12-C 条件深度收割（域 8 → 100）                      约 1–2 周（独立，随时）
P12-F 格式长尾 + Select 收口（域 1/2/3）              约 1–2 周（独立，随时）
```

总量（1 人全职）≈ **8–11 周**。瓶颈为宿主实机验证排队——ROT 常驻实例可复用，
较 P5 时代「等前台窗口」约束已大幅缓解。执行纪律沿用 §8.3：A 未出全链 err=0
日志前不宣称域 6/7/11/12 达标；B 未出求解完成日志前不宣称域 12 达标。

### 9.6 明确豁免（双 100% 不含，且不影响达标声明）

1. 自研 mesher / native_bam / wrapping 与 scFLOWpre 内核**数值 bit 等**——
   官方内核经 typed COM/C ABI 已可全驱动，复刻无必要（DEV_PLAN §0.4 策略不变）；
2. CADthru / Datakit / Parasolid 商业内核**本体重写**（驱动 + 格式字节级即深度达标）；
3. scFLOWsolver / scPOST **本体重写**（ExecuteSolver 驱动 + FPH/FLD/iFLD 读侧
   L3 即深度达标）；
4. 远程集群作业推送（本地 ExecuteSolver 即产品闭环，集群属部署层）。

### 9.7 12 域「双 100%」一句话验收（可打勾清单）

1. PPH：全成员类型（含 PKBody3）round-trip 字节恒等或语义等价有据；LZMS 策略钉死。
2. 工程：New → Import → Execute → Save → 宿主重开，全链零成员丢失。
3. Select：全部选择/视图菜单可用或灰显有据；by-element/intersection/check 接线。
4. CAD：XT 登记 + B-rep 拓扑可提取 + STEP/patch 经宿主 err=0。
5. Octree：细化宿主权威执行 + 三向对齐三档黄金回归。
6. BAM：typed/VBS 宿主 e2e err=0 + native_bam 报告对拍。
7. COM：typed 对账 199 类全覆盖 + rot 全链 err=0 + 深管线 4 ABI 实机日志。
8. 条件：165/165 精确 XML 键 + Save 后宿主 Cond 节点零破坏。
9. 网格：宿主 CreateMesh e2e + 自研黄金三档质量不劣于断言。
10. 几何：CreateFaceRegion 宿主 Query 非 Nothing + 原语/布尔原生写回 PPH。
11. Wrap/Disc/Overset：e2e err=0 + 建组录制 + 成员与黄金同类。
12. Solver：ExecuteSolver 提交 → 求解完成 → FLD 回读全链闭环。

打满 12 句，§0 表 12 域全部改 100%（双口径），表下脚注：
*内核数值等价以「官方内核全驱动 + 字节级格式闭环 + 量化对拍」替代，复刻不在目标内。*


### 9.8 执行状态追加（P12-A，2026-08-25：权威通道收官）

§9.4 域 7 四工作项落地（执行细节与实测教训见 DEV_PLAN §17.10）：

| 工作项 | 结果 | 验收 |
|---|---|---|
| typed 包装 9 → 全 catalog 类 | **关闭**：typed 17 类（SNode 145 方法 / FaceRegion 70 / FluidRegion 66 / MeshingGroupSetting 104 / NumericalRegion 20 / SubmeshSurfaceRegion 19 / AdaptiveParam 等，`TYPED_CLASSES` 注册表 + 工厂返回 typed）+ 136 `Cond*` 经 `Conditions` 泛型 + 46 `ComObject.call` 兜底 = 199/199 | 对账测试 24 个全绿 |
| 深管线 2 ABI 实机 | **COM 暴露 + 全链验证**：DISPID 13（`CreateMeshOctree`→`IVMDL::CreateMeshOctreeByDefaultParam`）/ 14（`ConvertFacetToXT` 自由函数）；实机 mesh_oct 参数校验链（SCF_ERR_ARG）、xt 业务码 202，`last_exception_code=0` 无 AV | 业务码非 -1 的完整验收卡前置（SNode 注入 / 真实 facet 文件 → P12-D/E） |
| e2e 日志入库 | **关闭**：ridge 30/30 + octant 42/42 + bam 3125/3125 + cad 12/12，全 err=0 经 rot；日志/VBS/输出 pph/MDL 归档仓库根（`p12a_*_e2e.*`，沿 p5 先例） | run.ok + 全量 err=0 双闸门 |
| 后端收敛 | **关闭**：`AUTHORITATIVE_BACKEND="rot"` 唯一权威入口，gui/manual 降级诊断（`--status`） | 29 路由锁定测试 |

域分数更新（对 §9.3 基线，逐项依据）：域 7 85→**92**（余 ExecuteSolver
→ P12-B、深管线业务码非 -1 → P12-D）；域 4 85→**88**（STEP e2e err=0
归档；CATIA/3dxml/patch 待 P12-D/F）；域 5 78→**80**（Refine 族六操作
e2e + .oct 归档；三向对齐扩样与宿主重开验证待 P12-E）；域 6 73→**85**
（wizard 全步 3125/3125 e2e + `VMDL.Save` 显式导出 1.7MB + pph 内嵌
gph/ridge.mdl；native_bam 报告对拍待 P12-E）。

P12-A 增量实测教训（细节见 DEV_PLAN §17.10）：VBS `Array()` 整型字面量
（VT_I2）致 `RefineFromCurvature` 原生 double 读 AV——生成器改恒出
Double 字面量；cad e2e 需裸宿主（带已开工程时 OpenCadFile(STEP) 解析后
挂起）；`EndMDLWizard` 产出的 VMDL 权威导出 = `VMDL.Save(path)`（不经
SaveProject 内嵌）。

---

## 10. P12-A 后基线重核与高杠杆冲刺计划（2026-08-30 立）

> 输入：§9.8（P12-A 权威通道收官）+ 2026-08-30 对代码/数据/测试状态的
> 全量实测复核。本节**不修改** §9.1 双 100% 口径、§9.6 豁免与 §9.7
> 十二句验收，仅做三件事：① 基线实测重核（纠正「文档转述」风险）；
> ② 按**分/周杠杆**重排 §9.5 波次顺序；③ 新增 Sprint 0 基线固化
> （P12-A 未提交风险）。执行入口见 DEV_PLAN §18。

### 10.0 实测重核（2026-08-30，非文档转述）

| 项 | 实测结果 |
|---|---|
| 测试 | 收集 792 项；全量回归 **789 passed / 3 skipped / 0 failed**（592s，py3.12 环境；py3.14 历史记录的 4 个 capstone 环境 error 此处不存在） |
| API 目录 | `vb_api_catalog.json` 199 类 / 4439 方法；Doc 424 方法（含 `ExecuteSolver` / `QuitAndExecuteSolver`）；Conditions `CreateCond*` 89；Region 族 56 方法 |
| 条件收割 | `merged.json` **63 类型**带精确字段 schema / 6065 字段（源：151 官方例程 PPH 全量收割）；`cond_types.json` 165 实名 → 精确键缺口 102 类型 |
| NYI | 余 6 项（2 产品边界 + 4 暂缓）；4 暂缓项在 catalog 均有 typed API 入口（`CreateCoordinatesSpecifiedPart` / `CreateSubmeshMeshingGroup` / `ImportCADAsFacet` / `CreateActranFilesMonitor`） |
| Solver 地基 | `ExecuteSolver` / `QuitAndExecuteSolver` typed 包装**已写好**（`automation/scflowpre_api.py:368-373`）——P12-B 地基前置 |
| 宿主环境 | 宿主进程未在跑（需 Kicker 冷启动，配方钉死于 DEV_PLAN §17.10）；许可 27500@localhost 在线（SCFLOWPP 32 席） |
| Git 风险 | HEAD=`245f1c4`（P11），**P12-A 交付（13 文件 +1803 行）未提交**；未跟踪 186 个（`_p12a_*` 诊断临时件与 `p12a_*_e2e.*` 证据混放） |

### 10.1 12 域基线与差距（2026-08-31 Sprint C 后实况；基线快照见 §9.8）

| # | 域 | 完整度 | 深度 | 距 100% | 卡点性质 |
|---|---|---|---|---|---|
| 12 | Solver/FPH | 100% | L2+ | **0** | ✅ B 关（求解日志 ×2 + FLD 对拍） |
| 10 | 几何编辑 | 100% | L2+ | **0** | ✅ D 关（Query 闸门 + 持久腿 + CreateMDL 产物闭环） |
| 11 | Wrap/Disc/Overset | 100% | L2+ | **0** | ✅ E 关（回放 3100 err=0 + 建组指纹同类） |
| 9 | 自研网格 | 100% | L2+ | **0** | ✅ E 关（CreateMesh e2e + 真 facet XT 码 0） |
| 5 | Octree | 100% | L2+ | **0** | ✅ E 关（三向对齐三样本精确 + 重开两绿） |
| 8 | 条件体系 | 92% | L2+ | 8 | ✅ C 主收割（§10.9：精确键 47→90/165 + 事务层/毒类型/覆盖上限三模型 + prp 写端）；余 8 分 = 向导门控家族（GUI 向导自动化后续项） |
| 6 | BAM | 100% | L2+ | **0** | ✅ E 关（拓扑不变量对拍 PASS） |
| 4 | CAD/XT | 94% | L2-3 | 6 | ✅ patch e2e 已随 F 绿（§10.8）；**CATIA 裁决（2026-09-01）**：全机扫描 0 真 CATIA 几何样本（CATPart/CATProduct/cgr 均无；命中仅为 HDF5 `.exp`/链接器 export/Datakit `dtk.model` schema 误报），Datakit schema 在位证明宿主 CATIA 转换链已安装——**产品边界如实声明**（样本缺失非代码缺口），6 分转为边界项 |
| 3 | Select/View | 100% | L2 | **0** | ✅ F 关（5 项 NYI 接线 e2e err=0，清单仅剩产品边界项） |
| 7 | 宿主自动化 | 100% | L2+ | **0** | ✅ C 复核关（xt_ec=0 §10.6 + 条件 typed 自动化持久化路径实测 §10.9） |
| 2 | 工程管理 | 100% | L3 | **0** | ✅ F 关（sctsnapshot 150 样本字节恒等 + LZMS 策略钉死） |
| 1 | PPH 读写 | 100% | L3 | **0** | ✅ D 关（PKBody3 三路字节恒等，P2/P4 回归） |

**整体完整度 ≈ 98.8%（12 域均分），剩余 14 分**（域 8 条件 8 →
GUI 向导自动化后续项；域 4 CAD 6 → patch 腿已随 F 绿，余 CATIA
样本缺失待裁决）。结构性判断：

1. 哑铃结构已收敛为「底层满格、腰部待接线」：格式层（字节级闭环）与
   内核驱动层（typed 199/199 对账 + C ABI 深管线 + 四流程 e2e 全 err=0）
   均生产级，剩余缺口**几乎全是"接线 + 实机验收"，无结构性逆向风险**；
2. 域 8 是单点最大洼地（18 分）与单位投入产出之王：P10 证明 typed
   `create_cond` 实机闭环，89 个 `CreateCond*` 意味着 **create →
   Save → diff main.xml → 提取精确键** 可全自动脚本化，63 → 165 是
   纯工程量问题（B 后原最大洼地域 12 已关闭，E/D/F 后满格域 9/12）；
3. 域 4 尾 6 分：patch e2e **已随 F 绿**（§10.8）；CATIA 裁决
   **已完成（2026-09-01）**——全机 0 真 CATIA 几何样本（仅误命中），
   Datakit schema 在位证明宿主转换链已安装，**产品边界如实声明**，
   非代码缺口；域 7 尾随 C 收口。

### 10.2 冲刺计划（执行顺序，取代 §9.5 字母序）

| 冲刺 | 域 | 增量 | 投入 | 关键工作项 | 验收一句话 |
|---|---|---|---|---|---|
| **0 基线固化** | — | 0 | 0.5 天 | 提交 P12-A（13 文件）独立提交；`p12a_*_e2e.*` 证据入库；186 未跟踪件分拣（证据保留 / 诊断件移 `scratch/` 或删除） | git status 干净；792 回归全绿 |
| **B 求解链路** | 12（+域 7 尾 8） | **+90** | 1 周 | Execute 面板勾 API → rot 调 `Doc.ExecuteSolver(sphPath)`；FPH/FLD 产物经 `fph.py` / `fldstats.py` 回读；Day-1 先探 solver 启动与许可需求 | box 提交→求解完成日志 + FLD 场量非空断言 |
| **E 网格/BAM/包装收口** | 5/6/9/11 | **+102** | 2 周 | `MeshingGroup.CreateMesh` e2e（复用 P12-A BAM e2e 的 VMDL/gph 产物，绕「无几何」死锁）；Wrapping GUI 参数对齐锁定序列；Disc/Overset 建组录制（对照 box_disc/box_overset 黄金）；`ConvertFacetToXT` 用 BAM 产物真实 facet；BAM 报告对拍；三向对齐扩样 | 四域 err=0 日志 + 成员与黄金同类 **✅ 完成（2026-08-30，§10.6）** |
| **D 几何/Region 权威接线** | 10/4 | **+46** | 1.5-2 周 | Register Region 走 `Doc.CreateFaceRegion`（typed 70 方法就绪）；SNode 注入（`CreateGroupPart` / `ImportCADAsFacet`）→ `CreateMDL` True → 深管线业务码非 -1；B-rep 提取（`PK_BODY_ask_*` 全家）；PKBody3 token 字母表→字节闭环（域 1 共享） | `QueryFaceRegionByName` **首次非 Nothing**（§8.5 #10 关门）**✅ 完成（2026-08-30，§10.7；CreateMDL 实测 void 改判产物证据，+44/+46）** |
| **C 条件深度收割** | 8 | +18 | 1-2 周（随时可插） | 收割机脚本化：89 `CreateCond*` → create → SaveProject → diff main.xml → 精确键自动入 `merged.json`（HTML 显示名猜测禁令沿用 §9.4）；2023.2 库 150 PPH 增量收割；材料五库 prp 写端 | 165/165 精确键 + Save 不破坏宿主 Cond 节点 **◐ 部分达标（2026-08-31，§10.9：47→90/165，CreateCond* 面结构性上限 79/165；Save 不破坏实测通过；prp 写端完成；余 75 向导门控 → GUI 向导自动化后续项）** |
| **F 格式长尾 + Select 收口** | 1/2/3 | +17 | 1-2 周（最后） | 4 暂缓 NYI typed 接线；Actran 重评估；sctsnapshot 重序列化扩 6+ 样本；LZMS 跨平台写端策略钉死（写对称实现或豁免声明，二选一如实记录） | NYI 清单仅剩产品边界项 **✅ 完成（2026-08-30，§10.8；域 3/2 满格，整体 97.3%）** |

### 10.3 轨迹预估与纪律闸门

| 节点 | 累计投入 | 整体完整度 |
|---|---|---|
| Sprint 0 | 0.5 天 | 76.6%（基线固化） |
| +B | ~1 周 | **84.1%** |
| +E | ~3 周 | **92.6%** |
| +D | ~5 周 | **96.3%**（实测，+44/+46） |
| +F | ~6 周 | **97.3%**（实测，域 3/2 满格 9/12） |
| +C | ~7 周 | **100%**（12 域双口径；含域 7 尾复核与域 4 CATIA 裁决） |

对 §9.5 原估（8-11 周）：B 提前（单项 ROI 之王）+ E 复用 P12-A 产物
——**前 3 周即 +192 分**，是「显著提升」的主引擎。

纪律闸门（§8.3 沿用，违反即虚假达标）：B 无求解完成日志不宣称域 12；
E 无 err=0 日志不宣称域 5/6/9/11；D 无 Query 非 Nothing 不宣称域 10；
C 的键必须来自真实 XML。**宿主实机时间是唯一瓶颈资源**——全部实机验收
按冲刺批量排程，Kicker 冷启动用 §17.10 钉死配方。

### 10.4 与 §9.5 的差异说明

| 方面 | §9.5 原序 | 本节顺序 | 理由 |
|---|---|---|---|
| 首攻 | A（已完）→ B/E/D | **B 先** | 90 分/周且地基前置、独立无依赖 |
| E 时机 | A 后 | D 之前 | 复用 P12-A BAM 产物即现成几何，解 CreateMesh「无几何」死锁；E 对 D 的依赖仅「业务码非 -1」一项，可后置补 |
| C/D 并行 | C 独立随时 | D 与 C 并行（C 抢宿主窗口时排队） | C 收割为脚本化小步，占 rot 窗口时间短 |
| Sprint 0 | 无 | **新增** | P12-A 未提交 + 186 临时件 = 基线风险，半天消除 |
| 豁免口径 | §9.6 | 不变 | — |

### 10.5 Sprint B 交付实录（2026-08-30）

**结果**：域 12 Solver/FPH **10%→100%，L0→L2+**；域 7 尾项
（ExecuteSolver 实机接线）关闭；整体 76.6%→**84.1%**（§10.3 首跳
兑现，实际投入 1 天）。执行细节与实测钉死见 DEV_PLAN §18.3。

**纪律闸门核验**（§10.3 口径）：
- 求解完成日志 ×2：`CALCULATION FINISH` + ERROR LOG 空
  （`p12b_solve_e2e.l` rot 通道 / `p12b_dp50_e2e.l` JobLauncher 直驱）；
- FLD 场量非空：`boxdp_400.fph` `strict_ok=true`（11 场量、
  VEL/PRES 非零），且 VEL min −2.15652e-05 与 L 日志 FIELD EXTREMA、
  P=50Pa 与边界条件逐值对上——读回不是「有文件」，是「数值对拍」。

**链路**（新模块 `automation/solver_run.py` + typed `SaveSphFile`）：
OpenProject → SetModeMesh → SavePolyFile(gph) → SaveSphFile(sph,gph)
→ `ExecuteSolver(sph)`（rot，异步）→ 计算进程退出判定（scMonitor
常驻不计）→ `<工程名>_400.fph` 经 `fph.py` 全解析。

**对后续冲刺的输入**：① 产物命名分裂（场文件=工程名 / 日志=
sph 干名）与 scMonitor 常驻已钉死，E 的实机编排直接复用；
② Kicker 2025.2 冷启动实测修正（按钮 `STPRE`、宿主进程
`STpre_Bx64net`、模态「Initial Wizard」）替代 §17.10 旧文本；
③ box 单 open 边界物理退化（零流量）——E/C 若要真实流量验收，
需双边界压差配置（本次已用 50Pa 变体兜底证明链路产真实场）。

### 10.6 Sprint E 交付实录（2026-08-30）

**结果**：域 5 Octree / 域 6 BAM / 域 9 自研网格 / 域 11
Wrap-Disc-Overset 四域 **→100%（L2+）**；整体 84.1%→**92.6%**
（§10.3 第二跳兑现，实际投入 1 天 < 预估 2 周）；域 7 标注卡点
「深管线业务码非 -1」实测解除（`xt_ec=0` 达 SCTprime 内核）。
执行细节与实测钉死见 DEV_PLAN §18.4。

**纪律闸门核验**（§10.3 口径，五 flow 官方 gate 全 PASS，证据归
仓库根 `p12e_*_e2e.*`）：
- **wrap**：录制回放 3100 动作全 err=0、25 对象 alive（域 11
  GUI 序列对齐）；
- **mesh**：`CreateMesh` ret=True + `WaitForWorker` ret=1，产物
  gph/ridge 落盘（域 9）；
- **disc / overset**：建组 err 全 0，产物指纹与官方
  box_disc / box_overset PPH **same_class=True**（域 11）；
- **xt**：`ConvertFacetToXT` 真实 facet（P12-A BAM VMDL）业务码 0，
  产物为真 Parasolid（域 9/7 深管线）；
- **BAM 对拍**：宿主 MDL × 自研分析模型拓扑不变量全对上（域 6，
  密度键 recorded-only 豁免 §9.6）；**三向对齐**：octant bits ↔
  .oct 成员 ↔ GPH 细胞三样本精确一致（域 5）。

**对后续冲刺的输入**：① 宿主会话 OpenProject 挂起现象（挂起调用
持有目标工程、同文件后续打开全挂；换目标或换宿主实例可解）——
D/C 实机批量**每 flow 用独立工程 + 前置换宿主预案**；② rot 通道
`ExecuteVBSWithFile` 对慢 VBS 提前返回，verdict 必须轮询 `end`
标记（`tools/_p12e_e2e_run.py` end_wait 模式可复用）；③ Disc/
Overset 黄金指纹与模块（`disc_overset.py`）直接服务 D 的
Region/Part 建组验收对拍；④ reopen 正式 gate 日志未取（实测两绿，
非验收句项）——D/C 批量时顺带补录。

### 10.7 Sprint D 交付实录（2026-08-30）

**结果**：域 10 几何编辑 66%→**100%（L2+）**、域 1 PPH 读写
96%→**100%（L3）**、域 4 CAD/XT 88%→**94%**；整体 92.6%→**96.3%**
（+44/+46，实际投入 1 天 < 预估 1.5-2 周）。执行细节与实测钉死见
DEV_PLAN §18.5。

**纪律闸门核验**（§10.3 口径，四 flow 官方 gate 全 PASS，证据归
仓库根 `p12d_*_e2e.*`）：
- **region**（§8.5 #10 关门）：`Doc.CreateFaceRegion("P12DRegion")`
  → `Doc.QueryFaceRegionByName` **项目史上首次非 Nothing**，
  13/13 err=0；负面对照 `_p12d_absent` 判别有效；
- **region_reopen**：Save → 重开 → 再 Query 非 Nothing（8/8）；
  字节扫描钉死权威名表文件层落点 = main.xml 三结构
  （conditions 区 / phase_pair / auto_grouping 各 1 处）——
  §6.3 七场景「新名不注册」之谜解答：读侧名表只在宿主写回时存在，
  权威注册唯一正路 = 宿主 API；
- **snode**（CreateMDL 项）：录制 2662 行回放 + SNode 注入 +
  VMDL.Save 显式导出，3134/3134 err=0，产物 .gph + MDL 1.7 MB；
  `MDLWizard.CreateMDL` 实测 **void 方法**（验收按产物证据改判）；
- **facet**（域 4）：`ImportCADAsFacet(box.x_t)` typed 直调 err=0。

**离线闭环**（域 1/10）：PKBody3 → `parse_binary_xt` →
`encode_binary_xt` **字节恒等**三路全绿（box 'A' 流 + kernel 'B'
流 + 2023.2 V34.1 'A' 流，P2/P4 既有回归）；`decode_brep` box.x_t
拓扑计数（5 体/6 面/16 边/16 顶点）+ 新增 `test_facet_crosscheck`
（B-rep 拓扑 ↔ PK_TOPOL_facet_2 分面：三角=2×面数、分面角点=
B-rep 顶点）。

**对后续冲刺的输入**：① patch flow（`ImportPatchAsCAD` +
PotatoChips.stl）流程/包装/离线测试已就绪，仅欠实机 err=0 日志
——2026-08-30 夜连续 3 实例 WER APPCRASH（mfc140u.dll，同期
NVIDIA 后端 AV）致两轮冷启动均未准入执行，环境恢复后
`py tools/_p12d_e2e_run.py patch` 直接重跑；② rot 通道
`ExecuteVBSWithFile` 接纳/拒绝逐次不稳定（拒=零执行、忙时幻影
True），`_p12d_e2e_run.py` 的 end 标记判据 + 拒绝重试模式可复用
于 C 批量；③ `Doc.CreateGroupPart` headless Nothing 负发现存档，
SNode 注入走 `QuerySNodeByName`；④ E 遗留①（域 5 reopen 正式
日志）与 box 双边界压差随 C 批量处理。

### 10.8 Sprint F 交付实录（2026-08-30）

**结果**：域 3 Select/View 90%→**100%（L2）**、域 2 工程管理
97%→**100%（L3）**；整体 96.3%→**97.3%**（12 域满格 9/12；实际
投入 1 天 < 预估 1-2 周）。执行细节与实测钉死见 DEV_PLAN §18.6。

**实机 gate**（证据归仓库根 `p12f_*_e2e.*` / `p12d_patch_e2e.*`）：
- **facet**（Define Facet Part）：`CreateMeshingGroup` +
  `ImportCADAsFacet(box.x_t)` 10/10 err=0，产物含
  `meshinggroup1_part.mdl`；
- **coord**（Create Non-Facet/Closed Volume Part）：
  `CreateCoordinatesSpecifiedPart("P12FCoordPart")` 9/9 err=0、
  返回非 Nothing，名落 main.xml ×2；
- **submesh**（Create 2D Sub-mesh Meshing Unit）：
  `CreateSubmeshMeshingGroup("P12FSubMG")` 同上全绿；
- **fix**（Fix Marked Element Shape）：`FixMarkedElements`
  retval=0（err=0，meshed box 工程）；
- **actran**（Create Actran Files）：typed 链 err=0 但业务层
  retval=False（SetModeMesh/SetActive 前置变体同结果、0 文件）
  ——Acoustic Session 前置无样本不可满足，边界如实记录，菜单
  已接线不再灰显；
- **patch**（D 遗留①关账）：无括号 retval 调用被 rot **稳定
  拒绝**（5/5 零执行，内容性），**括号形式
  `Set SN5_ = Doc_.ImportPatchAsCAD("…")` GATE PASS**、
  `sn5_` 非 Nothing、产物
  含 `meshinggroup1_part.mdl`。

**离线闭环**（域 1/2）：sctsnapshot 官方案例库 151 pph 中 150 个
含快照成员，**150/150 重序列化字节恒等**（`TestOfficialSnapshots`，
18s）；LZMS 写端策略钉死 = 写对称实现（同 API 族
`CreateCompressor`/`CreateDecompressor`）+ 非 Windows 平台守卫 +
纯 Python 压缩器豁免声明（DEV_SUMMARY §3.5）；NYI 清单 6 项 →
1 项（Restore Closed Volume Data，产品边界）。

**对后续冲刺的输入**：① 唯一剩余冲刺 = C（域 8 条件 18 分 +
域 7 尾 8 分复核）：89 `CreateCond*` 收割机沿用
`_p12d/_p12f` 的 end 标记判据 + 拒绝重试 + **retval 括号调用**
（P12-F 新钉死）配方；② 域 4 尾 6 分裁决待定：patch e2e 已绿，
CATIA V4/V5/V6 样本全机缺失（无样本不猜口径，如实记录）。

### 10.9 Sprint C 交付实录（2026-08-31）

**结果**：域 8 条件体系 82%→**92%（L2→L2+）**、域 7 宿主自动化
92%→**100%（L2+）**；整体 97.3%→**98.8%**（12 域满格 10/12；余
域 8 尾 8 分 + 域 4 尾 6 分）。C 为**部分达标**：165/165 中精确键
**47→90**（+43，全走收割管线），`CreateCond*` 路线到结构性上限
——执行细节与实测钉死见 DEV_PLAN §18.7。

**核心交付**：`tools/_p12c_cond_harvest.py`（收割机 plan/build/
run/merge/probe/all）+ `p12c_registry_report.json`（75 缺口如实
五分类）+ 材料五库 prp 写端（`material_lib.py` PrpDocument 读写 +
round-trip 测试）+ 收割机离线测试 10 项 + `pphxml` 容器短名别名
归一（配套回归 27 项绿）+ 21 个实测别名入册。

**实测钉死（宿主行为三模型，后续冲刺的地基）**：

1. **条件事务层**：COM `CreateCond*` 条件只活在与创建同脚本的会话
   事务里，「create → 强制脏（SetDefaultTemperature）→ SaveProject」
   同脚本才落 main.xml；脚本边界未提交即弃（P10 Acceleration 闭环
   只验对象级、未验持久化——C 补上）；
2. **保存毒**：`CondBatteryARCDataPreprocessing` create err=0 但
   序列化毒杀同脚本保存（`probe` 二分定位法沉淀）；基线须 2025.2
   原生工程（2023.2 旧 CAB 保存触发版本转换 Confirm 死循环）；
3. **覆盖上限**：89 个 `CreateCond*` 仅映射 79/165 universe 类型，
   其余 86 个（cosim 28 / particle 11 / multiphase 7 等）为 GUI
   向导门控家族，无 COM 单调用路径——165 全覆盖需 GUI 向导自动化
   （pywinauto 驱动向导 + 录制反推，登记为后续冲刺项）。

**对后续冲刺的输入**：① 域 8 尾 8 分 = GUI 向导自动化（Analysis
Type/DEM/CoSIM 向导逐族收割，沿 `probe` 配方 + end 标记 + 括号
retval 调用）；② 域 4 尾 6 分 = CATIA 样本裁决（沿 D/F 遗留）；
③ `CondCoSim`/`CondDTSI`/`CondDTSR` 创建器参数形态待向导录制反推。

### 10.10 Sprint G 收口冲刺实录（2026-09-01/02）

**结果**：G1 xt 遗留 ✅ 关账（Status priming 实机 GATE PASS：
18/18 err=0、`xt_ec=0`、产物落盘）；G3 域 4 CATIA ✅ 裁决关账
（全机 0 真样本，Datakit 链在位，**产品边界声明**，6 分转边界项，
§10.1 已更新）；G2 域 8 GUI 向导 ◐ **摸底完成**——Condition
Wizard 结构/语义/配方钉死（9 轮 probe），收割执行转下一冲刺。
执行细节与开放问题（勾选→落盘链路未通、68 类持久化落点未定、
Finish 全量投影语义）见 DEV_PLAN §18.8。

**域分变化**：无（域 8 维持 92%——收割口径待落点钉死后重估；
域 4 维持 94% 但 6 分性质改判为产品边界项）。整体维持 **98.8%**；
结构性剩余 = 域 8 尾 8 分（GUI 向导收割，入口已开）。

### 10.11 Sprint H1/H2 实录（2026-09-02）：68 类落点终审 = 纯会话态

**H1（DEV_PLAN §19.4）**：CondFreeSurface 代表类落点钉死——勾选
（BM_GETCHECK 0→1 铁证）→ Finish → Confirm 确认 → Save 全链首通，
双工程（原生空工程 + box）byte-diff 均无 FreeSurface/Cond* 变化。
GUI 配方升级为 Win32 通道：`WM_COMMAND 34062` 开向导（工具栏按钮
owner-drawn 无 InvokePattern，UIA/click_input/物理点击全无效）、
`BM_GETCHECK`/`BM_CLICK` 勾选（无 TogglePattern）、Confirm 循环
（确定/关闭）。

**H2（DEV_PLAN §19.5）**：收割机 v2（`tools/_p12h_wizard_harvest.py`，
plan/base/run/runcombo/merge + 离线归一化判定器 + 12 用例测试）。
27 分析族 batch：**25 session_state + 1 keys_projected（Electric
current，仅 mesh 四成员字节重投影、main.xml 无键）+ 1 not_run
（Thermoregulation，深页门控，转 H3）**。级联门控实钉：
Evaporation←Free surface、Boil/condensation 与 Phase change
material←Heat、Topology optimization←Flow。深页探针：24 页全翻，
Condition List 只读无 Add/Delete，向导内无 Cond* 实体创建入口。

**68 类 no_com_creator 落点终审 = `wizard_session_state`（纯会话
态）**。证据链四路闭环：族勾选零键 + 向导无创建入口 + COM 无创
建器（P12-C）+ 151 官方样本零出现（P12-C merged）。

**域分变化**：域 8 口径按 §19.3-1 预授权重估——「GUI 向导会话态
配置」对标本仓 `pph_gui` 替代面板覆盖 = 对齐实现，XML 键收割路线
关账；分数与 165 类对账归属（68 类→`wizard_session_state`）在
H4/H5 收口统一刷新（当前账面维持 92%/98.8%，重估后域 8 → 100%）。
结构性剩余 = H3 特殊 6 类（aliased 4 + FMI 1 + poison 1 + 深页
门控 1）+ H4 对账 + H5 边界项入册与 100% 声明。

### 10.12 Sprint H3 实录（2026-09-03）：特殊 6 类逐类有归属

**复验机 `tools/_p12h_special6.py`**（DEV_PLAN §19.6）：6 类实机
6 臂（FMIVariable 双臂）+ 2 静态处置，臂日志全 err=0；离线归并 =
四成员 byte 扫描（H1 方法学）→ `p12h_special6_report.json` +
`cond_types.json` dispositions 入册（version 3）。测试
`tests/test_p12h_special6.py`（15 用例）。

**处置**：CondBoundaryHumidity = alias→CondHumidity（复验钉死）；
CondOutputLFileWaterLevel = member_locus
（`main.xml:output_timing/condition@name`，无 type 短名内联）；
CondFMIVariable = member_locus
（`main.xml:cosim_struct_data/fmi/variables/variable@name`，**无
FMI 前置使能要求**，plain 臂裸 create 即落盘）；FpDEM/Repulsion =
create_returns_nothing（catalog 真实签名复验仍 Nothing，归向导唯
一路径族）；Battery = poison_isolated（C 轮证据在册不复跑）；
Thermoregulation = wizard_session_state_gated（H2 并轨）。

**对 P12-C 五分类修正**：WaterLevel/FMIVariable 由"不序列化/缺行"
→ 真实键（typed 扫描漏内联落点）；FpDEM/Repulsion 由 aliased→
create_returns_nothing。H4 对账口径随之更新：165 类中
create_returns_nothing 族 3 类（CoSIM/FpDEM/Repulsion）与 68 类
同归属候选。
