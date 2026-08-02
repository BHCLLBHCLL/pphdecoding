# PPH 解析功能开发状态总结

> 更新日期：2026-08-02 ｜ 仓库：`pphdecoding` ｜ 格式细节见
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
| 测试 | ✅ 通过 | 91 项测试全过（laptop + box + GUI/VTK 离屏），CLI 摘要正常 |

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

### 3.1（原难度 6）Parasolid 实体几何：部分提取已交付，完整还原仍为长期项

- ✅ 已交付：`parasolid.py` 轻量传输流解析——文件头
  （`TRANSMIT FILE created by modeller version 3701153`）、schema 标识
  （`SCH_3701153_37102_13006`）、**schema 字段表**（22 个字段：
  `lattice`/`mesh`/`polyline`/`owner`/`boundary_*`/`index_map*`/
  `child`/`lowest_node_id`/`mesh_offset_data`/`finger_*`/`frame`/
  `legal_owners` 等，含类型 token 与流内位置）、**实体类型**
  （`CADthru/PKEdge` / `PKFace` / `PKVertex`）与 SDL 属性
  （`SDL/TYSA_NAME` / `LAYER` / `UNAME`）。5 个实测体全部可解析。
- ❌ 未解：完整 B-rep 拓扑/几何还原仍需要 Parasolid 内核
  （商业 SDK / 长期逆向）；字段表的完整记录帧（含数据区偏移）仅部分
  理解，未作为 API 承诺。

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
