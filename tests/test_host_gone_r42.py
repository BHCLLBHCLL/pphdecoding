#!/usr/bin/env python3
"""R4-2 回归：宿主消失（host gone）事件的独立归因台账。

背景：R3-1 的 STEP mesh 失败在旧实现里只能读到 reason 字符串「host process
gone while worker blocked」，拿不到 pid（进程已消失）、也拿不到它最后跑到哪。
本文件钉住 R4-2 的字段：reason_kind / host_gone / last_seen_hosts /
log_last_line / vbs。
"""

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation.host_watchdog import FlowExecutor, log_last_line  # noqa: E402


def _write_log(p: Path, lines) -> Path:
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


class TestLogLastLine(unittest.TestCase):
    def test_last_nonempty_line(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_log(Path(td) / "a.log", ["start", "s141=0", "", "  "])
            self.assertEqual(log_last_line(p), "s141=0")

    def test_empty_and_missing(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(log_last_line(Path(td) / "nope.log"), "")
            p = _write_log(Path(td) / "empty.log", [""])
            self.assertEqual(log_last_line(p), "")


class TestHostGoneRow(unittest.TestCase):
    def _executor(self, tmp: Path, host_fn, **kw) -> FlowExecutor:
        log = _write_log(tmp / "flow.log", ["start", "s141=0"])
        opts = {"poll": 0.05, "gone_check_after": 0.05,
                "gone_confirm": 0.1, "idle_limit": 30.0}
        opts.update(kw)
        ex = FlowExecutor(log, log, name="r42", host_fn=host_fn, **opts)
        ex._dump_fn = lambda p, d: None
        ex._kill_fn = lambda p: True
        ex._diag_fn = lambda p: {"pid": p}
        return ex

    def _run_monitor(self, ex: FlowExecutor) -> dict:
        stop = threading.Event()
        worker = threading.Thread(target=lambda: stop.wait(5.0), daemon=True)
        worker.start()
        try:
            outcome = ex._monitor(worker, {}, time.time(), 1)
        finally:
            stop.set()
            worker.join(timeout=2)
        rows = (ex.work_dir / "hang_characterization.jsonl").read_text(
            encoding="utf-8").splitlines()
        return {"outcome": outcome, "row": json.loads(rows[-1])}

    def test_host_gone_row_carries_attribution(self):
        seen = []

        def host_fn():
            seen.append(1)
            return [1234] if len(seen) == 1 else []

        with tempfile.TemporaryDirectory() as td:
            ex = self._executor(Path(td), host_fn)
            res = self._run_monitor(ex)
            self.assertEqual(res["outcome"], "hung")
            row = res["row"]
            self.assertEqual(row["reason_kind"], "host_gone")
            self.assertTrue(row["host_gone"])
            self.assertEqual(row["last_seen_hosts"], [1234])
            self.assertEqual(row["last_seen_diag"], [{"pid": 1234}])
            self.assertEqual(row["log_last_line"], "s141=0")
            self.assertEqual(row["vbs"], "flow.log")
            self.assertEqual(row["host_pids"], [])
            self.assertIn("host process gone", row["reason"])

    def test_log_idle_row_is_tagged_and_not_host_gone(self):
        with tempfile.TemporaryDirectory() as td:
            ex = self._executor(Path(td), lambda: [7], idle_limit=0.3)
            res = self._run_monitor(ex)
            row = res["row"]
            self.assertEqual(res["outcome"], "hung")
            self.assertEqual(row["reason_kind"], "log_idle")
            self.assertNotIn("host_gone", row)
            self.assertEqual(row["host_pids"], [7])
            self.assertIn("log idle", row["reason"])

    def test_unknown_probe_neither_gone_nor_idle_tag(self):
        def _raiser():
            raise TimeoutError("probe timeout")

        with tempfile.TemporaryDirectory() as td:
            ex = self._executor(Path(td), _raiser, idle_limit=0.3)
            res = self._run_monitor(ex)
            self.assertEqual(res["row"]["reason_kind"], "log_idle")
            self.assertNotIn("host_gone", res["row"])


if __name__ == "__main__":
    unittest.main()
