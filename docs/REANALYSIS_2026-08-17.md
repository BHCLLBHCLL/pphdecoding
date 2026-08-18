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
| 4 | Wrapping 实机执行验证 | 录制锁定但未跑通端到端 | ~~需要 Kicker 宿主（环境阻塞）~~ **已解除并跑通**（360/360 步 err=0，§6.1） |
| 5 | V37 新增 89 med 签名的字段级钉死 | 形态正确、字段未逐字段钉死 | cellular-guise 会话可解锁 |
| 6 | in-proc COM 桥实机验证 | RVA 0xD212B8 版本风险未验证 | ~~需要带许可证宿主~~ **已解除并验证**（安装版布局实测，§6.1） |

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

> **环境事实（2026-08-17）**：本机 CradleCFD2025.2 已安装、许可
> 27500@localhost 可达、Kicker 双实例常驻——三项全部在实机完成，
> 详细路径与结论见 §6.1 与 DEV_SUMMARY §6.3 前置块。

1. Wrapping 端到端实机执行（~~需 Kicker 宿主，沙箱外~~ **已跑通**）；
2. in-proc COM（ScflowPipeline）实机验证 RVA 0xD212B8 假设（**已验证**）；
3. sctsnapshot 记录流字节级重序列化 + **scFLOWpre** 实机验收（**已验收**）
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

---

## 6. P5 执行结果（2026-08-16/17，按计划逐项落地）

| 项 | 结果 | 提交 |
|---|---|---|
| P5-1 Create 四原语接线 | cone/torus/rectangle-sheet 内核封装 + geometry_ops GUI 接线 + 测试全绿 | `a5df2ce` `f9eb6ba` |
| P5-2 89 med → high | 5022 根因钉死：cellular 家族需 cellular-guise 实体（PK_BODY_create_implicit/lattice），`PK_SESSION_set_cellular_guise(1)` 会话启动后 rc=900 锁定；如实记为 blocked，未伪造验证 | `92220ac` |
| P5-3 region 多 face | picked_faces 累积注册 + sface_num 多面写回 + 回退 last_pick | `f835bbe` |
| P5-4 网格可用性 | 质量报告接入 voxmesh CLI（`391c270`）；2:1 平衡独立校验器测试（平衡/非平衡双路径，`fca4ebf`）；面区域映射 box 实测 `{'@PartSurface_Part': 1536}` | `391c270` `fca4ebf` |
| P5-5 宿主验证 | 见下 | `22e2bb2` `c64de13` `3487808` |

### 6.1 P5-5 宿主验证实测结果（原标注“环境阻塞”，实测已解除）

> 环境事实的**规范位置**见 DEV_SUMMARY §6.3「前置环境事实」块（安装路径 /
> SCTprime 版本 / 许可可达性 / 三条已验证路径对照表），后续宿主验证先看那里。

环境实测：本机 CradleCFD2025.2 已安装（MSC Licensing 27500@localhost 可达），
Kicker 启动的 scFLOWpre 常驻运行。三项全部获得实机证据：

1. **Wrapping 端到端（首次跑通）**：录制锁定序列 360 步经
   `ExecuteVBSWithFile` 在 scFLOWpre 进程内执行，**360/360 步 err=0**，
   `SaveProject` 产出 `p5_wrapping_e2e_out.pph`（含 `wrappinggroup2.mdl` +
   `wrappinggroup2.oct`，oct 为 101 KB 有效 CRDL-FLD），宿主重开该产物
   err=0。执行日志 `p5_wrapping_e2e.log` / 脚本 `p5_wrapping_e2e.vbs`。
   途中修复一个真实缺陷：`_array_assign_actions` 三段拼接导致 VBScript
   重复 `Dim ArrayParam1_()`（编译期 Name redefined，整段脚本不执行，
   表现为 ExecuteVBSWithFile 返回 False 且无任何输出）；原录制脚本只有
   一处 Dim。现按 `declare=False` 只在首段声明。
