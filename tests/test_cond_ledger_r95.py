#!/usr/bin/env python3
"""R9-4 / R9-5 回归：崩溃标记 + 条件账目口径。

* R9-4：host-gone 行若带 WER 报告，必须同时给 host_crash=True（可直接断言）；
* R9-5：tools/cond_ledger.py 的常量口径必须与 schemas/cond_types.json 现状一致。
"""

import importlib.util
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation.host_watchdog import FlowExecutor  # noqa: E402

LEDGER = ROOT / "tools" / "cond_ledger.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestConditionLedger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not LEDGER.is_file():
            raise unittest.SkipTest("tools/cond_ledger.py missing")
        cls.led = _load("cond_ledger_r95", LEDGER)

    def test_ledger_matches_documented_scope(self):
        led = self.led.ledger()
        self.assertEqual(led["universe"], 165)
        self.assertEqual(led["buckets"], {"exact_key": 92, "alias": 1,
                                          "boundary": 72})
        self.assertEqual(led["kinds"]["registry_key"], 90)
        self.assertEqual(led["kinds"]["member_locus"], 2)
        self.assertEqual(self.led.check(led), [])

    def test_annotation_is_outside_universe(self):
        led = self.led.ledger()
        self.assertEqual(led["annotations"], ["Thermoregulation"])
        self.assertEqual(sum(led["buckets"].values()), 165)


class TestHostCrashFlag(unittest.TestCase):
    def _run(self, wer):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "flow.log"
            log.write_text("start\ns141=0\n", encoding="utf-8")
            seen = []

            def host_fn():
                seen.append(1)
                return [4321] if len(seen) == 1 else []

            ex = FlowExecutor(log, log, name="r94", poll=0.05,
                              gone_check_after=0.05, gone_confirm=0.1,
                              idle_limit=30.0, host_fn=host_fn)
            ex._dump_fn = lambda p, d: None
            ex._kill_fn = lambda p: True
            ex._diag_fn = lambda p: {"pid": p}
            ex._mem_fn = lambda p: {"pid": p, "ws_mb": 1.0}
            ex._worker_pids_fn = lambda: []
            ex._wer_fn = wer
            stop = threading.Event()
            worker = threading.Thread(target=lambda: stop.wait(5.0),
                                      daemon=True)
            worker.start()
            try:
                ex._monitor(worker, {}, time.time(), 1)
            finally:
                stop.set()
                worker.join(timeout=2)
            rows = (Path(td) / "hang_characterization.jsonl").read_text(
                encoding="utf-8").splitlines()
            return json.loads(rows[-1])

    def test_wer_present_sets_host_crash(self):
        row = self._run(lambda: ["AppCrash_scFLOWpre_x"])
        self.assertTrue(row["host_crash"])
        self.assertEqual(row["wer_reports"], ["AppCrash_scFLOWpre_x"])

    def test_no_wer_means_no_crash_flag(self):
        row = self._run(lambda: [])
        self.assertNotIn("host_crash", row)
        self.assertNotIn("wer_reports", row)


if __name__ == "__main__":
    unittest.main()
