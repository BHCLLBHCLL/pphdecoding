# pphdecoding 当前代码状态独立复核 —— 对照 scFLOWpre 2025.2

> 复核日期：2026-09-12 ｜ 基线：HEAD `7838278`（J5）+ J6/J7 未提交改动（7 modified / 108 untracked）
> 方法：**代码级验证**（读实现 + 跑测试 + 独立复算产物），非文档转述。
> 对照基准：本机已安装的 Cradle CFD 2025.2 scFLOWpre（`SCTpre_Bx64net.exe`）及其
> 手册 `Manuals/scFLOW/HTML/Pre_eng`（468 主题页 / 428 菜单项，2026-09-12 实测解析）。

---

## 0. 一句话结论

**这不是 scFLOWpre 的替代品，而是三层组合体**：① 生产级的 **PPH 格式工具链**（离线、部分字节级）；
② 一个**查看器 + 浅编辑器 GUI**（123 菜单项，写回 `main.xml/xenv/prp/x_t`）；
③ 一个**驱动已安装 scFLOWpre 的自动化 + 验证框架**（VBS/COM/C-ABI，真实产物）。

按 scFLOWpre 真实功能面衡量：**整体完整度约 70–76%，深度呈哑铃形**——
格式层 **L3**（真字节级、可复现），宿主驱动层 **L2**（产物真实但能力来自宿主），
GUI/自研算法层 **L1–L2**（大量面板只写内存 session，自研 mesher 与官方内核无等价性）。
仓库文档宣称的「12 域 / 双口径 100%」是**口径与记账产物**，不是测量结果（见 §5、§6）。

**并且：当前工作树回归是红的** —— 我方独立全量复跑两次均为
**1 failed / 1101 passed / 4 skipped（625 s / 682 s）**，与文档「回归全绿」矛盾。

---

## 1. 对照基准：scFLOWpre 2025.2 实测功能面

从手册 `hh_toc.htm` 解析（非人工估计）：

| 顶级菜单 | 条目数 | 本仓 GUI 菜单项 | 差距 |
|---|---:|---:|---|
| Condition | **284** | 13 | 最大落差：仓内用「1 个通用表单 + 194 类型目录」替代 284 个专用对话框 |
| Option | 34 | 3（+鼠标模式/工具/语言 QActionGroup） | 20/23 设置页只写内存 session |
| View | 32 | 33 | 表面已对齐 |
| Select | 25 | 18 | 拾取模式全在，行为测试缺失 |
| Edit | 21 | 22 | 表面已对齐 |
| File | 12 | 12 | 对齐 |
| Execute | 9 | 11 | 对齐 |
| Help | 3 | 3 | 对齐 |
| **合计** | **428** | **123（其中 1 项 NYI 灰显）** | 差距 100% 集中在 Condition / Option |

> `tools/scan_nyi_menus.py` 复跑确认：**唯一未接线菜单项** = Edit → Restore Closed Volume Data…
> 但「已接线」≠「等价」：见 §4-C。

---

## 2. 仓库规模与形态（实测）

| 层 | 文件数 | 行数 |
|---|---:|---:|
| 根目录 Python（格式层 / GUI / 算法） | 46 | 43,285 |
| `automation/`（宿主自动化 + 求解链） | 14 | 6,693 |
| `tools/`（E2E 驱动 + 收割 + 扫描） | 27 | 7,737 |
| `tests/`（pytest 测试） | 114 | 18,634 |
| `tests/box/`（逆向分析脚本，pytest 不收集） | 261 | 16,064 |
| `native/`（C++ 桥 + COM 组件 + 构建） | 5 | 1,668 |
| 文档 Markdown（根 + docs/） | 17 | 30,933 |
| Schema JSON（merged / vb_api_catalog / cond_types…） | 6 | 193,575 |
| **合计 Python** | **462** | **92,413** |

证据产物：**44 个宿主 E2E 日志**（39 个 err=0 且有 end 标记）、**39 个 `*_out.pph`（237.7 MB）**、
**139 行挂起/异常台账** `hang_characterization.jsonl`（ok 82 / error 47 / hung 10）、
5 组求解器 FPH/RPH 产物、~300 个 `tests/box/` 黄金件（含 1,227 页 Parasolid V35 手册缓存、88 MB 反汇编缓存）。

---

## 3. 分层深度清单（A–E）

### A. 格式 / 解析层 —— 全仓最强，**L2–L3**

| 模块 | 行数 | 真实能力 | 深度 |
|---|---:|---|---|
| `sctsnapshot.py` | 1,349 | 小端 CADThru 记录流、LZMS、PKBody3、**重序列化与宿主字节恒等**（box+laptop+150/150 官方案例）；OCTREEDIVISION 前序位图 / OCTREEREGION 后序字节编解码 | **L3** |
| `blowfish_le.py` | 111 | PKBody3 Blowfish-LE ECB，**重加密逐字节复现宿主密文** | **L3** |
| `parasolid.py` | 1,198 | XT 传输流 schema 驱动编解码，`parse→encode` 字节恒等（'A'/'B'/'PS' 三方言，含 V34.1 跨版本） | **L3（格式）** |
| `gphstats.py` | 1,019 | GPH 体网格读写；**section 采用原生 40 字节头**，多节与宿主逐字节一致 | L2 |
| `mdl.py` | 844 | MDL 面片读写（区域 / 闭体 / 体区域 / ridge）+ 微小面·多重边·面匹配分析 | L2（写端有偏差，见 §7-1） |
| `oct.py` | 413 | 八叉树前序位图 + 叶子重建 + 写端 + 细化/粗化 | L2（unit 恒空，见 §7-2） |
| `pph_parser.py` / `crdlfld.py` / `pphxml.py` / `pphwriter.py` | 504/337/330/161 | ZIP 容器、CRDL-FLD 公共层、XML 方言净化还原、LZMS+Blowfish 写回 | L2（成员级字节保持；容器字节不复现） |
| `ps_facet2_nodes.py` / `ps_tessellate.py` / `geometry_ops.py` | 1,791/558/579 | **直调厂商 `pskernel.dll`**：分面、B-rep 拓扑遍历、create_solid_*/boolean/transform/sew；真实内核调用 | L2–L3（内核中介） |
| `pskernel_abi.py` / `_v37*.py` | 366/333/201 | 1,081(2023)/1,101(2025.2) 个 PK_* 导出签名映射；V37 独有 104 个 = 家族+argc 元数据 | L1–L2（元数据） |

**关键结论**：读端 ~90% 完整、有真 L3 证明；**写端 ~55–65%**，全部写端只在「自己读得回来」层面闭环，
**没有任何一项做过宿主回读验收**。

### B. 宿主自动化 + 求解链 —— **L2–L3，但强依赖宿主**

- **三层机制**：ROT 附着常驻实例 → `Application.ExecuteVBSWithFile`（权威通道）；
  进程内 COM 组件 `pphdecoding.ScflowPipeline`（HKCU 注册）→ SCTprime C++ ABI 直调；
  诊断用 dispatch 实例。`-vbs` CLI 已证伪；裸 exe 启动因缺 Kicker 许可注入会崩。
- **命令库**：`LOCKED_COMMANDS` 12 条（open_cad_file / open_project / begin_solid_edit /
  mesher_settings 146 动作 / parts_control / build_analysis_model 99 动作向导 /
  generate_octree / set_mode_octree / generate_mesh / set_mode_mesh /
  begin_wrapping 43 动作 / save_project），`UNLOCKED` 1 条（quit，从未在宿主执行）。
  录制来源 `tests/box_vbs*.vbs`（UTF-16 BOM）行级锁定。
- **真实产物**：BAM → `_part.mdl` 1.7–3.0 MB；octree → `.oct` 101 KB→472 KB；
  mesh → `.gph` 1.0→5.0 MB；wrapping → `wrappinggroup{1,2}.mdl` 2.97 MB + 0.23 MB + oct 101 KB；
  XT 导出 → `p12e_xt_out.X_T` 4,855 B；disc/overset 容器与黄金件**指纹同类（独立复现 0 差异）**。
- **求解链**：真的提交厂商 MPI 求解器并判定完成（`CALCULATION FINISH` ×2）；
  `solver_delta.py` 对 FPH 逐场点对点 Δmax/Δmean/Δrel + tol 门控。
  **但数值等价证据薄弱**：I5 的「全零 delta」是在一个 **PRES/VEL 均值恒为 0 的零流场**上得到的。
- **自愈基建**：`FlowExecutor`（日志活性监视 + MiniDump 取证 + 杀进程 + 冷启动重试）、
  `ModalWatcher`、`host_boot`。台账 10 次挂起全部处置；J7 三流程 187 检查 0 人工干预。
- **typed API 覆盖**：`catalog_coverage()` = 17 typed + 136 `startswith("Cond")` + 46 generic-call
  —— **纯名称划分**，182/199 类从未在宿主上跑过。

### C. GUI 层 —— 表面 ~95%，语义 **~35–40%**

- `pph_gui.py` 7,681 行：8 菜单 / 123 动作 / 3 工具条 / 5 PaneFrame / 4 工作栈页；
  `nav_panels.py` 14,915 行：22 个导航面板 + 13 个对话框 + 条件向导 16 页 + AMW 9 页。
- **真正持久化**（写回 `main.xml` / `main.xenv` / MDL 名表 / `x_t`）的面板仅 5 族：
  条件向导核心、Parts Control、Mesher/Faceter（14 xenv 键）、Import/Modify Parts（9/4 键）、AMW 参数（14 键）。
- **只写内存 session（重启即失）**：Part Material 指派、Mesh Parameter、Non-Solid Part、
  Register Region 的 Apply、**Option Settings 20/23 页**。
- **纯脚手架（L0）**：Undo（只回滚 3 个 session dict，回滚不了已提交的成员字节）、
  Project Type Setting（只读弹窗）、Change Language、Octant 邻接显示、Prism Layer 报告、
  Measurement（仅 AABB 对角线）、Output-of-List-File 子页（可编辑但 apply() 从不读）。
- **BC 子编辑器是「壳」**：例如 flow BC 只写 3–5 个 XML 标签，而宿主 `CondBoundaryFlowIO`
  实际有 **592** 个字段路径。
- **3D**：VTK 查看器真实可用（MDL/OCT/GPH 图层、剖切、橡皮框拾取建区域、质量/干涉检查），
  但**没有任何解场后处理**（FPH/LPH 数据在 GUI 里根本没有通路）。
- **`main.sctsnapshot` 从不回写** —— 任何零件/条件编辑后快照即过期，且无宿主回读验证。

### D. 自研网格 / 几何层 —— **功能面 ~25–30%，深度 L2（本机实测对拍）**

| 模块 | 行数 | 算法 | 实测 vs 宿主黄金件 | 深度 |
|---|---:|---|---|---|
| `voxmesh.py` | 1,131 | snappy 式 castellation：八叉树自适应细化 → 2:1 平衡 → inside/cut/outside 分类 → 内部 hex + 切割带 ConvexHull → pairing 悬挂面 1:4 分裂 → `.oct`+`.gph` | 宿主 box 黄金 = 944 单元 / 体积精确 1e-6 / 非正交 max 25.81 / 边界 5.29；voxmesh rough d2/max4 = **2,528 单元、体积 +6.12%**（且该误差**不随细化下降**：各深度恒为 +6.12%，因 margin 0.02 使 `n_outside=0`，rough 网格填满整个根盒）；cut-poly max4 = 2,528 单元、-1.65%、边界非正交 52.5°；`fit_to_surface` 近似 no-op（snap 前后顶点数与坐标和 9 位小数相同） | **L2 算法 / L1 互操作** |
| `polymesh.py` | 781 | 真 clipped Voronoi（Delaunay 对偶）：表面/镜对/尖边球/近壁层 seed → 体积质心 Lloyd 平滑 → 有界 Voronoi 胞元 → 表面凸裁剪 | box 实测 div8：1,604 单元、**体积 -0.00%（精确）**，但**边界非正交 max 77.19° vs 宿主 5.29°**；**输出的 GPH 完全不写区域名**（`write_gph` 不传 surface_regions/cvol/volume_regions） | **L2** |
| `native_bam.py` | 869 | 真拓扑/数值：一致定向 + 水密分量定向翻转 → csid；多重边并查集；面匹配（质心/法向 -0.99/面积 1%）；微小面并查集坍缩；Repair 量化哈希焊接；ridge 二面角 | **本层最接近宿主**：`remove_tiny=False` 时 laptop 4 闭体 == 宿主、**ridge 边 1,971 == 宿主 1,971 精确**、逐体面划分与宿主一致（仅标签置换）；box ridge 边 852 == 宿主 852。但特征节点规则用 `>=2` 而宿主是 `>=3`（1,877 vs 188）；22 个 BamParams 中 **10 个从未生效** | **L2（记账级 L3）** |
| `geometry_ops.py` | 579 | **不是自研**：ctypes 驱动 Cradle 自带的 Parasolid V37 `pskernel.dll`（同产品同内核）：block/cyl/sphere/cone/torus、boolean、transform、sew、trimmed sheet、facet→B-rep | 无 Cradle 安装即抛错（测试 skip）；操作面窄：**无 fillet/chamfer/loft/sweep/extrude/revolve/shell/draft/pattern**；对 faceted body 的 boolean 是近似的 | **L3（依赖宿主内核）** |
| `quality.py` | 439 | checkMesh 式指标 | 非正交度/偏斜度/体积/质心 4 项定义正确（宿主 box 体积精确 1e-6）；**长宽比指标实现错误**（只取 owner 面、与文档定义不符），在宿主黄金 GPH 上给出 n=943/944、max 62,777，在 polymesh 上给出 1e14–1e15 | **L2** |

**关键缺口**：三向对齐测试（`test_oct_tri_alignment.py`，5 精确 + 2 两向）验证的是**宿主产物之间**的一致性，
**自研 octree 从不参与**；**自研 `.oct`/`.gph` 从未被宿主打开过哪怕一次**
（GUI 只用本仓 reader 重开自己写的 pph）——这正是 §6 子序 bug 能存活的原因。
native 路径的 `wrapping` 也不是算法，只是把面片写成 `*_wrap.mdl`；真正的 wrapping 由宿主执行。

### E. 测试与证据 —— 数量大，**但近 4 成测不到宿主行为**

- **1,106 测试 / 114 文件**；本次全量：**1 failed / 1101 passed / 4 skipped（625 s）**。
- **live host 测试 = 0**：所有 `win32com/pythoncom/pywinauto` 引用都是 mock/fake；
  真实宿主证据全部来自手工运行的 `tools/_p12*_run.py`，落在根目录 `p12*_e2e.*`，**不在 pytest 内**。
- **~166 个「生成器自证」测试**：加载 `tools/_p12*_run.py`，断言**自己生成的 VBS 源串**
  （`assertIn("MG_.CreateMesh", joined)`）或解析自己写的合成日志。
- **~248 个 mock 化自动化测试**；`test_select_pick` / `test_menu_bar` / `test_view_keys` 等
  直接 `assertIn` `pph_gui.py` 的**源码字符串**。
- 上述两类合计 **~415/1,106（37%）在原理上无法发现宿主行为错误**。
- **真·断言宿主结果**且通过的：`TestOfficialSnapshots`（150/150 字节恒等）、
  八叉树三向对齐（5 官方样本）、PKBody3 三条流字节恒等、`test_bam_reconcile`、
  `test_disc_overset_golden`、`test_mesh_quality_benchmark`——**这批是全仓最有价值的资产**。
- **没有任何测试解析 `p12*_e2e.log`** —— E2E 证据语料完全没有回归锁定。

---

## 4. 12 域对照：文档声称 vs 独立复核

| # | 域 | 声称 | 实际支撑（证据类型） | 复核后 | 残留风险 |
|---|---|---|---|---|---|
| 1 | PPH 解析与写端 | 100% L3 | (a) 快照 150/150 字节恒等、PKBody3 三流字节恒等、clone/XML/LZMS round-trip | **93% L3** | LZMS 写端 Windows-only 却仍算达成项 |
| 2 | 工程文件管理 | 100% L3 | (a)+(b) 同上；Save-override 测试用的是**假 archive** | **88% L2–L3** | 「新建→导入→执行→保存→宿主重开，零丢失」从未作为一条链演示 |
| 3 | Select/View/3D | 100% L2 | (c) NYI 由「改口径」6→1；接线测试断言源码字符串 | **68% L1–L2** | 拾取/橡皮框/视图行为无行为级测试 |
| 4 | CAD/XT 导入 | 100% L2–L3 | (a) XT 拓扑 + PKBody3 闭合；STEP 真 2 零件真 bbox；STL 落 `part.mdl`。**(c) CATIA V5 零几何**、V4/V6 无样本 | **70% L2** | CATIA 导入本机不可用，被登记为「产品边界」而非修复；**2026-09-13 用 6 个新样本 + 同场 XT 对照复测，边界维持（见 §9）** |
| 5 | Octree | 100% L2+ | (a) **证据最扎实**：快照位图↔`.oct`↔GPH 三向对齐 5 样本精确；REGION 后序写回字节等 | **92% L2+** | 细化**参数语义**仅 err=0，未做数值对拍 |
| 6 | BAM | 100% L2+ | (a-ish) 宿主 MDL vs 原生拓扑不变量对拍；向导 3125/3125 err=0 | **76% L2** | 密度/Influence 几何 = recorded-only 豁免 |
| 7 | 宿主自动化 | 100% L2+ | (c) 「199/199」是名称划分（17 typed + 136 前缀 + 46 generic），末桶对着 mock 断言 | **82% L2+** | 182/199 类从未上过宿主 |
| 8 | 条件体系 | 100% L2+ | (b)+(c) 165 = exact_key 92 / alias 1 / **boundary 72（43.6%）**；对账脚本**硬编码 92/1/72** | **65% L2** | 65/72 边界类型的字段 `count=0, samples=[]`，是名字不是键 |
| 9 | 自研网格 | 100% L2+ | (a) 宿主 CreateMesh ret=True；自研 vs 黄金**仅质量阈值** | **66% L2** | 与宿主网格无几何/数值等价 |
| 10 | 几何编辑 | 100% L2+ | (a) `QueryFaceRegionByName` 首次非 Nothing（含阴性对照）+ 重开腿 + J7 13/13 | **80% L2+** | CreateMDL 以产物判定（COM 方法 void） |
| 11 | Wrapping/Disc/Overset | 100% L2+ | (a) disc/overset 指纹独立复现 0 差异；(b) **wrapping 日志截断** | **72% L2** | `p12e_wrapping_e2e.log` 814 步 err=0 但**无 end 标记**；台账 10 次挂起 |
| 12 | Solver/FPH | 100% L2+ | (a) `CALCULATION FINISH` ×2 | **60% L2** | 仓内**零** `.fld/.iFLD` 产物；I5 delta 建立在零流场上；官方例 exA36-3 8/8 MPI rank BAD TERMINATION |

**复核均值 ≈ 76%**（文档 100%）。

---

## 5. 与文档结论的冲突点（可验证）

| # | 文档声称 | 反证 |
|---|---|---|
| O1 | 「12 域双口径 100%」 | 由**改口径**产生：§9.1 完整度 = 「菜单可用**或**灰显且有理由」；§9.6 豁免数值内核；§9.7 第 8 项从「165/165 精确 XML 键」改写为「165/165 三类归属」（精确键战役止步 90/165） |
| O2 | §9.7 第 12 项「FLD 回读全链闭合」 | 仓内 **0 个** `.fld/.iFLD` 文件；`i5_summary.json` 记 `fld:[], ifld:[], fld_compare:null`；该项从未改回 |
| O3 | 域 12「数值等价」 | I5 delta 表算在单开口边界 box 上：`EC_Scalar:PRES` 均值 0.000000、`EC_Vector:VEL` 均值 0.000000 —— 对全零场求 delta 近乎空断言；有真实场的 50 Pa 变体从未双跑 |
| O4 | 域 7「typed 对账 199/199 全覆盖」 | `automation/scflowpre_api.py` 的 `catalog_coverage()` 为前缀划分；测试对着 `_FakeDispatch` mock 断言 |
| O5 | 「回归全绿」 | 实测 **1 failed / 1101 passed / 4 skipped**；且 gap §10.25（1007 passed/11 skipped）与 DEV_PLAN §21.10（1106）两处文档互相矛盾 |
| O6 | 域 11「wrapping 3100 步全 err=0」 | `p12e_wrapping_e2e.log` 实为 **814 步、无 end 标记**；`p12e_bam_e2e.log` 同样无 end；J7 重跑只覆盖 region/mesh/wiz |
| O7 | J2「CATPart snode 复放 err=0（137 checks）」 | `p12n_catia_mdl_e2e.log` 内含 `s096=424` |
| O8 | I7「CATIA V5 导入边界解除」 | 当日被 J2 推翻（`sn2__alive=True` 实为 box.pph 自带 Part 节点）；说明「aliveness 探针无容器差分」曾被当作证据 |
| O9 | `p12h_wizard_report.json` 作为 27 族结论来源 | 该文件在**每个 commit** 里都只有 1 个族（Flow）；27 族结论只存在于 `p12h_registry_report.json`（原始产物可复现该结论，但两个已提交文件互相矛盾） |
| O10 | 「165/165 零未归类」 | `tools/_p12h_reconcile.py` 硬编码 `buckets == {92,1,72}`，其余自动归为 registry_key —— 记账而非发现 |
| O11 | 测试「全离线」 | token grep 确实为 0，但 `pywinauto` 在 2 个文件里被 mock，Qt 可用性会让 skip 数在有序/隔离运行间漂移（4↔8） |

