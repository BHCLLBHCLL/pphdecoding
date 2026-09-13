# P12-O J3 exA36-2 第二案例 delta 汇总（收口版）

生成：2026-09-06 00:24:52。案例：exA36-2（官方瞬态 5918 单元 + BATTERY p2d 电化学内模，
ENERGY-only；sph 电流脚本 TABLE (0,3)/(200,0)/(300,3) = 3 A 放电至 t=200 s
后静置）。三腿 = 三次独立冷启动宿主会话（probe 22:57、c1 23:31、c2 23:58）。

## 腿一览（截停机制详见 interrupt_forensics.md）

| leg | 起 | 终 | 截停 | cycle | TIME(solver) | 结局 |
|---|---|---|---|---|---|---|
| probe | 22:57:53 | 23:13:17 | instruction 优雅停（INTERRUPT FILE 检出） | 247 | 974.3 s | CALCULATION FINISH + 完整终态 fph/rph |
| c1 | 23:31:52 | 23:57:33 | instruction 优雅停 | 166 | ~1533 s | CALCULATION FINISH + 完整终态 fph/rph |
| c2 | 23:58:49 | 00:15:22 | terminate 检出（monitor_termination::killProcess） | 70 | 1009.2 s | BAD TERMINATION RANK 1-7，仅 t=0 初始 fph |

## 表 1：三腿 t=0 初始保存逐位一致（等时复现点）

c1_0 vs c2_0 / c1_0 vs probe_0（初始保存，mesh+sph→solver 初始化）：
**gate tol=0 双 PASS，11/11 场逐位一致**（0 fail / 0 only_a / 0 only_b）。

| 场 | 判定 | 注 |
|---|---|---|
| EC_Scalar:BCUR | PASS |  |
| EC_Scalar:BSOC | PASS |  |
| EC_Scalar:BVLT | PASS |  |
| EC_Scalar:ENTL | PASS |  |
| EC_Scalar:TEMP | PASS |  |
| EC_Scalar:TEPS | PASS |  |
| EC_Scalar:TURK | PASS |  |
| FC_Scalar:HTFX | PASS |  |
| FC_Scalar:TEMP | PASS |  |
| FC_Scalar:TEPS | PASS |  |
| FC_Scalar:TURK | PASS |  |

→ mesh/gph/sph→求解器初始化链路跨冷启动**逐位可复现**（案例泛化，非 box
专属）。sph md5 差异仅 `% Date` 行 + FPH/RPH/ETCO 干名（c1/c2 两行级
diff 实证）——非物理配置差异。

## 表 2：双跑原配对 c1@166(final) vs c2@0(t=0)（gate tol 0）

两腿被外部作业控制代理在**任意 sim-time** 截停（c1=166 s 放电期优雅停、
c2=70 s 放电期 terminate 杀）→ 终态 sim-time 不等（且 c2 无终态保存），
gate FAIL **归因 = 不等时比较，非数值发散**：

| 场 | 判定 | 注 |
|---|---|---|
| EC_Scalar:BCUR | PASS |  |
| EC_Scalar:BSOC | FAIL | delta_max 0.0713081 > tol_max 0 |
| EC_Scalar:BVLT | FAIL | delta_max 0.0136318 > tol_max 0 |
| EC_Scalar:ENTL | FAIL | delta_max 775.824 > tol_max 0 |
| EC_Scalar:TEMP | FAIL | delta_max 0.923601 > tol_max 0 |
| EC_Scalar:TEPS | PASS |  |
| EC_Scalar:TURK | PASS |  |
| FC_Scalar:HTFX | PASS |  |
| FC_Scalar:TEMP | FAIL | delta_max 0.923601 > tol_max 0 |
| FC_Scalar:TEPS | PASS |  |
| FC_Scalar:TURK | PASS |  |

6/11 PASS = 脚本/BC 常量场（BCUR=脚本 3 A 恒定、TEPS/TURK=湍流关闭的
初值常数、HTFX=BC 驱动面热流）——**两腿物理同一性的场级旁证**；5/11
FAIL = 演化状态场（TEMP 差 +0.9236 K、ENTL 775.8、BSOC 0.0713、
BVLT 0.0136）与 c1 由 t0→t166 演化量同号同量级（表 3 验证）。gate 工具
在该案例上正确判别演化状态（富 11 场含 BSOC/BVLT/BCUR 电池三标量）。

## 表 3：c1@166 vs c1@0（同腿演化对照，gate tol 0）

演化场 delta_max 与表 2 一致 → 表 2 FAIL 量 = 纯演化量，无额外发散。
