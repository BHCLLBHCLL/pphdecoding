# PPH 项目文件格式说明（逆向工程）

> 目标：完整描述 Cradle scFLOW 项目文件 `.pph` 的容器与全部成员格式，
> 支撑导出转换与文件互操作。分析样例：
> - `tests/laptop_thermal_steady_scaled_v3_fanonly_simple.pph`（复杂风扇模型）
> - `box.pph` / `tests/box/`（0.01×0.01×0.01 立方体 + `open` 边界，最小几何）
> （scFLOW 2025，SCTpre SDK 5225.20302.20251223）。

## 1. 容器格式：ZIP 归档

`.pph` 是**标准 ZIP 归档**（`PK\x03\x04` 魔数），成员使用 method 8
（deflate）写入；实测小成员的 deflate 流实际为 stored 块（压缩率≈0），
压缩后大小 ≈ 原始大小 + 5 字节块头。任何 ZIP 工具（Python `zipfile`、
7-Zip 等）均可直接解包。

成员清单与角色（按存储顺序）：

| 成员 | 角色 | 格式 |
|------|------|------|
| `main.js` | 用户子程序脚本 | 文本（JavaScript，`//@FormattedScript` 段） |
| `main.prp` | 材料物性数据库 | 标准 XML（`<property><group><entry>`） |
| `main.sctsnapshot` | 当前状态快照 | **CADThru 小端记录流**（§6） |
| `main.xenv` | 环境/单位/容差 | 标准 XML（UTF-8 BOM，`Section/Key`） |
| `main.xml` | 项目定义（前处理全部设置） | **scFLOW XML 方言**（§5.1） |
| `<组名>.gph` | 体网格 | CRDL-FLD 大端（见 gphdecoding 仓） |
| `<组名>.oct` | 八叉树 | CRDL-FLD 大端（§4） |
| `<组名>_part.mdl` | 显示/零件面片几何 | CRDL-FLD 大端（§3） |
| `<组名>_ridge.mdl` | ridge 细节面片几何 | CRDL-FLD 大端（§3） |

> 网格组名即 ZIP 内文件前缀（本例 `meshinggroup1`）。多网格组项目
> 会有多组 `.gph/.oct/_part.mdl/_ridge.mdl`。

## 2. CRDL-FLD 公共二进制层（GPH/OCT/MDL）

三种二进制成员共享同一容器格式（与 gphdecoding 仓 GPH 一致）：

- 文件头：`[I4=8]["CRDL-FLD"][I4=8][I4][I4][I4]`（三个 I4 观测为 4,4,4），
  之后是命名节序列。
- **全部大端序**。
- 命名节：`[I4=32][名称 32B ASCII，空格填充]` + 记录流。
- 记录流元素：
  - 描述符：`[I4=12][type][dim0][dim1]`；type 4=I4、8=R8/C1。
  - 数据块：`[I4=12][byte_count][payload][I4=byte_count]`（尾部哨兵=块长）。
- 通用元数据节：`FileRevision`（如 2025）、`Application`（"SCTpre"）、
  `ApplicationVersion`、`ReleaseDate`、`GridType`、`Dimension`、`Bias`、
  `Date`、`Encoding`、`UnitOfCoordinates`（f64 缩放 1.0 + 单位串 'm'）、
  `HeaderDataEnd` / `OverlapStart_0` / `OverlapEnd`（40 字节空标记节）。

> **解析陷阱**：32 字节 ASCII 字符串数据块（如单位串 `'m'+空格`）与节头
> 字节层面同构（`[I4=32]+可打印ASCII`）。通用节扫描必须校验后继内容
> （记录流 `[I4=12]` / 下一节头 / 文件尾），否则会把字符串块误识别为节
> （本仓 `crdlfld._valid_section_start` 已实现该校验）。

## 3. MDL 面片几何（`*_part.mdl` / `*_ridge.mdl`）

节序（两文件相同）：

