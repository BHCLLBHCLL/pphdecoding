# PLAN — Parasolid 编辑（transform）与 SCTpre VBS 结果回写补全策略

> 日期：2026-08-15 ｜ 仓库：`pphdecoding` ｜ 结论：两块均可补全，且路径明确。

---

## 0. 执行摘要

两块都**不需要黑盒猜测**：

- **Parasolid** 有公开 V35 头文件文档（`q-solid.com` 完整托管）+ 可逆 `pskernel.dll`；
- **scFLOWpre** 有 VB 手册（`VB_Interface_eng`）+ 已实测通路的 COM API。

---

## 1. Parasolid 编辑（transform）

### 1.1 关键发现：公开文档给出了精确函数签名

Parasolid V35 文档（`q-solid.com`，公开托管）直接给出签名，与反汇编完全吻合：

```c
// 旧版（deprecated）
PK_ERROR_code_t PK_BODY_transform(
    PK_BODY_t body,          // 被变换体
    PK_TRANSF_t transf,      // 变换矩阵（按值传）
    double tolerance,        // 替换几何容差
    int *n_replaces,         // 被替换几何数（出）
    PK_GEOM_t **replaces,    // 被替换几何（出，可选）
    PK_LOGICAL_t **exact     // 是否精确（出，可选）
);

// 现行版（supersedes 旧版）
PK_ERROR_code_t PK_BODY_transform_2(
    PK_BODY_t body, PK_TRANSF_t transf, double tolerance,
    const PK_BODY_transform_o_t *options,
    PK_TOPOL_track_r_t *tracking, PK_TOPOL_local_r_t *results
);

// 选项结构（4 个 int = 16 字节）
struct PK_BODY_transform_o_s {
    int o_t_version;          // 版本号
    PK_LOGICAL_t merge_face;  // 是否合并相邻面（默认 true）
    PK_check_fa_fa_t check_fa_fa;  // 面-面一致性检查（默认 yes）
    PK_local_ops_update_t update;  // 局部操作更新标志
};

// 便捷构造：平移变换
PK_TRANSF_create_translation(PK_VECTOR_t displacement, PK_TRANSF_t *transf);
```

**这就是之前 3 参数调用崩溃的根因**——真实签名是 **6 参数**，`transf` 是
**按值传的 96 字节矩阵**（x64 下实际以指针传），`tolerance` 是第 3 个
`double` 参数。反汇编里 `mov edi, ecx`(body)、`movaps xmm6, xmm2`(tolerance
是 double)、`mov r14, [rbp+0x1710]`(第 5 参数) 正是这 6 参数布局的证据。

### 1.2 直接逆 pskernel.dll 的可行性——已证实可行

本仓库已有完整逆向工具链（均实测可用）：

- **capstone 5.0.7** 已安装；`tests/box/disasm_*.py`、`full_disasm_sctprime.py`
  等 30+ 个脚本已验证对 SCTprime/pskernel 的 PE 解析 + 反汇编 + 调用点分析；
- 实测：`PK_BODY_transform` @ RVA `0x119ae0`、`PK_BODY_transform_2` @ RVA
  `0x11ba10` 可成功反汇编，且反汇编出的参数布局与公开文档一致；
- 历史证明：`PK_TOPOL_facet_2_o_t`(version 5)、`PK_BODY_boolean_o_t`
  (o_t_version=2)、`PK_FACE_delete_o_t`(o_t_version=1) 都已用同一套工具逆向钉死。

### 1.3 transform 补全策略（按序）

| 步骤 | 内容 | 依据 |
|------|------|------|
| **S1（立即，零风险）** | 从 `cabdecoding/cab_ps_ops.py` 移植已验证的 `PK_BODY_boolean_2`（union/subtract/intersect，6 参数签名已锁定）+ `PK_FACE_delete`，作为「编辑」的第一条可用算子 | cabdecoding 已实测通过 |
| **S2（核心）** | 用 `PK_BODY_transform_2` + 6 参数签名 + `PK_BODY_transform_o_t`(4 int) + `PK_TRANSF_t` 实现平移/旋转 | 公开文档签名已拿到 |
| **S3（钉死矩阵 ABI）** | 反汇编 `PK_BODY_transform_2` 里 `transf` 的读取模式，确认 `PK_TRANSF_t` 是 `double[3][4]`(96B) 还是 `[4][4]`(128B)。反汇编已显示函数按 8×16 字节 = 128 字节拷贝变换（`movups [rax-0x60]…[rax+0x10]`），倾向 4×4 齐次矩阵 | 反汇编已观察到 |
| **S4（稳健）** | 改用 `PK_TRANSF_create_translation` 让内核自己构造变换（避免手工排布矩阵行列），再喂给 `PK_BODY_transform_2` | 公开文档 + 避免矩阵布局猜错 |
| **S5（可选）** | 仿照 cabdecoding 的 `transmit_parts` 用 `PK_BODY_ask_parent` 把 body tag 映射回 part 再 `PK_PART_transmit`，形成「编辑→编码」完整闭环 | 已交付 transmit |