**过程性缺陷（新发现）**：`tests/test_host_pipeline.py` 中 `class TestBackendConvergence`
**重复定义 7 次**（行 302/366/430/494/558/620/682），**定义 65 个测试方法、实际只收集 29 个**，
36 个定义是死代码；而唯一存活的那份正是被 J4 改动作废、当前**失败**的那份。

---

## 6. 关键缺陷清单（按严重度，全部可复现）

| 级别 | 缺陷 | 证据 | 影响 |
|---|---|---|---|
| P0 | **native BAM 默认参数会删光自己的黄金模型**：`BamParams.remove_tiny=True` + `remove_tiny_tol=1e-3`（**绝对**长度，`native_bam.py:69-70,144-145,818`） | 我方实测：对 `tests/box/meshinggroup1_part.mdl`（0.01 m 立方体 / 60,492 面）调 `remove_tiny_faces`，tol=1e-3 → **found=60492 / removed=60492 / kept=0**；tol=1e-6 → kept=60492。GUI 的 AMW「Remove Tiny Faces」页默认同值（`nav_panels.py:12525` `sess.get("remove_tiny_tol", 0.001)`） | 原生 BAM 默认路径在这台机器的黄金件上产出空模型；本应生效的**相对**容差 `tiny_pct` 与 `project_solids/sheets` 已接线但从未被使用 |
| P0 | **voxmesh 写出的 `.oct` 子序与宿主/本仓 reader 不一致**：`voxmesh._OctNode.split` 以 x 外层、z 内层生成子表（`voxmesh.py:459-467`），序号 = **4x+2y+z**（z 最快）；而 `.oct`/快照的约定是 **x+2y+4z**（x 最快，`oct.py:81-88`、`sctsnapshot.py:1115-1117`）。`_walk_nodes` 直接把该顺序写成前序位图（`voxmesh.py:578-589` → `oct.write_oct`） | 代码级已确认两侧顺序；实测量化（独立审计）：L-shape、initial_depth=2/max_depth=3 下回读 **127/155 叶子落在错误包围盒**，且叶子集合本身不同（不是置换） | GUI「Voxel Fitting Mesh (Self Build)」写出的 `meshinggroup1.oct` 被宿主重建为**另一棵八叉树**；现有测试只断言叶子**数量**（`tests/test_voxmesh.py:73-76`）故 CI 全绿 |
| P0 | **回归红**：`test_host_pipeline.py:740` 断言 `pph_gui.py` 内含 `run_vbs_authoritative` 字面量，J4 改为 `_selfheal_execute()` 后失效 | 我方两次独立全量复跑均 1 failed | 仓库无法自证「全绿」；且暴露「源码字符串断言」的脆弱性 |
| P0 | **无任何写端宿主回读验收** | 所有二进制写端只在本仓 reader 上 round-trip | 「生产级写端」结论缺少最后一环 |
| P1 | **MDL/OCT section 头 36 字节 vs 宿主 40 字节**（`mdl.py:273`、`oct.py:285` 缺尾部 `I4(32)`；`gphstats.py:807` 才是原生布局） | 重序列化 box `meshinggroup1_part.mdl` 得 2,968,694 B vs 宿主 2,969,210 B | 自解析靠 4 字节重同步掩盖；宿主能否接受未验证 |
| P1 | **MDL 改写丢数据**：laptop 式 LS_MdlVolumeRegions 的种子点、ridge 式 per-region I4 数组被解析后从不写出 | `mdl.py:216-224/328-339` | 往返不是无损的 |
| P1 | **容器字节不可复现** | box.pph 5,650,178 B → clone 751,103 B，时间戳重置；宿主成员 method=8 近 0 压缩 | 「clone 与参考目录逐字节一致」仅指成员内容 |
| P1 | **`OctModel.unit` 在真实文件上恒为空** | `crdlfld.py:142-164` 误把 32 字节单位串块判为 section | 单位语义缺失，且无测试锁定 |
| P1 | **GUI 面板大量只写 session** | Part Material / Mesh Param / Non-Solid / Option Settings 20/23 页 | 「参数可编辑」≠「参数生效」 |
| P1 | **条件系统 68/165 类型字段是启发式猜测** | 64 个来自 `inject_sibling_sample_fields` 的同类键复制 + 4 个来自显示名 sanitize；`write_condition_to_xml` 会照写 | 可能向 `main.xml` 写入宿主不认的标签，且无校验 |
| P2 | **199/199 typed 覆盖是名称划分** | `scflowpre_api.py` `catalog_coverage()` | 覆盖率指标失去信息量 |
| P2 | **E2E 证据语料无回归锁定** | 无测试解析 `p12*_e2e.log` | 宿主能力「时变」无法被 CI 捕获 |
| P2 | **`sctsnapshot.py:259-265` 吞异常** | 任何 cabinet 失败都报「wimlib not found」 | 曾把 8 failed/6 errors 伪装成环境问题 |
| P2 | **`OctModel`/`MeshParam` 之外的 L0 脚手架** | Undo / Measurement / Prism Layer / Neighbor / Language / Output-List-File | 菜单反显为「已接线」 |
| P1 | **`quality.py` 长宽比指标实现错误**：只取 owner 面且与 docstring 定义不符 | 宿主黄金 box GPH 上 n=943/944、max 62,777（1 个 NaN）；polymesh 上 1e14–1e15（而单元体积其实是均值的 0.29–0.52 倍，非畸变） | 质量报告中的长宽比不可用；基准测试因此**刻意不对宿主断言该指标** |
| P1 | **native_bam 特征节点规则 `>=2` 而宿主为 `>=3`** | 用宿主黄金件验证：`>=3` 的节点数 = 188（laptop）/ 8（box），与宿主 node_state **精确相等**；`native_bam.py:719-721` 用 `>=2` 得 1,877 / 848 | 特征节点标记约 10 倍于宿主 |
| P1 | **`voxmesh` 体积误差 +6.12% 且不随细化收敛**、`fit_to_surface` 近似 no-op | 各深度误差恒为 +6.12%（`n_outside=0`，rough 路径填满根盒）；cut-poly 路径 snap 前后顶点数/坐标和/边界偏差完全相同 | 自研网格体积不守恒（宿主为精确 1e-6） |
| P1 | **基准测试是「指标选择性」的** | `test_mesh_quality_benchmark.py` 的「不劣于宿主」只比较**内部面**非正交度（25.24 vs 25.81），而此时边界非正交度 0.00（阶梯）vs 宿主 5.29（贴体）；**全程没有体积或几何偏差断言**；`n_cells > 100` 与宿主 944 无关 | 文档「黄金质量不劣于宿主」的结论不成立 |
| P2 | **native_bam 参数面大量失效** | `BamParams` 22 字段中 10 个从未被引用（project_solids/sheets、acc_type、sb_ang、sb_len、max_edge、absolute、dist_abs、edge_abs、tiny_pct） | 「参数透传」名义存在、实际无效 |
| P3 | SSH 集群派发为 stub | `cluster_dispatch.py` 三个方法 `NotImplementedError` | §9.6-4 部署层豁免 |

---

## 7. 谁做什么：本仓 vs scFLOWpre

| 能力 | 本仓自研 | 委派宿主 | scFLOWpre 独有（未复刻） |
|---|---|---|---|
| PPH 容器 / 快照 / Parasolid 传输流 | ✅ L3 读写 | — | — |
| MDL/OCT/GPH 二进制 | ✅ 读 L2 + 写 L2（未验收） | — | 内核语义 |
| 几何造型（block/boolean/transform） | ✅ **直调同款 Parasolid 内核** | — | — |
| CAD 转换（STEP/CATIA/Datakit） | ✗ | ✅ OpenCadFile | Datakit 转换器本体 |
| BAM / Octree / Mesh / Wrapping | ⚠️ 自研 MVP（不等价） | ✅ 权威 | facet/octree/poly 内核算法 |
| 条件与物理设置 | ⚠️ 类型目录 + 通用表单（90 精确键） | ✅ CreateCond* | 284 个对话框的物理语义与校验 |
| 求解 | ✗ | ✅ ExecuteSolver | 求解器本体 |
| 后处理（FLD/iFLD 场量读取） | ✅ 读端 L2–L3 | ✗ | scPOST |
| 结果数值等价验证 | ✅ `solver_delta` 门控 | — | — |
| GUI | ✅ 查看器 + 浅编辑 | ⚠️ VBS 草稿降级 | 完整前处理器交互 |

**本质**：本仓是 scFLOWpre 的**离线格式工具链 + 自动化编排/验证层**；
凡是「算出来的东西」，几乎都来自宿主或许可证；凡是「格式里的东西」，本仓做到了业界少见的深度。

---

## 8. 评级与建议

| 维度 | 评级 |
|---|---|
| 格式解码（读） | **A−（~90%，L2–L3）** |
| 格式编码（写） | **C+（~55–65%，L2，未验收）** |
| 宿主自动化 | **B（~82%，L2+，强依赖已安装且已许可的宿主）** |
| 求解链 | **B−（~60%，数值证据建立在零流场上，无 FLD/iFLD）** |
| GUI | **C+（表面 ~95%，语义 ~35–40%）** |
| 自研网格/几何 | **C−（功能面 ~25–30%，L2；voxmesh 体积 +6.12%、`.oct` 子序错误，polymesh 边界非正交 77° vs 宿主 5.3°，native_bam 未生效参数 10/22）** |
| 测试可信度 | **C（数量大，37% 原理上测不到宿主；无 live host 测试；有 36 个被遮蔽的死测试）** |
| 文档可信度 | **C−（结论由口径变更与硬编码对账产生；存在 11 处可验证的过度声称）** |

**优先级建议**

1. **修红**：把 `test_host_pipeline.py:740` 的源码字符串断言改为行为断言；删除 6 份重复的 `TestBackendConvergence`。
2. **补写端验收**：增加「本仓写出 → 宿主 OpenProject → 成员/拓扑回读」的闭环（这是把写端从 L2 抬到 L3 的唯一路径）。
3. **修 3 个确定性缺陷**：MDL/OCT 40 字节 section 头、MDL 种子点/区域数组写出、`oct.unit` 误判。
4. **把 E2E 日志纳入回归**：至少断言 `has_end` 与 err=0 计数，杜绝「截断日志当成功凭证」。
5. **修正文档口径**：把「100%」改为分域实测值 + 明确豁免清单；§9.7 第 12 项（FLD 回读）应撤回。
6. **提高数值等价证据质量**：用有真实流场的算例（如 50 Pa 变体）重做 I5 双跑；在无害算例上补一次真实 host 集成测试（哪怕是 gated）。

---

## 9. CATIA V5 边界专项复测（2026-09-13，用户提供新样本后）

**样本来源**：`CATIA-Designs-Portfolio-main/`（位于本仓工作树内），6 个真 CATIA V5 文件
（魔数 `V5_CFV2`，1 个 CATProduct + 5 个 CATPart，合计 20.46 MB，另有 44 张设计截图）。
provenance 与 I7 找到的 STAR-CCM+ 教程数据**完全不同**（GitHub 学生作品集）。

| 文件 | 大小 | sha256(16) |
|---|---:|---|
| Bottle_Model_Design.CATPart | 1,650,641 | bea3247918e22948 |
| Bushes_Model.CATPart | 230,187 | a94a98cf232ab849 |
| Handset_Model.CATPart | 115,238 | 1f910b3cebb92fdb |
| Ribbed_Bracket_Design.CATPart | 172,473 | 92c77908e6203b81 |
| USB_Catia_Model.CATPart | 247,395 | d87b9c2aded4b861 |
| PIPE_VICE_FINAL_ASSEMBLY.CATProduct | 41,143 | 1326d77fff3dc633 |

**测法**：沿用 J2 r3 cadmatrix 配方（裸宿主 → `OpenCadFile` → WaitForWorker → ping×2 →
`QuerySNodeByName("Part")` → stem 探针 → `GetSParts` → ping×3 → `GetSParts` 二轮 →
`GetAllPartsBoundingBox` → SaveProject），冷启动一次、5 条腿顺序跑，**含 XT 对照腿**
（证明当日 CAD 链活着）。证据：`p12r_*_e2e.{vbs,log}`、`_p12r_catia/*_out.pph`。

| 腿 | sn__alive | sn2__alive | GetSParts | bbox | 步骤 err=0 | 容器成员 |
|---|---|---|---|---|---|---|
| **ctrl_xt**（box.x_t 对照） | **True** | **True** | 0 | **[0, 0.01]** | 21/21 | 5（**含 main.sctsnapshot**） |
| catia_usb（CATPart） | False | False | -1（空） | ±DBL_MAX | 21/21 | 4（无 snapshot） |
| catia_bottle（CATPart） | False | False | -1 | ±DBL_MAX | 21/21 | 4（无 snapshot） |
| catia_bracket（CATPart） | False | False | -1 | ±DBL_MAX | 21/21 | 4（无 snapshot） |
| catia_product（CATProduct） | False | False | -1 | ±DBL_MAX | 21/21 | 4（无 snapshot） |

**结论（边界维持，且证据等级提升）**：
1. **同场对照腿证明不是宿主/当日链故障**——XT 同时刻 `sn_/sn2_/sn3_` 全 True 且 bbox 真实；
2. 4 条 CATIA 腿**全部静默零几何**（err=0、无模态、`GetSParts` 空、bbox 空指纹、
   **容器里根本没有 `main.sctsnapshot` 成员**——CAD 体从未进入文档）；
3. 结合 J2 的 STAR-CCM+ 样本结论（同签名），说明 **CATIA V5 读链失效不是样本特异**，
   而是本机 **CADthru CATIA V5 读特性未授权 / 转换器 headless no-op** 之一；
4. 自愈基建表现良好：台账 +5 行全 `ok`（45–95 s，`attempts=1`，0 挂起，0 人工干预）。
5. **下一步（唯一判别手段）**：GUI 路线（File → Import 走 CADthru 交互式导入）与 COM 路线对照；
   若 GUI 能导入则判为 COM/headless 特异，若不能则为转换核问题。
   **注意**：原「许可边界」假说已被 §10 的许可证实证推翻——CATIA V5 读特性
   （`OP_CATIAV5R`）在本机**已授权**（32 席，0 占用）。

> 附带发现：G3 早期「全机 0 真 CATIA 样本」是**扫描时点**造成的假象——
> 新样本就落在 I7 扫描根 `D:\training` 之内（且在本仓工作树内），若当时存在必被扫到。

---

## 10. CADthru 路线与许可证（2026-09-13 实测）

**问题**：CADthru/InterOp 的 CAD 导入是否需要本机 Cradle 许可？——**需要，且是按格式的特性**。

### 10.1 二进制层的许可证闸门（字符串实证）

`CADthru_Bx64net.exe`（17.9 MB）与 `DKCTCore_Bx64.exe`（Datakit 转换核）中**硬编码**了 13 条
按格式的许可拒绝消息：

```
No valid license found to import 3DXML / ACIS / CATIA V4 / CATIA V5 / IGES / Inventor /
JT / Pro/Engineer / Rhinoceros / SolidEdge / SolidWorks / Unigraphics / VDAFS File:
```

对应的 FlexNet 特性码也在二进制里：`OP_CATIAV4` / `OP_CATIAV5R` / `OP_CATIAV5RW`
（显示名 `CAD Translator - CATIA V4 / CATIA V5 R / CATIA V5 RW`）。
其他相关键：`MSC_LICENSE_FILE`（**CAD 核心读的是这个变量，不是 CRADLE_LICENSE_FILE**）、
`INTEROPLICENSETYPE` / `INT_INTEROPLICENSETYPE`（转换器库选择）、
`INT_CHECKINTEROPLICENSEATFILEOPEN`、`INT_INTEROPNETWORKLICENSEPRIORTODONGLELICENSE`。

手册旁证：`V20252_CADthru_CAD_Interface.html` 的**导出**表明确标注
CATIA V5 / ACIS / IGES 三项 “Requires Extension Option license”，SolidEdge 行标注
“datakit and extension option only”。

### 10.2 本机实际授权（license.dat + lmstat 实证）

许可源：MSC vendor daemon @ **27500@localhost**（UP），license.dat
= `C:\MSC_Licensing_Beryllium\license.dat`（2214 条 increment）。
（`CRADLE_LICENSE_FILE=27891@localhost` 指向的服务器**已宕**，但 CAD 核心不读它。）

| 特性 | 是否授权 | 席位数 |
|---|---|---|
| `CADTHRUSTD`（CADthru 基础） | ✅ | 32 |
| **`OP_CATIAV5R`（CATIA V5 读）** | ✅ | 32 |
| `OP_CATIAV5RW`（读/写） | ✅ | 32 |
| `OP_CATIAV4` / `OP_IGES` / `OP_SAT` / `OP_PROE` / `OP_SLDWRKS` / `OP_UNIGRAPHICS` / `OP_INVENTOR` / `OP_OPTIMZ` | ✅ | 均 32 |
| 3DXML / SolidEdge / JT / Rhinoceros / VDAFS | ❌ **无对应 increment** | — |

scFLOW 前处理器族亦在位：`SCFLOWPP` / `SCFLOW_PPCORE` / `SCFLOWSOL` / `SCPOST` /
`SCTWPP` / `SCSTREAM_*` 等（32 席，有效期至 2098-10-28）。

### 10.3 结论：CATIA 失败**不是**许可拒绝

| 事实 | 证据 |
|---|---|
| XT（Parasolid，基础路径）导入**正常** | 对照腿 2/2 绿：`sn_/sn2_/sn3_=True`、bbox [0, 0.01]、容器含 `main.sctsnapshot` |
| CATIA 导入**6/6 静默零几何**（两次独立运行，3 种 CATPart + 1 种 CATProduct） | `GetSParts` 空、bbox ±DBL_MAX、err=0、无模态、容器**无 snapshot 成员** |
| **CATIA V5 读特性已授权且 0 占用** | `license.dat` FEATURE 行 + `lmstat -f OP_CATIAV5R` = 32 issued / 0 in use |

因此 `docs/NYI_INVENTORY.md` 与 gap §10.21 登记的根因假说
「本机 CADthru CATIA V5 读特性未授权」**被证据推翻**。剩余候选：
① 转换核在非交互（COM/headless）路径下静默 no-op；
② 转换器库选择/配置（`INT_INTEROPLICENSETYPE`）与文件版本不匹配。
判别手段仍是 GUI 路线（File → Import 交互式导入）对照。

> 补充观测：导入全程以 `lmstat -f` 轮询 `OP_CATIAV5R/RW`、`CADTHRUSTD`、`SCFLOWPP`
> **未捕获到任何签出**（含 XT 成功腿）。即采样周期可能粗于签出窗口，或
> scFLOWpre 的会话许可经 Kicker 注入而非 FlexNet 常驻持有——此点未定，如实记录。
> **能确证的是「授权在位」，不能确证的是「签出链路是否被走到」。**

## 11. STEP 导入的许可证结论（2026-09-13 实测）

**问题**：STEP 走 Datakit 吗？需要 Cradle 许可吗？
**答**：**本安装上 STEP 不走 Datakit（是 Cradle 自带的 STEP 读取器），也不需要任何按格式的许可。**

### 11.1 静态证据（三路互证）

