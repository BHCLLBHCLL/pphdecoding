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
python tools/extract_schema.py box.pph -o schemas/box.json   # 抽取条件/环境/物性 Schema
python tools/extract_schema.py a.pph b.pph --merge -o schemas/merged.json
python tools/build_corpus.py . -o corpus.json --limit 1      # 黄金语料清单（成员哈希）
python -m scflowpre_probe                          # 探测 scFLOWpre 安装与 DLL 导出
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
- **Execute 面板开关**：“使用 scFLOWpre API 构建 Model / Octree / Mesh”
  默认关闭；关闭时保持原生查看/解析行为，打开时勾选 BAM/Octree/Mesh 并
  确认/Apply 后生成可在 scFLOWpre 宿主中运行的 VBS（BAM → Octree → Mesh
  + SaveProject + 完成标记）；在宿主中执行脚本后，GUI 会自动轮询标记并
  Reload，无需手动刷新。
- **Octree Parameter** 对话框已按 scFLOW 手册与录制 VBS 刷新：Density +
  Facet (Octree) + AF Facetter + OCT Length + Result 分组，参数与 xenv
  （`OCT_MESH/FACET_*`、`FACET/SOLID_BASE_*`、`OCT_LENGTH_PARAM_*`）一致。
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
| `mdl.py` | `*_part.mdl` / `*_ridge.mdl` 面片几何（解析 + `write_mdl` 写端：区域/闭体/体区域原生布局） |
| `oct.py` | `*.oct` 八叉树（前序位图 → 叶子包围盒重建） |
| `sctsnapshot.py` | 快照记录流 + LZMS / PKBody3 / ZIPOCTREE DIVISION·REGION |
| `blowfish_le.py` | PKBody3 Blowfish 小端变体 ECB（`blowfish_tables.py`） |
| `pphxml.py` | `main.xml`（索引标签方言）/ `main.prp` / `main.xenv` / `main.js` |
| `gphstats.py` | 仓库内轻量 GPH 统计（gphdecoding 仓不可用时的降级） |
| `fldstats.py` | scPOST 求解器 FLD 场文件统计（官方 Samples_POST/FLD 样例；f32/f64 方言、六面体/混合单元、材料、BC 区域、场量） |
| `fldutil_bridge.py` | FLDUTIL_Bx64.dll Rosetta（FEM 中性格式 I/O 库）+ 容器级真值对拍 |
| `native_bam.py` | 原生 BAM（对齐 Analysis Model Wizard 步骤：闭体识别/多重边/匹配/微小面/Repair/CheckErrors/ridge） |
| `voxmesh.py` | 自研 Voxel/hex-dominant mesher（MDL/STL → octree → hex/poly → `.oct`+`.gph`） |
| `polymesh.py` | 自研原生多面体 mesher（clipped Voronoi：Lloyd/近壁层/VoroCrust 式特征保形 → `.gph`） |
| `parasolid.py` | Parasolid 传输流部分提取（schema/字段名/实体类型） |
| `pphwriter.py` | 写端：LZMS 压缩 + Blowfish 加密 + ZIP 容器 round-trip |
| `pph_vtk.py` | VTK 几何构建器（MDL/OCT/GPH → vtkPolyData，离屏可测） |
| `pph_gui.py` | PyQt5 + VTK 查看/修改 GUI（成员树/文本编辑/快照/3D） |
| `schema_extract.py` | 从 PPH 抽取条件/环境键/物性组 Schema（JSON） |
| `condition_registry.py` | 条件类型注册表（跨项目合并、校验、JSON 持久化） |
| `units.py` | xenv UNIT 键注册表 + 单位换算引擎（含复合单位/温度） |
| `scflowpre_probe.py` | scFLOWpre 安装与 DLL 导出探测（纯 PE 解析，只读） |
| `tools/build_corpus.py` | 黄金语料清单（成员角色/大小/压缩比/SHA-256） |

## Phase 0/1 工具（scFLOWpre 功能对照开发前置）

- `tools/extract_schema.py`：把 `main.xml` 条件树、`main.xenv` Section/Key、
  `main.prp` 物性组转成 JSON 注册表；支持多项目合并。输出示例见 `schemas/box.json`。
- `condition_registry.py`：按 `Cond*` 类型汇总字段/区域/样本值，供通用条件编辑器
  与“未知字段/类型不匹配”校验使用。
- `units.py`：覆盖 xenv UNIT 键（长度/速度/压力/温度/复合单位等）与快照
  `unit_type` 解析；`convert()` 支持 SI 因子换算与温度偏移换算。
- `scflowpre_probe.py`：探测本机 Cradle 安装、关键 DLL 导出数量与
  `SCTpreCLIHelper`/`scConverter` 等批处理工具，为自动化桥提供可行性证据。
