# pphdecoding 全面重分析：代码状态 × scFLOWpre 功能完整度与深度（2026-08-17）

> 日期：2026-08-17 ｜ 仓库：pphdecoding ｜ 对照：Cradle CFD 2025.2 scFLOWpre
>
> 背景：本会话（parasolid/pskernel 逆向线）与并行会话（P0–P4 功能差距线）均已
> 落地，function_gap_analysis.md 已刷新到 P4 后状态。本文在**最新代码状态**
> （653 测试、76 测试文件、约 30 个顶层模块）上做一轮独立复核，把本会话新增的
> 内核逆向深度（parasolid 二进制 XT、pskernel ABI 映射、V37 新增签名表、
> 双版本审计）计入完整度评估，并给出下一轮（P5）改进计划。
>
> 关联：[function_gap_analysis.md](function_gap_analysis.md)（P0–P4 差距全量）、
> [DEV_PLAN.md](DEV_PLAN.md) §12–§17、[docs/pskernel_user_guide.md](docs/pskernel_user_guide.md)
> （内核调用手册）、[docs/V37_SIGNATURES.md](docs/V37_SIGNATURES.md)（V37 签名表）。

---

## 0.0 对照基准：scFLOWpre 功能面（明确比对对象）

> 本文与 function_gap_analysis.md 的对照对象均为 **Cradle CFD 2025.2 的
> scFLOWpre**（scFLOWpre_Bx64net.exe 前处理器；内部 DLL 名 SCTprime /
> SCTpreCore 是组件名，产品名统一为 scFLOWpre，勿与 scSTREAM 的 STpre 混淆）。
> 其功能面（本仓复刻/逼近的目标）如下：

| 基准域 | scFLOWpre 功能面 |
|---|---|
| 工程容器 | .pph（ZIP + main.xml/xenv/js/prp/sctsnapshot + OCT/MDL/GPH/FLD 成员） |
| 几何 | Parasolid B-rep（CAD 导入 x_t/x_b 等）+ CADthru 分面 + Solid-based/AF faceter |
| 菜单 | File 13 / Edit 19+Ridge 3 / Select 26 / View 40 / Condition 顶层 15 + 向导 ~200 叶 / Execute 9 / Option 多页 |
| 条件向导 | ~180–200 个 Cond* 类型（流/壁/热/辐射/多相/粒子/风扇/电池…） |
| 网格 | Polyhedral（BAM 9 页向导）与 Voxel fitting 两条 mesher 路径；八叉树细化 |
| 高级网格 | Wrapping / Discontinuous / Overset / 棱柱层 / 质量度量 |
| 求解衔接 | scFLOWsolver 输入（FLD/FPH）、scPOST 后处理（FLD/iFLD 读取） |

本仓策略（DEV_PLAN §0.4）：**格式层复刻 + 界面层逼近 + 宿主自动化驱动官方
内核 + 自研 mesher 兼容产物**，明确不以「重写 scFLOWpre 内核」为目标。

---

## 0. 代码状态快照（实测 2026-08-17）

| 项 | 值 |
|---|---|
| 顶层 Python 模块 | ~30 个（最大 nav_panels 622 KB / pph_gui 323 KB / ps_facet2_nodes 70 KB / sctsnapshot 56 KB / parasolid 47 KB / voxmesh 47 KB） |
| 本会话新增 | fph.py / ifld.py / fldstats.py / fldutil_bridge.py（FLD 系）、pskernel_abi.py / pskernel_v37.py / pskernel_v37_sigs.py（内核 ABI 系）、docs/pskernel_user_guide.md / docs/V37_SIGNATURES.md |
| 测试 | pytest 收集 **653 项**（76 个测试文件）；全仓套件 EXIT=0 |
| 版本支持 | CradleCFD2023（Parasolid V34.1）+ CradleCFD2025.2（V37）双版本三通道确证 |
| 最近提交 | P0–P4 功能差距实施 + 条件/材料/自动化收尾 + pskernel 逆向线（bb8bb69…75f213e） |

### 0.1 本会话（内核逆向线）的增量清单

1. **parasolid.py 二进制 XT 全量解码/编码**（P2 线收尾）：A/B/PS 三种 flag、
   指针/正整数 +1 偏移与 pair 编码、变长节点 varlen-before-index、未设哨兵归一、
   编辑序列 n_elts 双约定；V34.1 与 V37 的 PKBody3 均字节级 round-trip；
   此前「后段标量失步」根因（u32/u16 之争 + 顺序颠倒）已钉死。
