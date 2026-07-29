# PPH 项目文件格式说明（逆向工程）

> 目标：完整描述 Cradle scFLOW 项目文件 `.pph` 的容器与全部成员格式，
> 支撑导出转换与文件互操作。分析样例：
> `tests/laptop_thermal_steady_scaled_v3_fanonly_simple.pph`
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

28 字节头（小端）：

```
[u32 magic = 0xC0E5510A][u16 hdr_len = 24][u16 codec/id]
[u64 uncompressed_size][u64 uncompressed_size（重复）]
[u32 compressed_size][payload compressed_size 字节]
```

- `ZIPBODYBYTES`：Parasolid 体的压缩序列化（本例 4 个体，
  解压后 3,059..116,595 字节）。`PKBODY_T` 为体句柄 id。
- `ZIPOCTREE`：八叉树数据（解压后 25,102,350 字节，压缩 427,949 字节，
  比 58.7:1）。
- `ZIPFACETINGRULES`：面片化规则（解压后 1,274 字节）。

> **未解**：payload 为厂商私有位流编码。已排除 zlib/raw-deflate/
> lzma/lz4/zstd/brotli/bz2/PackBits。特征：ZIPBODYBYTES 起始为 128 字节
> 0x88 族填充（0x88/0x89/0x98），ZIPOCTREE 起始为 0xAA 族
> （0xAA/0xA9/0x9A/0x99）——呈位打包 RLE/LZ 混合特征。codec/id 字段
> （1035/1067/1162/1189/1194/1011）随块变化，疑似版本或块参数。
> 头部三尺寸字段完整，payload 可原样透传（round-trip 互操作不受影响）。

### 6.4 解析注意

- 部分结构（如 `ASSEMBLY` 的 `CSINFO` 之后）含 **48 字节未对齐保留区**
  （观测为 0 与 `...ff 7f` 垃圾字节混合），顺序解析会失步；
  `sctsnapshot._resync` 通过前向搜索下一个合法记录头重新对齐。
- 本样例顶层 14 条记录全部对齐（skipped_bytes=0）。

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
   ▲                                       ▲
   │ LS_SurfaceRegions/LS_Parts            │ LS_MdlSurfaceRegions
   └────── 区域名一致(open/@PartSurface_*) ──┘
sctsnapshot: ASSEMBLY 树(air_domain/rotation1/impeller1) ↔ mdl 面区域
sctsnapshot: BSGSEX/MeshingGroup_1 ↔ main.xml 网格组 ↔ oct 文件名
main.prp: 物性条目 ← main.xml conditions 引用
```

## 9. 已知未解项

1. **ZIP payload 编码**（§6.3）：厂商私有位流，待进一步逆向；
   不影响其余全部内容的解析与互操作（块可原样透传）。
2. `LS_CsidOfFaces` 双块的精确语义（观测：b1 全 0、b2=闭体 id 1..N，
   推测为面两侧闭体 id）。
3. `FACEGROUPW` 中 `MESH_CHORDTOL/CHORDANG/SURFTOL/SURFANG` 的 8 字节
   负载编码（未按 f64 对齐解读出常见值）。
4. `DPOINTU`/`LENGTHVWU` 固定 36/12 字节结构的字段划分
   （推测 f64 值 + u32 单位码，部分观测为未初始化值）。

## 10. 本仓解析器用法

```bash
python pph_parser.py 项目.pph               # 全部成员摘要
python pph_parser.py 项目.pph --extract out # 解包
python pph_parser.py 项目.pph --snapshot    # sctsnapshot 完整记录树
python pph_parser.py 项目.pph --octree      # 八叉树叶子深度统计
python tests/test_pph_parser.py             # 18 项健全性测试
```

模块：

| 模块 | 职责 |
|------|------|
| `pph_parser.py` | CLI + ZIP 容器 + 成员分类 + 摘要 |
| `crdlfld.py` | CRDL-FLD 公共层（节扫描、记录迭代、元数据） |
| `mdl.py` | MDL 面片几何（节点/面/csid/frid/状态/区域） |
| `oct.py` | OCT 八叉树（位图、叶子重建、块 id） |
| `sctsnapshot.py` | 快照记录流（树、ZIP 头、语义提取） |
| `pphxml.py` | main.xml 方言净化、prp、xenv、js |
"""