| 证据 | 结果 |
|---|---|
| `DKCTCore_Bx64.exe`（Datakit 转换核，271 KB） | **"step" 出现 0 次** → Datakit 核根本不处理 STEP |
| `CADthru_Bx64net.exe` | 内含**完整原生 STEP 读取器**：`STEPAssistant` / `CTSTEPAssistant Version` / `STEPfacecollection` / `step_advanced_brep_shape_representation::load` / `step_b_spline_surface_with_knots::load` / `*.stp;*.step` |
| 13 条 `No valid license found to import X File` | 3DXML / ACIS / CATIA V4 / CATIA V5 / IGES / Inventor / JT / Pro-E / Rhino / SolidEdge / SolidWorks / UG / VDAFS —— **无 STEP** |
| 9 个 `CAD Translator - X` 许可特性 | ACIS SAT / CATIA V4 / CATIA V5 R / CATIA V5 RW / IGES / Inventor / PRO-E / SolidWorks / Unigraphics —— **无 STEP** |
| 11 个 `OP_*` 特性码（与 license.dat 一一对应） | 无 `OP_STEP`；license.dat 中亦无任何 STEP 相关 increment |
| 手册 CAD Interface 表 | CATIA V5 / SolidWorks 行标注 `Datakit2025.2:` / `MSCCT:` 后端；**STEP 行无后端标注** → Cradle 原生 |

### 11.2 实机实证（同一冷启动宿主，XT 对照 + 3 个真 STEP 文件）

| 腿 | `sn_`（OpenCadFile 返回） | `GetSParts` | `GetAllPartsBoundingBox` | 容器成员 | err |
|---|---|---|---|---|---|
| ctrl_xt（box.x_t） | True | 0 | **[0, 0.01]** | 5（含 snapshot） | 21/21 |
| step_base（42 KB） | **True** | **1** | **[-82.2, 36]** | **5（含 snapshot）** | 21/21 |
| step_key（8.9 KB） | **True** | 0 | **[-4, 3]** | 5（含 snapshot） | 21/21 |
| step_top（1.39 MB） | **True** | 0 | **[-83.05, 40]** | 5（含 snapshot） | 21/21 |

对照 CATIA 的同一配方：`sn_=False`、`parts_ub=-1`、bbox `±DBL_MAX`、成员 4（**无 snapshot**）。
STEP 四腿**全部落几何**且无模态、无许可拒绝 —— 与"不受按格式许可门控"一致。

### 11.3 结论与对计划的影响

1. **STEP 导入不需要 Extension Option 许可**；需要的是 scFLOWpre 的**基础会话许可**
   （`SCFLOWPP` / `SCFLOW_PPCORE` 族，本机 32 席在位）——没有它连前处理器都起不来。
2. 因此 **P1-3 的"STEP → 宿主转一次成 x_t → 离线复用"路线无许可风险**，是纯工程任务。
3. **新发现（供 P1-5 用）**：STEP 导入后 `QuerySNodeByName("Part")` 与按文件名 stem 的查询**均为 False**
   （三腿一致），说明 STEP 的顶节点命名与 x_t 不同 —— 零件/装配发现必须走 **SNode 树枚举**，
   不能沿用 x_t 的按名查询配方。这条会直接影响 P1-4/P1-5 的驱动器写法。

---

## 12. STEP（及 x_t 离线）对 Cradle 安装的依赖边界（2026-09-13 实查）

**问题**：STEP 导入需要安装 Cradle 吗？
**答**：**需要。** 本仓没有任何独立 STEP 能力，STEP 只能经 Cradle 自带的读取器 + 运行中的宿主。

### 12.1 三路证据

| 层 | 事实 | 证据 |
|---|---|---|
| 代码 | 仓库内 **STEP 解析代码 = 0 行** | 对 `AP203/AP214/ISO-10303/FILE_SCHEMA/CARTESIAN_POINT/step_advanced` 等模式全仓扫描：0 命中；STEP 只出现在后缀白名单（`edit_ops._CAD_SUFFIXES`、`pipeline_plan.CAD_EXTENSIONS`） |
| 二进制 | 真正读 STEP 的是 **Cradle 自带** `CADthru_Bx64net.exe`（`STEPAssistant` / `CTSTEPAssistant Version` / `step_advanced_brep_shape_representation::load`） | 位于 `C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64`；Datakit 核 `DKCTCore_Bx64.exe` 中 "step" 0 命中 |
| 运行 | `Doc.OpenCadFile` 是宿主 COM API；宿主须经 Kicker 冷启动 + 基础会话许可 | `automation/scflowpre_api.py`（ROT 附着）、`host_boot.cold_boot`；实测宿主不在跑时该链路不可用 |

### 12.2 依赖分级（本仓最容易误读的一点）

| 能力 | 需 Cradle **安装** | 需**宿主进程** | 需**许可** |
|---|---|---|---|
| **STEP 导入**（唯一路径 = COM `OpenCadFile`） | ✅ | ✅ | 基础会话（**非按格式**，见 §11） |
| x_t 导入（宿主路径） | ✅ | ✅ | 基础会话 |
| x_t 离线剖分（`cad_import` / `ps_tessellate` / `geometry_ops`） | ✅ `pskernel.dll` + `Schemas/` | ❌ | ❌ |
| PPH 解析/写端、快照、Blowfish、自研 mesher/BAM、GUI 主体 | ❌（仅需 Windows `cabinet.dll`） | ❌ | ❌ |
| 材料库 / 条件树 / XT schema / pskernel ABI 表 | ✅（读安装目录数据文件） | ❌ | ❌ |

**结论**：本仓所谓"离线"= **不需要宿主进程与许可**，**不等于"不需要 Cradle"**。
`find_cradle_programs()`（`ps_facet2_nodes`）依次扫 `CRADLE_PROGRAMS` → `P_SCHEMA` →
`C:\Program Files\Cradle\CradleCFD*\Programs_x64`，要求同时存在 `pskernel.dll` 与 `Schemas/`；
找不到时 `cad_import.available()` 为 False，GUI 直接拒绝 CAD 导入（现有测试亦以 skipTest 处理）。
全仓 **16 个模块**引用 Cradle 安装路径：`ps_facet2_nodes`(20) / `ps_tessellate`(14) / `pph_gui`(14) /
`pskernel_v37`(12) / `pskernel_abi`(8) / `condition_tree`(7) / `parasolid`(6) / `geometry_ops`(6) /
`material_lib`(5) / `cad_import`(4) 等。

> **文档偏差**：README 写"依赖：仅 `numpy`（Python 3.10+）"。就**纯 Python 依赖**而言正确，
> 但会让人误以为 CAD/几何/材料能力可在无 Cradle 机器上运行——实际不能。

### 12.3 若要摆脱 Cradle（不建议，记录以明代价）

| 路线 | 代价 | 与"快速补齐"的关系 |
|---|---|---|
| 引入 OCCT/OpenCascade（pythonocc）自建 STEP 读取 | 周–月级；几何结果与 Datakit/Cradle 不一致 | 与 P1 目标冲突 |
| 外部工具 STEP → x_t，再走本仓 x_t 路径 | 离线剖分仍需 pskernel（仍要安装）；走宿主路径则仍要宿主 | 不解决依赖 |
| 放弃 CAD 导入，只做 PPH 格式工具链 + 自研 mesher + 宿主自动化 | 域 4 直接出范围 | 与用户"CAD 优先 x_t/STEP"指示冲突 |

**对计划的影响**：P1 全部条目以"本机已安装 Cradle 且可启动宿主"为前置；
CAD 域交付物应包含**环境前置检查**（`--status` 已有雏形）并把 CAD 测试在无安装环境下显式 skip。

---

## 13. 「已安装但无许可」时的能力边界（2026-09-13 实测）

**方法**：把许可指向死地址后跑对照实验——`MSC_LICENSE_FILE=27500@127.0.0.1:1`、
`CRADLE_LICENSE_FILE=27891@127.0.0.1:1`（控制组：`lmutil lmstat -c 27500@127.0.0.1:1`
返回 `-96,7 HOST_NOT_FOUND`，证明地址确实不可达），然后分别测离线路径与宿主路径。

### 13.1 结论表

| 路线 | 只装 Cradle、无许可 | 实测证据 |
|---|---|---|
| **x_t 离线读**（pskernel 剖分：`ps_facet2_nodes.tessellate_xt` / `cad_import` / `geometry_ops`） | ✅ **成功** | 同次实测：`tessellate_xt(box.x_t)` → **1 体 / 8 顶点 / 12 三角，0.1 s** |
| **x_t 离线写**（`parasolid.encode_binary_xt` / `transmit_xt` / `mdl.write_mdl`） | ✅ **成功** | 同次实测：`transmit_xt` 输出 **4,432 B**；纯 Python 编码器只需安装目录的 `Schemas/` |
| **x_t 经宿主导入**（`Doc.OpenCadFile(".x_t")`） | ❌ **不可用** | 同次实测：`cold_boot()` **560 s 后 RuntimeError: host booted but VBS channel not reachable** |
| **x_t 经宿主导出**（`SNode.SaveXTFile` / 原生 `ConvertFacetToXT`） | ❌ 不可用 | 同上（均要求宿主可用） |
| **STEP 导入** | ❌ **不可用** | 本仓无离线 STEP 通道（解析代码 0 行，见 §12），唯一路径是宿主 `OpenCadFile` |
| PPH 解析/写端、快照、GPH/MDL/OCT、自研 mesher/BAM/质量、GUI 主体 | ✅ | 纯 Python（仅 Windows `cabinet.dll`） |

### 13.2 机制解释

Cradle 安装提供两类东西，许可只卡第二类：

1. **库与 schema**（`pskernel.dll`、`Schemas/`、`SCTpre.prp`、`scflow_main.xml`）→ 支撑**离线**能力，**不需要许可**；
2. **宿主应用 + Kicker 许可注入** → 支撑**全部 COM/CAD 转换**能力，**需要许可**。

仓库自身证据（`automation/host_pipeline.py:834-844`）："绝不能直接 start 裸 exe——
scFLOWpre 必须经 Kicker 启动（许可/产品键注入），裸 exe 会在 `SetupSCTpreLib` 抛
`0xE0000000` 并弹模态错误框"。本次实测补充了另一种表现：**进程能起、窗口在，
但 VBS/COM 通道始终不可达**（560 s 超时）——即宿主进入"未完成初始化"状态。

### 13.3 需要修的坑（供计划采纳）

`cad_import.available()` **只检查 `pskernel.dll` 是否存在，不检查许可/宿主可用性**
（`ps_facet2_nodes.available()` → `find_cradle_programs() is not None`）。
后果：在"已安装但无许可"的机器上，GUI 会显示 CAD 能力可用，用户点导入后才在宿主环节失败，
且失败信息不指向许可。建议拆成两个判据：
`offline_cad_available()`（pskernel 在位）与 `host_cad_available()`（宿主可达 + 许可在位），
GUI 据此分别灰显/提示。

---

## 14. pskernel.dll 是否具备 STEP 读写能力（2026-09-13 实查）

**结论：没有。pskernel 只认 Parasolid 自己的 XT 传输流。**

### 14.1 导出表证据（2025.2 `pskernel.dll`，72 MB，1454 个导出）

| 检索 | 结果 |
|---|---|
| 名字匹配 `step / iso10303 / ap2xx / iges / translat / interop / datakit` | **0 个**（唯一命中 `PK_TRANSF_create_translation` 是**几何平移变换**，与"格式转换器"无关） |
| 名字含 `IMPORT` / `EXPORT` | **0 个** |
| 名字含 `FILE` | 1 个：`PK_BODY_make_swept_profiles`（扫掠建模，非文件 I/O） |
| 实际 I/O 面（全部为 XT） | `PK_PART_receive` / `_b` / `_u` / `_meshes`、`PK_PART_transmit` / `_b` / `_u`、`PK_PARTITION_receive*` / `transmit*`（10 项）、`PK_SESSION_transmit` / `_u`、`PK_DEBUG_receive` / `transmit` |

### 14.2 文件内容证据

在 72 MB 的 DLL 里检索 STEP 格式标志：

| 标志 | 出现次数 |
|---|---|
| `ISO-10303` | **0** |
| `AP203` / `AP214` / `AP242` | **0 / 0 / 0** |
| `FILE_SCHEMA` | **0** |
| `CARTESIAN_POINT` | **0** |
| `ADVANCED_BREP` | **0** |

含 "step" 的 55 条字符串**全部是几何步进/推进**语义（`Failed to create step mesh`、
`Parameter step $f invalid, abort march`、`Backing off $d step`、`Can't halve on step 0`…），
与 STEP 格式无关。

### 14.3 STEP 到底在哪里

| 组件 | 角色 | 证据 |
|---|---|---|
| `CADthru_Bx64net.exe`（17.9 MB） | **Cradle 自带 STEP 读取器** → 产出 Parasolid body → 以 XT `'A'`（CADthru frustrum）流写入 PPH 的 `CADthru/PKBody3` | `STEPAssistant` / `CTSTEPAssistant Version` / `STEPfacecollection` / `step_advanced_brep_shape_representation::load` |
| `scConverter_{D,S}x64net.exe`（25 MB） | **独立转换器应用**，COM ProgID `scConverter_Sx64net.Application.2025`（HKLM 已注册，CLSID `{DFAC6C29-F66F-4F87-9E5A-2BE919042F00}`） | 注册表实查；仓库 `scflowpre_probe.py` 已探测该 ProgID |
| `DKCTCore_Bx64.exe`（Datakit 核） | 只处理 CATIA/IGES/ACIS/Pro-E/SolidWorks/UG/Inventor —— **"step" 0 命中** | 见 §11 |

即链路为：`STEP ──(CADthru/STEPAssistant，非 pskernel)──> Parasolid body ──> XT 'A' 流 ──> pskernel`。

### 14.4 对 P1 计划的影响（可执行）

1. **"STEP 离线"不可能靠 pskernel 实现**——离线栈（`ps_facet2_nodes` / `parasolid.py` / `geometry_ops`）
   全部是 XT-only，只能接收已经转好的 x_t。这与 §12/§13 的结论一致。
2. **P1-3 的转换环节有个更便宜的候选通道**：`scConverter` 是**独立于 scFLOWpre 的 COM 面**，
   无需 Kicker 拉起整个前处理器宿主。若它能直接完成 `STEP → x_t`，则
   "STEP 导入"可以脱离 scFLOWpre 会话（仍需安装与相应许可，但少一层宿主依赖）。
3. **仓库现状**：`scConverter_Sx64net.Application.2025` 只在**探测清单**里出现
   （`tests/test_scflowpre_probe.py:78`、`tests/test_host_pipeline.py:285`），
   **从未被真正驱动**。这是一个尚未开采的低成本入口。
4. **建议新增 P1-0（0.5 人日，先于 P1-3）**：验证 `scConverter` 的可驱动性与 STEP→x_t 能力；
   若通，P1-3 改用该通道，STEP 路径的宿主耦合从"必须冷启动 scFLOWpre"降为"仅需转换器"。

---

## 15. P1-0 执行结果：scConverter vs CADthru（2026-09-13，实测）

**任务**：验证 `scConverter` 能否被驱动、能否做 STEP→x_t；通了就改用它，不通就回落宿主路线。

### 15.1 结论

| 候选 | 结论 | 证据 |
|---|---|---|
| `scConverter_Sx64net.Application.2025` | ❌ **不是 CAD 转换器**（**不通**） | 仅 3 个对话框入口 `GetDialogFLD2FLD` / `GetDialogFLD2IFLD` / `GetDialogP2FLD`；二进制中 `*cad*` 标识符 **0 个**、`No valid license found to import` **0 个**、`CADthru/PKBody3` **0 个**；格式足迹是 FLD(170)/iFLD(17)/FPH(37)/CGNS(41)/NASTRAN(10)/CSV(11)。厂商示例 `windtool\STtools_eng.vbs` 亦只用其 FLD 对话框。**它是场数据（后处理）转换器。** |
| `CADthru_Bx64net.Application.2025` | ✅ **可驱动，且能 STEP→x_t**（**通了**） | 见下 |

### 15.2 CADthru 独立 COM 通道（新发现，P1-0 的主要产出）

**注册**：HKLM `CADthru_Bx64net.Application.2025` → CLSID `{FDAB4A86-C93B-44F2-B5D5-091434422B5B}`
→ LocalServer32 `...\CradleCFD2025.2\Programs_x64\CADthru_Bx64net.exe`（**无 typelib**）。

**API 形态（踩坑已钉死）**：

```python
import win32com.client
app = win32com.client.Dispatch('CADthru_Bx64net.Application.2025')
app.SetConfiguration('STARTUPSETTING', 'INT_CADIMPORTLIBRARYPRIORITY', 1, 0)  # 0=InterOp 1=datakit 2=CoreTechnologie
doc = app.CreateDocument        # ★ 属性，不能加括号
asm = doc.OpenXtFile(path)      # ★ 手册：开 XT / STEP / STL / MDL
ret = doc.SaveXTFile(asm, out)  # ★ 两参 (obj, path)，不是 SaveXTFile(path)
app.Quit()
```

* 服务器是纯 late-binding IDispatch：`GetTypeInfo` 失败、`dir()` 空；
  成员名靠 `_oleobj_.GetIDsOfNames()` 探测（Document 共 **133** 个成员，dispid 1..116）。
* `Document.Translate` **不是**格式转换入口（两参调用报类型不匹配）；
  真正的转换由 `OpenXtFile` 内部按格式完成。
* 手册依据：`Manuals\SCT\HTML\VB_Interface_eng\Sct_vb_Pre_PrimeDocument_Class.html`
  —— *"OpenXtFile: Open XT, STEP, STL, or MDL file and register it in the project"*；
  厂商示例 `Cth_CreateMdl90.vbs` 注释亦写明可开 `XT, CT3, STEP, STL, MDL, PRE, FLD`。

**几何一致性验证（宿主回读，同一冷启动，29/29 err=0）**：

| 用例 | 来源 | `sn_` | `GetSParts` | bbox |
|---|---|---|---|---|
| orig_step_base | `base v7.step` 直接导入 | True | 1 | **[-82.2, 36]** |
| conv_step_base | 该 STEP 经 CADthru 转出的 `.x_t` | True | 1 | **[-82.2, 36]** ✅ 一致 |
| orig_step_key | `key v2.step` 直接导入 | True | 0 | **[-4, 3]** |
| conv_step_key | 该 STEP 经 CADthru 转出的 `.x_t` | True | 0 | **[-4, 3]** ✅ 一致 |

附带：转换后的 x_t 令 `sn3_`（按文件名 stem 查询）从 False 变 True —— 转换顺带规范了顶层命名。

### 15.3 许可与宿主依赖（关键升级）

| 问题 | 实测结论 |
|---|---|
| CADthru 转换需要 scFLOWpre 宿主吗？ | **不需要**。独立 LocalServer32，全程无 Kicker、无 scFLOWpre 会话。 |
| 需要许可吗？ | **不需要**。把 `MSC_LICENSE_FILE=27500@127.0.0.1:1`、`CRADLE_LICENSE_FILE=27891@127.0.0.1:1`（死地址）后，两个 STEP 仍转换成功（38,495 B / 6,911 B，err=0）。 |
| 速度 | 单个文件 **9.5–18 s**（对比宿主路线需冷启动 ≈60–90 s + 模态风险）。 |

**由此得到一条全免许可的 CAD 摄入链**：
`STEP ──(CADthru COM，需安装不需许可)──> x_t ──(pskernel/parasolid.py，需安装不需许可)──> MDL/GPH/PPH`

### 15.4 交付物与新发现的缺陷

* 新增工具 **`tools/cadthru_convert.py`**（含 CLI 与 `convert()` API，自测通过：
  `key v2.step → 6,902 B`，pskernel 可载入）。自测抓到一个真实 bug 并已修：
  **必须传绝对路径**——CADthru 是独立进程，相对路径会被它解析到别处（ret=0 且文件缺失）。
* **新缺陷（P2 候选）**：本仓 pskernel 剖分路径**不能直接消费 CADthru 产出的 `PART1` 装配流**——
  `receive_xt` 成功返回 tag（51），但 `body_faces`/`facet_body`/`decode_brep` 一律
  `OSError: access violation reading 0x5C`。根因：收到的是**装配 tag 而非 body tag**，
  需要装配遍历（`PK_ASSEMBLY_* /` 子部件枚举）才能取到实体。
  影响：离线 x_t 管线目前只能吃"单 body 流"；CADthru 输出需经宿主导入（已验证可行）或补装配遍历。
  同一原因也解释了 `receive_xt(box.x_t)` 返回 5 个 tag 而 `tessellate_xt` 只得 1 个部件的现象。

---

## 16. P1-3 / P2 执行结果（2026-09-13）

> **最终全量回归：`1115 passed / 4 skipped / 0 failed`（622 s）** —— 全绿。
> 起点为 `1101 passed / 1 failed`（§5-O5 的红基线）：修红见 §16.7；
> 净新增 14 个测试（P2-1/P2-2/P2-5 回归 + 写端宿主字节保真）。

### 16.1 P2-1 ✅ voxmesh 八叉树子序