2. **in-proc COM 桥 + RVA 0xD212B8 实机验证**：
   - COM `Dispatch` 走 LocalServer32 会拉起**瞬态新实例**（PID 实测出现
     又退出，Kicker 双实例 21240/22468 从未加载本仓 DLL）；
     `ExecuteVBSWithFile` 在瞬态实例内为**真 in-proc**（tasklist /m
     scflow_bridge.dll 实测挂在 scFLOWpre 进程上），11 个厂商模块全加载、
     符号解析成功（`host_pipeline_result.txt`）。
   - 安装版 SCTprime = **6025.20101.20251128**（原 RVA 推导自
     5225.20302.20251223，已是旧补丁）。capstone 反汇编 + 导出符号实测：
     `CreateShapeGroupSet` 仍是 `lea rcx,[rip+G]; call [G+8]-getter`，
     **G=0xd212b8 在新版保留**；但旧版 `[ctx+0xF8]` 文档槽已不匹配
     （新版函数走 `[ctx+0x4C8]` 组注册表）。ReadProcessMemory 实测两个
     Kicker 实例 `[G+8]` 均非空（瞬态 COM 实例为空——缺 Kicker 产品键
     注入的跛脚路径，DEV_SUMMARY §6 已预警）。桥已改为
     `context_ready = [G+8] != null`（SEH 保护），新增 Status /
     ContextReadyRaw / LastExceptionCode 诊断口。
   - 待补项（如实记录）：在 Kicker 实例内（File → Execute VBScript）跑
     通 `context_ready=1 → set_handle>0` 的完整管线。**2026-08-17 回填**：
     gui 后端按实机配方重写并验证到 Execute 步（AttachThreadInput 前台
     恢复 → GetMenuBarInfo 屏幕坐标真实点击菜单 → #32768 弹窗项点击 →
     自绘对话框 UIA ValuePattern+Invoke 填充提交；WM_COMMAND/menu_select
     /WM_SETTEXT/WM_CHAR 对该宿主实测全部无效）。Execute 生效关闭对话框，
     但未产出结果文件（疑为对话框把内容当脚本正文而非文件名，或宿主 UI
     被并发人工操作干扰）——用户选择如实记为待补；宿主窗口就绪后 gui
     后端一键复跑或 manual 后端人工执行即可。
3. **sctsnapshot 字节级重序列化 + scFLOWpre 实机验收**：parse→serialize
   字节恒等（box 27,539 B）已有 23 项回归测试；本轮新增实机验收：
   重序列化后经 `pphwriter.clone_pph` 回写 PPH（9 成员，deflate 后
   751 KB），宿主 `OpenProject` 验收 **ok=True**。

### 6.2 「历史环境阻塞标注」回填验证（2026-08-17）

1. **test_native_bridge::real（DEV_PLAN §12.7 的 pytest 46% 停滞用例）**：
   `SCF_RUN_BRIDGE_TESTS=1` 本机实跑 **7/7 全绿（0.38s）**——加载厂商
   DLL、符号解析、context-not-ready 优雅路径全部验证；旧沙箱停滞不复现。
2. **`-vbs` CLI 参数（DEV_SUMMARY §6.3 清单第 5 条"待实机确认"）**：
   实测**不存在**——两种形式（`-vbs <path>` / `-vbs=<path>`）均正常启动
   GUI 且忽略脚本（标记脚本 90s/60s 无输出，进程被终止）。
   `vbs_bridge.py` cli 后端改为返回显式 unsupported（不再静默拉起 GUI），
   测试同步更新（`b6bf39e`）。
3. **写回产物宿主验收（DEV_PLAN §13.3/§15.1 #7）**：新增 main.xml
   region 改写回填实测——宿主打开改写 PPH ok，但
   `QueryFaceRegionByName("@P5BackfillRegion")` 返回 Nothing（连完整
   克隆原 region 结构仅改名也不生效）。**负面发现：宿主 face region
   注册表权威在 MDL 成员**（`@PartSurface_Part` 仅在
   `meshinggroup1_part.mdl` 字节流出现，main.xml 的 `<regions>` 只是
   镜像），P5-3 GUI region 写端（只写 main.xml）对宿主不生效，需补
   MDL region 名表写端（新增待办）。

