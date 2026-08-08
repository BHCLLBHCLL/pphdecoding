# scFLOWpre 功能对照与未实现功能开发计划

> 日期：2026-08-08 ｜ 仓库：`pphdecoding` ｜ 对照版本：Cradle CFD 2025.2（scFLOWpre 2025.2，
> SCTpre SDK 5225.20302.20251223）
>
> 对照输入：
> - 用户手册（Pre_eng，476 页）；操作手册（Operation_eng，294 页）；练习手册（Exercise_eng，157 页）
> - `C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\scFLOWpre_Bx64net.exe` 及其同目录 DLL
> - 本仓库 `pph_parser/pph_gui/pphwriter/sctsnapshot/mdl/oct/gphstats/parasolid` 等模块与 112 项测试

---

## 1. 当前代码功能实现分析

### 1.1 已交付能力（v1.0-beta，2026-08-03）

| 能力域 | 状态 | 说明 |
|------|------|------|
| `.pph` ZIP 容器 | 完整 | 成员分类、解包、`clone_pph`/`rewrite_pph` 逐成员读写回 |
| 文本成员 | 完整 | `main.js` / `main.prp` / `main.xenv` / `main.xml` 解析、摘要、编辑、写回；`sanitize_scflow_xml` 处理 `<SECTITEM[n]>` 方言 |
| CRDL-FLD 公共二进制层 | 完整 | gph/oct/mdl 共享的大端节扫描、记录迭代、元数据 |
| MDL 面片几何 | 完整（读） | 顶点、面（face_type 133/134）、csid 双侧闭体、frid 面区域、ridge 状态 |
| OCT 八叉树 | 完整（读） | 前序位图、Morton 子序、叶子包围盒重建、深度统计 |
| GPH 体网格 | 部分（读统计） | `gphstats` 轻量解析（面/单元/边界/顶点/区域/Parts）；完整写端未实现 |
| sctsnapshot 快照 | 完整（读） | 小端记录流、失步重同步、LZMS 解压（cabinet/wimlib）、PKBody3 Blowfish 解密、OCTREEDIVISION/REGION 语义、BSGSEX |
| 写端 | 部分 | LZMS 压缩、PKBody3 加密、ZIP 容器 round-trip 已闭环；sctsnapshot 记录级字节重排与 SCTpre 实机验收未完成 |
| Parasolid 提取 | 部分 | 传输流 schema/字段名/实体类型（PKEdge/PKFace/PKVertex）、SDL 属性；完整 B-rep 还原未实现 |
| GUI | 已交付查看/轻编辑 | scFLOWpre 式四窗格布局、成员树/模型树、属性窗、3D 视图（MDL/OCT/GPH）、剖切、拾取、Dashboard、文本编辑、快照树 |
| 导航参数表单 | 部分 | 12 类导航面板（Parts Control、Create/Modify Parts、Mesher/Faceter、Octree/Mesh 参数等）主要读写 `xenv/xml` 少量键；**不调用网格器/求解器** |
| 测试 | 112 项通过 | 容器/文本/快照/LZMS/MDL/OCT/GPH/语义/GUI/VTK 离屏/writer round-trip |

### 1.2 关键缺口（按重要性）

1. **没有任何计算管线**：Prepare Parts → Wrapping → Build Analysis Model → Octree → Mesh → Solver 全链路未实现，`ExecuteBody` 明确标注“不调用网格器/求解器”。
2. **条件体系覆盖极低**：样例 `main.xml` 仅含少量条件；scFLOWpre 导出符号中有约 180 个 `Cond*` 条件类，手册 Conditions 分类 285 页。当前 GUI 只有条件摘要与少量硬编码表单。
3. **几何/Parasolid 只有字段提取**：不能导入 CAD、不能做布尔/修复/面片化（faceting）、不能生成 MDL，也不能做闭体识别。
4. **二进制写端缺失**：能写回 ZIP 成员与加密块，但不能生成/修改 `.oct`、`.gph`、`_part.mdl`、`_ridge.mdl` 的计算结果。
5. **自动化与批处理缺失**：无 VBScript 录制/执行、无 scFLOWpreAPI 桥、无 `scflowcomb2025`/CMB 批处理、无求解器启动与结果读取（FPH/L 文件）。
6. **GUI 与手册功能面差距大**：Edit 22 页、Select 23 页、View 33 页、Option 35 页中大部分菜单未实现或仅为占位。

