# DEV_SUMMARY — pphdecoding 开发总结

> 仓库：Cradle scFLOW 项目文件 `.pph` 逆向与解析器  
> 文档日期：2026-08-01  
> 对照样例：`box.pph`（简单立方体）+ `laptop_thermal_steady_scaled_v3_fanonly_simple.pph`  
> 当前测试：`python -m pytest tests/test_pph_parser.py` → **31 passed**

完整格式规范见 [PPH_FORMAT_SPEC.md](PPH_FORMAT_SPEC.md)；用法见 [README.md](README.md)。

---

## 1. 目标与范围

解析 scFLOW 工程包 `.pph`（ZIP 容器），覆盖：

| 层次 | 内容 |
|------|------|
| 容器 | ZIP 成员分类、解包 |
| 文本 | `main.xml` / `main.prp` / `main.xenv` / `main.js` |
| CRDL-FLD | `*.oct` / `*_part.mdl` / `*_ridge.mdl` /（可选）`*.gph` |
| 快照 | `main.sctsnapshot` 小端记录流、LZMS、PKBody3、ZIPOCTREE |

**非目标（仍受限）**：无 Parasolid 运行时独立还原 B-rep；`OCTREEREGION` flag 的完整物理/网格算法语义。

---

## 2. 开发过程（里程碑）

按依赖关系推进，而不是按文件名顺序。

### 2.1 容器与公共层（v0.1）

- ZIP 成员角色识别（`pph_parser.py`）
- CRDL-FLD 大端公共层（`crdlfld.py`）→ gph / oct / mdl 共用
- OCT 前序 refinement 位图与叶子包围盒重建（`oct.py`）
- MDL 面片（节点 / 面 / csid / frid / 面区域）（`mdl.py`）
- XML 方言净化（`pphxml.py`）

### 2.2 快照记录流与 LZMS

- 小端 `TAG[16]+LEN+PAYLOAD` 嵌套记录（与 CRDL-FLD 大端不同）
- ZIP 块误判为厂商私有压缩 → 逆向 `SCTprime_Bx64.dll` 定位
  `CreateDecompressor(4,…)` → **Microsoft LZMS**（`cabinet.dll`）
- `ZIPBODYBYTES` / `ZIPOCTREE` / `ZIPFACETINGRULES` 解压通路打通

### 2.3 ZIPOCTREE 结构定位

| 记录 | 结论 |
|------|------|
| `OCTREEBODY` | `BYTEARRAY` **≡** 同项目 `*.oct` |
| `OCTREEMDLBODY` | CAD 三角面片体（顶点/边/面/PKBOX/面组） |
| `OCTREEDIVISION` / `OCTREEREGION` | 附属数组（语义见下） |
| `INDEXARRAY` | `{count=1, offset=0}` 单段描述符 |

### 2.4 box.pph 对照（简化样例）

引入 `0.01³` 立方体 + `open` 边界样例，用于：

- 缩小 DIVISION/REGION 搜索空间
- 验证 `OCTREEMDLBODY`（8/19/12，`PKBOX=[0,0.01]³`）
- 验证 PKBody3 pad+尾标变体（`pad=0xB1`）
- 否定若干错误假说（REGION=立方体相交、DIVISION=子槽字节掩码等）

探索脚本集中在 `tests/box/`；过时假说清单见 [tests/box/NOTES.md](tests/box/NOTES.md)。

### 2.5 PKBody3 解密

- 外层：`CADthru/PKBody3` + `size` + `data` + 可选 `pad` + 尾标 `0x17DA2940`
- `data`：**Blowfish 小端变体 ECB**，固定密钥 `HowDareYouSaySuchAThing`
- 实现：`blowfish_le.py` + `blowfish_tables.py`（DLL `BF_INIT` 金标准对照）
- 明文：Parasolid 二进制传输流（含 `SCH_3701153`）；同版本密文前缀相同来自 ECB

### 2.6 DIVISION / REGION 写入端（DLL）

在 `SCTprime_Bx64.dll` 定位序列化函数：

| 数组 | RVA（代表） | 序 | 语义 |
|------|-------------|----|------|
| DIVISION | `0x89be0` / `0x89ce0` | **前序**；子序 `(1,3,2,0,5,7,6,4)`；LSB-first | 每 octant 1 bit = is-internal |
| REGION | `0x89d60` | **后序**；子序存储 `0..7` | 每 octant 1 字节（`node+0x64`） |

验证：按上述规则重放，**box 与 laptop 对 DIVISION 均为 100% 字节一致**。  
此前 laptop ~78%「匹配」是子序错误导致的统计巧合。

---

## 3. 当前版本模块图

```
.pph (ZIP)
 ├─ main.xml / .prp / .xenv / .js     → pphxml.py
 ├─ *.oct / *_part.mdl / *_ridge.mdl → crdlfld + oct/mdl
 ├─ *.gph (可选深度)                 → 外链 gphdecoding
 └─ main.sctsnapshot                 → sctsnapshot.py
      ├─ ZIP* → LZMS (cabinet.dll)
      ├─ ZIPBODYBYTES → PKBody3 → blowfish_le.decrypt
      └─ ZIPOCTREE → OCTREEBODY / DIVISION / REGION / MDLBODY
```