### 6.3 MDL region 名表写端 + 注册表权威定位实测（2026-08-17 续）

MDL 名表写端已实现（`mdl.add_surface_region`，parse→write 全量重序列化，
round-trip 测试锁定）。本轮做**全成员逐一改名/追加的宿主实测矩阵**
（box.pph → clone_pph 单成员改写 → 宿主 `OpenProject` +
`QueryFaceRegionByName`）：

| 改写位置 | 宿主结果 |
|---|---|
| main.xml `<regions>` 增 region（完整克隆结构） | 打开 ok，新名不注册 |
| main.xml SECTITEM 增 NAME | 打开 ok，新名不注册 |
| part MDL 名表增名（index 0/1） | 打开 ok，新名不注册 |
| ridge MDL 名表原地改名 | 打开 ok，旧名仍在、新名不注册 |
| GPH `LS_SurfaceRegions` 原地改名 | 打开 ok（**无重建**），旧名仍在、新名不注册 |
| snapshot `ZIPOCTREE→FACEGROUPSW` 原地改名（P3-2 重压缩链路） | 打开 ok，旧名仍在、新名不注册 |
| GPH `LS_SurfaceRegions` **追加记录**（空/1 面/2400 面 × count 同/不同步） | **宿主无界重建**：瞬态实例持续 60–90% CPU，>5 分钟不完成（非模态等待） |
| GPH 无关字节翻转（Application 名） | 打开 ok（对照） |

结论（如实记录，**修正 §7.3 的「宿主认 MDL 权威」判断**）：

1. **GPH region 表追加在宿主侧是禁区**——任何追加（哪怕空区域）触发
   无界重建；`gphstats.append_surface_region` 仅作格式级写端并标注
   host-hostile。原地改名宿主安全（`gphstats.rename_surface_region`，
   实机验证打开 ok）。
2. **宿主 region 注册表的权威写端仍未在文件层定位**：所有含名成员的
   改名/追加均不改变 `QueryFaceRegionByName` 结果（旧名持续解析），
   P6-2「MDL 权威接线」仅保证文件自洽，宿主生效性未证实（疑为宿主侧
   缓存或另有未定位来源；后续待办：对比宿主 Save 前后文件差异）。
3. 本轮交付：`gphstats.rename_surface_region` + `append_surface_region`；
   `_iter_surface_region_blocks` 重写为结构直扫（旧 4 字节步进解析器误吞
   追加记录的 type-1 描述符），gph 系 30 项测试全绿。

---

## 7. P5 后全面重分析（12 域完整度 × 深度清单，P6 规划输入）

> 日期：2026-08-16（P5 收尾 + 工作区清理 + gui 后端复跑后）｜方法：
> 独立代码巡检（40 顶层模块 / ~4.07 万行 / 80 测试文件、598 tests
> 全绿口径）× 本文档 §1 口径逐域复核。与 §1 的差异均已标注。

### 7.1 代码状态快照（巡检修正）

| 项 | 值 | 修正说明 |
|---|---|---|
| 顶层 Python 模块 | **40 个**（~4.07 万行） | §0 旧记「~30」过期 |
| 测试 | 80 个 test_*.py；run_all_tests **598 全绿** | §0 的 653 为 kernel 线会话 pytest 收集口径 |
| >10KB 模块 | 26 个（nav_panels 14896 行最大） | — |
| automation/ | 8 模块（pipeline_plan 1115 行最大） | — |
| NYI 灰显 | **7 项**（2 产品边界 + 5 暂缓） | — |

### 7.2 12 域完整度 × 深度清单（P5 后）