---

## 2. 对照基准

### 2.1 手册功能面

Pre 手册按菜单/功能域分布（按文件名前缀统计）：

| 功能域 | 页面数 | 代表功能 |
|------|------|------|
| Condition（条件） | 285 | 分析类型、基本设置、边界条件、材料、网格/八叉树参数、输出、粒子/DEM/自由表面/辐射/电池等 |
| Option（选项） | 35 | 环境设置、项目配置（CAD/文件/网格/单位/容差/ridge/tiny face/Voxel）、单位换算、语言 |
| View（视图） | 33 | Part/Octree/Mesh、剖面、相邻八分体、显示/隐藏、细化层级、prism 报告 |
| Select（选择） | 23 | 鼠标拾取、橡皮框/圆/多边形、全选/取消、按单元号/列表选择、质量检查 |
| Edit（编辑） | 22 | 创建/修改 Parts、Facet Part、Non-Solid、Region 注册、ridge 重算、八分体细化/合并、测量 |
| File（文件） | 13 | 新建/打开/保存/另存、导入/导出、VBScript 录制/执行、Actran 文件 |
| Execute（执行） | 10 | Begin/Cancel/Execute/Retry Wrapping、Build Analysis Model、Octree、Mesh、Solver |
| Analysis Model Wizard | 10 | 面片精度、tiny face 移除、多折边/面、修复报告 |
| 变量/表/脚本 | 8 | 常量、映射、格式化/非格式化脚本、用户自定义函数 |
| 界面 | 6 | Navigation/Tree/Property/Draw 窗格、Layout、鼠标/键盘操作 |

操作手册（294 页）覆盖完整操作流：新建项目 → 导入 CAD/Part → 准备 Part → 注册区域 → 设置条件 → 建分析模型 → 生成八叉树/网格 → 执行求解 → 后处理可视化，另有 scFAST（GPU）与 Tutorial 1–3、Training 1–3。

练习手册（157 页）覆盖 36 类功能示例与 6 个预处理专题（内部/外部流体域、修复损坏面、tiny geometry、Voxel Fitting、Thin Mesh、Sweep Mesh、坐标指定 Part），可作为验收用例清单。

### 2.2 程序逆向要点（Programs_x64）

| 二进制 | 导出数 | 证据与用途 |
|------|------|------|
| `scFLOWpre_Bx64net.exe` | — | 原生 MFC GUI 主程序；导入 `scFLOWpreCmd/API/DB/GUI`、`SCTpre*`、`ZipLibrary`、`ParasolidGW`；内置 VBScript 引擎（`CLSID_VBScript`、`ExecuteVBS`、`StartRecordVBS`、`history.vbs`） |
| `scFLOWpreCmd_Bx64net.dll` | 11,001 | 246 个 C++ 类；约 180 个 `Cond*` 条件类；`Doc/Env/ProjectSetting/Conditions/MeshingGroup/Region/OctParam/SurfParam/SweepParam/TetraParam/PolyConvParam/WrappingParam`；`AddTemporaryDrawingObject*`、`AddscFLOWpreCmdCallback` 表明是可扩展的命令/插件内核 |
| `scFLOWpreAPI_Bx64.dll` | 44 | VBS 自动化 API：`ExecuteVBS`、`ExecuteVBSWithFile`、`StartRecordVBS`、`EndRecordVBS`、窗格/菜单/语言控制 |
| `scFLOWpreDB_Bx64.dll` | 273 | 条件显示名/单位转换/颜色/通用工具；`LocalParasolid` 暴露 `PKBody_*`/`PKBodies_*`（布尔、Sew、Imprint、Repair、Offset、ConvertToBytes/Encrypt 等） |
| `SCTprime_Bx64.dll` | 1,176 | CADThru 核心接口：`IShapeGroupSet/CreateShapeGroup`、`CreateMDL`、`CreateFacetOctree`、`CreateWrapOctreeByDefaultParam`、`ExecuteWrapping`、`CreateMeshOctreeByDefaultParam`、`IVMDL/IOctree/IFaceRegion/ITinyFacesClass`、`ConvertFacetToXT`——即“无界面预处理核心” |
| `SCTpreCore_Dx64.dll` | 814 | 网格参数对象：`OCTPARAM/SURFPARAM/TETRAPARAM/HYBRIDPARAM/POLYCONVPARAM/PolyBoundaryLayerParam/SWEEPMESHPARAM/ElemFixerParam`，含 `LoadEnv/SaveEnv/convertUnitOfCoordinate` |
| `SCTpreLib_Dx64.dll` | 720 | `InitSCTpreLib*`、`getOctParam/getMesh/getOctree/getSurfParam/getTetraParam`；boost 序列化 OCT/MESH 参数（对应 `sctsnapshot`/ZIP 中的参数块） |
| `SCTpreSolver_Dx64.dll` | 18,002 | 求解器侧数据类（4 字母条件类、`CSolverCommandProxy`），是未来解析 CMB/求解文件的依据 |
| `ParasolidGW_Bx64.dll` / `PrimeParasolidGW_Bx64.dll` | 1,174 / 1,175 | Parasolid 内核包装：`PKBody_*`、`PKBodies_*`、`PKAssembly_*`、`PKBSurf/PKBCurve` 等（配合 `pskernel.dll`） |
| `ImportGeometry_Bx64.dll` | 18 | `ImportLayers`（DXF）、`ReadMDL/ReadPre/ReadFLD`、`TransformScale` 等导入能力 |
| `ZipLibrary.dll` | 5 | `ExpandZip`/`ZipToFile`（PPH 容器） |
| `scFLOWpreGUI_Bx64net.dll` | 24 | 插件接口 `scFLOWpreAddin_*`（CreateMenu/CreatePanes/OnExecuteVBS/ViewerMode） |
| `SCTpreCLIHelper_Bx64.exe` | — | 批处理辅助：为 `scflowcomb2025` 输出 pre/solver 命令行（`preproc-cmd`、`exe-cmdline` 等） |

