#!/usr/bin/env python3
"""R8-4 回归：host-gone 台账补记**工作进程**画像 + WER 报告。

R7-1 的教训：真正崩的是工作进程 scFLOWpre_Bx64net，而探针与台账只盯 STpre，
于是「工作进程崩溃」被记成「宿主消失」。本文件钉住补记字段。
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

from automation import host_watchdog  # noqa: E402
from automation.host_watchdog import FlowExecutor, wer_reports  # noqa: E402


class TestWerLookup(unittest.TestCase):
    def test_returns_list_and_respects_limit(self):
        got = wer_reports()
        self.assertIsInstance(got, list)
        self.assertLessEqual(len(got), 6)
        self.assertLessEqual(len(wer_reports(limit=2)), 2)

    def test_unmatched_image_is_empty(self):
        self.assertEqual(wer_reports(images=("no_such_image_r84",)), [])


class TestHostGoneWorkerProfile(unittest.TestCase):
    def _executor(self, tmp: Path, host_fn, **kw) -> FlowExecutor:
        log = tmp / "flow.log"
        log.write_text("start\ns141=0\n", encoding="utf-8")
        opts = {"poll": 0.05, "gone_check_after": 0.05,
                "gone_confirm": 0.1, "idle_limit": 30.0}
        opts.update(kw)
        ex = FlowExecutor(log, log, name="r84", host_fn=host_fn, **opts)
        ex._dump_fn = lambda p, d: None
        ex._kill_fn = lambda p: True
        ex._diag_fn = lambda p: {"pid": p}
        ex._mem_fn = lambda p: {"pid": p, "ws_mb": 12.5}
        ex._worker_pids_fn = lambda: [555]
        ex._wer_fn = lambda: ["AppCrash_scFLOWpre_test"]
        return ex

    def _run(self, ex: FlowExecutor) -> dict:
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

    def test_worker_profile_and_wer_recorded(self):
        seen = []

        def host_fn():
            seen.append(1)
            return [4321] if len(seen) == 1 else []

        with tempfile.TemporaryDirectory() as td:
            res = self._run(self._executor(Path(td), host_fn))
            row = res["row"]
            self.assertEqual(row["reason_kind"], "host_gone")
            self.assertEqual(row["worker_image"], "scFLOWpre_Bx64net")
            self.assertEqual(row["last_seen_worker"], [555])
            self.assertEqual(row["last_seen_worker_memory"],
                             [{"pid": 555, "ws_mb": 12.5}])
            self.assertEqual(row["wer_reports"],
                             ["AppCrash_scFLOWpre_test"])
            self.assertEqual(row["last_seen_hosts"], [4321])

    def test_worker_sampled_only_while_host_alive(self):
        # 宿主一次都没探到时，不应留下工作进程画像（避免误导归因）
        with tempfile.TemporaryDirectory() as td:
            res = self._run(self._executor(Path(td), lambda: []))
            row = res["row"]
            self.assertEqual(row["reason_kind"], "host_gone")
            self.assertEqual(row["last_seen_worker"], [])
            self.assertNotIn("last_seen_worker_memory", row)

    def test_production_wer_lookup_does_not_raise(self):
        self.assertIsInstance(host_watchdog.wer_reports(), list)


if __name__ == "__main__":
    unittest.main()