| 域 | 完整度 | 深度 | P5 后变化 / 巡检修正 |
|---|---|---|---|
| PPH 解析与写端 | 95% | 深 | 无变化（字节级闭环） |
| 工程文件管理 | 95% | 深 | sctsnapshot 字节级重序列化（27,539 B 恒等）+ 宿主 OpenProject 验收 ok |
| Select/View/3D | 88% | 中–深 | 无变化 |
| CAD/XT 几何导入 | 80% | 深 | 无变化（二进制 XT + ABI 签名级） |
| Octree 八叉树 | 72% | 中 | 无变化 |
| BAM 分析模型 | 70% | 中 | 无变化 |
| 宿主自动化 COM/VBS | **70%** | 中 | 62→70（Wrapping e2e 360/360 + in-proc 桥 RVA 实证 + gui 后端框架发现修复 `68891e1`）；仍欠：Kicker 实例内 `context_ready=1 → handle>0` 完整闭合（环境态，见 §7.4） |
| 条件体系（~180 Cond*） | **60%** | **浅** | 55→60（P5-3 多 face 引用）；**巡检修正**：165 类型已注册可见，但带字段 schema 仅 6 类型（源自 3 样本工程）——「≥60 可编辑」是目录+粗桩综合口径，字段级深度远低于表面 |
| 几何编辑 Create/Modify | **55%** | 底层深、GUI 中 | 45→55（P5-1：create 6 原语 + transform 4 + boolean/delete_faces 全接线）；`pipeline_plan.py` L855–901 的 VBS TODO 草稿仍残留（实体 API 未录制） |
| 自研网格生成 | **55%** | 中 | 45→55（P5-4：2:1 平衡/pairing/质量报告/面区域映射四能力全有，box 实测 `{'@PartSurface_Part': 1536}`）；欠规模化对拍与黄金文件 |
| Wrapping/Disc/Overset | **55%** | 中 | 40→55（端到端实机跑通 + 产物宿主重开 err=0，P5 首次） |
| Solver/FPH 链路 | 10% | 读侧深 | 无变化（合理延后；fph/fldstats/ifld 读侧全解析） |

### 7.3 哑铃结构的 P5 后形态：三类「表面 ≠ 权威」错配

1. **条件域**：目录可见（165）≠ 字段可编辑（6）——registry 广度与
   schema 深度之间断裂；
2. **region 域**：GUI 写 main.xml 镜像 ≠ 宿主认 MDL 权威——
   `write_mdl(surface_regions=...)` API 层已生产级且 BAM 路径已接线
   （`native_bam.write_bam_mdl` L853），**仅 Register Region GUI 流
   （nav_panels L3115）未调用**——缺口比 §6.2 记录的更窄，纯接线层；
3. **网格域**：质量基础设施（quality.py 4 类度量 + 直方图）≠ 验证
   信用（无与宿主 mesher 的量化对拍、黄金文件仅 box 族）。

下端（格式 + Parasolid 内核）保持签名级无变化；**P6 的最大杠杆
从「接线底层」转向「打通权威闭环 + 字段级扩面」**。

### 7.4 gui 后端复跑补充证据（2026-08-16，`68891e1`）

修复两个真实缺陷后（主框架类名 `Afx:00007FF683D10000:0` 匹配 +
隐藏窗口 visible_only=False 兜底），框架可发现、SW_RESTORE 可恢复
前台；但**闲置 Kicker 实例拒绝打开菜单**——物理点击/合成点击/
消息级 WM_LBUTTONDOWN/Alt+F/UIA DoDefaultAction 五路全部无效，
`WindowFromPoint` 证实命中 'Menu' 工具条、无隐藏模态、UI 线程响应
（SendMessageTimeout ok）。窗口还会在脚本间隙被外部回藏。结论：
非代码缺陷，是 Kicker 实例长驻闲置态的交互限制——完整管线闭合
需新鲜启动的宿主窗口（manual 后端随时可用）。

---

## 8. P6 改进计划（按杠杆排序）

