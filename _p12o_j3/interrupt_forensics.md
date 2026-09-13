# J3 中断代理取证（interrupt_forensics）

生成：2026-09-06。背景：J3-④ 三腿（probe/c1/c2）+ ② a1r 全被外部
作业控制中断代理在任意 sim-time 截停，等时终态双跑不可达。本文表征
中断机制、排除仓库内写入源、记录对 a1 系列归因的影响。

## 1. 观测事件表

| leg | 案例 | 截停机制 | cycle | TIME(solver) | 结局 |
|---|---|---|---|---|---|
| a1（I5） | exA36-3 | monalive 失联 → monitor_termination::killProcess | 1 | 692.1 s | BAD TERM RANK 1-7 |
| a1r（②） | exA36-3 | terminate 检出 → monitor_termination::killProcess | 2 | 952.1 s | BAD TERM RANK 1-7 |
| probe | exA36-2 | instruction 检出 → 优雅停 | 247 | 974.3 s | CALCULATION FINISH + 完整 fph/rph |
| c1 | exA36-2 | instruction 检出 → 优雅停 | 166 | ~1533 s | CALCULATION FINISH + 完整 fph/rph |
| c2 | exA36-2 | terminate 检出 → monitor_termination::killProcess | 70 | 1009.2 s | BAD TERM RANK 1-7 |

## 2. 两种截停机制

### 2.1 instruction 优雅停（probe、c1）

求解器在每个 cycle 末轮询 `<sph>.instruction` 文件。检出后：

```
+++ INTERRUPT FILE (scFLOWpre.sph.instruction) WAS FOUND +++
+++ REACHED END-TIME OF CALCULATION SPECFIED IN INTERRUPT FILE +++
...
***** CALCULATION FINISH AT ... *****
```

完整终态 fph/rph 落盘。日志正常收束。

### 2.2 terminate 硬杀（a1r、c2）

`monitor_termination::killProcess` 检出 terminate 文件后强杀所有 rank：

```
********** monitor_termination::killProcess **********
Since the terminate file was detected, this process will be killed.
...
=   BAD TERMINATION OF ONE OF YOUR APPLICATION PROCESSES
```

RANK 1-7 EXIT STATUS -1/ffffffff + mpiexec exit -1 记账。无终态保存
（c2 仅 t=0 初始 fph）。

### 2.3 a1（I5 原始）的 monalive 变体

```
********** monitor_termination::killProcess **********
Since the monalive file is no longer detected, this process will be killed.
```

monalive = 26 B ASCII 时间戳文件，mtime = 死亡时刻。与 terminate 同签名
BAD TERMINATION RANK 1-7，仅谓词不同。

## 3. instruction 文件格式

仅 probe_exb05 残留（该腿 license 失败，instruction 未被消费）：

```xml
<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<COMMANDS>
  <COMMAND Name="INTERRUPT">
    <VARIABLE Name="cycle" Value="-2"/>
    <VARIABLE Name="lapse_time">
      <YEAR>0</YEAR><MONTH>0</MONTH><DAY>0</DAY>
      <HOUR>0</HOUR><MINUTE>0</MINUTE><SECOND>0</SECOND>
    </VARIABLE>
  </COMMAND>
</COMMANDS>
```

cycle=-2 + lapse_time 全零 = **立即停**（非延迟停）。写入者 = 外部代理
（非求解器自身——求解器消费后删除文件，仅 license-fail 腿残留）。

## 4. 写入源排除（writer-hunt negatives）

| 排查面 | 方法 | 结果 |
|---|---|---|
| 仓库代码 | 全树 grep `instruction` / `INTERRUPT` / `terminate` / `monalive` | 无写入逻辑（仅 solver_run.py 的进程名匹配） |
| 其他会话 | list_chat_sessions + 唯一活跃会话检查 | 无其他项目会话在跑 |
| pph/sph/csln 策略 | 关键词 grep 工程文件 | 无 stop-policy 字段 |
| job 文件（csln/redirection） | 读 scFLOWpre.csln | 无时间限制/stop 指令 |
| VBS 脚本 | solve_vbs.vbs 仅 ExecuteSolver 后退出 | 无写 instruction/terminate 逻辑 |

→ 写入源 = **仓库外代理**。候选：Cradle scMonitor/JobLauncher 栈的
某策略守护进程、或本机安全/运维软件的进程寿命管控。具体身份超出本机
自动化可诊断面。

## 5. 对 a1 系列归因的影响

J3-② verdict = `CRASH_RECURRED_SAME_SIGNATURE_952s_ISOLATED`，原始
归因 = 「ELEC/FVF 长内环相位与 monitor-liveness 契约的求解器内部交互」。

J3-④ 新证据：c2（exA36-2 P2D 路径，**非 ELEC/FVF**）同样被 terminate
机制以同签名 BAD TERMINATION RANK 1-7 击杀 → ELEC/FVF 相位特异性
**不成立**。修正归因：

- a1/a1r/c2 的 BAD TERMINATION = 外部作业控制代理写 terminate 文件 →
  monitor_termination::killProcess 强杀（**非求解器内部缺陷**）
- a1 的 monalive 变体 = 同一外部代理的另一种干预模式（心跳文件删除/
  过期）
- 资源轨迹平稳（a1r 719→768 MB 无泄漏）+ 独占下仍复发 → 并发/资源
  耗尽假设排除（与 ② 一致）
- 「ELEC/FVF 相位特异」归因**撤回**，替换为「外部作业控制中断代理」

## 6. 对 J3-④ 双跑的影响

等时终态双跑要求两腿跑到相同 sim-time 后比较终态。外部代理在任意
sim-time 截停 → 等时不可控。本夜交付：

- t=0 初始保存三腿跨冷启动逐位一致（gate PASS 11/11）=  genuine
  复现点（案例泛化，非 box 专属）
- c1@166 vs c2@0 不等时比较 FAIL 归因 = 纯演化量（工具 sanity 验证）
- 中断机制全表征入册（本文）

等时终态双跑 = 需在无外部代理干预的窗口重跑（或 vendor 侧配合禁用
instruction/terminate 机制），列为后续可选动作。