| 文件 | 职责 | 状态 |
|------|------|------|
| `pph_parser.py` | CLI、摘要、解包 | 稳定 |
| `crdlfld.py` | CRDL-FLD 公共层 | 稳定 |
| `oct.py` | 八叉树 | 稳定 |
| `mdl.py` | 面片几何 | 稳定 |
| `pphxml.py` | 文本成员 | 稳定 |
| `sctsnapshot.py` | 快照 / LZMS / 八叉树附属数组 | 稳定（API 已对齐 DLL） |
| `blowfish_le.py` | PKBody3 解密 | 稳定 |
| `blowfish_tables.py` | Blowfish P/S 表 | 稳定 |

### 关键 API（当前）

```text
ZipBlob.decompress() / decompress_body()
PKBody3.decrypt()
SctSnapshot.decompress_octree()
SctSnapshot.octree_crdlfld_bytes()
SctSnapshot.octree_division() / octree_division_bits()
SctSnapshot.octree_region() / octree_region_as_oct_order(refinement)
SctSnapshot.OCTREE_DIVISION_CHILD_ORDER  # (1,3,2,0,5,7,6,4)
SctSnapshot.octree_mdl_body()
```

---

## 4. 样例工程

| 样例 | 路径 | 用途 |
|------|------|------|
| laptop | `tests/laptop_thermal_steady_scaled_v3_fanonly_simple(.pph)` | 全量规模（~4M octants） |
| box | `tests/box/`（由 `box.pph` 解包） | 语义裁决与几何对照 |

验证入口：

```bash
python -m pytest tests/test_pph_parser.py
python tests/box/verify_dll_order.py      # DIVISION/REGION 序（box+laptop）
python tests/box/verify_division.py       # DIVISION 单独重放（box）
python tests/box/analyze_box_octree.py    # box 摘要
```

---

## 5. 已闭合 vs 开放项

### 5.1 已闭合（勿再当作未解）

- ZIP → Microsoft LZMS  
- PKBody3 外层变体 + Blowfish-LE ECB 解密  
- `OCTREEBODY` ≡ `*.oct`；`OCTREEMDLBODY` 面片布局  
- `OCTREEDIVISION` 位图语义与序列化序（两样本 100%）  
- `OCTREEREGION` 后序序列化 + 尾零填充；与 oct 对齐 API  
- `INDEXARRAY` = `{1,0}` 单段描述符  
- MDL `face_type` 133/134；OCT refinement 前序 `x+2y+4z`

### 5.2 仍开放

| 优先级 | 项 | 说明 |
|--------|----|------|
| 高 | Parasolid 传输流 → B-rep | 需 PS 内核；解密明文已可得 |
| 中 | `OCTREEREGION` flag 物理含义 | 序列化已定；box 上 flag1=特殊细化区叶子，与 open BC 的精确映射未钉死 |
| 低 | `unit_type` 全表、`pad` 触发条件、快照保留区 | 不影响主路径解析 |

详见规范 §9。

---

## 6. 关键教训（给后续开发）

1. **压缩/加密不要猜编解码**：以 DLL 导入与调用点为准（LZMS、Blowfish）。  
2. **同长度数组 ≠ 同遍历序**：`*.oct` 前序 `0..7` ≠ DIVISION 子序置换 ≠ REGION 后序。  
3. **部分匹配率陷阱**：随机基线 ~78% 会被当成「接近正确」；必须以字节级重放验收。  
4. **简化样例价值**：`box.pph` 把 DIVISION 从「猜掩码」推进到「可证明的位图序」。  
5. **探索脚本会过期**：`tests/box/` 大量实验保留作记录；以 `NOTES.md` + 规范 §6.3 为准。

---

## 7. 当前版本状态快照

| 项 | 值 |
|----|-----|
| 分支 | `main`（跟踪 `origin/main`） |
| 回归测试 | 31 passed |
| 格式规范 | `PPH_FORMAT_SPEC.md`（§6.3 / §9 已按 DLL 结论刷新） |
| 样例探索说明 | `tests/box/NOTES.md` |
| 运行依赖 | Python 3.10+、`numpy`；LZMS 需 Windows `cabinet.dll` |
| 可选依赖 | 同级 `gphdecoding`（GPH 深度统计） |

### 建议下一步（非阻塞）

1. 若需 B-rep：对接 Parasolid（或厂商）加载 `PKBody3.decrypt()` 明文。  
2. REGION flag：在后序重映射基础上，对照 mesher 参数 / open 延伸规则做谓词。  
3. 清理或归档 `tests/box/` 中已标注过时的探索脚本，避免误用。

---

## 8. 文档索引

| 文档 | 内容 |
|------|------|
| [README.md](README.md) | 用法与模块一览 |
| [PPH_FORMAT_SPEC.md](PPH_FORMAT_SPEC.md) | 格式规范与待解表 |
| [tests/box/NOTES.md](tests/box/NOTES.md) | box 探索脚本权威入口 / 过时清单 |
| [DEV_SUMMARY.md](DEV_SUMMARY.md) | 本文：过程与版本状态 |
