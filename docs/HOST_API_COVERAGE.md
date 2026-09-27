# 宿主 VB API 覆盖与能力边界（收口一页）

> 自动生成：`python tools/host_coverage_doc.py`（数字取自 `schemas/`；口径与边界写死在本工具里，便于审阅与反驳）。
> 详细轮次记录见 `docs/ROUNDS.md`（R45–R55），审计细节见 `docs/CODE_STATE_AUDIT_20260906.md`（§59–§67）。

## 1. 结论（一行）

**155/199 类**（3925/4455 成员）已用 `GetIDsOfNames` 逐名普查；宿主未实现 **27 条**；取不到实例的类 **4 个**；剩余 29 个**全部有终态**。

证据轮次：R50（2026-09-23T20:52:01），日志 `_p12u_gate\r50\name_verdicts.json`，工程集 box.pph, exB01-1_intake_manifold.pph, exA26-1_ldc.pph, exA16-2.pph, exA25-1.pph, exA18-4.pph。

## 2. 口径（怎么判的）

- **成员可用性**：`IDispatch::GetIDsOfNames` 逐个解析手册成员名，只解析不调用（零副作用）；`DISP_E_UNKNOWNNAME` 即宿主未实现。
- **对象取法**：三层配方（手册 `instance` → 目录声明在已持有宿主上的取用成员 → 命名片段），实参按手册词表与阶梯给；**验身**（该类独有成员解析率 ≥ 半数）通过才收。
- **假证据闸门**：整类未知过半不记（`swept_suspect`）；派发名不通时回退成员键名；标量返回不算对象。

## 3. 桶分布（互斥且守恒）

| 桶 | 数量 |
|---|---|
| 已普查 | **155** |
| 取不到实例（缺前置流程） | 4 |
| 取到但手册无成员 | 11 |
| 从未尝试 | 29 |
| **合计** | **199** |

## 4. 未实现成员（27 条 / 17 类）

> Python 侧不会为这些条目造包装；调用前会被拦下（typed 直调与 VBS 生成共用同一判据），并给出下一步。

- `ClosedVolume` — GetSweepDestinationFaceRegion / ImportCSV
- `CondBoundaryFlowIO` — GetMassVolumePressureInflowDirectionType​ / GetPbmFuncType / SetPbmFuncType
- `CondFreeSurface` — GetPhaseCheangeSw / SetPhaseCheangeSw
- `CondInitial` — GetPbmFuncType / SetPbmFuncType
- `CondInitialShapeModify` — RemoveMorphingRegion
- `CondOutputTimeSeries` — GetProjectonType / SetProjectonType
- `CondPorousMedia` — ImportCSV
- `CondSource` — IsEnableConditionForCalculation
- `CoordinatesSpecifiedPart` — GetRadiationValue / ImportCSV
- `Doc` — GetAllMapCondNames
- `FaceRegionDerivedSheet` — ImportCSV
- `FluidRegion` — ImportCSV
- `IVEdge` — GetPart / IsEqual
- `MeshingGroup` — GetDiscontinuous / ReplaceMDLMode / SetDiscontinuous
- `MeshingGroupSetting` — GetInternalUnit
- `SpecialRegion` — ImportCSV
- `VolumeRegion` — GetSweepDestinationFaceRegion

## 5. 未普查类终态分布

| 终态 | 数量 |
|---|---|
| `needs-corpus` | 25 |
| `host-interface-absent` | 0 |
| `no-creation-path` | 2 |
| `call-rejected` | 2 |
| `foreign-app` | 0 |
| `probe-limitation` | 0 |

## 6. 缺语料：补上能多覆盖几类、要什么算例

| 组 | 类数 | 预计可覆盖 | 成本档 | 要什么算例 |
|---|---|---|---|---|
| CoSim | 3 | 3 | 大 | 一个**CoSim 设置**算例（结构耦合侧配合，本机语料没有） |
| 其他 | 3 | 3 | 小 | 同条件/向导：多数是「建一个对象就有」的类 |
| 几何/MDL | 5 | 3 | 中 | 一个跑完 MDL/BAM 的算例（面区域→闭空间；本仓 exB01 类算例可复用） |
| 材料/物性 | 1 | 0 | 中 | 一个**注册了材料**的算例（材料库/物性表；本机算例多含） |
| 条件/向导 | 3 | 3 | 小 | 任取一个算例，用条件向导建一个该类条件（分钟级） |
| 混合物/燃烧 | 4 | 3 | 中 | 一个带**混合气体/燃烧**设置的条件算例（需专门设置） |
| 粒子/DEM | 6 | 6 | 大 | 一个**粒子/DEM 算例**（粒子发生/属性/边界一整套条件） |

合计预计可覆盖 **21 类**（无取法的类单列在 `no_path`，见 `schemas/unswept_account.json`）。

## 7. 复验窗口（何时重开）

一条命令：`python tools/sweep_reopen_check.py`（建议重开 → exit 1）。
硬理由：宿主版本变化 / 目录成员集与证据对不上 / 覆盖率低于收口下限（155）。软信息：工程集变化、目录被重生成。
重开时先复查谁：`python tools/sweep_reopen_check.py --watchlist`（suspect / 近阈否 / 无结论 / 空对象 / 无成员五档，各有可执行动作）。

## 8. 适用边界（不许外推）

- 只覆盖本机 Cradle 2025.2 + `scFLOWpre_Bx64net.Application.2025`；换版本必须重跑。
- 只覆盖**6 个算例**（box.pph + 5 个 Exercise）能提供的对象；语料缺失的类一律记 `needs-corpus`，**不代表宿主没有**该功能。
- `host_absent` 只说明「这个名字在宿主上解析不到」，**不**说明「功能不存在」（手册拼写错、别名、宿主另有入口都可能）。
- 普查结论**不替代**实机功能验收：单个功能的验收仍以端到端跑通为准。

---

复验入口汇总：`tools/host_member_sweep.py`（重跑普查）、`tools/unswept_account.py`（终态归因）、`tools/sweep_reopen_check.py`（复验窗口/盯防）、`tools/api_contract_check.py`（契约门 10 项 + `--self-test`）。