| 节 | 内容 |
|----|------|
| `LS_CoordinateSystem` | 坐标系 id（描述符链，观测 0） |
| `LS_Nodes` | 顶点坐标：3 个等长 R8 块，X/Y/Z 轴块布局（同 GPH LS_Nodes） |
| `LS_Faces` | 面片：`face_type I4[n_faces]` + `conn I4[Σnpe]`（CSR，0-based） |
| `LS_CsidOfFaces` | 两个 `I4[n_faces]`：面两侧闭体 id（b1 全 0=外部，b2 ∈ 1..N） |
| `LS_FridOfFaces` | 两个相同 `I4[n_faces]`：面区域 id（frid ∈ 0..3） |
| `LS_EdgeStateOfFaces` | `U1[Σnpe]` 每半边状态（1=ridge/特征边） |
| `LS_StateOfNodes` | `I4[n_vertices]` 顶点状态（1=特征点） |
| `LS_MdlClosedVolumes` | 闭体表：255B 名称块 + 描述符链（末值=体索引） |
| `LS_MdlVolumeRegions` | 体区域名（FluidRegion）+ 种子点 R8[3] |
| `LS_MdlSurfaceRegions` | 面区域名 + 描述符链（末值=frid），ridge 版可附 I4 列表 |

**face_type 类型码**（关键发现）：

- `133` = 三角形（3 顶点），`134` = 四边形（4 顶点），即 `npe = type - 130`。
- 验证：part.mdl 全 133（43,766 面 × 3 = 131,298 = conn 长 ✓）；
  ridge.mdl 35,114×133 + 774,943×134（Σ = 3,205,114 = conn 长 ✓）。
- CSR 索引：`face_offsets[0]=0`，`offsets[i+1]=offsets[i]+(type[i]-130)`。

样例规模：`_part.mdl` = 21,889 顶点 / 43,766 面（显示用抽稀面片）；
`_ridge.mdl` = 792,506 顶点 / 810,057 面（全细节 ridge 面片）。

`LS_MdlSurfaceRegions` 的 frid 与 `LS_FridOfFaces` 对应
（观测：open/air_domain=0, case1=1, rotation1=2, impeller1=3）；
`@PartSurface_*` 为自动生成的部件表面区域。

## 4. OCT 八叉树（`*.oct`）

节序：

| 节 | 内容 |
|----|------|
| `Application`/`Dimension`/`Date`/`UnitOfCoordinates` | 常规元数据 |
| `LS_CoordinateSystem` | 坐标系 id |
| `LS_OctLastGenYear` | 最近生成年份（0=未知） |
| `LS_OctRootOctantMinMax` | 根包围盒 `R8[6]` = (xmin,ymin,zmin,xmax,ymax,zmax) |
| `LS_OctOctantRefinement` | `U1[n]` 前序位图（见下） |
| `LS_OctOctantBlockID` | `I4[n]` 块 id（本样例全 -1） |

**八叉树编码（LS_OctOctantRefinement）**：

- 按**深度优先前序遍历**存储，每节点 1 字节：
  `1` = 内部节点（被细分，其后紧跟 8 个子节点），`0` = 叶子。
- 完整八叉树不变量：`n = 1 + 8 × count(1)`。
  样例：n=3,960,249，count(1)=495,031，`(n-1)/8 = 495,031` ✓。
- 几何重建：从根包围盒出发，内部节点将包围盒三轴二分，
  子节点 0..7 按 Z 序（Morton）展开（bit0=x, bit1=y, bit2=z；
  bit=0 取低半区）。`oct.OctModel.iter_leaves()` 已实现。
- 样例统计：叶子 3,465,218，深度 2..20（直方图见测试）。

> **与快照关系**：同内容亦嵌在 `main.sctsnapshot` 的 `ZIPOCTREE`→
> `OCTREEBODY`→`BYTEARRAY` 中（字节级一致，见 §6.3.2）。ZIP 成员 `.oct`
> 可视为该块的抽出副本。

## 5. 文本成员

### 5.1 `main.xml` — 项目定义（scFLOW XML 方言）

根元素 `<scFLOWpre>`，顶层节：
`version / sctpresdk_major_version / sctpresdk_version_date / date /
project / parts / regions / reference_points / tables / multi_yaxis_tables /
local_coords / mapping_conditions / conditions / adaptive_param / state`。

**方言陷阱**：包含索引标签 `<SECTITEM[0]>`、`</SECTITEM[0]>`，
标准 XML 解析器报错。`pphxml.sanitize_scflow_xml` 将 `TAG[N]` 改写为
`TAG__IDXN`（索引可用 `restore_index` 还原），之后可用 ElementTree 解析。

内容：网格组（parts/meshinggroup）、流体/体/面区域（regions）、
边界条件与求解控制（conditions：CondBoundaryFlowIO 等 23 项）、
自适应网格参数（adaptive_param）、GUI 状态（state：视图矩阵等）。