| # | 项 | 内容 | 验收锚点 | 杠杆判断 |
|---|---|---|---|---|
| P6-1 | **条件字段级扩面** | 165 注册类型 → ≥60 类型带字段 schema：样本工程字段提取管线（tools/extract_cond_types + html_cond_extract 交叉）+ 真实录制反推；GenericCondBody 从「样本驱动」升「schema+帮助元数据」双驱动 | ≥60 类型字段表单可编辑 + XML round-trip 测试 | **最高 ROI**：断裂点明确（6→60），基础设施全就绪 |
| P6-2 | **Register Region → MDL 权威接线** | nav_panels L3115 注册流调用 `write_mdl(surface_regions=...)` 回写 MDL 名表（BAM 路径已有同型调用可抄）；宿主验收 | 改写后宿主 `QueryFaceRegionByName` 非 Nothing | 小而关键：~~直接闭合 §6.2 负面发现~~ → **§6.3 实测矩阵显示 MDL 名表写端不足以宿主生效**（全成员改名/追加均不改变宿主解析），验收锚点暂不可达；先做「宿主 Save 前后文件差异」定位权威写回路径 |
| P6-3 | **网格量化对拍 + 黄金文件扩容** | 与宿主 mesher 同几何产物对拍（单元数/非正交度分布）；黄金文件从 box 族扩 2–3 个真实几何 | 对拍报告 + 不变量回归 | 把「有基础设施」变成「有验证信用」 |
| P6-4 | **几何 VBS 草稿清理** | pipeline_plan L855–901 TODO 占位：录制锁定实体 API 或删除（原生路径已是正路） | 草稿清零或锁定 | 消除「表面接线、深层 TODO」残留 |
| P6-5 | **宿主交互环境收敛**（环境依赖，随时插入） | 新鲜 Kicker 启动宿主 + gui 后端一键复跑完整管线（框架发现已修）；或调查 Kicker 启动参数 | `context_ready=1 → set_handle>0` 实测日志 | 闭合宿主自动化最后 30% 的关键步 |
| P6-6 | cellular-guise 子进程实验（低优先） | PK_SESSION_start 选项在会话启动前设 cellular guise（避开 rc=900），实测 lattice/frame getter | getter rc=0 实测记录 | 边缘家族，不阻塞主线 |

**Solver/FPH 维持合理延后**（读侧已深，算侧为产品边界）。

---

## 9. P6 执行结果与 12 域刷新（2026-08-17）

> P6-1..P6-4 + 收尾项（Octree 写端验证 / BAM Influence / 宿主诊断口 /
> Wrapping 清理）全部落地，每项独立提交并推送。本节为 §7.2 清单的
> 刷新版；P6-5 环境态部分完成（诊断口就绪，完整管线仍待宿主窗口可见）。

### 9.1 P6 执行摘要（交付 × 回归 × 提交）

| 项 | 交付 | 回归 | 提交 |
|---|---|---|---|
| P6-1 条件字段级扩面 | `condition_help_schema.py` 三源合并：样本 10 类（精确 XML 键，**不覆盖**保持 round-trip 精确）+ HTML 帮助页 184 页（显示名 sanitize 为 snake_case 键）+ 求解设置树 `condition_tree.json`（XML 键）注入；带字段 schema 类型 **10 → ≥25** | 条件相关 53 tests 全绿 | `619c899` |
| P6-3 网格量化对拍 | quality benchmark vs 宿主 box 黄金（纯 hex `max_depth=2` + 切割路径非正交度不劣于宿主断言）+ gphstats numpy2 大小端 U4 写端溢出修复 | 网格/GPH 62 passed 1 skipped | `6a8624e` |
| Octree 写端验证 | OCTREEREGION 后序写端 roundtrip（前序→后序编码 + ZIPOCTREE BYTEARRAY 等长约束 + `serialize(original_data=)` 语义钉死） | 19 tests 全绿 | `8ea7ec7` |
| BAM Influence | `BamParams.influence_enable/targets` 透传 `BamReport` + `summary_lines`（几何效应仍在宿主内核，配置如实记录） | 22 tests 全绿 | `dd7ba88` |
| P6-5 宿主诊断口 | `host_pipeline.host_status()`：安装/Kicker 启动器/在跑实例/主框架可见性/`gui_ready` 一屏诊断 + `--status` CLI；gui 后端错误提示明确指向 `Kicker_Bx64.exe` | 16 tests 全绿 | `70535ae` |
| P6-2 + P6-4 几何 | P6-2：`mdl.add_surface_region` 名表回写（Register Region → MDL 权威接线 API 层）；P6-4：Create/Modify Parts VBS TODO 草稿清零，实体操作明示走原生 `geometry_ops` | 几何编辑 24 tests 全绿 | `91ac5ec` |
| Wrapping 清理 | 「占位/待录制锁定」陈旧标注清除、未知 op 由静默 TODO 改显式 `ValueError` + 测试 | 6 tests 全绿 | `ab83e35` |