`voxmesh._OctNode.split` 改为宿主人 `.oct` 约定 **slot = x + 2y + 4z（x 最快）**。
验收：非对称树（raffinements 于 slot 1/4/7 各一 + 两层嵌套）写 `.oct` 再读回，
**叶子集合逐个恒等**（修复前 L-shape 127/155 叶子错盒）。
测试：`tests/test_oct_child_order.py`（4 项，含子序直接断言 `x+2y+4z`）。

### 16.2 P2-2 ✅ native_bam 对齐宿主

| 项 | 修正前 | 修正后 | 宿主参考 |
|---|---|---|---|
| 默认微小面容差 | 1e-3（**绝对**）→ 黄金 box 60,492 面**全删**（kept=0） | **1e-5**（= 录制向导 `FindTinyFace 1e-05`） | 不删（kept=60,492）✅ |
| ridge 特征点规则 | `>=2` → 848（box）/1,877（laptop） | `>=3` → **8**（box） | **8**（box）、188（laptop）✅ |
| ridge 边数 | 852 | 852 | 852 ✅ |

GUI 侧 `nav_panels` 的容差默认值同步改为 1e-5。
测试：`tests/test_native_bam_golden.py`（3 项，含"旧默认会删光"的反向把关）。

### 16.3 P2-3 ✅（主体）CRDL-FLD 段框修正 + `oct.unit`

三个写端此前**都缺容器头第 4 个 I4**（规范 `PPH_FORMAT_SPEC` §2 与宿主字节均为
`[I4=8][MAGIC][I4=8][I4][I4][I4]`），且 `mdl`/`oct` 的节头缺尾随 `[I4=32]` 与
20 字节节尾哨兵。逐一修正后：

| 写端 | 结果 |
|---|---|
| **MDL** | 与宿主 `meshinggroup1_part.mdl` **逐字节相同**（2,969,210 B，0 差异）——除下述 LS_Nodes 编码差异 |
| **OCT** | 与宿主仅 **2 字节**不同（偏移 283 = Date；1131） |
| GPH | 容器头修正；节结构仍不完整（见 §16.6） |

其余修正：`Application` 补 `desc`、`Encoding` 补 `desc` 且载荷改 `UTF-8`、
`UnitOfCoordinates` 补 `f64(1.0)` 比例 + 长名（`Metre`）+ 短名三段、
`LS_EdgeStateOfFaces` / `LS_OctOctantRefinement` 各补一个宿主实有的描述符、
区域类节不再重复 20 字节哨兵。

**`oct.unit` 修复**：此前恒为空——`scan_sections` 把 `UnitOfCoordinates` 体内
`unit32` 数据块的「[I4=32]+32B ASCII」误判为节头，使该节被截断到首个记录。
改为用「下一个具名节起点」重算 end 后走正规 `iter_data_blocks` → **`unit = 'm'`**。

**残留（已定位）**：MDL 的 `LS_Nodes` 有 208,593 字节不同，但**解析后的
X/Y/Z 坐标、face conn、frid 全部逐值相同**——属**编码/布局层面**差异（非数值），
下一步按同一套字节对照法钉死。

### 16.4 P2-4 ✅ quality.py 长宽比

原实现是「**owner 面顶点包围盒**长短边之比」，与模块文档定义（中心到各面重心距离
max/min）不符，且对只拥有 0–2 个面的单元退化。改为文档口径（关联面 = owner ∪ neigh）：

| 对象 | 修正前 | 修正后 |
|---|---|---|
| 宿主黄金 GPH | n=943/944、含 1 个 NaN、max **62,777** | **944/944、0 NaN、1.004–1.228**（mean 1.060） |
| polymesh 输出 | 1e14–1e15 | 与体积比一致（0.29–0.52×均值不再是畸变） |

### 16.5 P2-5 ✅ pskernel 分区/装配展开

`PK_PART_receive` 返回的是**分区(5007)/装配(5008)**标签而非 body(5006)，
直接喂 body 接口即 `access violation`。新增 `part_bodies()`（`PK_PARTITION_ask_bodies`）、
`assembly_parts()`（`PK_ASSEMBLY_ask_parts`）与递归 `bodies_of()`：

| 输入 | 修正前 | 修正后 |
|---|---|---|
| CADthru 转出的 STEP（tag class **5008**） | `tessellate` **0 部件**、`decode_brep` 崩 | **2 body / 6,952 三角**；`decode_brep` 2 体/34 面/76 边/44 点 |
| 本仓 `box.x_t`（5 × class 5006） | 1 部件 | 1 部件（不回归）✅ |

测试：`tests/test_ps_receive_expand.py`（3 项，夹具 `tests/box/_cadthru_step_asm.x_t`）。

### 16.6 P1-3 ✅ STEP→x_t 转换缓存与工程成员写入

`tools/cadthru_convert.py` 扩展：

* `convert_cached(src, cache_dir)`：**内容寻址缓存**（`<stem>-<sha16>.x_t`）。
  实测：冷跑 **15.6 s**（真转换）→ 命中 **0.27 s**（**不再启动 CADthru**），
  直接兑现 P1-3 的「同一 STEP 二次处理不再需要转换器」。
* `inject_into_pph(pph, out, member, x_t)`：经 `pphwriter.clone_pph` 把转换产物
  注入 PPH 副本（未改动成员字节原样保留）。实测 10 成员、成员 6,922 B 校验通过。
* CLI：`--cache/--pph/--out-pph/--member`；修掉模块 docstring 的 `\S` 转义告警，
  并补 sys.path 引导（脚本方式运行时可导入 `pphwrier` 等仓内模块）。

### 16.7 P0-1 ✅（附带修红）重复测试类 + 陈旧断言

* `tests/test_host_pipeline.py` 中 `class TestBackendConvergence` **重复 7 次**
  （审计 §5 发现）：**删除前 6 份死代码（380 行）**，保留唯一被 unittest 加载的那份；
  文件 843 → 463 行。
* 该存活用例仍断言 `host_pipeline.run_vbs_authoritative(...)` 字面量，J4 改走
  `FlowExecutor` 后失败。改为断言**契约**：① 不得出现 `backend="com"`；
  ② `FlowExecutor` 已接线；③ `run_vbs_if_ready` 已接线；④ 至少一条被真实调用。
* 结果：`tests/test_host_pipeline.py` **29 passed**，全量回归转绿。

### 16.8 P2 验收（宿主回读自研产物）——**未达成**，已定位

**测法**（即 P0-3 的精简版）：把宿主工程 `_p12a_e2e/box.pph` 的三个网格成员
用**本仓写端**重写后回注 → 宿主 `OpenProject` → 31 项探针（`QuerySNodeByName("Part")`、
`GetMDL`、`DoesMeshExist`、`GetOctree`、`GetAllPartsBoundingBox`、`GetSParts`）。

| 用例 | `sn_` | `mdl_` | `oct_` | `mesh_exists` | bbox |
|---|---|---|---|---|---|
| **对照**：宿主原工程 | True | True | True | True | [0, 0.01] ✅ |
| **纯容器克隆**（不改任何成员） | True | True | True | True | [0, 0.01] ✅ |
| **本仓写端重写成员** | **False** | **False** | **False** | **False** | 空 ✗ |

**结论（诚实的负面结果 + 精确定位）**：

1. **容器/ZIP 写回路径没问题**——纯克隆通过，说明 `clone_pph` 不是瓶颈；
2. 拒绝来自**成员内容**。逐字节比对（PPH 内成员 vs 宿主原成员）：

| 成员 | 大小 | 不同字节 | 定位 |
|---|---|---|---|
| `meshinggroup1.oct` | 均 472,289 | **2** | 偏移 283（Date）、1131 |
| `meshinggroup1_part.mdl` | 均 2,969,210 | 208,684 | `LS_Nodes` 占 208,593，其余为 Application/Date/Encoding/Faces/Csid/Frid/ES/区域各 1–42 字节 |
| `meshinggroup1.gph` | 1,034,894 vs 928,780 | 528,083 | **缺 13 个节**：ApplicationVersion/Bias/Comments/Cycle/Element_InformationFlag/Encoding/GridType/LS_Assemblies/LS_CvolIdOfElements/LS_Parts/LS_SurfaceRegions/LS_VolumeRegions/ReleaseDate，且 `Application`(-16)/`LS_Links`(-32)/`LS_Nodes`(-32) 缺描述符 |

3. 关键旁证：MDL 的 `LS_Nodes` 差异**不是数值差异**——`parse_mdl` 读回的两份模型
   `xyz` / `conn` / `frid` **完全逐值相同**，属编码布局问题。
4. **因此下一步的靶心是 GPH 写端补全**（`gphstats.write_gph_volume` 补齐上表 13 节
   与描述符），方法与 MDL/OCT 相同：宿主字节对照 → 逐节对齐 → 重跑本验收。
   GPH 补完后若仍被拒，再查 MDL 的 `LS_Nodes` 编码差异。

**已入册的产物**：`_p2_accept/{ours_part.mdl,ours.oct,ours.gph,ours_members.pph,pure_clone.pph}`、
`p2_accept_reopen.vbs/.log`（含对照与克隆两次运行的日志）。

### 16.9 GPH 写端补全（2026-09-13 续做）——已大幅推进，未收口

按 §16.8 的靶心继续，本轮完成：

| 修正 | 内容 | 依据 |
|---|---|---|
| 容器/节框 | 与 MDL/OCT 同批修正（容器头第 4 个 I4、40 字节节头、20 字节哨兵） | 宿主字节 |
| **元数据节补齐** | 新增 ApplicationVersion / ReleaseDate / GridType / Bias / Encoding（节序按宿主） | 宿主 23 节清单 |
| `Application` | 补 `desc(1,1,8)` | 宿主 @+40 |
| `Encoding` | 描述符为 `desc(1,32,1)`（此前写成 `(1,1,32)`，MDL 同错已并修） | 宿主 @+40 |
| **数组节"每块一描述符"** | 发现宿主在 **LS_Links 的 owner/neigh/npe 与 LS_Nodes 的 X/Y/Z 每个数据块前都重复一次** `desc(4,n,1)`/`desc(8,n,1)`（非只写一次）——这是此前 -32 的根因 | 首差异偏移扫描 |
| 数组节默认写出 | 验收构建脚本改为真正传入 cvol / surface_regions / volume_regions / parts / assemblies / element_info | — |

**成果（`_p2_accept/ours.gph` vs 宿主 1,034,894 B）**：

| 节 | 宿主 | 本轮前 | 本轮后 |
|---|---|---|---|
| LS_Links | 705,868 | 705,836 | **705,868 ✅ 逐字节相同** |
| LS_Nodes | 222,472 | 222,440 | **222,472 ✅ 逐字节相同** |
| 节总数 | 23 | 8（缺 15） | **20（仅缺 Comments / Cycle / Unused 共 608 B）** |
| 文件 | 1,034,894 | 928,780 | **995,838（-39,056）** |

**剩余（已逐项定位，约 1 人日）**：

1. **LS_SurfaceRegions −38,416**（占剩余差异 98%）：我们的 `_surface_regions_section` 收到的是
   `surface_regions_summary()` 的 `(name, 计数)`，而该函数签名要求 `(name, face_ids)`——
   即**每个区域缺少面号数组**（宿主每区约 600 个面号）。修法：给 `gphstats` 加一个返回
   `[(name, np.ndarray[face_ids])]` 的读取函数并接进验收构建。
2. `LS_VolumeRegions` / `LS_Parts` 各 **−16**：各缺一个描述符（模式同数组节，位置待钉）。
3. `Comments` / `Cycle` / `Unused` 共 **608 B**：纯元数据模板，可照宿主字节固化
   （`Comments` = `desc(1,80,1)+block(80,"PolyHedra")`；`Unused` = `desc(4,1,1)+desc(4,u32,4)+desc(8,1,1)+block(f64)`；
   `Cycle` 内含嵌套 `Unit:$TEMP` 块，最复杂）。

**重要行为变化**：把 GPH 补到 20/23 节后，宿主对该工程的行为从**干净拒绝**（31 步全 err=0、
探针全 False）变成 **`OpenProject` 阶段挂起**（日志停在 `s004`，自愈按 idle 420 s 判挂、
两次尝试后放弃，台账 +2 行 hung）——说明宿主**开始真正解析我们的成员**，
只是被不一致的区域表（LS_SurfaceRegions）卡住。这比"静默拒绝"更接近成功，
且**必须在补完 LS_SurfaceRegions 后复验**，不能停在挂起状态。

---

### 16.10 ✅ GPH 写端补全完成 + 三写端宿主字节保真（2026-09-13 收口）

#### 一、GPH 写端补全（承接 §16.9）

| 修正项 | 内容 |
|---|---|
| **LS_SurfaceRegions 面号数组** | 验收脚本改用已存在的 `gphstats.surface_region_face_ids()`（此前误用 `surface_regions_summary()`，只给计数 → 每区缺 ~600 个面号，占剩余差异 98%） |
| **区域记录描述符** | 发现宿主在**每条区域记录前**写 `desc(1,255,1)`（SurfaceRegions/VolumeRegions/Parts 三节皆是）→ −16/记录 |
| **三个元数据节** | 新增 `Comments`（`desc(1,80,1)+block("PolyHedra")`）、`Cycle`（含内嵌 `Unit:$TEMP` 记录）、`Unused`（u32 + f64）——按宿主实字节固化为模板 |
| **`Application` 描述符** | GPH 为 `(1,8,1)`、MDL 亦为 `(1,8,1)`（与 OCT 的 `(1,8,1)` 同；此前误作 `(1,1,8)`）→ 各 2 字节 |

#### 二、写端布局的四条通用规律（本轮钉死，全部来自宿主字节对照）

1. **容器头**：`[I4=8][CRDL-FLD][I4=8][I4][I4][I4]`（四个字段，非三个）。
2. **节头 40 字节**：`[I4=32][name 32B][I4=32]` + 记录流；非空节尾 20 字节哨兵
   `[I4=12][0][0][0][I4=12]`；空节无哨兵。
3. **数组描述符逐块交错**：一个数组块前跟一个 `desc(type, n, 1)`，**不是**把
   n 个描述符连写在所有块之前（MDL 的 LS_Nodes / LS_Faces / Csid / Frid、
   GPH 的 LS_Links / LS_Nodes 全部适用）。连写会得到**同尺寸、不同字节**的文件。
4. **描述符 type 常为 1 而非 4**：如 `LS_EdgeStateOfFaces`、`LS_OctOctantRefinement`
   的数组描述符是 `desc(1, n, 1)`。

#### 三、最终保真度（对宿主原生产物做解析→写出往返）

| 写端 | 夹具 | 往返结果 |
|---|---|---|
| **MDL** | `tests/box/meshinggroup1_part.mdl` (2,969,210 B) | **逐字节相同 ✅** |
| **OCT** | `tests/box/meshinggroup1.oct` (12,609 B) | **逐字节相同 ✅** |
| **GPH** | `tests/box/meshinggroup1.gph` (141,902 B) | **逐字节相同 ✅** |

新增回归 **`tests/test_writer_host_fidelity.py`**（3 项）：从源文件读出 Date 参数后
回填，断言解析→写出**完全逐字节相等**；任何布局回退立即变红。

#### 四、P2 验收（宿主回读）——**通过 ✅**

`_p2_accept/ours_members.pph`：宿主工程 `_p12a_e2e/box.pph` 的
`meshinggroup1_part.mdl` / `.oct` / `.gph` **三个成员全部由本仓写端重写**后回注。

| 用例 | `sn_` | `mdl_` | `oct_` | `mesh_exists` | bbox | 结论 |
|---|---|---|---|---|---|---|
| 对照：宿主原工程 | True | True | True | True | [0, 0.01] | 基线 |
| 纯容器克隆 | True | True | True | True | [0, 0.01] | 容器路径 OK |
| **本仓写端重写三成员** | **True** | **True** | **True** | **True** | **[0, 0.01]** | **✅ 通过** |

两次独立运行均通过（31/31 err=0、`has_end=true`、自愈 attempts=1、0 挂起）。

> **P2 验收句「自研 .oct/.gph/_part.mdl 首次被宿主打开且几何非空」达成。**
> 写端由「自承 L2（自读自写）」升级为**宿主字节级保真 + 宿主实机可读**。

### 附：本报告用到的复核动作

- 全量回归 2 次（本机 + 独立审计 agent）：`1 failed / 1101 passed / 4 skipped`（625 s / 682 s）
- 独立复现：disc/overset 指纹对拍、`p12e_wrapping_e2e.log` 截断（814 步 / 无 end）、`catalog_coverage` 名称划分、`_section` 头长度（36 vs 40）、`write_condition_to_xml` 写入路径
- 独立实测：`remove_tiny_faces` 对黄金 box（60,492 面）在默认 tol=1e-3 下 **kept=0**，tol=1e-6 下 kept=60,492；voxmesh 子序 4x+2y+z vs `.oct` 约定 x+2y+4z（两侧代码）
- 独立宿主实测（2026-09-13）：CATIA V5 边界专项 5 腿探针（1 XT 对照 + 4 CATIA），
  对照腿绿 / 4 条 CATIA 腿静默零几何 + 容器无 snapshot；台账 +5 行全 ok
- STEP 专项（2026-09-13）：3 个真 STEP + XT 对照 4 腿全绿、几何落地、无许可门控（§11）
- 许可置死对照实验（2026-09-13）：离线 x_t 读写成功；宿主 `cold_boot` 560 s 失败（§13）
- 手册基准解析：`hh_toc.htm` → 475 条目 / 428 菜单项 / 468 主题页
- 分层代码审计：格式层、GUI 层、宿主自动化层、网格层（4 个独立 subagent，全部代码级 file:line 证据）

---

## 17. R2 更新（2026-09-14）—— CAD 全链闭环 + 面元级等价 + BC 去壳

三条对 §9 / §4 / §3 结论的实质推进：

1. **CAD → 网格全链闭环**（补齐 §9「与宿主网格无几何/数值等价」中的**链路**缺口）
   - `tools/cad_pipeline_gate.py` 拆 build / mesh / reopen 三段；x_t 腿：build **42/42**、
     mesh **176/176**、reopen **25/25**，全部 err=0，且 **`mesh_exists=True`（同会话 + 重开后）**、
     `mesh_err=False`。
   - 根因（与 R1-3 的猜测不同）：`CreateMesh` / `CreateMeshMonitor` 返回值**不可信**；真正的
     缺口是**流体区域登记**（`CreateFluidRegion` + `FluidRegion.RegisterSPart`）。三条否定配方
     （同会话 / 重开工程 / 补录制八叉树参数表）产出的 `meshinggroup1_error.mdl` 均为
     **17150 faces / 8577 verts**，与绿色参照 `p12a_bam_e2e_out.pph` 的 `meshinggroup1_ridge.mdl`
     同规模 → **面片阶段忠实，缺的是 gph**（`NUMERICALREGION.N = 0`）。
   - 证据：`_p12u_gate/r2_1_probe.json`、`r2_1_xt.json`、`r2_1_xt_wizard.json`、
     `r2_1_xt_recorded.json`、`r2_1_xt_fluidregion.json`、`r2_1_both.json`。

2. **面元级等价**（把 §9 的「仅质量阈值」升级为量化结论）
   - `tools/cad_compare.py --facets`：离线剖分 **12** 三角 vs 宿主 BAM **60 492** 三角，
     **总面积 0.0006 == 0.0006（相对误差 0.0）**、**六轴向面积分解逐轴完全相同（相对误差 0.0）**、
     bbox 一致；差异仅为分面密度（三角数比值 5041）。证据 `_p12u_cmp/r2_2_facets.json`。
   - 即「几何等价」已是可测事实；未解决的只剩**网格单元级**（gph 内容）数值等价（R3-5）。
   - 附带修正：`mdl.triangulate_faces` 返回**顶点下标**而非坐标，`cad_compare` 旧分支误当坐标
     （从未被执行过）→ 新增 `facet_profile_mesh()`。

3. **BC 去壳入口落地**（针对 §3「flow BC 只写 3–5 标签」）
   - `nav_panels.py`：`GenericCondBody(initial=...)` 预填 + `write_condition_to_xml(replace_el=...)`
     原地重写 + flow BC 页「All fields (schema)…」入口；`tests/test_cond_deshell_r24.py` 4 项。
   - 尚未铺开到其余 BC 页（wall / thermal / sym / periodic / source / initial）→ R3-2。


---

## 18. R3 更新（2026-09-14）—— 自愈层健壮化 + BC 去壳铺开 + STEP 宿主崩溃定性

### 18.1 两个「把失败伪装成别的问题」的基础设施缺陷（已修）

