# PPH 解析功能开发状态总结

> 更新日期：2026-08-01 ｜ 仓库：`pphdecoding` ｜ 格式细节见
> [PPH_FORMAT_SPEC.md](PPH_FORMAT_SPEC.md)

## 1. 总体判断

**解析/解码方向已相当完整，且已被 31 项测试锁定**（laptop 复杂样例 + box
最小样例全部通过）。剩余工作集中在三处：

1. 几何还原（Parasolid 实体 B-rep，硬未解）；
2. 若干结构的语义确认（区域 flag、双侧闭体、尾标/填充字节等）；
3. 尚未起步的写出/互操作路径（当前是纯解码器）。

## 2. 当前完整性：已解析的层面

| 层面 | 状态 | 说明 |
|------|------|------|
| 容器（ZIP） | ✅ 完整 | 成员分类、解包、round-trip 与参考目录逐字节一致 |
| 文本成员 | ✅ 完整 | `main.js` / `main.prp` / `main.xenv` / `main.xml` 均可解析；XML 方言索引标签 `<SECTITEM[0]>` 有 sanitize/还原机制 |
| CRDL-FLD 公共层 | ✅ 完整 | gph/oct/mdl 共享的大端节扫描、记录迭代、元数据；`_valid_section_start` 防误判 |
| MDL 面片几何 | ✅ 完整 | part/ridge 的顶点、面（face_type 133/134 = npe 规则）、csid、frid、状态、区域 |
| OCT 八叉树 | ✅ 完整 | 前序位图、内部/叶子计数不变式、Morton 子序、叶子包围盒重建、深度统计 |
| sctsnapshot 快照 | ✅ 完整 | 小端记录流、失步 `_resync`、LZMS 解压、`OCTREEDIVISION`/`OCTREEREGION` 序列化序（box/laptop 100% 重放一致）、`OCTREEMDLBODY`、单位量 VWU/DPOINTU |
| 加密 | ✅ 闭环 | PKBody3 外层 → Blowfish-LE ECB 固定密钥 → Parasolid 二进制传输流；加解密互逆已验证 |
| 测试 | ✅ 通过 | 31 项测试全过（laptop 复杂样例 + box 最小样例），CLI 摘要正常 |

主要模块：

| 模块 | 职责 |
|------|------|
| `pph_parser.py` | CLI + ZIP 容器 + 成员分类 + 摘要报告 |
| `crdlfld.py` | CRDL-FLD 公共二进制层（gph/oct/mdl 共享） |
| `mdl.py` | `*_part.mdl` / `*_ridge.mdl` 面片几何 |
| `oct.py` | `*.oct` 八叉树（前序位图 → 叶子包围盒重建） |
| `sctsnapshot.py` | 快照记录流 + LZMS / PKBody3 / ZIPOCTREE DIVISION·REGION |
| `blowfish_le.py` | PKBody3 Blowfish 小端变体 ECB（`blowfish_tables.py`） |
| `pphxml.py` | main.xml 方言净化、prp、xenv、js |

## 3. 未完成的关键点

### 3.1 硬未解：Parasolid 实体几何还原

- 已掌握：Blowfish-LE 解密得到含 `SCH_3701153` 的二进制传输流，可读
  schema/字段名。
- 缺口：没有 Parasolid 运行时，**无法独立还原拓扑/几何实体（B-rep）**。
- 影响：PKBody3 当前只停留在"解密出明文传输流"，下游几何互操作受限于此。

### 3.2 结构已明、语义未钉死

| 项 | 已掌握 | 缺口 |
|----|--------|------|
| `OCTREEREGION` flag 物理含义 | 后序序列化、取值 `{0,1}`、重映射后 flag=1 全为叶子且集中于 ±x 翼细化区 | 与 open 边界条件 / 网格算法的精确对应（非简单 AABB） |
| `LS_CsidOfFaces` | 双路 `I4[n_faces]` 布局 | 严格"双侧闭体"语义；box 仅确认 b1 全 0、b2 全 1 |
| PKBody3 尾标 `0x17DA2940` | 确认为常量标记 | 校验算法未识别（已排除 CRC32） |
| PKBody3 `pad` 字节 | 可选；box 首见 `0xB1` | 取值含义与触发条件未知 |

### 3.3 次要缺口

- `unit_type` 码表：布局已解，但样例恒为 1，未与 `main.xenv` UNIT
  全量建立映射。
- 快照 48 字节未对齐保留区：`_resync` 可跳过，但不知是否承载语义
  （laptop/box 顶层 skipped=0）。
- `main.xml` 索引标签非标准 XML：标准解析器需先 sanitize，是已知互操作陷阱。

### 3.4 平台与依赖限制

- **LZMS 解压仅限 Windows** `cabinet.dll`；非 Windows 只能透传原始压缩块，
  无法解码嵌套内容（读取侧受限）。
- gph 深度统计依赖同级 `gphdecoding` 仓，不在本仓库内。

### 3.5 写端整体缺失

- 仓库是**纯解码器**：ZIP 打包、LZMS 压缩、Blowfish 加密、sctsnapshot
  序列化均未实现。
- `encrypt_ecb` 与 LZMS `CreateCompressor` 已验证可行，但
  PPH_FORMAT_SPEC 开篇"支撑导出转换与文件互操作"的目标目前只完成了解读一半。

### 3.6 验证覆盖局限

- 所有结论基于 **laptop 与 box 两个样例**；测试断言含样例特定值
  （30 个物性组、23 个条件等）。
- 多网格组、`unit_type ≠ 1`、不同 pad/尾标变体等尚未被覆盖，属于
  "未验证"而非"已验证失败"。

## 4. 建议的下一步

按投入产出排序：

1. **语义钉死**：用更多真实项目 pph 验证 `OCTREEREGION`、`LS_CsidOfFaces`、
   `unit_type` 映射（纯解析，收益明确）。
2. **平台解耦**：为非 Windows 提供 LZMS 解码 fallback（纯 Python 实现或
   外部库），补全读取侧能力。
3. **写端起步**：从最小可写闭环（box.pph：ZIP 打包 + Blowfish 加密 +
   LZMS 压缩）验证 round-trip，为文件互操作铺路。
4. **Parasolid 还原**：评估引入 Parasolid 内核 / 替代方案（长期硬骨头）。
