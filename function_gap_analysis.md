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
| Select/View/3D | 85% | 强项层 |
| CAD/XT 几何导入 | 80% | 强项层 |
| BAM 分析模型 | 70% | 中间层 |
| Octree 八叉树 | 65% | 中间层 |
| 宿主自动化 COM/VBS | 55% | 中间层 |
| 几何编辑 Create/Modify | 30% | 差距层 |
| 自研网格生成 | 30% | 差距层 |
| Wrapping/Disc/Overset | 25% | 差距层 |
| 条件体系（~180 Cond*） | **15%** | 差距层（最大） |
| Solver/FPH 链路 | 10% | 差距层（合理延后） |

```
功能域                    0        25        50        75      100
────────────────────────────────────────────────────────────────────

【强项层 · 生产级】
PPH 解析与写端          ██████████████████████████████████████░░  95%
工程文件管理            ██████████████████████████████████████░░  95%
Select/View/3D         ███████████████████████████████████░░░░░░  85%
CAD/XT 几何导入         ██████████████████████████████████░░░░░░░  80%

【中间层 · 可用但有条件】
BAM 分析模型            █████████████████████████████████░░░░░░░░  70%
Octree 八叉树           ██████████████████████████████░░░░░░░░░░░  65%
宿主自动化 COM/VBS      ██████████████████████████░░░░░░░░░░░░░░░  55%

···························· 以下为主要差距区 ···························

几何编辑 Create/Modify  ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  30%
自研网格生成            ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  30%
Wrapping/Disc/Overset  ██████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  25%
条件体系(~180 Cond*)   ██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  15%  ◀ 差距最大
Solver/FPH 链路         ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  10%
```

> 每格 = 2.5%（40 格满幅）；`█` = 完整度，`░` = 缺口。排序：强项层 →
> 中间层 → 差距区（值降序），与 §3 差距排序对应。

---

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
| Octree | API 参数链路（DeleteOctree+Initialize+SetOctType+SetMeshNum+SetMinSize）实测边长 0.001/单元约 1000 达标；本地 refine/merge 并行可用；区域 Size 按 main.xml 零件展开 | OCTREEREGION 后序**写端缺**（归 sctsnapshot）；voxmesh 八叉树无 2:1 平衡/pairing |
| 宿主自动化 | `pipeline_plan.LOCKED_COMMANDS` 主链路（open_project/begin_solid_edit/parts_control/build_analysis_model/generate_octree/generate_mesh/save_project）三份日志（box_com_diag1–3）err=0；Wrapping 录制锁定（79 参数对） | in-proc COM 桥（ScflowPipeline）**从未实机验证**（版本相关 RVA 0xD212B8 风险）；外部 COM 被 LocalServer 裸 exe 崩溃结构性阻塞（绕过 Kicker 必崩 0xE0000000）；edit_ops 全部 Ridge/Octant 操作未实测；batch_bridge 仅 dry-run |

### 2.3 差距层（MVP 或桩，10–30%）

| 功能域 | 现状 | 差距 |
|---|---|---|
| 条件体系 | 16 分类页中 analysis_type/basic_setting/analysis_control（~1000 行）/output 有**完整 XML 读写**；5 个 Cond*（CondBoundaryFlowIO/WallStress/WallThermal/Symmetry/CondInitial）有粗桩 XML 编辑器 | **~180 个 Cond* 仅覆盖 5 个粗桩 + 17 个 bc_filters 可见**；~160 个类型不可见；其余 12 个为 session 存根（弹窗「在 scFLOWpre 中完成」）；Detailed Settings 全是桩；region 仅写单 face 引用 |
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
| 4 | **外部 COM 全自动化** | 结构性阻塞 | LocalServer32 注册表直指裸 exe（绕过 Kicker 必崩）；in-proc 桥未实测；当前仅半自动（Kicker 启动 + 宿主内执行 VBS） |
| 5 | **Wrapping/Disc/Overset** | 录制≠验证 | Wrapping 锁定但未实机执行；Disc/Overset 无实质实现 |
| 6 | **native_bam 精度** | 几何近似 | 容差合并/Influence/微小面保留规则与宿主内核不等价 |
| 7 | **边缘 NYI + 质量基础设施** | 11 菜单灰显 | Select 高级项 5 个、Edit 3 个、Ridge 2 个、File 1 个；网格质量统计（非正交度/偏斜度）缺失 |

---

## 4. 改进计划

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