### 5.2 `main.prp` — 材料物性库

标准 XML：`<property version date><group><key/><name/><entry>...`。
本例 30 个 group（gas/liquid/solid 等），entry 下为物性键值
（density、viscosity、conductivity……）。

### 5.3 `main.xenv` — 环境设置

UTF-8 BOM 的标准 XML：`<Data type="env"><Section name><Key name>值`。
13 个 Section：`TYPE`(PROJECT_TYPE=scflow)、`CAD`、`UNIT`（127 个单位键）、
`PART`、`PROJ_SETTING_FILE`（如 `PROJECT_GPH_COMPRESSION_TYPE=NONE`）、
`MESH_COMMON`、`TOLERANCE`、`TINYFACE`、`RIDGE`、`FACET`、`OCT_MESH`、
`MESH`、`MSC_COSIM`。

### 5.4 `main.js` — 用户子程序脚本

JavaScript 文本。`//@FormattedScript` 注释分隔的函数模板
（`usr_input`、`usr_adaptive_mesh`、`usr_dyna_exforce` 等 313 个）。
本例全部为空模板（无用户实现）。

## 6. `main.sctsnapshot` — 状态快照（CADThru 记录流）

SCTpre 的 CAD/网格内核（CADThru，基于 Parasolid）状态序列化。
与 CRDL-FLD 相反，**全部小端序**。

### 6.1 记录语法

```
record := TAG[16] (ASCII，空格填充) + LEN (u32le) + PAYLOAD[LEN]
```

- 容器标签：`*STRUCT`、`ASSEMBLY`、`BODY`、`BYTEARRAY`、`WRAPBYTEARRAY`、
  `QUEUEBODY`、`FACEGROUPSW`、`FACEGROUPW`、`FACEINFOMAP`、`EDGEINFOMAP`、
  `VERTEXINFOMAP`、`FFREVERSEMAP`、`STRINGARRAY(W)`、`DUMMYASSYINFO`、
  `BSGSEX` 等——负载即子记录序列。
- 标量：`INTEGER`/`BOOL`/`*NUMBER`/`PKBODY_T` 等（i32，LEN=4）、
  `DOUBLE`（f64，LEN=8）。
- 字符串：`STRING`（UTF-8）、`STRINGW`/`NAMESTRINGW`（UTF-16LE）、
  `LOCATIONSTRING`（字节串，内容形如 `"0,0,"` 路径）。
- 数组：`INTARRAY`（i32）、`DOUBLEARRAY`（f64）、
  `TRANSFORMMATRIX`（16×f64 = 4×4 变换矩阵）、
  `FACESTATES`/`EDGESTATES`/`VERTEXSTATES`（u16）、
  `FIDPKFACE`/`EIDPKEDGE`/`VIDPKVERTEX`（i32，Parasolid 实体 id）、
  `EDGEISSEAMLINE`（u8）。
- `*INFOLEN/*LENGTH` + `ZEROLENGTH(2)` 计数：`VERTEXSTATESLEN=8,
  ZEROLENGTH=1, VERTEXSTATES[14B]` 表示 8 项中尾部 1 项为零被省略，
  实际存 7×u16。
- **带单位量**（DLL `ValueWithUnit` / `DPointU` XML 模板确认）：
  - `MESH_CHORDTOL` / `MESH_CHORDANG` / `MESH_SURFTOL` / `MESH_SURFANG`：
    各 **8 字节 `f64le`**（面片弦高/角度容差；本例均为 `0.0` 未设）。
  - `LENGTHVWU`（及同类 `*VWU`）：**12 字节 = `f64le value` + `i32le unit_type`**
    （本例 `unit_type=1`；可读样例值如 `0.02345`）。
  - `DPOINTU`：**36 字节 = `3×f64le` 坐标 + `3×i32le` 各轴单位类型**
    （值在前、类型在后；与 XML 叙述的 Type/Value 顺序相反。本例类型均为 1；
    部分槽位坐标未初始化呈垃圾浮点，过滤 `|c|<1e3` 可得有效点）。

### 6.2 顶层结构（本样例）

