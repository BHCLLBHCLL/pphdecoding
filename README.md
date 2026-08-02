# pphdecoding

decode cradle scflow project format pph file

解析 Cradle scFLOW 项目文件 `.pph`（ZIP 容器 + CRDL-FLD 二进制 +
CADThru 快照记录流）。完整格式说明见 [PPH_FORMAT_SPEC.md](PPH_FORMAT_SPEC.md)；
开发过程与当前版本状态见 [DEV_SUMMARY.md](DEV_SUMMARY.md)。

## 用法

```bash
python pph_gui.py                            # GUI：查看/修改（PyQt5 + VTK 3D）
python pph_gui.py 项目.pph                   # GUI 直接打开
python pph_parser.py tests\laptop_thermal_steady_scaled_v3_fanonly_simple.pph
python pph_parser.py 项目.pph --extract out_dir   # 解包
python pph_parser.py 项目.pph --snapshot          # sctsnapshot 完整记录树
python pph_parser.py 项目.pph --octree            # 八叉树叶子深度统计
python tests/test_pph_parser.py                   # 健全性测试（含 LZMS / DIVISION）
python tests/test_samples.py                      # 跨样例结构不变式
python tests/test_gui.py                          # GUI/VTK 离屏测试
python tests/box/verify_dll_order.py              # DIVISION/REGION 写入端序对照
```

写端（读 → 改 → 写回）：见 `pphwriter.py`（LZMS 压缩 + Blowfish 加密 +
ZIP 容器）与 `parasolid.py`（解密传输流的 schema/字段名/实体类型部分提取）。

## GUI（pph_gui.py）

基于 **PyQt5 + VTK（OpenGL2 硬件加速）** 的查看/修改界面：

- 成员树（文本/快照/网格组）→ 点击切换视图；
- **文本编辑**：main.js / main.prp / main.xenv / main.xml 直接编辑，
  "另存为"通过 `pphwriter` 写回新 .pph（未修改的成员原样复制）；
- **快照**：sctsnapshot 记录树 + PKBody3/Parasolid 摘要；
- **3D（CFD 风格）**：MDL 面片（frid/csid 着色，区域名图例）、
  OCT 叶子包围盒（深度着色）、GPH 边界面（owner 着色），轨道相机交互；
  **网格线叠加**（vtkExtractEdges 暗色线条）、**右上角坐标方向指示器**、
  **右侧 Qt 图例面板**（离散区域色块行 + 连续渐变条，替代 VTK 色标条，
  布局确定、文字始终可读）、渐变背景，均可开关；大网格自动限量渲染
  （MDL 30 万面 / OCT 4 万叶子 / GPH 12 万面，见 `pph_gui.DEFAULT_CAPS`）；
- 兼容 VTK 9.3：`QVTKRenderWindowInteractor` 已无 `start()`，
  交互器在 3D 页首次显示时经 `GetInteractor().Initialize()` + 轨道相机
  样式初始化（`tests/test_gui.py` 有回归测试）；
- 依赖自动安装：`python -m pip install -r requirements-gui.txt`
  （PyQt5 / vtk / numpy；本仓库环境已装 PyQt5 5.15.10 + VTK 9.3.1）。

## 模块

| 模块 | 职责 |
|------|------|
| `pph_parser.py` | CLI + ZIP 容器 + 成员分类 + 摘要报告 |
| `crdlfld.py` | CRDL-FLD 公共二进制层（gph/oct/mdl 共享） |
| `mdl.py` | `*_part.mdl` / `*_ridge.mdl` 面片几何 |
| `oct.py` | `*.oct` 八叉树（前序位图 → 叶子包围盒重建） |
| `sctsnapshot.py` | 快照记录流 + LZMS / PKBody3 / ZIPOCTREE DIVISION·REGION |
| `blowfish_le.py` | PKBody3 Blowfish 小端变体 ECB（`blowfish_tables.py`） |
| `pphxml.py` | `main.xml`（索引标签方言）/ `main.prp` / `main.xenv` / `main.js` |
| `gphstats.py` | 仓库内轻量 GPH 统计（gphdecoding 仓不可用时的降级） |
| `parasolid.py` | Parasolid 传输流部分提取（schema/字段名/实体类型） |
| `pphwriter.py` | 写端：LZMS 压缩 + Blowfish 加密 + ZIP 容器 round-trip |
| `pph_vtk.py` | VTK 几何构建器（MDL/OCT/GPH → vtkPolyData，离屏可测） |
| `pph_gui.py` | PyQt5 + VTK 查看/修改 GUI（成员树/文本编辑/快照/3D） |

依赖：仅 `numpy`（Python 3.10+）。体网格 `.gph` 的深度统计在检测到
[gphdecoding](https://github.com/) 仓（同级目录）时自动调用其 `gph_model`，
否则回退到仓库内 `gphstats.py`。
`main.sctsnapshot` 内 LZMS 压缩块解压需要 Windows `cabinet.dll`
（`sctsnapshot.ZipBlob.decompress()`），非 Windows 自动回退 wimlib。

## 八叉树附属数组（要点）

- **`OCTREEDIVISION`**：每 octant 1 bit（is-internal），前序 + 子序
  `(1,3,2,0,5,7,6,4)` + LSB-first → `octree_division()` /
  `octree_division_bits()`
- **`OCTREEREGION`**：每 octant 1 字节，**后序** + 子序 `0..7` →
  `octree_region()`；与 `*.oct` 对齐用 `octree_region_as_oct_order()`
- **`INDEXARRAY`**：`{count=1, offset=0}`，标记后续 `BYTEARRAY` 为单段
- **`PKBody3`**：`CADthru/PKBody3` + `u32 size` + `data[ceil8(size)]`
  （Blowfish-LE ECB，密钥 `HowDareYouSaySuchAThing`）→ `decrypt()`；
  无独立 pad/尾标——`0x17DA2940` 是零填充块密文 `E(0^8)` 的低 32 位
