# PPH 解析功能开发状态总结

> 更新日期：2026-08-09（新增第 6 节）｜ 仓库：`pphdecoding` ｜ 格式细节见
> [PPH_FORMAT_SPEC.md](PPH_FORMAT_SPEC.md)

## 1. 总体判断

**解析/解码方向已完整，写端已闭环，语义已钉死，共 82 项测试锁定**
（laptop 复杂样例 + box 最小样例）。上一轮排序的 6 个关键点（1=3.6、
2=3.3、3=3.4、4=3.2、5=3.5、6=3.1）已**逐个解决**并同步刷新本文档；
剩余工作收敛为两个长期项：

1. 收集更多真实项目样例，把"样例特定值断言"进一步升级为黄金文件对比
   （纯样本问题，非技术问题）；
2. Parasolid **完整实体几何还原**（B-rep）仍需要商业内核或长期逆向——
   本仓库已交付"传输流部分提取"（schema/字段名/实体类型）作为过渡能力。

## 2. 当前完整性：已解析的层面

| 层面 | 状态 | 说明 |
|------|------|------|
| 容器（ZIP） | ✅ 完整 | 成员分类、解包、写端 `clone_pph` round-trip 与参考目录逐字节一致 |
| 文本成员 | ✅ 完整 | `main.js` / `main.prp` / `main.xenv` / `main.xml` 均可解析；XML 方言索引标签 `<SECTITEM[0]>` 有 sanitize/还原机制；`serialize_main_xml` 支撑改后写回 |
| CRDL-FLD 公共层 | ✅ 完整 | gph/oct/mdl 共享的大端节扫描、记录迭代、元数据；`_valid_section_start` 防误判 |
| MDL 面片几何 | ✅ 完整 | part/ridge 的顶点、面（face_type 133/134 = npe 规则）、csid、frid、状态、区域；**双侧闭体语义已钉死** |
| OCT 八叉树 | ✅ 完整 | 前序位图、内部/叶子计数不变式、Morton 子序、叶子包围盒重建、深度统计 |
| sctsnapshot 快照 | ✅ 完整 | 小端记录流、失步 `_resync`、LZMS 解压（Windows cabinet.dll + **wimlib 跨平台回退**）、`OCTREEDIVISION`/`OCTREEREGION` 序列化序（box/laptop 100% 重放一致）、`OCTREEMDLBODY`、单位量 VWU/DPOINTU；**OCTREEREGION 语义已钉死** |
| 加密 | ✅ 闭环 | PKBody3 外层 → Blowfish-LE ECB 固定密钥 → Parasolid 二进制传输流；**PKBody3 包装布局已修正**（见 3.2），写端 `encrypt_pkbody3` 可逐字节复现原始密文 |
| 写端 | ✅ 闭环 | `pphwriter.py`：LZMS 压缩（Windows `CreateCompressor`）+ Blowfish 加密 + ZIP 容器；PKBody3/LZMS/XML 三路 round-trip 测试全过 |
| Parasolid 部分提取 | ✅ 已交付 | `parasolid.py`：文件头/版本/schema、schema 字段表（token+字段名）、实体类型（PKEdge/PKFace/PKVertex）、SDL 属性 |
| 平台与依赖 | ✅ 已解 | LZMS 解压非 Windows 回退 wimlib；gph 深度统计内置 `gphstats` 降级（不再依赖同级 gphdecoding 仓） |
| GUI 查看/修改 | ✅ 已交付 | `pph_gui.py`（PyQt5 + VTK OpenGL2）：成员树、文本编辑+另存写回、快照记录树、MDL/OCT/GPH 3D 视窗（限量渲染）；`pph_vtk.py` 几何构建器离屏可测 |
| 测试 | ✅ 通过 | 112 项测试全过（laptop + box + GUI/VTK 离屏），CLI 摘要正常 |

### GUI 2.0（scFLOW Pre 风格，2026-08-02）

