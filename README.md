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

基于 **PyQt5 + VTK（OpenGL2 硬件加速）** 的查看/修改界面，
参照 scFLOW Pre 手册（`CradleCFD2025.2/Manuals/scFLOW/HTML/Pre_eng`）
重新设计：

- **Navigation Window**（左上方）：工具按钮行（打开/另存为/重载）+
  当前文件信息卡片 + 分组导航树（模型数据 / 视图 / 数据），点击即跳转；
- **Tree Window**（左下方）：成员树（文本/快照/网格组）+ 右键菜单
  （属性 / 在 3D 中显示 / 在文本中打开 / 解析属性）；**模型树**
  （第二标签页）按网格组列出闭体（body）与面区域，**复选框控制显隐**
  （勾选=显示、取消=隐藏），**右键菜单**：仅显示此项 / 隐藏此项 /
  显示全部 / 隐藏全部 / 在 3D 中查看——不使用单击/双击（避免触发
  重复解析卡死）；解析后的 MDL 模型缓存复用，重渲染不重新解析；
- **Property Window**（右侧）：选中树项的解析属性
  （归档信息、GPH/OCT/MDL 统计、xenv/prp/xml/js 摘要、快照/Parasolid）；
- **Draw Window**（中央 3D）：分组控制面板（网格组/显示/着色/视图按钮、
  图层开关、剖面裁剪 X/Y/Z 滑动条），着色/线框模式、网格线叠加、
  **剖面裁剪**、**橡皮框缩放**、Fit/Reset、坐标方向指示器、Qt 图例
  （区域名色块 + 渐变条）；**视图类型**（全部 / 仅几何 MDL /
  仅网格 GPH+OCT）；**拾取面**（点击 MDL 面单独显示）+ 恢复全部；
  打开文件后 **3D 为默认显示区域**；
- **看板（Dashboard）**：文件格式数据卡片（归档/压缩率/GPH/OCT/MDL/
  快照/Parasolid，2×4 网格排布）+ 成员尺寸 Top12 条形图，大网格
  （>64 MiB）自动跳过深度统计，可手动刷新；
- **文本编辑**：main.js / main.prp / main.xenv / main.xml 直接编辑，
  "另存为"通过 `pphwriter` 写回新 .pph（未修改的成员原样复制）；
- **快照**：sctsnapshot 记录树 + PKBody3/Parasolid 摘要；
- 大网格自动限量渲染（MDL 30 万面 / OCT 4 万叶子 / GPH 12 万面）；
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
