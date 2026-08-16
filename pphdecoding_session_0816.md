# pphdecoding 会话记录 — 2026-08-16

> 任务主线：按改进计划从 P0 到 P3 进行代码改进（P0~P2 及 P3-1/P3-2 已在此前会话完成）。
> 本会话：收尾 P3-3（NYI 菜单本地实现）测试修复 → P3-4（测试补充 + 全量回归）→ 待收尾文档。

## 1. 会话起点

- 上次会话遗留：P3-3 三个菜单（Select by Element Number / Select Faces That Have the Same Area / Check Intersection）已实现，但 `tests/test_mdl_analysis.py` 中 `test_shared_interface_ignored` / `test_touching_boxes_not_reported` 失败（贴合盒误报穿越）。
- P3-4（全量回归）与收尾文档为待办。

## 2. P3-3 修复：贴合面误报穿越（mdl.py）

### 2.1 现象

两个仅共面贴合/共享邻边的盒子被报为"体间穿越"（34 处命中），首例 `face_a=2, face_b=6`。

### 2.2 诊断过程

1. 最小复现：`_mdl_from_boxes([盒A, 盒B])`，A 的 y- 面（face 2）与 B 的 x- 面（face 6）共享边 `(1,0,0)-(1,0,1)`。
2. 三角形级验证：共享 2 个顶点的三角形对 `_tri_tri_crossing=True`（边恰好从对方三角形平面上掠过，属于数值边界的"伪穿越"），设计上应由**顶点邻近过滤**排除。
3. 检查过滤逻辑（旧实现）：用 `cKDTree` 查 A 侧每个 flat 顶点在 B 侧的**全局最近点索引** `a2b`，命中当前检测三角形（`3*ib..3*ib+2`）才跳过。
4. 根因：最近点是**全局**的——贴合边顶点在 B 集合中大量重复出现（属于很多别的三角形），最近点索引常常不属于当前配对的三角形 `ib`，过滤漏判；scipy 亦非必需依赖。

### 2.3 修复