- 参照 scFLOW Pre 手册（`CradleCFD2025.2/Manuals/scFLOW/HTML/Pre_eng`）
  重构界面：**Navigation Window**（工具按钮 + 文件信息卡片 + 分组导航树）、
  **Tree Window**（成员树 + 右键菜单）、**Property Window**（选中项解析
  属性）、**Draw Window**（3D：分组控制面板、着色/线框、网格线、剖面
  裁剪 X/Y/Z、橡皮框缩放、Fit/Reset、坐标指示器、Qt 图例）；
- 新增 **格式数据看板（Dashboard）**：归档/压缩率/GPH/OCT/MDL/快照/
  Parasolid 数据卡片（2×4 网格排布）+ 成员尺寸 Top12 条形图；>64 MiB
  大网格自动跳过深度统计（可手动刷新）；
- **3D 默认显示 + 模型显隐控制**：打开文件后默认进入 3D；视图类型
  （全部/仅几何 MDL/仅网格 GPH+OCT）；**模型树改用复选框 + 右键菜单**
  控制闭体/面区域显隐（取消勾选即从 MDL 掩码中隐藏），不再用单击/双击
  触发渲染；MDL/OCT/GPH 模型**缓存复用**（`View3DTab._cache`），勾选
  切换不重新解析；二进制成员单击只显示轻量属性，深度解析移至右键
  「解析属性（深度）」；**拾取面**（vtkCellPicker 点击 MDL 面隔离显示）
  + 恢复全部（联动模型树全勾选）；
- 测试：GUI 相关 30 项（含导航/属性/看板/线框/剖面/橡皮框/模型树复选框/
  显隐信号/面掩码/视图过滤/默认 3D/真实 View3DTab 信号绑定回归），
  全量 112 项通过。

主要模块：

| 模块 | 职责 |
|------|------|
| `pph_parser.py` | CLI + ZIP 容器 + 成员分类 + 摘要报告（含 Parasolid 提取摘要） |
| `crdlfld.py` | CRDL-FLD 公共二进制层（gph/oct/mdl 共享） |
| `mdl.py` | `*_part.mdl` / `*_ridge.mdl` 面片几何（csid 双侧闭体、frid、区域） |
| `oct.py` | `*.oct` 八叉树（前序位图 → 叶子包围盒重建） |
| `sctsnapshot.py` | 快照记录流 + LZMS（cabinet/wimlib）+ PKBody3 + OCTREERESTR 区域 |
| `blowfish_le.py` | PKBody3 Blowfish 小端变体 ECB（`blowfish_tables.py`） |
| `pphxml.py` | main.xml 方言净化/序列化、prp、xenv、js、unit_type→xenv 映射 |
| `gphstats.py` | 仓库内轻量 GPH 统计（gphdecoding 仓不可用时的降级路径） |
| `parasolid.py` | Parasolid 传输流部分提取（schema/字段名/实体类型） |
| `pphwriter.py` | 写端：LZMS 压缩 + Blowfish 加密 + ZIP 容器 round-trip |
| `pph_vtk.py` | VTK 几何构建器（MDL/OCT/GPH → vtkPolyData + 离屏渲染） |
| `pph_gui.py` | PyQt5 + VTK 查看/修改 GUI（依赖：`requirements-gui.txt`） |

## 3. 六个关键点的解决状态

### 3.0 版本审计：CradleCFD2023 = Parasolid V34.1（非 V35）

- ✅ 遍历 CradleCFD2023/Programs_x64 与 2023.2 官方案例（150 个 pph、99 个原生 x_t、24 个随案例 DLL）：pph 容器/快照/压缩链路与 2025.2 同族，全部可解析；运行期 PKBody3 全量解码 + 字节级 round-trip。
- ✅ **版本三通道确证 V34.1**：pskernel.dll FileVersion 34.01.153；Schemas 含 sch_34101；PKBody3 = modeller version 3401153 / SCH_3401153_34101_13006。案例 x_t 输入横跨 V22..V34（原建模器版本，非 scFLOWpre 版本）。MSCCTAssistant 自带 pskernel = V30.01。
- ✅ 导出集：2023 = 1350（1100 PK_*）⊂ 2025.2 = 1454（1204 PK_*），V37 新增 PK_BODY_slice / PK_FACE_ask_type 等 104 项；GW/wrapper DLL 不导出 PK_*。
- ✅ pskernel_abi.py：以 q-solid Parasolid_Docs_V35 手册（逐函数签名页）为语料做接口映射——V34.1 映射 1081/1100（98.3%），V37 映射 1101/1204（其余为 V35 之后新增）；含 PE 导出解析、签名解析、ctypes 原型生成、多版本差异报告。V34.1/V37 的 'A' 流二进制 XT 解码器跨版本验证通过（exA05 PKBody3 394 节点字节级 round-trip）。