**P6-1 诚实记录**：≥25 类型（样本 10 + HTML/树注入）未达「≥60 类型」
目标——HTML 帮助页只有显示名（无 XML 键），自动关键词匹配误匹配率高
已弃用；突破 60 需 P6-5 真实录制反推或更多样本工程（权威 XML 键源）。

### 9.2 12 域完整度 × 深度清单（P6 后，vs scFLOWpre 2025.2）

| 域 | 完整度 | 深度 | P6 后变化 |
|---|---|---|---|
| PPH 解析与写端 | 95% | 深 | 无变化（字节级闭环） |
| 工程文件管理 | 95% | 深 | 无变化（sctsnapshot 重序列化 + 宿主验收 ok） |
| Select/View/3D | 88% | 中–深 | 无变化 |
| CAD/XT 几何导入 | 80% | 深 | 无变化（二进制 XT + ABI 签名级） |
| Octree 八叉树 | **75%** | 中 | 72→75：OCTREEREGION 后序写端 roundtrip 验证（19 tests） |
| BAM 分析模型 | **73%** | 中 | 70→73：Influence 参数透传 BamReport（22 tests）；几何效应仍在宿主内核 |
| 宿主自动化 COM/VBS | **72%** | 中 | 70→72：`host_status()` 诊断口（16 tests）；Kicker 实例内 `context_ready=1 → handle>0` 完整管线仍待宿主窗口可见 |
| 条件体系（~180 Cond*） | **68%** | 浅–中 | 65→68（P7-1 样本深扫：25→33 类型，见 9.4）；60→65 为 P6-1（10→≥25） |
| 自研网格生成 | **63%** | 中 | 55→63：量化对拍 vs 宿主黄金 + numpy2 写端修复（62 passed/1 skipped）；黄金文件仍 box 族 |
| 几何编辑 Create/Modify | **62%** | 底层深、GUI 中 | 55→62：MDL 名表写端 API + VBS 草稿清零（24 tests）；GUI 归档 flush 接线 + 宿主 `QueryFaceRegionByName` 验收待补 |
| Wrapping/Disc/Overset | **58%** | 中 | 55→58：占位清理 + 显式报错（6 tests）；质量清理，无新能力增量 |
| Solver/FPH 链路 | 10% | 读侧深 | 无变化（合理延后；fph/fldstats/ifld 读侧全解析） |

### 9.3 剩余缺口（P7 输入，按杠杆排序）

1. ~~**条件字段 schema 25→60+**：需更多样本工程~~ **P7-1 已部分交付**
   （25→33，吃透现有样本的嵌套条件面，见 9.4）；进一步突破仍需
   P7-3 真实录制反推或新样本工程；
2. **Register Region GUI 归档 flush 接线**：`mdl.add_surface_region`
   API 已就绪（P6-2），纯 GUI 接线 + 宿主 `QueryFaceRegionByName`
   非 Nothing 验收；
3. **Kicker 实例内完整管线**（`context_ready=1 → set_handle>0`）：
   需前台可见宿主窗口；`python -m automation.host_pipeline --status`
   可一键判断就绪态（gui_ready）；