结论：scFLOWpre 的“几何/面片/八叉树/闭体”核心能力集中在 **SCTprime + ParasolidGW**，参数/条件集中在 **scFLOWpreCmd**，批处理入口为 **CMB + scflowcomb2025 + SCTpreCLIHelper**，脚本入口为 **VBScript（history.vbs / ExecuteVBScript）**。

---

## 3. 功能差距矩阵

状态图例：✅ 已实现（本仓库）｜◑ 部分（读/表单/占位）｜❌ 未实现。

### 3.1 文件（File）

| 功能 | 手册 | 当前 | 说明 |
|------|------|------|------|
| 新建项目 | File-New_Project | ❌ | 无项目模板/项目类型切换 |
| 打开/保存/另存为 | File-Open/Save/Save_As | ◑ | 打开/另存 PPH 已实现；保存为原文件、项目文件夹模式未实现 |
| 打开项目文件夹 | File-Open_Project_Folder | ◑ | 有方法但未完整接入菜单 |
| 导入 | File-Import | ❌ | 仅成员导出；CAD/Patch/OCT/GPH/PRE/VIEW 导入均为表单占位 |
| 导出 | File-Export | ❌ | 无 CMB/FPH/结果文件导出 |
| VBScript 录制/执行 | File-Start/Stop/Execute_VBScript | ❌ | GUI 有入口未接线；无 `scFLOWpreAPI` 桥 |
| Actran 文件 | File-Create_Actran_Files | ❌ | 会话类型依赖 |

### 3.2 编辑（Edit）与选择（Select）

| 功能 | 手册页 | 当前 |
|------|------|------|
| Create/Modify Parts（几何创建/变换/布尔） | 2 页 | ◑ 表单仅写部分 XML 标志；无几何操作 |
| Define Facet Part / Non-Solid / Non-Facet Closed Volume | 3 页 | ◑ 表单占位 |
| Register Region（面/体区域） | 1 页 | ◑ 表单可改 XML；无几何拾取注册 |
| Ridge（重算/设非 ridge） | 3 页 | ❌ 仅能读取 edge state |
| Refine/Merge Octants、Refine from Curvature/Separation | 5 页 | ❌ |
| 测量工具 | 1 页 | ❌ |
| Undo | 1 页 | ❌ |
| 2D Sub-mesh | 1 页 | ❌ |
| 鼠标拾取（Face/Part/Vertex/Edge/Spread） | 5 页 | ◑ 仅 MDL 面拾取 |
| 橡皮框/圆/多边形（选择/隐藏/显示） | 6 页 | ◑ 仅橡皮框缩放 |
| 全选/取消/按编号/列表选择 | 8 页 | ❌ |
| Element Quality Check | 2 页 | ❌ |

