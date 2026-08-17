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

综合 API 通路、原生实现深度与实机验证状态的估算（%）：

| 功能域 | 完整度 | 分层 |
|---|---|---|
| PPH 解析与写端 | 95% | 强项层 |
| 工程文件管理 | 95% | 强项层 |
| Select/View/3D | 88% | 强项层 |
| CAD/XT 几何导入 | 80% | 强项层 |
| Octree 八叉树 | 75% | 中间层 |
| BAM 分析模型 | 73% | 中间层 |
| 宿主自动化 COM/VBS | 72% | 中间层 |
| 条件体系（~180 Cond*） | **65%** | 中间层 |
| 自研网格生成 | 63% | 中间层 |
| 几何编辑 Create/Modify | 62% | 中间层 |
| Wrapping/Disc/Overset | 58% | 中间层 |
| Solver/FPH 链路 | 10% | 差距层（合理延后） |

```
功能域                    0        25        50        75      100
────────────────────────────────────────────────────────────────────

【强项层 · 生产级】
PPH 解析与写端          ██████████████████████████████████████░░  95%
工程文件管理            ██████████████████████████████████████░░  95%
Select/View/3D         ███████████████████████████████░░░░░  88%
CAD/XT 几何导入         ████████████████████████████████████░░░░░░░░  80%

【中间层 · 可用但有条件】
Octree 八叉树           ███████████████████████████████░░░░░░░░░░░  75%
BAM 分析模型            ██████████████████████████████████░░░░░░░░░  73%
宿主自动化 COM/VBS      ██████████████████████████████████░░░░░░░░░  72%
条件体系(~180 Cond*)   █████████████████████████░░░░░░░░░░░░░░░░░  65%
自研网格生成            █████████████████████████░░░░░░░░░░░░░░░░░  63%
几何编辑 Create/Modify  ██████████████████████████░░░░░░░░░░░░░░░░  62%
Wrapping/Disc/Overset  ███████████████████████░░░░░░░░░░░░░░░░░░░░  58%

···························· 以下为主要差距区 ···························

Solver/FPH 链路         ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  10%  ◀ 合理延后
```

> 每格 = 2.5%（40 格满幅）；`█` = 完整度，`░` = 缺口。排序：强项层 →
> 中间层 → 差距区（值降序）。
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