4. **网格黄金文件扩容**：box 族 → 2–3 个真实几何，对拍报告常态化；
5. **cellular-guise 会话锁定根因验证**（rc=900，P6-6 未动，低优先）。

### 9.4 P7-1 条件 schema 扩源（2026-08-17 交付）

**根因**：`pphxml.conditions()` 只读 `<conditions>` 直接子级——样本中
嵌套在 `output_param/`、`particle_dem/`、`radiation/`、`info_sted/`、
`multiphase_cond/` 子树内的条件全部漏提（P6-1「需更多样本工程」结论的
一半缺口其实就在现有样本里）。

**交付**：
- `MainXml.all_conditions(known_types)` 深扫三类形态（嵌套 `condition`
  元素 / 条件形容器 `<type>CondXxx</type>` / 空 type 按父容器推断），
  `cond_types.json` 目录交叉核对（165 实名类型）防值槽假阳性；
- `schema_extract` 接入深扫；`schemas/merged.json` 以 6 样本重建
  （box/box2/box_disc/box_overset/laptop/p5_wrapping），类型 10→20；
- 注册表带字段类型 **25→33**：净新 8（CondParticleBoundaryDEM 100 字段、
  CondParticleSymmBoundaryDEM、CondParticleSymmHeatBoundaryDEM、
  CondOutputLFileYplus/Passage/ElectricCurrent、CondStedInfo 21、
  CondMultiphaseMaterial）+ 权威升级 2（CondBoundaryRadiation 4→32、
  CondOutputLFileHeatTransfer 5→22，html 显示名键 → 样本 XML 键）；
- `tests/test_condition_deep_scan.py` 13 项（三类形态命中、假阳性排除、
  33 覆盖、样本键优先）；条件域回归 59 tests 全绿。

**诚实边界**：Symm*DEM 在样本中是裸默认条件（仅 type/name/regions 无
参数面），入注册表但表单元数据为空——如实反映样本，不虚构字段。

### 9.5 Wave A–E 执行结果与 12 域刷新（2026-08-17 晚，P7 首轮波次）

> P7-1 之后按 §8「产品 100%」计划推进 Wave A–E（10 提交：
> `5ae3b71`/`3a8a826`/`558a468`/`db04808`/`0c18ef8`/`084d3a2`/
> `6971cdc`/`3ca616c`/`183ffc3`/`0703049`）。本表取代 §9.2（P6 快照）。

#### 9.5.1 Wave 交付摘要

| Wave | 交付 | 测试增量 | 提交 |
|---|---|---|---|
| A 写端闸门 | `project_persist.py`（clone_pph 新成员/XT 登记/MDL regions）+ GUI Save As/XT register/Register Region MDL flush + 空工程模板 | test_project_persist 196 行、test_empty_project 85 行、test_register_region +108 行 | `5ae3b71`/`3a8a826` |
| B 宿主闸门 | Disc/Overset 开关持久化（COM True/False 锁定）+ OpenCadFile/QueryFace VBS | test_host_pipeline +41 行、test_parts_control 139 行 | `558a468` |
| C 条件扩面 | 精确 XML 键 60+ 类型 + 官方例工程键并入（`official_examples.py` + merge 工具） | test_official_schema 120 行 | `db04808`/`183ffc3` |
| D 网格/八叉树收口 | box_disc 黄金 + L-shape OCTREEREGION/mesh 检查 + CAD tessellation 回退 | benchmark +57 行、oct_region_write +70 行、surface_mdl_fallback 69 行 | `0c18ef8`/`3ca616c` |
| E Select 收口 | Spread Face to Edge（mdl 邻接查询 + GUI） | test_spread_face_to_edge 81 行 | `084d3a2` |
| 独立 | GPH LS_SurfaceRegions 写端（原地改名宿主 open=0 实测；追加=宿主无界重建，已作 host-hostile 警告）；官方 Disc/Overset group layout 钉死 | gph_write_sections +42 行、official_disc_overset 82 行 | `6971cdc`/`0703049` |