### 3.3 视图（View）与选项（Option）

| 功能 | 当前 |
|------|------|
| Part/Octree/Mesh 显示切换、Fit、Reset、Show All | ✅（3D 层与模型树） |
| 网格剖面 | ✅（vtkCutter/clip，X/Y/Z/自定义平面） |
| 隐藏/显示 Parts/Faces、仅显示选中 | ✅（模型树复选 + 掩码） |
| 坐标轴、图例、平行投影 | ✅ |
| 细化层级显示、相邻八分体、Region 注册检查、Prism 报告、Element Types | ❌ |
| 朝向切换显示（Switch Display Surface by Orientation） | ❌ |
| 橡皮框/圆/多边形 Hide/Show | ❌ |
| Parts List 对话框 | ❌ |
| 环境设置/项目配置（CAD/File/Mesh/Unit/Tolerance/Ridge/TinyFace/Voxel/MSC CoSim） | ◑ xenv 文本编辑 + 少量表单；无完整对话框 |
| 单位换算 | ◑ `unit_type→xenv` 映射已建立，127 个单位键未全覆盖 |
| 语言/翻译 | ❌ |

### 3.4 条件（Condition）——最大缺口

| 子域 | 手册页 | 当前 |
|------|------|------|
| Project Type Setting | 1 | ◑ 可读 XML 类型；无会话切换/转换 |
| Parts Control | 1 | ◑ 表单（discontinuous/overset/wrapping + part flags） |
| Mesher/Faceter Setting | 1 | ◑ 表单（少量 xenv 键） |
| Octree Parameter / Mesh Parameter / Wrapping Parameter | 9 | ◑ 表单（少量键），缺详细设置 |
| Part Material / Fluid / Solid / 多相 | 6 | ◑ 表单选择 + prp 摘要；无完整物性编辑 |
| Conditions（全部） | 285 | ◑ 仅摘要树；样例含少量条件，scFLOWpre 有约 180 个条件类 |
| 变量/常量/映射/脚本/用户函数 | 8 | ◑ 解析 main.js 函数模板；无编辑器 |
| 表格/多 Y 轴表 | 2 | ◑ 解析占位 |
| 自适应网格参数 | 1 | ❌ |

### 3.5 执行（Execute）与结果

| 功能 | 当前 |
|------|------|
| Prepare Parts / Begin/Cancel/Execute/Retry Wrapping | ❌（表单占位） |
| Build Analysis Model（闭体识别） | ❌（表单占位） |
| Generate Octree / Generate Mesh | ❌（表单占位） |
| Execute Solver / Job 注册 / 监控 | ❌ |
| 结果文件（FPH/L 文件/Pathline/HeatPath） | ❌ 无解析器 |
| 批处理（scflowcomb2025/CMB） | ❌ |

---

## 4. 未实现功能开发计划

### 4.1 总体架构

```
┌────────────────────────── pphdecoding 2.0（目标架构）──────────────────────────┐
│                                                                                │
│  UI 层（PyQt6/PyQt5）                                                          │
│  ├─ Navigation / Tree / Property / Draw（对齐 Pre 手册四窗格）                  │
│  ├─ 条件编辑器（schema 驱动，覆盖 285 页 Conditions）                          │
│  ├─ 几何编辑（OCCT 桥：创建/变换/布尔/修复/测量/选择）                         │
│  └─ 批处理/监控面板（Execute + Job + 结果可视化）                              │
│                                                                                │
│  服务层                                                                         │
│  ├─ ProjectService     新建/打开/保存/导入/导出/项目类型                        │
│  ├─ SchemaRegistry     条件/环境/材料 schema + 单位换算                         │
│  ├─ GeometryService    CAD 导入、B-rep、faceting、闭体识别                       │
│  ├─ MeshingService     Octree / 体网格 / prism / 质量检查                       │
│  ├─ ResultService      FPH / L 文件 / Pathline / HeatPath 解析                  │
│  └─ JobService         求解器启动、监控、批处理                                 │
│                                                                                │
│  适配层（两种引擎策略并存）                                                      │
│  ├─ AutomationBridge   VBScript + scFLOWpreAPI + GUI 自动化（验收/黄金样本）    │
│  ├─ NativeBridge       C++/CLI 封装 scFLOWpreCmd/SCTprime/SCTpreLib（高性能）   │
│  ├─ BatchBridge        CMB + scflowcomb2025 + SCTpreCLIHelper                  │
│  └─ NativeEngine       OCCT 几何 + 自研八叉树/体网格（长期独立路线）            │
│                                                                                │
│  格式层（已有 + 扩展）                                                          │
│  pph ZIP / CRDL-FLD / MDL / OCT / GPH 写端 / sctsnapshot 记录级重排 /          │
│  PKBody3 / Parasolid 传输流 / XML·PRP·XENV·JS                                   │
└────────────────────────────────────────────────────────────────────────────────┘
```