| # | 记录 | 含义 |
|---|------|------|
| 1 | `CADTHRUVERSION`=8, `TREESTRUCT` | GUI 树状态（QUEUEID=113 'TreeState'） |
| 2 | `CADTHRUVERSION`=8, `VIEWSTRUCT` | 视图状态（QUEUEID=112，DOUBLEARRAY 18×f64） |
| 3 | `CADTHRUVERSION`=3, `TOPASSYSTRUCT` | 顶层装配 + Parasolid 体 |
| 4 | `TOPASSYSTRUCT` | 八叉树装配（"laptop_3d_geom Octree" + `ZIPOCTREE`） |
| 5 | `BSGSEX` | BodyShapeGroups：网格组/八叉树参数/区域加密限制 |
| 6-8 | `CADTHRUVERSION`=8 + `QUEUESTRUCT` ×3 | 其他 GUI 队列（50200/50209/50210） |

`TOPASSYSTRUCT`#1：`UNIQUEBODYNUMBER`=4 + 4×(`PKBODY_T` + `ZIPBODYBYTES`)
+ `ASSEMBLY` 树：

```
laptop_3d_geom (PKASSEMBLY 62714, children=4)
├── ____  → BODY air_domain (PKBODY 65125, FACEGROUPW 'open', FACE/EDGE/VERTEXINFOMAP, FFREVERSEMAP)
├── fan2  (空)
└── fan1  → BODY rotation1 (65252), BODY impeller1 (63022)
```

- `FACEINFOMAP`：`FACESTATES u16[n]` + `FIDPKFACE i32[n]`（Parasolid face id）。
- `FFREVERSEMAP`：`STRINGARRAY` 索引列表（如 `'212,213,...'`），
  新旧 face/edge id 映射（`NEWFIDTOOLDFID`/`NEWEIDTOOLDEID`）。
- `ORGFILENAMES`：源文件历史（嵌套 INTEGER+STRINGW 记录，
  含原始 `laptop_3d_geom.x_t` 路径）。

`BSGSEX`：`BODYSHAPEGROUPS` → 每网格组
（`MeshingGroup_1_Default`、`_MeshingGroup_1_Default1`、`TemporarySG`）：
`OCTREEPARAM`（OCTREESIZEBYLEN/OCTREESIZEBYPRM 增长比 1.4、
OCTREEBALANCING、OCTREERESTR 区域加密限制 open/case1/rotation1/impeller1、
NUMERICALREGION）+ `WRAPPINGOPTCLS`（包面参数）。

### 6.3 ZIP 压缩块（`ZIPBODYBYTES`/`ZIPOCTREE`/`ZIPFACETINGRULES`）

整段记录负载即为 **Microsoft LZMS** 压缩流（Windows Compression API，
`COMPRESSION_ALGORITHM_LZMS = 4`，`cabinet.dll` 的 `CreateDecompressor` /
`Decompress`）。流首可读字段（小端，亦为 LZMS 流自身前缀）：

```
[u32 magic = 0xC0E5510A][u16 hdr_len = 24][u16 stream_id]
[u64 uncompressed_size][u64 uncompressed_size（重复）]
[u32 compressed_size][...LZMS 压缩数据 compressed_size 字节...]
```

**解析要点：**

- 解压必须从偏移 0（含 magic）开始；剥离任意前缀（含 28 字节）后传入会
  失败（`ERROR_BAD_COMPRESSION_BUFFER` / err=605）。
- 查询输出尺寸时 `Decompress(..., out=NULL)` 返回
  `ERROR_INSUFFICIENT_BUFFER`（122）属正常契约，随后按 `needed` 分配再解。
- `stream_id` 随块变化，是流元数据而非独立编解码选择器。本例：

  | 块 | stream_id | unc | comp |
  |----|-----------|-----|------|
  | ZIPBODYBYTES ×4 | 1035 / 1162 / 1189 / 1194 | 17627 / 116595 / 7843 / 3059 | 15760 / 102033 / 7270 / 2893 |
  | ZIPOCTREE | 1267 | 25,102,350 | 427,949 |
  | ZIPFACETINGRULES | 1067 | 1,274 | 478 |

- 解压尺寸与 `uncompressed_size` 字段精确吻合。
- Windows：`sctsnapshot.ZipBlob.decompress()`；非 Windows 可原样透传
  （round-trip 不受影响）；自 2026-08 起非 Windows 可回退
  **wimlib**（`wimlib_create_decompressor` / `wimlib_decompress_with_decompressor`
  或 1.13 一次性 API，`WIMLIB_COMPRESSION_TYPE_LZMS = 3`），见
  `sctsnapshot.lzms_decompress`。
  `CreateCompressor(LZMS)` 可重压（字节可能不同；`stream_id` 每次变化）。

