"""宿主 hang watchdog：批量流程的自愈执行器（DEV_PLAN §20.1 I2）。

背景（§18.4 遗留③）：rot 通道 ``ExecuteVBSWithFile`` 为同步 COM
调用、无超时；宿主会话在脏状态（曾挂过的会话内重开同文件）下
``OpenProject`` 可能 10–16 min 无模态无 err 挂起，调用永不返回。
本模块把执行移入 worker 线程，主线程按**日志活性**监视：
日志 ``idle`` 超过 ``idle_limit`` 且 worker 仍未返回 → 判定挂起 →
采集诊断 + MiniDump 转储 + 杀宿主 + 冷启动重建 + 重试（默认 1 次）。
每次处置追加表征台账（jsonl），积累遗留③数据点。

注入点（离线单测用）：``worker_fn``/``boot_fn``/``dump_fn``/
``kill_fn``/``diag_fn``/``idle_limit``/``poll``。
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import ctypes
from ctypes import wintypes

from automation import modal_watch

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
dbghelp = ctypes.windll.dbghelp

kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL,
                                 wintypes.DWORD]
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                 wintypes.DWORD, wintypes.LPVOID,
                                 wintypes.DWORD, wintypes.DWORD,
                                 wintypes.HANDLE]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
dbghelp.MiniDumpWriteDump.restype = wintypes.BOOL
dbghelp.MiniDumpWriteDump.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                      wintypes.HANDLE, wintypes.DWORD,
                                      wintypes.LPVOID, wintypes.LPVOID,
                                      wintypes.LPVOID]

GENERIC_WRITE = 0x40000000
CREATE_ALWAYS = 2
PROCESS_ALL_ACCESS = 0x1F0FFF
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


def write_minidump(pid: int, dump_path: str | Path) -> str | None:
    """对挂起进程写 MiniDumpNormal 转储（尽力而为，失败返回 None）。"""
    hproc = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not hproc:
        return None
    hfile = kernel32.CreateFileW(str(dump_path), GENERIC_WRITE, 0, None,
                                 CREATE_ALWAYS, 0, None)
    if hfile in (None, INVALID_HANDLE_VALUE):
        kernel32.CloseHandle(hproc)
        return None
    try:
        ok = dbghelp.MiniDumpWriteDump(hproc, pid, hfile, 0, None, None,
                                       None)
        return str(dump_path) if ok else None
    except Exception:  # noqa: BLE001
        return None
    finally:
        kernel32.CloseHandle(hfile)
        kernel32.CloseHandle(hproc)


def collect_process_diag(pid: int) -> dict:
    """采集挂起时刻进程画像（CPU/内存/线程/启动时刻）。"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process -Id " + str(pid)
             + " | Select-Object Id,CPU,WS,Threads,StartTime"
               " | ConvertTo-Json"],
            capture_output=True, text=True, timeout=20).stdout
        return json.loads(out) if out.strip() else {"pid": pid}
    except Exception as exc:  # noqa: BLE001
        return {"pid": pid, "error": repr(exc)}


def kill_pid(pid: int) -> bool:
    """强杀进程树并确认消失（taskkill 失败或未消失则重试一次）。"""
    for _ in range(2):
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                       capture_output=True, text=True, timeout=15)
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if not _pid_alive(pid):
                return True
            time.sleep(1.0)
    return not _pid_alive(pid)


def _pid_alive(pid: int) -> bool:
    """pid 是否存活。R3-1：优先无子进程的 OpenProcess 探针（毫秒级），
    PowerShell 仅作回退，且回退超时**保守判为存活**（绝不误判已死）。"""
    try:
        return modal_watch.pid_alive(pid)
    except Exception:  # noqa: BLE001
        pass
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process -Id " + str(pid) + " -ErrorAction SilentlyContinue"
             " | Select-Object -ExpandProperty Id"],
            capture_output=True, text=True, timeout=15).stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return True
    return bool(out)


def log_size(log: Path) -> int:
    try:
        return log.stat().st_size
    except OSError:
        return 0


#: R8-4：WER 报告目录（崩溃取证用；只读目录，不查事件日志——后者需权限）
WER_DIRS = (r"C:\ProgramData\Microsoft\Windows\WER\ReportArchive",
            r"C:\ProgramData\Microsoft\Windows\WER\ReportQueue")