**核心决策**：计算密集且商业级的部分（CAD 转换、wrapping、faceting、体网格）优先走“桥接 + 验收”路线，用 scFLOWpre 本体做黄金输出；同时逐步沉淀自研实现。这能把“功能可用”的交付从数年压缩到半年，并让自研算法始终有黄金参照。

### 4.2 阶段一：参数/条件层全覆盖（W1–W4）

目标：任何 `.pph` 的 `main.xml/xenv/prp/js` 都能结构化编辑并写回，覆盖全部条件类型与单位。

技术方案：
1. **Schema 抽取工具 `tools/extract_schema.py`**：
   - 输入：真实项目 `main.xml` 中的 `<conditions>` 树、`main.xenv` 全部 Section/Key、`main.prp` 物性组；
   - 对照：`scFLOWpreCmd` 导出符号中的 `Cond*` 类名与 setter 方法名、`SCTpreCore` 参数对象、`scFLOWpreDB` 的 `CondClassNameToDispName/ConditionNameToDispName`；
   - 输出：`schemas/conditions.yaml`、`schemas/xenv_keys.yaml`、`schemas/prp_groups.yaml`。
2. **录制补全**：通过 `File → Start Recording VBScript` 在 scFLOWpre 中操作每个条件页，得到 `history.vbs`；解析其 `SetProperty/AddCondition/ApplyToRegion` 调用序列，反推字段语义与默认值。
3. **通用条件编辑器 `condition_editor.py`**：
   - 按分析类型/边界/输出分组树；字段类型：bool/int/float/string/enum/区域引用/表格引用/脚本引用/带单位量；
   - 单位感知输入（`ValueWithUnit`/`DPointU` 已解码，扩展为完整 `UNIT` 表）；
   - 写回走 `serialize_main_xml` + `set_xenv_value`，支持“改 → 写回 → scFLOWpre 重开”验收。
4. **表格/变量/脚本编辑器**：`tables`、`multi_yaxis_tables`、`mapping_conditions`、常量值、格式化/非格式化脚本、用户函数（`main.js` 函数模板已有解析基础）。

里程碑 M1：schema 注册表 v1、全部条件页可浏览、常用条件可编辑写回、round-trip 测试通过。

### 4.3 阶段二：自动化桥与批处理（W3–W8，与阶段一重叠）

目标：打通“打开 PPH → 执行预处理 → 生成网格 → 运行求解 → 读结果”的完整闭环（先依赖 scFLOWpre 本体）。

技术方案：
1. **VBS/GUI 桥（验收与黄金样本用）**：`automation/vbs_bridge.py`
   - 用 `pywinauto`/UI Automation 驱动 `scFLOWpre_Bx64net.exe`，调用 `File → Execute VBScript`，或直接生成 `history.vbs` 回放；
   - 封装 `scFLOWpreAPI` 的 `ExecuteVBS/StartRecordVBS/EndRecordVBS`（先确认能否从外部进程加载调用，否则走 GUI 自动化）。
2. **NativeBridge（推荐主力，W5 启动）**：`native/scflow_bridge.cpp` + MSVC
   - 用 ctypes 无法安全调用 C++ 类，因此写一个 C 接口包装 DLL，动态链接 `scFLOWpreCmd`、`SCTprime`、`SCTpreLib`、`ParasolidGW`；
   - 首批 API：`doc_open/save`、`shapegroup_create/mdl_create`、`wrap_execute`、`octree_create`、`mesh_create`、`cmb_export`、`solver_run`；
   - 导出符号即接口地图：`SCTprime` 的 `CreateShapeGroupSet/CreateShapeGroup/CreateMDL/CreateFacetOctree/ExecuteWrapping/CreateMeshOctreeByDefaultParam` 可直接对应管线步骤。