> 历史误判：曾当作厂商私有位流（已排除 zlib/lzma/lz4/zstd/brotli/bz2/
> PackBits/LZNT1/XPRESS）。实为微软 WIM/ESD 同款 LZMS；通过 SCTprime DLL
> 逆向定位到 `CreateDecompressor(4, …)` 后确认。

#### 6.3.1 `ZIPBODYBYTES` → `CADthru/PKBody3`

```
CADthru/PKBody3          # 15 字节 ASCII 魔数
u32le size               # 逻辑数据长度（明文/密文长度，非物理占用）
data[ceil8(size)]        # Blowfish-LE ECB 密文，物理上按 8 字节块补齐
```

**关键修正（2026-08-02）**：包装体没有独立的 pad / 尾标字段。物理密文
按 8 字节块补齐（`ceil8(size)`）；当 `size % 8 != 0` 时，末块为
零填充块，其固定密钥密文 `E(0^8) = e5 e4 e5 b1 40 29 da 17` 的低 32 位
恰为 `0x17DA2940`——这就是历史上观察到的“尾标”与 `0xB1`“pad”
（`0xB1` 是密文第 `size` 字节）。该值不是独立存储的标记或校验
（已排除 CRC32 / Adler / 求和），也不承载状态语义。

| 变体 | 条件 | 本例 |
|------|------|------|
| 8 倍数长度 | `19 + size == len` | laptop PK 65125（7824B）/ 65252（3040B） |
| 非 8 倍数 | `19 + ceil8(size) == len`，末块密文尾= `0x17DA2940`（E(0) 低 32 位） | box PK 51：`size=7643` → `data=7648`；laptop PK 62715 / 63022 |

**`data` 加解密（已闭合）：**

- 算法：**Blowfish 小端变体 ECB**（标准 16 轮 / π 表 / 密钥扩展；
  唯一差别是 8 字节块按两个 **LE u32** 读作 (L,R)）。实现见
  `blowfish_le.py`（金标准对照：DLL `BF_INIT` @ `0x57BBB0`）。
- 固定密钥：`b"HowDareYouSaySuchAThing"`（23 字节）。
- 解密后为 **Parasolid 二进制传输流**（类 `.x_b`，内嵌
  `SCH_3701153` schema 与 ASCII 字段名）。
- 同版本项目间密文前 ~400 字节相同：ECB 下相同 schema 头明文 →
  相同密文块（历史误称为“私有 schema 前缀”）。
- API：`ZipBlob.decompress_body()` → `PKBody3`；
  `PKBody3.decrypt()`（返回精确明文，长度 = `logical_size`）/
  `schema_prefix` / `logical_size`；`checksum` / `pad` 为兼容性派生字段
  （`0x17DA2940` / 零填充块密文碎片）。
  写端：`pphwriter.encrypt_pkbody3()` 可对解密结果**逐字节复现**原始密文。

#### 6.3.2 `ZIPOCTREE` → 嵌套快照记录流

解压后为与外层同构的小端记录序列（本例顶层 7 条，skipped=0）：

| 标签 | 含义 / 本例规模 |
|------|-----------------|
| `LOCATIONLENGTH` / `LOCATIONSTRING` | 路径长度与内容（本例空路径） |
| `OCTREEVISIBLE` | 可见性标志 |
| `OCTREEMDLBODY` | 八叉树关联 MDL 体（~66 KiB 子记录） |
| **`OCTREEBODY`** | 见下：内含完整 `*.oct` |
| `OCTREEDIVISION` | 见下 |
| `OCTREEREGION` | 见下 |

大块共用包装：`QUEUESTRUCT` → `QUEUEBODY` →
`INDEXARRAY[8]` + `BYTEARRAY[…]`。

- **`INDEXARRAY`**：`i32le[2] = {count=1, offset=0}`（box / laptop 恒同）。
  表示后续 `BYTEARRAY` 为**单段**负载（非 version/flags）。
- **`OCTREEBODY`**：`BYTEARRAY` **字节级等于** 同项目 `*.oct` 成员
  （本例 19,802,609 B，以 `CRDL-FLD` 开头）。