`_intersect_face_sets`（[mdl.py](file:///d:/training/cgns/pphdecoding/mdl.py#L744)）改为对每个 AABB 候选对直接做 3×3 顶点距离判断：

```python
tri_a_pts = ma.xyz[ta.reshape(-1)].reshape(-1, 3, 3)
tri_b_pts = mb.xyz[tb.reshape(-1)].reshape(-1, 3, 3)
pairs = _aabb_cross_pairs(tri_a_pts, tri_b_pts, cap=max_pairs)
tol2 = vertex_tol * vertex_tol
for ia, ib in pairs:
    # 顶点邻近过滤（拓扑连接/装配贴合）：任一顶点对几何重合 → 跳过
    if tol2 > 0.0:
        d2 = ((tri_a_pts[ia][:, None, :] - tri_b_pts[ib][None]) ** 2)
        if float(d2.sum(-1).min()) < tol2:
            continue
    if _tri_tri_crossing(tri_a_pts[ia], tri_b_pts[ib]):
        ...
```

- 候选对粒度精确、语义正确（就是"这对三角形是否共享几何顶点"），去掉了 scipy 依赖。
- 结果：`tests/test_mdl_analysis.py` 14 项全部通过，P3-3 完成。

## 3. P3-4：全量回归

### 3.1 环境问题排查

| 问题 | 结论 |
| --- | --- |
| `python -m pytest` 无模块 | 当前终端 python 是 TRAE 自带解释器，无 pytest/PyQt5 |
| 系统 python 探测 | `C:\ProgramData\anaconda3\python.exe` 具备 PyQt5/scipy/vtk，作为回归解释器 |
| PowerShell 重定向把 stderr 混成 CLIXML 噪声 | 回归改为 python 进程内重定向到文件 |
- 沙箱拦截 anaconda site-packages 的 pyc 写入 → 加 `-B` / `PYTHONDONTWRITEBYTECODE=1`。

### 3.2 单进程 discover 崩溃（0xC0000005）定位

1. 单独跑 `tests.test_native_bridge` 全过；与 `test_host_pipeline` 合跑也过 → 需要组合定位。
2. 写 `bisect_crash.py`（逐对 `{m, test_native_bridge}` 子进程探测）：
   - **`test_generic_cond_form` + bridge 实机调用 → 0xC0000005**（Qt offscreen 与厂商 DLL 同进程混载触发访问冲突）。
   - 其余 70+ 模块组合均 ok。
3. 决策：
   - `TestNativeBridgeReal` 加环境变量门控 `SCF_RUN_BRIDGE_TESTS=1`，不默认混入回归（[tests/test_native_bridge.py](file:///d:/training/cgns/pphdecoding/tests/test_native_bridge.py#L71)）。
   - 单进程 discover 仍在 `test_register_region` 处崩（跨模块状态污染）→ **全量回归改为逐模块子进程隔离**，落地为 [run_all_tests.py](file:///d:/training/cgns/pphdecoding/run_all_tests.py)：
     - 每模块独立进程跑 `python -B -m unittest tests.<m> -v`；
     - 汇总 tests/failures/errors/skipped；rc=5（unittest 收集不到的 pytest 风格模块）标记 `[pyst]` 不计失败；
     - 期间修掉脚本自身一个 `globals()` 局部变量 KeyError。

### 3.3 逐模块回归暴露的真实缺陷（均已修复）

#### (a) test_parts_control — `_nav_keys` 辅助过时

- 失败：`begin_wrap not found in [...]`。
- 分析：实现（[pph_gui.py](file:///d:/training/cgns/pphdecoding/pph_gui.py#L973) `_nav_nodes`）把 Wrapping 执行项（begin_wrap 等）作为**顶级 leaf**插入（对齐手册：与 Prepare Parts 同级、Mesher/Faceter 之前），而测试辅助只收集分组节点下的 child。
- 修复：`_nav_keys` 兼容顶级 leaf（[tests/test_parts_control.py](file:///d:/training/cgns/pphdecoding/tests/test_parts_control.py#L24)）。

#### (b) test_generic_cond_form — 写回校验 50 个 missing required

- 失败：`test_write_and_validate_flow_io` 中 registry 校验报 50 条 `missing required field: *.input` 等。
- 分析：`CondBoundaryFlowIO` 有 414 个 required 字段，其中 50 个 `kind=empty`（语料中就是空元素形态如 `<input/>`，无文本样本→无 default）、49 个 composite 父节点。测试只写"required 且有 default"的字段 → empty 字段永远缺失。
- 修复（测试侧，[tests/test_generic_cond_form.py](file:///d:/training/cgns/pphdecoding/tests/test_generic_cond_form.py#L127)）：required 且（有 default 或 kind=empty）都写入；empty 写空元素；composite 父节点由子路径写入时自动创建（`_ensure` 逻辑已具备）。

#### (c) test_generic_cond_form — `GenericCondBody._build_group` 无限递归（真 bug）

- 现象：单独跑该类先 `RecursionError`（982 层），随后 Qt 深层级控件析构直接把进程杀成 0xC0000005——这就是 3.2 中"与 native_bridge 组合崩溃"的真凶之一（同进程内的 Qt 崩溃）。
- 诊断：用纯逻辑复刻分组递归并限深打印，看到前缀演化为
  `velocity_vertical_value` → `velocity_vertical_value.`（尾点）→ `velocity_vertical_value..velocity_vertical_value` → …
- 根因（[nav_panels.py](file:///d:/training/cgns/pphdecoding/nav_panels.py#L13887) 旧代码）：
  ```python
  seg = name[len(prefix):]   # 只剥了前缀，没剥分隔点！
  ```
  `seg` 带前导 `.` → `parent_seg = seg.split(".",1)[0]` 得空串 → `sub_prefix` 尾点 → 下一层所有名字都不匹配 `prefix + "."` → seg 又回到全名 → 再切出同样的 parent_seg → 无限递归。
- 修复：
  ```python
  seg = name[len(prefix) + 1:] if prefix and name.startswith(prefix + ".") else name
  ```
  （注：该 bug 由 P1-2 的通用表单引入，`velocity_vertical_value` 这类"复合节点带同名叶子路径"的 schema 触发。）

#### (d) `_validate` 对 empty/composite 必填字段误报

- 递归修复后暴露：表单校验对 414 个 required 里的 50 empty + 49 composite 报 `Required field empty`（它们本来就没有文本值）。
- 修复（[nav_panels.py](file:///d:/training/cgns/pphdecoding/nav_panels.py#L13950)）：`kind in ("empty", "composite")` 跳过"必填非空"检查。

### 3.4 回归结果（截至本记录）

- `tests.test_generic_cond_form`：**10 项全过**（含表单构建 + 写回闭环）。
- `tests.test_parts_control` + `tests.test_native_bridge`（实机门控后）：11 项 OK（skipped=3）。
- `tests.test_mdl_analysis`：14 项 OK。
- 其余模块在最近一轮 `run_all_tests.py` 中除上述已修复项外均 ok（`[pyst]` 标记的 pytest 风格模块需用 pytest 跑，当前环境没有）。
- **待办：跑一轮完整 `run_all_tests.py` 确认全绿。**

## 4. 本会话文件变更清单

| 文件 | 变更 |
| --- | --- |
| [mdl.py](file:///d:/training/cgns/pphdecoding/mdl.py) | `_intersect_face_sets` 顶点邻近过滤重写（3×3 距离判断，去 scipy） |
| [tests/test_native_bridge.py](file:///d:/training/cgns/pphdecoding/tests/test_native_bridge.py) | `TestNativeBridgeReal` 加 `SCF_RUN_BRIDGE_TESTS=1` 门控 |
| [tests/test_parts_control.py](file:///d:/training/cgns/pphdecoding/tests/test_parts_control.py) | `_nav_keys` 兼容顶级 leaf |
| [tests/test_generic_cond_form.py](file:///d:/training/cgns/pphdecoding/tests/test_generic_cond_form.py) | required+empty 字段写入空元素 |
| [nav_panels.py](file:///d:/training/cgns/pphdecoding/nav_panels.py) | `_build_group` 前缀切片少剥一个点导致的无限递归修复；`_validate` 跳过 empty/composite |
| [run_all_tests.py](file:///d:/training/cgns/pphdecoding/run_all_tests.py) | 新增：逐模块子进程隔离的全量回归 runner |

## 5. 待办（下一步）

1. ~~跑完整 `run_all_tests.py`（anaconda python）确认全绿~~ —— 已完成（见 §7）。
2. ~~收尾文档：更新 `function_gap_analysis.md` / `DEV_PLAN.md §17` / `DEV_SUMMARY.md §7`~~ —— 已完成（见 §8）。

## 6. 续跑（P3-4 收尾）：全量回归两处问题的定位与修复

首轮完整回归（73 模块）：544 tests、2 failures（`test_semantics`）、
`test_register_region` 崩溃（rc=0xC0000005）。此前会话从未跑到 R/S
之后的模块（单进程 discover 在 register_region 即崩），属**新暴露的
存量问题**，非本会话改动引入（HEAD 版 sctsnapshot 复测结果完全一致）。

### 6.1 test_semantics 2 处失败：box 样本错配

- 根因：根目录 `box.pph` 已被 8-13 提交 0336d7d（"refreshed box
  sample"）换成内部八叉树 **20105 节点**的新样本，而
  `tests/box/meshinggroup1.oct` 等配套仍是原 **2249 节点**保存
  （7/31，未随刷新）。测试拿"新快照 × 旧 .oct"做 OCTREEREGION
  交叉验证，`octree_region(n_octants=2249)` 把新缓冲截断到 2249，
  断言全成噪声。
- 修复（[tests/test_semantics.py](file:///d:/training/cgns/pphdecoding/tests/test_semantics.py)）：box 侧改用
  `tests/box/main.sctsnapshot`（与 .oct/.mdl 同一保存的原始快照，
  已验证满足全部原始钉死值：restrict=[]、{4:64, 5:819}、883 叶、
  y≥0）；`_load_snap` 支持裸 .sctsnapshot 输入。

### 6.2 test_register_region 崩溃：QMessageBox × offscreen 原生崩溃

- faulthandler 定位：崩溃在 [nav_panels.py](file:///d:/training/cgns/pphdecoding/nav_panels.py) `_register_surface` 尾部的
  `QMessageBox.information`；最小复现（offscreen + 裸
  `QMessageBox.information(QWidget, ...)`）同样 0xC0000005——
  **anaconda PyQt5 在 offscreen 平台下模态静态弹窗必崩**。
  此前"单进程 discover 在 test_register_region 崩 = 跨模块污染"
  的判断有误，真凶就是 QMessageBox。
- 修复：nav_panels.py 新增 `patch_message_box_offscreen()`（导入期
  调用）：offscreen 时把 information/warning/critical/question 四个
  静态方法替换为日志打印（question 返回 Yes）。pph_gui 经
  `import nav_panels` 自动覆盖；option_settings/option_dialogs 内
  4 处调用仅在错误路径触发，暂未接线。

### 6.3 终轮回归（全绿）

```
== 549 tests, 0 failures, 0 errors, 3 skipped; 0 failed modules, 0 crashed modules
```

（544 + test_register_region 5 项；skipped 3 = 实机桥门控。）

## 7. 收尾文档（P0~P3 完成状态）

- [function_gap_analysis.md](file:///d:/training/cgns/pphdecoding/function_gap_analysis.md) §4：新增执行状态表（P0~P3 逐项交付 + 回归证据）与剩余长尾清单。
- [DEV_PLAN.md](file:///d:/training/cgns/pphdecoding/DEV_PLAN.md) §17.2：新增执行状态引言（549 全绿 + 长尾）。
- [DEV_SUMMARY.md](file:///d:/training/cgns/pphdecoding/DEV_SUMMARY.md) §7：新增「P0–P3 执行结果」段（哑铃结构收敛：条件表单全覆盖、几何编辑落地、网格质量基础设施、NYI 11→8）。

## 8. 经验教训（续）

- **样本三件套（pph/.oct/.mdl）必须同源配对**：刷新 pph 而不刷新
  tests/ 下的配套提取文件，交叉验证测试会静默错配；`octree_region
  (n_octants)` 的截断语义还会掩盖长度不一致。
- **offscreen + QMessageBox 静态弹窗在该 PyQt5 构建下必崩**（模态
  exec 无窗口系统）；GUI 代码要经单点 guard 打补丁，不能指望
  "跨模块污染"解释一切进程内崩溃。
- gitignore 掉 tests/ 目录会让"测试是否曾经绿过"无从考证——排障时
  先 `git check-ignore` 确认测试文件版本状态。
- faulthandler.enable() + 最小复现脚本是钉死 Qt 原生崩溃位置的最快
  路径（栈直接指向出错 Python 行）。

## 9. 本会话续跑文件变更清单

| 文件 | 变更 |
| --- | --- |
| [tests/test_semantics.py](file:///d:/training/cgns/pphdecoding/tests/test_semantics.py) | box 快照改用 tests/box/main.sctsnapshot（同源配对）；_load_snap 支持裸快照 |
| [nav_panels.py](file:///d:/training/cgns/pphdecoding/nav_panels.py) | 新增 patch_message_box_offscreen()（offscreen 下 QMessageBox 静态弹窗改日志） |
| [function_gap_analysis.md](file:///d:/training/cgns/pphdecoding/function_gap_analysis.md) / [DEV_PLAN.md](file:///d:/training/cgns/pphdecoding/DEV_PLAN.md) / [DEV_SUMMARY.md](file:///d:/training/cgns/pphdecoding/DEV_SUMMARY.md) | P0~P3 完成状态收尾 |

## 10. P4 执行（续跑二：P4-2 收尾 + P4-3 + P4-4）

### 10.1 P4-2 材料五库收尾

- [material_lib.py](file:///d:/training/cgns/pphdecoding/material_lib.py)
  `parse_reaction_species` 组分解析修复：实测格式为
  `<component no="1"> C,1 </component>`（元素,个数 逗号分隔），
  原按 "C 1, H 4" 空格对解析必空；16/16 tests 全绿
  （anaconda python + offscreen，GUI 4 项含）。

### 10.2 P4-3 自动化生态

- **Disc/Overset 录制锁定**：box_com_diag4.vbs/.log — COM 宿主内
  `SetPartsControl "Discontinuous"/"Overset"` True/False 四种调用
  全部 err=0；结论回填 [automation/pipeline_plan.py](file:///d:/training/cgns/pphdecoding/automation/pipeline_plan.py)。
- **COM ProgID 注册表探测**：windtool VBS 注释背书的厂商 ProgID
  （STtools.vbs:4 / STpre_STsolver.vbs:7-8）落
  [scflowpre_probe.py](file:///d:/training/cgns/pphdecoding/scflowpre_probe.py)
  `COM_PROGIDS` + `probe_com_progpids()`（HKCR 只读；实测 scFLOWpre/
  STpre/scConverter S/D 已注册，STsolver/scPOST 未装）；接入 `probe()`
  与 `host_pipeline.locate_scflowpre()`（related_progpids 字段）。
- **SCTpreCLIHelper 实测结论落档**：子命令清单 + 校验顺序
  （先存在后扩展名；.pph not supported，CLI 面向 SC/Tetra 工程）写入
  [automation/batch_bridge.py](file:///d:/training/cgns/pphdecoding/automation/batch_bridge.py)
  模块头；全链 dry-run 需 SC/Tetra 工程样本（用户决策：跳过实测只落码）。

### 10.3 P4-4 边际收尾

- **NYI 8 → 7**：Select Elements by List File… 接线
  （[pph_gui.py](file:///d:/training/cgns/pphdecoding/pph_gui.py)
  `_select_by_list_file`，复用 `_parse_element_numbers`）；其余 7 项
  逐项评估落 [tools/scan_nyi_menus.py](file:///d:/training/cgns/pphdecoding/tools/scan_nyi_menus.py)
  `EVALUATIONS`（2 产品边界 + 5 暂缓，依据 Pre_eng 帮助页），
  docs/NYI_INVENTORY.md 自动生成附注。
- **黄金文件集 5 真实项目**：box / box2 / laptop 之外，经 COM 宿主
  SaveProject 新生成 tests/box_disc.pph（main.xml 落
  `<Discontinuous>true`）与 tests/box_overset.pph（登记
  `*_mapped.bdf`/`*_RotorInfo`）；证据 box_com_diag5.vbs/.log；
  [tests/test_samples.py](file:///d:/training/cgns/pphdecoding/tests/test_samples.py)
  自动纳入并更新黄金集文档。

### 10.4 P4 终轮回归

```
Ran 594 tests in 351.918s
OK (skipped=3)
```

（P3 末 549 → 594：+45 项新增测试；skipped 3 = 实机桥门控。
回归日志 regression_p4.log；注意 sandbox 下须 `python -B` 防
site-packages pyc 写入被拦。）

## 11. 原会话经验教训（原 §6，存档）

- **顶点邻近过滤要在"候选对"粒度判定**，全局最近邻索引在顶点重复出现的面片网格里必然漏判。
- **Qt offscreen + 厂商 COM/DLL 同进程混载**会随机 0xC0000005；实机桥测试必须环境变量门控、且全量回归用**逐模块子进程隔离**。
- 字符串前缀切片构建层级路径时，剥前缀务必**连分隔符一起剥**；此类 bug 的症状是"前缀尾部积累分隔符 + 无限递归"。
- 计数驱动的 required 推断对 `empty`/`composite` 形态字段要特殊处理（写回空元素、跳过非空校验），否则通用表单闭环必挂。
- 回归输出：PowerShell 下 stderr 会转 CLIXML 噪声，长输出统一 python 进程内重定向文件 + `-u` unbuffered。