3. **BatchBridge**：生成 CMB → 用 `scflowcomb2025`（本机 `SCTpreCLIHelper` 可打印命令行；Linux 版支持 `-prescript/-prearg`），实现无人值守批处理。
4. **ResultService v1**：解析求解输出（L 文件文本、FPH 字段文件），先支持温度/速度/压力场加载与 VTK 显示。

里程碑 M2：命令行/自动化可对 box、laptop 样例完成 Prepare→BAM→Octree→Mesh→Solver→结果可视化全链路。

### 4.4 阶段三：几何/B-rep 与预处理几何能力（W6–W14）

目标：脱离“只能看”的几何能力，实现 CAD 导入、装配树、MDL 生成、闭体识别、基础几何编辑。

技术方案：
1. **OCCT 集成 `geometry/`**（pythonocc-core 优先，失败则 C++ OCCT 包装）：
   - STEP/IGES/STL/BREP 原生导入；Parasolid X_T 优先用 `scConverter`/`SCTprime ConvertFacetToXT`/`ParasolidGW` 桥转 STEP 或直接解析（受许可约束），Datakit 作为备选；
   - 装配树 → 部件/实体/面/边/顶点模型，字段与 `sctsnapshot` 的 `FACEGROUPW/FACEINFOMAP/EDGEINFOMAP/VERTEXINFOMAP/FFREVERSEMAP` 对齐。
2. **MDL 写端 `mdl_writer.py`**：按已解码的 CRDL-FLD 布局生成 `LS_Nodes/LS_Faces/LS_CsidOfFaces/LS_FridOfFaces/LS_EdgeStateOfFaces/LS_MdlClosedVolumes/LS_MdlVolumeRegions/LS_MdlSurfaceRegions`；先用简单几何验证，再用 SCTprime 生成 MDL 对照。
3. **闭体识别（Build Analysis Model 的几何核心）**：
   - 输入：缝合后的面片拓扑；利用 `csid` 双侧连通关系做洪水填充，实现内部/外部流体域识别；
   - 容差来自 Project Configuration（Distance to Regard Two Bodies as Same / Sew / Non-Manifold / Contact 等）；
   - 输出：闭体表、体积/表面区域、区域种子点，与 `LS_MdlClosedVolumes/LS_MdlVolumeRegions` 一致。
4. **几何编辑**：OCCT 布尔（加/减/交）、变换、创建盒/圆柱/球/面/线、Sew/Repair/Offset/Imprint、tiny-face 检测与移除、ridge 重算（对照 Option→Project Configuration→Ridges/Tiny Faces）。

里程碑 M3：可导入 STEP/STL 工程、生成并写回 MDL、box/laptop 闭体识别与 SCTprime 结果一致、基础编辑命令可用。

### 4.5 阶段四：八叉树与网格生成（W10–W20）

目标：从“桥接生成”到“自研可解释”，v1 至少支持笛卡尔核心网格 + 简单棱柱层。

技术方案（双轨）：
1. **桥接轨（先交付）**：通过 NativeBridge 调 `SCTprime`/`SCTpreLib` 生成 OCT/GPH，并用 `pphwriter` 写回 `.pph`；同时捕获中间结果作为黄金样本。
2. **自研轨（研究级）**：
   - `octree_gen.py`：由面片几何驱动细化（弦差/角度/曲率/分离度、区域加密限制、平衡），输出 CRDL-FLD `.oct`；用 `sctsnapshot.OCTREEDIVISION/OCTREEREGION` 语义做正确性校验；
   - `mesh_gen.py`：笛卡尔核心网格 → 边界贴合/多面体转换 → prism 层插入 → 光顺 → 质量检查；参数对照 `SCTpreCore` 的 `OCTPARAM/SURFPARAM/TETRAPARAM/HYBRIDPARAM/POLYCONVPARAM/PolyBoundaryLayerParam`；
   - `gph_writer.py`：CRDL-FLD GPH 写端（LS_Nodes/LS_Links/LS_Region/LS_Parts 等），当前只有读统计，需要补齐完整节布局；
   - 质量检查：单元行列式/面扭曲/非正交/长宽比/体积比，对照 `OCTBASEPOLYPARAM.check*` 系列。