- **`OCTREEDIVISION`**（DLL 写入端 `SCTprime_Bx64!0x89be0` / `0x89ce0`）：
  - 每位对应一个八叉体：`1` = 内部（有 8 子），`0` = 叶子
  - **前序 DFS** 发出；子访问序相对存储槽 `0..7`（`x+2y+4z`）为
    **`(1,3,2,0,5,7,6,4)`**（DLL 内嵌表）
  - 字节内 **LSB-first**；长度 = `ceil(n_octants/8)` =
    `n_internal+1`（满八叉树恒等式）
  - 与 `*.oct` refinement **描述同一棵树**，仅子遍历置换不同；
    box / laptop 按上述规则重放均 **100% 字节一致**
- **`OCTREEREGION`**（DLL 写入端 `0x89d60`）：
  - 每节点 1 字节，取自内存节点 `+0x64`；值域 `{0,1}`
  - **后序 DFS** 发出；子访问序为存储槽序 **`0..7`**
  - 存储长度 ≥ `n_octants`，尾部为零填充（laptop：4,737,668 =
    3,960,249 + 777,419）
  - **不是** `*.oct` 前序下标；对齐 refinement 须做后序→前序重映射
    （`octree_region_as_oct_order`）
  - 几何：`flag=1` 集中于特殊细化区（box：±x 翼块叶子，且全部
    `flag=1` 均为叶子；laptop：局部高深度柱）

API：`SctSnapshot.decompress_octree()` /
`octree_crdlfld_bytes()` / `octree_division()` / `octree_division_bits()` /
`octree_region(n_octants)` / `octree_region_as_oct_order(refinement)` /
`octree_mdl_body()`。常量：`SctSnapshot.OCTREE_DIVISION_CHILD_ORDER`。

**`OCTREEMDLBODY`（已闭合，box.pph 验证）：**

| 字段 | 含义 |
|------|------|
| `INTEGER` ×3 | `n_vertices, n_fins, n_facets` |
| `DPOINTARRAY` | `n_vertices × (f64 x,y,z)` |
| `FINARRAY` | `n_fins × (i32 v0, i32 v1)` |
| `FACETARRAY` | `n_facets × 9×i32`：`(v0,v1,v2, idx, -1, -1, fin0, fin1, fin2)` |
| `PKBOX` | `6×f64` AABB |
| `BYTEARRAY` | 长度分别为 `n_facets` / `n_fins` 的标志（box 全 1） |
| `FACEGROUPSW` | 面组名（box：`open` + `$$$-$$$Part`，各覆盖 12 三角面） |

box 几何：8 顶点 / 19 边 / 12 三角面，`PKBOX=[0,0.01]³`，与 0.01 立方体一致。
laptop：410 / 1216 / 808，同一布局。

#### 6.3.3 `ZIPFACETINGRULES` → `FACETINGRULES`

解压后单条顶层记录 `FACETINGRULES`（本例 LEN=1254，44 个子记录）：

- 若干 `BOOL`（0/1 开关）与 `DOUBLE`（含 `0`、`1e6`、`1e4` 等）
- `STRINGW` 容差串（如 `'9.999…e-07 m'`、`'0.0001 m'`）
- 大量空 `INTARRAY` / `INT2ARRAY` / `BYTEARRAY` / `boolARRAY`
- 嵌套 `FACEALIGNSTATES` 等

API：`SctSnapshot.decompress_faceting_rules()`。

### 6.4 解析注意

- 部分结构（如 `ASSEMBLY` 的 `CSINFO` 之后）含 **48 字节未对齐保留区**
  （观测为 0 与 `...ff 7f` 垃圾字节混合），顺序解析会失步；
  `sctsnapshot._resync` 通过前向搜索下一个合法记录头重新对齐。
- 本样例顶层 14 条记录全部对齐（skipped_bytes=0）。
- LZMS 块本身是叶子：不要把压缩负载当子记录流解析；先解压再按 §6.3.x
  解释明文。

## 7. 体网格 GPH（`<组名>.gph`）

CRDL-FLD 大端，与 gphdecoding 仓完全同构（`gph_model.py`/`gph_parser.py`
可直接解析）。本例：9,665,034 面 / 3,069,898 单元 / 3,523,639 顶点
（BE float64），多面体（npe 4..8），Parts air_domain(cvol=1) /
rotation1(cvol=3)，面区域 5 个。详见 `gphdecoding/GPH_FORMAT_SPEC.md`。