| # | 缺陷 | 证据 | 修法 |
|---|---|---|---|
| 1 | 进程探针走 powershell Get-Process（20 s 上限）：重网格期间整机繁忙 → TimeoutExpired 直接崩 flow；探针无输出还会被判成宿主消失而误杀健康宿主 | `_p12u_gate/r13_step_mesh.log`；`_p12u_gate/hang_characterization.jsonl` | `automation/modal_watch.py`：`host_pids_toolhelp()` / `pid_alive()`（Toolhelp32 + OpenProcess，纯 ctypes、毫秒级、无子进程）；`host_watchdog._hosts_safe()`：探针异常折成 None（未知），`_monitor` 对未知**绝不**判宿主消失 |
| 2 | `json.dumps(..., ensure_ascii=False)` 打印到 ANSI 代码页 stdout → UnicodeEncodeError，把真实原因（宿主崩溃）掩盖成编码错误 | step_mesh 的 `error: UnicodeEncodeError: 'charmap' ...` | `tools/_p12e_e2e_run.py::utf8_stdout()`（stdout/stderr → UTF-8 + replace），gate 启动即调用 |

另：网格段 / 重开段的惰性阈值按段放宽（1500 s / 900 s）——两段都在**同一条 VBS 行内**长时间不写日志（x_t mesh 实测 170 s、STEP reopen 20–360 s），默认 420 s 会把正常计算判成 hung。

### 18.2 CAD 端到端：x_t 稳定，STEP 定量归因为「宿主崩溃」

* **x_t 腿 ✅**：build 42/42、mesh **176/176**（170.5 s）、reopen 25/25，**`mesh_exists=True`（同会话 + 重开后）**、`mesh_err=False`、bbox [0,0.01]；
* **STEP 腿**：build/reopen 绿，mesh 段三次尝试全部以 `host process gone while worker blocked (idle 90.1s)` 且 **`host_pids: []`** 结束 —— 宿主进程在网格计算中**真的退出**（此前被探针超时与编码错误掩盖）。即 `key v2.step`（bbox ≈82 mm）在录制八叉树参数（`TARGETNUMBER=100000`、`BASESIZE.MIN=0.00021875`）下把宿主算崩 → R4-1 做 bbox 自适应参数标定。

### 18.3 BC 去壳从「单页按钮」升级为「全页通用入口」

`nav_panels.py`：`_find_condition_el_any()`（按名定位、不限类型）＋ `_deshell_condition_el()` ＋ `_install_deshell_menus()`（给每个带 `_cond_list` 的页挂右键 All fields (schema)... 菜单，`id()` 记账幂等）；R2-4 的 flow 按钮改为委派同一核心。测试 `tests/test_cond_deshell_r32.py` 4 项，条件域全量 **92 passed**。

### 18.4 §3「快照从不回写」的精确化

格式层**并非**缺失：`sctsnapshot.SctSnapshot.serialize()` + `SnapRecord.serialize()` 已存在，且 `tests/test_snapshot_reserialize.py` 证明对真实快照 `snap.serialize(raw) == raw`（逐字节）。缺口在 **GUI 侧从未调用**（`pph_gui.py` 只 `SctSnapshot.load` 供展示）。故落盘化的前置不是「写通道」，而是**逐面板状态存储审计**（R4-3）。

---

## 19. R4 更新（2026-09-14）—— 面板落盘通道 + 条件写盘零破坏 + STEP 网格定性

### 19.1 面板存储映射（R4-3，可再生）

`tools/panel_store_audit.py` → `docs/PANEL_STORE_MAP.md` + `schemas/panel_store_map.json`，
37 个面板类逐条带 file:line 证据：**persisted 11 / memory_only 6 / read_only 3 / none 17**。
memory_only 剩 `_PartsControlFollowupBody` / `CreatePartsBody` / `NonSolidBody` / `MeshParamBody` /
`ExecuteBody` / `CondTypeCatalogDialog`。

### 19.2 落盘通道打通（R4-4）

`panel_xenv_get` / `panel_xenv_set` / `panel_bool`：面板状态写 `main.xenv` Section/Key 并置
`xenv_dirty`；**无 xenv 时如实返回 False**。首个切片 `OptionNavBody` → `[OPTION_NAV]`，
重启保留（容器重写后回读一致）且宿主 OpenProject **25/25 err=0**、`mesh_exists=True`（多一段
不破坏宿主）。注意：宿主 xenv 现有 13 段（CAD/FACET/MESH/MESH_COMMON/OCT_MESH/RIDGE/TINYFACE/
TOLERANCE/UNIT/…），**无** OPTION 类段 —— 宿主把同名开关放在用户设置里。

### 19.3 条件写盘零破坏（R4-5）

`p12c_cond_harvest_out.pph`（49 条条件）逐条走去壳同路径原地重写 **24** 条：离线 **0 diff**、
宿主 **71/71 err=0**、`GetConditions().QueryConditionByName` **12/12 回读成功**。

### 19.4 STEP 网格：宿主退出是参数/时间驱动的（R4-1）

`cad_pipeline_gate` 新增 `--target-num` / `--min-size`（透传到录制参数表）。粗档
（50000 / 0.002，录制值 100000 / 0.00021875）下宿主存活 **1502 s**（vs 录制参数 ~90 s），
但最终仍 `host_gone`（`last_seen_hosts=[2136]`，worker `scFLOWpre_Bx64net` 继续空转）。
即：**宿主进程 STpre 在持续重网格中自行退出**，对参数敏感 → 指向宿主侧资源/超时；尚无成功档，
也没有内存量证据（R5-1/R5-2 承接）。

### 19.5 宿主消失事件独立归因（R4-2）

`hang_characterization.jsonl` 新增 `reason_kind`（`host_gone` / `log_idle`）、`host_gone`、
`last_seen_hosts`/`last_seen_diag`、`log_last_line`、`vbs` —— R4-1 的 Run A 行已实际带全字段。

---

## 20. R5 更新（2026-09-14）—— 进度信号 + 面板落盘再切 2 页

### 20.1 进度信号：CPU 活性取代「纯日志静默」判活（R5-1）

`modal_watch` 新增纯 ctypes 探针 `process_memory` / `process_cpu_seconds` / `total_cpu_seconds` /
`host_and_worker_cpu`（网格算在**工作进程** `scFLOWpre_Bx64net` 里，必须一并计入）；
`FlowExecutor._cpu_progress_ok()` 在**宿主曾探到在场**的前提下，用 CPU 推进重置日志惰性计时。
该守卫是关键：否则「宿主已死 + 工作进程空转」（R3-1/R4-1 的失败形态）会被误判成健康。
台账新增 `cpu_progress_events` / `last_seen_memory`（内存在宿主存活时采样）。

### 20.2 面板落盘：memory_only 6 → 4（R5-3）

`panel_json_get/set` 提供 JSON 变体；`MeshParamBody` → `main.xenv [PANEL_MESH_PARAM]`、
`NonSolidBody` → `[PANEL_NON_SOLID]`。审计随之 **persisted 11 → 13 / memory_only 6 → 4**
（余 `_PartsControlFollowupBody` / `CreatePartsBody` / `ExecuteBody` / `CondTypeCatalogDialog`）。
带 3 个额外 xenv 段的工程宿主重开 **25/25 err=0**、`mesh_exists=True`。

### 20.3 未执行项（如实记账）

* R5-2 STEP 参数阶梯：**已被 R5-1 解锁**（长网格不再被误杀），但每档最长 ~25 min → R6-1；
* R5-4 条件补深、R5-5 数值等价：各自需要一整块预算 → R6-2 / R6-3。

---

## 21. R6 更新（2026-09-14）—— 宿主键实测映射 + 面板落盘收尾 + STEP 宿主退出去参数化

### 21.1 宿主键映射实测（R6-5）

`tools/xenv_key_probe.py`：宿主改设置 → SaveProject → **diff main.xenv**，键名不靠猜。实测 5 条：

| COM setter | main.xenv 键 | 观测 |
|---|---|---|
| SetFacetSimpleChordTol | FACET.SIMPLE_CHORD_TOLERANCE | 1 → 0 |
| SetFacetSimpleMaxAngle | FACET.SIMPLE_MAX_ANGLE | 5 → 0 |
| SetFacetSimpleMaxWidth | FACET.SIMPLE_MAX_WIDTH | 5 → 0 |
| SetFacetUseDetailMaxWidth | FACET.USE_DETAIL_MAX_WIDTH | true → false |
| SetFacetUseAbsoluteValue | （未变化） | 未证实 |

**数值 setter 不回读原值**（7/9/13 全读回 0），布尔 setter 精确生效 → 写宿主键只能写实测确认过的取值。

### 21.2 面板落盘收尾（R6-4）

`ExecuteBody` → `PANEL_EXECUTE`、`CreatePartsBody` → `PANEL_CREATE_PARTS`；审计 **persisted 15 /
memory_only 2**（余 `_PartsControlFollowupBody` 与对话框 `CondTypeCatalogDialog`）。

### 21.3 STEP 宿主退出：参数假说被推翻，OOM 被否证（R6-1）

三档实测宿主存活 **90 s / 189.9 s / 1502 s**（更粗的档反而更早死）→ 与八叉树细度**非单调**；
台账 `last_seen_memory` 显示宿主消失前仅 **87.7 MB WS（峰值 143.8 MB）** → **OOM 否证**。
`cpu_progress_events=3` 证明 R5-1 的进度信号在生产生效，且 `host_gone` 判据正确优先。
→ 机理待定（优雅退出 / 崩溃 / 内部超时），R7-1 用 WER + Application 事件日志区分。

---

## 22. R7 更新（2026-09-14）—— 宿主崩溃定性 + 反向写宿主键 + 面板落盘收尾

### 22.1 宿主工作进程崩溃（R7-1）

Windows Application 日志 / WER 取证：`Application Error` ID 1000 的出错应用是
**`scFLOWpre_Bx64net.exe`**（工作进程），出错模块 **`mfc140u.dll`**；同秒 WER ID 1001 `APPCRASH`；
另有 `RADAR_PRE_LEAK_64`（SCTpre 家族）。时间戳与 STEP 网格轮次一一对应。
**判定：崩溃**（非优雅退出、非 OOM —— R6-1 已证 87.7 MB WS）。

关键修正：探针与台账此前只盯 **STpre**，而崩的是**工作进程**；STpre 随后退出，表现为「宿主消失」。
→ R8-4 补记工作进程画像与 WER 路径。

### 22.2 反向写宿主键被尊重（R7-4）

直接写 `main.xenv` 的 `FACET.SIMPLE_MAX_ANGLE=8` / `SIMPLE_MAX_WIDTH=9` / `USE_DETAIL_MAX_WIDTH=false`，
宿主 getter 回读 **8 / 9 / False**，27/27 err=0、`sn_/mg_/mdl_/oct_/mgs_=True`。
→ 修正 §21.1 的解读：数值不往返是 **setter 侧归一化**，不是存储限制；**写 xenv 是可行路径**。

### 22.3 面板落盘收尾（R7-5）

`_PartsControlFollowupBody` → `PANEL_FOLLOWUP`；审计 **persisted 16 / memory_only 1**（仅剩对话框
`CondTypeCatalogDialog`）。同时把「审计精确计数」断言改为**单调不变量**，消除连续两轮的回归脆性。

---

## 23. R8 更新（2026-09-14）—— 条件线实测封顶 + STEP 绕行定位 + 取证/宿主键闭环

### 23.1 条件体系：92 精确键 = 全部可落点类型（R8-1，负结果）

完整批量收割 16 个未落键 creator（全部 `True`、`save_err=0`）后 `types_before == types_after == 115`、
`new_in_universe=0`、`remaining_missing=75`。归属：`registry_key` **90** + `member_locus` **2** = **92**；
`wizard_session_state` 71（+1 gated）、`alias` 1、`poison_isolated` 1（共 166 条）。
**结论：≥140/165 的验收线前提有误**；有 XML 落点的类型已全部登记，其余为设计上无落点的向导态。

### 23.2 STEP 绕行：拦路石在宿主摄取（R8-3）

重跑转换（不用缓存）：9.9 s，产物离线 **1 body / 4358 三角 / bbox [-4,-4,0]–[4,4,3]** 完全正常；
但宿主 `OpenCadFile` 得 `ret_bam=False`、**`sn_=False`**（无 SNode），与旧缓存产物同形。
→ 拦路石 = **宿主对 CADthru x_t 的摄取**（宿主原生 x_t 同流程 `sn_=True`）→ R9-2 做格式差分。

### 23.3 取证补全与宿主键闭环（R8-4 / R8-5）

* `FlowExecutor` 台账 host-gone 行新增工作进程画像（`worker_image` / `last_seen_worker` /
  `last_seen_worker_memory`）与 `wer_reports`（直读 WER 目录，免权限；本机实测列出
  `AppCrash_scFLOWpre_Bx64ne_*`，与 R7-1 事件日志互证）；
* **宿主键闭环成立**：Faceter 面板 `apply` 写出的 `FACET.SIMPLE_CHORD_TOLERANCE` / `SIMPLE_MAX_ANGLE`
  **正是** R6-5/R7-4 实测键（离线断言），实机侧 R7-4 已证宿主回读一致、27/27 err=0。

---

## 24. R9 更新（2026-09-14）—— x_t 拒收判据（schema 版本）+ 崩溃标记 + 账目口径固化

### 24.1 宿主拒收 CADthru x_t 的字段级判据（R9-2）

`tools/xt_format_diff.py` 逐字段对比头部块（注意：只看连续 `**` 行会得到假阴性——两边都只剩 3 行）：

| 字段 | 宿主原生 `tests/box/box.x_t` | CADthru 产出 |
|---|---|---|
| **`SCH`** | **`SCH_3400153_34001`（Parasolid v34）** | **`SCH_3701153_37102`（v37）** |
| `FRU` / `APPL` | sdl_parasolid_customer_support / parasolid_acceptance_tests | Software Cradle Co.,Ltd. / CADthru |
| `KEY` / `FILE` | 占位名 | 绝对路径 |

**判据：写入端 schema（v37）高于宿主接收端（v34）→ `OpenCadFile` 静默零几何**（不报错、无 SNode），
与 R8-3 观测及 CATIA 边界形态同源。修复方向 → R10-2。

### 24.2 失败标记自动化（R9-4）

host-gone 行带 WER 报告时同时置 **`host_crash=True`**，可直接断言。

### 24.3 条件账目口径固化（R9-5）

`tools/cond_ledger.py` 常量 + 校验：宇宙 **165 = 精确键 92（90+2）+ 别名 1 + 边界 72（71+1）**；
`Thermoregulation` 为宇宙外族级注记，单独记账。再生若改账目 → 立即红。

---

## 25. R10 更新（2026-09-14）—— 零流场判据落地 + CADthru 控版否证 + 宿主键 8 条

### 25.1 §5-O3「零流场 delta」从指控变成代码判据（R10-1 前提部分）

`solver_delta.zero_field_report()`：判据取**主变量**（`VEL` / `PRES`）而非「所有场为零」——
湍流辅助量（`EVIS`/`TURK`/`TEPS`）在零流场里天然非零，用它们判会漏报。真数据验证：
I5 `b1/box_b1_400.fph` vs `b2/box_b2_400.fph` → **`zero_field=True`、`primary_nonzero=[]`、
`auxiliary_nonzero_count>0`**。即那张「delta_max=0」的表只说明**两边都是零**。

FLD/iFLD 可得性：读取器齐备（`fldstats`/`ifld`/`solver_delta --kind fld|ifld`/`fldutil_bridge`），
但磁盘上已解算产物**全是 `.fph`**、无 `.fld`/`.ifld` → 「工具可得、产物不可得」。
50 Pa 双跑未执行（单腿 1000–1500 s）→ R11-1 唯一主项。

### 25.2 CADthru 无法控版（R10-2，否证）

`SaveXTFile(asm, path)` 固定产出 `SCH_3701153_37102`（v37）；任何 3 参调用 → COM
`无效的参数数目 (-2147352562)`；类型信息内省不可用。→ R9-2 的「v37 > 宿主 v34」是**硬约束**，
替代路线是**宿主自身导出 x_t**（→ R11-2）。

### 25.3 宿主键累计 8 条，三段证据齐（R10-3）

新增 `FACET.USE_SIMPLE_SETTING`（true→false）、`FACET.MDL_METHOD`（1→0）、
`FACET.DETAIL_CHORD_ANGLE`（10→0，数值 setter 再次归一化）；写回+回读 3/3、27/27 err=0。

---

## 26. R11 更新（2026-09-14）—— 零流场入 gate + 宿主侧导出否证 + 降版线索

### 26.1 零流场判据接入 gate（R11-3）

`gate_fph` 遇 `zero_field=True` **直接判不通过**并点名主变量；CLI 对 I5 b1/b2 实测 **exit=2**。
旧断言「自比必过」按新语义改写（零流场自比必须 FAIL）。顺带修掉 `solver_delta.py` 在 ANSI 控制台下
打印中文报告的 `UnicodeEncodeError`（第三次踩同一坑 → 统一走 `console_utf8`）。

### 26.2 「宿主侧导出 v34」证伪（R11-2）

| 产物 | `SCH=` |
|---|---|
| 宿主原生 `tests/box/box.x_t`（可读） | `SCH_3400153_34001`（v34） |
| CADthru 产出 | `SCH_3701153_37102`（v37） |
| **宿主 `Doc_.SaveXTFile` 导出** | **`SCH_3701153_37102`（v37）** |

宿主内核即 v37：写得出 v37、读不了 v37（只吃 v34）；`SaveXTFile` 返回 False 但仍写文件，
随后读自身产物即以 `com_error(-2147023170 远程过程调用失败)` 挂起（自愈 2 次 / 729 s）。

### 26.3 离线降版线索（R12-1 的依据）

`ps_facet2_nodes._TRANSMIT`（`PK_PART_transmit_o_t`）含**未使用**字段 **`transmit_nw_version`**，
而本仓已直调 `PK_PART_transmit` 写文本 x_t → **离线把 v37 重编码为 v34 可达**（无需宿主参与）。

---

## 27. R12 更新（2026-09-14）—— 离线降版尝试：字段/判据两条修正

### 27.1 `transmit_nw_version` 不改变输出 schema（负结果）

`tools/xt_downgrade.py` 逐档实测 `PK_PART_transmit(nw_version=?)`：`0` → 6278 B（v37）、`100` → 5464 B（v37）；
`1 / 34 / 1000 / 2025 / 3400153 / 34001 / 37102 / 3701153` → **无输出**（取值非法）。
即按当前 `_TRANSMIT` 布局写该字段**无法降版**。

### 27.2 判据修正：本仓 transmit 产物没有 `**PART2;`

其版本信息在首行 `T51 : TRANSMIT FILE created by modeller version 370115323
SCH_3701153_37102_1300` —— R9-2 的 `SCH=` 判据对这类文件不适用，需读版本串（工具已改）。

→ R13-1 从 `pskernel.dll` 导出表找真正的版本入口并核对 o_t 真实偏移。

---

## 28. R13 更新（2026-09-14）—— **x_t 离线降版成功**，宿主可读（R8-3/R9-2 断链修复）

### 28.1 根因：结构版本用错（R12 负结果的真相）

`docs/pskernel_user_guide.md` §11.5：V37 的 `PK_PART_transmit_o_t` 需 **`o_t_version=4`**
（1/2/3 为旧布局）、格式枚举 **`18220=text`**（不是 0..5）。本仓一直传 `1`/`0`，
选项转换器因此丢弃版本字段 —— 这就是 `transmit_nw_version` 看似无效的原因。

### 28.2 取值编码（Q-Solid 官方文档）

字段 `transmit_version`（V37 名 `transmit_nw_version`）= **主版本×10 + 次版本**：101 = Parasolid 10.1、
90 = 9.0；最早 7.0，当前版本亦允许。宿主接收端是 v34 → **`340`**。

### 28.3 实测闭环

| 步骤 | 结果 |
|---|---|
| 离线降版（`transmit_version=340`） | **5553 B，`SCH_3400000_340010`（v34）** |
| 宿主 `OpenCadFile` 该产物 | **`snode_alive=True`**、`ret_bam=True`、`vmdl_alive=True` |
| 宿主整体 | **28/28 err=0** + `SaveProject` 成功 |

→ **STEP → CADthru(v37) → 本仓离线降版(v34) → 宿主可读 → BAM** 全链自有化，
§23.2/§24.1 的「宿主静默零几何」至此闭环修复。

---

## 29. R14 更新（2026-09-14）—— 降版接成产品路径，并**纠正 §23.2/§24.1 的 schema 误判**

### 29.1 一条命令出 v34（R14-1）

`cadthru_convert.py --downgrade 340` → `SCH_3400000_340010`（v34，5553 B）。