3. **验收**：box 网格与 scFLOWpre 输出逐项比对（单元数、面数、边界、区域、质量分布）；laptop 样例先跑通再追求一致性。

里程碑 M4：自研 octree 生成器通过 box 黄金对照；桥接轨完成 laptop 网格生成；GPH 写端闭环。

### 4.6 阶段五：GUI 与手册功能对齐（W16–W26）

目标：按 Pre 手册逐页核对，补齐交互功能面。

技术方案：
1. **File/Edit/Select/View/Option/Execute/Help 菜单逐项实现**，以 3.1–3.5 差距矩阵为 checklist；
2. **选择系统**：橡皮框/圆/多边形（选择、隐藏、显示）、按单元号/列表选择、区域批量选择；
3. **视图系统**：细化层级显示、相邻八分体显示、Region 注册检查、Prism 报告、朝向切换显示、Element Types；
4. **测量与检查**：距离/角度/面积/体积测量、Element Quality Check 结果面板；
5. **条件编辑器全面接入**：285 页 Conditions 由 schema 驱动生成表单，分析类型联动（流/自由表面/多相/辐射/粒子/电池等）；
6. **环境设置与项目配置对话框**：单位、CAD、文件、网格、容差、ridge/tiny face、Voxel、MSC CoSim；
7. **批处理面板**：Execute 对话框真正执行 BAM→Octree→Mesh→Export→Save→Solver，并可选择只生成计划。

里程碑 M5：手册功能覆盖 checklist ≥90%，全部菜单可运行，核心工作流无需 scFLOWpre 手工介入。

### 4.7 阶段六：验证、黄金语料与发布（W24–W30）

1. **黄金语料库**：30+ 个真实 PPH（不同网格组/单位制/几何复杂度/分析类型），每个配“scFLOWpre 操作步骤 + history.vbs + 输出成员哈希”；
2. **字节级回归**：解析 → 编辑 → 写回 → scFLOWpre 重开一致；二进制成员逐字节对比；
3. **功能验收矩阵**：以练习手册 36 类功能 + 6 个预处理专题为用例，逐项自动跑批；
4. **性能**：laptop 级模型（3.9 亿字节 GPH / 3.4M 叶子）打开 <5s、渲染 <2s、写回 <10s；
5. **打包**：PyInstaller + 安装脚本；文档（README/DEV_SUMMARY 更新）；
6. **合规**：明确 scFLOWpre/Parasolid/OCCT/Datakit 的许可边界，桥接模式仅在本机已授权环境使用。

里程碑 M6：v1.0 发布，达到“可替代 scFLOWpre 的常用前处理操作 + 批处理”目标。

---

## 5. 时间节点

假设：3 人团队（Python/格式 1 人、C++/逆向 1 人、几何/网格算法 1 人）；若 1–2 人，工期按 ×1.5–×2 折算。

| 阶段 | 周期 | 里程碑 | 关键交付 |
|------|------|------|------|
| 0 基线 | W0（2026-08-08 起 2 周） | M0 | 样例语料 + schema 抽取 + scFLOWpre 自动化可行性验证 |
| 1 参数/条件层 | W1–W4 | M1（2026-09-05） | schema 注册表、条件编辑器、单位表、写回闭环 |
| 2 自动化桥/批处理 | W3–W8 | M2（2026-10-03） | VBS/API/Native/Batch 桥、全链路跑通、结果读取 v1 |
| 3 几何/B-rep | W6–W14 | M3（2026-11-14） | CAD 导入、MDL 写端、闭体识别、基础编辑 |
| 4 八叉树/网格 | W10–W20 | M4（2027-01-02） | octree 生成器、GPH 写端、桥接网格 v1 |
| 5 GUI 对齐 | W16–W26 | M5（2027-02-13） | 手册 checklist ≥90%、条件全编辑、Execute 可运行 |
| 6 验证/发布 | W24–W30 | M6（2027-03-27） | 黄金语料、验收矩阵、打包发布 |

```
2026-08  09       10       11       12       2027-01  02       03
├─M0──┤
      ├─M1────────┤
      ├────M2────────────┤
            ├────M3────────────────┤
                  ├────M4────────────────────┤
                        ├────M5────────────────────────┤
                              ├────M6────────────────────────┤
```

### 关键前置依赖