2. **pskernel_abi.py**：1454 个导出（1204 PK_*）× V35 手册逐函数签名映射
   （V37 覆盖 1101/1204）；PE 导出解析、签名解析、多版本差异、ctypes 原型生成。
3. **pskernel_v37.py + pskernel_v37_sigs.py**：V35 未收录的 **104 个 V36/V37
   新增 PK_***（cellular/lattice/frame 家族）四层手段逆向（家族归类 / 反汇编
   参数推断 / 经验调用 / schema 演进），产出完整签名表（15 high / 89 med）。
4. **版本三通道审计**：2023 = V34.1（34.01.153 / sch_34101 / 3401153），
   2025.2 = V37（37.01.153 / sch_37102 / 3701153）；案例 x_t 输入横跨 V22..V34。
5. **docs/pskernel_user_guide.md**：以 cabdecoding 蓝本为底、合并本仓逆向成果
   的内核调用手册（含 §11.6 待改进项清单）。

---

## 1. 功能完整度与深度重评估（12 域 × 深度注释）

沿用 function_gap_analysis.md 的 12 域与百分比口径，逐域补充**深度**判定
（深 = 字节/签名级；中 = 参数/链路级；浅 = 表单/桩级）：

| 域 | 完整度 | 深度 | 本轮修正说明 |
|---|---|---|---|
| PPH 解析与写端 | 95% | 深 | 无修正（字节级闭环 + 653 测试） |
| 工程文件管理 | 95% | 深 | 无修正 |
| Select/View/3D | 88% | 中–深 | 无修正 |
| CAD/XT 几何导入 | 80% | **深** | 二进制 x_t 全解码（A/B/PS flag）+ 内核 ABI 签名级映射（1101+104）+ V22..V37 输入实测；此前仅文本侧 |
| Octree 八叉树 | 72% | 中 | 无修正（区域写端在快照层，非 .oct） |
| BAM 分析模型 | 70% | 中 | 原生 native_bam 12/12 步 + Wizard VBS 锁定 |
| 宿主自动化 COM/VBS | 62% | 中 | 无修正（in-proc COM 未实机、外部 COM 被 Kicker 阻塞） |
| 条件体系（~180 Cond*） | 55% | 浅–中 | 165 实名类型锁定 + ≥60 可编辑；深度仍在表单层（P5 主战场） |
| 几何编辑 Create/Modify | 45% | **底层深、GUI 浅** | 内核 ABI 已生产级（boolean/transform/delete/基本体 + V37 slice/lattice/frame 签名表），但 GUI 仍是 VBS TODO 占位——**深度错配是本域最大问题** |
| 自研网格生成 | 45% | 中 | voxmesh/polymesh MVP；缺面区域映射与 2:1 平衡 |
| Wrapping/Disc/Overset | 40% | 中 | 录制锁定 + Disc/Overset COM 实测；Wrapping 未实机执行 |
| Solver/FPH 链路 | 10% | **读侧深、算侧边界** | FPH/FLD/iFLD 三格式全解析（本会话新增 fph/ifld/fldstats）；求解器本体 = 产品边界（合理延后） |

### 1.1 哑铃结构的最新形态

- 哑铃的**下端（格式 + 内核直调）已到签名级**：本会话把 Parasolid 侧从
  「调用几个函数」推进到「1204 导出全映射 + 104 新增全补 + 二进制流全解码」；
  与 cabdecoding 的用户手册（blend/mesh ABI 实测）合并后，内核 ABI 知识 =
  双仓最强项。
- 哑铃的**上端（用户功能层）**在 P0–P4 后从「桩」升到「表单可用」，但
  「深度不及表面」的结构性问题仍在：几何编辑 GUI 与内核 ABI 之间、
  条件表单与 XML 参数面之间，存在大量**已证底层、未接线表面**。
- 结论：**下一轮的最大杠杆不是继续深挖内核，而是把已证 ABI 接到 GUI**。

---

## 2. 关键功能差距（重排序）