### 3.05 版本审计补：CradleCFD2025.2 = Parasolid V37（新增导出逆向补充）

- ✅ 遍历 2025.2 程序与 2025.2 案例（151 个 pph、109 个原生 x_t/x_b、22 个随案例 DLL），pph/快照/PKBody3 链路全部可解析；案例 x_t 输入为原建模器版本（V22..V34 分布同 2023 集）。
- ✅ 版本三通道确证 V37：pskernel.dll FileVersion 37.01.153、Schemas 含 sch_37102、运行期 PKBody3 = modeller version 3701153。
- ✅ pskernel_v37.py：V35 手册未收录的 **104 个 V36/V37 新增 PK_*** 导出补充——家族归类（LATTICE 26 / PARTITION 14 / FRAME 10 / REGION 10 / TOPOL 10 / BODY/FACE/MARK/SESSION 等；49 个 _r_f + 1 个 _cb_r_f 变体）、反汇编参数推断（x64 入口首读/栈参数/字节参数，经文档化签名校准）、经验调用验证（PK_SESSION_ask_cellular_guise rc=0、guise=27110；FACE/REGION ask_type 等 cellular 家族函数因默认 modeling guise 返回 5022 门禁——签名形态已确认，待 cellular-guise 会话复核）、sch_34101-vs-sch_37102 节点类型演进 （新增 SKEWBOX/TPMS_SURF/IMPLICIT_SURF/IMPLICIT_VOLUME/PATTERN_* /LATTICE_DATA_PATTERN 8 型）。
- ✅ **完整签名补全（pskernel_v37_sigs.py）**：四层手段收敛为 104 个导出的 C 签名表（15 high / 89 med），_r_f 变体 = 基参数 + PK_FRUSTUM_t *frustrum（PK_GEOM_copy vs _r_f 反汇编钉死），PK_MARK_create_r_f 的基函数映射到 PK_MARK_create_2（命名去 _2）；全表渲染于 docs/V37_SIGNATURES.md。

### 3.1（原难度 6）Parasolid 实体几何：部分提取已交付，完整还原仍为长期项

- ✅ 已交付：parasolid.py 传输流解析/编码——文件头
  （TRANSMIT FILE created by modeller version 3701153）、schema 标识
  （SCH_3701153_37102_13006）、实体类型与 SDL 属性。
- ✅ **P2 二进制 XT 全量解码/编码（本批）**：parse_binary_xt /
  encode_binary_xt 闭环，parse→encode 字节级一致；支持 'A'（CADthru
  frustrum，u32 index/指针/n_elts）、'B'（bare binary）、'PS'（neutral/
  typed）三种 flag。已钉死（XT Format Reference 2.1/3.3 + kernel 产物
  对拍）：指针/正整数 = 小值存 v+1、大值 pair；编辑序列 n_elts = 正整数
  编码（B）或 u32（A）；节点 index 同指针编码；变长节点 varlen 在 index
  之前、变长字段无额外计数；未设哨兵 -32764/-3.14158e13 → None；
  terminator = type 1 + NULL 指针编码 index 0。box PKBody3（A 流）159 节点
  全量解码（BODY/8 VERTEX/12 EDGE/6 FACE + 几何 + SDL 属性全结构），
  kernel 同体 B 产物 87 节点与文本 ground truth 按 node_id 全字段一致；
  此前"后段标量失步"根因 = 编辑序列 n_elts 误按 u32、指针/索引未按 +1
  偏移、varlen 与 index 顺序颠倒。'A' 与 'B' 对同体节点标签可不同（kernel
  文本传输再索引），node_id 与连接关系不变。