- `voxmesh.py`：自研拟体素化 mesher（cfMesh/snappy 风格，参考
  `docs/VOXMESH_NOTES.md`）：`python -m voxmesh box.pph -o out --rough`；
  GUI `Execute → Voxel Fitting Mesh (Self Build)…`。
- `polymesh.py`：自研原生多面体 mesher（cfMesh pMesh/VoroCrust/LAVA 参考，
  见 `docs/POLYMESH_NOTES.md`）：`python -m polymesh box.pph -o out
  --preserve-features --lloyd 2 --layers 2`；
  GUI `Execute → Polyhedral Mesh (Self Build)…`。
- `native_bam.py`：原生 BAM（无宿主时对齐 Analysis Model Wizard 步骤，
  见 `docs/NATIVE_BAM_NOTES.md`）：Execute（API 关闭）勾选 BAM 或
  向导 Build/Create Facet 触发，写回布局一致的 `*_part.mdl`。
- `tools/build_corpus.py`：生成语料清单（含成员 SHA-256），作为字节级回归基线。

新增测试：`tests/test_schema_extract.py`、`tests/test_condition_registry.py`、
`tests/test_units.py`、`tests/test_scflowpre_probe.py`、`tests/test_corpus.py`。

## M2 自动化桥与批处理

- `automation/vbs_bridge.py`：VBScript 桥——构建/写出/读取 `.vbs`，
  `VbsBridge` 提供 manual / cli / gui（pywinauto）三种执行后端；
  实测本机 `scFLOWpreAPI.ExecuteVBS` 可由 NativeBridge 加载。
- `automation/history_vbs.py`：解析 scFLOWpre 录制的 `history.vbs`
  （续行拼接、Call/方法调用、参数切分），输出结构化动作序列，
  供条件 Schema 补全与自动化回放使用。
- `native/scflow_bridge.{h,cpp}` + `native/build.ps1`：C ABI 桥原型，
  MSVC 编译后由 `native_bridge.py` 加载；已实测 11 个关键 DLL 全部
  可加载，`ExecuteVBS` / `CreateShapeGroupSet` / `ExpandZip` 符号命中；
  新增管线符号探测（`--pipeline`，9 个 SCTprime/Zip/API 入口全部可解析）
  与 ZipLibrary 真实调用（`--expand-zip`，实验性）。
  编译：`powershell -ExecutionPolicy Bypass -File native\build.ps1`。
  NativeBridge 第一批真实管线调用已实现：`CreateShapeGroupSet` /
  `CreateShapeGroup` / `CreateMDL` 按 MSVC ABI 封装（16 字节
  `{ptr, id}` 接口包装对象、sret/this 实参顺序），CLI 入口为
  `--pipeline-create-set / --pipeline-create-group / --pipeline-create-mdl`；
  SCTprime 宿主文档上下文（`[ctx+0xF8]`）未就绪时返回
  `SCF_ERR_CONTEXT_NOT_READY`，不会崩溃。
- `automation/host_pipeline.py`：把桥注册为进程内 COM 组件
  （`pphdecoding.ScflowPipeline`，HKCU，无需管理员）并生成宿主 VBS；
  在 scFLOWpre 中 `File → Execute VBScript` 运行该脚本后，桥在宿主进程内
  直接调用 `CreateShapeGroupSet / CreateShapeGroup / CreateMDL`。用法：

  ```powershell
  python -m automation.host_pipeline --register
  python -m automation.host_pipeline --write-vbs host_pipeline.vbs `
      --project D:\training\cradle\box\box.pph
  # 在 scFLOWpre 中执行 host_pipeline.vbs
  # 结果写入 host_pipeline_result.txt（与 --result 指定路径一致）
  ```

  自动 GUI 后端（`--run --backend gui`）为尽力而为；宿主窗口不稳定时以
  手动执行 VBS 为准。
- `automation/batch_bridge.py`：Windows CLI 批处理桥（`scFLOWpreCLI` /
  `SCTpreCLI` / `SCTcombCLI` bat + `SCTpreCLIHelper`），支持命令构造与
  `all-cmdline` dry-run。
- `automation/pipeline_plan.py`：生成 VBS 验收计划并校验 PPH 中的
  MDL/OCT/GPH 成员；命令已用 `tests/box_vbs*.vbs`（v1/v3/v4）真实录制锁定
  （`LOCKED_COMMANDS`：OpenCadFile / OpenProject(path, False) /
  BeginSolidEdit / SetPartsControl / BuildAnalysisModel / CreateOctree /
  SetModeOctree / CreateMeshMonitor + WaitForWorker / SetModeMesh /
  SaveProject），未录制步骤保留在 `UNLOCKED_COMMANDS`；Wrapping 高层命令
  在 v1-v4 录制中均未出现，改由 NativeBridge 走 SCTprime 原生入口。

新增测试：`tests/test_vbs_bridge.py`、`tests/test_history_vbs.py`、
`tests/test_batch_bridge.py`、`tests/test_native_bridge.py`、
`tests/test_pipeline_plan.py`。

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