> pph_parser 对 gph 做通用节扫描；若 `gphdecoding` 仓可用（同级目录或
> `D:\training\cgns\gphdecoding`），自动调用其 `gph_model` 给出深度统计。

## 8. 成员间引用关系

```
main.xml (网格组 meshinggroup1, sgs_name=MeshingGroup_1)
   │         │                │                │
   ▼         ▼                ▼                ▼
meshinggroup1.gph   meshinggroup1.oct   *_part.mdl   *_ridge.mdl
   ▲                    ▲                  ▲
   │ LS_SurfaceRegions  │                  │ LS_MdlSurfaceRegions
   │ /LS_Parts          │                  │
   └────── 区域名一致(open/@PartSurface_*) ──┘
                        │
                        │ 字节级 ≡
                        ▼
          sctsnapshot ZIPOCTREE → OCTREEBODY → BYTEARRAY
sctsnapshot: ASSEMBLY 树(air_domain/rotation1/impeller1) ↔ mdl 面区域
             ZIPBODYBYTES → PKBody3 ↔ PKBODY_T 体句柄
sctsnapshot: BSGSEX/MeshingGroup_1 ↔ main.xml 网格组 ↔ oct/gph/mdl 文件名前缀
main.prp: 物性条目 ← main.xml conditions 引用
```

## 9. 待提升部分（无法完全逆向解析）

> 分析样例：`laptop_…_simple.pph`（复杂）与 **`box.pph`**（0.01³ 立方体 +
> `open` 边界，单 PK 体、2249 octants）。容器 ZIP、CRDL-FLD、文本成员、快照
> 记录树、LZMS、PKBody3 加解密、单位量、`OCTREEMDLBODY`、
> `OCTREEDIVISION`/`OCTREEREGION` 序列化序、`INDEXARRAY` 均已可解析。

### 9.1 硬未解（独立几何还原受限）

| 项 | 已掌握 | 缺口 | box 样例增益 |
|----|--------|------|----------------|
| Parasolid 传输流 → B-rep | Blowfish-LE 解密后为含 `SCH_3701153` 的二进制传输流 | 无 Parasolid 运行时则无法独立还原拓扑/几何实体 | 确认外层加密与两端变体；解密明文可读 schema/字段名 |

### 9.2 结构已知、语义未钉死

已钉死（2026-08-02，box + laptop 双样例）：

| 项 | 结论 | 证据 |
|----|------|------|
| `LS_CsidOfFaces` | 双侧闭体语义 `(volA, volB)`，0=外部，`b2 = frid + 1` | laptop part：frid×b2 = {(0,1),(1,2),(2,3),(3,4)} 精确一一对应；ridge 含界面面 `(2,1)`×412,644（两侧均非零）；`LS_MdlClosedVolumes` 记录数 = `max(b2)+1`（box 2 / laptop part 5 / laptop ridge 3） |
| `OCTREEREGION` flag | 每 octant 1 字节，后序；重映射后 `flag=1` **全为叶子**，集中于最深细化层；区域索引与 `OCTREERESTRRGN` / frid / csid-1 同空间 | box：883 叶子，深度 4–5，y∈[0,0.011] 上半精化板；laptop：3,445,907/3,465,218 叶子，深度 14–20，转子薄柱 x∈[-54.47,-51.78]、y∈[4.92,5.47]、z∈[-0.24,0.28] |
| `OCTREERESTR` 区域 | `OCTREERESTRRGN` 字段：`(kind, index, enabled, …)`；laptop 4 区 open=0 / case1=1 / rotation1=2 / impeller1=3（kind: open=0, 其余=2）；box 4 个 `OCTREERESTR` 全空 | 与 MDL `surface_regions` 索引、`csid-1` 一致 |

### 9.3 次要缺口

| 项 | 已掌握 | 缺口 | box 增益 |
|----|--------|------|----------|
| `unit_type` 码表 | 布局已解；`1 → MODEL_LENGTH_UNIT`（`pphxml.resolve_snapshot_unit`） | 其余码值需多单位制样例确认 | 仍恒为 1 |
| 快照 48 字节保留区 | 位于 `CSINFO→PBODYARRAY` 之间，4 个数据点均固定 48B，内容为旧序列化残留/未初始化垃圾，**不承载当前状态语义** | 无（可作已知对齐填充闭合） | skipped=0 |
| PKBody3 末块 | **已闭合**：`0x17DA2940` = E(0^8) 低 32 位；`0xB1` = 零填充块密文第 `size` 字节 | 无 | 见 §6.3.1 |

