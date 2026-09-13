#!/usr/bin/env python3
"""R3-1 回归：宿主进程探针（Toolhelp32 + 故障安全语义）。

背景：原探针走 `powershell Get-Process` 且 20 s 上限，重网格计算期间
整机繁忙时超时，异常直接崩掉 flow；探针无输出还会被判成"宿主消失"
而误杀健康宿主（`_p12u_gate/hang_characterization.jsonl` 的 step_mesh 行）。
本文件把修法钉住：

* 枚举改走 Toolhelp32 快照（无子进程、毫秒级）；
* `host_pids()` 才做 PowerShell 回退，且仅当快照抛错时；
* `FlowExecutor._hosts_safe()` 把探针异常折成 `None`（未知），
  `_monitor` 对"未知"绝不判定宿主消失。
"""

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import modal_watch  # noqa: E402
from automation.host_watchdog import FlowExecutor  # noqa: E402

WIN = sys.platform == "win32"


class TestProcessProbes(unittest.TestCase):
    @unittest.skipUnless(WIN, "Toolhelp32 仅 Windows")
    def test_pid_alive_self_and_bogus(self):
        self.assertTrue(modal_watch.pid_alive(os.getpid()))
        self.assertFalse(modal_watch.pid_alive(999999))

    @unittest.skipUnless(WIN, "Toolhelp32 仅 Windows")
    def test_toolhelp_finds_self(self):
        stem = os.path.splitext(os.path.basename(sys.executable))[0]
        pids = modal_watch.host_pids_toolhelp(stem)
        self.assertIn(os.getpid(), pids)

    @unittest.skipUnless(WIN, "Toolhelp32 仅 Windows")
    def test_toolhelp_unknown_image_is_empty(self):
        self.assertEqual(
            modal_watch.host_pids_toolhelp("no_such_image_r31_zzz"), [])

    def test_host_pids_prefers_toolhelp(self):
        orig_t, orig_p = (modal_watch.host_pids_toolhelp,
                          modal_watch._host_pids_powershell)
        try:
            modal_watch.host_pids_toolhelp = lambda name="x": [42]
            def _boom(name="x"):
                raise AssertionError("PowerShell 回退不该被调用")
            modal_watch._host_pids_powershell = _boom
            self.assertEqual(modal_watch.host_pids("whatever"), [42])
        finally:
            modal_watch.host_pids_toolhelp = orig_t
            modal_watch._host_pids_powershell = orig_p

    def test_host_pids_falls_back_when_snapshot_fails(self):
        orig_t, orig_p = (modal_watch.host_pids_toolhelp,
                          modal_watch._host_pids_powershell)
        try:
            def _boom(name="x"):
                raise OSError("snapshot unavailable")
            modal_watch.host_pids_toolhelp = _boom
            modal_watch._host_pids_powershell = lambda name="x": [7]
            self.assertEqual(modal_watch.host_pids("whatever"), [7])
        finally:
            modal_watch.host_pids_toolhelp = orig_t
            modal_watch._host_pids_powershell = orig_p


class TestWatchdogProbeSemantics(unittest.TestCase):
    def _executor(self, host_fn, tmp: Path) -> FlowExecutor:
        log = tmp / "flow.log"
        log.write_text("start\n", encoding="utf-8")
        ex = FlowExecutor(log, log, name="r31_unknown", idle_limit=0.6,
                          poll=0.05, gone_check_after=0.05, host_fn=host_fn)
        ex._dump_fn = lambda p, d: None
        ex._kill_fn = lambda p: True
        ex._diag_fn = lambda p: {}
        return ex

    def test_hosts_safe_swallows_probe_failure(self):
        def _raiser():
            raise TimeoutError("probe timeout")
        with tempfile.TemporaryDirectory() as td:
            ex = self._executor(_raiser, Path(td))
            self.assertIsNone(ex._hosts_safe())
            ex2 = self._executor(lambda: [11, 22], Path(td))
            self.assertEqual(ex2._hosts_safe(), [11, 22])

    def test_unknown_probe_never_declares_host_gone(self):
        stop = threading.Event()
        worker = threading.Thread(target=lambda: stop.wait(5.0), daemon=True)
        worker.start()
        try:
            def _raiser():
                raise TimeoutError("probe timeout")
            with tempfile.TemporaryDirectory() as td:
                ex = self._executor(_raiser, Path(td))
                outcome = ex._monitor(worker, {}, time.time(), 1)
                self.assertEqual(outcome, "hung")
                rows = (Path(td) / "hang_characterization.jsonl" \
                        ).read_text(encoding="utf-8").splitlines()
                row = json.loads(rows[-1])
                self.assertNotIn("host process gone", row["reason"])
                self.assertIn("log idle", row["reason"])
        finally:
            stop.set()
            worker.join(timeout=2)

    def test_monitor_source_uses_safe_probe(self):
        src = (ROOT / "automation" / "host_watchdog.py").read_text(
            encoding="utf-8")
        self.assertIn("self._hosts_safe()", src)
        self.assertNotIn("if not self._hosts():", src)


if __name__ == "__main__":
    unittest.main()