- ✅ 旧"schema 字段表"之谜已解：scan_fields 扫到的 22 字段帧 = BODY
  编辑序列中 I/A 操作的字节（field_data_offsets 的值 = 各字段的
  ptr_class），非独立数据区。
- ❌ 未解（长期）：与内核等价的语义级 B-rep 重建（boolean/造型 API 语义）
  仍依赖 Parasolid 内核；用户手册中未公开的 CADthru 扩展字段（finger_* /
  frame / legal_owners 等）语义未逐一钉死。

### 3.2（原难度 4）语义钉死：CsidOfFaces / OCTREEREGION / PKBody3 末块

- ✅ `LS_CsidOfFaces` = 双侧闭体 `(volA, volB)`，`0` = 外部：
  - laptop part：`b2 = frid + 1` 精确一一对应（frid 0..3 ↔ b2 1..4）；
  - laptop ridge：体间界面面 `(2,1)` × 412,644（两侧均非零）；
  - `LS_MdlClosedVolumes` 记录数 = `max(b2) + 1`（box 2 / laptop part 5 /
    laptop ridge 3），记录 0 = 外部。
- ✅ `OCTREEREGION`：重映射到 oct 前序后 `flag=1` **全为叶子**，集中在
  最深细化层（box：883/1968 叶子、深度 4–5、y∈[0,0.011] 上半精化板；
  laptop：3,445,907/3,465,218 叶子、深度 14–20、转子薄柱）；区域索引
  与 `OCTREERESTRRGN` / MDL frid / csid-1 同空间
  （laptop：open=0、case1=1、rotation1=2、impeller1=3）。
- ✅ `OCTREERESTR`：`OCTREERESTRRGN` = `(kind, index, enabled, …)`；
  box 4 个全空，laptop meshing group 含 4 区域。
- ✅ **PKBody3 包装布局重大修正**：`size` 是逻辑长度，物理密文占
  `ceil8(size)`，**没有独立的 pad/尾标字段**。历史上观察到的
  `0x17DA2940`"尾标"实为固定密钥下 `E(0^8) = e5 e4 e5 b1 40 29 da 17`
  的低 32 位（仅当 `size % 8 != 0` 时出现），`0xB1`"pad"是零填充块密文
  的第 `size` 字节。`PKBody3.parse` 已按新布局修正，`decrypt()` 现返回
  精确明文；写端再加密可逐字节复现。

### 3.3（原难度 2）次要缺口

- ✅ 快照 48 字节保留区：位于 `CSINFO→PBODYARRAY` 之间，4 个数据点均
  固定 48B，内容为旧序列化流残留或未初始化垃圾，**不承载当前状态语义**
  ——降级为"已知对齐填充"闭合。
- ✅ `main.xml` 索引标签：`sanitize_scflow_xml` 正则已修复（原未吞标签
  闭合 `>`，会向文本注入多余字符）；`serialize_main_xml` 与 sanitize 互逆，
  "改 XML → 写回 pph → 重解析"round-trip 测试通过。
- ✅ `unit_type`：`1 → MODEL_LENGTH_UNIT` 映射已建立
  （`pphxml.UNIT_TYPE_TO_XENV_KEY` / `resolve_snapshot_unit`）；其余码值
  待多单位制样例。

### 3.4（原难度 3）平台与依赖限制

- ✅ LZMS 解压跨平台：Windows 优先 `cabinet.dll`，非 Windows 回退
  **wimlib**（支持 ≥1.14 的 `wimlib_create_decompressor` +
  `wimlib_decompress_with_decompressor`，兼容 1.13 一次性
  `wimlib_decompress`；`WIMLIB_COMPRESSION_TYPE_LZMS = 3`）。流必须从
  偏移 0 整体解压（已确认 err=605 约束）。