### 29.2 纠错：真正的原因是**相对路径**，不是 schema 版本

给 gate 传 `--step <相对路径>` 时宿主 CWD 不同 → `OpenCadFile` **静默返回 Nothing**
（`sn_=False`/`ret_bam=False`），看着像「格式被拒」。修正为绝对路径后：

* `r14_1_v34.x_t`（v34）→ `sn_=True`、`vmdl_=True`、`ret_bam/ret_oct=True`、build 42/42；
* `r8_3_keyv2.x_t`（**未降版 v37**）→ `snode_alive=True`、`ret_bam=True`、28/28。

**所以 §23.2「宿主拒收 CADthru x_t」与 §24.1「v37 > v34 → 拒收」均为假象**：宿主本来就读得了 v37。
§24.1 的字段差异仍然真实，但**不是失败原因**；§25.2「CADthru 无法控版」成立但**与 STEP 路由无关**。
R13-1 的离线降版保留为**可用能力**（能产出宿主同代 schema），非必要条件。

**教训**：交给宿主的路径必须绝对化 —— 这条已两次踩到（CADthru 转换、gate --step），R15-1 断言化。

### 29.3 STEP 路由现状

STEP → CADthru(v37) → 宿主摄取 → BAM（`ret_bam=True`、`vmdl_`/`oct_` 在场）**已通**；
唯一剩余阻塞 = 宿主 worker 在网格计算中崩溃（§22.1 的 APPCRASH / mfc140u.dll，外部缺陷）。

---

## 30. R15 更新（2026-09-14）—— 宿主路径纪律断言化 + STEP 路由收口

### 30.1 路径必须绝对（R15-1）

`automation/host_paths.py`：`require_abs()` / `abs_str()`，相对路径**当场抛** `RelativeHostPath`。
`tools/cad_pipeline_gate.py` 的 `--step` 从「悄悄 resolve」改为**断言** —— 正是那处 resolve 掩盖了
「传参就错」，把 R8-3/R9-2 引向 schema 误判（§29.2 已纠正）。

### 30.2 STEP 路由收口（R15-3）

```
STEP --CADthru--> x_t(v37 即可) --宿主 OpenCadFile--> SNode → BuildAnalysisModel → BAM
```

剩余唯一阻塞 = 宿主 worker 网格期崩溃（§22.1，外部缺陷）。v34 降版为**可选能力**，非必要条件。

---

## 31. R16 更新（2026-09-14）—— **数值等价首次拿到非零场证据**

### 31.1 分段驱动 + 官方 50 Pa 算例

`tools/solver_dual_run.py`（leg1/leg2/delta/status，逐段落册）默认算例 = 本机 2025.2 官方样本
`exA06-2_d_50.pph`。实测单腿 **57–187 s**（远快于 J3 exA36-2 的 1000–1500 s）。

### 31.2 delta 结论（`_p12u_gate/r16_dual/delta_table.json`）

`ok=true`、**`zero_field=false`**、`primary_nonzero=[EC_Scalar:PRES, EC_Vector:VEL, FC_Scalar:PRES,
FC_Vector:VEL]`、`gate_ok=true` —— 两次独立求解下主变量逐点一致。

§5-O3「delta 建立在零流场」**至此解决**：新证据带主变量、且 gate 拒绝零流场。

### 31.3 排期估算纠错（教训）

此前六轮按「50 Pa 双跑需 ≥1 h」反复让位，该估算取自**别的算例**（J3 exA36-2）；
目标算例 exA06-2 实测单腿 57–187 s。**估算必须以目标算例实测为准**（R17-3 入册为硬规矩）。

---

## 32. R17 更新（2026-09-14）—— **数值等价完整验收：本仓重写成员 vs 宿主原生，逐点一致**

官方 `exA06-2_d_50.pph` 只带 `meshinggroup1.gph` + `_ridge.mdl`（无 `_part.mdl`/`.oct`）→ 对照腿重写
对象 = **GPH**（本仓写端）。

| 腿 | 工程 | 求解 | FPH |
|---|---|---|---|
| 原生 | 官方工程 | 57–187 s | `r16_dual/leg1/exA06-2_d_50_139.fph` |
| 对照 | 同工程 + **GPH 由本仓写端重写** | 57 s | `r17_ours/ours_139.fph` |

对拍（`_p12u_gate/r17_ours/delta_native_vs_ours.json`）：`zero_field=false`、
`primary_nonzero=[EC_Scalar:PRES, EC_Vector:VEL, FC_Scalar:PRES, FC_Vector:VEL]`、
**`gate_ok=true`、`n_fail=0`**（默认容差 0 = 逐位复现线）。

**结论**：本仓写端重写的网格成员喂给求解器后，主变量与宿主原生工程**逐点一致** ——
「自研产物数值等价」由推测变为实测。该线（R10-1 判据 → R11-3 入 gate → R16 非零场 → R17 对照）收口。

---

## 33. R18 更新（2026-09-14）—— 数值等价线进入维护态 + 排期纪律入册

### 33.1 对照腿固化（R18-1）

`tools/solver_leg_ours.py`：一条命令完成「原生网格成员 → 本仓写端重写 → `clone_pph` 回注 → 求解 →
与原生腿 FPH 对拍（含零流场判据）」。参数化 `--base` / `--member`（gph / oct / part.mdl）/
`--native-fph`；R17 的一次性脚本已删除。测试 3 项。

### 33.2 排期纪律（R18-3，硬规矩）

`docs/ROUNDS.md` 顶部：**任何「需要 X 小时实机」的估算必须在目标算例上实测定档，不得外推**。
反例：R10–R15 六轮按「≥1 h」让位 50 Pa 双跑（数字取自 J3 exA36-2 的 1000–1500 s/腿），
而目标算例 exA06-2 实测 57–187 s/腿。

### 33.3 FLD/iFLD

仍未回答（读取器齐备、磁盘产物缺席）→ R19-1 主项，实测单腿 57–187 s，排得进一轮。

---

## 34. R19 更新（2026-09-14）—— FLD/iFLD 可得性：工具可得、默认产物不可得

用 R16/R17 已有的 exA06-2 **两腿独立求解**产物做零成本取证：

* 产物类型：`.fph .rph .ccdt .csln .gph .sph .l .log`；
* `.fld` / `.ifld` 全树计数 **0**；
* sph 明文键搜索不可靠（**不作为证据**，如实标注）。

**结论**：读取器齐备（`fldstats`/`ifld`/`solver_delta --kind fld|ifld`/`fldutil_bridge`），
但默认求解链不产出 FLD/iFLD（与 J3 期记录一致，本轮独立复现）。要拿到需在求解器输出设置显式开启，
具体开关未定位 → R20-1（查手册/设置界面，而非猜 sph 键名）。

---

## 35. R20 更新（2026-09-14）—— FLD/iFLD 的**归属被纠正**：不是 scFLOWpre 输出项

检索手册树（`Manuals\{CADthru,Common,scFLOW,scPOST,SCT,ST}`）：

* scFLOWpre 手册（`scFLOW\HTML\Pre_eng`）里 `FLD / iFLD / FLD output` **0 命中**；
* 全树只有 **ST_FE103–FE113** 一类**读取侧错误码**提到 FLD/FLDI（"READ INVALID DATA. Data in FLD-file is
  invalid"、"CANNOT FIND VARIABLE(nnnn) IN FLDI(ffff)" …）。

**结论**：FLD/iFLD 是 **STpre / scPOST 侧的映射与读取格式**，不是 scFLOWpre 求解器的输出选项；
R19-1 遗留的「产物可得性」应改走 `fldutil`/scPOST 从求解结果生成（本仓 `fldutil_bridge.py` 即此链路）→ R21-1。

---

## 36. R21 更新（2026-09-14）—— FLD/iFLD 生成：本机无无头入口（收口）

* `fldutil_bridge.py` 是**只读**桥（exports/rosace/cross_check/probe_counts），不生成 FLD；
* 安装树无独立 `FLDUTIL.exe`；`Programs_x64\*.exe` 无 `scPOST*.exe`；scPOST 只以
  `kicker_conf\document_def_scPOST_eng.xml` + `Samples_POST\ProjectTemplates\…` 的 **GUI 模块**形态存在。

**最终口径**：iFLD/FLD **读取可得**（本仓读取器齐备），**生成需 scPOST GUI** —— 属产品形态限制，
非本仓缺口；除非接入 scPOST 自动化通道，否则该线不再投入（R22 起不再列条目）。

---

## 37. R22 更新（2026-09-14）—— 数值等价结论入口径行 + leg-ours 集成待办

### 37.1 口径回填（R22-1 后半）

`docs/NEXT_PRIORITIES_20260913.md` 新增一行：**R16/R17/R18 数值等价 ✅ 已达成并固化** ——
`exA06-2_d_50` 双跑、本仓重写 GPH vs 宿主原生、`zero_field=false`、`gate_ok=true`、`n_fail=0`。
与 §32/§33 口径一致（本条即 R22-1 的第二个验收点）。

### 37.2 leg-ours 并入 `solver_dual_run`（未完成，需先核文件现状）

两次按记忆中的文本改 `tools/solver_dual_run.py` 的 `stage` 行均**未命中**（文件实际内容与预期不符）。
教训与 R16 的排期纪律同源：**改文件前先读文件**，不要凭记忆构造 old_string。→ R23-1。


---

## 38. R23 更新（2026-09-14）—— 数值等价线三段同源

`solver_dual_run.py` 新增 `leg-ours` 分发（复用 `solver_leg_ours.build_ours` 重写网格成员后跑腿），
与 `--member` 参数；测试扩到 4 项（choice / 分发分支 / 复用点三重契约）。

至此该线四段同源：`leg1`（原生）/ `leg2`（原生复跑）/ `leg-ours`（本仓重写成员）/ `delta`（对拍）。
**方法教训入册**：R22 的编辑失败源于「凭记忆构造 old_string」——R23 先读后改，一次命中（且发现 R22
那批编辑其实已写入 half，缺的只是分发分支）。


---

## 39. R25 更新（2026-09-14）—— 面板落盘线封顶（memory_only 面板 = 0）

`tools/panel_store_audit.py` 按 R24 定的口径改造：**跳过 `NOT_A_PANEL` 计数**并单列字段 ——
`counts = {none:17, persisted:16, read_only:3}`（`memory_only` 不再出现）、`memory_only_panels = []`、
`not_a_panel = ['CondTypeCatalogDialog']`。

**面板线结论**：17 个纯 UI 类 / **16 个已落盘** / 3 个只读 / **0 个只写内存面板**。
`tests/test_panel_persist_r64.py` 新增口径测试；`test_panel_persist_r53.py` 的旧断言同步改写。


---

## 40. R26 更新（2026-09-14）—— 宿主键 10 条；`OCT_MESH` 段仅部分核实

R26-1（51/51 err=0）新增 2 条实测键：

| setter | xenv 键 | 观测 |
|---|---|---|
| `SetAFFaceterLengthFactor` | `FACET.SOLID_BASE_LENGTH_FACTOR` | 0.05 → 0（数值 setter 归一化） |
| `SetIntersectionDetectionDepth` | `FACET.INTERSECTION_DETECTION_DEPTH` | 12 → 0（同上） |
| `SetCompleteParallelFlag` | （无变化） | **否证**：该 setter 不写 xenv |

实测键累计 **10 条**。观察项：本轮差分中 `FACET.USE_SIMPLE_SETTING` 由 true → false，疑为上述 setter 的
宿主联动，本轮不足以定罪 → R27-2 归因。

**尚未满足收敛判据**（`OCT_MESH` 段 4+ 键未核实）→ R27-1。

---

## 41. R27 更新（2026-09-14）—— 宿主键 13 条 + **收敛判定**

R27-1（51/51 err=0）新增 3 条实测键：`FACET.SOLID_BASE_MINIMUM_ANGLE` /
`SOLID_BASE_LENGTH_FACTOR_FOR_OCTREE` / `SOLID_BASE_MINIMUM_ANGLE_FOR_OCTREE`（累计 **13 条**）。
`FACET.USE_SIMPLE_SETTING` 的 true→false 联动**两轮独立复现**（归因待做，属观察项）。

### ★ 收敛判定：不再有可验证的新 R* 条目

| 面 | 状态 |
|---|---|
| 数值等价 | ✅ R17/R18/R23 |
| STEP 路由 | ✅ 摄取已通（剩余 = 宿主 mesh worker 崩溃，外部缺陷，有 APPCRASH+WER 证据） |
| FLD/iFLD | ✅ 产品形态限制（R20/R21） |
| 条件体系 | ✅ 92 精确键封顶（R8-1） |
| 面板落盘 | ✅ memory_only 面板 = 0（R25） |
| 宿主键 | ✅ 13 条实测（R27-1） |
| x_t schema | ✅ 误判已纠正 + 可选降版（R14-1） |


---

## 42. R28 更新（2026-09-14）—— 宿主键支线收口 + **第二次收敛判定**

三轮独立探查（`tools/_r28_probe.py`，各自冷启动）：

| 轮 | 内容 | 结果 |
|---|---|---|
| A | OCT_MESH 段（`SetVoxelOctRefineType` / `SetFacetLengthFactor` / `SetFacetAngle`） | `err0=45/47`、**xenv 零变化** → **无可用写入口** |
| B | 单变量 `SetAFFaceterLengthFactor` | 仅 `FACET.SOLID_BASE_LENGTH_FACTOR` 变（0.05→0），`USE_SIMPLE_SETTING` **未变** |
| C | 单变量 `SetIntersectionDetectionDepth` | 仅 `FACET.INTERSECTION_DETECTION_DEPTH` 变（12→0），`USE_SIMPLE_SETTING` **未变** |

**归因**：R26/R27 的 `USE_SIMPLE_SETTING` true→false 只在「同改 ≥3 setter」的组合场景出现，
**非单变量效应**（宿主一致性重算）。

### ★ 收敛判定（第二次）

R27 遗留的两件收尾均以否证/归因收口 → 七面全部「已修复 / 已定性」、宿主键 13 条实测 + 2 条否证、
**无新的可验证条目** → 按目标约定（至 R40 或不再有可验证的新 R* 条目）**终止**。

---

## 43. R29 更新（2026-09-14）—— OCT_MESH 段穷举实测：5/6 可写，推翻两条旧推断

候选 setter 取自官方 API 目录（`MeshingGroupSetting`，36 个）。**单会话逐档**改一个 setter + `SaveProject`
（74/74 err=0），逐档**增量** diff `main.xenv`：

| setter | 增量键 |
|---|---|
| `SetSolidFacetLengthFactor` | `OCT_MESH.FACET_LENGTH_FACTOR` |
| `SetSolidFacetAngle` | `OCT_MESH.FACET_ANGLE` |
| `SetSolidFacetMaxWidthFactor` | `OCT_MESH.FACET_MAX_WIDTH_FACTOR` |
| `SetSolidFacetSpecifyEachRegionFlag` | `OCT_MESH.FACET_SPECIFY_EACH_REGION` |
| `SetCompleteParallelFlag` | `OCT_MESH.COMPLETE_PARALLEL`（**推翻 §40 的否证**） |
| `SetVoxelOctRefineType`(3) | 无变化（未找到入口） |

**被推翻的推断**：§42 的「OCT_MESH 段无可用写入口」（实际 5/6 可写）、§40 的「`CompleteParallelFlag` 不写
xenv」（实际写 `OCT_MESH.COMPLETE_PARALLEL`）。两者都源于**多 setter 同改掩盖增量归属**。

### ★ 口径（新增）：键映射必须单变量逐档增量

> 任何「setter ↔ 宿主键」映射，必须**一次只改一个 setter**、**逐档 SaveProject**、**逐档增量 diff**；
> 多 setter 同改只能用于「段落粗筛」，不得据以给出否证。

宿主键累计 **18 条**。遗留 `VOXEL_OCT_REFINE_TYPE`（字符串档探针自身失败）→ R30-1。

---

## 44. R30 更新（2026-09-15）—— OCT_MESH 段 6/6 定谳 + 手册取值词表入目录

### 44.1 `VOXEL_OCT_REFINE_TYPE` 定谳：字符串枚举，非数值

单变量逐档（新工具 `tools/xenv_setter_probe.py`，base=`box.pph`，两轮共 9 档、`73/73`+`59/59`
全 err=0）。每档**新取**一次 `GetMeshingGroupSetting`，只调一个 setter，记返回值 + getter 读回 +
`SaveProject`，再逐档增量 diff `main.xenv`：

| 调用 | setter 返回 | getter 读回 | `OCT_MESH.VOXEL_OCT_REFINE_TYPE` |
|---|---|---|---|
| （纯读） | — | `octree` | 3（基线） |
| `SetVoxelOctRefineType("speed")` | True | speed | **1** |
| `SetVoxelOctRefineType("shape")` | True | shape | **2** |
| `SetVoxelOctRefineType("octree")` | True | octree | **3**（回到基线，可逆） |
| `...("Speed")` / `...("SHAPE")` | **False** | 原值不变 | 不变 |
| `...(0)` | **False** | 原值不变 | 不变 |

编码 `speed=1 / shape=2 / octree=3`；**大小写敏感**、**只接受字符串**。
**OCT_MESH 段 6 键 6/6 单变量定谳**（§43 五条 + 本条）——
**宿主键累计 19 条**（§40 = 13 → §43 = 18 → 本节 +1）。

### 44.2 根因：目录里没有取值词表（旧解析把取值行当参数）

手册把枚举取值写成**续行**（首格为空、`cells[1] = "poly"`）。旧 `_parse_method_block`
走「续行 → 新参数」分支，产出 `{"type": "", "name": "\"poly\"", "description": …}`：
全库 **1205 条假参数 / 239 个方法**，取值词表在自家 schema 里不可见 —— 这是 R29 只能猜
`"octree"`/`"voxel"` 的直接原因。

修 `tools/extract_vb_api_scflow.py`：续行三型派发（枚举行 → `values` 挂到最近的参数/返回值；
`(Note)` 行 → `note` + `note_ref`；其余 → 参数续行），并补两种行型（无表头参数行、整数枚举行）。
重新生成目录：

| 指标 | 修前 | 修后 |
|---|---|---|
| 假参数（name 带引号、type 空） | 1205 | **0** |
| 取值词表条目 | 0 | **1591** |
| 带取值的参数/返回值 | 0 | 340 |
| `note` / `note_ref` | 0 / 0 | 690 / 73 |

接住的手册行型与笔误（实测计数）：枚举 3 格 634、4 格 836、5 格 7、同格多值 12、全角引号
`”GVEL”` 1、漏闭合引号 `"IRBN` 1；整数枚举行 52。副产：`Conditions.GetFPHVariableOutput`
旧解析**丢了一个参数**（`(VARIANT)value` 行无 `[Argument]` 表头），现参数与 `0/1/2` 取值齐全。

### ★ 口径（本节新增两条）

> **同值档不算证据**：setter 被设成「恰好是该键现值」时 xenv 不动，既不能证明也不能否证；
> 逐档探针必须**至少含一个与现值不同的取值**。（R29 对值 3 的「无变化」即踩此坑。）

> **词表双源**：取值必须「**手册取值表** + **宿主 getter 读回**」两处对齐。手册会漏值——
> `GetVoxelOctRefineType` 只列 `shape`/`speed`，宿主实测还有默认值 `octree`。

§43 ★（键映射必须单变量逐档增量）与本节两条并列为**实机映射取证的强制口径**；
载体：`tools/xenv_setter_probe.py`（档位语法 `SETTER=VALUE[:GETTER]`，字符串自动加引号——
裸标识符会被 VBScript 当变量名，错误被 `On Error Resume Next` 吞掉 → 假否证）。

### 44.3 派生数据非幂等（R30-4）：快照必须能从**已提交输入**复算

复算 `schemas/merged.json` 时撞见 `tools/_p12c_cond_harvest.py merge` **非幂等**：
连跑三次 `CondSource` 计数 79→80→81→82。根因是 `extend_merged_schema` 的**累加**语义
（`target["count"] += …`）叠加「载荷=所有不在基线 pph 里的类型」——哨兵 `alias_evidence`
永不为空（`CondFan/CondFix/Spray` 无 universe 落点），于是每次运行都重喂已入库类型。
修法：载荷收敛为 `to_add`（既不在基线、也不在 merged.json 里），且仅在其非空时写盘。

**由此暴露的既有红灯**（与本次修改无关）：`p12h_registry_report.json` 冻结于 R8，其
`dispositions` 内的实样计数来自**当时未提交**的膨胀数据（9/60/80），而已提交的
`merged.json` 是 8/59/79 —— **干净检出时 `test_p12h_reconcile` 的 round-trip 断言必红**；
同测试另有一处写死 wizard 审结计数 25/1/1，而已提交的 `p12h_wizard_report.json` 只有 1 族。