### 9.4 已闭合（勿再当作未解）

- ZIP 块 → **Microsoft LZMS**
- `MESH_*` 容差 → **`f64le`**；`LENGTHVWU`/`DPOINTU` → 单位量布局
- `ZIPOCTREE`→`OCTREEBODY` → **≡ `*.oct`**
- **`OCTREEMDLBODY`** → CAD 三角面片体（§6.3.2；box 8/19/12 + `[0,0.01]³`）
- MDL `face_type` 133/134；OCT refinement 前序 DFS 位图（子序 `x+2y+4z`）
- PKBody3 外层三种尺寸变体；**`data` → Blowfish-LE ECB**（密钥固定）
- **`OCTREEDIVISION`** → 每 octant 1 bit is-internal；前序 + 子序
  `(1,3,2,0,5,7,6,4)` + LSB-first（box/laptop 100% 重放）
- **`OCTREEREGION`** → 每 octant 1 字节；**后序** + 子序 `0..7` + 尾零填充
- **`INDEXARRAY`** → `{count=1, offset=0}` 单段描述符
- **PKBody3 末块** → 无独立 pad/尾标；`0x17DA2940` 为 `E(0^8)` 低 32 位
- **`OCTREERESTRRGN`** → `(kind, index, …)` 区域表，索引 = frid = csid-1
- **写端闭环** → `pphwriter`（LZMS 压缩 / Blowfish 加密 / ZIP 容器），
  PKBody3 再加密逐字节一致

## 10. 本仓解析器用法

```bash
python pph_parser.py 项目.pph               # 全部成员摘要（含 LZMS 解压摘要）
python pph_parser.py 项目.pph --extract out # 解包
python pph_parser.py 项目.pph --snapshot    # sctsnapshot 完整记录树
python pph_parser.py 项目.pph --octree      # 八叉树叶子深度统计
python tests/test_pph_parser.py             # 健全性测试（含 LZMS / DIVISION 重放）
python tests/test_samples.py                # 跨样例结构不变式（自动发现 *.pph）
python tests/test_minor_gaps.py             # 48B 保留区 / XML 往返 / unit_type
python tests/test_platform.py               # LZMS 跨平台回退 / gph 内建统计
python tests/test_semantics.py              # 双侧闭体 / OCTREEREGION / PKBody3 末块
python tests/test_writer.py                 # 写端 round-trip
python tests/test_parasolid.py              # Parasolid 传输流部分提取
python tests/box/verify_dll_order.py        # DIVISION/REGION 写入端序对照
```

模块：

| 模块 | 职责 |
|------|------|
| `pph_parser.py` | CLI + ZIP 容器 + 成员分类 + 摘要 |
| `crdlfld.py` | CRDL-FLD 公共层（节扫描、记录迭代、元数据；>512MiB mmap） |
| `mdl.py` | MDL 面片几何（节点/面/csid/frid/状态/区域） |
| `oct.py` | OCT 八叉树（位图、叶子重建、块 id） |
| `sctsnapshot.py` | 快照记录流、LZMS、PKBody3、ZIPOCTREE DIVISION/REGION |
| `blowfish_le.py` | PKBody3 Blowfish 小端变体 ECB（`blowfish_tables.py`） |
| `pphxml.py` | main.xml 方言净化、prp、xenv、js |
| `gphstats.py` | 仓库内轻量 GPH 统计（gphdecoding 仓不可用时的降级路径） |
| `parasolid.py` | Parasolid 传输流部分提取（schema/字段名/实体类型） |
| `pphwriter.py` | 写端：LZMS 压缩 + Blowfish 加密 + ZIP 容器 round-trip |

关键 API：`ZipBlob.decompress()` / `decompress_body()` /
`PKBody3.decrypt()` / `SctSnapshot.decompress_octree()` /
`octree_crdlfld_bytes()` / `octree_division_bits()` /
`octree_region_as_oct_order()` / `decompress_faceting_rules()`
（LZMS 解压 Windows `cabinet.dll`，非 Windows 回退 wimlib；压缩需
Windows `cabinet.dll`）。写端：`pphwriter.lzms_compress()` /
`encrypt_pkbody3()` / `clone_pph()`。

开发过程与版本状态见 [DEV_SUMMARY.md](DEV_SUMMARY.md)。