- ✅ gph 深度统计不再依赖同级 `gphdecoding` 仓：新增 `gphstats.py`
  内建轻量统计（LS_Links 面/单元/边界面/npe、LS_Nodes 顶点、区域、
  Parts），box 样例与 gphdecoding 输出逐项一致
  （3168 面 / 944 单元 / 600 边界面 / 1305 顶点）。
- ⚠️ 残余风险：本机未安装 wimlib，wimlib 路径经 mock 测试验证调度逻辑，
  真实库上的格式兼容需在装有 wimlib 的机器上确认（LZMS 块格式与
  Windows 一致，风险低）。

### 3.5（原难度 5）写端整体缺失

- ✅ `pphwriter.py` 已交付：
  - `lzms_compress()`：Windows `CreateCompressor(LZMS)`，输出与样本同构
    的 28 字节头 + 负载流，可被读取端 `ZipBlob.parse` / `lzms_decompress`
    直接消费；
  - `encrypt_pkbody3()`：Blowfish-LE ECB + `CADthru/PKBody3` 包装（修正后
    布局），对解密结果再加密**逐字节一致**；
  - `clone_pph()` / `rewrite_pph()`：ZIP/deflate 容器读改写，支持
    main.xml 修改后写回。
- ✅ round-trip 测试：LZMS 压缩→解压、PKBody3 加密→解密、ZIP 克隆、
  XML 改后重解析、完整"解压→解密→加密→再压缩→再解压"闭环。
- ❌ 未做：sctsnapshot 记录流的字节级重序列化（解析器不保留原始负载
  字节），以及 SCTpre 对改写文件的实测验收（需要图形界面/许可环境）。

### 3.6（原难度 1）验证覆盖局限

- ✅ `tests/test_samples.py`：跨样例结构不变式扫描器（自动发现
  `tests/**/*.pph`），覆盖容器角色、网格组一致性、Oct 不变量、MDL
  CSR/csid/frid 不变量、快照/嵌套块/分割/区域不变量。
- ✅ `tests/test_semantics.py`：把 3.2 的语义钉死固化为断言
  （csid 双侧、OCTREEREGION 几何、PKBody3 末块）。
- ⚠️ 剩余：仍只有 laptop + box 两个样例；多网格组、`unit_type≠1`、
  其他 pad/尾标变体属于"未验证"而非"已验证失败"。

## 4. 剩余关键点难度排序与可行性分析（2026-08-02 更新）

排序依据：解决难度（★ 低 → ★★★★★ 极高）、可行性、投入与前置依赖。

| 排序 | 关键点 | 难度 | 可行性 | 预计投入 | 关键路径 |
|----|--------|------|--------|----------|----------|
| 1 | 扩大样例集并建立黄金文件对比（3.6 收敛） | ★★☆ | 高 | 数天–数周（取决于样例获取） | 收集真实项目 pph；把样例特定值断言升级为结构断言 + 黄金对比 |
| 2 | wimlib 真实库验证（3.4 残余） | ★☆☆ | 高 | 半天–1 天 | 在装有 wimlib 的 Linux/WSL 上跑 `lzms_decompress` 实测 |
| 3 | sctsnapshot 字节级重序列化 + SCTpre 验收（3.5 残余） | ★★★☆ | 中–高 | 数周 | 保留记录原始字节的序列化器；SCTpre 实机验收 |
| 4 | 多单位制样例补全 `unit_type` 码表（3.3 残余） | ★★☆ | 高 | 数天 | 用 SCTpre 建 mm/inch 项目对照 main.xenv UNIT |
| 5 | Parasolid 完整 B-rep 还原（3.1 残余） | ★★★★★ | 低（独立）/ 中（商业组件） | 数月–长期 | 商业 SDK（OCCT Import / Datakit / CAD Exchanger）或超长逆向 |

### 逐项分析

**① 扩大样例集（建议最先做）**

- 本质是**样本问题而非技术问题**：解析器结构已被 82 项测试锁定，
  剩余不确定性全部来自"没见过更多变体"。
- 路径：收集不同规模/单位制/网格组的真实 pph，跑 `test_samples.py`
  自动扫描 + 逐字节黄金对比。

**② wimlib 真实库验证**