处置：以已提交输入重生成快照（`p12h_registry_report.json` + `cond_types.json` v8→v9，
仅 3 条 evidence 计数与 version 变化），把写死计数改为**契约断言**，并新增
`tests/test_cond_harvest_merge_r304.py` 钉住幂等。

> ★ **口径（新增）**：任何被测试断言的**冻结快照**，必须能由**已提交**的输入复算得出；
> 「工作树多跑一次生成器恰好对上」不算通过 —— 那是把未提交状态当成了事实。

### 44.4 提交纪律把权威目录挡在门外（R30-5）

`tools/git_milestone.py --dry-run` 的跳过清单里出现了
`schemas/vb_api_catalog.json (2139148 B > 1 MB)`。追查发现更严重：该文件在 **HEAD 上就是
1,979,841 B**，最后一次入库是 **2026-08-20（`0cecf53`, P9）** —— 此后每轮重新提取的目录
**都没进仓库**，仓库里的 API 面一直落后于实际提取结果（本轮把 1591 条取值 + 690 条 Note
补进目录时才发现）。

修法：体量上限按路径区分 —— `schemas/*.json`（权威 schema）与 `docs/*.md`（文档）
放宽到 **8 MB**；其余路径维持 1 MB（大运行产物仍不得入库）。
`tests/test_git_milestone_size_r305.py` 钉住该口径，并带「目录当前体量必须在其上限内」
的不变量（防止再次静默跳过）。

**同一纪律在三处各写了一遍，第一版只改了一处**，于是复现了同类事故：

| # | 位置 | 后果 |
|---|---|---|
| 1 | `candidates()` 收录筛 | 只体现在 `--dry-run` 的「跳过」清单里（可见） |
| 2 | `main()` 暂存后二次体积筛（硬编码 `MAX_BYTES`） | **`git add` 后又被 `git reset` 剔除**：提交与推送都成功，目录却没进仓库 |
| 3 | `candidates()` 的 `if not p.is_file(): continue` | **删除**永远提交不掉（`tools/_r17_dual_ours.py` 类清理遗留） |

三处一并修（统一走 `bad_staged()`、支持 `D` 状态），并把「收录 N 个 / 删除 M 个」
打进输出，使 dry-run 与实际暂存集可对照。

---

## 45. R31 更新（2026-09-15）—— 实测键回流面板 / 描述即词表 / 取值三态 / 一致性护栏

### 45.1 OCT_MESH 6/6 回流面板（R31-1）：提案前提有误，已改正

R31 提案写「6 键里只有 2 条接进面板」。**读码实测：`MesherFaceterBody` 已写 5 条**
（`FACET_ANGLE`/`FACET_LENGTH_FACTOR`/`FACET_MAX_WIDTH_FACTOR`/`FACET_SPECIFY_EACH_REGION`/
`COMPLETE_PARALLEL`），真正缺的只有 R30 才定谳的 `VOXEL_OCT_REFINE_TYPE`。
这条同时暴露一个**编码翻译**问题：宿主 setter 说字符串枚举、xenv 落整数码。

* 表格 `pphxml.VOXEL_OCT_REFINE_TYPES = {speed:1, shape:2, octree:3}`（R30 实测值）；
* 面板读：码 → 名（未知码回落 `octree`）；面板写：名 → 码，**未知取值不落盘**；
* 实机闭环（`tools/xenv_host_write_check.py` 新增 `WRITES_MORE`，支持非 FACET 段且
  写入值/期望回读值分列）：写码 `2` → 宿主 `GetVoxelOctRefineType` 回读 **`shape`**，
  `hits 4/4`、`29/29 err=0`、SNode/MDL/OCT 全在场（51.5 s，`_p12u_gate/r31_1_write.json`）。

### 45.2 「描述即词表」行型（R31-2）：+166 条取值

两类写法：`Type of connection (string)["default" (default), …]` 与
`License mode "hpc" : HPC edition "lt" : …`。判定：**第一个引号前必须是类型标记
（(string)/(BSTR)/(VARIANT)）或 label 词（mode/type/edition/…）**。
实测 234 行 → **116 行词表 / 118 行散文或格式提示**（`Use "cycle_interval" to get …`、
`Color (string "0xAABBGGRR")`）被挡。目录：取值 **1519 → 1757**、带取值参数 **340 → 410**、
假参数仍 **0**。

### 45.3 取值查询 API 是三态，不是白名单（R31-3）

`automation/scflowpre_api.py`：`load_catalog`（缓存）/ `api_values` / `api_value_set` /
`check_api_value` → **True / False / None**。

> ★ **口径（新增）**：`None`（手册无词表）与 `False`（有词表但取值不在内）**必须分开**。
> 手册有漏项（`octree` 即漏项），把「没词表」当「非法」会误杀宿主合法取值。

### 45.4 一致性护栏（R31-4）：两条事故各钉一条，且已验证非空转

`tests/test_snapshot_guards_r314.py`：

1. `git_milestone.candidates()` 的「跳过」清单 ∩ `git ls-files` \(=\) ∅（R30-5 事故）；
2. `cond_types.json` dispositions == 报告 dispositions + 族注记；报告每条 `registry_key`
   证据里的「官方案例库实样 N 例」== `merged.json` 该类型的 `count`（受检 ≥80 类，R30-4 事故）。

**非空转证据**：同一段比较逻辑跑**修复前的提交对** `dd4e278` → 报出 **3 处不一致**
（CondPorousMedia 60/59、CondSource 80/79、CondSourceMass 9/8）；当前工作树 0 处。

---

## 46. R32 更新（2026-09-15）—— 实测键账本 / 词表驱动控件 / 手册变体归一

### 46.1 账本：先把「19 条」这个数改对（`schemas/host_keys.json`）

文档里所有 `SECTION.KEY` 逐条回溯证据后，可复算的是 **18 条**（FACET 12 + OCT_MESH 6）：
R6-5 4 + R10-3 3 + R26 2 + R27 3 + R29 5 + R30 1。旧口径「19」把 R6-5 的
`SetFacetUseAbsoluteValue`（审计 §21.1 原文即「未变化 / 未证实」）也计成了键，
此后每轮在错误基数上叠加（8/10/13/18/19 全部 +1）。**账本从此是唯一口径**，
每条含 setter / 轮次 / 证据文件，`tools/host_key_coverage.py` 逐条给写入口结论。

**单会话重核**（`tools/xenv_setter_probe.py`，18 档、256/256 err=0、71.3 s）：
每档 `delta_vs_prev` **恰好**是账本里那一把键。getter 名由目录自动配对
（`Set<X>`→`Get<X>`），不靠猜。

**写入口对账**（执行面板 `apply()` 后读 xenv，不扫源码）：18 条里 **17 条**有写入口；
本轮补上缺的 `FACET.USE_DETAIL_MAX_WIDTH`（R6-5 实测键却一直没有控件）；
剩 1 条 `FACET.INTERSECTION_DETECTION_DEPTH` 记入账本 `known_gaps` + 理由 ——
**缺口必须显式声明**，新增缺口不许静默（工具以「gaps == known_gaps」判通过）。

> ★ **新发现（反向漏项）**：`SetIntersectionDetectionDepth` **宿主实有、手册全无**
> （目录 199 类与全库 HTML 均无 `IntersectionDetection` 字样；实机返回 True 且落键）。
> R30 发现的是「取值漏项」，这一条是**成员漏项** —— 手册是子集，双向都成立。

### 46.2 枚举控件由词表驱动，两层分工（R32-2）

`nav_panels._voxel_refine_items()`：**可写白名单** = 实测编码表；**标签** = 目录描述。
目录新增「有实测码」的取值会自动进控件；「有值无码」不进（写不出去）。

### 46.3 「描述即词表」的拒行分类与两条窄规则（R32-3）

118 行拒行的分类：格式提示 88、Note 段落 16、带 2+ 取值 10、单取值 4。新增：

* 描述里**任何位置**先出现完整类型标记 **且 ≥2 个取值**；
* 括号内逗号分隔列表（含全角 `（…）`）。

**两次过宽/污染，都被随后的体检抓出**：第一版混进 63 条颜色占位 `"0xAABBGGRR"`
→ 加格式提示过滤；Note 段落污染 `Doc.SewSheets`（`"not in part mode,"`）→ Note 判散文。
收口：取值 **1757 → 1801**，格式提示 0、假参数 0。

**口径变更**：`Conditions.GetRadiationVFRETimingParam` 的 `Use "cycle_interval" to get
cycle interval` 经复核**是**词表（两个选择子 + 完整类型标记），R31-2 用错反例，
R32-3 换成 Note 文本作反例。

### 46.4 表头变体归一：+1942 条返回值（本轮最大一笔）

解析器只认 `[Return Value]`（大写 V），而手册里 `[Return value]` 有 **4280 行**
（另 `[Arguments]`/`[Return]` 各 50、拼写错与日文变体若干）——
**近一半方法的返回值连同其取值词表被静默丢弃**。归一后 **+1942 条 return、0 丢失**；
目录现值 4455 条目 / 4177 有 return / 5604 参数 / 1801 取值
（形状体检：仅 2 条手册笔误，其余全是标识符样）。

**自踩一坑并被护栏拦住**：`_head_kind` 参数正则写成 `argi`（兼容错拼 `[Argiment]`），
把正常拼写 `[Argument]` 整类漏掉，表现为取值从参数「消失」（挪到条目级）；
R32-3 的护栏（`Conditions.GetAnalysisType` 的 30 条取值必须挂在参数 `type` 上）把它抓出，
修正是把 `argu` 加回正则。

### 46.5 遗留（不猜）

手册笔误两个取值 `"'protectd1"` / `"'orthogonality"`（引号内多一个单引号）：
只在账上显式声明「待实机确认」→ R33-1，**不猜真值**。

---

## 47. R33 更新（2026-09-15）—— 手册词表三路对拍 / 取值守卫 / 缺口终态

### 47.1 笔误定谳：宿主**自己写出的** XML 是判据（R33-1）

扫官方算例库 151 个工程的 `main.xml`：`<stability_type><name>protectd1</name>`（**755 处**）、
`<stabilitygeom_type><name>orthogonality</name>`（**151 处**）—— 手册的 `"'protectd1"` 是笔误。
提取期修正（`_VALUE_FIXES`），手册原文保留在 `manual_value`；修正后取值形状体检 0 条可疑。

### 47.2 三路对拍：语料 2 组 + 实机 3 组（R33-3）

新工具 `tools/api_value_corpus_diff.py`（语料 = 宿主写出的 `<xxx_type><name>VALUE</name>`）：

| 容器 ↔ 目录成员 | 手册 | 语料 | 结论 |
|---|---|---|---|
| `stability_type` ↔ `GetPresetStabilityParam.param` | 2 | 2 | 一致 |
| `stabilitygeom_type` ↔ `GetPresetStabilityParamGeom.param` | 4 | **5** | **手册漏项 `elem_volume`** → 按语料入库（`source: host-corpus`） |

实机对拍（单会话 8 档、120/120 err=0）：`ChangeMesher`/`ChangeSurfMesher`/
`SetVoxelOctRefineType` 的手册取值全部被接受且 getter 回读同值；臆造取值全部被拒。

> 附口径实证：`ChangeSurfMesher("facet_base")` 的 xenv 增量**为空**（该档恰等于现值）——
> 「同值档不算证据」（§30/R30 口径）的又一次实证；判据 = setter 返回值 + getter 回读。

### 47.3 取值守卫进 typed 桥派发路径（R33-2）

`ComObject._check_values`：派发前校验位置参数里的字符串取值。三态：`True` 放行；
`False` **默认只告警（照常派发）**、`strict_values=True` 才抛 `ApiValueError`（**派发前**拦下）；
`None` 不管。默认不拦的理由同 §45.3（手册是子集，`octree` 即漏项）。
类名接线走 `TYPED_CLASSES`（`wire_api_classes()` 17 个类），不读 2 MB 目录 → 零 import 成本。

### 47.4 缺口终态（R33-4）

`known_gaps` 升级为 `known_gap_status`：`FACET.INTERSECTION_DETECTION_DEPTH` =
`no-panel-surface`（`terminal: true` + 理由 + 轮次）—— 缺口不许停在"待办"，
测试要求「缺口 ↔ 终态一一对应」。

---

## 48. R34 更新（2026-09-15）—— 语料对拍扩面 / VBS 取值校验 / 桥接落差账

### 48.1 语料对拍扩面：333 容器、36 同源链接、12 条漏项（R34-1）

语料取值两种写法都收（`<X><name>V</name>` 与 `<X_type>V</X_type>`）→ **333 个容器**，
按「取值集交叉」自动找链接。**交叉只能找候选**（实测 `loop_eq_param` 与
`equa_start_param` 都会匹配到 `Conditions.GetUpwdParam`），故加**名字同源**门槛：

| 桶 | 组数 | 处置 |
|---|---|---|
| 名字同源 | 36 | 12 条差异入库（`source: host-corpus`）→ 复跑 `auto_with_gap = 0` |
| 仅取值重叠 | 23 | 只提示，**不入库**（测试钉住"不得并进它匹配到的那个槽"） |

入库漏项：`battery`/`clear`/`infinite_elements`、`not_connect`、`glue`、`none`、
`CAVI`/`CMBV`/`CONC_VAPOR`、`saturated_humidity`、`surface`、`eq_comb`。

### 48.2 VBS 通道取值校验：第二版才守住（R34-2）

`build_vbs`（VBS 唯一生成口）校验「字面量紧跟方法名」的形态**之前**，
**第一版漏了 `note_ref` 回退**：setter 自己常无词表（取值挂在 getter 上，
R30 实测 `SetVoxelOctRefineType`），不跟进引用就**整类放过**。补上后两条通道
（typed 桥 / VBS）与 `check_api_value` 同一口径：`None` 不管、`False` 默认告警、
`strict` 抛错（VBS 侧在**生成阶段**抛，早于任何宿主会话）。

### 48.3 桥接落差账 + 两条不变量（R34-3）

17 类覆盖目录 1766 成员里的 **372（21.1%）**；`Conditions` 仅 **1.2%（7/607）**，
Doc 14.1%，WrappingGroup/NumericalRegion/SubmeshSurfaceRegion 100%。

1. **包装方法必须可追溯到目录名**（自研便捷方法按命名规则排除），否则等于调手册外成员；
2. **标题名 ≠ 签名名 41 处必须记 `signature_name`**（如标题 `…WitouthMovingPart` vs
   签名 `…WithoutMovingPart`、`SelectFace` vs `SetSelectFaces`）——包装类按签名写，
   不记这条就会在"目录里找不到"（本项第一版即因此误报）。

---

## 49. R35 更新（2026-09-15）—— 名字实机裁定 / 归因入库 / 目录物化

### 49.1 名字裁定：`GetTypeInfo` 双路皆堵，`GetIDsOfNames` 可用（R35-1）

离线：`HKCR\\CLSID\\{6FDA4768-…}\\TypeLib` **不存在**，二进制 `LoadTypeLib` 全部失败
→ 服务器**未注册类型库**。运行时：7 个对象的 `GetTypeInfo` 全部 `com_error`
→ 也没有运行时类型信息。故只剩 `IDispatch::GetIDsOfNames`（**只解析、不调用**）。

实机裁定 **20/41**：`both` 13 / `heading` 4 / `signature` 3 / 未裁定 21（`Cond*` 需实例）。
两条典型：`Doc.CreateDiscontinuousMeshingGroupWitouthMovingPart` **签名胜**；
`Conditions.SetContactThicknessDefault` **标题胜**（签名 `SetContactTicknessDefault` 是拼写错）。
→ **"一律用签名名"是错的**：派发名优先级 = 裁定名 → 签名名 → 目录键。裁定表入册
`schemas/name_verdicts.json`。

两个坑（已写进代码注释）：① 未开工程就 `GetConditions` 抛 `DISP_E_MEMBERNOTFOUND`，
后续实例构建全被挡；② 裸 `CDispatch` 链式调用被 win32com 当属性读，
`QueryMeshingGroupByIndex(0)` 抛 `TypeError: 'bool' object is not callable` → 必须走 typed 包装。

### 49.2 归因口径：精确同源才入库（R35-2）

23 条仅重叠候选按词干归因 → 8 条找到真成员；其中 **3 条精确同源**
（`region_type`/`variable_type`/`transfer_type`）→ 16 条取值入库；
5 条仅"包含"关系（`upwd_param` → `GetUpwdOptionParamForEquation`）**不入库**，留提示。

### 49.3 目录物化：覆盖率 21.1% → 99.6%（R35-3）

`materialize_catalog_wrappers()`：属性名 = **目录键**（保证与目录对账一致），
派发名 = **裁定名优先**。意义是**取值校验覆盖每个手册成员**（物化方法同走
`call()` → `_check_values`），手写包装不被覆盖。

---

## 50. R36 更新（2026-09-15）—— 裁定补齐 / 仅包含关系归因 / 属性物化

### 50.1 实例构造把「无实例」从 21 压到 10（R36-1）

`_obtain()`：`Cond*` 走 `conditions.CreateCond*/QueryCond*ByName`，其余走 `Get*/GetPreset*`。
新拿到 9 类（`obtained_via` 落盘）→ 裁定 **20 → 31/41**：`both 21 / heading 6 / signature 4`。

> ★ **第三次踩同一个坑**：实例构建必须传 **typed 包装**。裸 `CDispatch` 的 `getattr`
> 会被 win32com 当属性读 → `_obtain` **静默全失败**（表现为裁定数一点不涨，没有任何报错）。
> 仓库里凡是"按名字取 COM 成员"的地方都不能用裸 dispatch。

新裁定关键两条：`CondBladeShape.EditChordLength` **标题胜**（签名 `EditChoordLength` 拼写错）；
`CondOutputLFileTurbo.ClearOutletBladeRegions` **签名胜**（标题多写 Blade）。
裁定表**单调合并**（取不到实例的类保留上次结论），现覆盖 16 类。

**余 10 处**需要链式实例（手册 `instance` 字段已给配方）：`PropItem`（`PropDataBase.GetPropItem`）、
`MapCond`/`CondMapForStructure`（`GetValue`）、`ClosedVolume`（`GetCoordinatesSpecifiedPartLinkedToMesh`）、
`SpecialRegion`（`QueryPropValueObj`）、`CondCoSimRegion`（`GetOwner`）、`CondCoSim`、
`CondBoussinesqBaseTemp`（先建同名条件再按名查）→ R37-1。

### 50.2 仅包含关系归因：取值词汇唯一性（R36-2）

`upwd_param` 的语料 12 条全是 `eq_*` 形状；全库只有 `GetUpwdOptionParamForEquation.eq`
是 `eq_*` 词汇（名字更像的 `GetUpwdParam.key` 是 `MOM/ENERGY/TURB` 大写码）→ 认定为同族，
补 4 条 → 复跑对拍 `一致=True（12 = 12）`。addenda 累计 **33**。

### 50.3 属性物化（R36-3）

目录 16 条属性全部物化成 Python property：**名字取括号前那段**（`Visible(BOOL)` → `Visible`，
宿主认的也是这段），读经 `prop()`、写经 `set_prop()`，已存在者不覆盖。

---

## 51. R37 更新（2026-09-15）—— 链式实例 / VBS 纠名 / 参数个数

### 51.1 链式实例：+1，其余 9 条给**确切原因**（R37-1）

`_chains()` 按手册 `instance` 配方实现链式取实例；本机 `box.pph` 只有
`SpecialRegion` 拿到（`doc.GetSpecialRegions()[0]`，裁定 `both`）→ **32/41**。
其余 9 条逐类落 `chain_errors`：`ClosedVolume`（`GetClosedVolumes` **返回空**）、
`CondCoSim`（`CreateCondCoSim` 返回空）、`PropItem`（`CondInitial.GetPhaseMaterial()` 空，
工程未注册材料）、`CondBoussinesqBaseTemp`（目录**无** `CreateCondBoussinesqBaseTemp`）、
`CondCoSimRegion`/`MapCond`/`CondMapForStructure`（前置对象缺失）。

> ★ **结论**：这 9 条不是工序问题，而是**本机工程缺对象** → R38-1 换官方算例工程补。
> **第四次踩坑**：`obtained_via` 里塞了 COM 对象 → `json.dumps` 抛
> `TypeError: Object of type CDispatch is not JSON serializable`；证据结构只能放可序列化值。

### 51.2 VBS 通道按裁定表纠名（R37-2）

