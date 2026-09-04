# PPH Viewer NYI 菜单清单

> 由 `tools/scan_nyi_menus.py` 自动生成。
> 对应日志：`[…] not available in PPH viewer`（现已灰显）。

合计 **1** 项。P4-4 逐项评估见各条附注。

## Ridge

- Restore Closed Volume Data… — **产品边界**：仅 patch 导入 + Store and Open 再导入场景可用。

## 产品边界声明（Sprint H5 统一入册）

### CATIA V4/V5/V6 导入（域 4）

**产品边界**：全机 0 真 CATIA 几何样本（CATPart/CATProduct/cgr 均无；命中仅为 HDF5 `.exp`/链接器 export/Datakit `dtk.model` schema 误报）；Datakit schema 在位证明宿主 CATIA 转换链已装。样本缺失非代码缺口（§18.8 G3 裁决，2026-09-01）。

### Actran Acoustic（域 3 菜单 / 域 8 链）

**产品边界**：typed 接线链绿（`CreateActranFiles` e2e err=0）但业务 retval=False——Acoustic Session 前置在本机无样本可构造；菜单已接线，前置具备即可复验（P12-F §10.8 如实记录）。

### Restore Closed Volume Data…（域 10）

**产品边界**：仅 patch 导入 + Store and Open 再导入场景可用（P4-4 评估沿用）。


### 宿主大 VBS 执行能力时变（自动化基建，I2 遗留④）

**宿主侧边界（2026-09-04 表征，DEV_PLAN §20.6）**：同一宿主版本
（2025.2）对 `ExecuteVBSWithFile` 的可执行性随时间退化——08:00–
10:16 大录制（553–608KB，wrap 三次全量 + bam 前缀二分至 8910 行）
可完整执行；10:23 起系统性拒绝（大文件 RPC_E_SERVERCALL_REJECTED /
返回 False，至 12:35 连 2KB 脚本皆拒，仅 boot 后 VBS 可达性 probe
瞬间可达）。已排除：磁盘（D: 17.4GB 空闲）、Defender（无 1116/
1117 事件）、脚本编码/续行/块配对、文件锁、ROT 僵尸、模态。疑似
宿主许可/会话侧耗尽。自愈侧对策已建（watchdog 重试 + cold_boot
健康检查 + 断点续跑）；gate 复验策略 = 宿主机重启或次日首跑窗口。