def wer_reports(images=("scFLOWpre", "SCTpre", "STpre"),
                limit: int = 6) -> list[str]:
    """最近与本产品相关的 WER 报告目录名（R8-4；读不到就返回空表）。"""
    hits: list[tuple[float, str]] = []
    for d in WER_DIRS:
        try:
            entries = list(Path(d).iterdir())
        except OSError:
            continue
        for e in entries:
            name = e.name
            if not any(img.lower() in name.lower() for img in images):
                continue
            try:
                hits.append((e.stat().st_mtime, name))
            except OSError:
                continue
    hits.sort(reverse=True)
    return [n for _t, n in hits[:limit]]


def log_last_line(log: Path) -> str:
    """日志最后一条非空行（R4-2：host-gone 归因用）。"""
    try:
        lines = [ln.strip() for ln in
                 log.read_text(encoding="utf-8", errors="replace").splitlines()
                 if ln.strip()]
    except OSError:
        return ""
    return lines[-1][:200] if lines else ""


def has_end_marker(log: Path) -> bool:
    try:
        return "end" in log.read_text(encoding="utf-8",
                                      errors="replace").splitlines()
    except OSError:
        return False


class FlowExecutor:
    """单 flow 自愈执行：worker 执行 VBS + 主线程日志活性监视。

    ``worker_fn(vbs_path, timeout) -> dict`` 缺省为
    ``host_pipeline.run_vbs_authoritative``；``boot_fn() -> pid``
    缺省为 ``host_boot.cold_boot``（杀宿主后重建会话）。
    """

    def __init__(self, vbs_path: str | Path, log_path: str | Path, *,
                 name: str = "flow", timeout: float = 600.0,
                 idle_limit: float = 420.0, poll: float = 5.0,
                 attempts: int = 2, watch_modals: bool = True,
                 work_dir: str | Path | None = None,
                 worker_fn=None, boot_fn=None, dump_fn=write_minidump,
                 kill_fn=kill_pid, diag_fn=collect_process_diag,
                 host_fn=modal_watch.host_pids,
                 gone_check_after: float = 60.0,
                 gone_confirm: float = 30.0,
                 kill_all_fn=None, error_retry_delay: float = 20.0,
                 kill_settle: float = 2.0, retry_with_boot: bool = False,
                 cpu_fn=None, mem_fn=None,
                 cpu_progress_delta: float = 2.0,
                 worker_image: str = "scFLOWpre_Bx64net",
                 worker_pids_fn=None, wer_fn=wer_reports):
        self.vbs_path = Path(vbs_path)
        self.log_path = Path(log_path)
        self.name = name
        self.timeout = timeout
        self.idle_limit = idle_limit
        self.poll = poll
        self.attempts = attempts
        self.watch_modals = watch_modals
        self.work_dir = Path(work_dir) if work_dir else \
            self.log_path.parent
        self.characterization_path = self.work_dir / \
            "hang_characterization.jsonl"
        self._worker_fn = worker_fn
        self._boot_fn = boot_fn
        self._dump_fn = dump_fn
        self._kill_fn = kill_fn
        self._diag_fn = diag_fn
        self._host_fn = host_fn
        self.gone_check_after = gone_check_after
        self.gone_confirm = gone_confirm
        self._kill_all_fn = kill_all_fn
        self.error_retry_delay = error_retry_delay
        self.kill_settle = kill_settle
        # OpenCadFile 流（bam/wrap）：中止重跑前必须冷启动——上次执行
        # 半途而废时宿主里工程开着，OpenCadFile 会挂（P12-A 铁律）。

        self.retry_with_boot = retry_with_boot
        # R4-2：最后一次**探到**的宿主 pid。宿主消失后就再也问不到 pid 了，
        # 归因要靠这份快照（外加日志最后一行 / VBS 路径）。
        self._last_seen_hosts: list[int] = []
        # R5-1：进度信号。网格计算期间日志必然长时间不动（x_t 170 s、STEP 25 min），
        # 只按日志静默判活会误杀正常计算；CPU 在推进 = 还在干活。但**仅在宿主
        # 在场时才算数** —— 否则「宿主已死 + 工作进程空转」会被误判成健康
        # （R3-1/R4-1 的 host_gone 形态）。
        self._cpu_fn = cpu_fn or modal_watch.host_and_worker_cpu
        self._mem_fn = mem_fn or modal_watch.process_memory
        self.cpu_progress_delta = cpu_progress_delta
        self._last_cpu: float | None = None
        self._cpu_progress = 0
        self._host_seen_alive = False
        self._last_seen_mem: list[dict] = []
        # R8-4：R7-1 的教训 —— 真正崩的是**工作进程** scFLOWpre_Bx64net，而
        # 探针与台账此前只盯 STpre，于是「工作进程崩溃」被记成「宿主消失」。
        self.worker_image = worker_image
        self._worker_pids_fn = worker_pids_fn or (
            lambda: modal_watch.host_pids(worker_image))
        self._wer_fn = wer_fn
        self._last_seen_worker: list[int] = []
        self._last_seen_worker_mem: list[dict] = []

    def _kill_all(self) -> None:
        if self._kill_all_fn is not None:
            self._kill_all_fn()
            return
        from automation.host_boot import kill_all_hosts
        kill_all_hosts()

    # -- 注入缺省 ----------------------------------------------------------

    def _worker(self, vbs, timeout):
        if self._worker_fn is not None:
            return self._worker_fn(vbs, timeout)
        from automation import host_pipeline
        return host_pipeline.run_vbs_authoritative(vbs, timeout=timeout)

    def _boot(self):
        if self._boot_fn is not None:
            return self._boot_fn()
        from automation import host_boot
        return host_boot.cold_boot()

    # -- 主流程 ------------------------------------------------------------

    def _hosts(self) -> list[int]:
        return self._host_fn()

    def _hosts_safe(self):
        """宿主 pid 探针；异常/超时 → None（未知），**绝不当作已消失**。

        R3-1：忙时探针可能失败，把「未知」判成「宿主消失」会误杀正在做
        重网格计算的健康宿主（``_p12u_gate/hang_characterization.jsonl``
        的 step_mesh 行即此误判）。"""
        try:
            alive = self._host_fn()
        except Exception:  # noqa: BLE001
            return None
        if alive:
            # R5-1：宿主还在时采样内存 —— 它一消失就再也问不到了
            self._host_seen_alive = True
            mem = [m for m in (self._mem_fn(p) for p in alive) if m]
            if mem:
                self._last_seen_mem = mem
            # R8-4：工作进程同样要在它还在时采样（网格就跑在它里面）
            try:
                wpids = list(self._worker_pids_fn() or [])
            except Exception:  # noqa: BLE001
                wpids = []
            if wpids:
                self._last_seen_worker = wpids
                wmem = [m for m in (self._mem_fn(p) for p in wpids) if m]
                if wmem:
                    self._last_seen_worker_mem = wmem
        return alive

    def _cpu_progress_ok(self) -> bool:
        """R5-1：CPU 在推进 **且** 宿主在场 → 视为活性（重置日志惰性计时）。"""
        if not self._host_seen_alive:
            return False
        try:
            cpu = self._cpu_fn()
        except Exception:  # noqa: BLE001
            return False
        if cpu is None:
            return False
        prev, self._last_cpu = self._last_cpu, cpu
        if prev is None:
            return False
        return (cpu - prev) >= self.cpu_progress_delta

    def _characterize(self, attempt: int, outcome: str, reason: str,
                      idle_s: float, t_start: float,
                      reason_kind: str = "") -> dict:
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "flow": self.name, "attempt": attempt, "outcome": outcome,
               "reason": reason, "log": self.log_path.name,
               "log_bytes": log_size(self.log_path),
               "idle_s": round(idle_s, 1), "elapsed_s":
               round(time.time() - t_start, 1),
               "vbs_bytes": self.vbs_path.stat().st_size}
        if reason_kind:
            row["reason_kind"] = reason_kind
        if outcome in ("hung", "completed_no_return"):
            hosts = self._hosts_safe() or []
            row["host_pids"] = hosts
            row["host_diag"] = [self._diag_fn(p) for p in hosts]
            row["windows"] = [{k: w[k] for k in ("cls", "title")}
                              for h in hosts
                              for w in modal_watch.visible_windows(h)]
            if self._cpu_progress:
                row["cpu_progress_events"] = self._cpu_progress
            if reason_kind == "host_gone":
                # R4-2：宿主已经没了 —— 现查 pid 必然为空，归因靠「最后一次
                # 探到的 pid」+ 日志最后一行 + VBS 路径（三个都是判因线索）。
                row["host_gone"] = True
                row["last_seen_hosts"] = list(self._last_seen_hosts)
                row["last_seen_diag"] = [self._diag_fn(p)
                                         for p in self._last_seen_hosts]
                row["vbs"] = self.vbs_path.name
                row["log_last_line"] = log_last_line(self.log_path)
                if self._last_seen_mem:
                    # R5-1：最后采到的内存画像（判 OOM 用）
                    row["last_seen_memory"] = self._last_seen_mem
                # R8-4：工作进程画像 + WER 报告（R7-1 定性靠离线取证，这里
                # 直接把线索落进台账，省掉事后翻日志）
                row["worker_image"] = self.worker_image
                row["last_seen_worker"] = list(self._last_seen_worker)
                if self._last_seen_worker_mem:
                    row["last_seen_worker_memory"] = \
                        self._last_seen_worker_mem
                try:
                    wer = list(self._wer_fn() or [])
                except Exception:  # noqa: BLE001
                    wer = []
                if wer:
                    row["wer_reports"] = wer
            if outcome == "hung":
                dump = self.work_dir / (self.name + "_hang_" +
                                        time.strftime("%H%M%S") + ".dmp")
                for p in hosts:
                    d = self._dump_fn(p, dump)
                    if d:
                        row["dump"] = d
                        break
        try:
            with open(self.characterization_path, "a",
                      encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass
        return row

    def _hang_cleanup(self, attempt: int, reason: str, idle: float,
                      t_start: float, result: dict,
                      log_complete: bool, reason_kind: str = "") -> str:
        """挂起处置：判类（completed_no_return/hung）→ 表征 → 杀宿主。"""
        outcome = "completed_no_return" if log_complete else "hung"
        row = self._characterize(attempt, outcome, reason, idle, t_start,
                                 reason_kind)
        killed = {}
        for p in row.get("host_pids", []):
            killed[str(p)] = self._kill_fn(p)
        if killed:
            # 单 pid taskkill /T 有漏杀先例（I2 r2 wrap）：僵尸宿主留在
            # ROT 会让后续 rot 附着选错实例 → 按映像名兜底清场；仍存活
            # 则记 zombie（cold_boot 前置清场仍会拦截）。
            time.sleep(self.kill_settle)
            left = self._hosts()
            if left:
                self._kill_all()
                time.sleep(self.kill_settle)
                left = self._hosts()
            if left:
                row["zombie"] = left
            row["killed"] = killed
            self._rewrite_last_row(row)
        result["forced"] = True
        return outcome

    def _rewrite_last_row(self, row: dict) -> None:
        """把补写的行（killed 校验等）替换台账最后一行。"""
        try:
            path = self.characterization_path
            rows = path.read_text(encoding="utf-8").splitlines()
            if rows:
                rows[-1] = json.dumps(row, ensure_ascii=False)
                path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        except (OSError, ValueError):
            pass

    def _monitor(self, worker: threading.Thread, result: dict,
                 t_start: float, attempt: int) -> str:
        """返回 "done" | "hung"。挂起时完成诊断+转储+杀宿主。

        两判据：①日志惰性 ≥ idle_limit；②惰性 > 60s 期间宿主进程
        消失（实测遗留③变体：宿主自行退出而 COM worker 仍阻塞）→
        提前判定，省去剩余惰性等待。
        """
        last_size = log_size(self.log_path)
        last_change = time.time()
        hosts_gone_since: float | None = None
        checked_hosts = False
        while True:
            if not worker.is_alive():
                return "done"
            time.sleep(self.poll)
            if not worker.is_alive():
                return "done"
            size = log_size(self.log_path)
            if size != last_size:
                last_size = size
                last_change = time.time()
                hosts_gone_since = None
                checked_hosts = False
                continue
            idle = time.time() - last_change
            if hosts_gone_since is None and self._cpu_progress_ok():
                # R5-1：日志不动但 CPU 在涨 → 计算还在走，重置惰性计时
                last_change = time.time()
                self._cpu_progress += 1
                checked_hosts = False
                continue
            if idle > self.gone_check_after and not checked_hosts:
                checked_hosts = True
                alive = self._hosts_safe()
                if alive is None:
                    # 探针不可用/超时 → 未知：不判消失，稍后重探
                    hosts_gone_since = None
                    checked_hosts = False
                elif not alive:
                    hosts_gone_since = hosts_gone_since or time.time()
                else:
                    self._last_seen_hosts = list(alive)   # R4-2
                    hosts_gone_since = None
                    checked_hosts = False
            if hosts_gone_since is not None and \
                    time.time() - hosts_gone_since > self.gone_confirm:
                outcome = self._hang_cleanup(
                    attempt, "host process gone while worker "
                    "blocked (idle " + str(round(idle, 1)) + "s)",
                    idle, t_start, result,
                    log_complete=has_end_marker(self.log_path),
                    reason_kind="host_gone")
                return outcome
            if idle >= self.idle_limit:
                outcome = self._hang_cleanup(
                    attempt, "log idle " + str(round(idle, 1)) + "s >= "
                    + str(self.idle_limit) + "s", idle, t_start, result,
                    log_complete=has_end_marker(self.log_path),
                    reason_kind="log_idle")
                return outcome

    def _attempt(self, n: int) -> dict:
        t_start = time.time()
        result: dict = {}

        def _work():
            try:
                result["run"] = self._worker(str(self.vbs_path),
                                             self.timeout)
            except Exception as exc:  # noqa: BLE001
                result["run"] = {"ok": False, "error": repr(exc)}

        worker = threading.Thread(target=_work, daemon=True)
        worker.start()
        watcher = modal_watch.ModalWatcher() if self.watch_modals else None
        if watcher is not None:
            watcher.start()
        try:
            outcome = self._monitor(worker, result, t_start, n)
        finally:
            if watcher is not None:
                watcher.stop()
        if outcome == "done":
            worker.join(timeout=30)
            run = result.get("run", {})
            self._characterize(n, "ok" if run.get("ok") else "error",
                               "worker returned", 0.0, t_start)
            return {"outcome": "ok" if run.get("ok") else "error",
                    "run": run,
                    "modal_closures": watcher.closures if watcher else []}
        # hung / completed_no_return：宿主已杀，等 COM 调用随连接
        # 断开退出后冷启动重建（下一 flow 需要活宿主）
        worker.join(timeout=15)
        if outcome == "completed_no_return":
            try:
                self._boot()
            except Exception as exc:  # noqa: BLE001
                pass
            return {"outcome": "completed_no_return",
                    "run": {"ok": True, "backend": "rot",
                            "note": "log complete; COM call not "
                            "returned; host recycled"},
                    "rebooted": True}
        try:
            self._boot()
            result["rebooted"] = True
        except Exception as exc:  # noqa: BLE001
            result["boot_error"] = repr(exc)
        return {"outcome": "hung", "run": result.get("run", {}),
                "rebooted": result.get("rebooted", False),
                "boot_error": result.get("boot_error")}

    def execute(self) -> dict:
        attempts = []
        n = 0
        error_retries = 0
        while n < self.attempts:
            n += 1
            res = self._attempt(n)
            attempts.append(res)
            if res["outcome"] == "hung":
                continue
            if res["outcome"] == "error" \
                    and not has_end_marker(self.log_path) \
                    and error_retries < 3:
                # 宿主忙/未就绪类拒绝（ExecuteVBSWithFile 返回 False、
                # 日志不完整）：同宿主小憩后重跑；第二次仍败则判宿主
                # 状态已损（RPC_E_SERVERCALL_REJECTED 后不复位，I2
                # bam 实测）→ 冷启动重建。error 重试不消耗 attempts。
                error_retries += 1
                if error_retries == 2:
                    try:
                        self._boot()
                    except Exception:  # noqa: BLE001
                        pass
                time.sleep(self.error_retry_delay)
                n -= 1
                continue
            break
        last = attempts[-1]["outcome"]
        return {"name": self.name, "attempts": attempts,
                "outcome": last,
                "ok": last in ("ok", "completed_no_return")}