`vbs_bridge.name_corrections()`（读 `schemas/name_verdicts.json`）+
`validate_actions` 扫方法名 → 命中即报「应改用 Y」，`strict` 抛 `ApiValueError`。
堵的是真实故障：**4 处「只有签名名能解析」**的对，VBS 生成器按目录键发出去必然失败
（typed 桥已被物化包装兜住，VBS 直写没有）。

### 51.3 参数个数校验（R37-3）

`signature_arity()`：`(path, flag)`→2、`SetX flag`→1、`GetParam(key value)`→2、
`GetMesher()`→0、无签名→None。默认**只告警**（手册有可选参数，硬拦会误杀），
`strict_values=True` 才在派发前抛。

---

## 52. R38 更新（2026-09-15）—— 多工程裁定 / arity 口径 / 裁定名入目录

### 52.1 多工程单会话：换工程没换到对象，但换出两个真问题（R38-1）

`--project` 可重复 → 一个会话里轮换 `exA26-1_ldc`（CoSim）、`exB01-1_intake_manifold`
（闭空间标记最多）等，已取到的类不重复取。结果合并覆盖仍 **32/41**、未裁定仍 9 条
（6 个类）——**换工程解决不了**：这些对象在"只打开工程"的状态下不存在。

> ★ **第五次同族事故（假否证）**：`conds.GetCondCoSim()`/`GetCoSimRegions()` 返回
> **tuple**，未拆包就送 `GetIDsOfNames` → `AttributeError` → 探针把**能解析的名字判成
> `neither`**。修法两条：① `_raw` 拆 tuple/数组；② **口径分清** —— 解析过程报错记
> `unknown`（探针侧问题），只有"确实查无此名"才是 `neither`（宿主事实）。
> 另加**兜底原因**：没实例又没链式错误的类补「各工程 Get*/Create*/Query* 都未产出实例」，
> 未裁定不许静默。

### 52.2 arity 口径：多则报、少不报（R38-2）

依据：手册 optional 标注**极稀疏**（全库 14 文件 41 处，多在本仓域外的 Post/Kicker）。
故 `len(args) > expected` 才报；少传交给宿主判。

### 52.3 裁定名入目录（R38-3）

`_apply_name_verdicts()` 在提取期写入 `dispatch_name`/`dispatch_source`（**32 条**）；
`vbs_bridge.name_corrections()` 改为**先读目录**、裁定表回退 —— 只读目录的消费者也能纠名。

---

## 53. R39 更新（2026-09-15）—— 分歧总账 / 解析稳健化 / 契约门

### 53.1 41 处分歧的总账：每条都有终态（R39-1）

`tools/dispatch_account.py` 合成三份来源（目录 41 处分歧 + 类级 `instance` 配方、
实机裁定表、驱动证据的 `chain_errors`）→ **41 = 32 裁定 + 9 NYI**，NYI 每条带
**原因 + 配方**（例：`ClosedVolume.SelectFace`「`doc.GetClosedVolumes` 返回空：
闭空间要经 MDL 建模流程产生」，配方 `cvol.GetCoordinatesSpecifiedPartLinkedToMesh(id)`）。
口径：**"待办"不是终态**。

### 53.2 假否证根治：递归拆包 + 形态诊断（R39-2）

R38 只拆一层 tuple；`conds.GetCondCoSim()` **还套一层** → 仍抛 `AttributeError`。
本轮 `_unwrap()` 递归拆到 4 层 + `unknown` 时记 `object_type`/`object_repr`。

> ★ **口径**：实例拿到了、名字却解析不出来 → **探针侧限制**，**不得写成"宿主不认"**。
> 总账该条即如此表述（"该对象形态不支持 GetIDsOfNames（探针侧限制，非宿主否证）"）。
> R38/R39 两次假否证同根：**容器形态未拆净**。

### 53.3 契约门：一条命令查完 R29–R39 的不变量（R39-3）

`tools/api_contract_check.py` 六项全 PASS：目录（假参数 0 / 取值形状 0 / dispatch_name 32）、
账本（18 键、缺口 ↔ 终态）、总账（41 = 32+9）、桥接（覆盖 0.996 / 未知包装 0）、
语料（39 链接 0 缺口）、守卫三态（None/False/True）。

> 本轮把原 R39-3「optional 标记提取」**换掉**：标注全库仅 14 文件 41 处且多在域外，
> 收益极低；而散落的不变量缺一个统一入口 —— 换成契约门更值。

---

## 54. R40 更新（2026-09-15）—— MDL 流程 / 契约门进回归 / 守卫盘点 + **收敛判定**

### 54.1 闭空间：流程走通但对象拿不到，原因精确到机制（R40-1）

`--with-mdl` 走 `mg.GetMDL() → SelectAllFace(True) → CreateClosedVolumeFromSelectedFace
→ QueryClosedVolumeByIndex(0)`。三处实测教训：

1. **MDL 不在 `TYPED_CLASSES`** → 无物化包装，`getattr` 直接 AttributeError，必须走泛型
   `mdl.call(...)`；
2. **拿到的是"包着空对象的 ComObject"**：`mdl is not None` 成立，炸在 `_invoke(None, …)`，
   报错文本 `'NoneType' object has no attribute …` 会误导成"成员名写错"——
   判据必须看 `getattr(mdl, "raw", None) is None`；
3. 终态原因：**「`mg.GetMDL()` 底层返回 None（ComObject 包了个空对象）：闭空间必须建立在
   MDL 之上 —— 该工程尚未完成 MDL/BAM 建模流程」**。

### 54.2 契约门进回归入口（R40-2）

`run_all_tests.py` 先跑 `tools/api_contract_check.py`（六项），`gate_rc` 计入退出码。

### 54.3 守卫覆盖盘点（R40-3）

`tools/guard_coverage.py`：四条写路径逐条可查 —— typed 桥（取值三态 + 参数个数）、
VBS 生成（取值 + 纠名）、面板写 xenv（实测键账本 + 枚举白名单）、工具直写（逐个声明，
未声明 0）。**自证教训**：第一版用文本匹配找直写者，把本工具自己的 docstring 列成
"未声明直写者"（假阳性）→ 改用 **AST**。

### 54.4 ★ 收敛判定（R40 到界）

| 面 | 状态 |
|---|---|
| 数值等价 / CAD 摄取 / 条件封顶 / 面板落盘 | ✅ 已达成（R14/R15、R17/R18/R23、R8-1、R25-1） |
| 宿主键账本（18 条 + 缺口终态）/ API 目录（假参数 0） | ✅ R32-1 / R33-4 / R30–R36 |
| 名字裁定（32/41）+ 9 条终态 NYI | ✅ R35–R40（逐条带原因+配方） |
| 写路径守卫（4 条）+ 契约门（6 项） | ✅ R40-3 / R39-3 / R40-2 |
| FLD/iFLD | ⛔ 产品形态限制（R20/R21） |
| STEP 宿主网格崩溃 | ⛔ 外部缺陷（APPCRASH `mfc140u.dll` + WER） |
| 闭空间/材料/映射对象裁定（9 条） | ⛔ NYI：需多步 GUI 流程造对象，原因与配方已入册 |

→ **目标达成**：四条支线均达可复验终态；剩余三面属产品限制 / 外部缺陷 / 需多步 GUI 流程，
不再有"可验证且成本合理"的新 R* 条目。

---

## 55. R41 更新（2026-09-15）—— 9 条 NYI 推进：机制级结论 + `unknown` 归零

### 55.1 三条"宿主无此接口"的硬证据（反向漏项第二例）

用泛型 `call()` 试手册外的创建器（物化包装只覆盖目录里有的成员），拿到
`DISP_E_UNKNOWNNAME`：

| 尝试的成员 | 结果 |
|---|---|
| `CreateCondMapForStructure` / `QueryCondMapForStructureByName` | 未知名称 |
| `GetAllMapCondNames` | 未知名称 |
| `CreateCondBoussinesqBaseTemp` | 未知名称 |

→ 手册列了这些类，**宿主却没实现对应创建/查询接口**。R32-1 的
`SetIntersectionDetectionDepth` 是"宿主有、手册无"；这里是"手册有、宿主无" ——
**双向漏项都拿到了实例**。

### 55.2 其余 5 条：前置对象阻塞（原因逐条落册）

`ClosedVolume`：`mdl_probe` = `{begin: ok, wizard: ComObject, CreateMDL: None, mdl_raw_is_none: true}`
—— `wizard.CreateMDL` 调过之后 `GetMDL()` 仍为空；`PropItem` 需闭空间/材料；
`CondCoSim`/`CondCoSimRegion` 在 ldc / exA16-2 / exA25-1 三个 CoSim 算例里
`GetCondCoSim()` 都返回空。

### 55.3 三个探针缺陷（"假否证"同族，逐个修掉）

1. `errors.setdefault` → **旧失败文本盖住新结论**；改为覆盖；
2. `_try` 存实例**未拆 tuple** → `'tuple' object has no attribute 'call'`；改为 `_unwrap`；
3. **空 tuple 被当成对象**：`GetCondCoSim()` 返回 `()` 表示"没有该条件"，而 `_unwrap`
   只判类型不判空 → 空元组一路传到名字解析 → 记成 `unknown`。
   **空容器 = 没拿到对象**（已加单测）。

### 55.4 判据升级：最强证据优先

`dispatch_account.py` 现按 **宿主无接口(UNKNOWNNAME) > 实例已取到但解析失败 > 未取到实例**
排序原因，并落 `host_interface_absent` 字段 ——"手册有、宿主机没有"变成**机器可查**。
本轮 `unknown` **归零**（R39-2 的验收项至此真正达成）。

---

## 56. R42 更新（2026-09-15）—— 成员可用性入册 / 仓内引用自检 / NYI 终态

### 56.1 普查：手册列了、宿主没实现的 12 处（R42-1）

`--sweep` 对已取到实例的类逐个解析手册成员（`GetIDsOfNames`，只解析不调用，零副作用）：

| 类 | 未实现成员 |
|---|---|
| `CondBoundaryFlowIO` | `GetMassVolumePressureInflowDirectionType`（**名字含零宽空格 U+200B**）、`GetPbmFuncType`、`SetPbmFuncType` |
| `CondOutputTimeSeries` | `GetProjectonType`、`SetProjectonType`（手册拼写错） |
| `MeshingGroup` | `GetDiscontinuous`、`SetDiscontinuous`、`ReplaceMDLMode` |
| `Doc`/`MeshingGroupSetting`/`SpecialRegion`/`CondInitialShapeModify` | `GetAllMapCondNames`/`GetInternalUnit`/`ImportCSV`/`RemoveMorphingRegion` |

> 两个数据卫生发现：**零宽空格藏在成员名里**（该名字永远调不通）；
> `GetProjectonType` 是**两边都错**的拼写（R34-3 的 41 处是"标题 vs 签名"分歧，这次两边一致地错）。

入册：`_apply_host_absent()` → 目录 `host_absent`（12 条）+ 证据字段；
`materialize_catalog_wrappers()` **跳过**这些成员（typed 桥覆盖 1759 → 1754，下降正确）。

### 56.2 引用自检：死代码 + 检查自身假阳性（R42-2）

契约门第 7 项首跑就红：**真阳性** = `ScFlowpreMeshingGroupSetting.GetInternalUnit`
手写包装（宿主无此成员，调用必 `com_error`）→ 删除；
**假阳性** = `ImportCSV`（在 `SpecialRegion` 未实现、别的类实现了）→ 判据改为
**只在无歧义时判**（同名成员在所有类都 absent 才算）。修完：8 条无歧义、**引用 0**、门 7/7 PASS。

### 56.3 NYI 终态（R42-3）

每条 NYI 落 `terminal`：**3 `host-interface-absent` + 6 `needs-gui-flow`** ——
后者是 MDL/材料/CoSim 流程的产物，只打开工程拿不到，**明确不做**，不留"待办"。

---

## 57. R43 更新（2026-09-15）—— 普查覆盖率口径 + 探针侧错误归零

### 57.1 覆盖率三桶互斥（R43-1）

`schemas/host_member_availability.json` 的 `coverage`：

| 桶 | 数 | 含义 |
|---|---|---|
| `classes_swept` | **17**（成员 1873/4455） | 取到实例并逐成员解析过 |
| `empty_objects` | **8** | 试过但只有空壳 —— 正是 R41/R42 的 NYI 类 |
| `unswept_classes` | **174** | **从未尝试**（≠ 已实现） |

17 + 8 + 174 = 199 ✓（测试守恒）。契约门输出 `coverage` 与 `probe_errors`。

### 57.2 探针侧错误 28 → 0：空壳对象不许进 ctx（R43-2）

28 条 `error:AttributeError(NoneType)` 全在 `Octree`：官方算例里 `mg.GetOctree()`
返回**空壳**（工程未建八叉树），而 ctx 把它当对象收下 → 每个成员都报错，
**噪声差点埋掉真结论**。修法：`_empty()` 判空壳、**不收进 ctx**、
在 `coverage.empty_objects` 里留名归因。

**顺带修掉 2 个假阳性**：属性键带类型后缀（`Visible(BOOL)`/`UserControl(BOOL)`），
宿主认的是括号前那段 —— 不剥后缀会把已实现属性误报成"宿主未实现"（unknown 12 → 14）。
剥后缀后回到 **12**，目录里两条误标 `host_absent` 自动清除。

---

## 58. R44 更新（2026-09-15）—— 普查扩面到 Cond* + 空对象前置提示

### 58.1 批量条件实例化：覆盖 17 → 84 类（R44-1）

目录有 **89 个 `CreateCond*`** 创建器。探针在工程会话内批量调用（参数按 1→3→2 参退让）
→ **78 个实例**一次建成 → 逐成员解析：

| 指标 | R43 | R44 |
|---|---|---|
| 已普查类 | 17 | **84**（/199） |
| 已普查成员 | 1873 | **2793**（/4455） |
| 未实现成员（条目） | 12 | **16** |
| 探针侧错误 | 0 | **0** |

新增 4 处"手册有、宿主无"：`CondInitial.GetPbmFuncType`/`SetPbmFuncType`、
`CondPorousMedia.ImportCSV`、`CondSource.IsEnableConditionForCalculation`。

> ★ **口径**：同名成员可能在**多个类**都未实现（`GetPbmFuncType` 2 类、`ImportCSV` 2 类）
> —— 统计数**条目**（16），去重名字只有 13；R42 的"只在 SpecialRegion"断言据此更正。

### 58.2 空对象前置提示（R44-2）

`coverage.empty_hints` 落盘 8 条（`ClosedVolume`→MDL/BAM；`PropItem`→材料/物性；
`CondMapForStructure`/`MapCond`→映射流程；`CondBoussinesqBaseTemp`→条件向导；
`CondCoSim`/`CondCoSimRegion`→CoSim 设置；`Octree`→建八叉树）。测试要求每条提示
存在且含可操作关键词（MDL/材料/八叉树）。
> **口径修正（本节起生效）**：实机网格类验收一律以 `DoesMeshExist` / `DoesMeshErrorExist` 判定，
> **不得**以 `CreateMesh*` 返回值为准（R2-1 实测三者互不一致：`CreateMeshMonitor=True` 而
> `mesh_exists=False, mesh_err=True`）。

---

## 59. R45 更新（2026-09-15）—— 自动配方扩面（146 类）+ 三个假证据闸门 + 提示进产品面

### 59.1 覆盖 84 → 146 类（R45-1）

| 指标 | R44 | R45 |
|---|---|---|
| 已普查类 | 84 | **146**（/199，73.4%） |
| 已普查成员 | 2793 | **3855**（/4455） |
| 未实现成员（条目/名字） | 16 / 13 | **25 / 17** |
| 探针侧错误 | 0 | **0** |

取实例不再靠逐条手写链条，而是**生成候选计划**（`auto_plans()`，纯函数、离线可单测）：
① 类级 `instance` 配方（手册给的取法，参数照抄，含 `[in](BSTR)ProgID` 这类前缀参数的还原）；
② 目录里声明在已持有宿主（`Doc`/`Conditions`/`MeshingGroup`/`Env`/`Application`…）上的
`Create*/Get*/Query*`；③ 宿主独有成员的名字家族穷举。参数按阶梯退让。
**66 类**由自动配方取得。

### 59.2 三个假证据闸门（R45-1b，本轮主要发现）

| 事故 | 假结论 | 闸门 |
|---|---|---|
| 会话 `Application` 被别名成 `Kicker.Application` | 9 个成员 8 个 `unknown_name` → 8 条假的"宿主未实现" | 别名清空 + **验身**：会话对象实为目录 `Application` 类（unknown 比率 0.00） |
| 配方给的是**别家对象**（`CondOversetGap` 页写 `CreateCondSpray`） | 别人的成员全判未实现 | `identity_ok()`：类**独有成员**解析率 ≥ 半数才算拿到；否掉的进 `identity_rejected` |
| 对象过时/别名错导致整类失败 | 整类假否证 | `sweep_class_verdict()`：整类未知过半（成员 ≥4）→ **整类不记**，停在"未普查" |

另修两处假阳性：标题/签名对（`ClosedVolume.SelectFace`：派发名不通时回退成员键名，
证据 `resolved_via_member_key`）；自动配方错误**不并入** `call_errors`
（多宿主同名尝试会把"接口有、对象没造出来"误判成 host-interface-absent，
隔离前 NYI 终态曾从 3+6 漂成 6+0）。

### 59.3 覆盖率四桶（R45-1c）

手册页**零成员**的类（`CondALECancel`/`ParticleRegion`…）单列
`no_member_classes`：146 已普查 + 4 取不到实例 + 10 无成员 + 39 未尝试 = **199** ✅。
同时修掉 `empty_objects` 与已普查的**重叠**（早期工程空、后面工程拿到 → 199 数出 201）。

### 59.4 提示进产品面（R45-2）与常规入口（R45-3）

`automation.scflowpre_api.object_hints()` / `host_absent_members()`（缺证据文件返回空、不崩）
+ `docs/NYI_INVENTORY.md` 自动生成节「宿主侧能力边界」（取不到实例的类 + 25 条未实现成员）
+ `tools/host_member_sweep.py`（默认 5 工程、`--budget`、`--min-classes` 非零退出、`--report-only`）。
提示表升为模块级**知识** `EMPTY_HINTS`（已取到的 `ClosedVolume`/`Octree` 不再出现在当轮证据，
但知识留存）。

### 59.5 附带

目录 `host_absent` 16 → **25 条**（16 类）；分歧总账已裁定 32 → **35**、NYI 9 → **6**
（终态 1 host-interface-absent + 5 needs-gui-flow）。

---

## 60. R46 更新（2026-09-15）—— 未普查类终态归因 + 取得路径进总账 + 宿主边界上面板

### 60.1 六种终态（R46-1）

39 个未普查类逐类归因（`tools/unswept_account.py` → `schemas/unswept_account.json`），
判据全部来自证据（配方宿主 / 候选调用错误 / 返回空）：

| 终态 | 数 | 判据 |
|---|---|---|
| `needs-corpus` | 23 | 前置对象本会话没有（snode/obj_R/condcosim/mixedgas/combustion/particletracking），或取法试过**返回空** |
| `no-creation-path` | 12 | 手册未声明任何创建/取用路径（WrappingParam/IS*/IV*/PropGroup/CrossSectionView…） |
| `foreign-app` | 3 | Kicker.*（本会话是 scFLOWpre 会话） |
| `call-rejected` | 1 | 手册取法存在但调用被拒（非「未知名称」） |
| `host-interface-absent` | 0 | 手册声明的取法全部 UNKNOWNNAME（判据+测试就绪） |
| `probe-limitation` | 0 | 无结论（宁可停这里，也不编理由） |

新增证据 `coverage.auto_empty_targets`（21 条）：把「本机工程没有这类对象」与
「宿主没这个接口」分开 —— R45 三个假证据闸门的延续。

### 60.2 取得路径总账（R46-2）

`coverage.obtained_via` **156 条**（146 已普查 + 10 无成员类，零缺口），形态：
`chain:` / `auto:` / `CreateCond*:` / `session:`（会话直取，如 GetHybridParam）；
测试要求非前缀形态必须是目录里真实存在的成员名。

### 60.3 面板（R46-3）

条件类型目录新增 **Host 列**（`⚠ N` + tooltip）与 **「Host 边界…」** 对话框
（`HostBoundaryDialog`）；数据 = `scflowpre_api.host_absent_members()` /
`object_hints()`，文本 = 纯函数 `render_host_boundary()`。测试在
`QT_QPA_PLATFORM=offscreen` 下真建对话框；Qt 不可用则跳过。

> `tools/host_member_sweep.py` 的逐轮证据落点改为 `--evidence`（默认中立目录），
> 不再写死 `_p12u_gate/r45/`（否则复算会覆盖上一轮证据）。