- W0–W2：确认 `scFLOWpreAPI` 是否可从外部进程调用；确认本机 `scFLOWpre` 命令行/COM 暴露方式；确认 `scConverter` 对 X_T 的转换能力。
- W3–W5：MSVC 工具链与 C++ 桥原型；`scFLOWpreCmd` 类布局分析（可用导出符号 + 少量反汇编辅助）。
- W6–W8：OCCT（pythonocc）许可与安装；X_T 读取路线定型（scConverter / ParasolidGW / Datakit）。

---

## 6. 风险与对策

| 风险 | 等级 | 对策 |
|------|------|------|
| 商业二进制桥接的许可/合规风险 | 高 | 桥接仅在已授权 Cradle 环境使用；对外交付自研引擎 + OCCT；文档明示边界 |
| C++ 类 ABI 逆向成本高（MSVC 名字修饰、vtable 布局） | 高 | 优先用 `SCTprime` 的 C++ 自由函数（`CreateShapeGroupSet` 等）与 `scFLOWpreCmd` 的简单 setter；避免深度遍历 vtable；VBS/批处理作降级路径 |
| Parasolid X_T 读取无开源实现 | 中 | STEP/IGES/STL 全自研；X_T 走 scConverter/ParasolidGW 桥；长期评估 Datakit/商业 SDK |
| 网格算法与商业 mesher 差距 | 高 | v1 以桥接为“能用”，自研定位“可解释/可定制”，验收标准分两档 |
| 格式随版本漂移 | 中 | 黄金语料 + 字节级回归 + schema 版本化（SCTpre SDK 版本号已在样本中） |
| 大模型性能 | 中 | 惰性解析、缓存复用、分块 mmap、渲染上限（已有部分实现） |
| 样例不足导致语义误判 | 中 | W0 建立 30+ 语料库；每次语义修正必须新增黄金对照 |

---

## 7. 建议立即启动的动作（W0–W2）

1. 收集 5–10 个真实 PPH（不同网格组/单位制/项目类型），跑 `tests/test_samples.py` 建立基线；
2. 编写 `tools/extract_schema.py`，从样本 `main.xml/xenv/prp` + `scFLOWpreCmd` 导出符号生成条件/键/单位注册表；
3. 在 scFLOWpre 中录制 `history.vbs` 覆盖 Navigation 全部 24 项，验证“录制 → 回放”可行性；
4. 用 `SCTpreCLIHelper -h` 与本机程序目录确认 Windows 批处理路径（`scflowcomb2025`/`SCTpref`）；
5. 用 `ctypes` 加载 `scFLOWpreAPI`，验证 `ExecuteVBS` 是否可跨进程调用；不可则准备 pywinauto 方案；
6. 评估 pythonocc-core 安装（本机 Python 3.12/Anaconda 环境），确定 OCCT 路线。

---

## 附录 A：证据来源

- 本仓库：`README.md`、`DEV_SUMMARY.md`、`PPH_FORMAT_SPEC.md`、`tests/`（112 项）、`nav_panels.py`（12 类导航面板）、`pph_gui.py`（PphViewer/View3DTab）
- 手册：`Pre_eng`（476 页）、`Operation_eng`（294 页）、`Exercise_eng`（157 页），正文已抽取为语料 `%TEMP%\scflow_manual_corpus.txt`
- 导出表：`%TEMP%\scflow_exports\*.txt`（scFLOWpreCmd 11,001、SCTpreSolver 18,002、SCTprime 1,176、ParasolidGW 1,174、SCTpreCore 814、SCTpreLib 720 等）
- 程序字符串：`%TEMP%\scflow_exe_strings.txt`（VBScript 引擎、scFLOWpreAddin 接口）

## 附录 B：术语对照

| 术语 | 说明 |
|------|------|
| PPH | scFLOW 项目文件（ZIP 容器） |
| CRDL-FLD | gph/oct/mdl 共享的大端二进制格式 |
| MDL | 面片几何（part/ridge） |
| OCT | 八叉树（网格生成用） |
| GPH | 体网格 |
| sctsnapshot | 当前状态快照（CADThru 小端记录流） |
| PKBody3 | Parasolid 实体加密块（Blowfish-LE ECB） |
| BAM | Build Analysis Model（闭体识别/面片化） |
| CMB | 组合批处理文件（scflowcomb2025 输入） |
| FPH | scFLOW 字段输出文件 |