**条件域量化（实测）**：注册表 165/165 目录类型带字段 schema（总量
28,111 字段），其中 56 类型由真实 PPH 背书（count>0：仓内样本 + 官方
例工程；CondBatteryModel 576 / CondMoving 644 / CondBoundaryFlowIO 439 /
ParticleForceConnection 411 / CondMultiphaseMaterial 390 / CondPorousMedia
293 / CondParticleGenerationDEM 240 / CondFan 184 字段）。

#### 9.5.2 12 域完整度 × 深度清单（Wave A–E 后，vs scFLOWpre 2025.2）

| 域 | 完整度 | 深度 | Wave 变化与证据 |
|---|---|---|---|
| PPH 解析与写端 | **96%** | 深 | 95→96：clone_pph 新成员追加固化 + GPH LS_SurfaceRegions 写端（原地改名宿主 open=0；追加宿主敌对——诚实负面入警告） |
| 工程文件管理 | **97%** | 深 | 95→97：Save As 接线 + XT→xml/mdl/zip 登记 + 空工程模板（New→Import XT→Save→宿主开闭环测试） |
| Select/View/3D | **90%** | 中–深 | 88→90：Spread Face to Edge；NYI 清单减员 |
| CAD/XT 几何导入 | **85%** | 深 | 80→85：XT 预览+工程登记统一路径（Save 后宿主 Parts 树非空）+ OpenCadFile（STEP 走宿主）VBS |
| Octree 八叉树 | **78%** | 中 | 75→78：L-shape OCTREEREGION 回归（oct_region_write 扩 70 行） |
| BAM 分析模型 | 73% | 中 | 无增量（域 6 宿主 e2e 属 Wave B 剩余项） |
| 宿主自动化 COM/VBS | **76%** | 中 | 72→76：全成员宿主实测矩阵 7 场景（OpenProject+QueryFaceRegionByName 真机）+ gui 后端实机配方到 Execute 步 + Disc/Overset 开关 VBS；**完整管线 set_handle>0→结果文件仍待补** |
| 条件体系（~165 Cond*） | **80%** | 中 | 68→80：165/165 带字段 + 56 真实 PPH 精确键（官方例并入）；§8.2 的「≥60 精确键」差 4 个，其余按「generic+不覆盖未知」满分口径已满足 |
| 自研网格生成 | **68%** | 中 | 63→68：box_disc 黄金 + L-shape mesh 检查 + CAD tessellation 回退 + GPH 区域名写端 |
| 几何编辑 Create/Modify | **66%** | 底层深、GUI 中 | 62→66：Register Region GUI flush 接线（mdl.add_surface_region→clone_pph）；**宿主 QueryFaceRegionByName 全路径「新名不注册」**（7 场景矩阵全负面——权威名表源在宿主内部，未定位）；ridge.mdl 回退 |
| Wrapping/Disc/Overset | **65%** | 中 | 58→65：Disc/Overset 开关持久化 + 官方 group layout 钉死；建组/BDF·RotorInfo 映射录制仍缺 |
| Solver/FPH 链路 | 10% | 读侧深 | 无变化（合理延后） |

#### 9.5.3 诚实负面与剩余缺口（P8 输入）

1. **宿主名表权威源未定位**：7 场景写路径（main.xml regions/SECTITEM、
   part/ridge MDL 名表、GPH LS_SurfaceRegions、snapshot FACEGROUPSW）
   全部「打开 ok 但新名不注册」；GPH 追加更触发宿主无界重建——
   Register Region 的宿主生效路径需下一轮反推（疑内部二进制缓存/注册
   流程，非任何已测绘容器）；
2. **宿主管线最后一公里**：gui 后端到 Execute 步生效（对话框关闭）但
   无结果文件产出；Kicker 前台实例一键复跑仍是最短路径；
3. **BAM 宿主 e2e**（域 6）与 Wrapping 建组/BDF 映射录制（域 11 剩余）
   未动；
4. **条件精确键 56→60+**：补 4 个即可达 §8.2 关门线（持续数据积累）。