- 代码路径已就绪（新旧两套 API 分派），缺一台有 wimlib 的机器做
  端到端解压验证；LZMS 流格式与 Windows 完全一致，风险低。

**③ sctsnapshot 重序列化**

- 解析器把叶子存为"值"而非原始负载字节；若要字节级改写快照，需在
  解析时保留原始记录字节，或按 DLL 写入端序列化序重建
  （`OCTREEDIVISION`/`OCTREEREGION` 的写入序已逆向，是重要前置）。
- 风险：SCTpre 对字节级细节敏感，验收成本高。

**④ unit_type 码表**

- 用 SCTpre 建不同单位制项目，对照 `main.xenv` UNIT 键建立全量映射；
  低风险，样例驱动。

**⑤ Parasolid 完整还原**

- 本仓库已交付部分提取（schema/字段名/实体类型），满足轻量互操作；
- 完整 B-rep 需决策是否采购商业组件；自研逆向以月–年计，风险极高。

## 5. 建议的下一步

1. **收集样例**：3–5 个真实项目 pph（不同网格组/单位制/几何复杂度），
   跑跨样例扫描并沉淀黄金文件——同时收敛 3.6、3.3、3.2 的残余项。
2. **wimlib 实测**：在有 wimlib 的环境跑一次跨平台解压测试，闭合 3.4。
3. **写端进阶**：从"成员级重写"推进到"sctsnapshot 记录级重写"，用
   SCTpre 实测验收（3.5 残余）。
4. **Parasolid 决策**：评估商业组件 vs 自研（3.1 残余，长期）。
5. **GUI 实测**：在带 GPU 的桌面会话运行 `python pph_gui.py`，验证 VTK
   OpenGL 加速渲染与真实窗口交互（离屏测试已覆盖构建与逻辑，未覆盖
   实际像素输出）。

测试：`python -m pytest tests -q`（91 项，约 68 s；laptop 样例解析较慢）。
GUI 运行：`python pph_gui.py [项目.pph]`；依赖缺失时
`python -m pip install -r requirements-gui.txt`。

## 6. scFLOWpre 宿主自动化：沙箱排查结论与 COM 激活分析（2026-08-09）

> 相关代码：`automation/host_pipeline.py`（in-proc COM 桥 + 宿主内 VBS）、
> `automation/vbs_bridge.py`、`automation/batch_bridge.py`、
> `native_bridge.py`。本节固化沙箱内 scFLOWpre 宿主排查的最终结论，
> 以及"回到正常桌面会话后是否需要解决 COM 激活问题"的分析。

### 6.1 沙箱排查结论：宿主无法在本环境稳定运行

- ❌ **直接启动 `scFLOWpre_Bx64net.exe` 必崩**：多份错误报告栈完全
  一致——`KERNELBASE.RaiseException(0xE0000000)` ←
  `SCTpreLib_Dx64.dll!SetupSCTpreLib()+0x21` ←
  `scFLOWpreCmd_Bx64net.dll!InitializescFLOWpreCmd()+0x557` ←
  `scFLOWpreGUI_Bx64net.dll!scFLOWpreAddin_Initialize()` ← exe 主流程。
- ✅ **根因已逆向钉死**：`SetupSCTpreLib`（RVA 0x4847B0）逻辑为
  `call 0x1800531E0; test eax,eax; je RaiseException`；其内部初始化子步骤
  （0x2E2D60 等）在独立进程中按序直接调用时访问违例/返回 0，说明依赖
  **Kicker 启动时注入的进程级状态**（license mode / product key），
  直接启动 exe 不是受支持路径。