| # | 差距 | 量化 | 杠杆判断 |
|---|---|---|---|
| 1 | 几何编辑 Create/Modify Parts 未接线 | GUI 4 个 Create 原语 + 布尔/变换 = VBS TODO 占位；底层 ABI 生产级 | **最高杠杆**：内核侧 0 成本，纯 GUI/桥接线 |
| 2 | 条件体系深度 | ≥60/180 可见可编辑，但仅表单层；XML 读写只覆盖 16 分类页中 3 页 | 量大面广，逐批推进 |
| 3 | 自研网格面区域映射 + 2:1 平衡 | 输出 GPH 无区域名；voxmesh 无配对/平衡 | 影响网格可用性验收 |
| 4 | Wrapping 实机执行验证 | 录制锁定但未跑通端到端 | 需要 Kicker 宿主（环境阻塞） |
| 5 | V37 新增 89 med 签名的字段级钉死 | 形态正确、字段未逐字段钉死 | cellular-guise 会话可解锁 |
| 6 | in-proc COM 桥实机验证 | RVA 0xD212B8 版本风险未验证 | 需要带许可证宿主 |

---

## 3. 新改进计划（P5，按杠杆排序）

### P5-1 几何编辑 GUI ↔ 内核 ABI 接线（最高杠杆）

1. Create Parts 四原语走原生 ABI：PK_BODY_create_solid_block（已证）外补
   cylinder/sphere/cone/torus（pskernel_abi 已映射签名，选项结构体按
   pskernel_user_guide §5 范式 memset+o_t_version 实测校准）；
2. Modify Parts 布尔/变换/删面接 ps_facet2_nodes 既有封装（boolean_2 /
   transform_2 / face_delete_2 已生产级）替换 VBS TODO；
3. V37 新增族按需接入：PK_BODY_slice（4 参含 logical，反汇编已钉）、
   PK_LATTICE/FRAME 家族（cellular-guise 前置，见 P5-2）；
4. 验收：box 工程 Create→Modify→Boolean→Save→重开 全链测试 +
   transmit 产物对拍。

### P5-2 V37 新增 ABI 字段级钉死（89 med → high）

1. 定位 cellular-guise 会话引导（PK_SESSION_start 选项 + set_cellular_guise，
   已证 ask 侧 rc=0），在子进程实测 lattice/frame 家族 getter；
2. 逐函数选项转换器反汇编（pskernel_user_guide §11.5 的 o_t_version=4 范式），
   钉死 _o_t/_r_t 字段布局；
3. 目标：把 pskernel_v37_sigs 的 89 med 项中 LATTICE/FRAME/REGION getter
   族升级为 high（其余如实维持 med）。

### P5-3 条件体系参数级对齐（55% → 65%+）

1. 首批 60 个可编辑 Cond* 的 XML 读写补全（当前仅 3 分类页完整）；
2. region 多 face 引用（当前单 face）＋ 单位/范围校验（GenericCondBody
   schema 驱动已就绪）；
3. 材料五库（P4-2 已只读）补 prp 写端回写。

### P5-4 自研网格可用性（45% → 55%）

1. 面区域映射：voxmesh/polymesh 输出 GPH 补 LS_SurfaceRegions 区域名
   （gphstats 写端已有区域 API，缺 mesher 侧指派逻辑）；
2. voxmesh 2:1 平衡 / pairing；质量度量统计接入 quality.py。

### P5-5 宿主验证类（环境依赖，随时插入）

1. Wrapping 端到端实机执行（需 Kicker 宿主，沙箱外）；
2. in-proc COM（ScflowPipeline）实机验证 RVA 0xD212B8 假设；
3. sctsnapshot 记录流字节级重序列化 + **scFLOWpre** 实机验收
   （DEV_SUMMARY §13 遗留；内部组件名 SCTprime/SCTpreCore）。

---

## 4. 验收锚点

- P5-1：Create/Modify 4 原语 + 3 编辑算子 GUI→内核→x_t round-trip 测试全绿；
- P5-2：LATTICE/FRAME getter 族在 cellular-guise 会话 rc=0 实测记录；
- P5-3：≥60 个 Cond* 的 XML round-trip 测试（test_conditions 扩展）；
- P5-4：voxmesh 输出 GPH 含区域名 + 2:1 平衡不变量；
- P5-5：宿主日志（box_com_diag* 系列）新增 wrapping/in-proc 证据。

---

## 5. 与既有文档的关系

本文不替代 function_gap_analysis.md / DEV_PLAN §12–§17，而是**以本会话的内核
逆向成果为输入的一次独立复核**：完整度百分比沿用其口径（已引用），新增的是
「深度」维度与「已证底层未接线」的结构性判断，以及据此排序的 P5 计划。
计划执行后的状态回填请同步 function_gap_analysis.md §0 图表与 DEV_PLAN §17。
