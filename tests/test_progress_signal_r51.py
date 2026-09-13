#!/usr/bin/env python3
"""R5-1 回归：进度信号（CPU 活性）+ 宿主内存取证。

背景：x_t 网格 170 s、STEP 网格 25 min 都不写日志，只按日志静默判活会误杀
正常计算；而「宿主已死 + 工作进程空转」又必须照旧判 host_gone。本文件把两条
互斥判据钉住。
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


def _write_log(p: Path, lines) -> Path:
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


class TestProcessProbes(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows only")
    def test_memory_of_self(self):
        mem = modal_watch.process_memory(os.getpid())
        self.assertIsNotNone(mem)
        self.assertGreater(mem["ws_mb"], 0.0)
        self.assertGreaterEqual(mem["peak_ws_mb"], mem["ws_mb"] - 0.1)
        self.assertIsNone(modal_watch.process_memory(999999))

    @unittest.skipUnless(sys.platform == "win32", "Windows only")
    def test_cpu_of_self(self):
        cpu = modal_watch.process_cpu_seconds(os.getpid())
        # 注意 0.0 是合法值，不能用 or 判空
        self.assertIsNotNone(cpu)
        self.assertGreaterEqual(cpu, 0.0)
        self.assertIsNone(modal_watch.process_cpu_seconds(999999))

    @unittest.skipUnless(sys.platform == "win32", "Windows only")
    def test_total_cpu_partial(self):
        self.assertIsNotNone(
            modal_watch.total_cpu_seconds([os.getpid(), 999999]))
        self.assertIsNone(modal_watch.total_cpu_seconds([999999]))


class TestProgressSignal(unittest.TestCase):
    def _executor(self, tmp: Path, host_fn, cpu_fn, **kw) -> FlowExecutor:
        log = _write_log(tmp / "flow.log", ["start", "s141=0"])
        opts = {"poll": 0.05, "gone_check_after": 0.05,
                "gone_confirm": 0.1, "idle_limit": 0.4}
        opts.update(kw)
        ex = FlowExecutor(log, log, name="r51", host_fn=host_fn,
                          cpu_fn=cpu_fn, **opts)
        ex._dump_fn = lambda p, d: None
        ex._kill_fn = lambda p: True
        ex._diag_fn = lambda p: {"pid": p}
        ex._mem_fn = lambda p: {"pid": p, "ws_mb": 123.0}
        return ex

    def _rows(self, ex: FlowExecutor):
        p = ex.work_dir / "hang_characterization.jsonl"
        if not p.is_file():
            return []
        return [json.loads(x) for x in
                p.read_text(encoding="utf-8").splitlines()]

    def test_cpu_progress_prevents_false_idle_kill(self):
        ticks = {"n": 0}

        def cpu_fn():
            ticks["n"] += 1
            return float(ticks["n"]) * 10.0     # 每次 +10 s 远大于 delta

        stop = threading.Event()
        worker = threading.Thread(target=lambda: stop.wait(1.2), daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                ex = self._executor(Path(td), lambda: [11], cpu_fn)
                outcome = ex._monitor(worker, {}, time.time(), 1)
                # 日志一直不动，但 CPU 在涨 → 不得判 hung
                self.assertEqual(outcome, "done")
                self.assertEqual(self._rows(ex), [])
                self.assertGreater(ex._cpu_progress, 0)
        finally:
            stop.set()
            worker.join(timeout=2)

    def test_host_gone_still_wins_over_cpu_progress(self):
        ticks = {"n": 0}

        def cpu_fn():
            ticks["n"] += 1
            return float(ticks["n"]) * 10.0

        seen = []

        def host_fn():
            seen.append(1)
            return [4321] if len(seen) == 1 else []

        stop = threading.Event()
        worker = threading.Thread(target=lambda: stop.wait(5.0), daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                ex = self._executor(Path(td), host_fn, cpu_fn)
                outcome = ex._monitor(worker, {}, time.time(), 1)
                self.assertEqual(outcome, "hung")
                row = self._rows(ex)[-1]
                self.assertEqual(row["reason_kind"], "host_gone")
                self.assertEqual(row["last_seen_hosts"], [4321])
                self.assertEqual(row["last_seen_memory"],
                                 [{"pid": 4321, "ws_mb": 123.0}])
        finally:
            stop.set()
            worker.join(timeout=2)

    def test_no_host_seen_disables_progress_path(self):
        ticks = {"n": 0}

        def cpu_fn():
            ticks["n"] += 1
            return float(ticks["n"]) * 10.0

        stop = threading.Event()
        worker = threading.Thread(target=lambda: stop.wait(5.0), daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                # 探针一直说没有宿主 → 不得靠 CPU 续命
                ex = self._executor(Path(td), lambda: [], cpu_fn)
                outcome = ex._monitor(worker, {}, time.time(), 1)
                self.assertEqual(outcome, "hung")
                self.assertEqual(ex._cpu_progress, 0)
        finally:
            stop.set()
            worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