- ✅ **手册佐证**（`Manuals\scFLOW\HTML\VB_Interface_eng\`）：
  Application 对象的文档化获取方式是
  `CreateObject("scFLOWpre_Bx64net.Application.2025")`；Application 类
  提供 `ExecuteVBS / ExecuteVBSWithFile`（宿主内脚本通道，正是本仓
  NativeBridge 想走的路）；Kicker 类负责许可证检出与启动设置
  （`GetLicenseStatus / GetApplicationLaunchSetting / SetProductType`）。
- ✅ **许可证因素已排除**：`CRADLE_LICENSE_FILE=27891@localhost` 指向
  未监听端口；实际许可证服务器 localhost:27500 在线（lmstat：SCFLOWPP
  32 许可、0 占用）。把变量改指 27500@localhost、license.dat、或删除
  变量后重试均同样崩溃 → 不是"服务器不可达"，而是 Kicker 注入的
  进程状态缺失。
- 三个现象由此全部归因：「Warnning」框 = SetupSCTpreLib 抛出的自绘
  错误报告对话框；主窗口消失 = 错误框确认后应用退出；**COM LocalServer
  激活挂起** = 激活出的新实例卡在同一个模态错误框上，COM 永远等不到
  类工厂注册完成。沙箱无稳定交互桌面会话（Kicker 窗口在本会话也会
  消失），无法在本环境继续验证。

### 6.2 COM 激活分析：不需要"解决"，需要"规避"

**注册表实测**（本机，HKLM）：`scFLOWpre_Bx64net.Application.2025`
→ CLSID `{6FDA4768-C96A-478C-BCE1-96B2216D99E8}` →
`LocalServer32 = C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\scFLOWpre_Bx64net.exe`
——即外部 `CreateObject` 激活**必然拉起不经 Kicker 的裸 exe**，这是
结构性事实，与沙箱无关。

分路径结论：

| 路径 | 是否涉及 LocalServer 激活 | 结论 |
|------|--------------------------|------|
| A. Kicker 启动宿主 → 宿主内 File → Execute VBScript（当前 `--write-vbs` + manual 主路径） | 否 | **无需解决** |
| B. 外部脚本驱动 `app.ExecuteVBSWithFile`（后续全自动化目标） | 取决于 `app` 的获取方式 | **不需"修"，需"绕"**（见 6.3） |

沙箱挂起三因素中哪些会跟到原生桌面：

1. **LocalServer32 直指裸 exe（会跟到原生）**：按 6.1 的逆向结论，
   原生机器上 COM 激活出**新实例**大概率复现同样的 0xE0000000 崩溃；
2. **模态框无人确认 → 永久挂起（沙箱特有）**：原生上表现为激活
   失败/超时返回而非死等，可诊断性好，但激活本身依然失败；
3. **交互桌面会话不稳、Kicker 窗口消失（纯沙箱特有）**：原生不存在。

路径 A 免疫的机理（对照 `host_pipeline.py` 生成的 VBS）：
`GetApplication()` 是宿主 VBS 引擎内建函数，直接返回宿主自身对象，
不触发任何激活（116 行的 `CreateObject(...Application...)` 只是兜底，
宿主内正常走不到）；`CreateObject("pphdecoding.ScflowPipeline")` 是
**InprocServer32**（`--register` 注册到 HKCU），DLL 加载进已初始化好的
宿主进程，`SetupSCTpreLib` 早已完成，不存在状态缺失问题。

### 6.3 原生桌面验证清单（按序执行）

1. 经 **Kicker** 正常启动宿主（不要直接启动裸 exe）；
2. `python -m automation.host_pipeline --register` +
   `--write-vbs host_pipeline.vbs --project <pph>`，宿主内
   File → Execute VBScript 执行 → 验证结果文件
   `context_ready=True`、`set_handle / group_handle > 0`、`mdl=True`
   （此步完全不碰 COM 激活）；
3. 外部脚本试 `GetObject(, "scFLOWpre_Bx64net.Application.2025")`
   **ROT 附加**（前提：宿主把 Application 注册进 ROT，需实机确认）；
4. 再试 `CreateObject`：若类工厂注册为 MULTIPLEUSE 且已有实例在跑，
   激活会直接附加到运行中进程——对比激活前后
   `Get-Process scFLOWpre_Bx64net` 的 PID 数即可判断是"附加"还是
   "拉新进程崩溃"；
5. 若 3、4 均不可行，放弃外部 COM 驱动：求证 `vbs_bridge.py` 中
   `-vbs` CLI 参数是否真实存在（代码标注"待实机确认"），或停在
   "Kicker 启动 + GUI 菜单后端"的半自动方案。

### 6.4 代码层待修隐患（原生实测前建议处理）

- ⚠️ `host_pipeline.py:116`：VBS 内的 `CreateObject` 兜底若被
  wscript/cscript 在**宿主外**执行，会触发 LocalServer 激活 → 原生上
  同样崩。建议加注释"仅限宿主内执行"，或删掉兜底让错误显式暴露；
- ⚠️ `host_pipeline.py:_run_gui`（约 236 行）：无进程时直接
  `Application.start(exe)` 拉起裸 exe，同样绕过 Kicker。gui 后端应
  改为"要求先经 Kicker 启动实例在跑"，否则复现同样崩溃。

## 7. 功能完整度对照结论（vs scFLOWpre，2026-08-16）

> 完整分析含功能域完整度对照图与模块交叉表，见
> [function_gap_analysis.md](function_gap_analysis.md)；改进计划（P0–P3）
> 见 [DEV_PLAN.md](DEV_PLAN.md) §17。本节为状态快照结论。

**总体判断：项目呈「底层强、上层弱」的哑铃结构。**

- **生产级（80–95%）**：PPH 解析/写端、.oct/.gph/.mdl 写端、Parasolid
  内核直调（facet/boolean/transform/B-rep 全闭环）、Select/View/3D
  （真 VTK 拾取 + 橡皮框选，仅 11 项 NYI 灰显）、Register Region
  （真写 main.xml）；
- **中间层（55–70%）**：BAM（API 模式录制锁定 + 实测 err=0；原生 12/12
  步对齐但缺容差合并/Influence）、Octree（参数链路实测达标）、宿主自动化
  （主链路三份日志 err=0；in-proc COM 桥未实测、外部 COM 被 LocalServer
  结构性阻塞）；
- **差距层（10–30%）**：条件体系（**~180 个 Cond\* 仅 5 个粗桩**，最大
  差距）、自研网格（voxmesh/polymesh 双 MVP，无 2:1 平衡/质量度量/区域
  映射）、几何编辑（Create/Modify 为 TODO 草稿，**底层算子已生产级只欠
  接线**——性价比最好的改进点）、Wrapping（录制锁定未实机执行）、
  Solver/FPH（明确延后，合理）。

GUI 壳层完成度高（112/123 菜单项接线），但部分「接线」背后是 VBS 草稿
或 session 存根，深度不及表面；差距排序与 P0–P3 改进计划以
DEV_PLAN §17 为准（P0 = 实机验证收尾 + 几何编辑接线；P1 = 条件表单
schema-driven 系统化；P2 = 网格质量基础设施；P3 = 深度对齐与长尾）。

**P0–P3 执行结果（2026-08-16 收尾）：计划全部落地，全量回归
549 项测试全绿**（`run_all_tests.py` 逐模块子进程隔离；0 失败 /
0 崩溃 / 3 skipped，实机桥用例 `SCF_RUN_BRIDGE_TESTS=1` 门控）。
上述哑铃结构已明显收敛：

- **条件体系**（原差距 #1）：~180 个 Cond\* 类型经
  condition_registry 元数据推断 + GenericCondBody 通用表单全覆盖，
  XML 写回闭环（含 empty/composite 必填形态）；
- **几何编辑**（原差距 #3）：Create/Modify Parts 原生模式落地
  （geometry_ops.py：block / boolean / transform / face_delete
  写回 PPH），TODO 草稿清零；
- **网格质量**（原差距 #2/#7 的质量侧）：voxmesh 2:1 平衡 + pairing +
  面区域映射、polymesh 体积质心 Lloyd、quality.py 非正交度/偏斜度
  统计；
- **NYI 菜单**：11 → 8（Select by Element Number / Same Area /
  Check Intersection 已本地实现）。

剩余长尾：Disc / Overset 录制锁定、样例集黄金文件对比、
余 8 个 NYI 菜单、in-proc COM 桥原生桌面门控实测。
逐项交付证据表见 [function_gap_analysis.md](function_gap_analysis.md)
§4。