**风险点**：仅剩 `PK_TRANSF_t` 的精确字节布局（96 vs 128 字节）与按值传递的
ABI 细节——通过 S3 反汇编 + S4 用内核构造函数可闭环，无不可逾越障碍。

---

## 2. SCTpre VBS 结果回写

### 2.1 手册确认了 API

`VB_Interface_eng/Scf_vb_Preprocessor_Application_Class.html` +
`Scf_vb_Preprocessor_Doc_Class.html` 明确列出：

- `ExecuteVBS(code)` / `ExecuteVBSWithFile(path)` — 执行 VBS；
- `GetDocument` → Document 类 → `OpenProject`（打开工程）、`OpenCadFile`、
  `SaveProject`；
- `GetApplication()` — 宿主内获取（方法 3），
  `CreateObject("scFLOWpre_Bx64net.Application.2025")` 是外部获取方式。

这与实测一致：**`ExecuteVBSWithFile` 已返回 True（脚本被接受）**。

### 2.2 结果文件为空的根因（3 个候选）

1. **VBS 编码/行尾**：`vbs_bridge.py` 用 `encode("utf-16")` + CRLF；此前手写
   的 `acceptance.vbs` 是 UTF-8、诊断 `hello.vbs` 是字面 `\r\n`（转义 bug）
   ——都会导致宿主 VBS 引擎解析失败/静默无输出；
2. **OpenProject 相对路径**：VBS 里 `OpenProject "box.pph", False` 用了相对
   路径，宿主 cwd 不是仓库目录 → 打开失败（被 `On Error Resume Next` 吞掉）；
3. **OpenProject 签名**：手册正文只写「Opens a project」，参数表在原始 HTML
   `<table>` 里（提取时被剥离），需核对是 `OpenProject(path)` 还是
   `OpenProject(path, flag)`。

### 2.3 VBS 回写补全策略

| 步骤 | 内容 |
|------|------|
| **V1** | 写一个正确 UTF-16 + CRLF 的最小 VBS（只 `FSO.CreateTextFile + WriteLine "hello"`），经 `ExecuteVBSWithFile` 执行，确认「宿主能写文件」这一前提成立 |
| **V2** | 逐层加 `GetApplication → GetDocument → OpenProject`（绝对路径），每层写 `Err.Number` 到结果文件，定位到哪一步断 |
| **V3** | 从手册 HTML `<table>` 提取 `OpenProject`/`OpenCadFile` 的确切参数表（此前只剥了正文文字，漏了表格） |
| **V4** | 一旦 OpenProject 成功，把「验收」落到：打开写端产出的改写 PPH（clone / 含新 GPH/MDL）→ 检查无报错，完成「布局一致」实证 |

---

## 3. 总体判断与建议执行顺序

1. **先做 S1（移植 boolean_2 + face_delete）**——零逆向风险、立刻获得「编辑」
   能力，且已有 cabdecoding 现成代码；
2. **再做 S3+S4（transform）**——用公开签名 + 内核 `PK_TRANSF_create_translation`
   闭环，避免手工矩阵踩坑；
3. **V1→V3（VBS）**——纯工程调试（编码+路径+签名），无逆向障碍。

**核心结论**：两块都不需要黑盒猜测——Parasolid 有公开 V35 头文件文档，
scFLOWpre 有 VB 手册；两者加上本仓库已验证的 capstone 反汇编工具链，足以把
`PK_TRANSF_t` 布局和 `OpenProject` 签名钉死，从而完整补全「Parasolid 编辑」与
「SCTpre VBS 结果回写」。